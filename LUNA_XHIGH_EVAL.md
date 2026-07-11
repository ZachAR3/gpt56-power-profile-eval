# LUNA EXHIGH Evaluation

## 1. Executive summary

The power-profile overhaul has a sound high-level goal—make the Honor service the authoritative owner of CPU power settings and reapply the persisted profile after restart—but the current implementation is not ready to merge or release.

The most serious issue is an ownership contradiction: startup stops and masks `power-profiles-daemon`, while the delegated `honor-tools` apply path still calls `powerprofilesctl set` and the application requires `ppd_ok` for success. On a normal installation this makes reconciliation and subsequent profile changes partial or unsuccessful. The new direct RAPL path also encodes the PL2 enable/time-window bits beyond the 64-bit MSR value, so those bits are discarded. Finally, the delayed EPP rewrite deliberately leaves a requested `performance` governor at `powersave`, and its boolean failures are ignored after the UI/state have already reported success.

The architecture around the change is promising: typed immutable models, atomic validated persistence, positive platform detection, a serialized hardware queue, and a GUI dirty-state fix are all good foundations. However, the new privileged OS integration lacks a complete ownership contract, transactional verification, lifecycle cleanup, and production-like tests.

**Final verdict: Unsafe to merge or release.** The PPD ownership contract, RAPL bit packing, delayed rewrite semantics/error reporting, and daemon lifecycle must be corrected before this can advance to “Requires significant fixes.”

## 2. Scope and methodology

### Repository and comparison base

- Reviewed repository: `honor-control`, the nested Git repository at `/home/zach/Desktop/productivity/misc/HonorTools/honor-control`.
- The workspace-level `.git` is not a usable Git repository; sibling projects are separate directories. The power-profile commits and default branch are in `honor-control`.
- Branch: `main`.
- Reviewed commit: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f` (`README: document Intel-only compatibility`), also `origin/main` and `origin/HEAD`.
- `git merge-base HEAD origin/main` is the reviewed commit itself because the reviewed branch is the default branch. For a meaningful overhaul comparison, I used `4d8994a` (`Initial commit: Honor Control — D-Bus service and Qt6 GUI for Honor MagicBook laptops`) as the pre-overhaul baseline.
- Effective change range: `4d8994a..34d31f9`, containing the four commits below. The initial commit is a root commit, so `4d8994a^` is not a valid comparison base.

Relevant commits:

- `15f4d66` — Fix power profile application: RAPL, EPP, and UI snap-back.
- `d391bb0` — Clean up power profile code: safety, simplicity, correctness.
- `7213294` — Guard `stop_competing_power_daemons` behind platform detection.
- `34d31f9` — Document Intel-only compatibility.

The range changes only four files: `README.md`, `honor_control/backend/application.py`, `honor_control/backend/hardware.py`, and `honor_control/frontend/gui/pages/power.py` (326 insertions, 7 deletions). I also inspected the delegated sibling dependency at `../honor-tools/honor/power.py`, because the production adapter calls its `apply_profile` implementation.

### Subsystems inspected

- Application lifecycle, mutation serialization, delayed tasks, startup reconciliation, AC/battery auto-switching, refresh/state publication, and shutdown.
- `HardwarePort`, `FakeHardware`, `HonorToolsAdapter`, platform allowlisting, capability detection, sysfs paths, RAPL, EPP, HWP, MSR access, `systemctl`, and the delegated `honor-tools` power implementation.
- `ConfigStore`, profile defaults, TOML validation/persistence, snapshot models, D-Bus APIs, polkit authorization, systemd service hardening, CLI integration, GUI integration, and documentation.
- Power, hardware, application, GUI, configuration, client, backend, and sibling `honor-tools` tests.

### Commands and results

- `git status --short --branch`, branch/log/remote inspection: clean `main`, tracking `origin/main`; no pre-existing worktree changes.
- `git diff --stat 4d8994a..HEAD`, `git diff --name-status`, `git show`, `git blame`, and `git diff --check`: completed; diff whitespace check passed.
- `.venv/bin/ruff check honor_control tests`: passed.
- `.venv/bin/python -m compileall -q honor_control`: passed.
- Backend, GUI, and CLI import checks: passed.
- `systemd-analyze verify packaging/systemd/honor-control.service`: passed.
- `.venv/bin/pytest` was not present, so pytest was run with the available `/home/zach/.local/bin/pytest` (pytest 9.1.1, Python 3.14.6).
- `pytest -q tests/test_hardware.py tests/test_gui.py`: **36 passed**.
- `pytest -q tests/test_config_store.py tests/test_cli.py tests/test_core.py tests/test_polkit.py tests/test_validation.py tests/test_gesture_runtime.py`: **108 passed**.
- `pytest -q` and application tests did not complete. The isolated unchanged queue test `tests/test_backend.py::TestCommandQueue::test_run_executes_function` fails under the available Python 3.14.6 after the ten-second default timeout with `CommandTimeoutError` at `honor_control/backend/command_queue.py:114`. An application initialization test similarly timed out. This is a pre-existing/general queue/tooling issue; `command_queue.py` is outside the overhaul diff, although the new direct `stop_daemons` call makes the interaction visible during initialization.
- Sibling `honor-tools`: `pytest -q` passed (**31 passed**); its `ruff check honor tests` reported 12 existing unused-import/style errors. No sibling files were modified.
- `command -v powerprofilesctl`: `/usr/bin/powerprofilesctl`; safe `systemctl`/`powerprofilesctl get` probes could not connect in this sandbox and returned `Operation not permitted`. No service, daemon, sysfs, MSR, or real hardware mutation was attempted.
- No mypy, pyright, pylint, bandit, or semgrep configuration/tool was available.

### Limitations and assumptions

- I did not run hardware-marked tests or invoke the production apply path because it writes CPU power controls and system services.
- The PPD failure described below is a code-level inference from the delegated `powerprofilesctl set` call and the application’s mandatory `ppd_ok` check; it was not executed against a real Honor machine.
- The RAPL register analysis assumes the standard IA32 package power-limit layout that the implementation itself claims to target. A local calculation confirmed that the PL2 enable/time-window bits become zero after the code’s shift and mask.
- The reviewed report is written at the `honor-control` repository root. No production source file was modified.

## 3. Architecture and behavior overview

The service is a root systemd process exposing a versioned D-Bus API. The CLI and Qt GUI use the client protocol and do not access hardware directly. D-Bus methods are authorized by polkit, then delegated to `ApplicationService`.

Power state has three representations:

1. `ConfigStore` owns persisted desired state in `/var/lib/honor-control/state.toml`. It stores the selected profile, AC/battery policy, and editable profile definitions. Profile values are validated, including PL1/PL2 bounds, governor/EPP/PPD enumerations, and maximum-performance range.
2. `SnapshotStore` publishes immutable `PowerSnapshot` values to D-Bus and the GUI. It combines desired configuration with hardware observations.
3. `ApplicationService._last_applied_power_profile` is an in-memory name-only marker. Live hardware status comes from `HonorToolsAdapter.read_power`, which delegates to `honor.power.get_status` and maps the reported PPD name to a profile name.

The main apply path is:

1. `set_power_profile` validates the profile name and enters the global mutation lock.
2. `_apply_power_profile` asks the hardware adapter for capability. The current capability check requires the Honor platform guard and the presence of the `powerprofilesctl` executable.
3. The serialized `HardwareCommandQueue` calls `HonorToolsAdapter.apply_power_profile` on its worker thread.
4. The adapter creates an `honor-tools` `Config`, injects the application’s definition, and calls `honor.power.apply_profile`. The sibling library writes governor/EPP/RAPL sysfs values, calls `powerprofilesctl set`, and writes turbo/max-performance controls. The adapter translates its nested result to `governor_ok`, `epp_ok`, `ppd_ok`, `rapl_ok`, and `misc_ok`.
5. Only if all five flags are true does the application mark the profile applied and persist the desired name. It refreshes the snapshot and schedules a new fire-and-forget delayed task.
6. After 0.5 seconds, that task writes PL1/PL2 through `/dev/cpu/0/msr`, then rewrites EPP through every discovered CPU’s absolute sysfs path. The returned booleans are currently discarded.

Startup loads configuration and refreshes all domains. The overhaul then calls `stop_competing_power_daemons`, which stops and masks `power-profiles-daemon` and `intel_lpmd` on the verified Honor platform and attempts to enable HWP dynamic boost. It then reconciles the persisted desired profile only when the name reported by the initial snapshot differs from the desired name.

Background refresh runs every five seconds. AC/battery auto-switch checks every two seconds, applies the configured transition profile with `persist_desired=False`, and runs an optional validated root-owned hook after a successful base apply. Normal shutdown cancels only the latest pending power task, stops supervised controllers, and closes the hardware queue. It does not restore or unmask the system power daemons.

## 4. Findings

### Critical

#### PP-001 — The overhaul disables PPD while the apply contract still requires PPD

- **Severity:** Critical
- **Confidence:** High
- **Category:** Functional correctness / operating-system integration
- **Status:** Newly introduced by `15f4d66`/`d391bb0`; the platform guard in `7213294` narrows the affected hardware but does not resolve the contract.
- **Affected paths:** `honor_control/backend/application.py:164-165, 348-353`; `honor_control/backend/hardware.py:806-842, 844-885`; dependency path `../honor-tools/honor/power.py:175-231`.

`initialize()` stops and masks `power-profiles-daemon` before `_reconcile_power_profile()` runs. The delegated `honor-tools` implementation still calls `powerprofilesctl set <profile>` and returns `ppd_ok=False` when that command cannot reach PPD. `HonorToolsAdapter` maps that value to `ppd_ok`, and `_apply_power_profile` requires `ppd_ok` along with all other flags before reporting success.

The capability probe only checks whether the `powerprofilesctl` executable exists (`hardware.py:597-619`); it does not know that the daemon was just stopped. Therefore a normal installed system can report power capability as supported, stop its provider, then fail the required provider operation. Because the result is partial, the delayed direct MSR/EPP rewrite is not scheduled.

**Failure scenario and impact:** after service startup on a verified laptop with PPD installed, reconciliation and every later profile change can return `power_partial_apply` with `ppd=False`. Some direct writes may already have occurred before the PPD call, so the machine can be left in a mixed state while the GUI reports no fully applied profile. This defeats the main purpose of the overhaul.

**Recommended fix:** establish one explicit owner. Either keep PPD running and make the ordering/retry strategy reliable, or remove the PPD dependency from the adapter and make `ppd_ok` optional/represented as intentionally disabled while the service owns the equivalent controls. Capability detection, apply results, readback, and documentation must all use the same ownership model. Do not declare success unless the selected ownership contract has been verified.

**Suggested tests:** mock `powerprofilesctl` as present but its daemon unavailable; assert startup reconciliation and manual/automatic applies use the intended direct path and return an accurate result. Add an integration test for PPD active, stopped, missing, and masked states.

### High

#### PP-002 — System-wide daemon masks persist after shutdown, failure, or uninstall

- **Severity:** High
- **Confidence:** High
- **Category:** Lifecycle / privilege boundary / recovery
- **Status:** Newly introduced.
- **Affected paths:** `honor_control/backend/hardware.py:844-896`; `honor_control/backend/application.py:181-186`; `packaging/systemd/honor-control.service:7-12`.

The code uses `systemctl stop` followed by `systemctl mask` for both daemons. The mask is persistent and system-wide. There is no matching `unmask` or `start` path in `ApplicationService.shutdown`, the service’s `ExecStopPost` only restores fan auto mode, and the installer/uninstaller does not establish ownership of or restore the prior daemon state.

**Failure scenario and impact:** a service update, configuration error, crash loop, or uninstall can leave PPD masked indefinitely. If Honor Control is not running, the user loses the distribution’s normal CPU power manager. The method also does not record whether a unit was initially disabled, enabled, or already masked, so an unconditional future unmask would be unsafe.

**Recommended fix:** avoid persistent masking from application code. Prefer a documented package/systemd ownership arrangement, or record the exact prior unit state and restore it in a failure-safe lifecycle path and uninstall flow. If masking remains unavoidable, make it a separately managed installation action with explicit user consent and a tested rollback.

**Suggested tests:** exercise clean shutdown, SIGTERM during startup, failed reconciliation, service restart, and uninstall with PPD initially enabled, disabled, and already masked. Assert the original state is restored and that partial masking cannot survive a failed startup.

#### PP-003 — PL2 enable and time-window bits are shifted out of the RAPL register

- **Severity:** High
- **Confidence:** High
- **Category:** Hardware correctness
- **Status:** Newly introduced.
- **Affected path:** `honor_control/backend/hardware.py:999-1019`.

The method builds `hi` with `pl2_units | (1 << 47) | (tw2 << 49)`, then computes `val = lo | (hi << 32)`. In the standard 64-bit package power-limit layout assumed by the comments, PL2’s enable bit is bit 47 and its time-window field is bits 49-55 in the final value. Setting those positions before shifting moves them to bits 79 and above; the final `& 0xFFFFFFFFFFFFFFFF` removes them. The PL2 numeric limit survives because its units start at bit 0 before the shift, but PL2 enable and the intended time window do not.

A local calculation using the same expression produced `pl2_enable_bit=0` and `pl2_time_window=0` in the final value. The code therefore does not implement the “PL1/PL2 enabled with preserved windows” behavior claimed by its comments.

**Failure scenario and impact:** performance profiles may not enforce the intended burst limit, or may depend on stale hardware state for PL2 behavior. The profile can appear applied while its short-term power envelope is not the requested one.

**Recommended fix:** construct the final 64-bit value directly with fields at their final positions, preserve only documented fields, validate the resulting bit layout, and read back/decode the register before returning success. Verify the exact register semantics for the supported CPU family and any MMIO RAPL variant.

**Suggested tests:** pure unit tests with mocked MSR reads for multiple power-unit exponents and time windows; decode the written 64-bit value and assert PL1, PL2, enable, clamp, and time-window fields independently. Add a target-hardware readback test as a manual release gate.

#### PP-004 — The delayed EPP rewrite makes the performance profile leave `powersave` selected

- **Severity:** High
- **Confidence:** High
- **Category:** State transition / hardware semantics
- **Status:** Newly introduced.
- **Affected paths:** `honor_control/backend/application.py:367-418`; `honor_control/backend/hardware.py:898-959`; profile definition `honor_control/core/models.py:297-305`.

The built-in performance profile requests `governor="performance"`. The normal delegated apply writes that governor. The delayed `rewrite_epp` then first writes `powersave` on every CPU and, when the requested governor is `performance`, intentionally does not restore it (`hardware.py:926-959`). The method returns true for successful EPP writes even though the final governor is different from the requested profile.

**Failure scenario and impact:** roughly 0.5 seconds after a successful performance apply, the CPU policy is `powersave`, despite the profile definition, UI, and successful `OperationResult` saying performance. This is a user-visible regression in the core feature and is especially misleading because the workaround is not represented in the model or snapshot.

**Recommended fix:** do not combine incompatible governor/EPP requirements behind a silent state substitution. Define the supported combinations explicitly, or use a driver-supported sequence that preserves both requested semantics. If the platform genuinely cannot represent `performance` governor plus the chosen EPP, return a structured partial/unsupported result and show the effective state.

**Suggested tests:** model a fake sysfs CPU set and assert the final governor/EPP pair for every built-in and custom combination. Add a delayed-task test that waits past 0.5 seconds and verifies the snapshot/effective hardware state matches the result.

#### PP-005 — Delayed hardware failures are ignored after state is persisted and success is returned

- **Severity:** High
- **Confidence:** High
- **Category:** Error handling / persistence synchronization
- **Status:** Newly introduced.
- **Affected paths:** `honor_control/backend/application.py:353-421`; `honor_control/backend/hardware.py:898-1044`.

The application persists desired state, refreshes the snapshot, and returns `applied=True` before the delayed MSR/EPP operations execute. `_delayed_power_rewrite` discards both boolean return values and logs only exceptions. A normal `False` from `write_rapl_msr` or `rewrite_epp` therefore produces no state transition, no `last_error`, no partial result, and no retry. `write_rapl_msr` is expected to return false for common permission/device failures.

**Failure scenario and impact:** the direct MSR path is unavailable, the EPP file is missing, or one CPU write fails. The GUI and persisted state still say the profile applied, and startup reconciliation may later skip work based only on the profile name. The machine can remain on the wrong power limits indefinitely.

**Recommended fix:** make the follow-on operation part of an explicit state machine. Either await and verify it before returning success, or publish a pending state and transition to applied/partial/failed only after readback. Check booleans, record per-mechanism failures, cancel/retry deliberately, and make reconciliation use the resulting effective state.

**Suggested tests:** make each delayed operation return false, raise, timeout, or partially succeed; assert the public result, snapshot, persisted desired state, logs, and retry/recovery behavior. Test shutdown at each point in the delayed sequence.

#### PP-006 — Startup can time out because the best-effort daemon stop exceeds the queue deadline

- **Severity:** High
- **Confidence:** High
- **Category:** Concurrency / startup reliability
- **Status:** Newly introduced.
- **Affected paths:** `honor_control/backend/application.py:164`; `honor_control/backend/hardware.py:874-885`; `honor_control/backend/command_queue.py:26,68-121`.

The application runs `stop_competing_power_daemons` through the hardware queue’s default ten-second timeout. The method performs four sequential `systemctl` calls, each with its own five-second timeout. In the worst case the worker can remain in the method for twenty seconds while the queue marks the command timed out after ten seconds. The next queued call can then be rejected as busy while the old worker operation continues. `initialize()` does not catch this failure.

**Failure scenario and impact:** a systemd or system-bus call is slow or unavailable. Service startup fails or enters a restart loop, while the worker may continue stopping/masking units after the application has already failed. This is contrary to the method’s “best-effort” documentation and can compound PP-002.

**Recommended fix:** use one bounded systemd transaction or a timeout budget no greater than the outer queue deadline; preferably make daemon ownership a service/package operation rather than four synchronous subprocess calls. Catch and publish a non-fatal unavailable result if the policy truly is best-effort.

**Suggested tests:** inject four slow `systemctl` calls and assert startup remains bounded, no queue poisoning occurs unexpectedly, and the failure state is visible. Test missing systemd, a failed bus call, and successful calls.

### Medium

#### PP-007 — Power capability is reported from an executable check, not from the mechanisms the overhaul requires

- **Severity:** Medium
- **Confidence:** High
- **Category:** Capability detection / portability
- **Status:** Pre-existing code, worsened by the overhaul’s new `/dev/cpu/0/msr`, HWP, and per-CPU EPP dependencies.
- **Affected paths:** `honor_control/backend/hardware.py:597-619`; `honor_control/backend/hardware.py:898-1044`; `docs/hardware-support.md:23-28`.

`get_power_capability` checks the positive Honor platform match and `shutil.which("powerprofilesctl")`, but not `/dev/cpu/0/msr`, `intel_pstate`, per-CPU governor/EPP files, HWP dynamic boost, RAPL sysfs trees, or whether the PPD service is reachable. The delegated apply can return partial flags after writes have already occurred, while the capability still says supported. The documentation claims that each power mechanism is checked separately, which is not what this code does.

**Failure scenario and impact:** a verified DMI/CPU identity runs a different kernel, container, hardened service, or missing MSR module. The UI offers the feature, direct writes fail later, and the delayed failure is hidden by PP-005.

**Recommended fix:** make capability probing a non-mutating per-mechanism result, including the exact resources and permission state needed by the chosen ownership model. Make the application require only the mechanisms a selected profile actually uses, or clearly report partial availability.

**Suggested tests:** build temporary sysfs fixtures and mock `/dev/cpu/0/msr`, PPD reachability, EPP, governor, HWP, and RAPL resources independently. Assert capability reason codes and apply gating for each missing mechanism.

#### PP-008 — Raw MSR I/O is not exception-safe or write-complete

- **Severity:** Medium
- **Confidence:** High
- **Category:** Resource lifecycle / error handling
- **Status:** Newly introduced.
- **Affected path:** `honor_control/backend/hardware.py:988-1036`.

The new method manually opens the MSR device multiple times and closes descriptors only on the normal path. A short read can make `struct.unpack` raise an exception that is not caught by the `except OSError` handler, leaving the descriptor open. The write does not check that `os.write` wrote all eight bytes, and there is no register readback before returning `True`.

**Failure scenario and impact:** a transient or unusual MSR device response leaks descriptors or raises through the worker; a short/partial write is reported as successful. Repeated profile changes can degrade the service and leave unknown hardware state.

**Recommended fix:** use context-managed descriptors or `try/finally`, catch and classify all expected decoding/I/O errors, loop/check for a complete write, and read/decode the register after writing. Return a structured result rather than a bare boolean if partial state matters.

**Suggested tests:** mock short reads, `struct.error`, `os.write` returning fewer than eight bytes, open failures, and readback mismatches; assert descriptors are closed and false/partial status is propagated.

#### PP-009 — Delayed tasks are not fully owned or ordered by the service lifecycle

- **Severity:** Medium
- **Confidence:** Medium
- **Category:** Concurrency / lifecycle
- **Status:** Newly introduced.
- **Affected paths:** `honor_control/backend/application.py:126, 367-373, 391-421`; `honor_control/backend/application.py:181-186`.

The service stores only one `_pending_power_task`. A new apply overwrites that reference without cancelling or awaiting the previous task. The supervisor does not own these tasks, and shutdown cancels only the latest one. Rapid manual changes or AC/battery transitions can leave older profile rewrites queued after a newer profile; shutdown can also race with an older task already waiting on the hardware queue.

**Failure scenario and impact:** a stale delayed task writes the previous profile’s RAPL/EPP after a newer selection, or a task emits a late queue operation during teardown. The result is nondeterministic effective power state and hard-to-reproduce race behavior.

**Recommended fix:** put delayed power work under a dedicated supervisor/controller with one generation token or cancellation policy. Cancel and await the prior task before replacing it, and make each task verify it is still the current desired generation before writing.

**Suggested tests:** apply profiles A/B/C within less than 0.5 seconds, vary queue delays, then assert only C reaches the delayed hardware methods. Test cancellation before sleep, during MSR I/O, during EPP I/O, and at shutdown.

#### PP-010 — Startup reconciliation compares only a profile name, not the actual definition

- **Severity:** Medium
- **Confidence:** High
- **Category:** State synchronization / persistence
- **Status:** Newly introduced.
- **Affected paths:** `honor_control/backend/application.py:1013-1045, 1102-1144`; `honor_control/backend/hardware.py:778-804`.

`_reconcile_power_profile` skips application when `snapshot.power.applied_profile == desired`. The live adapter derives that applied name from the PPD profile string, while RAPL, EPP, governor, turbo, and maximum-performance values are not compared to the persisted definition. A same-name PPD state is therefore treated as full equivalence.

**Failure scenario and impact:** a customized built-in profile, suspend/resume, firmware reset, or partial previous apply leaves one mechanism wrong while the PPD name remains the same. A service restart skips reconciliation and preserves the drift.

**Recommended fix:** compare each supported observed mechanism with the desired definition, persist an applied-definition fingerprint if useful, or always reapply on startup when the service owns the hardware. Represent unknown/stale observations explicitly.

**Suggested tests:** keep the reported profile name constant while varying each observed field; assert reconciliation repairs mismatches and skips only a verified exact match.

#### PP-011 — New hardware paths bypass the adapter’s injectable root and are hard to test safely

- **Severity:** Medium
- **Confidence:** High
- **Category:** Testability / platform abstraction
- **Status:** Newly introduced.
- **Affected paths:** `honor_control/backend/hardware.py:444-455, 889-895, 921-945, 988-1025`.

`HonorToolsAdapter` already accepts `root_path` and provides `_rooted`, but the new HWP, CPU cpufreq, and MSR operations use hard-coded absolute paths and `glob.glob` against the host. The existing filesystem tests can exercise platform discovery but cannot safely exercise these new write paths without touching the real machine.

**Failure scenario and impact:** a chroot/container or fixture-backed adapter can read one root while the new methods write the host. Production-like tests are effectively excluded, leaving the most privileged code covered only by `FakeHardware` methods that always return `True`.

**Recommended fix:** inject a filesystem/device and command runner, or consistently root all paths through an adapter abstraction. Keep raw MSR access behind a small platform-specific backend that can be fully mocked.

**Suggested tests:** use a temporary fake CPU/RAPL tree and a mocked MSR device/systemctl runner; assert no path outside the fixture is accessed.

#### PP-012 — The service’s existing command-queue test contract is broken in the reviewed environment

- **Severity:** Medium
- **Confidence:** High for the observed failure; Medium for root cause
- **Category:** General async infrastructure / testability
- **Status:** Pre-existing and unrelated to the overhaul; the overhaul interacts with it during new startup initialization.
- **Affected paths:** `honor_control/backend/command_queue.py:68-121`; `tests/test_backend.py:70-73`.

With Python 3.14.6, `pytest -vv tests/test_backend.py::TestCommandQueue::test_run_executes_function` waits ten seconds and fails with `CommandTimeoutError`. A small direct `asyncio.run(q.run(...))` reproduction showed the same behavior, while an explicitly scheduled task completed. The queue file is unchanged in `4d8994a..HEAD`, so this is not attributed to the power overhaul, but it prevents the application lifecycle tests from being a reliable gate and makes the new direct `initialize()` queue call especially problematic in this environment.

**Recommended fix:** reproduce on the project’s intended Python versions, then fix or constrain the queue’s cross-thread future completion behavior and test both direct-await and scheduled-task callers. Do not accept a release with the documented full suite unable to complete.

**Suggested tests:** run the queue tests on every supported Python version, test direct `asyncio.run`, nested application calls, cancellation, timeout poisoning, and loop shutdown.

### Low

#### PP-013 — README compatibility wording does not match the actual platform gate

- **Severity:** Low
- **Confidence:** High for the internal inconsistency
- **Category:** Documentation / platform expectations
- **Status:** Newly introduced by `34d31f9`.
- **Affected paths:** `README.md:11-16`; `honor_control/backend/hardware.py:505-547, 597-619`.

The README says AMD-based Honor laptops will have “sysfs-only EPP” power behavior. The actual positive platform allowlist requires the Intel/Meteor Lake markers and returns `UNSUPPORTED` before power writes on an AMD platform, so the service does not expose that sysfs-only path. The broad statement that all Honor MagicBook laptops released to date use Intel is also not substantiated by repository evidence.

**Recommended fix:** document the actual behavior: unsupported platforms receive no power writes. If future AMD support is intended, add a separate capability/backend rather than implying a partial implementation that the current gate does not provide.

**Suggested tests:** assert the README-supported platform matrix against capability behavior for Intel, AMD, unknown Honor, and non-Honor fixtures.

## 5. Test and validation assessment

Existing coverage is strongest around pure validation, configuration persistence, D-Bus/client codecs, fake hardware, platform discovery, and GUI construction. The GUI test suite covers editor dirty-state preservation, but not the new active-profile selection dirty flag.

The following important behavior is not meaningfully tested:

- Startup daemon stop/mask behavior, systemd state ownership, rollback, and service failure paths.
- PPD active/stopped/missing behavior and the contract between `HonorToolsAdapter` and `honor-tools`.
- Raw MSR bit encoding, power-unit conversion, PL1/PL2 readback, MMIO RAPL variants, descriptor cleanup, permissions, and partial writes.
- EPP/governor final-state combinations, especially the performance profile after the 0.5-second task.
- Delayed task cancellation, generation ordering, rapid profile changes, automatic transitions, and service shutdown.
- Capability probes for the direct hardware mechanisms added by the overhaul.
- Startup reconciliation when a same-name profile has different observed settings.
- Realistic `HonorToolsAdapter` behavior; `FakeHardware` returns true for every new method and therefore cannot expose these failures.

The existing `tests/test_application.py` tests are not a sufficient release gate in the current environment because service initialization cannot complete through the queue. The non-queue tests passing does not validate the production power path. The sibling `honor-tools` power tests pass, but they test its sysfs/PPD helper in isolation and do not cover the new adapter, systemd, MSR, or cross-package ownership behavior.

Prioritized additional tests:

1. A pure MSR encoder/decoder test suite, including exact PL2 enable/time-window assertions and readback mismatch handling.
2. A mock integration test for PPD ownership: active provider, unavailable provider, masked provider, and no provider.
3. A full `ApplicationService` apply/reconcile test using a fake hardware backend whose delayed MSR/EPP operations can fail, block, or return false.
4. A task-generation test for rapid manual and auto-switch transitions plus shutdown cancellation.
5. A fixture-backed `HonorToolsAdapter` test for CPU sysfs, HWP, RAPL, and MSR paths; no host writes.
6. Lifecycle tests proving daemon state restoration after normal stop, failed startup, crash/restart, and uninstall.
7. GUI tests for active-combo preservation, apply success/failure, profile-list changes, and external/automatic transitions.
8. Run all of the above on the supported Python versions, with the queue direct-await regression resolved first.

## 6. Architecture and maintainability assessment

The existing separation between D-Bus, application orchestration, immutable models, configuration, snapshots, and hardware adapter is good. The positive platform allowlist and the rule that unsupported hardware cannot write are especially appropriate for a hardware-control project. The global mutation lock plus serialized worker queue also gives the system a clear serialization point.

The overhaul introduces a second, implicit power-control layer beside `honor-tools`: the dependency performs the normal profile transaction, while `HonorToolsAdapter` performs direct MSR and EPP corrections after the transaction. Neither layer owns the complete profile contract. This is the root of the PPD contradiction, the unreported delayed failures, and the mismatch between requested and effective governor state.

A targeted refactor is justified, not a rewrite:

- Define an explicit power backend contract with capability probes, ownership mode, requested state, effective state, and per-mechanism verification. The adapter should return a structured transaction result rather than a loosely interpreted nested dictionary.
- Put PPD coordination and direct CPU control behind the same backend. A profile should have one authoritative apply sequence, one rollback/partial-failure policy, and one readback path.
- Represent delayed work as a supervised generation-based controller, not an untracked task stored in one replaceable attribute. This prevents stale writes and gives shutdown a clear ownership boundary.
- Separate hardware path access and command execution behind injectable interfaces. This makes MSR/sysfs/systemctl behavior testable without relaxing the production safety boundary.
- Keep profile definitions and observed/effective state distinct. A name alone is insufficient once profiles are editable and contain multiple independent controls.
- Treat platform support as a capability matrix. MRA/Intel identity, PPD availability, sysfs support, MSR access, and EPP/governor compatibility should not collapse into one executable-present boolean.

The GUI change is small and reasonably cohesive, but its active-selection state should be tested separately from editor state. The current use of multiple dirty flags is acceptable for now; a shared view-model or explicit “pending selection” state would become worthwhile if more asynchronous controls are added.

## 7. Positive observations

- The service keeps frontends away from hardware and configuration writes; D-Bus/polkit remains the system boundary.
- The verified platform allowlist is conservative, and `7213294` correctly prevents the new daemon-stop behavior from touching unknown/non-Honor hardware.
- Configuration parsing validates profile names, PL1/PL2 ranges, governor/EPP/PPD values, turbo state, and maximum-performance percentage. Atomic state persistence and separate desired/applied flags are good foundations.
- The `3-150 W` MSR bounds added in `d391bb0` are a useful defense-in-depth measure, even though the register construction and verification still need correction.
- The GUI’s `_active_combo_dirty` fix directly addresses the reported five-second snapshot snap-back and uses signal blocking for programmatic selection changes. Existing GUI tests continue to pass.
- Delayed work at least has a reference and cancellation attempt after `d391bb0`; this is better than the original unreferenced task, though it is not sufficient for multiple concurrent applies.
- The README explicitly labels the project Alpha and calls real hardware validation a manual pre-release gate. That disclosure is appropriate given the absence of production-like hardware tests.
- The sibling `honor-tools` power unit has focused tests for profile application inputs, while the repository’s pure config, codec, platform, and GUI tests provide a useful base for adding the missing integration cases.

## 8. Prioritized remediation plan

### Before merge/release

1. Choose and implement a single PPD/direct-control ownership model. Remove the unconditional runtime mask unless its lifecycle and contract are fully designed.
2. Fix the IA32 package power-limit bit assembly and add encode/decode/readback tests. Confirm the supported CPU’s MSR versus MMIO RAPL behavior.
3. Make the final effective governor/EPP state match the profile contract, or explicitly model and report a supported alternative instead of silently leaving `powersave`.
4. Make delayed work transactional and observable: handle false returns, exceptions, timeouts, partial state, retries, persistence, and snapshot updates consistently.
5. Add safe daemon restoration for normal shutdown, failed initialization, service crash/restart, and uninstall, preserving the pre-existing unit state.
6. Resolve the command-queue Python/runtime regression and make the full `honor-control` suite a required gate.

### Soon afterward

1. Replace executable-only capability detection with a per-mechanism capability matrix.
2. Add structured MSR I/O with context-managed descriptors, complete-write checks, readback, and explicit permission/error codes.
3. Move power tasks under a supervisor or generation-based controller and test rapid profile/AC transitions.
4. Reconcile by effective definition, not only profile name.
5. Inject filesystem/device/subprocess dependencies so the direct hardware path can be tested without real writes.

### Optional cleanup and longer-term improvements

1. Align the README and hardware-support documentation with actual AMD/unsupported-platform behavior.
2. Remove stale inline comments and keep the cross-package power contract documented in one place.
3. Add static typing for the hardware result dictionaries or replace them with typed result models.
4. Clean up the sibling `honor-tools` lint errors so dependency quality does not obscure integration regressions.

### Validation plan after fixes

Run pure encoder/validation tests, fixture-backed adapter tests, mocked PPD/systemd lifecycle tests, application state-machine tests, GUI tests, all linters/type checks available in CI, and the complete test suite on supported Python versions. Then perform a manual release gate on the verified MRA-XXX hardware: capture daemon state before installation, apply every built-in and one custom profile, verify RAPL PL1/PL2 and per-CPU governor/EPP/turbo/max-performance readbacks over time, exercise suspend/resume and AC transitions, stop/restart/uninstall the service, and confirm the original system power-manager state is restored. Record all hardware results before enabling broader distribution.

## 9. Final verdict

**Unsafe to merge or release.** The current implementation can disable the system power manager while still requiring it, can encode the PL2 register incorrectly, can leave the performance profile in `powersave`, and can report success after delayed hardware writes fail. The minimum changes required for the next readiness level are:

- resolve PPD/direct-control ownership and restore system daemon state safely;
- correct and verify RAPL MSR encoding;
- make effective governor/EPP behavior intentional and observable;
- make delayed power operations ordered, cancellable, and error-visible;
- add mocked/fixture-backed tests for the new privileged paths;
- restore a passing, complete application test gate.

Until those changes are verified, passing lint, compilation, GUI, and fake-hardware tests does not establish power-profile correctness or release safety.
