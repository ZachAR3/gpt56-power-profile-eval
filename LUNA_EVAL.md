# LUNA power-profile overhaul evaluation

Review date: 2026-07-11

## 1. Executive summary

The overhaul has a good intent and some useful safety improvements: it adds a
startup reconciliation path, keeps the GUI selection from being overwritten by
polling, bounds direct RAPL inputs, serializes new hardware operations through
the existing queue, and finally guards daemon management behind platform
detection. The commits are small and their messages explain the motivating
failures well.

The implementation is not ready to merge or release. The most serious problems
are:

- The `HonorToolsAdapter` contract is incompatible with the `honor-tools`
  version actually resolved in this checkout. A real profile apply returns a
  `PowerProfile.__init__()` error before it reaches hardware. This mismatch is
  pre-existing in the initial commit, but the overhaul still depends on it and
  has no compatibility or integration test.
- Startup stops and permanently masks both `power-profiles-daemon` and
  `intel_lpmd`, while the profile implementation still calls
  `powerprofilesctl set`. There is no unmask/restore path in service shutdown or
  uninstall. This changes system-wide power management even when the feature is
  unavailable and makes the intended PPD apply path self-contradictory.
- The new RAPL MSR encoder places the PL2 enable and time-window bits in a
  temporary high word and then shifts that word again. Those bits are masked
  out, so the delayed rewrite disables PL2 and loses its time window.
- The service reports a profile as successfully applied and persists it before
  the delayed MSR/EPP enforcement has run. The delayed boolean results are
  discarded, and no post-settle verification changes the result or health
  state.
- The performance profile asks for the `performance` governor, but the delayed
  EPP rewrite intentionally leaves every CPU in `powersave`. The API therefore
  reports a profile whose requested governor is not the final governor.

The fake-hardware tests pass, but they do not exercise the new systemd, MSR,
sysfs, dependency, or delayed-task behavior. The combination of a broken
resolved dependency, irreversible system-wide side effects, and an untested
hardware register encoder makes the current implementation unsafe to merge or
release.

Final verdict: **Unsafe to merge or release**.

## 2. Scope and methodology

### Repository and comparison base

- Branch reviewed: `main`
- Commit reviewed: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f`
  (`README: document Intel-only compatibility`)
- Working tree: clean at the start of review; branch tracks
  `origin/main` and is also the repository default branch.
- Default branch merge base: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f`
  (`HEAD` itself). Because the overhaul was committed directly to the default
  branch, that merge base produces an empty diff and is not a useful behavioral
  baseline.
- Behavioral comparison base selected: root commit
  `4d8994ab2eeb9595d1222ac4ad1789b8579a966f` (`Initial commit: Honor Control —
  D-Bus service and Qt6 GUI for Honor MagicBook laptops`). This is the
  defensible base for evaluating the full recent power-profile change set. The
  exact root hash was confirmed from Git history; abbreviated form is
  `4d8994a`.
- Reviewed change range: `4d8994a..34d31f9`.

Relevant commits in that range:

1. `15f4d66` — `Fix power profile application: RAPL, EPP, and UI snap-back`
2. `d391bb0` — `Clean up power profile code: safety, simplicity, correctness`
3. `7213294` — `Guard stop_competing_power_daemons behind platform detection`
4. `34d31f9` — `README: document Intel-only compatibility`

The range changes four tracked files: `README.md`,
`honor_control/backend/application.py`,
`honor_control/backend/hardware.py`, and
`honor_control/frontend/gui/pages/power.py`. No tests were changed by these
commits.

### Subsystems inspected

I reviewed the changed files and traced their call paths through:

- `ApplicationService.initialize`, `set_power_profile`,
  `_apply_power_profile`, `_delayed_power_rewrite`,
  `_reconcile_power_profile`, `_refresh_power`, and `_auto_switch_loop`.
- `HardwarePort`, `FakeHardware`, and `HonorToolsAdapter`, including platform
  detection, capability probing, `honor-tools` integration, sysfs access,
  systemd calls, HWP control, EPP writes, and direct RAPL MSR writes.
- Power models and validation in `honor_control/core/models.py`,
  `honor_control/core/validation.py`, and persisted state in
  `honor_control/backend/config_store.py`.
- `HardwareCommandQueue`, `RuntimeSupervisor`, `SnapshotStore`, and service
  startup/shutdown behavior.
- D-Bus API/codec/client/protocol, CLI, tray, GUI controller/state, and the
  power page to check propagation of desired/applied state and operation
  results.
- Systemd, polkit, install, uninstall, hardware-support, safety, architecture,
  and D-Bus documentation.
- Application, hardware, config, client, CLI, and GUI tests.
- The resolved `honor-tools` package in this checkout. A sibling
  `../honor-tools` source tree was also inspected only to understand the
  dependency API discrepancy; it is not part of this repository's reviewed
  change set.

### Commands and validation performed

The following commands were run from the repository root.

| Command | Result |
|---|---|
| `git status --short --branch` | Clean `main`, tracking `origin/main`. |
| `git branch -vv --all`, `git log --oneline --decorate --graph --all -n 80` | Confirmed branch/default-branch relationship and four relevant post-root commits. |
| `git diff --name-status 4d8994a..HEAD`, `git diff --numstat 4d8994a..HEAD` | Confirmed the four changed files and change size. |
| `git show`, `git blame`, and unified diffs for the relevant commits | Traced ownership and whether findings are new or pre-existing. |
| `rg` searches for power-profile, PPD, RAPL, EPP, governor, HWP, persistence, auto-switch, and UI paths | Traced surrounding consumers and documentation. |
| `./.venv/bin/python -m pytest -q` | **221 passed** in 8.63 seconds. |
| `bash scripts/smoke-test.sh` | **7 checks passed**, including compile, Ruff, imports, and pytest. The script used the available system pytest fallback because `.venv/bin/pytest` is absent. |
| `./.venv/bin/ruff check honor_control tests` | Passed: `All checks passed!` |
| `./.venv/bin/python -m compileall -q honor_control tests` | Passed. |
| `git diff --check 4d8994a..HEAD` | Passed. |
| `systemd-analyze verify packaging/systemd/honor-control.service` | Passed with no diagnostic output. |
| `./.venv/bin/python -m pip check` | Failed on an environment-level unrelated dependency: `glances 4.5.5 requires pyinstrument, which is not installed.` |
| `./.venv/bin/python -c '... import honor ...'` and `pip show honor-tools` | Resolved `honor-tools` version `0.1.0` from the local `.venv`. |
| Safe adapter probe calling `HonorToolsAdapter.apply_power_profile` with a temporary empty root | Returned `PowerProfile.__init__() got an unexpected keyword argument 'turbo_enabled'`; no hardware apply was reached. |
| Pure arithmetic check of the RAPL packing expression | Confirmed `pl2_enable=0` and `tw2_written=0` for a nonzero input time window. |
| Read-only `systemctl is-active/is-enabled`, `systemctl cat`, `powerprofilesctl get`, and `stat` checks | PPD was active/enabled, the reported PPD profile was `balanced`, `intel_lpmd` was enabled, `/dev/cpu/0/msr` was present, and HWP dynamic-boost sysfs was present. |

The first attempted `./.venv/bin/pytest -q` command could not start because
the executable is not present (`127`); the module invocation and smoke-test
fallback ran the full suite successfully. No type checker, `bandit`, or
`shellcheck` executable is installed, and the repository contains no CI or
type-check configuration.

I did not start the service, call `powerprofilesctl set`, stop or mask any
unit, write `/dev/cpu/*/msr`, write power sysfs, or interact with real hardware
in a mutating way. Consequently, claims about the final hardware state are
based on code, dependency behavior, and safe arithmetic/probe evidence rather
than a live profile application.

## 3. Architecture and behavior overview

### Components and ownership

The service is composed in `honor_control/backend/service.py`. In production it
runs as root on the system bus and constructs `HonorToolsAdapter`,
`ConfigStore`, `SnapshotStore`, `HardwareCommandQueue`, `RuntimeSupervisor`,
and `ApplicationService`. GUI, tray, and CLI clients use the D-Bus API rather
than instantiating hardware code.

The relevant ownership is:

- `ConfigStore` owns persisted desired power state at
  `/var/lib/honor-control/state.toml`. It stores the selected manual profile,
  profile definitions, and the AC/battery policy.
- `ApplicationService` owns use-case sequencing, mutation serialization,
  desired/applied bookkeeping, auto-switch polling, and snapshot projection.
- `HardwareCommandQueue` runs synchronous hardware/dependency calls on one
  daemon thread and applies a 10-second default command timeout.
- `HonorToolsAdapter` is the production boundary around `honor-tools`, plus
  the new direct systemd, sysfs, HWP, and MSR operations. `FakeHardware` is the
  test/session-bus implementation.
- `SnapshotStore` publishes immutable-ish typed snapshots with sequence
  numbers. `PowerSnapshot.observed_summary` carries raw dependency telemetry,
  while `desired_profile` and `applied_profile` are projected by the
  application service.
- D-Bus authorizes `SetProfile` as an active-user operation and profile
  definition/auto-switch configuration as admin operations. CLI, tray, and GUI
  all eventually invoke the same D-Bus/application path.

### Startup and state flow

Current production startup is:

1. Load persisted state.
2. Run `_refresh_all`, which detects the platform, probes capabilities, and
   reads power status through the serialized queue.
3. Call `stop_competing_power_daemons` through the queue. On a positively
   detected platform, this runs `systemctl stop` and `systemctl mask` for
   `power-profiles-daemon` and `intel_lpmd`, then writes
   `hwp_dynamic_boost=1` if the sysfs file exists.
4. `_reconcile_power_profile` compares the persisted manual desired profile to
   the profile name inferred from the initial PPD status. If the names differ,
   it calls `_apply_power_profile` without rewriting the desired state.
5. Start the refresh and auto-switch controllers.

The intended state distinction is sound in concept: persisted `desired_profile`
is user intent, `applied_profile` is the last service-applied profile, and
`observed_summary` is live hardware/dependency data. In practice, the
`applied_profile` field is set from a boolean result map before the delayed
rewrite and is then preferred over newly read hardware data, so the distinction
is not yet a verified state machine.

### Manual application path

`set_power_profile` validates the name against the persisted dynamic registry,
then `_apply_power_profile`:

1. Checks `Capability.writable` from `get_power_capability`.
2. Builds a plain dictionary containing PL1, PL2, governor, EPP, PPD profile,
   turbo, and maximum-performance settings.
3. Calls `HonorToolsAdapter.apply_power_profile` through the command queue.
4. Normalizes the dependency result into `governor_ok`, `epp_ok`, `ppd_ok`,
   `rapl_ok`, and `misc_ok`. All five must be true for success.
5. Sets `_last_applied_power_profile`, persists the manual desired name, and
   refreshes power state.
6. Schedules `_delayed_power_rewrite` after 0.5 seconds and immediately
   returns success. The delayed task separately writes the RAPL MSR and
   rewrites EPP/governor via sysfs.

`HonorToolsAdapter.apply_power_profile` constructs an external
`honor.config.PowerProfile` and calls `honor.power.apply_profile`. The external
library writes RAPL sysfs constraints, PPD, EPP, governors, and Intel-pstate
miscellaneous values. The new adapter code then tries to defeat external PPD
writes by directly touching `/dev/cpu/0/msr` and rewriting every discovered
CPU's EPP file.

### Auto-switch path

The auto-switch controller wakes every two seconds, refreshes power, reads the
discovered AC supply, and applies the configured AC or battery profile when the
source or policy tuple changes. It does not persist the temporary automatic
profile as the manual desired profile. A configured root-owned executable hook
is run after a successful application. Failed applications do not advance the
last source/policy tuple, so the same failure is retried on every two-second
poll.

### Error and recovery paths

Capability failures return `OperationResult.unavailable`; dependency result
maps return failed or partial results; queue exceptions are mapped by D-Bus.
Startup reconciliation catches its own apply exceptions and logs them so the
service can start. Delayed rewrite exceptions are also logged, but false
boolean returns are not treated as errors. There is no power-specific rollback
for a hardware success followed by a config-save failure, and no state/health
field for a delayed enforcement that failed after the user received success.

## 4. Findings

### Critical

#### PP-001 — The resolved `honor-tools` API makes every real profile apply fail

- Severity: Critical
- Confidence: High for the dependency resolved in this checkout; Medium for
  every possible external installation because the version range is broad.
- Category: Functional correctness / dependency compatibility
- Status: Pre-existing in the root commit; not fixed by the overhaul and still
  release-blocking.
- Affected paths and symbols:
  - `honor_control/backend/hardware.py:806-842`,
    `HonorToolsAdapter.apply_power_profile`
  - `honor_control/backend/application.py:328-347`,
    `ApplicationService._apply_power_profile`
  - `pyproject.toml:20-23`, `honor-tools>=0.1,<0.2`
  - Resolved dependency evidence:
    `.venv/lib/python3.14/site-packages/honor/config.py:25-34`

The adapter passes `turbo_enabled` and `max_perf_pct` into the external
`PowerProfile` constructor. The installed `honor-tools 0.1.0` constructor has
only `pl1_uw`, `pl2_uw`, `governor`, `epp`, and `ppd_profile`. A safe direct
probe of the adapter returned:

```text
{'error': "PowerProfile.__init__() got an unexpected keyword argument 'turbo_enabled'"}
```

The exception is caught by the adapter and converted to an error result, so
the application returns `power_apply_failed` and does not persist or report
the profile as applied. The same failure affects startup reconciliation and
automatic switching. Git blame shows the incompatible constructor call in
`4d8994a`, so this is not attributed to `15f4d66`; the recent work nevertheless
relies on the broken boundary and adds no version/API check.

Realistic impact: on a verified MRA platform with a writable capability, the
GUI and CLI appear to offer power profiles but every apply fails before any
profile mechanism is invoked. The repository's fake hardware tests cannot
detect this.

Recommended fix: define and enforce a real dependency contract. Either release
and require a version of `honor-tools` that contains these fields, or adapt to
the older API without exposing unsupported fields. Do not rely on an adjacent
unversioned source checkout. Prefer a typed adapter integration test that
installs the declared dependency and exercises the constructor/result shape.

Suggested tests:

- Run the adapter against the minimum and maximum supported dependency versions
  in isolated environments.
- Add a test with the actual declared dependency that calls
  `apply_power_profile` with a definition and asserts a normalized result, not
  an error.
- Add a compatibility test proving optional turbo/max-performance fields are
  either applied or explicitly reported unsupported.

#### PP-002 — Startup masks system power managers and never restores them

- Severity: Critical
- Confidence: High
- Category: System integration / privilege boundary / lifecycle
- Status: Newly introduced by `15f4d66`, changed from `disable` to permanent
  `mask` by `d391bb0`, and platform-guarded by `7213294`.
- Affected paths and symbols:
  - `honor_control/backend/application.py:155-165`,
    `ApplicationService.initialize`
  - `honor_control/backend/hardware.py:844-896`,
    `HonorToolsAdapter.stop_competing_power_daemons`
  - `honor_control/backend/hardware.py:597-619`,
    `get_power_capability`
  - `scripts/uninstall-local.sh:19-48`
  - External apply path observed in
    `.venv/lib/python3.14/site-packages/honor/power.py:175-192`

Every production initialization calls the new method through the queue. On a
positive platform match it runs `systemctl stop` and `systemctl mask` for both
`power-profiles-daemon` and `intel_lpmd`, then enables HWP dynamic boost. The
mask is not `--runtime`, no prior active/enabled/masked state is recorded, and
neither `ApplicationService.shutdown` nor `uninstall-local.sh` calls
`systemctl unmask` or restores a previously active daemon.

The same implementation still relies on `honor.power.apply_profile`, whose
PPD step runs `powerprofilesctl set` and whose `ppd_ok` is required for a full
application. Stopping/masking the service that owns that D-Bus command is a
direct ownership contradiction. The review host showed PPD active and enabled
before review; no stop/mask operation was executed.

Realistic impact: starting Honor Control on a supported laptop can disable the
system's normal power manager, then cause profile applies to fail or report
partial because PPD is unavailable. Removing Honor Control can leave PPD
masked, so the machine remains without its normal power policy after the
application is gone. The new platform guard prevents this on clearly
unsupported hardware, which is good, but it does not make the ownership or
restore model safe on supported hardware.

Recommended fix: choose one owner for CPU power policy. The least risky path is
to keep PPD running and integrate with it, while applying only mechanisms that
are explicitly supported. If disabling competing daemons is unavoidable, make
it an explicit, capability-gated ownership mode that records each unit's
original state, uses a reversible runtime mechanism, restores state on normal
shutdown, and has an uninstall/crash-recovery path. Do not call PPD after
intentionally disabling it.

Suggested tests:

- Mock systemd for supported, unsupported, missing-unit, timeout, and failed
  command cases; assert no command runs on unsupported or unavailable power
  capability.
- Verify original enabled/active/masked state is restored on normal shutdown,
  failed startup, service crash recovery, and uninstall.
- Run a disposable-VM integration test that checks PPD remains usable after
  starting and removing the service.

### High

#### PP-003 — The direct RAPL encoder drops PL2 enable and time-window bits

- Severity: High
- Confidence: High
- Category: Hardware correctness / power and thermal safety
- Status: Newly introduced by `15f4d66` and retained by `d391bb0`.
- Affected paths and symbols:
  - `honor_control/backend/hardware.py:961-1036`,
    `HonorToolsAdapter.write_rapl_msr`
  - In particular, `honor_control/backend/hardware.py:1007-1019`

The code builds `hi` as though it were already in the upper 32-bit half of
the MSR, placing PL2 enable at bit 47 and the time window at bits 49-55, and
then shifts the whole value by 32:

```python
hi = pl2_units | (1 << 47) | (tw2 << 49)
val = (lo | (hi << 32)) & 0xFFFFFFFFFFFFFFFF
```

PL2 power units in `hi` are correctly shifted into global bits 32-46, but
`1 << 47` becomes bit 79 and `tw2 << 49` becomes bits 81-87 before the
64-bit mask. A pure arithmetic check of the exact expression returned
`pl2_enable=0` and `tw2_written=0` from a nonzero `tw2`.

The delayed rewrite therefore overwrites the package limit register with PL2
disabled and its time window cleared. Depending on the processor's existing
state and kernel behavior, the requested burst limit is not enforced or the
power behavior differs from the selected profile. This is especially serious
because the method is intended to bypass the sysfs path and is treated as the
final enforcement step.

Recommended fix: construct the 64-bit register with global positions exactly
once, for example by placing `pl2_units` at `<< 32`, the PL2 enable bit at
`<< 47`, and the PL2 time window at `<< 49`, with explicit field masks. Decide
and document clamp/enable preservation instead of silently rebuilding those
bits. Check the number of bytes written and use `try/finally` for descriptors.

Suggested tests:

- Unit-test the encoder with a mocked MSR file and nonzero PL1/PL2/time-window
  values; assert every field in the resulting 64-bit value.
- Test invalid bounds, short reads, short writes, `OSError`, and descriptor
  cleanup without touching `/dev/cpu/0/msr`.
- On the verified laptop, read back the MSR and both RAPL sysfs trees after an
  apply in a controlled hardware test.

#### PP-004 — Apply success is returned before delayed enforcement, and delayed failures are lost

- Severity: High
- Confidence: High
- Category: State synchronization / error handling / observability
- Status: Newly introduced by `15f4d66` and modified by `d391bb0`.
- Affected paths and symbols:
  - `honor_control/backend/application.py:348-381`,
    `ApplicationService._apply_power_profile`
  - `honor_control/backend/application.py:391-421`,
    `ApplicationService._delayed_power_rewrite`
  - `honor_control/backend/application.py:1132-1135`,
    `ApplicationService._refresh_power`

After the initial dependency result is all true, the service sets
`_last_applied_power_profile`, persists the desired name, refreshes the
snapshot, schedules a task, and returns `OperationResult.success`. The task
then awaits two methods that return `bool`, but neither return value is
checked. Exceptions are only logged, and there is no readback or subsequent
snapshot update that changes `applied`, `details`, or service health.

The service's `applied_profile` projection also prefers the in-memory profile
name over the newly read hardware status. It can consequently continue to
display a successful profile after the delayed MSR or EPP write returned
`False`, or after an external daemon re-clobbered the setting. Automatic hooks
run immediately after `_apply_power_profile` returns, before delayed
enforcement has completed.

Realistic impact: a permissions error on `/dev/cpu/0/msr`, a missing EPP file,
an EBUSY sequence that exhausts retries, or a shutdown during the 0.5-second
window leaves the CPU with only the initial dependency state. The user sees a
successful, persisted profile and an automatic hook can act on a state that is
not yet final.

Recommended fix: make enforcement a defined state transition. Either await a
bounded post-PPD enforcement and verification before returning success, or
return an explicit pending result and expose a pending/failure state until the
delayed phase verifies. Treat `False` as a partial/failure result, retain the
previous applied profile on failure, record per-mechanism details, and verify
governor, EPP, RAPL, PPD, turbo, and max-performance values after settling.

Suggested tests:

- Use a fake hardware port whose delayed MSR or EPP method returns `False` or
  raises; assert no false success/persistence and that the previous applied
  profile remains visible.
- Assert automatic hooks do not run before the final enforcement state is
  verified.
- Exercise delayed failure after a successful initial apply and verify the
  snapshot, operation details, and health signal.

#### PP-005 — The performance profile ends with `powersave`, not its requested governor

- Severity: High
- Confidence: High for the documented Intel-pstate path
- Category: Profile semantics / hardware state
- Status: Newly introduced by `15f4d66`.
- Affected paths and symbols:
  - `honor_control/backend/hardware.py:898-959`,
    `HonorToolsAdapter.rewrite_epp`
  - `honor_control/core/models.py:296-305`, built-in performance definition
  - `honor_control/backend/application.py:329-336`, definition propagation

The delayed method writes `powersave` to every CPU before writing EPP. It only
restores the requested governor when `governor != "performance"`; for the
performance profile it logs that it is intentionally keeping `powersave`.
The built-in profile and the GUI/CLI contract still say its governor is
`performance`, and the initial external apply writes that governor before the
delayed method changes it.

The code may be making a reasonable Intel-pstate tradeoff for one target
machine, but it is not a correct application of the declared profile and the
effective state is not exposed to callers. A user selecting a custom profile
with `governor="performance"` receives the same mismatch.

Recommended fix: decide whether EPP or the governor is authoritative for each
driver. Encode that decision in the profile capability/result model. If EPP
must win, change the profile definition and UI to describe the effective
governor; otherwise restore `performance` and verify the resulting EPP, or use
a driver-specific sequence that supports both.

Suggested tests:

- Mock sysfs for a performance apply and assert the final governor and EPP
  values, not just that writes occurred.
- Add a capability/driver matrix for Intel-pstate modes and ensure the API
  reports an effective state when the requested combination is impossible.

#### PP-006 — Startup reconciliation trusts a PPD profile label instead of hardware state

- Severity: High
- Confidence: High
- Category: Persistence / recovery / state synchronization
- Status: Newly introduced by `15f4d66`.
- Affected paths and symbols:
  - `honor_control/backend/application.py:1013-1045`,
    `ApplicationService._reconcile_power_profile`
  - `honor_control/backend/hardware.py:778-802`,
    `HonorToolsAdapter.read_power`

`read_power` derives `applied_profile` solely by mapping the PPD string
(`power-saver`, `balanced`, or `performance`) to a built-in name. It does not
compare RAPL values, per-CPU governors, EPP, turbo, or maximum-performance
settings. `_reconcile_power_profile` returns without applying anything when
that derived name equals the persisted desired name.

Realistic impact: if RAPL was overwritten by `intel_lpmd` or another writer but
PPD still reports `performance`, a service restart sees matching names and
skips reconciliation. After the new startup daemon action, the service can
remain in a state where the UI says the desired profile is applied but the
35 W/55 W limits or EPP are not present. Custom profiles are even less
identifiable because their PPD mode can be the same as a built-in profile.

Recommended fix: make reconciliation compare the complete desired definition
to per-mechanism observed values, or conservatively reapply the desired profile
after establishing ownership on every startup. Treat unknown or incomplete
observations as needing reconciliation. Keep the custom profile identity
separate from the PPD label.

Suggested tests:

- Seed persisted `performance`, return PPD `performance` with mismatched RAPL,
  EPP, or governor values, and assert that startup reapplies.
- Repeat with a custom profile that shares `ppd_profile="balanced"` with the
  built-in profile.
- Test a service restart after an interrupted delayed rewrite.

#### PP-007 — Daemon cleanup can exceed the hardware queue deadline and abort startup

- Severity: High
- Confidence: High
- Category: Concurrency / lifecycle / timeout handling
- Status: Newly introduced by `d391bb0`.
- Affected paths and symbols:
  - `honor_control/backend/application.py:162-165`
  - `honor_control/backend/hardware.py:874-885`
  - `honor_control/backend/command_queue.py:26,68-123`

`initialize` invokes daemon cleanup through `HardwareCommandQueue.run` using
the default 10-second timeout. The cleanup performs up to four sequential
`systemctl` calls, each with its own five-second timeout: stop and mask for two
units. The worst-case bounded work is therefore 20 seconds, not counting HWP
file I/O. If systemd is slow or unavailable, the queue can time out at 10
seconds while its daemon thread continues executing the remaining commands.
`initialize` does not catch this exception, so service startup unwinds and the
service process exits through its `finally` shutdown path.

Realistic impact: a transient systemd/D-Bus stall, a stopped system manager, or
one slow unit can make Honor Control fail to start. The queue is then poisoned
while the worker still has system-management work, complicating restart and
possibly leaving only one of the two units changed.

Recommended fix: do not put an unbounded multi-command system-management
transaction behind the default hardware deadline. Use one explicit overall
deadline longer than the maximum, or better, a dedicated reversible systemd
ownership component with one bounded operation. Catch cleanup failure during
startup, publish degraded health, and avoid claiming that competing daemons
were stopped when return codes were ignored.

Suggested tests:

- Mock each `systemctl` call to consume five seconds and prove startup does not
  unexpectedly terminate or poison the queue.
- Test partial stop/mask failure and verify cleanup/health behavior.
- Test queue shutdown while cleanup is still running.

#### PP-008 — Fire-and-forget rewrites are not generation-safe or fully owned

- Severity: High
- Confidence: Medium
- Category: Concurrency / lifecycle / reentrancy
- Status: Newly introduced by `15f4d66` and only partially addressed by
  `d391bb0`.
- Affected paths and symbols:
  - `honor_control/backend/application.py:126`, `_pending_power_task`
  - `honor_control/backend/application.py:371-373`, task creation
  - `honor_control/backend/application.py:183-184`, shutdown cancellation
  - `honor_control/backend/application.py:406-418`, separate queue operations

The service stores only the most recently created delayed task. Applying
profiles repeatedly overwrites that reference without cancelling or awaiting
older tasks. Shutdown cancels only the latest task. Each delayed rewrite also
performs RAPL and EPP as separate queue commands without holding the application
mutation lock or associating the task with the latest profile generation.

A possible sequence is: profile A's RAPL rewrite completes, profile B is
applied, then A's EPP rewrite runs after B's apply and before B's delayed task.
The machine temporarily has a mixed A/B state. If shutdown or a queue failure
prevents B's delayed task from completing, the stale A write can be the final
one. An older task already inside a queue operation is also not cancelled by
`shutdown`.

Recommended fix: represent one pending enforcement generation, cancel and
await the prior task before scheduling a new one, and make the RAPL/EPP phase a
single serialized hardware operation. Recheck the generation before committing
results and manage the task through the supervisor or an explicit lifecycle
owner.

Suggested tests:

- Apply profiles A and B with controllable barriers and assert the final writes
  are exclusively B.
- Cancel/shutdown with multiple pending rewrites and assert no stale hardware
  operation occurs after shutdown.
- Test a new apply while the previous delayed operation is waiting on the
  queue.

### Medium

#### PP-009 — Capability probing is much weaker than the mechanisms being changed

- Severity: Medium
- Confidence: High
- Category: Capability modeling / partial failure
- Status: The weak probe is pre-existing; the new startup side effects worsen
  its consequences.
- Affected paths and symbols:
  - `honor_control/backend/hardware.py:597-619`,
    `HonorToolsAdapter.get_power_capability`
  - `honor_control/backend/application.py:162-165`
  - `honor_control/backend/hardware.py:868-896`
  - `docs/hardware-support.md:23-28`

The capability reports `SUPPORTED` when `honor-tools` imports, the platform
allowlist matches, and `powerprofilesctl` exists. It does not probe or report
the availability, write access, or driver identity for RAPL sysfs, EPP,
governors, `/dev/cpu/0/msr`, Intel-pstate HWP, or the two systemd units. The
documentation says every mechanism is checked separately, but the code does
not do that. More importantly, startup cleanup is gated only by the platform,
not by this capability result.

Realistic impact: on a verified-looking machine with a missing MSR device,
unusable EPP, no PPD service, or no write access, the service can still mask
`intel_lpmd` and enable HWP while reporting the profile feature unavailable or
while every apply is partial. The user loses an external power manager without
receiving a usable replacement.

Recommended fix: use a typed per-mechanism capability result with explicit
status/reason/resource fields. Gate ownership changes on the minimum complete
capability set and distinguish optional PPD, RAPL, EPP, governor, and misc
mechanisms in the apply result.

Suggested tests:

- Build capability fixtures for each missing path, denied permission, driver,
  and daemon state.
- Assert startup performs no global side effect when the feature is unavailable
  or only partially supported.
- Verify optional mechanism failures are reported as partial rather than
  silently treated as success.

#### PP-010 — Failed auto-switch applies retry forever every two seconds

- Severity: Medium
- Confidence: High
- Category: Error recovery / performance
- Status: Pre-existing behavior documented in `OVERHAUL_PLAN.md:527-531` and
  not fixed by the recent power commits; the new daemon masking can make the
  failure persistent and expensive.
- Affected paths and symbols:
  - `honor_control/backend/application.py:1327-1377`,
    `ApplicationService._auto_switch_loop`

The loop advances `last_ac` and `last_policy` only after a successful apply.
If PPD is masked, the dependency result is partial on every attempt, so the
same policy is applied again every two seconds. Each attempt can rewrite all
RAPL sysfs trees, governors, EPP, and pstate values before discovering the PPD
failure. There is no backoff, failure latch, or retry-on-new-event policy.

Realistic impact: a failed auto-switch causes repeated privileged hardware
writes, repeated subprocess/D-Bus work, and log churn while the user sees a
persistent desired/applied mismatch. It can also keep the serialized queue
busy for interactive battery/fan operations.

Recommended fix: separate source-event detection from apply retry state. Record
the failed transition, back off, and retry only on a new stable source event,
explicit user request, or bounded timer. Emit the failure in the snapshot.

Suggested tests:

- Make the fake adapter return a partial result and assert only one attempt is
  made per source transition.
- Assert a new AC/battery event resets the backoff and a policy edit triggers
  one new attempt.
- Test queue pressure while auto-switch is in a failed state.

#### PP-011 — Hardware success and persistence failure can leave contradictory state

- Severity: Medium
- Confidence: High
- Category: Persistence / partial failure
- Status: Pre-existing in the root application flow; relevant to the overhaul's
  desired/applied persistence guarantees.
- Affected paths and symbols:
  - `honor_control/backend/application.py:353-366`,
    `ApplicationService._apply_power_profile`
  - `honor_control/backend/application.py:481-498`,
    `ApplicationService.save_power_profile`
  - `honor_control/backend/config_store.py:401-430`, `ConfigStore.update`

The service applies hardware before saving a manual desired profile. If the
atomic state save fails after the hardware call succeeds, the exception escapes
without a structured result, rollback, or a snapshot refresh. The CPU can be
running the new profile while disk still records the old profile. Saving an
active custom definition has the inverse problem: the definition is persisted
before its re-application, so a failed apply can be reported as failure even
though the new definition is already durable.

Realistic impact: a full/read-only state filesystem or interrupted write causes
the user to receive an internal error while hardware has changed. A restart
then reconciles the old desired state, potentially changing the CPU back. The
in-memory `_last_applied_power_profile` can also disagree with the persisted
state during the remainder of the process.

Recommended fix: define an explicit transaction policy. Persist a pending
desired generation before hardware apply and commit applied state only after
verification, or retain the old desired state and return a structured partial
result with observed/applied details when persistence fails. Apply the same
policy to active definition edits.

Suggested tests:

- Inject a state-save failure after a successful fake hardware apply and assert
  the returned result, snapshot, and persisted state are consistent.
- Inject an apply failure after a successful profile-definition save and assert
  the UI/API clearly distinguish saved definition from unapplied hardware.
- Test restart reconciliation from each interrupted phase.

#### PP-012 — New high-risk paths have no meaningful production-adapter tests

- Severity: Medium
- Confidence: High
- Category: Test coverage / release validation
- Status: Newly introduced test gap; no test files changed by the overhaul.
- Affected paths and symbols:
  - `honor_control/backend/hardware.py:844-1044`
  - `honor_control/backend/application.py:155-165,348-421,1013-1045`
  - `tests/test_hardware.py:160-256`
  - `tests/test_application.py:119-281`
  - `tests/test_gui.py:127-165`

The 221 passing tests primarily exercise `FakeHardware`, whose power apply,
delayed EPP, delayed RAPL, and daemon-stop methods return success without
modeling state. Hardware tests cover platform/battery discovery but do not
cover the new systemctl, HWP, EPP, or MSR code. Application tests do not assert
delayed failure, startup reconcile verification, task cancellation, or save
failure. The GUI tests cover preservation of profile-editor fields but not the
new active-combo dirty behavior. There is no dependency API compatibility test.

This is why the suite can pass while the safe adapter probe fails and while the
RAPL encoder's bit loss remains undetected.

Recommended fix: add deterministic unit tests with injected systemd, sysfs,
MSR, and dependency ports; keep real-hardware tests as a separate manual gate.
Do not make the fake return unconditional success for mechanisms whose failure
semantics are central to the feature.

Suggested tests are listed under each finding. The minimum release gate should
include dependency compatibility, RAPL encoding/readback, systemd ownership
cleanup, delayed-task cancellation, per-mechanism failure, startup
reconciliation, and GUI active selection.

### Low

#### PP-013 — New power I/O bypasses the adapter's injectable root and duplicates ownership

- Severity: Low
- Confidence: High
- Category: Architecture / maintainability / testability
- Status: Newly introduced by `15f4d66`.
- Affected paths and symbols:
  - `honor_control/backend/hardware.py:444-455`, `HonorToolsAdapter._root`
  - `honor_control/backend/hardware.py:889-895,921-945,961-1044`

The adapter already accepts `root_path` for discovery and test fixtures, but
the new power code hard-codes `/sys/devices/system/cpu`,
`/dev/cpu/0/msr`, and absolute sysfs paths, and imports `subprocess` directly
inside the operation. The new paths therefore cannot be exercised through the
existing temporary-root test strategy. The adapter now also owns three
different power-policy mechanisms while delegating the original sequence to
`honor-tools`, making ownership and ordering difficult to reason about.

Recommended fix: introduce small injected ports for sysfs/cpufreq, MSR, and
systemd ownership, or pass a platform-scoped power capability object. Keep one
layer responsible for sequencing and expose a typed result rather than a raw
dictionary of booleans. This is a targeted boundary refactor, not a rewrite.

Suggested tests:

- Run all power adapter tests against a temporary root and mocked MSR file.
- Test the systemd port without invoking the host system manager.
- Add a typed result contract test between the adapter and application service.

#### PP-014 — The new AMD compatibility statement does not match actual behavior

- Severity: Low
- Confidence: High
- Category: Documentation / platform contract
- Status: Newly introduced by `34d31f9`.
- Affected paths and symbols:
  - `README.md:11-16`
  - `honor_control/backend/hardware.py:43-50,505-547,597-609`

The README says AMD-based Honor laptops will fail safely with “sysfs-only EPP.”
The actual positive platform allowlist requires the MRA-XXX product and Intel
Core Ultra/Meteor Lake markers. An AMD model does not match, so
`get_power_capability` returns unsupported and the application never schedules
the EPP rewrite. That is a safe outcome, but it is not the documented
sysfs-only behavior.

Recommended fix: document AMD as entirely unsupported until an AMD-specific
capability path exists, or implement and test the claimed partial behavior.
Keep the exact verified platform/CPU matrix in the support documentation.

Suggested tests:

- Add platform fixtures for verified Intel, unknown Intel, and AMD identities;
  assert the advertised capability/status for each.

## 5. Test and validation assessment

### What is covered

The suite gives useful coverage of the surrounding architecture:

- Dynamic profile names, custom profile persistence, auto-switch policy
  persistence, manual-vs-automatic desired state, basic invalid-name handling,
  and fake successful application are tested in `tests/test_application.py`.
- Config state round-tripping and profile field validation are tested in
  `tests/test_config_store.py`.
- D-Bus/client snapshot codecs and editable profile fields are tested in
  `tests/test_client.py`.
- CLI argument parsing for profile fields and auto-switch options is tested in
  `tests/test_cli.py`.
- GUI construction and preservation of unsaved editor values are tested in
  `tests/test_gui.py`.
- Platform allowlisting and non-`BAT0`/AC path discovery are tested in
  `tests/test_hardware.py`.
- The queue, supervisor, validation, polkit, and import/smoke paths are covered
  elsewhere in the suite.

### Important missing behavior

The tests do not prove the behavior most affected by the overhaul:

1. Actual `honor-tools` API compatibility and result normalization.
2. Correct MSR field encoding, PL2 enablement, time windows, short I/O, and
   descriptor cleanup.
3. Systemd stop/mask behavior, original-state capture, unmask/restore, and
   no-op behavior for unsupported/unavailable platforms.
4. HWP dynamic-boost policy and restoration.
5. EPP readback, governor final state, per-CPU partial failures, and offline CPU
   handling.
6. Delayed task failures, rapid successive profiles, shutdown cancellation,
   queue timeouts, and stale generations.
7. Post-settle readback and the distinction between desired, applied, and
   observed state.
8. Startup reconciliation where the PPD name matches but RAPL/EPP/governor
   values do not.
9. Persistence failures after hardware success and active custom-definition
   apply failures.
10. Auto-switch backoff, stable-transition/debounce behavior, and the effect of
    a failed PPD apply.
11. The active profile combo's unsaved selection during snapshot refresh; the
    new GUI fix is not directly tested.

### Weak or misleading coverage

`FakeHardware.apply_power_profile` returns all mechanism flags as true and its
delayed methods do not model any actual RAPL/EPP state. The application tests
therefore prove orchestration only on the all-success path. The auto-switch
test checks that calls stop repeating after success, but not the failure path
that currently repeats forever. The changelog and README describe fake-hardware
verification/CI, but this repository has no CI workflow and no production
adapter test covering the new privileged paths.

### Prioritized additional test plan

1. Add a dependency-contract test using the declared installation and a second
   supported dependency version.
2. Extract/test a pure RAPL encoder and a mocked MSR port, including all bit
   fields and failure cleanup.
3. Inject a systemd port and test platform/capability gating, timeout,
   partial-failure, restore, uninstall, and crash-recovery behavior.
4. Add application tests for delayed false/exception results, pending state,
   post-settle verification, persistence failure, and startup mismatch.
5. Add generation/cancellation tests for A/B profile races and shutdown.
6. Add failure/backoff tests for auto-switch.
7. Add a Qt test that selects a different active profile, sends an unchanged
   snapshot, and verifies the selection remains until apply succeeds or is
   explicitly reset.
8. Add a manual hardware gate on the exact MRA-XXX laptop for sysfs/MSR
   readback, PPD interaction, thermal/power behavior, reboot reconciliation,
   and service uninstall restoration.

## 6. Architecture and maintainability assessment

### What is structurally sound

The high-level boundary is appropriate: frontends use D-Bus, the root service
owns hardware, synchronous calls go through one queue, and desired state is
stored separately from GUI settings. The new methods also use the existing
queue rather than writing sysfs from an asyncio task directly. The profile
registry is extensible enough for custom definitions, and the application
validates profile names before calling the adapter.

The platform guard added in `7213294` is an important correction. An unknown
machine does not execute the new daemon or HWP writes, and the capability path
returns unsupported rather than treating a generic platform object as safe.

### Separation of responsibilities and coupling

Power policy is currently split across three owners:

1. `honor-tools` applies the original RAPL/EPP/governor/PPD sequence.
2. `HonorToolsAdapter` independently manages systemd, HWP, MSR bits, and a
   second EPP sequence.
3. `ApplicationService` schedules enforcement and decides which booleans mean
   “applied.”

The boundaries communicate through an untyped `dict[str, Any]` and raw boolean
flags. This makes a dependency API mismatch easy to miss and makes it unclear
which layer owns rollback, verification, or final governor semantics. A
targeted refactor is justified: define a typed `PowerDefinition`, a typed
`PowerApplyResult` with per-mechanism status/details, and one coherent adapter
sequence. Keep the existing application/queue architecture; do not rewrite
the whole service.

### State-management design

The desired/applied/observed model is a good design goal, but the implementation
does not yet make it authoritative. `applied_profile` is an in-memory name
assigned before delayed work and often preferred over observations. Delayed
work is not a first-class pending state. Startup reconciliation compares a
single PPD label rather than the profile definition. A small explicit state
machine—`desired`, `pending`, `applied`, `partial`, `failed`, with per-mechanism
observations—would make UI, CLI, auto-switch, and restart behavior consistent.

### Platform and dependency extensibility

The implementation is intentionally Intel/MRA-specific, which is acceptable
for an alpha product if the capability contract is honest. The hard-coded
paths, HWP assumption, direct MSR layout, and PPD race workaround should live
behind a platform-scoped power backend. Adding another Intel driver or AMD
platform should be a new capability implementation, not a series of conditionals
inside `HonorToolsAdapter`.

The existing `root_path` injection should be extended to the new power paths,
and systemd should be represented by an injectable port. This would make the
privileged behavior testable without weakening the production privilege
boundary.

### Concurrency and lifecycle

The single worker queue is a strong foundation, but the delayed task bypasses
the application mutation lock and is not supervised as a lifecycle controller.
The queue serializes individual calls, not the logical profile-enforcement
transaction. A single latest-generation task owned by the supervisor would
reduce stale writes, shutdown races, and repeated work.

The auto-switch loop should also consume a stable AC-source event or at least
maintain explicit debounce/backoff state. Polling every two seconds is simple,
but retrying full privileged applies forever is not a robust controller policy.

### Maintainability conclusion

A targeted refactor is warranted before release, not a full rewrite. The
existing D-Bus/application/config/snapshot layers can remain. The concrete
refactor should be limited to the power backend contract, capability model,
enforcement transaction, systemd ownership, and tests. This directly improves
correctness, makes future platform support possible, and removes the need for
frontends to infer whether a profile is really final.

## 7. Positive observations

- The commits are narrowly scoped and the commit messages identify the three
  motivating symptoms: GUI snap-back, asynchronous EPP changes, and competing
  RAPL writers.
- The active-profile GUI fix is directionally correct. It blocks programmatic
  combo updates, tracks user changes, and allows snapshot refreshes to update
  the applied profile only when there is no pending user selection.
- New synchronous operations are sent through `HardwareCommandQueue`, so the
  direct MSR, EPP, systemd, and HWP calls do not run on the asyncio event loop
  thread.
- The service retains the user's desired profile in persisted state and adds a
  startup reconciliation path instead of relying only on transient in-memory
  selection.
- The direct RAPL code rejects values outside a bounded 3–150 W range before
  opening the MSR device, and the cleanup commit correctly recognizes that the
  package-scoped register only needs CPU 0 on the target laptop.
- The `7213294` platform guard is materially safer than the original
  unconditional systemd behavior: non-Honor/unknown hardware does not have
  PPD or `intel_lpmd` touched by this method.
- The application already distinguishes full and partial dependency results,
  and the GUI/CLI use structured operation results instead of assuming every
  backend call succeeded.
- The profile registry and persisted state preserve custom profiles and their
  editable fields through the D-Bus/client/GUI/CLI path, and the legacy config
  migration limitation is at least documented in `CHANGELOG.md`.

## 8. Prioritized remediation plan

### Must fix before merge or release

1. **Repair and pin the dependency contract.** Make the declared installation
   compatible with `HonorToolsAdapter`, decide the supported `honor-tools` API,
   and add an integration test using that exact dependency.
2. **Remove unsafe daemon ownership as currently implemented.** Keep PPD alive
   if the apply path calls it, or replace the whole path with a direct,
   explicitly owned mechanism. If external daemons must be stopped, capture
   and restore their state on all exits and uninstall, and gate the action on a
   complete capability result.
3. **Correct and test RAPL MSR encoding.** Fix PL2 field placement, preserve or
   explicitly set all required bits, check short I/O, close descriptors on all
   paths, and validate against the exact target CPU/MSR behavior.
4. **Make enforcement and reporting coherent.** Do not return/persist full
   success before delayed enforcement is verified. Check boolean results,
   report per-mechanism failures, update snapshots/health, and define the
   effective governor/EPP semantics.
5. **Make startup reconciliation compare real state.** Reapply on incomplete or
   mismatched observations, including custom profile definitions, rather than
   trusting the PPD label.
6. **Fix lifecycle and timeout behavior.** Own one generation-safe delayed
   task, prevent A/B interleaving, and keep daemon cleanup within an explicit
   overall deadline without allowing startup to fail silently.
7. **Fix persistence and auto-switch failure semantics.** Define the order and
   recovery policy for hardware versus state saves and add backoff/latching for
   repeated failed automatic transitions.

### Should fix soon afterward

1. Replace raw power dictionaries with typed definitions/results and add
   per-mechanism capabilities.
2. Inject sysfs/MSR/systemd ports so all new privileged paths are testable
   without host mutation.
3. Add the prioritized unit, integration, and GUI tests from Section 5, plus a
   CI job that installs the declared dependencies and runs them.
4. Update hardware-support, safety, README, and D-Bus documentation to state
   the actual ownership model, effective governor behavior, and AMD status.
5. Add explicit diagnostics for PPD/`intel_lpmd` ownership and delayed
   enforcement failures.

### Optional cleanup and longer-term improvements

1. Replace polling auto-switch with a shared debounced power-source event when
   the platform layer supports it.
2. Add a platform-specific maximum safe RAPL envelope rather than treating a
   generic 150 W ceiling as universally safe.
3. Keep a manual hardware test matrix for new Intel kernel versions and
   `intel_pstate` behavior.
4. Remove duplicated dependency-level power behavior once the adapter owns a
   stable typed backend contract.

### Validation after fixes

1. Run the complete unit/GUI/CLI suite, Ruff, compile checks, dependency
   compatibility matrix, and systemd packaging verification.
2. Run mocked failure tests for every power mechanism, persistence failure,
   queue timeout, cancellation, and systemd restore path.
3. In a disposable VM, verify PPD and `intel_lpmd` state before/after service
   start, restart, crash, uninstall, and purge.
4. On the exact supported MRA-XXX laptop, read back RAPL MSR fields, both RAPL
   sysfs trees, every CPU governor/EPP, PPD state, HWP, turbo, and
   `max_perf_pct` after each built-in and representative custom profile.
5. Test reboot/startup reconciliation, AC transitions, failed automatic
   applies, GUI selection persistence, and service shutdown while a rewrite is
   pending.
6. Review the final operation result and snapshot semantics with a real
   partial-apply case before release approval.

## 9. Final verdict

**Unsafe to merge or release.**

The minimum changes needed to advance to any merge-ready level are: repair the
resolved `honor-tools` API contract; remove or fully own/reverse the PPD and
`intel_lpmd` masking; correct the PL2 MSR encoding; make delayed enforcement
generation-safe and part of verified result semantics; reconcile against actual
mechanism state; and add deterministic tests for those paths. Until those are
complete, the passing fake-hardware suite is not evidence that the power
profile system is safe or functional on real hardware.
