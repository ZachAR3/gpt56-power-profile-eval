# LUNA_HIGH_EVAL

## 1. Executive summary

The power-profile overhaul is directionally strong: it adds explicit desired/applied state handling, a serialized hardware boundary, platform gating, bounded profile validation, a startup reconciliation path, and a GUI fix for refreshes overwriting user selections. The implementation is not ready to merge or release, however.

The most serious defect is in the new direct RAPL MSR encoder. The PL2 enable and time-window bits are constructed using absolute MSR bit positions and then shifted into the high dword a second time. The resulting 64-bit value leaves PL2 disabled. The service also reports a profile as fully applied before its delayed direct-MSR/EPP enforcement runs, ignores the delayed boolean results, and persistently masks system power-management daemons without recording or restoring their prior state. In addition, the delayed path intentionally leaves Performance profiles at the `powersave` governor, contradicting the profile definition.

Final verdict: **Unsafe to merge or release**.

## 2. Scope and methodology

### Repository and comparison

- Repository reviewed: `honor-control` under `/home/zach/Desktop/productivity/misc/HonorTools/honor-control`.
- Branch: `main`, at `34d31f9` (`README: document Intel-only compatibility`), tracking `origin/main`; working tree was clean before this report was created.
- The current branch is itself the repository default branch, so its merge base with the default branch is `HEAD`, which is not a useful pre-change comparison. I therefore used the initial commit `4d8994a` as the defensible pre-overhaul baseline because the subsequent commits are explicitly titled as power-profile fixes/cleanup/platform gating. The reviewed range is `4d8994a..34d31f9`.
- Relevant commits:
  - `15f4d66` — RAPL MSR writes, delayed EPP rewrite, daemon stopping, startup reconciliation, and GUI selection preservation.
  - `d391bb0` — bounds checks, CPU-0 MSR write, startup-only daemon handling, task retention/cancellation, and cleanup.
  - `7213294` — platform guard around daemon stopping.
  - `34d31f9` — Intel-only compatibility documentation.
- The range changes four files: `honor_control/backend/application.py`, `honor_control/backend/hardware.py`, `honor_control/frontend/gui/pages/power.py`, and `README.md`.

### Code and call paths inspected

I inspected the changed files and their surrounding call paths, including:

- `ApplicationService` initialization, profile application, delayed rewrites, startup reconciliation, auto-switching, refresh, shutdown, and persistence.
- `HonorToolsAdapter`, `FakeHardware`, platform allowlisting, capability probes, `honor-tools` integration, sysfs access, RAPL MSR encoding, EPP/governor handling, and systemd daemon control.
- The sibling `honor-tools` implementation of `apply_profile`, `get_status`, RAPL sysfs writes, EPP writes, governor writes, and PPD calls.
- `ConfigStore`, profile validation, default profiles, snapshot models, D-Bus methods, CLI arguments, GUI state/update logic, systemd packaging, install/uninstall scripts, safety documentation, and architecture documentation.
- Existing application, hardware, GUI, backend, config, client, CLI, validation, and dependency tests.

### Commands and results

- `git status --short --branch` — clean `main` checkout before report creation.
- `git log --oneline --decorate` and commit/diff inspection — completed; change range and affected files identified above.
- `git diff --check 4d8994a HEAD` — passed.
- `ruff check honor_control tests` — passed.
- `python -m compileall -q honor_control` — passed.
- `systemd-analyze verify packaging/systemd/honor-control.service` — passed.
- `pytest -q tests/test_hardware.py` — passed, 23 tests.
- `pytest -q` in the sibling `honor-tools` repository — passed, 31 tests.
- `pytest -q` and focused application/backend/GUI runs in this environment did not complete. They stalled at the first cross-thread hardware-queue completion. A minimal reproduction showed the sandbox rejecting asyncio's self-pipe write with `PermissionError: [Errno 1] Operation not permitted`; the callback then did not wake the event loop. An attempt to rerun the full suite outside the sandbox was rejected because it would execute hardware-control code with unrestricted host access. This is recorded as an environment/tooling limitation, not as a verified application assertion failure.
- No real hardware writes, `systemctl` mutations, MSR access, or system configuration changes were performed.
- No type checker is configured in `pyproject.toml`; no mypy/pyright run was available.

### Limitations and assumptions

The review is primarily static and fake-hardware based. The target hardware path is Intel-specific and could not be exercised safely here. Hardware-dependent claims are labeled by confidence and grounded in the source-level bit layout, call ordering, and return-value handling.

## 3. Architecture and behavior overview

The service runs as a root systemd/D-Bus daemon. The GUI, tray, and CLI are unprivileged clients; they submit typed requests over D-Bus and consume cached snapshots. `ApplicationService` owns orchestration and persistence but does not import `honor-tools` directly.

The relevant power flow is:

1. `ApplicationService.initialize()` loads `/var/lib/honor-control/state.toml`, refreshes platform/capability/power snapshots, calls `stop_competing_power_daemons()`, and then attempts to reconcile the persisted desired profile.
2. The application validates a profile name against the persisted profile registry and checks `get_power_capability().writable`.
3. `HonorToolsAdapter.apply_power_profile()` creates an `honor-tools` configuration from the typed profile and calls `honor.power.apply_profile()`. That dependency writes RAPL sysfs limits, temporarily sets all governors to `powersave`, calls `powerprofilesctl`, writes EPP, restores the requested governor, and writes turbo/max-performance settings. The adapter reduces the dependency's nested dictionaries to aggregate booleans.
4. On aggregate success, the application updates `_last_applied_power_profile`, persists desired state when appropriate, refreshes the power snapshot, and schedules `_delayed_power_rewrite()` after 0.5 seconds.
5. The delayed task writes PL1/PL2 directly to `/dev/cpu/0/msr` and rewrites EPP through every CPU's cpufreq sysfs path. Its exceptions are logged; its boolean return values are not propagated into the original operation result or snapshot.
6. The command queue serializes synchronous hardware calls on one daemon thread. The application mutation lock serializes complete application-level mutations. Snapshot updates retain desired state from `ConfigStore` while representing the last observed/applied information.
7. AC/battery auto-switching runs in a background loop. It selects a profile and calls the same `_apply_power_profile()` path without replacing the manually selected desired profile; transition hooks run afterward.
8. The GUI receives snapshots through the worker-thread D-Bus client. The power page maintains dirty flags so a refresh does not overwrite an in-progress selection or profile edit.

State ownership is conceptually split correctly: `ConfigStore` owns desired profiles and policy; `HonorToolsAdapter` owns live hardware I/O; `SnapshotStore` owns immutable observations; `ApplicationService` owns use-case sequencing. In practice, the delayed power task creates a fourth, unrepresented state transition after the application has already declared success.

## 4. Findings

### Critical

#### PP-001 — PL2 is disabled by incorrect MSR bit construction

- Severity: Critical
- Confidence: High
- Category: Hardware correctness / power-limit enforcement
- Status: Newly introduced by the overhaul
- Affected code: `honor_control/backend/hardware.py:1007-1019`, symbol `HonorToolsAdapter.write_rapl_msr()`.

The code builds `hi` as if it were a full 64-bit MSR value, using `(1 << 47)` for PL2 enable and `(tw2 << 49)` for the PL2 time window, and then shifts the entire value left by 32 in `val = lo | (hi << 32)`. Those bits are shifted to positions 79 and above and are removed by the final 64-bit mask. Only the PL2 power-unit value, which happens to be in the low part of `hi`, survives the shift.

The direct calculation against the checked-in expression produced `encoded=0x0000000000018000 pl2_enable_bit=0 pl2_time_window=0` for the enable/time-window portions. In the high dword representation, PL2 enable and its time-window field should be relative to that dword (bits 15 and 17 respectively), or the code should construct the complete 64-bit value without the second shift.

A realistic Performance apply therefore writes PL1 enabled, but writes a PL2 value with PL2 enable clear. Burst power behavior is not the requested 55 W envelope and may depend on stale hardware state. This is a direct correctness defect in newly added CPU hardware control.

Recommended fix: correct the field positions, mask each field explicitly, preserve only intended fields, and read back/decode MSR 0x610 after writing. Add a pure encoder test that asserts PL1 enable bit 15, PL2 enable bit 47, both power fields, and both time-window fields.

Suggested tests: unit-test the encoder with a known power-unit value and old time windows; test zero/max field boundaries; mock `os.open`, `os.read`, `os.write`, and assert the exact 64-bit payload and a full eight-byte write.

### High

#### PP-002 — The operation reports “applied” before delayed enforcement and ignores enforcement failure

- Severity: High
- Confidence: High
- Category: Error handling / state synchronization
- Status: Newly introduced by the overhaul
- Affected code: `honor_control/backend/application.py:338-381` and `391-421`; `honor_control/backend/hardware.py:898-959` and `961-1036`.

The initial `honor-tools` result only proves that the dependency's sysfs writes and PPD command returned success. The direct MSR write and the second EPP rewrite happen later in a fire-and-forget task. `_delayed_power_rewrite()` does not check the boolean results from `write_rapl_msr()` or `rewrite_epp()`, and catches exceptions only to log a warning. The original call then returns `OperationResult.success(... applied=True)` and, for manual applies, persists the desired profile before the delayed hardware state is known.

If `/dev/cpu/0/msr` is absent, denied, unsupported, or the EPP path cannot be written, the user receives success and the snapshot continues to identify the selected profile as applied. A restart reconciliation can also treat that persisted selection as authoritative. This violates the repository's stated desired/applied/observed separation and makes a safety-critical failure invisible to the API.

Recommended fix: either make the complete enforcement/verification part of the awaited operation, or model a typed `pending` state and transition to `applied` only after successful readback. Propagate partial failure, mark the power domain stale/degraded, and retry or expose a recovery action. Verify RAPL, governor, EPP, PPD, turbo, and max-performance values rather than relying on write-return booleans.

Suggested tests: make fake MSR and EPP operations fail after the base apply; assert `partial`/`failed`, no false `applied=True`, appropriate snapshot state, and a bounded retry. Test shutdown while enforcement is pending.

#### PP-003 — Startup permanently masks system power managers without reversible ownership

- Severity: High
- Confidence: High
- Category: Privilege boundary / lifecycle / compatibility
- Status: Newly introduced by the overhaul
- Affected code: `honor_control/backend/application.py:155-165`; `honor_control/backend/hardware.py:844-896`; `scripts/uninstall-local.sh:19-49`.

Every supported-platform service startup invokes `stop_competing_power_daemons()`, before checking whether power control is actually writable. On an allowlisted Honor platform it runs `systemctl stop` and `systemctl mask` for both `power-profiles-daemon` and `intel_lpmd`, then attempts a global HWP sysfs write. Return codes are ignored and no prior enabled/running/masked state is captured. Shutdown only cancels an application task and stops the queue; it does not unmask or restore either daemon. The uninstall script also stops/removes Honor Control but never unmaskes these units.

This can disable the host's standard power manager even when `powerprofilesctl` is unavailable, when MSR access is unavailable, or when the Honor service later fails. It persists across reboots and remains after uninstall. The platform guard avoids touching non-Honor machines, but it does not make the action safe or reversible on supported machines.

Recommended fix: do not mask distribution-managed services as an implicit runtime side effect. Prefer an explicit, documented ownership mode that is installed/configured transactionally, checks the power capability first, records the prior state, and restores it on disable, shutdown, uninstall, and failed startup. At minimum, use a dedicated systemd conflict/coordination design and surface failures rather than silently ignoring them.

Suggested tests: mock `systemctl` for unsupported, missing-capability, failed-stop, already-masked, and successful cases; assert no calls when power capability is unavailable; assert exact restoration of prior state on shutdown/uninstall and failed apply.

#### PP-004 — Performance profiles end in `powersave` despite requesting `performance`

- Severity: High
- Confidence: High
- Category: Functional correctness / API contract
- Status: Newly introduced by the overhaul
- Affected code: `honor_control/backend/hardware.py:910-959`; `honor_control/core/models.py:297-304`; `honor_control/backend/application.py:348-380`.

The delayed EPP implementation deliberately leaves every CPU at `powersave` when the requested governor is `performance`, because the author observed that restoring `performance` resets EPP. The built-in Performance profile explicitly declares `governor="performance"` and `epp="performance"`, and the application reports full success after the delayed task is scheduled. The final hardware state therefore does not match the profile definition or the user-visible editor.

This may still produce good throughput on some Intel systems, but it is a silent semantic change: a user selecting Performance cannot obtain the requested governor, and the snapshot's observed summary can disagree with the applied profile. It also makes future profiles with `performance` governor impossible to reason about.

Recommended fix: determine and document a supported ordering/driver-specific combination, or represent this as a distinct profile capability/constraint. If both settings cannot coexist on a given driver, reject that definition or use a profile definition that declares the actual governor. Always verify and report the final state.

Suggested tests: mock cpufreq files and assert final governor/EPP for both governors; test a driver that rejects EPP under `performance`; ensure the operation becomes partial or uses an explicit normalized definition rather than returning full success.

#### PP-005 — Startup reconciliation treats the PPD label as proof of complete application

- Severity: High
- Confidence: High
- Category: Recovery / state synchronization
- Status: Newly introduced by the overhaul
- Affected code: `honor_control/backend/application.py:1013-1045`; `honor_control/backend/hardware.py:778-802`.

`read_power()` maps only `powerprofilesctl get` to `silent`, `balanced`, or `performance`. `_reconcile_power_profile()` skips reapplication whenever that label equals the persisted desired profile. It does not compare RAPL values, governors, EPP, turbo, or max-performance settings. The initial refresh also happens before daemon masking.

For example, after a restart PPD can report `performance` while its prior activity has overwritten RAPL or EPP. The service then masks PPD and skips reconciliation because the label already matches, leaving the direct limits wrong even though the persisted profile and snapshot say Performance. This defeats the stated purpose of startup reconciliation.

Recommended fix: reconcile against all required fields, not the PPD label, or always perform one complete verified apply after taking ownership of the competing writers. Keep the observed PPD label and the complete hardware verification as separate fields.

Suggested tests: construct a snapshot with PPD `performance` but incorrect RAPL/EPP/governor and assert startup re-applies; test failures after daemon stopping and ensure degraded state is visible.

### Medium

#### PP-006 — Multiple delayed rewrite tasks are not generation-safe or fully cancelled

- Severity: Medium
- Confidence: Medium
- Category: Concurrency / lifecycle
- Status: Newly introduced by the overhaul
- Affected code: `honor_control/backend/application.py:126`, `371-373`, and `181-186`.

Each successful apply schedules a new delayed task. The service stores only the newest task reference and cancels only that task during shutdown. Earlier tasks remain scheduled. They can perform stale RAPL/EPP writes after a later profile has been selected, or race with shutdown while the queue is being closed. The queue often converts the latter into a logged failure, but the lifecycle does not guarantee that no stale hardware mutation is still in flight.

Recommended fix: use one owned task with a generation counter or cancel/await the prior task before scheduling a replacement. Tie the task to the current desired profile and make shutdown await cancellation before closing the queue. Do not let an older profile rewrite hardware after a newer apply.

Suggested tests: apply two profiles in quick succession with controlled sleeps; assert only the latest rewrite reaches hardware. Cancel during sleep and during each queue operation; assert no post-shutdown write.

#### PP-007 — Direct MSR I/O has weak short-read/short-write and descriptor handling

- Severity: Medium
- Confidence: High
- Category: Resource management / hardware I/O robustness
- Status: Newly introduced by the overhaul
- Affected code: `honor_control/backend/hardware.py:988-1025`.

The method opens the MSR device repeatedly and closes descriptors only on the normal path. A short read can cause `struct.unpack()` to raise `struct.error`, which is not covered by the `except OSError`; a failure before `os.close()` leaks the descriptor. `os.write()` is not checked for a full eight-byte write. The delayed caller then logs the exception or ignores a false boolean, so the failure is not represented in service state.

Recommended fix: use context managers, validate exact read/write lengths, catch malformed-device data explicitly, and perform a readback/decode verification. Return a structured result that distinguishes unavailable, short I/O, and verification failure.

Suggested tests: mock short reads, short writes, `struct.error`, and close failures; assert descriptors are closed and the operation is reported as partial/unavailable.

### Low

#### PP-008 — Compatibility documentation contradicts the actual platform gate

- Severity: Low
- Confidence: High
- Category: Documentation / maintainability
- Status: Newly introduced by the overhaul
- Affected code: `README.md:10-16`; `honor_control/backend/hardware.py:597-619` and `868-896`.

The README says AMD systems will have “sysfs-only EPP” behavior. The adapter's positive allowlist requires the Honor MRA product and one of the listed Intel CPU markers; an AMD machine cannot reach the writable power capability or the EPP rewrite path. The actual behavior is unsupported/no power-profile writes, not partial sysfs-only EPP.

Recommended fix: document the actual fail-closed behavior, and state that the current allowlist is an Intel MRA-XXX allowlist rather than implying general Honor compatibility.

## 5. Test and validation assessment

Existing coverage is strongest around domain validation, config serialization/atomicity, fake hardware behavior, platform/resource discovery, D-Bus/client codecs, and the GUI's profile-editor dirty state. The hardware discovery tests correctly cover non-`BAT0` devices, unknown DMI identities, and threshold write ordering. The sibling `honor-tools` tests cover its normal power-profile dictionary behavior but do not cover the new adapter layer or direct MSR path.

The important gaps are:

- No test for RAPL MSR bit encoding, field preservation, exact I/O length, or readback.
- No test for direct adapter behavior with mocked `/dev/cpu/0/msr`, cpufreq sysfs, `systemctl`, or HWP sysfs.
- No test that daemon stop/mask is gated by actual power capability or restored on shutdown/uninstall.
- No application test for delayed rewrite success/failure, pending state, stale task ordering, or shutdown cancellation.
- No test for startup reconciliation when PPD's profile label matches but RAPL/EPP/governor do not.
- No test for the declared Performance governor versus the final delayed governor.
- Existing power mutation tests use `FakeHardware`, which reports every power sub-operation successful and records no real post-delay state. They can pass while the production adapter has a disabled PL2 field or an unavailable MSR.
- The GUI test covers editor values surviving refresh, but not active-profile selection across an external apply, an apply failure, or an auto-switch transition.

Validation result: lint, compilation, systemd unit verification, and the 23 hardware tests passed. The full application/backend/GUI test runs could not complete in this sandbox because the cross-thread queue callback could not wake the event loop; this must be rerun in a normal supported runtime before relying on the suite's result.

Prioritized additional tests:

1. Pure RAPL encoder/decoder tests, including the PL2 enable-bit regression.
2. Adapter integration tests with mocked sysfs/MSR/systemd and exact call/return assertions.
3. Complete application apply tests that await delayed enforcement and cover all partial failures.
4. Startup/restart/reconciliation tests with mismatched observed fields.
5. Task-generation and shutdown tests for repeated applies.
6. GUI active-combo tests for user selection, external state changes, failed apply, and auto-switch.
7. Run the complete suite on every supported Python/runtime combination, with a safe fake-hardware configuration and a separately marked hardware test gate.

## 6. Architecture and maintainability assessment

The high-level separation is good. `HardwarePort` keeps frontends away from hardware, the command queue centralizes blocking I/O, `ConfigStore` is atomic and validated, and snapshots distinguish desired values from observations. The platform allowlist and fail-closed behavior for unknown hardware are appropriate for EC/MSR operations. Moving daemon handling out of every profile apply reduces repeated global side effects.

The main architectural weakness is that power application is split between two authorities: the `honor-tools` profile writer and an adapter-local delayed workaround. The first returns untyped nested dictionaries; the second writes the same conceptual state through raw sysfs/MSR paths after the application has already committed desired/applied state. This makes ordering, verification, ownership, and failure semantics implicit.

A targeted refactor is justified, not a rewrite:

- Introduce a typed power-enforcement result with per-mechanism requested, written, verified, and final values. This would eliminate aggregate boolean inference and make partial failure actionable.
- Put the complete apply sequence, including the direct workaround and verification, behind one `PowerEnforcer` abstraction. `ApplicationService` should receive a transaction result rather than schedule raw hardware steps itself.
- Model power-daemon ownership as a lifecycle resource with prior-state capture and restoration. The benefit is containment of the most consequential system-wide side effect.
- Add a capability record for each required mechanism (PPD, cpufreq governor/EPP, RAPL sysfs, direct MSR, turbo/max-performance, HWP boost) instead of treating `powerprofilesctl` existence as sufficient.
- Keep the current typed profile registry and immutable snapshots; extend them with enforcement status rather than replacing them.

General codebase concerns not caused solely by this overhaul include the lack of a configured type checker and the amount of behavior represented by raw dictionaries at the `honor-tools` boundary. Those are maintainability concerns, but the hardware and lifecycle defects above are the release blockers.

## 7. Positive observations

- The overhaul correctly recognized that PPD can overwrite direct settings asynchronously and attempted to handle that race explicitly rather than assuming one successful command is durable.
- RAPL writes were moved from every apply to initialization, reducing repeated global daemon mutations. The CPU-0 choice is a reasonable optimization for the package-scoped register, subject to verification on supported hardware.
- Bounds validation and existing config validation constrain PL1/PL2 to a sane range before hardware access.
- The positive DMI/vendor/product/CPU allowlist prevents unknown hardware from reaching the new daemon, HWP, EPP, or MSR paths.
- The application keeps desired profile persistence separate from the auto-switch's transient applied profile.
- The GUI fix uses a dedicated dirty flag and blocks signals while rebuilding combo boxes, addressing the reported refresh snap-back without putting D-Bus or hardware I/O on the Qt thread.
- The repository documents that real hardware testing is a manual release gate, which is appropriate for this class of change.

## 8. Prioritized remediation plan

1. **Before merge/release:** fix PP-001's RAPL encoding; add encoder and mocked-I/O tests; verify both PL1 and PL2 by readback.
2. **Before merge/release:** remove implicit permanent daemon masking. Establish explicit ownership, capability gating, prior-state capture, restoration, and failure reporting. Update install/uninstall behavior and safety documentation.
3. **Before merge/release:** make delayed enforcement part of the operation's verified state transition, or expose a real pending/partial state. Do not persist/report `applied=True` while MSR/EPP enforcement is unknown.
4. **Before merge/release:** resolve the Performance governor/EPP contract and make startup reconciliation validate all mechanisms rather than only the PPD label.
5. **Soon afterward:** make delayed rewrites generation-safe and fully cancellable; harden MSR file I/O with context managers, exact-length checks, and structured errors.
6. **Soon afterward:** add the prioritized adapter/application/GUI tests and rerun the full suite outside the sandbox restriction in a normal supported environment.
7. **Optional cleanup:** correct AMD/allowlist documentation, add a type-checking configuration, and replace raw dependency dictionaries with typed adapter results.

Practical validation after fixes:

- Run lint, compile, type checks, and all unit tests.
- Run mocked adapter tests for every failure and partial-success branch.
- Run the service in session-bus/fake-hardware mode to validate D-Bus, persistence, snapshot, and GUI behavior.
- On the explicitly approved MRA-XXX Intel test machine, record pre-state, apply each built-in profile, read back RAPL PL1/PL2, governor, EPP, turbo, max-performance, and PPD state, then restore the original daemon and CPU state.
- Test restart, service failure, uninstall, and unsupported-platform behavior; confirm no daemon remains unintentionally masked and no stale delayed task writes after shutdown.

## 9. Final verdict

**Unsafe to merge or release.** The minimum changes required to reach “Requires significant fixes” are: correct and verify the PL2 MSR encoding, remove or make reversible the global daemon masking, and redesign the delayed enforcement/result path so persisted and reported applied state reflects verified hardware. The governor/EPP mismatch and startup reconciliation logic must also be corrected before a Performance profile can be considered contract-correct.
