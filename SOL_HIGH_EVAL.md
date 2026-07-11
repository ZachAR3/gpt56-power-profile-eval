# 1. Executive summary

The power-profile overhaul is **unsafe to merge or release** in its current form.
It contains useful intentions—startup reconciliation, explicit task ownership,
platform gating, a GUI dirty flag, and bounds checks—but the central runtime path
is internally contradictory and the new direct-MSR implementation is incorrect.

The most serious issues are:

1. Startup stops and masks `power-profiles-daemon` (PPD), while the existing
   profile application implementation still requires `powerprofilesctl set` to
   succeed. A normal profile apply therefore becomes partial and the new delayed
   RAPL/EPP rewrite is never scheduled.
2. The 64-bit `MSR_PKG_POWER_LIMIT` value is assembled incorrectly. PL2's enable
   and time-window bits are shifted out of the 64-bit value; a targeted mocked
   test confirmed that the method returns success while writing PL2 disabled.
3. The packaged systemd service removes `CAP_SYS_RAWIO`, but Linux requires that
   capability to open `/dev/cpu/N/msr`. The direct-MSR path therefore cannot work
   under the shipped service unit even if `/dev/cpu/0/msr` exists.
4. The new RAPL/EPP rewrite happens after the API has already reported success,
   persisted desired state, and recorded the profile as applied. Boolean failures
   are ignored, and overlapping delayed tasks can reapply an older profile after
   a newer request.
5. Starting the service permanently masks two system power-management daemons,
   without recording prior state or restoring it on shutdown or uninstall.

These are not cosmetic or merely theoretical defects. Together they defeat the
overhaul's stated purpose, can leave a machine in a partially modified power
state, misreport that state to clients, and persistently alter unrelated system
services. No tests were added in the overhaul commits, and the current tests do
not exercise the new production methods or their lifecycle interactions.

**Final verdict: Unsafe to merge or release.**

# 2. Scope and methodology

## Repository and comparison range

- Repository reviewed: `/home/zach/Desktop/productivity/misc/HonorTools/honor-control`
- Branch: `main`
- Reviewed commit: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f`
- Default remote branch: `origin/main`
- `merge-base(HEAD, origin/main)`: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f`
- Working tree before creating this report: clean
- Historical comparison base selected:
  `4d8994ab2eeb9595d1222ac4ad1789b8579a966f`

The normal merge-base comparison is empty because the overhaul has already been
committed directly to the repository's default branch and `HEAD == origin/main`.
I therefore used the initial implementation, which is the parent of the first
power-overhaul commit, as the most defensible review base. The reviewed range is
`4d8994a..34d31f9`.

Relevant commits, in order:

- `15f4d66` — Fix power profile application: RAPL, EPP, and UI snap-back
- `d391bb0` — Clean up power profile code: safety, simplicity, correctness
- `7213294` — Guard stop_competing_power_daemons behind platform detection
- `34d31f9` — README: document Intel-only compatibility

The range changes four files: `README.md`,
`honor_control/backend/application.py`,
`honor_control/backend/hardware.py`, and
`honor_control/frontend/gui/pages/power.py` (326 insertions and 7 deletions).
No test or packaging file changed in the range.

## Files and subsystems inspected

The review covered the changed files and their surrounding paths, including:

- Application lifecycle, profile mutation, startup reconciliation, periodic
  refresh, AC auto-switching, script hooks, and shutdown in
  `honor_control/backend/application.py`.
- Hardware capability detection, DMI/CPU allowlisting, live power reads,
  `honor-tools` adaptation, direct sysfs writes, MSR writes, fake hardware, and
  root-path test isolation in `honor_control/backend/hardware.py`.
- Serialization/timeouts in `honor_control/backend/command_queue.py`.
- Desired-state persistence, schema parsing, profile registry, and validation in
  `honor_control/backend/config_store.py`, `honor_control/core/models.py`, and
  `honor_control/core/validation.py`.
- D-Bus API/codec/authorization, clients, CLI, Qt controller/page behavior, fan
  profile coupling, and tray/dashboard consumers.
- Service hardening, installer/uninstaller, polkit policy, documentation, and all
  repository tests.
- The sibling `honor-tools` source that the installer packages and the adapter
  invokes, especially `../honor-tools/honor/power.py` and
  `../honor-tools/honor/config.py`.

## Commands and results

All commands were read-only or wrote only temporary build/test data. No hardware
mutation, `systemctl` mutation, or system configuration change was performed.

- Git inspection: `git status --short --branch`, `git branch -vv`,
  `git symbolic-ref refs/remotes/origin/HEAD`, `git merge-base HEAD origin/main`,
  `git log --oneline --decorate --graph`, per-commit `git show`, range `git diff`,
  `git blame`, and `git diff --check 4d8994a..HEAD`.
  - Result: repository and range established; diff check passed.
- `git fsck --no-progress --no-dangling`
  - Result: passed.
- `.venv/bin/python -m pytest --collect-only -q`
  - Result: 221 tests collected.
- `timeout 120s .venv/bin/python -m pytest -vv -x`
  - Result: failed on the first application test after 80.48 seconds. A trivial
    fake-hardware queue command timed out; see the limitation below.
- `timeout 30s .venv/bin/python -m pytest -vv -x tests/test_backend.py`
  - Result: 6 tests passed, then
    `TestCommandQueue.test_run_executes_function` failed because a lambda that
    returns `42` timed out after 10 seconds.
- Individually bounded test-file runs:
  - `test_cli.py`: 12 passed.
  - `test_config_store.py`: 15 passed.
  - `test_core.py`: 59 passed.
  - `test_gesture_runtime.py`: 6 passed.
  - `test_gui.py`: 13 passed.
  - `test_hardware.py`: 23 passed.
  - `test_polkit.py`: 8 passed.
  - `test_validation.py`: 8 passed.
  - `test_client.py`: 23 passed, then the final fake-client test timed out in
    application initialization for the same queue reason.
  - In total, 173 individual tests were observed passing; this is not a full
    suite pass.
- `PYTHONPATH=../honor-tools .venv/bin/python -m pytest -q
  ../honor-tools/tests/test_power_profile.py ../honor-tools/tests/test_config.py`
  - Result: 18 passed.
- `.venv/bin/ruff check honor_control tests`
  - Result: passed.
- `.venv/bin/ruff check .`
  - Result: failed on six pre-existing issues in
    `Reverse engineering/capture_subscribers_driver.py`; none is in the overhaul.
- `.venv/bin/ruff format --check .`
  - Result: four pre-existing files would be reformatted, including two tests;
    none of the reported production files is part of the power overhaul except
    no changed power file was identified.
- `.venv/bin/python -m compileall -q honor_control tests`
  - Result: passed.
- `systemd-analyze verify packaging/systemd/honor-control.service`
  - Result: passed.
- `.venv/bin/python -m pip check`
  - Result: failed because an unrelated globally visible `glances` installation
    lacks `pyinstrument`; the repository packages themselves were not identified
    as conflicting.
- `.venv/bin/python -m build --sdist --wheel --outdir
  /tmp/honor-control-review-dist`
  - Result: could not run because the venv does not provide the `build` module's
    executable entry point (`No module named build.__main__`).
- Targeted mocked MSR encoding diagnostic (patched `os.open/read/write`; no real
  device access): called `write_rapl_msr(35_000_000, 55_000_000)` with power unit
  1 W/unit, PL1 time field 10, and PL2 time field 20.
  - Result:
    `ok=True value=0x0000003700158023 pl1_enabled=1 pl2_enabled=0 tw1=10 tw2=0`.

## Limitations and assumptions

- The workspace's outer `HonorTools` directory contains several projects and is
  not itself a Git worktree; `honor-control` is the relevant nested repository.
- The venv runs Python 3.14.6, pytest 9.1.1, and pytest-asyncio 1.4.0. In this
  sandbox, the hardware worker executes work and calls `loop.call_soon_threadsafe`,
  but the event-loop callback never runs. This is reproducible with a standalone
  `HardwareCommandQueue.run("x", lambda: 42)`. It is a pre-existing queue/runtime
  or sandbox compatibility issue, not introduced by this overhaul, but it blocks
  end-to-end test validation here. The repository declares Python `>=3.11`, so
  Python 3.14 is nominally supported by its metadata.
- No real Honor laptop or hardware-in-the-loop environment was available. The
  report does not claim live validation of RAPL, EPP, PPD timing, or thermal
  behavior.
- No destructive diagnostic was attempted. In particular, I did not run the new
  daemon-stopping method, write sysfs, or access a real MSR device.
- The sibling `honor-tools` directory is not a Git worktree in this workspace,
  but its source is explicitly copied by `scripts/install-local.sh:73-84` and is
  the implementation invoked at runtime, so it is valid integration evidence.

# 3. Architecture and behavior overview

## Main components

- `ApplicationService` owns use-case orchestration. D-Bus calls and internal
  controllers ultimately call its profile methods.
- `ConfigStore` owns immutable desired state in
  `/var/lib/honor-control/state.toml`: the selected manual profile, editable
  definitions, and AC/battery auto-switch policy.
- `SnapshotStore` publishes desired, applied, and observed information to D-Bus
  clients and Qt frontends.
- `HardwareCommandQueue` serializes synchronous hardware and subprocess work on
  one worker thread with a default ten-second deadline.
- `HonorToolsAdapter` gates production writes on a verified `HONOR`/`MRA-XXX` and
  Meteor Lake identity, then delegates the initial profile application to
  `honor.power.apply_profile`.
- `FakeHardware` supports application tests but makes every new power helper
  succeed unconditionally.
- `PowerPage` edits definitions, selects an active profile, configures automatic
  switching, and displays snapshot telemetry. The new active-combo dirty flag
  preserves a user's pending selection across refreshes.

## Startup and state ownership

`initialize()` loads persisted state, concurrently refreshes platform,
capabilities, and all observed domains, then serially calls
`stop_competing_power_daemons()` and `_reconcile_power_profile()`.

Desired state belongs to `ConfigStore`. Live power observations come from
`honor.power.get_status()`, which reads RAPL, governors, EPP, PPD, turbo, and
`max_perf_pct`. `HonorToolsAdapter.read_power()` reduces the applied-profile
identity to a mapping of PPD's current profile. In-process
`_last_applied_power_profile`, once non-empty, overrides that observed identity in
every later snapshot.

The overhaul also creates external state that is not represented in either
store: the enabled/masked state of PPD and `intel_lpmd`, plus HWP dynamic boost.
That state is process-external and persistent, but has no owner, snapshot field,
or restoration policy.

## Manual profile application

1. The requested name is validated against the persisted dynamic registry.
2. The power capability requires `honor-tools`, a verified platform, and a
   `powerprofilesctl` binary.
3. The profile definition is translated into `honor.config.PowerProfile` and
   passed to `honor.power.apply_profile()` through the serialized queue.
4. The dependency writes RAPL sysfs, temporarily selects `powersave`, invokes
   `powerprofilesctl set`, writes EPP, writes the requested governor, and writes
   turbo/max-performance controls.
5. The adapter collapses dependency result maps into five booleans. Only if all
   five are true does the application set `_last_applied_power_profile`, persist
   manual desired state, refresh the snapshot, and return success.
6. After that success has already been decided, a fire-and-forget task sleeps
   0.5 seconds, writes package RAPL directly through `/dev/cpu/0/msr`, and
   rewrites governor/EPP via sysfs.

## Automatic selection and persistence

The auto-switch controller polls every two seconds. It refreshes power to obtain
the AC source, chooses `on_ac` or `on_battery`, calls the same internal apply
method without replacing the manual desired profile, and optionally runs a
validated root-owned transition command. A successful transition is deduplicated
until AC state or policy changes. Failed transitions are retried every poll.

On restart, `_reconcile_power_profile()` compares persisted desired identity with
the PPD-derived applied identity. It reuses the normal apply method only when the
two names differ.

## OS/hardware integration and recovery

- PPD and `intel_lpmd` are stopped and persistently masked with `systemctl`.
  Return codes are discarded.
- HWP dynamic boost is best-effort enabled through Intel pstate sysfs.
- RAPL PL1/PL2 are written to MSR `0x610` after reading power units from `0x606`.
- EPP rewrite enumerates CPU directories globally, switches governors to
  `powersave`, retries EPP writes, performs an unvalidated read, and restores a
  non-performance governor.
- Delayed failures are only logged if an exception is raised. Normal `False`
  return values do not affect the operation result, persisted state, snapshot,
  health, or retry behavior.
- Shutdown cancels only the task currently stored in `_pending_power_task`; it
  does not await cancellation and does not restore daemon or HWP state.

# 4. Findings

## Critical

### PP-001 — Startup disables a dependency that every successful profile apply still requires

- **Severity:** Critical
- **Confidence:** High
- **Category:** Functional correctness; lifecycle; integration
- **Origin:** Newly introduced by the overhaul
- **Affected code:**
  - `honor_control/backend/application.py:155-165` (`initialize`)
  - `honor_control/backend/application.py:317-389` (`_apply_power_profile`)
  - `honor_control/backend/hardware.py:806-842` (`apply_power_profile`)
  - `honor_control/backend/hardware.py:844-885`
    (`stop_competing_power_daemons`)
  - Runtime dependency `../honor-tools/honor/power.py:175-229`

**Problem.** Initialization stops and masks PPD before any later user apply. The
dependency's `apply_profile()` still calls `powerprofilesctl set`, and the adapter
defines `ppd_ok` as exactly that command returning success. The application
requires `ppd_ok` along with every other mechanism before it reports success or
schedules the new direct RAPL/EPP rewrite.

**Evidence and reasoning.** The call order is explicit at application lines
163-165. The mask prevents service activation. The dependency's `_set_ppd()` at
lines 175-194 returns false for a nonzero command, and `apply_profile()` exposes
that value at line 218. Adapter line 836 preserves it, and application lines
353-373 schedule the delayed rewrite only inside the all-true branch.

**Failure scenario / impact.** Start the shipped service on a supported laptop,
then select Performance. The initial sysfs/governor/EPP/turbo writes can partially
occur, but `powerprofilesctl set performance` fails because PPD is masked. The
client receives `power_partial_apply`; desired state is not persisted; direct MSR
and delayed EPP are never attempted. Hardware is left partially changed and the
feature added to make 35 W/55 W “stick” does not run.

**Recommended fix.** Choose one coherent ownership model. Either keep PPD running
and coordinate with it, or remove PPD from the direct-control transaction and its
success criteria. If Honor Control owns direct controls, implement that as an
explicit backend strategy rather than calling a dependency that still requires
PPD. Do not mask PPD as a hidden prerequisite.

**Tests proving the fix.** Add an integration test with a fake `systemctl`/PPD
state machine: initialize, apply each built-in and a custom profile, and assert a
fully verified result. Test PPD-present, PPD-absent, and PPD-managed strategies
separately. Assert no mechanism is changed after the transaction reports failure,
or assert/document structured partial state and recovery.

### PP-002 — Direct MSR encoding silently writes PL2 disabled and loses its time window

- **Severity:** Critical
- **Confidence:** High
- **Category:** Hardware correctness; unsafe bit manipulation
- **Origin:** Newly introduced by the overhaul
- **Affected code:** `honor_control/backend/hardware.py:961-1036`, especially
  `1004-1019`

**Problem.** `hi` is intended to be the upper 32-bit field, but it is populated
with already-global bit positions `(1 << 47)` and `(tw2 << 49)` and then shifted
left by another 32 bits. The final 64-bit mask discards those fields. Only
`pl2_units`, shifted into bits 32+, remains. PL2 enable bit 47 is zero and its time
window in bits 49-55 is zero.

**Evidence and reasoning.** A no-hardware mocked call using 35 W/55 W and nonzero
PL1/PL2 time fields returned `True` but produced:

```text
value=0x0000003700158023 pl1_enabled=1 pl2_enabled=0 tw1=10 tw2=0
```

The expected layout is lower-field bits 14:0/15/16/23:17 and upper-field bits
46:32/47/48/55:49. The code mixes local-upper-field and global bit numbering.

**Failure scenario / impact.** The delayed rewrite reports success in logs, but
the CPU's second package power limit is disabled. Burst behavior does not match
the selected profile, and the method has modified a privileged CPU register while
claiming to have set both limits.

**Recommended fix.** Build two validated 32-bit fields using local positions and
shift the PL2 field once, or build the complete 64-bit value using global
positions without a second shift. Preserve only intentionally retained bits,
including documented lock/clamp/time semantics. Verify exact eight-byte reads and
writes and use context-managed descriptors.

**Tests proving the fix.** Add table-driven unit tests for multiple power-unit
exponents and boundary wattages. Decode the written value and assert PL1/PL2
units, both enable bits, clamp policy, both time fields, untouched reserved bits,
and exact write length. Test short read/write and locked-register behavior.

## High

### PP-003 — The shipped service sandbox cannot open the MSR device

- **Severity:** High
- **Confidence:** High
- **Category:** Packaging/runtime permissions
- **Origin:** Newly exposed by introducing direct MSR access without updating the service contract
- **Affected code:**
  - `honor_control/backend/hardware.py:988-1036`
  - `packaging/systemd/honor-control.service:19-35`, especially `23-25`

**Problem.** The service unit limits the capability bounding set to
`CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH`. It excludes `CAP_SYS_RAWIO`. The Linux x86
MSR driver's `msr_open()` rejects a caller without `CAP_SYS_RAWIO`, even when the
caller UID is root. The relevant upstream source is the Linux kernel's
[`arch/x86/kernel/msr.c`](https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/kernel/msr.c).

**Evidence and reasoning.** The production method opens `/dev/cpu/0/msr` three
times. The service's bounding set cannot be expanded by the process, and
`NoNewPrivileges=true` reinforces that boundary. The method catches the resulting
`OSError` and returns false; PP-004 then discards that false result.

**Failure scenario / impact.** Under the actual installed unit, every delayed MSR
rewrite fails with `EPERM`. The UI and D-Bus caller have already received success,
so users see a profile that cannot deliver the promised direct RAPL behavior.

**Recommended fix.** First decide whether direct raw-MSR writes are acceptable at
all. Prefer a kernel/sysfs interface or a narrowly scoped, auditable helper when
possible. If raw MSR is retained, explicitly add and document `CAP_SYS_RAWIO`,
probe the device and kernel-lockdown status as part of capability reporting, and
accept the security-hardening regression consciously. Do not advertise full
power capability when that required mechanism is unavailable.

**Tests proving the fix.** Run a non-mutating capability/open probe inside a
transient unit using the exact shipped hardening settings. Add packaging tests
that compare required backend resources/capabilities against the unit. Keep the
actual register write as an explicit manual hardware release gate.

### PP-004 — The operation reports success before the new required work runs, ignores normal failures, and permits stale rewrites

- **Severity:** High
- **Confidence:** High
- **Category:** State synchronization; concurrency; error handling
- **Origin:** Newly introduced by the overhaul
- **Affected code:** `honor_control/backend/application.py:181-186`, `353-421`

**Problem.** Application success, `_last_applied_power_profile`, and desired-state
persistence are finalized before the 0.5-second RAPL/EPP work. The delayed method
does not inspect the boolean results of either helper. A returned `False` is a
normal completion and produces no warning. Each apply overwrites the single task
reference without cancelling or sequencing the prior task.

**Evidence and reasoning.** Lines 353-366 commit state. Lines 371-373 start the
task. Lines 408-419 await queue calls but discard results. A second successful
apply within the settle window leaves the first task alive; both can later write
their captured definitions. Shutdown cancels only the most recently referenced
task and does not await it.

**Failure scenario / impact.** A user quickly selects Silent and then Performance.
Both calls report success. Depending on scheduling and queue contention, the old
Silent delayed task can write its RAPL/EPP after the later apply, while snapshots
continue to say Performance. Separately, missing `/dev/cpu/0/msr` returns false
with no change to the successful result.

**Recommended fix.** Make settle/rewrite/readback part of one serialized profile
transaction and return only after required mechanisms verify. If latency requires
an asynchronous API, represent `pending/applying/verified/failed` explicitly and
publish completion later. Use a monotonically increasing generation and cancel
and await superseded work. Never let an older generation write after a newer one.

**Tests proving the fix.** Use deterministic clocks/barriers to issue two profiles
inside 0.5 seconds and assert only the newest definition reaches hardware. Inject
`False`, exceptions, timeouts, cancellation, shutdown, and readback mismatch for
each mechanism. Assert returned status, persisted desired state, applied identity,
and snapshot details remain consistent.

### PP-005 — Service startup persistently masks system power daemons with no ownership or restoration policy

- **Severity:** High
- **Confidence:** High
- **Category:** System lifecycle; recovery; platform integration
- **Origin:** Newly introduced by the overhaul
- **Affected code:**
  - `honor_control/backend/application.py:155-165`, `181-186`
  - `honor_control/backend/hardware.py:844-896`
  - `scripts/uninstall-local.sh:19-49`

**Problem.** Every service initialization on a matched platform runs `systemctl
stop` and `systemctl mask` for PPD and `intel_lpmd`, regardless of whether a user
has selected a special profile. The method suppresses stdout/stderr, ignores
return codes, records no prior active/enabled/masked state, and exposes no result.
Neither application shutdown nor uninstall unmasks or restarts either service.
HWP dynamic boost is likewise changed without restoration.

**Evidence and reasoning.** A systemd mask is persistent configuration, not
process-local state. The docstring says it is “cleanly reversible with systemctl
unmask,” but no code performs that reversal. The uninstall script removes Honor
Control while leaving the masks behind.

**Failure scenario / impact.** Installing and starting Honor Control disables the
desktop's standard power-profile service and Intel's low-power-mode service across
reboots. Stopping or uninstalling Honor Control does not restore them, leaving the
machine with neither manager. Failures are silent, so behavior can vary depending
on which individual action succeeded.

**Recommended fix.** Avoid changing unrelated service enablement/mask state at
runtime. If exclusive ownership is truly required, make it an explicit,
administrator-approved install option with conflict metadata and documented
rollback. Record exact prior state and restore it transactionally on disable and
uninstall. Return and publish per-action outcomes.

**Tests proving the fix.** Model all prior daemon states (missing, inactive,
active, disabled, masked), partial `systemctl` failures, restart, crash, upgrade,
and uninstall. Assert the final state is either unchanged or exactly restored.

## Medium

### PP-006 — Startup reconciliation compares only a PPD label, not the profile definition or hardware state

- **Severity:** Medium
- **Confidence:** High
- **Category:** Persistence; recovery; state modeling
- **Origin:** Newly introduced reconciliation built on a pre-existing weak applied-state model
- **Affected code:**
  - `honor_control/backend/application.py:1013-1045`, `1102-1145`
  - `honor_control/backend/hardware.py:778-804`

**Problem.** Reconciliation skips whenever the PPD-derived string equals desired
profile identity. It does not compare PL1, PL2, governor, EPP, turbo, or
`max_perf_pct`. It also runs after PPD is stopped but uses the snapshot captured
before that stop. Edited built-in profiles remain indistinguishable from factory
profiles because both map to the same PPD name.

**Failure scenario / impact.** After reboot, PPD reports `performance`, so desired
`performance` is considered reconciled even if firmware reset RAPL, the built-in
definition was edited, or PPD applied different limits. Later refreshes cannot
query a masked PPD and may report no observed applied profile.

**Recommended fix.** Reconcile a complete, platform-applicable desired definition
against live observations after the system's power backend has reached its final
startup state. Identity equality may be an optimization only after every required
mechanism verifies.

**Tests proving the fix.** Cover same-name/wrong-RAPL, same-name/wrong-EPP,
same-name/edited-definition, custom profiles sharing a PPD mode, PPD unavailable,
and reboot-reset behavior.

### PP-007 — New production methods bypass the adapter's root abstraction and make isolated tests capable of touching the host

- **Severity:** Medium
- **Confidence:** High
- **Category:** Abstraction leakage; test safety; portability
- **Origin:** Newly introduced by the overhaul
- **Affected code:** `honor_control/backend/hardware.py:444-459`, `844-1044`

**Problem.** Existing adapter filesystem access is rooted through `self._root` and
`_rooted()` so tests can use a temporary tree. The new methods use host-global
`systemctl`, `glob('/sys/...')`, `pathlib.Path('/sys/...')`, and
`/dev/cpu/0/msr` directly. A test adapter whose fake DMI matches MRA-XXX can pass
the platform guard and then invoke real host `systemctl` or sysfs/MSR paths.

**Failure scenario / impact.** A future integration test builds a supported fake
sysroot and calls initialization to verify daemon behavior. Platform detection is
based on the fake root, but daemon mutation targets the real host. This defeats
the established safety boundary and is why the new code currently has no useful
filesystem-level tests.

**Recommended fix.** Inject filesystem roots and a typed service-manager/process
port. Keep raw MSR access behind an injectable interface. Production wiring may
select real implementations; tests must select fakes that cannot escape the temp
root.

**Tests proving the fix.** Use a supported temporary DMI/sysfs tree and fake
service manager, then assert every requested path and action remains within the
fake boundary. Add a test that fails if `subprocess.run`, global globbing, or real
`/dev` access occurs.

### PP-008 — Daemon shutdown can exceed the command queue deadline and prevent service startup

- **Severity:** Medium
- **Confidence:** High
- **Category:** Timeout composition; startup reliability
- **Origin:** Newly introduced by the overhaul
- **Affected code:**
  - `honor_control/backend/application.py:155-165`
  - `honor_control/backend/hardware.py:874-885`
  - `honor_control/backend/command_queue.py:26`, `68-123`

**Problem.** Four sequential `systemctl` calls each permit five seconds, for a
worst-case duration of roughly twenty seconds. They run inside a command with the
queue's default ten-second deadline. `initialize()` does not catch that timeout.
The queue is then poisoned until the still-running worker call completes.

**Failure scenario / impact.** A degraded or overloaded systemd takes near five
seconds for several actions. Honor Control times out during startup and systemd
restarts it, potentially repeating partially completed stop/mask operations.

**Recommended fix.** Do not perform this mutation at implicit startup. If retained,
use a total operation deadline shorter than the outer deadline, check results,
and make the action idempotent and recoverable. Catch and surface startup
degradation without creating a restart loop.

**Tests proving the fix.** Fake each subprocess as fast, slow, timed out, and
partially successful. Assert the total deadline, startup outcome, queue health,
and retry behavior.

### PP-009 — EPP rewrite can return success without writing or verifying the requested state

- **Severity:** Medium
- **Confidence:** High
- **Category:** Verification; partial failure handling
- **Origin:** Newly introduced by the overhaul
- **Affected code:** `honor_control/backend/hardware.py:898-959`

**Problem.** With no matching CPU directories, `all_ok` remains true. Governor
writes are ignored. A successful write marks the CPU successful even if the
readback fails or contains a different value. Restore-governor failures are also
ignored. For a requested `performance` governor the method intentionally leaves
`powersave`, so the final hardware definition differs from the persisted profile
while still returning true.

**Failure scenario / impact.** On a system lacking per-CPU cpufreq files, the
method returns true without any write. On partial CPU hotplug/sysfs failure it can
leave mixed governors/EPP values. None of this reaches the operation result due to
PP-004.

**Recommended fix.** Return a structured per-CPU result for pre-governor, EPP
write, exact readback, and final governor. Define whether governor is applicable
for each pstate mode instead of silently substituting another requested value.
Treat an empty target set as unavailable, not success.

**Tests proving the fix.** Cover zero CPUs, missing cpufreq on one CPU, failed
pre-governor, EBUSY retries, readback exception, readback mismatch, restore
failure, CPU hotplug during iteration, and performance-governor semantics.

### PP-010 — Applied state can permanently hide external changes and delayed failures

- **Severity:** Medium
- **Confidence:** High
- **Category:** State synchronization
- **Origin:** Pre-existing issue, materially worsened by the overhaul
- **Affected code:** `honor_control/backend/application.py:125`, `353-366`,
  `1102-1145`

**Problem.** Once `_last_applied_power_profile` is set, `_refresh_power()` always
uses it instead of the live adapter's profile identity. This behavior predates
the reviewed range. The overhaul worsens it because the variable is now set
before the direct RAPL/EPP phase and survives its normal boolean failures.

**Failure scenario / impact.** Firmware, an administrator, resume logic, or a
remaining power manager changes the live profile after Honor Control reports
success. Five-second refreshes continue to publish the old applied name. The GUI
dirty flag can then clear against a stale applied identity.

**Recommended fix.** Keep “last transaction verified” and “currently observed”
as separate fields. Never overwrite observed data with an in-memory label. Derive
current conformance from full live observations and expose drift explicitly.

**Tests proving the fix.** Apply a profile, mutate fake observed state externally,
refresh, and assert observed drift is visible while last-verified history remains
available separately. Repeat with delayed rewrite failure.

## Low

### PP-011 — Documentation describes behavior and compatibility that the code does not provide

- **Severity:** Low
- **Confidence:** High
- **Category:** Documentation correctness
- **Origin:** Newly introduced or made stale by the overhaul
- **Affected code:**
  - `README.md:10-16`
  - `docs/hardware-support.md:23-28`
  - `docs/architecture.md:58-66`
  - `honor_control/backend/hardware.py:597-619`, `778-804`, `844-959`

**Problem.** The README says AMD Honor machines “fail safely (no MSR writes,
sysfs-only EPP),” but the platform allowlist rejects non-Meteor-Lake hardware and
disables the entire power feature; there is no AMD sysfs-only path. Hardware docs
call PPD an integration requirement while startup masks it. Architecture docs say
applied means verified on hardware, but delayed MSR/EPP work is neither included
in success nor verified.

**Failure scenario / impact.** Users and maintainers make installation or support
decisions based on a nonexistent fallback and misunderstand the privilege and
daemon side effects.

**Recommended fix.** Update documentation only after the ownership model is
fixed. State the exact allowlist, required kernel interfaces/capabilities,
external service behavior, what is verified, and the manual hardware release
gate.

**Tests proving the fix.** Add documentation/contract tests for platform capability
matrices and a packaging check that required binaries, devices, capabilities, and
daemon strategy agree.

# 5. Test and validation assessment

## What is currently tested

The existing suite has broad coverage of the original architecture:

- Power profile name validation, successful fake application, custom definition
  persistence, built-in deletion rules, auto-switch persistence, root-script
  validation, and one successful AC transition.
- Config schema round trips and validation of PL1/PL2, EPP, governor, PPD profile,
  turbo, and maximum performance values.
- D-Bus codec/client round trips for editable profile fields.
- Basic PowerPage construction and preservation of unsaved profile-editor values.
- Platform allowlisting and fake-root DMI/battery discovery.
- `honor-tools` unit tests for its original sysfs/PPD profile application.

## Important behavior not tested

No test changed in any overhaul commit. Specifically absent are tests for:

- The initialize → stop/mask PPD → apply-profile interaction.
- `stop_competing_power_daemons()` on supported, unsupported, missing-daemon, or
  partially failing systems.
- Restoration on shutdown, uninstall, upgrade, or crash.
- MSR bit encoding, exact I/O, power-unit conversion, permissions, kernel
  lockdown, missing device, or locked registers.
- EPP rewrite enumeration, governor failure, exact readback, empty CPU sets, CPU
  hotplug, or partial per-CPU results.
- Delayed-task boolean failures, exceptions, overlap, cancellation, shutdown, and
  stale generation ordering.
- Restart reconciliation. Despite the commit message and plan naming it, there is
  no persisted desired/applied mismatch test.
- The new active-combo dirty flag. The GUI test covers the profile editor's
  separate `_profile_dirty`, not `_active_combo_dirty`.
- Packaged service capabilities versus runtime device requirements.
- Behavior on resume, external profile changes, or masked PPD reads.

The fake is misleading for this change: `rewrite_epp()` and `write_rapl_msr()`
always return true, `stop_competing_power_daemons()` has no state, and typical
tests end their event loop before the 0.5-second delayed task can execute. Thus a
green application test would not validate the production mechanism.

## Tooling/test failures

The full suite did not pass in this environment. The queue timed out even for a
worker lambda returning `42`; application initialization consequently failed.
Because the same cross-thread wakeup issue occurs in a standalone reproduction,
I treat it as a pre-existing queue/runtime or sandbox compatibility concern, not
evidence caused by this overhaul. It nevertheless means the overhaul lacks an
end-to-end validation result on a declared-supported Python version.

Repository-scoped Ruff lint and byte-compilation passed. Whole-tree Ruff and
format checks found unrelated pre-existing issues. Systemd unit verification and
Git checks passed. Build and `pip check` failures were environment/tooling issues
described in section 2.

## Prioritized additional tests

1. PPD ownership integration test covering startup through profile verification.
2. Pure MSR encoder/decoder tests for every field and failure mode.
3. Exact service-sandbox capability probe plus manual supported-laptop gate.
4. Deterministic concurrent/superseded apply test with fake time and barriers.
5. Delayed failure/result propagation and state-persistence tests.
6. Full-definition startup reconciliation and external-drift tests.
7. Daemon-state restoration/uninstall tests.
8. Per-CPU EPP structured-result and hotplug tests.
9. PowerPage pending-selection success/failure/external-refresh tests.
10. CI on the full declared Python range, including Python 3.14 or a narrowed
    `requires-python` declaration if 3.14 is not supported.

# 6. Architecture and maintainability assessment

## Separation of responsibilities and abstraction quality

The pre-overhaul layering is generally sound: application orchestration is
separate from hardware, state, transport, and UI. The overhaul bypasses those
strengths in two ways. First, `HonorToolsAdapter` now owns systemd policy, raw MSR
encoding, cpufreq iteration, timing workarounds, and generic dependency adaptation
in one class. Second, the application splits one logical apply transaction into a
reported synchronous phase and an unreported asynchronous phase.

A targeted refactor is justified; a rewrite is not. Introduce a `PowerBackend`
or strategy abstraction with one operation:

```text
probe requirements -> apply one definition -> settle -> read back -> structured result
```

Use explicit implementations/policies for PPD-managed and direct Intel control.
The platform policy should declare which mechanisms apply and the safe per-model
limits. The application should not know about a 0.5-second workaround, and the
generic hardware adapter should not silently decide to mask system services.

Concrete benefits:

- One owner and one completion point for desired/applied/observed state.
- No contradictory PPD/direct behavior.
- Testable process, filesystem, clock, and MSR interfaces.
- Clear capability reporting before mutation.
- Straightforward extension to another Intel generation or AMD without running
  Intel-specific code behind broad names.

## State management

The data model correctly distinguishes desired and applied fields in name, but
the implementation conflates “last method returned true” with “currently applied”
and compresses observations into a PPD label. Add explicit transaction state
(`idle`, `applying`, `verified`, `partial`, `failed`) and retain structured live
observations. Persist desired intent only under a clearly stated policy; do not
persist a value merely because phase one succeeded.

External service state is currently hidden. The preferred architecture avoids
owning it. If daemon ownership remains, represent it explicitly and give install,
startup, shutdown, and uninstall one lifecycle contract.

## Coupling, duplication, and extensibility

`rewrite_epp()` duplicates governor/EPP logic already present in `honor-tools`,
but with different semantics (the dependency restores `performance`; the new
method intentionally does not). RAPL is likewise applied once through dependency
sysfs and again via raw MSR. This duplication is the source of timing workarounds
and inconsistent success criteria.

Consolidate each mechanism in one layer. Return a typed result rather than a
heterogeneous dictionary plus guessed default `True` values. Mechanism
applicability should be explicit so a missing optional PPD is distinguishable from
a failed required PPD operation.

Platform extensibility is currently nominal. The method names are generic, but
the implementation assumes Intel pstate, Intel RAPL MSRs, CPU 0 package scope,
systemd, PPD, and `intel_lpmd`. A platform strategy and injected OS ports would
make these constraints honest without forcing a broad rewrite.

## Complexity, naming, and readability

The changed code is locally readable and comments make the intended workaround
easy to follow. However, several comments state unverified kernel/PPD behavior as
guaranteed fact, and `_pending_power_task` suggests single-task ownership that the
code does not enforce. `stop_competing_power_daemons` hides that it persistently
masks services and changes HWP state. Names should communicate lifecycle and
irreversibility when such behavior exists.

# 7. Positive observations

- Commit `7213294` added a necessary platform gate before daemon/system changes.
  Without it, starting the service on arbitrary hardware would have masked the
  standard power manager.
- The exact DMI and CPU allowlist is conservative and reuses the repository's
  fail-closed hardware policy.
- PL1/PL2 validation exists both in persisted configuration and again before raw
  MSR access. The ranges need platform-specific review, but rejecting unchecked
  arbitrary values is the right pattern.
- The GUI dirty-flag approach addresses the reported snap-back at the correct
  presentation boundary and preserves external snapshot updates when there is no
  pending user choice.
- Startup reconciliation is conceptually appropriate for persisted desired
  state; the defect is its identity-only verification, not the existence of the
  lifecycle step.
- Blocking hardware work remains routed through the serialized command queue.
- The follow-up cleanup commit recognized task lifetime, shutdown cancellation,
  package scope, and misleading naming/docstrings as important concerns.
- Config profile definitions are typed, atomically persisted, strictly validated,
  and carried consistently through D-Bus, CLI, and GUI fields.
- The repository explicitly states that fake-hardware CI is not a substitute for
  a real-hardware pre-release gate. That is especially appropriate for this work.

# 8. Prioritized remediation plan

## Must fix before merge or release

1. Resolve PP-001 by selecting a coherent PPD-managed or direct-control ownership
   model. Remove the stop/mask versus required-PPD contradiction.
2. Remove or correct raw MSR writing. If retained, fix PP-002 with audited
   bitfield construction and pure unit tests.
3. Resolve PP-003: align required privileges/devices/kernel policy with the
   shipped service sandbox and capability reporting. Reassess whether granting
   `CAP_SYS_RAWIO` is acceptable.
4. Make the complete apply/settle/readback sequence one state transaction; fix
   PP-004 so failures and superseded requests cannot be reported as applied.
5. Remove persistent implicit daemon masking or implement explicit administrator
   consent, prior-state tracking, rollback, shutdown, and uninstall restoration
   for PP-005.
6. Add production-path tests for all five items above. Do not rely on the current
   always-successful fake helpers.

## Should fix soon afterward

7. Reconcile complete definitions and live state rather than labels (PP-006).
8. Inject filesystem, process/service-manager, clock, and MSR ports (PP-007).
9. Correct timeout composition and startup failure behavior (PP-008).
10. Return and verify structured per-CPU governor/EPP results (PP-009).
11. Separate live observed, last verified, and desired state (PP-010).
12. Update all compatibility, architecture, privilege, and recovery documentation
    (PP-011).

## Optional cleanup / longer-term improvement

13. Move power mechanism applicability and safe limits into per-platform policy.
14. Replace dictionary result aggregation and default-true lookups with typed
    results whose required/optional semantics are explicit.
15. Add a reusable fake service manager and fake sysroot/MSR device so integration
    tests cannot escape to the host.
16. Resolve the Python 3.14/sandbox cross-thread queue wakeup problem or narrow and
    enforce the supported Python range.
17. Clean unrelated whole-tree Ruff/format issues and repair the build-tool dev
    environment so release validation is reproducible.

## Validation plan after fixes

1. Run pure unit tests for MSR fields, EPP/governor results, strategy selection,
   and state transitions.
2. Run full application integration tests using fake clock, service manager,
   sysroot, and MSR interfaces, including failure injection and rapid profile
   switching.
3. Run the complete 221-test repository suite across supported Python versions,
   Ruff, formatting, compileall, build, `pip check`, Git diff checks, and systemd
   verification.
4. Install into a disposable VM and verify service permissions, daemon state
   before/after install/start/stop/uninstall, reboot reconciliation, suspend/resume,
   and desktop PPD behavior without raw hardware writes.
5. Perform the documented manual release gate on each supported laptop/CPU SKU:
   capture before/after MSR and sysfs state with independent tooling, verify
   sustained and burst limits, EPP/governor/turbo, AC transitions, rapid changes,
   reboot/resume, thermal behavior, and exact recovery after failures.
6. Confirm that UI, CLI, D-Bus results, persisted desired state, and independent
   observations agree for success, partial failure, unavailable mechanisms, and
   external drift.

# 9. Final verdict

**Unsafe to merge or release.**

The minimum changes needed to reach **Requires significant fixes** are to stop
performing implicit persistent daemon masks, remove the PPD dependency
contradiction, and disable the raw-MSR path until its encoding and privilege model
are corrected. To advance beyond **Requires significant fixes**, the whole
profile operation must become a verified state transaction with deterministic
supersession/cancellation, complete reconciliation, structured per-mechanism
results, and production-path tests. A real-hardware gate is mandatory before any
release that writes RAPL MSRs.
