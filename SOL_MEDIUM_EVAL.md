# Power-profile overhaul engineering review

## 1. Executive summary

**Final verdict: Unsafe to merge or release.**

The overhaul has a sound high-level goal—reapply persisted intent, prevent the GUI from discarding an in-progress selection, serialize additional hardware operations, and compensate for platform power managers that overwrite settings—but the implementation is not safe or internally consistent.

The most serious regression is deterministic: service startup stops and masks `power-profiles-daemon` (PPD), while the configured `honor-tools` apply path still calls `powerprofilesctl set` and treats failure as a partial apply. On the supported Honor platform this makes successful profile application unlikely after the service starts, prevents persistence of a manually selected profile, prevents the new delayed correction from being scheduled, and leaves a system-wide power service persistently masked with no automatic restoration or uninstall cleanup. The result is both broken core functionality and an unmanaged host-level side effect.

The direct RAPL MSR writer also constructs the PL2 field incorrectly. It uses absolute bit positions inside a value that is subsequently shifted by 32 bits; masking to 64 bits then drops the intended PL2 enable and time-window bits. This undermines the feature the overhaul was specifically intended to fix.

Even after those defects are corrected, the delayed “fire-and-forget” phase is outside the apply transaction. Its Boolean failures are ignored, callers receive success before the decisive writes occur, state is labeled applied without post-settle verification, and earlier delayed tasks are neither cancelled nor versioned when a newer profile is selected. The performance-governor rewrite deliberately leaves the observed governor at `powersave` while the profile and snapshot can continue to claim `performance`.

The GUI dirty-selection fix is narrowly implemented and appears reasonable, and platform detection does prevent the new writes on unverified models. All 221 automated tests pass, but the new hardware and lifecycle behavior is almost entirely represented by an always-successful fake. There are no encoding, daemon-management, delayed-failure, ordering, cancellation, or post-settle verification tests. Real-hardware validation is explicitly absent, so this branch is not ready for merge or release.

## 2. Scope and methodology

### Git scope

- Branch reviewed: `main`
- Commit reviewed: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f` (`README: document Intel-only compatibility`)
- Working tree at review start: clean (`main...origin/main`)
- Default branch: `origin/HEAD -> origin/main`
- Comparison base: `4d8994a` (`Initial commit: Honor Control — D-Bus service and Qt6 GUI for Honor MagicBook laptops`)
- Review range: `4d8994a..34d31f9`
- Merge base of the reviewed checkout and `origin/main`: `34d31f9`, because the reviewed branch is already identical to the remote default branch. That merge base contains the changes and is not useful as a change base. Therefore the initial commit immediately preceding the four explicitly power-related commits is the most defensible semantic comparison base.

Relevant commits, in order:

1. `15f4d66057c144bfde12688c075f2b1e4035b6c4` — delayed EPP/RAPL rewrite, startup reconciliation, daemon stopping, GUI selection dirty state.
2. `d391bb07a9b7b4b797196155c7d8d40833e7619f` — daemon masking moved to startup, MSR bounds/CPU-0 change, delayed-task reference and shutdown cancellation.
3. `72132945c077b85f1842c4ae7913a9854f9dbe2d` — platform guard around daemon management.
4. `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f` — Intel compatibility documentation.

The direct diff changes four files: `README.md`, `honor_control/backend/application.py`, `honor_control/backend/hardware.py`, and `honor_control/frontend/gui/pages/power.py` (326 insertions, 7 deletions at the range endpoint). Review was not limited to those files.

### Subsystems inspected

- Application lifecycle, mutation locking, startup reconciliation, auto-switching, snapshots, and fan-profile consumption in `honor_control/backend/application.py`.
- Hardware protocol, fake implementation, capability probing, platform detection, `honor-tools` adapter, sysfs writes, daemon control, EPP rewriting, and direct MSR access in `honor_control/backend/hardware.py`.
- Queue serialization/cancellation semantics in `honor_control/backend/command_queue.py` and service composition/shutdown in `honor_control/backend/service.py`.
- Power configuration schema, defaults, persistence, validation, and migration/loading in `honor_control/backend/config_store.py`, `honor_control/core/models.py`, and `honor_control/core/validation.py`.
- D-Bus API/codec/authorization, client protocol/proxy, CLI, tray, GUI controller, and power page.
- Systemd, D-Bus, polkit, installation/uninstallation, safety, architecture, API, hardware-support, README, changelog, and overhaul-plan documentation.
- Power, hardware, GUI, client, CLI, configuration, authorization, and validation tests.
- Installed dependency implementation: `honor-tools 0.1.0` in `.venv`, especially `honor.power.apply_profile`, `_set_ppd`, and `get_status`.

### Commands and results

Safe, read-only or repository-local commands included:

- `git status --short --branch`, branch/remote enumeration, `git rev-parse`, `git log`, `git merge-base`, per-commit `git show`, range `git diff`, `git blame`: completed successfully. The initial tree was clean and local `main`, `origin/main`, and `origin/HEAD` all identified the reviewed commit/branch.
- `rg --files`, targeted `rg`, `find`, `sed`, and `nl`: used to inventory and trace code, configuration, packaging, tests, and documentation.
- `.venv/bin/python` plus `inspect`/`importlib.metadata`: confirmed installed `honor-tools` version `0.1.0`; confirmed `apply_profile()` calls `_set_ppd()`, which executes `powerprofilesctl set ...` and returns false on a non-zero exit.
- `python3 -m pytest -q`: **221 passed in 8.53s**.
- `.venv/bin/ruff check honor_control tests`: **passed**.
- `.venv/bin/python -m compileall -q honor_control tests`: **passed**.
- `git diff --check 4d8994a..HEAD`: **passed**.
- `bash -n scripts/*.sh`: **passed**.
- `.venv/bin/ruff check .`: **failed with 6 findings**, all in the pre-existing `Reverse engineering/capture_subscribers_driver.py` (import formatting/unused import/one-line statements). No overhaul file caused this result.
- `.venv/bin/pytest -q`: could not run because the virtualenv has no `pytest` executable. The available system Python runner was used instead.
- `.venv/bin/python -m build --no-isolation`: could not run because the virtualenv lacks a usable `build` module entry point.

No type-checker is configured in `pyproject.toml`; no `mypy`/`pyright` claim is made. No system service, daemon, sysfs node, MSR device, system configuration, or real hardware was touched.

### Limitations and assumptions

- No real MRA-XXX hardware was available. Claims about actual driver/firmware reactions are labeled as inference where appropriate; arithmetic, control-flow, dependency, and persistence defects are directly evidenced.
- The external dependency is version-ranged as `honor-tools>=0.1,<0.2`; the locally installed and inspected version is 0.1.0. A different compatible 0.1.x could change details, which is itself an integration risk because the application relies on undocumented timing/return shapes.
- No remote fetch was performed. The local remote-tracking default branch was current at the reviewed commit, and the working tree reported no divergence.
- The user requested only this report. No production code or tests were modified.

## 3. Architecture and behavior overview

The root system service constructs an `ApplicationService`, a persistent `ConfigStore`, a `SnapshotStore`, one `HardwareCommandQueue` worker, a runtime supervisor, and either `HonorToolsAdapter` (production/system bus) or `FakeHardware` (development/session bus). D-Bus methods authorize callers and delegate to application use cases. UI, tray, and CLI consume typed snapshots and issue intents through the client layer; they do not directly write hardware.

Power definitions are owned by `ConfigStore` in `/var/lib/honor-control/state.toml`. Three built-ins and custom profiles contain PL1/PL2, governor, EPP, PPD profile, turbo, and maximum-performance percentage. The persisted `power.profile` is manual desired intent. Auto-switch policy separately selects AC and battery profiles and intentionally applies them with `persist_desired=False` so a transient source change does not overwrite manual intent.

At startup, configuration is loaded and all domains are refreshed through the serialized hardware queue. The overhaul then calls `stop_competing_power_daemons()`, which, after a positive platform match, best-effort stops and masks PPD and `intel_lpmd` and enables Intel HWP dynamic boost. It then reconciles the persisted desired profile if the initial snapshot does not already report it.

An interactive or automatic apply obtains the power capability, resolves the persisted definition, and calls `HonorToolsAdapter.apply_power_profile()` on the hardware worker. The adapter creates an `honor.config.Config`, injects the requested definition, and delegates the write sequence to `honor.power.apply_profile()`. In inspected `honor-tools 0.1.0`, that dependency writes RAPL sysfs, invokes `powerprofilesctl set`, writes EPP/governor, and writes Intel turbo/max-performance sysfs. The adapter folds its detailed result into five Boolean groups. Only if all groups are true does the application update `_last_applied_power_profile`, optionally persist manual intent, refresh the snapshot, and schedule the new delayed correction.

The delayed task sleeps 0.5 seconds, then serially invokes a direct package RAPL MSR write and an EPP rewrite. The RAPL path reads MSR 0x606 for units and 0x610 for existing time windows, constructs a replacement value, and writes `/dev/cpu/0/msr`. The EPP path sets every enumerated CPU to `powersave`, retries EPP writes with a read after each successful write, and restores the requested governor unless it is `performance`; in that case it intentionally leaves `powersave`. Neither delayed Boolean result is consumed or reflected in operation status/snapshot.

`read_power()` delegates observed state to `honor.power.get_status()`, maps only the PPD profile to the three built-in names, and records raw data in `observed_summary`. `_refresh_power()` then overlays configuration, profiles, policy, and `_last_applied_power_profile`; once the in-memory last-applied marker is set, it overrides the dependency’s observed applied profile. Fan-curve selection consumes this applied-profile label. The auto-switch loop polls AC state every two seconds and applies/runs a root-owned transition hook once after an application result claims success.

On shutdown, only the task currently stored in `_pending_power_task` is cancelled (without awaiting it), supervisors stop, and the queue is closed. PPD, `intel_lpmd`, HWP dynamic boost, governor/EPP, and RAPL are not restored. The uninstall script likewise does not restore them.

The GUI power page now tracks `_active_combo_dirty`. Snapshot refreshes update the active selection only while the user has not selected a different entry; a later snapshot matching that selection clears the flag. This addresses the reported five-second snap-back without changing the D-Bus contract.

## 4. Findings

### Critical

#### PP-001 — Startup disables a required dependency and leaves host power services persistently masked

- **Severity:** Critical
- **Confidence:** High
- **Category:** Functional regression; lifecycle/recovery; host integration
- **Origin:** Newly introduced by the overhaul (`15f4d66`, changed to persistent masking in `d391bb0`; platform guard in `7213294` narrows but does not resolve it)
- **Affected code:** `honor_control/backend/application.py:155-165` (`initialize`); `honor_control/backend/hardware.py:597-619` (`get_power_capability`), `806-840` (`apply_power_profile`), `844-896` (`stop_competing_power_daemons`); `scripts/uninstall-local.sh:19-50`; installed `honor.power.apply_profile` / `_set_ppd`

`initialize()` stops and masks PPD before reconciliation or any later user apply. Yet the capability requires `powerprofilesctl`, and the adapter’s dependency invokes `powerprofilesctl set` for every profile. With PPD stopped, that command normally cannot reach its D-Bus service; because it is masked, activation cannot restart it. `honor-tools` returns `ppd_ok=False`, the adapter propagates that, and `_apply_power_profile()` returns partial. The delayed MSR/EPP rewrite is scheduled only in the all-true branch, so the very action intended to prevent PPD interference also prevents the overhaul’s corrective phase.

This was confirmed against the installed declared dependency (`honor-tools 0.1.0`): `_set_ppd()` executes `powerprofilesctl set <profile>` and returns `proc.returncode == 0`. It is not merely a naming inference.

The side effect is host-persistent and unowned. There is no unmask/restart in shutdown, `ExecStopPost`, uninstall, failure rollback, or capability failure. Return codes and stderr are discarded. Startup can therefore degrade the machine’s ordinary desktop power management even when profile reconciliation fails, the MSR device is unavailable, later writes fail, honor-control crashes, or honor-control is uninstalled. The platform guard limits impact to positively detected MRA-XXX systems, but that is precisely the supported population.

**Failure scenario:** Booting/enabling honor-control on a supported laptop masks PPD and `intel_lpmd`. Startup reconcile calls an apply whose `powerprofilesctl` phase fails; it records a partial result and never performs the delayed correction. Manual GUI/CLI selections also return partial and are not persisted. Desktop power-profile integration remains unavailable after honor-control stops or is removed because the units stay masked.

**Recommended fix:** Do not mask a service still used by the apply abstraction. Choose and implement one coherent ownership model. Prefer coordinating with PPD (perform PPD selection first and verify after settle), or remove PPD from the required apply path and capability if honor-control is deliberately the exclusive manager. Any takeover must be explicit, capability-gated on all required resources, transactional, preserve prior active/enabled/masked states, roll back on failure, and restore on shutdown/uninstall/disable. At minimum, remove startup masking until that lifecycle exists. Check and surface every service-control result.

**Tests:** Integration-test the real adapter against a fake `powerprofilesctl`/service-control boundary; assert call ordering and that apply remains possible. Cover absent/inactive/masked PPD, failed stop/mask, missing `/dev/cpu/0/msr`, startup reconcile failure, shutdown, crash recovery design, uninstall restoration, and preservation of a user’s pre-existing unit states.

### High

#### PP-002 — RAPL MSR encoding drops PL2 enable and time-window bits

- **Severity:** High
- **Confidence:** High
- **Category:** Hardware correctness; bit-field encoding
- **Origin:** Newly introduced
- **Affected code:** `honor_control/backend/hardware.py:961-1036`, specifically `write_rapl_msr` lines 1004-1024

The code extracts PL2’s time-window as an absolute register field (`old >> 49`), then builds `hi` using absolute positions `1 << 47` and `tw2 << 49`, and finally shifts the entire `hi` value left by 32. After the final 64-bit mask, those already-absolute enable/window bits are above bit 63 and disappear. Only `pl2_units`, which starts in `hi`’s low bits, lands in bits 32 onward. Thus the written register has a PL2 numeric limit but no PL2 enable bit and a zeroed PL2 window.

The source comment says “PL2 enabled” and “preserve time windows,” but the arithmetic contradicts both claims. This is deterministic and does not require hardware to reproduce.

**Failure scenario:** A performance profile requests a 55 W burst limit. The write returns `True` because the eight-byte write succeeds, but PL2 is disabled or otherwise interpreted differently by the CPU, so burst behavior does not match the profile. The log falsely reports success.

**Recommended fix:** Isolate encoding/decoding into pure functions with named masks. Either build PL2 as a 32-bit half (`pl2_units | 1<<15 | tw2<<17`, then shift that half by 32) or place all fields directly at absolute positions exactly once. Preserve documented reserved/lock/clamp fields deliberately, validate unit-width overflow, perform an MSR read-back, and compare decoded effective fields.

**Tests:** Table-driven pure tests for representative units and both halves; assert bits 47 and 49-55 after encoding and round-trip decode. Test boundary wattages, unit exponents, field overflow, locked registers, short reads/writes, and read-back mismatch.

#### PP-003 — The API reports success before the decisive correction and discards its failures

- **Severity:** High
- **Confidence:** High
- **Category:** Error handling; state synchronization; observability
- **Origin:** Newly introduced, while the pre-existing “last applied” overlay worsens the misreporting
- **Affected code:** `honor_control/backend/application.py:348-421` (`_apply_power_profile`, `_delayed_power_rewrite`), `1102-1145` (`_refresh_power`); `honor_control/backend/hardware.py:898-1036`

The overhaul’s stated remedy for overwritten RAPL/EPP values occurs after a 0.5-second sleep, but `_apply_power_profile()` returns success and may persist intent before that phase starts. `write_rapl_msr()` and `rewrite_epp()` return Booleans, yet `_delayed_power_rewrite()` ignores both. Only raised exceptions are logged. There is no post-settle observed verification, no update to `OperationResult.details`, no failure snapshot, and no retry/reconcile state.

This means missing `msr`, an encoding/write failure, zero CPU EPP paths, partial per-CPU failures, or read-back mismatch can all coexist with a success response. `_last_applied_power_profile` then overrides observed profile mapping indefinitely until process restart, so snapshots, GUI/tray, transition-hook gating, and fan-curve selection can consume asserted rather than verified state.

**Failure scenario:** The initial honor-tools sysfs phase returns true, the caller sees “Profile 'performance' applied,” and a transition hook runs. `/dev/cpu/0/msr` is absent or the subsequent EPP rewrite fails on some CPUs. The system remains at different power limits/settings, but the GUI and fan controller report/use `performance` and no structured error reaches the user.

**Recommended fix:** Make application a single versioned transaction with a bounded settle phase. Await the required correction, check Boolean results, read back and decode RAPL/governor/EPP/turbo/max-perf, and classify full/partial/failure before marking applied or running hooks. If UI latency requires asynchronous convergence, return an explicit pending state and publish completion/failure later; do not call it applied. Store desired, last attempted, and last verified applied state separately.

**Tests:** Force each delayed operation to return false and raise; assert no success/applied marker/hook. Test mixed per-CPU outcomes, absent MSR, post-settle read-back drift, snapshot error details, and successful convergence.

#### PP-004 — A `performance` profile is intentionally changed to `powersave` governor while state still claims the profile is fully applied

- **Severity:** High
- **Confidence:** High
- **Category:** Semantic correctness; leaky abstraction; state reporting
- **Origin:** Newly introduced behavior; the profile model’s independent governor/EPP controls are pre-existing
- **Affected code:** `honor_control/backend/hardware.py:898-959` (`rewrite_epp`); `honor_control/backend/application.py:328-380`, `1102-1145`; profile editor/CLI definitions in `honor_control/frontend/gui/pages/power.py:76-89` and `honor_control/cli/honorctl.py:441-464`

`rewrite_epp()` first writes `powersave` to every CPU. If the requested governor is `performance`, it explicitly does not restore it. Nevertheless, its return value represents only EPP-write success; the application has already marked the named profile fully applied, and the profile definition/UI continues to say its governor is `performance`.

The comment describes this as an Intel quirk, but silently substituting another requested setting violates the profile contract and makes governor and EPP controls misleading. It also conflicts with the dependency apply sequence, which intentionally restores the requested target governor after EPP. The delayed task undoes that target without updating observed/applied semantics.

**Failure scenario:** A user or custom policy selects `governor=performance`. The immediate dependency phase sets it, the operation returns success, and 0.5 seconds later honor-control changes it to `powersave`. Diagnostics may expose `powersave` in raw observations, while the named profile and applied marker continue to claim success.

**Recommended fix:** Define supported combinations explicitly. Reject an incompatible governor/EPP pair at validation time, normalize it visibly before persistence, or model the actual Intel control strategy without pretending both settings remain independently enforceable. Verification must compare requested and observed effective values and report a mismatch.

**Tests:** Matrix-test every accepted governor/EPP pair against expected final observed state. Assert that a fully applied result can never leave a different governor than the persisted definition unless the normalized definition shown to clients also changed.

### Medium

#### PP-005 — Delayed rewrites are not superseded, so stale profiles can overwrite newer selections

- **Severity:** Medium
- **Confidence:** High for the race; Medium for duration/user impact
- **Category:** Concurrency; invalid state transition
- **Origin:** Newly introduced
- **Affected code:** `honor_control/backend/application.py:125-126`, `181-186`, `367-421`

Each successful apply overwrites the single `_pending_power_task` reference without cancelling or versioning the previous task. Mutation locking covers the immediate apply, but delayed tasks run outside it and later enqueue hardware operations independently. The hardware queue prevents simultaneous writes, not stale writes.

If profile B is selected while profile A’s 0.5-second task is sleeping—or while B’s immediate apply occupies the queue—A can subsequently write A’s RAPL/EPP over B. B’s own delayed task will usually correct it later, but there is a real wrong-profile interval; if B’s task is cancelled during shutdown or fails, A can be the final state. Because only the newest task reference is retained, shutdown cannot cancel/await older tasks.

**Recommended fix:** Maintain a monotonically increasing apply generation. Cancel and await the prior correction before a newer apply, and recheck generation immediately before each write. Prefer keeping the correction inside the serialized mutation transaction. On shutdown, cancel and gather all owned tasks before queue shutdown.

**Tests:** Apply A then B at timing boundaries before/after the settle delay with controllable queue barriers; assert no A write occurs after B becomes current. Cover three rapid applies and shutdown during sleep and during queued work.

#### PP-006 — Capability probing does not cover resources required by the new implementation

- **Severity:** Medium
- **Confidence:** High
- **Category:** Platform/permission assumptions; recovery
- **Origin:** Newly exposed/worsened by the overhaul
- **Affected code:** `honor_control/backend/hardware.py:597-619`, `844-896`, `898-1036`; `docs/hardware-support.md:23-28`; `packaging/systemd/honor-control.service`

Power is reported writable when honor-tools imports, the DMI/CPU platform matches, and a `powerprofilesctl` binary exists. The new path additionally depends on a functioning PPD service (while simultaneously disabling it), systemctl authority, per-CPU cpufreq governor/EPP files, Intel pstate controls, `/dev/cpu/0/msr`, readable MSRs 0x606/0x610, and a writable unlocked 0x610. None is probed. Service-control and HWP writes silently discard failures.

The documentation claims the sysfs resources are requirements and “every mechanism is checked separately,” but the capability code does not check them. A binary in `PATH` is not evidence its D-Bus backend is usable. This produces optimistic UI/API availability and only late, partially hidden failure.

**Recommended fix:** Add non-mutating, per-mechanism capability probes and expose degraded modes/resources. Do not perform destructive ownership changes until all prerequisites and rollback prerequisites pass. Reconcile the systemd sandbox/capabilities with the exact device/sysfs/control operations and validate it in an installed-service test.

**Tests:** Capability matrix for missing/unreadable MSR, missing cpufreq/EPP files, offline CPU 0, missing Intel pstate, missing/unreachable PPD, failed systemctl, locked RAPL, and supported sysfs-only fallback.

#### PP-007 — EPP rewrite can return success without any CPUs and does not verify requested values

- **Severity:** Medium
- **Confidence:** High
- **Category:** False success; platform edge cases
- **Origin:** Newly introduced
- **Affected code:** `honor_control/backend/hardware.py:917-959`

`cpu_dirs` is derived from hard-coded host `/sys` globbing. If it is empty, `all_ok` remains `True`. Governor write results are ignored. A successful write is followed by a read whose content is discarded; even read failure is ignored, so the method does not establish that the requested EPP became effective. CPU hotplug/offline cpufreq directories can similarly create partial, unstable coverage. These paths also bypass the adapter’s injectable `root_path`, making safe unit testing unnecessarily difficult.

**Failure scenario:** cpufreq is unavailable, sysfs is namespaced differently, or CPUs are hotplugged. The delayed task treats EPP as successful without changing any CPU, and PP-003 hides that from the caller.

**Recommended fix:** Use the adapter root consistently, require at least one eligible/online CPU, check every governor result, compare stripped read-back to the requested value, and decide/document hotplug behavior. Return structured per-CPU results rather than one Boolean.

**Tests:** Empty CPU set, missing cpufreq on one/all CPUs, write-success/read-failure, read-back mismatch, governor failure, CPU hotplug simulation, and injected-root filesystem tests.

### Low

#### PP-008 — MSR file descriptors can leak on intermediate errors and short I/O is not validated

- **Severity:** Low
- **Confidence:** High
- **Category:** Resource lifecycle; defensive I/O
- **Origin:** Newly introduced
- **Affected code:** `honor_control/backend/hardware.py:988-1036`

Each MSR descriptor is manually closed only after all preceding operations succeed. An `lseek`, short `read`, `struct.unpack`, or `write` error can bypass `os.close()`. `struct.error` is not caught because only `OSError` is handled, and `os.write` length is not checked. Calls are infrequent, so ordinary impact is low, but repeated auto-switch/reconciliation failures can leak descriptors or propagate an unexpected exception.

**Recommended fix:** Use context-managed descriptors (`with open(...)` or a small `os.fdopen`/`try/finally` helper), require exactly eight bytes read/written, and convert malformed/short I/O into structured failure.

**Tests:** Inject failures/short I/O at every stage and assert descriptors close and the method returns/raises the documented result.

#### PP-009 — Compatibility and behavior documentation is inaccurate after the overhaul

- **Severity:** Low
- **Confidence:** High
- **Category:** Documentation; support contract
- **Origin:** Newly introduced/worsened
- **Affected code:** `README.md:11-16`; `docs/hardware-support.md:23-28`; `honor_control/backend/hardware.py:597-619`, `844-1036`

The README says AMD systems will perform “no MSR writes, sysfs-only EPP.” Current platform detection accepts only the exact verified MRA-XXX plus Intel identity; on an AMD model power capability is unsupported and neither delayed write runs. The hardware-support document says RAPL/governor/EPP resources are requirements and each mechanism is checked separately, but capability probing checks only honor-tools, platform, and the `powerprofilesctl` executable. No document warns that starting the service persistently masks PPD/`intel_lpmd`, changes HWP boost, or fails to restore those states.

**Recommended fix:** After correcting the ownership design, document the actual platform gate, required kernel devices/modules, final governor semantics, service interactions, persistence, rollback, and observed-vs-desired reporting. Remove unsupported global claims such as “all Honor MagicBook laptops released to date use Intel CPUs” unless maintained from authoritative compatibility data.

**Tests:** Documentation assertions can be included in release checklists; more importantly, make capability tests the executable source of truth and derive/display their reasons.

## 5. Test and validation assessment

### What is tested

The suite provides broad baseline coverage for configuration parsing/validation/persistence, typed snapshots and codecs, D-Bus/client/CLI surfaces, polkit action mapping, platform identity matching, battery behavior, fake fan/GPU/gesture behavior, application profile validation, custom-profile persistence, desired-vs-auto-switch semantics, transition-hook execution, and GUI construction/editor dirty-state preservation. The fake application tests confirm that successful applies update snapshots and that automatic transitions run hooks once.

The suite passed completely (221 tests), and production/tests pass configured Ruff and byte compilation. That establishes that the overhaul did not introduce ordinary syntax/import/style regressions in tested environments.

### Important missing behavior

The new behavior has almost no direct coverage:

1. No test invokes or mocks `stop_competing_power_daemons`; no assertion checks platform guard, ordering, systemctl return codes, state preservation, rollback, shutdown, or uninstall.
2. No integration test couples daemon stopping with the real `honor-tools` call to `powerprofilesctl`, so PP-001 is invisible.
3. No test covers `write_rapl_msr`, bit encoding, read-back, bounds, locks, units, errors, or descriptor closure.
4. No test covers `rewrite_epp`, zero/partial CPUs, read-back content, governor substitution, retries, or injected roots.
5. No test waits for or inspects `_delayed_power_rewrite`; the fake always returns true, and most tests shut down before the 0.5-second delay.
6. No test makes delayed operations fail or validates that the API/snapshot reflects settled hardware.
7. No test performs rapid consecutive applies or shutdown with multiple pending corrections.
8. The GUI test covers editor-field dirty state, not the newly added active-profile combo snap-back behavior or apply success/failure clearing.
9. No installed systemd-service test validates permissions/device access or restoration.
10. No real-hardware test has been run; the README explicitly identifies it as a manual pre-release gate.

### Weak or misleading tests

`FakeHardware.stop_competing_power_daemons`, `rewrite_epp`, and `write_rapl_msr` merely log and return success. This preserves protocol shape but cannot model the new two-phase transaction. `test_set_profile_success` therefore proves only the fake happy path. The auto-switch test’s 2.1-second sleep is slow/timing-sensitive and still does not assert delayed rewrite order/results. The passing suite should not be interpreted as evidence that the overhaul works on its only supported production platform.

### Prioritized additional tests

1. Pure MSR encode/decode and read-back tests (PP-002).
2. Adapter integration test proving coherent PPD/service-control/apply ordering and full lifecycle restoration (PP-001).
3. Application transaction tests for false/exception/post-settle mismatch and hook suppression (PP-003).
4. Deterministic generation/cancellation tests for rapid A→B→C applies and shutdown (PP-005).
5. Final governor/EPP combination matrix (PP-004).
6. Capability/resource matrix and installed systemd sandbox smoke test (PP-006).
7. Filesystem-injected EPP enumeration/write/read-back/hotplug tests (PP-007).
8. GUI active-combo dirty-state tests across refresh, success, partial failure, external auto-switch, and profile list changes.
9. Manual supported-hardware validation with pre/post raw MSR decode, sysfs observations over time, PPD state, reboot, service stop/disable, and uninstall recovery.

### Tooling failures

Repository-wide Ruff is not currently clean due solely to six pre-existing issues in `Reverse engineering/capture_subscribers_driver.py`. The virtualenv is incomplete for the advertised `dev` extra: it lacks pytest/build entry points. These are general repository/tooling concerns, not overhaul regressions. The system Python pytest run and scoped package/test lint both succeeded.

## 6. Architecture and maintainability assessment

The pre-existing architecture has valuable boundaries: frontends use a typed client contract, `ApplicationService` owns use cases, desired state is persisted centrally, snapshots separate reads from writes, and a single hardware queue prevents concurrent low-level mutations. The overhaul correctly routes its new hardware actions through that queue and places the real implementation behind `HardwarePort`.

The main architectural problem is split ownership. `honor-tools`, `HonorToolsAdapter`, and `ApplicationService` all own portions of one power transition; systemd daemon lifecycle is then embedded as another best-effort adapter method. The dependency applies RAPL/PPD/EPP/governor immediately, the application later repeats RAPL/EPP with different governor semantics, and neither layer owns final verification. This duplication creates the PPD contradiction, hides effective state, and makes errors impossible to report transactionally.

A targeted refactor—not a rewrite—is justified:

1. **Introduce a single power-apply result and one owner.** Define a typed `PowerApplyResult` containing requested generation, per-mechanism write result, settled observations, and effective profile. Let one layer execute the complete ordered plan. Concrete benefit: removes fragile dictionary defaults such as `result.get(..., True)`, makes partial failures explicit, and prevents duplicated/conflicting sequencing.
2. **Separate desired, applying, verified, and observed state.** Do not use `_last_applied_power_profile` to overwrite observation. Concrete benefit: UI, hooks, fan curves, and recovery can make correct decisions during convergence/failure.
3. **Model external-manager ownership explicitly.** Either integrate with PPD or implement an opt-in exclusive mode that records/restores service state. Concrete benefit: predictable lifecycle and no persistent surprise to the host.
4. **Extract pure RAPL codec plus injectable OS boundary.** Keep bit arithmetic and sysfs/MSR paths testable without hardware. Concrete benefit: prevents PP-002-class errors and makes resource/short-I/O cases cheap to test.
5. **Version asynchronous convergence.** If delayed settling remains necessary, make it a supervised, latest-generation-wins controller rather than untracked fire-and-forget work. Concrete benefit: eliminates stale writes and provides health/diagnostic visibility.
6. **Represent supported control combinations.** Governor and EPP should not appear independently configurable if the backend cannot honor all combinations. Concrete benefit: configuration, UI, and observed behavior remain aligned and extensible to future drivers/platforms.

The system can remain extensible for custom profiles and future platforms if capabilities describe mechanisms rather than one global writable flag. Platform-specific strategies can implement the same typed apply/observe interface without scattering Intel-specific hard-coded paths and behavior across application orchestration.

## 7. Positive observations

- The change range is small and focused despite the system-wide behavior it touches; the GUI, orchestration, and hardware adapter changes are easy to locate.
- The GUI dirty flag addresses the reported snapshot snap-back at the correct presentation boundary and blocks signals during programmatic selection.
- Startup reconciliation uses existing persisted desired state and intentionally avoids rewriting manual intent during automatic/source-driven application.
- All low-level calls, including delayed ones, go through the existing single-worker command queue; there are no simultaneous direct hardware writes from multiple threads.
- `write_rapl_msr` includes a basic 3–150 W guard and limits the package-scoped write to CPU 0, reducing needless writes compared with the first overhaul revision.
- The later platform guard prevents daemon/MSR/EPP actions on unknown models. This meaningfully limits blast radius even though it does not make the supported path safe.
- A reference to the newest delayed task is retained and cancellation is attempted on shutdown, an improvement over wholly unowned tasks even though lifecycle handling remains incomplete.
- Existing configuration validation rejects unknown profiles and bounds profile fields before the production apply path; custom definitions and auto-switch references persist coherently.
- The adapter aggregates dependency sub-results rather than blindly accepting the dependency’s top-level return, and errors are returned as structured operation results in the immediate phase.
- Documentation openly labels the software alpha and real-hardware testing as a pre-release gate.

## 8. Prioritized remediation plan

### Must fix before merge or release

1. Resolve PP-001: remove startup stop/mask immediately or redesign the complete PPD ownership/apply/restore lifecycle. Repair already masked units during upgrade/uninstall with preservation of prior state.
2. Resolve PP-002: replace and unit-test MSR encoding, add read-back verification, and validate on supported hardware.
3. Resolve PP-003/PP-004: do not report/persist/run hooks on “fully applied” until required settled writes and effective governor/EPP/RAPL are verified. Align accepted profile semantics with what the backend can actually enforce.
4. Resolve PP-005: make newer applies supersede all earlier delayed work; await owned work on shutdown.
5. Add the corresponding deterministic tests. The current fake-only happy path is not a sufficient merge gate.

### Should fix soon afterward

1. Expand capability probing and installed-service validation (PP-006).
2. Make EPP handling structured, injected-root testable, non-vacuous, and read-back verified (PP-007).
3. Fix descriptor/short-I/O handling (PP-008).
4. Correct compatibility, requirements, daemon side effects, and effective-state documentation (PP-009).
5. Pin or formally adapt to a tested `honor-tools` behavior/API; avoid relying on timing and untyped dictionaries across the whole `<0.2` range.

### Optional cleanup and longer-term improvements

1. Introduce the typed result/effective-state model described above and remove asserted-profile overlay from observed state.
2. Derive UI choices from platform capabilities so unsupported governor/EPP combinations cannot be authored.
3. Make repository-wide lint scope explicit (exclude archival reverse-engineering scripts or clean them separately) and ensure the development environment actually installs test/build tools.
4. Add diagnostics for last apply generation, settled observations, external manager ownership, and rollback status.

### Validation plan after fixes

1. Run the full unit/integration suite plus scoped Ruff, compile, diff check, shell syntax, and package build in a freshly created documented dev environment.
2. Run deterministic fake-OS integration tests for every failure/rollback stage and rapid transition ordering.
3. Install the actual systemd unit in an isolated supported-hardware test environment; verify capability access under its sandbox.
4. Record pre-state for PPD/`intel_lpmd`, HWP, governor/EPP, RAPL MSRs, turbo, and max performance. Apply each built-in and representative custom profile; sample observed state across the overwrite/settle window.
5. Exercise rapid GUI/CLI changes, AC/battery transitions, service restart/crash/stop/disable, reboot, upgrade, and uninstall. Confirm no stale write and exact restoration of external-manager state.
6. Only then perform thermal/load validation within vendor-safe bounds and confirm PL1/PL2 behavior; this must be a deliberate manual hardware gate, not an automated CI action.

## 9. Final verdict

**Unsafe to merge or release.**

To advance even to **Requires significant fixes**, the branch must stop persistently disabling a dependency it still requires and must correct the PL2 MSR encoding. To reach **Ready with minor fixes**, power application must become a verified, latest-generation-wins transaction whose failures and effective governor/EPP/RAPL state are accurately reported, with lifecycle restoration and deterministic tests. Release readiness additionally requires the repository’s stated real-hardware gate, including reboot/service/uninstall recovery, to pass on the supported MRA-XXX platform.
