# TERRA engineering evaluation — power-profile overhaul

Reviewed 2026-07-11.

## 1. Executive summary

**Verdict: Unsafe to merge or release.**

The overhaul addresses real issues: GUI selection snap-back, restart reconciliation, PPD interference, and Intel RAPL/EPP behavior. Its central integration is nevertheless contradictory. At service startup it stops and masks power-profiles-daemon (PPD), then the unchanged profile path invokes powerprofilesctl and requires that PPD operation to succeed. This makes ordinary profile application and reconciliation fail on a supported installed machine while permanently changing the system's normal power-manager state.

The new direct-MSR mechanism also cannot work in the packaged service as written. The unit drops CAP_SYS_RAWIO, which the standard Linux x86 MSR driver requires to open /dev/cpu/0/msr. That failure is silently discarded by the delayed task while UI and CLI can report a profile as applied. Delayed writes are unverified and race with subsequent profile selections.

No test changed in the overhaul range. The 221-test fake-hardware suite passes but cannot exercise PPD, systemd capabilities, MSR, EPP, or delayed-failure behavior. The system needs one coherent power-manager owner, deployment-aware capability checks, final-state verification, and focused tests before release.

## 2. Scope and methodology

### Revision and comparison base

| Item | Value |
|---|---|
| Branch / reviewed commit | main at 34d31f9c7efc195d7be5e9e39a75a3d4f938f33f |
| Default branch | origin/HEAD -> origin/main |
| Working tree at review start | clean; main...origin/main |
| Literal merge base | 34d31f9 (HEAD) |
| Functional comparison base | 4d8994a (initial commit) |
| Review range | 4d8994a..34d31f9 |

The literal merge base is not useful because the checked-out branch is itself the default branch. I used the parent of the first clearly identified overhaul commit as the defensible functional baseline.

Relevant commits:

1. 15f4d66 — added direct RAPL MSR/EPP rewrite, daemon stopping, startup reconciliation, and GUI selection changes.
2. d391bb0 — moved daemon masking to startup, added MSR bounds, and revised delayed-task handling.
3. 7213294 — restricted daemon stopping to detected Honor hardware.
4. 34d31f9 — Intel-only compatibility documentation.

The range changes README.md, honor_control/backend/application.py, honor_control/backend/hardware.py, and honor_control/frontend/gui/pages/power.py. No test file changed in this range.

### Inspection scope

I traced the changed runtime paths through ApplicationService lifecycle, config persistence, snapshots, automatic switching, HardwarePort and adapter implementations, platform/capability checks, command queue, supervisor, D-Bus API/authorization, client/CLI, GUI, systemd package, installer/uninstaller, and user documentation.

I also inspected the installed declared dependency, honor-tools 0.1.0, especially honor/power.py apply_profile() and _set_ppd(), and the upstream Linux x86 MSR driver source for its device-open capability requirement.

### Commands and validation

| Command / check | Result |
|---|---|
| Git status, branch/remote/default-branch/merge-base/log/show/full diffs | Established clean main, history, base, range, and affected subsystems. |
| Git diff --check across the range and current tree | Passed; no whitespace errors. |
| .venv/bin/python -m pytest --collect-only -q | 221 tests collected. |
| .venv/bin/python -m pytest -q | 221 passed in 8.65s outside the filesystem sandbox. |
| .venv/bin/ruff check honor_control tests | Passed. |
| .venv/bin/python -m compileall -q honor_control tests | Passed. |
| systemd-analyze verify packaging/systemd/honor-control.service | Passed outside the sandbox. |
| .venv/bin/python -m pip check | Environment failure: globally installed glances 4.5.5 lacks pyinstrument; unrelated to declared project dependencies. |
| Wheel-build attempts | Inconclusive: this venv lacks the build command entry point and pip wheel encountered a sandbox-owned generated build directory. No source issue was attributed to it. |

The first sandboxed pytest run stalled while a worker thread posted to its event loop. The same suite passed outside that sandbox; this is an execution-environment limitation, not a product test failure.

### Limitations and assumptions

No real hardware, MSR, sysfs, PPD, intel_lpmd, or system configuration was touched. Findings about these interfaces are based on call paths, package configuration, installed dependency source, kernel source, and test output. The CAP_SYS_RAWIO finding assumes the standard upstream Linux x86 msr driver; a downstream kernel might differ, but that is not a safe release assumption.

## 3. Architecture and behavior overview

The root D-Bus service composes ApplicationService, HonorToolsAdapter, ConfigStore, SnapshotStore, HardwareCommandQueue, and RuntimeSupervisor. GUI, CLI, and tray access the service via D-Bus; no new frontend hardware path was introduced. SetProfile is active-user authorized; profile definitions and auto-switch policy are administrator authorized.

ConfigStore owns desired system-wide state in /var/lib/honor-control/state.toml. PowerState contains the selected profile, profile registry, and auto-switch policy. A profile contains PL1/PL2, governor, EPP, PPD mode, turbo, and maximum-performance values. SnapshotStore publishes observed state; HardwareCommandQueue serializes blocking I/O; the application mutation lock serializes whole mutations.

Profile application currently works as follows:

1. GUI or CLI calls SetProfile. The new GUI dirty flag preserves an in-progress active-combo selection across the five-second snapshot refresh.
2. ApplicationService validates the name against persisted definitions and queries get_power_capability().
3. Production capability requires importable honor-tools, a positive MRA-XXX/Intel match, and the presence of powerprofilesctl. It does not verify PPD availability, EPP/RAPL resources, the MSR device, kernel lockdown, or service capability.
4. HonorToolsAdapter builds a dependency PowerProfile and calls honor-tools apply_profile(). Its returned map is reduced to governor_ok, epp_ok, ppd_ok, rapl_ok, and misc_ok.
5. If all initial checks pass, the application records an applied name, persists desired state for manual selection, refreshes the snapshot, and schedules a fire-and-forget task for 0.5 seconds later.
6. The delayed task writes RAPL MSR 0x610 and rewrites every CPU EPP value. It first sets governors to powersave; when the requested governor is performance it deliberately leaves powersave.

At startup, initialize() loads/publishes state, calls stop_competing_power_daemons(), then reconciles the persisted profile. On a detected target, that stops and masks PPD and intel_lpmd and best-effort enables HWP dynamic boost. It does not capture prior state. The uninstaller does not restore it.

The delayed path is outside the caller-visible result. Its false returns are ignored, no final read-back occurs, and later refreshes prefer _last_applied_power_profile over a newly observed PPD profile. Auto-switch shares the same apply path and can execute its root hook after the initial, not final, application is considered successful.

## 4. Findings

### Critical

#### PP-001 — Startup masks the daemon every profile application still requires

- **Severity:** Critical
- **Confidence:** High
- **Category:** Functional correctness; lifecycle; system-state ownership
- **Status:** Newly introduced by the overhaul
- **Affected paths:** honor_control/backend/application.py:155-165; honor_control/backend/hardware.py:844-896; .venv/lib/python3.14/site-packages/honor/power.py:175-194; scripts/uninstall-local.sh:19-49.

Initialize() stops and masks power-profiles-daemon before reconciliation. The inspected honor-tools 0.1.0 dependency still executes powerprofilesctl set through _set_ppd(); a nonzero return becomes ppd_ok=False. ApplicationService requires ppd_ok for success. A stopped/masked PPD cannot serve the D-Bus request made by powerprofilesctl, so startup reconciliation and normal SetProfile calls become partial rather than successful.

This is a direct contract contradiction. It also alters global service state and HWP dynamic boost on every startup, silently ignores operation failures, captures no former state, and leaves PPD/intel_lpmd masked after stop, uninstall, or failed service start. The platform guard only narrows the affected machines.

**Failure scenario / impact:** On a supported MRA-XXX, starting or upgrading the service masks PPD. Reconciliation asks powerprofilesctl to apply Performance, receives ppd_ok=False, and cannot declare it applied. The distribution power manager remains disabled until the user manually recovers it.

**Recommended fix:** Choose one owner: keep and coordinate through PPD, or remove PPD application from the profile contract and use a separately validated direct backend. Do not mask unrelated system services from normal startup. If an explicit admin transition remains, capture unit/mask/HWP state, return structured results, restore state on every rollback/uninstall path, and document it.

**Suggested tests:**

- Fake system-manager tests proving startup never disables a daemon required by the chosen profile backend.
- PPD-present and PPD-absent integration tests with accurate capability/result semantics.
- Upgrade, failed-start, shutdown, and uninstall tests that restore every changed global state.

### High

#### PP-002 — The packaged service lacks the capability required by the new MSR path

- **Severity:** High
- **Confidence:** High
- **Category:** Deployment / privilege boundary; functional correctness
- **Status:** Newly introduced, interacting with a pre-existing hardened unit
- **Affected paths:** honor_control/backend/hardware.py:961-1036; honor_control/backend/application.py:367-421; packaging/systemd/honor-control.service:25.

The new code opens /dev/cpu/0/msr. The unit CapabilityBoundingSet includes only CAP_DAC_OVERRIDE and CAP_DAC_READ_SEARCH, not CAP_SYS_RAWIO. The standard Linux x86 msr driver's msr_open() requires CAP_SYS_RAWIO before it opens an MSR device. A systemd capability bounding set permanently drops omitted capabilities, including for UID 0.

write_rapl_msr() catches the resulting OSError and returns False, but the delayed caller discards that result. get_power_capability() checks only for a powerprofilesctl executable, not MSR availability, kernel lockdown, or effective service privilege.

**Failure scenario / impact:** Even after PP-001 is fixed, the installed service can return success for Performance. The decisive direct RAPL write fails with permission denied half a second later, so the sustained-power goal is not achieved and no user-visible error is returned.

**Recommended fix:** Make raw-MSR support a separately probed optional mechanism. Check device availability, kernel lockdown, and effective service capability; read back target MSRs after write. Either add the narrowly justified capability after security review or do not use raw MSR in the standard service. Capability and result details must represent this mechanism directly.

**Suggested tests:** MSR open/read/write failure tests that return unavailable or partial, never success; unit-file/capability integration tests; and an opt-in privileged integration test with read-back.

#### PP-003 — Final RAPL/EPP outcome is neither verified nor represented in public state

- **Severity:** High
- **Confidence:** High
- **Category:** State synchronization; error handling; API correctness
- **Status:** Newly introduced
- **Affected paths:** honor_control/backend/application.py:348-380, 391-421, 1102-1144; honor_control/backend/hardware.py:898-1036.

The method returns success, persists desired state, and sets _last_applied_power_profile before the overhaul's delayed RAPL/EPP work runs. The delayed task ignores both boolean returns and performs no read-back. Refresh favors the logical name over fresh PPD observation.

A profile name consequently proves only the earlier dependency call, not that the delayed hardware enforcement completed or remained in effect.

**Failure scenario / impact:** Missing EPP files, EBUSY, MSR permission denial, or a later competing write leaves UI/CLI saying Performance is applied while low-level limits/EPP are ineffective. Automatic hooks may run after only this optimistic condition.

**Recommended fix:** Make final application stateful: aggregate mechanisms, settle, read governor/EPP/RAPL/manager state, and publish success only when required mechanisms verify. If asynchronous completion is necessary, expose pending then success/partial/failure. Do not let a logical name hide new observation.

**Suggested tests:** Table-driven false/exception/read-back-mismatch tests for both delayed operations, assertions for result/snapshot/health, and a hook test proving it runs only after final verification.

### Medium

#### PP-004 — Rapid profile changes can apply an obsolete delayed rewrite

- **Severity:** Medium
- **Confidence:** High
- **Category:** Concurrency / ordering
- **Status:** Newly introduced
- **Affected paths:** honor_control/backend/application.py:126, 183-185, 367-373, 391-421.

Each success schedules a delayed task. Reassigning _pending_power_task overwrites the old reference without cancelling the old task. The task does not hold the application mutation lock. The queue serializes calls but cannot establish that an older profile is still current. Shutdown cancels only the latest stored task.

**Failure scenario / impact:** Selecting Performance then Silent within 0.5 seconds schedules both rewrites. The older task can write Performance MSR/EPP after Silent's initial application. If the later task fails, stale settings remain while public state says Silent.

**Recommended fix:** Own one generation-tagged latest-wins task. Cancel and await the predecessor, or reacquire the mutation lock and verify generation/profile before every write/state update. Invalidate or await all outstanding tasks at shutdown.

**Suggested tests:** Use a controllable clock/fake queue for two selections within the delay, auto-switch, and shutdown; only the newest profile may write.

#### PP-005 — A configured performance governor is silently changed to powersave

- **Severity:** Medium
- **Confidence:** High
- **Category:** Configuration contract; state reporting
- **Status:** Newly introduced by delayed EPP rewrite
- **Affected paths:** honor_control/backend/hardware.py:898-959; honor_control/backend/application.py:328-336, 348-380; honor_control/core/models.py:257-305; honor_control/frontend/gui/pages/power.py:76-103.

The profile/UI promise a governor choice. honor-tools initially sets the requested governor, but the delayed rewrite first sets powersave and intentionally leaves it there for a performance governor. This may be a reasonable EPP workaround, but it is a silent semantic substitution: governor_ok was computed before it and no final read-back occurs.

**Failure scenario / impact:** A profile displayed and saved as governor=performance effectively runs powersave. Configuration, success result, and actual low-level state disagree.

**Recommended fix:** Reject or normalize incompatible governor/EPP combinations before applying, or model requested versus effective governor. Expose final effective values and do not report full application when a requested critical setting was substituted.

**Suggested tests:** Cover all governor/EPP combinations and assert final read-back plus UI-visible effective values.

#### PP-006 — Turbo and max-performance controls persist but are not applied

- **Severity:** Medium
- **Confidence:** High
- **Category:** Functional correctness; dependency contract
- **Status:** Pre-existing issue exposed/worsened by the overhaul
- **Affected paths:** honor_control/backend/config_store.py:72-100, 526-572; honor_control/backend/application.py:328-336; honor_control/frontend/gui/pages/power.py:90-103, 377-391; .venv/lib/python3.14/site-packages/honor/power.py:177-195.

The service persists/displays turbo_enabled and max_perf_pct and passes them to the dependency. Installed honor-tools 0.1.0 ignores both in apply_profile(): it unconditionally writes no_turbo=0 and max_perf_pct=100. misc_ok reports only those fixed writes, not whether saved values were honored.

This predates the review range, but it undermines the overhaul's presentation of complete, precise profile definitions.

**Failure scenario / impact:** A user saves turbo off and 60% maximum performance; the registry retains those values, but apply enables turbo and sets 100%.

**Recommended fix:** Update the dependency or apply/verify these values in the adapter. Until then disable/remove the controls and report them unavailable.

**Suggested tests:** Assert every stored profile field reaches the adapter and observed no_turbo/max_perf_pct match the definition; add dependency-version compatibility tests.

### Low

#### PP-007 — The new AMD compatibility statement conflicts with implementation

- **Severity:** Low
- **Confidence:** High
- **Category:** Documentation accuracy
- **Status:** Newly introduced
- **Affected paths:** README.md:12-15; honor_control/backend/hardware.py:43-50, 505-544, 597-619.

README says an AMD-based Honor will fail safely with sysfs-only EPP. get_power_capability() requires the exact MRA-XXX Intel allowlist and returns unsupported before any apply on any other CPU/model. No AMD/sysfs-only fallback exists.

**Failure scenario / impact:** A reader expects partial AMD behavior; the service disables power profiles entirely.

**Recommended fix:** Document non-allowlisted hardware as unsupported with no profile application, or implement/test the claimed fallback.

**Suggested tests:** Platform-capability test for a non-Intel Honor identity plus a documentation/capability matrix review.

## 5. Test and validation assessment

The 221 tests have useful breadth for pre-existing architecture: validation, snapshots, config atomicity, queue timeout semantics, supervisor lifecycle, D-Bus/polkit mapping, codecs, CLI parsing, GUI construction, fake hardware, battery discovery, and application happy paths.

Power coverage checks name rejection, fake success, custom-profile persistence, auto-switch persistence, and basic GUI behavior. The existing profile-editor dirty test is useful, but the changed active-combo dirty path is not directly tested.

Because FakeHardware returns unconditional success for rewrite_epp(), write_rapl_msr(), and stop_competing_power_daemons(), and no test changed in the range, current tests do not exercise PPD/systemctl ownership or rollback; PPD absent; direct MSR absence/CAP_SYS_RAWIO denial/lockdown/read-back; EPP failure/read-back; delayed false returns; rapid profile/auto-switch/shutdown races; deployed unit restrictions; or turbo/max-performance round trip.

The current profile-success test only observes the initial fake apply. Its asyncio runner ends before the 0.5-second task is validated, so it cannot prove overhaul behavior.

Priority additions:

1. Mechanism contract tests for success, false, exception, and read-back mismatch.
2. Fake system-manager/PPD ownership and restoration tests.
3. Unit-file-aware direct-MSR capability tests.
4. Deterministic latest-wins, auto-switch, cancellation, and shutdown tests.
5. Governor/EPP compatibility-matrix tests.
6. Turbo/max-performance dependency round-trip tests.

## 6. Architecture and maintainability assessment

The high-level service design remains promising: one root hardware owner, serialized mutations, atomic desired state, and D-Bus-only frontends. The overhaul bypasses those strengths by adding a second power path with global side effects and boolean-only outcomes.

The core defect is split ownership. The adapter delegates to PPD, writes sysfs/MSR directly, and disables PPD. It does not establish which layer is authoritative, which mechanisms are optional, or how observed values map to a profile name. Broad capability checks, weak recovery, and false success follow from this.

A targeted refactor is justified, not a rewrite:

1. Add a PowerApplyPlan and PowerApplyResult at the existing hardware boundary. Select one ownership strategy, enumerate required/optional mechanisms, aggregate results, and expose verified state. **Benefit:** one truthful result for D-Bus, snapshot, hooks, and diagnostics.
2. Split requested, effective, and observed power state. **Benefit:** pending/partial/substituted policy is visible and stale logical names cannot hide hardware state.
3. Make direct MSR an injected separately probeable backend with fake sysfs/device/system-manager dependencies. **Benefit:** safe testability and a narrow auditable privilege boundary.
4. Give delayed enforcement a dedicated generation/latest-wins controller. **Benefit:** stale writes are eliminated without rewriting the queue/application architecture.

## 7. Positive observations

- The 7213294 positive platform guard is an improvement: new daemon operations are kept off unrecognized hardware.
- Direct RAPL values have a 3–150 W bound and the package register is correctly treated as CPU-0 scoped.
- The GUI fix is focused and preserves user selection without duplicating profile lists.
- Startup reconciliation correctly recognizes that persisted desired state is not proof of hardware state; retain this goal after fixing ordering and verification.
- The initial honor-tools result is already aggregated instead of blindly assumed successful. The delayed path needs the same rigor.
- No direct frontend hardware access was introduced.

## 8. Prioritized remediation plan

### Must fix before merge or release

1. Fix PP-001 by selecting one PPD/direct-control ownership model, eliminating automatic self-disabling, and restoring every explicit global change.
2. Fix PP-002 by providing a security-reviewed, preflighted verified MSR capability or removing the raw-MSR claim/path from the standard service.
3. Fix PP-003 and PP-005 by publishing only verified final RAPL/EPP/governor state and modelling requested/effective values.
4. Fix PP-004 with latest-wins delayed work and complete shutdown cancellation.
5. Add PPD, MSR, delayed-failure, concurrency, and deployed-unit tests.

### Should fix soon afterward

1. Fix PP-006 by honoring or removing turbo/max-performance controls.
2. Correct PP-007 and document manager ownership, prerequisites, effective values, and recovery.
3. Return per-mechanism capability reasons rather than treating powerprofilesctl presence as complete support.

### Optional cleanup and longer-term improvement

1. Extract the focused apply-plan/result abstraction.
2. Inject MSR/sysfs/system-manager operations for fake-filesystem testing.
3. Add diagnostics for applied-versus-observed mismatch and the last failed mechanism.

### Practical validation after fixes

1. On a clean tree run the full suite, Ruff, compilation, diff checks, and systemd unit validation.
2. In a disposable VM exercise PPD-present, PPD-absent, MSR-unavailable, and permission-denied configurations; assert D-Bus result/snapshot after the settle window.
3. On verified hardware only, record baseline, apply and rapidly switch profiles, restart the service, read governor/EPP/RAPL, and run documented rollback.
4. Confirm service failure and uninstall restore every changed power-manager and HWP state.

## 9. Final verdict

**Unsafe to merge or release.**

To advance to **Requires significant fixes**, resolve the PPD self-disable contradiction and ensure the packaged service either has a safe verified MSR path or does not claim one. To advance to **Ready with minor fixes**, final RAPL/EPP/governor state must be accurate, stale tasks must be prevented, and focused tests must cover the new behavior. Correct the pre-existing turbo/max-performance contract and README mismatch before presenting the profile editor as precise hardware control.

