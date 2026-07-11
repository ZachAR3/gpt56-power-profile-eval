# Independent Audit of the `_EVAL` Code-Review Reports

**Repository:** `honor-control`  
**Reviewed revision:** `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f` (`main`, identical to `origin/main`)  
**Functional comparison base:** `4d8994ab2eeb9595d1222ac4ad1789b8579a966f`  
**Review range:** `4d8994a..34d31f9`  
**Reports audited:** 5.5 High, 5.5 XHigh, GLM Max, LUNA High, LUNA Max, LUNA XHigh, SOL High, SOL Medium, and TERRA XHigh  
**Repository changes made by this audit:** this report only; no production code or tests were modified.

The repository root also contained `LUNA_EVAL.md`, `SOL_EVAL.md`, and `TERRA_EVAL.md`. They are byte-for-byte duplicates of the uploaded LUNA Max, SOL Medium, and TERRA XHigh reports, so they are not scored twice.

## Executive Summary

**Strongest report: SOL High.** It had the best combination of technical accuracy, deployment awareness, prioritization, and signal-to-noise. In addition to the core PPD-ownership contradiction and PL2 packing bug, it correctly identified the shipped systemd unit's missing `CAP_SYS_RAWIO`, the false-positive EPP success path, the weak reconciliation model, the sticky “applied” overlay, timeout-budget mismatch, and lifecycle damage from persistent masks. It did not discover the resolved `honor-tools` constructor incompatibility, but it made no comparably serious false deployment claim.

**Close second: LUNA Max.** It was the only report to prove that the dependency version actually resolved in the checkout (`honor-tools 0.1.0`) rejects `turbo_enabled` and `max_perf_pct`, causing the production adapter to fail before any hardware operation. It also covered transaction boundaries, auto-switch retry behavior, capability weakness, lifecycle, reconciliation, and test isolation. It missed the deterministic `CAP_SYS_RAWIO` packaging failure and slightly over-prioritized the final-governor substitution and some retry behavior.

**Weakest report: GLM Max.** It found several real defects, especially the MSR packing error, stale delayed tasks, missing rollback, descriptor handling, and absent direct tests. However, two of its major High-severity deployment findings are wrong: `ProtectSystem=strict` does not itself prevent `systemctl mask`, and a successfully masked PPD unit is not reactivated by D-Bus. It also missed the actual service-capability failure (`CAP_SYS_RAWIO`) and the dependency API break, split one concurrency issue into duplicates, and devoted disproportionate attention to cosmetic imports/comments. Its length and confidence therefore overstate its reliability.

### Independently confirmed release blockers

1. **The declared/resolved dependency contract is broken.** `HonorToolsAdapter` passes two constructor fields that `honor-tools 0.1.0` does not accept, and a safe direct probe returns an error before hardware apply.
2. **Power-manager ownership is internally contradictory.** Startup masks PPD, then every full profile apply requires `powerprofilesctl set`/`ppd_ok=True`. The same masks are persistent and never rolled back.
3. **The PL2 MSR field is encoded incorrectly.** PL2 enable and time-window fields are shifted beyond bit 63 and discarded.
4. **The standard packaged service cannot perform the new MSR write.** Its capability bounding set excludes `CAP_SYS_RAWIO`, which the upstream x86 MSR driver requires to open `/dev/cpu/N/msr`.
5. **The apply transaction reports success before convergence.** The delayed MSR/EPP phase is unsupervised, its Boolean failures are ignored, and public state can continue to report the logical profile despite hardware drift.

### Overall conclusion

The branch is **unsafe to release**. The reports broadly agree on that conclusion, but their reasons are not equally reliable. The correct remediation is not to stack more delayed writes on top of PPD. The project needs one explicit power-policy owner, a versioned dependency/backend contract, a capability-accurate deployment model, and a verified convergence state rather than a name-only “applied” marker.

## Scope, Method, and Evidence Standard

The audit independently inspected Git history, the full change range, all callers and state paths around power profiles, the production adapter, fake hardware, configuration and validation, D-Bus/client/GUI flow, command serialization, systemd and uninstall packaging, documentation, and the resolved `honor-tools` package embedded in the checkout.

Key independent checks:

- `git diff 4d8994a..HEAD` changes only `README.md`, `application.py`, `hardware.py`, and the power GUI page; **no tests changed**.
- A safe adapter probe using the declared/resolved dependency returned: `PowerProfile.__init__() got an unexpected keyword argument 'turbo_enabled'`.
- A pure arithmetic reproduction of the current MSR expression produced a value with PL1 enabled, PL2 disabled, TW1 preserved, and TW2 zero.
- 150 focused backend/application/hardware/config/model tests passed under the available Python 3.13 runtime. Full collection in this extraction was limited by unavailable `sdbus`/PySide dependencies, while several source reports recorded 221/221 passes outside their restricted sandbox.
- Upstream Linux x86 `arch/x86/kernel/msr.c::msr_open()` requires `CAP_SYS_RAWIO`; the shipped unit bounds capabilities to `CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH` only.
- Upstream systemd implementation shows `systemctl mask` is a manager D-Bus operation; PID 1 performs unit-file mutation. `ProtectSystem=strict` in the client unit therefore does not prove mask failure.

Classifications mean:

- **Confirmed:** the material claim follows from code, packaging, dependency behavior, or a deterministic reproduction.
- **Partially correct:** a real issue exists, but scope, severity, causal explanation, or likely impact is incomplete/overstated.
- **Incorrect:** the causal claim conflicts with code or platform semantics.
- **Unverifiable:** evidence is environment-specific or insufficient to call a repository defect.
- **Low-value / non-issue:** true or arguable observation with little actionable impact, or a duplicate of a stronger finding.

## Claim-by-Claim Verification

### 5.5 High

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | Startup masks PPD while profile application still requires `powerprofilesctl set`. | **Confirmed** | Startup invokes daemon masking before reconciliation (`application.py:155-165`); a full apply requires `ppd_ok` (`application.py:348-353`); the resolved dependency implements that flag through `powerprofilesctl set` (`.venv/.../honor/power.py:175-192, 197-229`). |
| PP-002 | The direct RAPL writer shifts PL2 enable/time-window bits out of the 64-bit register. | **Confirmed** | `hi` uses absolute bits 47/49 and is then shifted another 32 bits (`hardware.py:1004-1019`). The reproduced value had PL2 enable=false and TW2=0. |
| PP-003 | Stale delayed tasks can overwrite a newer profile. | **Partially correct** | Each success creates a new task and replaces the single reference without cancelling/versioning the old one (`application.py:367-373`); shutdown only cancels the newest reference (`181-186`). The race is real, but normally the newer delayed task runs later and repairs the stale write; lasting wrong state additionally requires failure/cancellation/timing. |
| PP-004 | Delayed rewrite failure is invisible to the operation result and snapshot. | **Confirmed** | Success is returned at `application.py:374-381`; the later calls ignore their Boolean returns and only log exceptions (`391-421`). No verification updates `PowerSnapshot`. |
| PP-005 | New direct hardware methods bypass `root_path` and are unsafe to isolate in tests. | **Confirmed** | The adapter has an injected root (`hardware.py:436-458`), but daemon/HWP, EPP, and MSR code use absolute host paths (`889-894`, `921-940`, `989-1024`). |
| PP-006 | The command queue is broken on the reviewed runtime. | **Unverifiable** | The report reproduced a restricted Python 3.14 event-loop failure, but other reports ran all 221 tests outside that sandbox and this audit ran 150 focused tests, including queue and application tests, successfully. The queue code is outside the overhaul diff. Treat as an environment limitation until reproduced on a supported production runtime. |
| PP-007 | Compatibility documentation overstates AMD behavior. | **Confirmed** | README says all MagicBooks are Intel and AMD gets “sysfs-only EPP” (`README.md:11-16`), while the positive platform gate returns unsupported before any power operation (`hardware.py:604-609, 778-783`). Official HONOR product pages list AMD MagicBooks. |

### 5.5 XHigh

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | Startup disables PPD before an apply path that requires PPD. | **Confirmed** | Same control-path evidence as 5.5 High PP-001: `application.py:155-165, 348-353`; dependency `_set_ppd()` at `.venv/.../honor/power.py:175-192`. |
| PP-002 | Startup persistently masks system daemons without rollback. | **Confirmed** | The code runs non-runtime `systemctl mask` for PPD and intel_lpmd (`hardware.py:874-885`) and records no prior state. Neither shutdown (`application.py:181-186`) nor uninstall (`scripts/uninstall-local.sh:19-49`) restores it. |
| PP-003 | PL2 MSR fields are packed incorrectly. | **Confirmed** | `hardware.py:1004-1019`; arithmetic reproduction confirms the fields are lost. |
| PP-004 | Delayed writes can fail after the API reports success. | **Confirmed** | `application.py:354-381, 391-421`. |
| PP-005 | Stale delayed tasks race newer profiles and are not all cancelled. | **Partially correct** | The missing cancellation/generation is confirmed (`application.py:367-373, 181-186`), but the report overstates how often a stale value remains final because the later generation commonly runs last. |
| PP-006 | Power capability does not probe the resources introduced by the overhaul. | **Confirmed** | `get_power_capability()` checks only dependency import, platform allowlist, and the executable (`hardware.py:597-619`), not PPD availability, sysfs nodes, MSR device, permissions/capabilities, lockdown, or rollback prerequisites. |
| PP-007 | The command queue is a product defect on Python 3.14. | **Unverifiable** | Observed only in restricted execution environments; the same queue tests pass in this audit and full-suite passes were reported outside the sandbox. It is worth compatibility testing, but not established as a repository defect. |
| PP-008 | `stop_competing_power_daemons()` can exceed the outer queue deadline. | **Confirmed** | Four sequential subprocesses each have a 5-second timeout (`hardware.py:874-883`), while the queue default is 10 seconds (`command_queue.py:26, 68-74`). Worst case exceeds the outer budget and can poison startup. |
| PP-009 | Applied-profile observation depends on PPD even after PPD is disabled. | **Confirmed** | `read_power()` derives the profile name solely from the PPD label (`hardware.py:787-800`); startup reconciliation compares only that name (`application.py:1023-1031`). |
| PP-010 | Direct methods bypass the injectable root. | **Confirmed** | Absolute paths at `hardware.py:889-894, 921-940, 989-1024`. |
| PP-011 | The overhaul paths have almost no direct tests. | **Confirmed** | No test references `write_rapl_msr`, `rewrite_epp`, `stop_competing_power_daemons`, `_delayed_power_rewrite`, or `_reconcile_power_profile`; no tests changed in `4d8994a..HEAD`. |
| PP-012 | MSR I/O can leak descriptors and mishandles malformed/short I/O. | **Confirmed** | Descriptors are manually closed only on the happy path; `struct.unpack` errors and short I/O escape the `except OSError` block (`hardware.py:988-1035`), and write length is not checked. |

### GLM Max

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | PL2 enable/time-window bits are truncated. | **Confirmed** | `hardware.py:1004-1019`; reproduced independently. |
| PP-002 | A stale delayed task is not cancelled before a new one is scheduled. | **Partially correct** | The task ownership defect is real (`application.py:367-373`), but the claimed final-state impact is conditional and the report later duplicates this as PP-010. |
| PP-003 | `systemctl mask` fails because `ProtectSystem=strict` makes `/etc/systemd/system` read-only. | **Incorrect** | `systemctl mask` normally invokes systemd manager D-Bus methods and PID 1 performs the unit-file change; the client service does not need direct write access to `/etc/systemd/system`. Weakening `ProtectSystem` or adding `ReadWritePaths` is therefore not justified by this claim. |
| PP-004 | PPD is reactivated by D-Bus activation after it has been masked. | **Incorrect** | A successfully masked unit is not activatable. The real contradiction is the opposite: `powerprofilesctl set` fails because the service remains masked. Reactivation is possible only if masking failed, which the code never checks. |
| PP-005 | `ProtectKernelModules=true` makes the MSR path fail. | **Partially correct** | The unit cannot load modules, but the application never attempts to load `msr`; if the module/device already exists this setting is not the blocker. The deterministic blocker the report missed is the absent `CAP_SYS_RAWIO` (`honor-control.service:23-26`; Linux `msr_open()` requires it). |
| PP-006 | All new methods have zero test coverage. | **Partially correct** | There is no meaningful direct production-adapter coverage, which is important. “Zero” is too absolute because initialization/fake methods and surrounding application flows are indirectly exercised. |
| PP-007 | `time.sleep` in the hardware worker is itself an architecture bug. | **Low-value / non-issue** | The queue is explicitly a blocking-I/O worker (`command_queue.py:1-6`). The actionable concern is timeout budgeting and per-CPU retry duration, not that synchronous code sleeps in the synchronous worker. |
| PP-008 | Masked daemons are not restored on shutdown or uninstall. | **Confirmed** | `hardware.py:874-885`; `application.py:181-186`; `scripts/uninstall-local.sh:19-49`. |
| PP-009 | New methods bypass `root_path`. | **Confirmed** | Absolute host paths in `hardware.py:889-894, 921-940, 989-1024`. |
| PP-010 | The delayed rewrite does not take the mutation lock. | **Low-value / duplicative** | The observation is true, but it is the same ordering defect as PP-002. Merely taking the lock after the delay does not solve stale intent unless the task also carries a generation check. |
| PP-011 | Delayed failure is not communicated. | **Confirmed** | `application.py:374-381, 391-421`. |
| PP-012 | MSR descriptors can leak on exceptional paths. | **Confirmed** | `hardware.py:988-1035`. |
| PP-013 | A `# -- Fan --` comment is misplaced. | **Low-value / non-issue** | Cosmetic organization issue with no material effect on correctness, safety, or maintainability of the reviewed subsystem. |
| PP-014 | Local `pathlib` imports are redundant. | **Low-value / non-issue** | Style-only and not a meaningful review finding. |
| PP-015 | Sysfs helpers are inconsistent. | **Low-value / non-issue** | There is some duplication, but the report does not establish a correctness consequence. The higher-value issue is bypassing the injected I/O boundary and not validating readback. |
| PP-016 | Documentation and changelog were not updated. | **Partially correct** | The README was changed in the overhaul, so the broad statement is false. Architecture/safety docs do omit the new daemon/MSR lifecycle and contain inaccurate capability claims, so documentation drift is still real. |

### LUNA High

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | PL2 is disabled by incorrect MSR construction. | **Confirmed** | `hardware.py:1004-1019`; reproduced. |
| PP-002 | The operation is marked applied before delayed enforcement and loses its failures. | **Confirmed** | `application.py:354-381, 391-421`. |
| PP-003 | Startup permanently masks system power managers without reversible ownership. | **Confirmed** | `hardware.py:874-885`; no state capture or restore in shutdown/uninstall. |
| PP-004 | Performance profiles end with the `powersave` governor. | **Partially correct** | The final governor substitution is explicit (`hardware.py:910-915, 949-958`) and contradicts the profile definition (`models.py:296-305`). The report overstates it as unambiguously wrong: the code documents an Intel EPP constraint, so the defect is inaccurate modeling/verification unless hardware evidence shows a viable `performance`+EPP combination. |
| PP-005 | Reconciliation treats the PPD label as proof of a complete apply. | **Confirmed** | `hardware.py:787-800`; `application.py:1023-1031`. |
| PP-006 | Delayed tasks are not generation-safe or fully cancelled. | **Partially correct** | Confirmed ordering/lifecycle weakness, but persistence of the wrong final profile is conditional; cancellation alone also cannot stop a blocking worker call already in progress. |
| PP-007 | Raw MSR I/O lacks short-I/O and descriptor safety. | **Confirmed** | `hardware.py:988-1035`. |
| PP-008 | Compatibility docs contradict the platform gate. | **Confirmed** | `README.md:11-16`; `hardware.py:604-609, 778-783`. |

### LUNA Max

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | The resolved `honor-tools` API makes real profile application fail. | **Confirmed** | The adapter passes `turbo_enabled` and `max_perf_pct` (`hardware.py:816-824`), while the installed/allowed `honor-tools 0.1.0` `PowerProfile` has only five fields (`.venv/.../honor/config.py:25-34`). A direct safe probe returned `unexpected keyword argument turbo_enabled`. The report correctly limits confidence for other possible 0.1.x versions. |
| PP-002 | Startup masks PPD/intel_lpmd and never restores them. | **Confirmed** | `application.py:155-165`; `hardware.py:874-885`; shutdown/uninstall omit restoration. |
| PP-003 | The RAPL encoder drops PL2 enable/time-window. | **Confirmed** | `hardware.py:1004-1019`. |
| PP-004 | Success precedes delayed enforcement and failures are lost. | **Confirmed** | `application.py:354-381, 391-421`. |
| PP-005 | Performance ends at `powersave` instead of the requested governor. | **Partially correct** | The mismatch is real, but whether it is a hardware bug or a required Intel P-state strategy is not established. It should be modeled as effective state or an unsupported combination, not automatically “fixed” by restoring performance. |
| PP-006 | Startup reconciliation trusts a PPD label rather than hardware state. | **Confirmed** | `hardware.py:787-800`; `application.py:1023-1031`. |
| PP-007 | Daemon cleanup can exceed the queue deadline and abort startup. | **Confirmed** | Up to four 5-second subprocess waits under a 10-second outer queue deadline (`hardware.py:874-883`; `command_queue.py:26`). |
| PP-008 | Fire-and-forget rewrites are not generation-safe or fully owned. | **Partially correct** | The ownership problem is confirmed; final stale state is conditional, and cancel/await alone is insufficient once a blocking queue operation has started. |
| PP-009 | Capability probing is weaker than the mechanisms changed. | **Confirmed** | `hardware.py:597-619` omits all new direct-resource and privilege checks. |
| PP-010 | Failed auto-switch applies retry every two seconds indefinitely. | **Partially correct** | On failure `last_ac/last_policy` remain unchanged (`application.py:1327-1377`), so retries continue while the condition persists. Retrying may be intentional, but no backoff/health suppression creates log and hardware churn. |
| PP-011 | Hardware success plus persistence failure can leave contradictory state. | **Confirmed** | `_last_applied_power_profile` is set before `ConfigStore.update()` (`application.py:354-365`); an exception can leave hardware and in-memory state changed without a structured result. This is a real transaction-boundary flaw. |
| PP-012 | High-risk production adapter paths lack meaningful tests. | **Confirmed** | No direct tests for daemon control, MSR packing/I/O, EPP convergence, delayed failures, or dependency API compatibility. |
| PP-013 | New power I/O bypasses the injectable root. | **Confirmed** | `hardware.py:889-894, 921-940, 989-1024`. |
| PP-014 | AMD compatibility wording does not match actual behavior. | **Confirmed** | `README.md:11-16`; positive platform gate disables the domain entirely. |

### LUNA XHigh

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | The overhaul disables PPD while the apply contract still requires it. | **Confirmed** | `application.py:155-165, 348-353`; dependency `_set_ppd()`. |
| PP-002 | System-wide masks persist after shutdown/failure/uninstall. | **Confirmed** | `hardware.py:874-885`; no rollback path. |
| PP-003 | PL2 fields are shifted out of the register. | **Confirmed** | `hardware.py:1004-1019`. |
| PP-004 | Delayed EPP handling leaves the performance profile in powersave. | **Partially correct** | Behavior and state mismatch confirmed; technical necessity and severity are not proved. |
| PP-005 | Delayed hardware failures are ignored after success/persistence. | **Confirmed** | `application.py:354-381, 391-421`. |
| PP-006 | Startup can time out because daemon stop exceeds the queue deadline. | **Confirmed** | Four possible 5-second waits versus 10-second queue default. |
| PP-007 | Capability is based on an executable check rather than required mechanisms. | **Confirmed** | `hardware.py:597-619`. |
| PP-008 | Raw MSR I/O is not exception-safe or write-complete. | **Confirmed** | `hardware.py:988-1035`. |
| PP-009 | Delayed tasks are not fully owned/ordered by lifecycle. | **Partially correct** | Confirmed missing generation and only newest reference retained; lasting stale state is conditional. |
| PP-010 | Reconciliation compares only a profile name, not the definition. | **Confirmed** | `application.py:1023-1031`; applied name originates from PPD mapping. |
| PP-011 | New paths bypass the injectable root. | **Confirmed** | Absolute paths in the three new methods. |
| PP-012 | The command queue contract is broken. | **Unverifiable** | Environment-specific reproduction conflicts with successful focused/full runs outside that sandbox. |
| PP-013 | README compatibility wording disagrees with the gate. | **Confirmed** | `README.md:11-16`; `hardware.py:604-609`. |

### SOL High

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | Startup disables a dependency required by every successful profile apply. | **Confirmed** | `application.py:155-165, 348-353`; `.venv/.../honor/power.py:175-192`. |
| PP-002 | MSR encoding writes PL2 disabled and loses its time window. | **Confirmed** | `hardware.py:1004-1019`; independently reproduced. |
| PP-003 | The shipped service sandbox cannot open the MSR device. | **Confirmed** | The unit bounds capabilities to DAC-only (`honor-control.service:23-26`). Upstream Linux x86 `msr_open()` checks `capable(CAP_SYS_RAWIO)` and returns `-EPERM` otherwise. This is the correct deterministic deployment finding missed by most reports. |
| PP-004 | Success precedes required delayed work; failures are ignored; stale rewrites are possible. | **Confirmed** | `application.py:354-381, 391-421`; no generation/cancellation before scheduling. The stale-final-state portion is conditional, but the combined finding is sound. |
| PP-005 | Startup persistently masks host power daemons without ownership/restore policy. | **Confirmed** | `hardware.py:874-885`; no capture/restore in lifecycle or uninstall. |
| PP-006 | Reconciliation compares only a PPD label, not definition/hardware state. | **Confirmed** | `hardware.py:787-800`; `application.py:1023-1031`. |
| PP-007 | Production methods bypass the root abstraction. | **Confirmed** | `hardware.py:889-894, 921-940, 989-1024`. |
| PP-008 | Daemon shutdown can exceed the command queue deadline and block startup. | **Confirmed** | Four 5-second subprocess budgets under a 10-second queue timeout. |
| PP-009 | EPP rewrite can return success without writing or verifying requested state. | **Confirmed** | An empty CPU list returns `True`; governor write results are ignored; readback content/errors are discarded (`hardware.py:921-959`). |
| PP-010 | Applied state can hide external drift and delayed failure. | **Confirmed** | `_refresh_power()` overlays `_last_applied_power_profile` on every observation (`application.py:1132-1136`), so the name can remain “applied” after hardware changes. |
| PP-011 | Documentation describes unsupported compatibility/behavior. | **Confirmed** | `README.md:11-16`; `docs/hardware-support.md:23-28`; actual positive gate and incomplete per-mechanism checks. |

### SOL Medium

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | Startup disables a required dependency and persistently masks host services. | **Confirmed** | `application.py:155-165, 348-353`; `hardware.py:874-885`; no restore. |
| PP-002 | RAPL encoding drops PL2 fields. | **Confirmed** | `hardware.py:1004-1019`. |
| PP-003 | API reports success before decisive correction and discards failures. | **Confirmed** | `application.py:354-381, 391-421`. |
| PP-004 | Performance is silently changed to powersave while state claims full apply. | **Partially correct** | Final substitution and state mismatch are confirmed; the report cannot establish that restoring performance is a supported hardware combination. |
| PP-005 | Stale delayed rewrites can overwrite newer selections. | **Partially correct** | Race confirmed; lasting final corruption is conditional and cancellation cannot stop already-running synchronous work. |
| PP-006 | Capability probing omits required resources. | **Confirmed** | `hardware.py:597-619`. |
| PP-007 | EPP rewrite can vacuously succeed and does not verify values. | **Confirmed** | `hardware.py:921-959`. |
| PP-008 | MSR descriptors/short I/O are not robust. | **Confirmed** | `hardware.py:988-1035`. |
| PP-009 | Compatibility and behavior documentation is inaccurate. | **Confirmed** | `README.md:11-16`; `docs/hardware-support.md:23-28`. |

### TERRA XHigh

| Finding | Report claim | Classification | Independent verification |
|---|---|---|---|
| PP-001 | Startup masks the daemon every profile apply still requires. | **Confirmed** | `application.py:155-165, 348-353`; dependency `_set_ppd()`. |
| PP-002 | The packaged service lacks the capability required by the MSR path. | **Confirmed** | `honor-control.service:23-26`; Linux x86 `msr_open()` requires `CAP_SYS_RAWIO`. |
| PP-003 | Final RAPL/EPP outcome is unverified and not represented in public state. | **Confirmed** | `application.py:354-381, 391-421`; `PowerSnapshot` has no pending/verified per-mechanism state (`models.py:311-327`). |
| PP-004 | Rapid changes can apply an obsolete delayed rewrite. | **Partially correct** | Missing generation/cancellation confirmed; lasting wrong final state requires additional timing/failure conditions. |
| PP-005 | The performance governor is silently changed to powersave. | **Partially correct** | Mismatch confirmed, but report does not prove the requested combination is supportable on target Intel P-state behavior. |
| PP-006 | Turbo/max-performance controls persist but are not applied. | **Partially correct** | The resolved dependency always writes fixed `no_turbo=0` and `max_perf_pct=100` (`.venv/.../honor/power.py:221-225`), but the current adapter actually fails earlier because `PowerProfile` rejects those constructor fields. The report found the user-visible contract failure but missed the more fundamental API incompatibility. |
| PP-007 | AMD compatibility statement conflicts with implementation. | **Confirmed** | `README.md:11-16`; `hardware.py:604-609, 778-783`. |


## Missed Issues

### 1. The currently allowed dependency version cannot construct a profile

**Missed by every report except LUNA Max.** `pyproject.toml:27-30` permits `honor-tools>=0.1,<0.2`. The dependency present in the checkout defines `PowerProfile` with only `pl1_uw`, `pl2_uw`, `governor`, `epp`, and `ppd_profile`, while the adapter always sends `turbo_enabled` and `max_perf_pct` (`hardware.py:816-824`). The adapter catches the resulting `TypeError` and returns an error (`841-842`). Manual selection, startup reconciliation, and auto-switching therefore fail before reaching the PPD/MSR logic in the reviewed environment.

This is release-blocking even though it predates the overhaul: the new changes depend on a production boundary that was never integration-tested. The correct fix is to pin a compatible minimum version and test it, or feature-detect/adapt to older APIs while marking unsupported fields explicitly. A sibling checkout must not silently define production behavior that the declared package range does not guarantee.

### 2. The systemd unit lacks `CAP_SYS_RAWIO`

**Missed by all except SOL High and TERRA XHigh.** `packaging/systemd/honor-control.service:23-26` removes every capability except two DAC capabilities. The upstream x86 MSR driver rejects `open()` without `CAP_SYS_RAWIO`. Thus `/dev/cpu/0/msr` can exist and still be unusable by the service. `get_power_capability()` does not test effective service capability, and delayed failure is discarded.

This is more concrete than GLM Max's `ProtectKernelModules` theory: preloading the module does not solve the missing capability. Before adding raw-I/O privilege, the project should decide whether direct MSR access belongs in the main D-Bus daemon at all. A small narrowly scoped privileged helper or a supported kernel/sysfs interface is safer than broadening the whole service.

### 3. Saving an active profile persists first, then can report a failed/non-persisted apply

**Missed by all reports.** `save_power_profile()` writes the new definition to disk first (`application.py:481-490`), then reapplies it if the profile is active (`491-497`). If apply fails, the method returns the apply failure/partial result directly even though the new definition remains persisted. In particular, `_apply_power_profile(..., persist_desired=False)` can return `persisted=False`, contradicting what just happened.

Impact: the UI can tell the user the operation failed without making clear that the changed definition is now durable and may be retried at startup. The save path needs an explicit policy: validate/preflight then atomically commit and converge, or persist a clearly represented pending definition and report `persisted=True, applied=False`.

### 4. Successful hardware mutation followed by config-write failure is not transactional

LUNA Max noticed the general problem, but the other reports missed it. `_apply_power_profile()` sets `_last_applied_power_profile` before awaiting `ConfigStore.update()` (`application.py:354-365`). If persistence raises, hardware and the in-memory marker may have changed, no structured `OperationResult` is returned, and refresh is skipped. The fix is not a rollback fantasy for all hardware; it is a defined transaction state (`attempted`, `hardware_verified`, `desired_persisted`) and recovery/reconciliation path.

### 5. Daemon takeover is gated only by DMI/platform, not by a usable power backend

Several reports criticized capability probing, but most did not connect it to startup side effects. `initialize()` always calls `stop_competing_power_daemons()` after the first refresh (`application.py:155-165`). The method checks only the positive platform match (`hardware.py:865-869`), not dependency API compatibility, PPD/systemctl result, MSR/EPP availability, effective privilege, or whether the user enabled an exclusive-owner mode. A supported laptop with a broken dependency can therefore lose its normal power managers even though Honor Control cannot apply a profile.

### 6. `rewrite_epp()` can consume the queue timeout budget on high-core-count systems

GLM Max called `time.sleep()` itself a defect, which is the wrong abstraction critique. The real issue is cumulative duration: up to five attempts per CPU with 0.1-second sleeps (`hardware.py:931-945`) are serialized inside a command with a 10-second outer deadline. Twenty failing logical CPUs consume roughly the entire budget before filesystem overhead. The operation can time out, poison subsequent queue work until the worker returns, and still continue mutating hardware after the caller has given up. Use one bounded retry budget, per-mechanism timeout reporting, and a single convergence controller.

### 7. The documentation's “desired/applied/observed are separate” invariant is not true in public state

SOL High identified the core state-overlay bug, but most reports did not connect it to the README invariant. `_refresh_power()` overwrites the hardware-derived applied name with `_last_applied_power_profile` whenever that marker is non-empty (`application.py:1132-1136`). README claims those state classes never overwrite one another (`README.md:79-81`). The snapshot needs separate fields for last attempted/verified transaction and current observation; a logical name must not replace observation.

## Bad or Risky Recommendations

### Weakening `ProtectSystem` to make `systemctl mask` work — GLM Max PP-003

Do **not** add `ReadWritePaths=/etc/systemd/system` or weaken `ProtectSystem` on this rationale. The premise is wrong: normal `systemctl mask` asks PID 1 to mutate unit files through the systemd manager. Granting the service direct write access to system unit directories would reduce hardening without fixing the actual ownership contradiction. The better alternative is to move any explicit takeover into a transactional package/admin operation with checked manager results and rollback.

### Assuming masked PPD will be reactivated, then designing around that — GLM Max PP-004

A successfully masked unit cannot be activated. Treating `ppd_ok=False` as non-blocking while retaining the same profile contract would merely hide a failed required mechanism. Define two explicit backend modes instead: PPD-coordinated mode, where PPD stays available and is verified; or exclusive direct mode, where PPD fields are not part of the apply contract and equivalent controls are independently verified.

### Removing `ProtectKernelModules` or loading modules from the main service — GLM Max PP-005

This broadens privilege and still does not provide `CAP_SYS_RAWIO`. If raw MSR is retained, arrange module availability outside the main daemon (for example packaging/modules-load) and use a narrowly privileged helper or explicitly justified capability. Also handle kernel lockdown and readback. Prefer avoiding raw MSR when a supported interface can meet the requirement.

### Blindly restoring PPD/intel_lpmd on every process shutdown

LUNA High, LUNA Max, and SOL Medium include normal shutdown in their restoration recommendations. Restoring on uninstall, disable, failed takeover, and explicit release is essential. Restoring on every process shutdown is not automatically safe: a systemd restart can create a window in which PPD resumes and rewrites state before Honor Control starts again. Model ownership as a durable lease/configuration with original-state records and explicit acquire/release semantics, rather than tying host policy to one Python process's destructor.

### “Cancel and await the old task” as the complete stale-task fix

Several reports recommend cancellation as the primary fix. Once a delayed task has entered `HardwareCommandQueue.run()`, cancelling the coroutine cannot cancel the synchronous worker operation; the queue deliberately marks unfinished cancelled work as timed out/busy (`command_queue.py:115-118`). Use a single supervised convergence worker with a monotonically increasing generation, check generation before every stage and before publishing state, and serialize final verification. Cancellation can be an optimization before work starts, not the correctness boundary.

### Restoring `performance` governor after EPP without proving driver semantics

Multiple reports imply the code should simply restore the requested `performance` governor. The current code explicitly says doing so resets EPP (`hardware.py:910-915`). The reportable defect is that the profile model and success state claim two controls that the backend says cannot coexist. The safer alternative is to validate/normalize supported combinations, expose requested versus effective policy, and verify on target hardware before selecting a sequence.

### Making the entire 0.5-second correction synchronous inside the existing call without a state model

Awaiting convergence is better than returning false success, but simply extending the current D-Bus mutation can collide with the 10-second queue deadline, block the global mutation lock, and degrade UI responsiveness. Either use a bounded two-phase transaction with explicit `pending` status and completion signal, or await a tightly bounded settle/readback phase whose timeout and partial result are first-class.

### Adding `CAP_SYS_RAWIO` to the whole daemon as a one-line fix

TERRA correctly frames this as a security decision, but a naive capability addition would expose every code path and imported dependency in the root D-Bus daemon to raw hardware I/O. Prefer a minimal helper with a tiny argument surface and strict validation, or eliminate the direct MSR path. If the capability is added, make it platform- and install-mode-specific, test under the real unit, and document lockdown/device requirements.

## Comparative Scorecard

Scores use the same standard for every report: 9-10 is exceptional and materially complete; 7-8 is strong but has important gaps; 5-6 is mixed and needs independent re-verification; below 5 is not dependable as a maintainer's action list.

| Report | Accuracy | Depth | Completeness | Prioritization | Fix quality | Architectural understanding | Signal-to-noise | Overall usefulness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SOL High | 9.3 | 9.0 | 8.8 | 9.2 | 8.7 | 9.0 | 9.1 | 9.0 |
| LUNA Max | 8.8 | 9.2 | 9.0 | 8.4 | 8.6 | 9.0 | 8.0 | 8.8 |
| TERRA XHigh | 9.0 | 8.0 | 7.7 | 9.0 | 8.6 | 8.5 | 9.3 | 8.6 |
| SOL Medium | 8.7 | 7.7 | 7.5 | 8.7 | 8.5 | 8.2 | 9.0 | 8.2 |
| LUNA XHigh | 8.2 | 8.3 | 8.2 | 8.1 | 8.3 | 8.4 | 8.1 | 8.2 |
| 5.5 XHigh | 8.2 | 8.7 | 8.1 | 8.3 | 8.2 | 8.5 | 7.8 | 8.2 |
| LUNA High | 8.5 | 7.6 | 7.2 | 8.3 | 8.0 | 8.0 | 8.7 | 8.0 |
| 5.5 High | 8.0 | 7.5 | 7.0 | 7.8 | 7.8 | 7.8 | 8.0 | 7.7 |
| GLM Max | 5.7 | 8.4 | 7.8 | 5.8 | 6.0 | 7.0 | 4.8 | 6.0 |


### Score rationale

- **SOL High:** best deployment/code balance; catches the actual capability boundary and avoids GLM's incorrect systemd theory. Main miss: dependency constructor incompatibility.
- **LUNA Max:** deepest repository/dependency integration review and the only report to prove the active dependency break. Main miss: `CAP_SYS_RAWIO`; a few findings are somewhat over-prioritized.
- **TERRA XHigh:** exceptionally concise and accurate, with the key capability and turbo/max contract findings. Less complete on lifecycle details, dependency API shape, EPP false success, and state overlay.
- **SOL Medium:** high signal and sound fixes, especially around EPP verification and transaction state. It lacks the packaged-service capability and dependency discoveries.
- **LUNA XHigh:** broad and architecturally aware; loses points for treating an environment-specific queue failure as a release concern and for some overstatement around governor/task outcomes.
- **5.5 XHigh:** thorough and generally accurate, but similarly elevates the sandbox queue behavior and misses the two strongest dependency/deployment blockers.
- **LUNA High:** concise, accurate core review with good lifecycle/state observations, but materially less complete.
- **5.5 High:** identifies the central code bugs but omits several production blockers and gives too much weight to the local command-queue environment.
- **GLM Max:** substantial effort and several valid findings, but major false positives in systemd behavior, duplicated concurrency findings, cosmetic noise, and missed deterministic blockers reduce trust.

## Final Ranking

1. **SOL High** — strongest overall accuracy, prioritization, and production deployment reasoning. It correctly found the missing raw-I/O capability, which directly invalidates the central MSR mechanism under the shipped unit.
2. **LUNA Max** — strongest dependency and transaction analysis. Its proof that the currently resolved dependency rejects the adapter's constructor is uniquely valuable and release-blocking.
3. **TERRA XHigh** — best signal-to-noise and excellent severity discipline; catches both the service capability and the unimplemented turbo/max contract, but is less complete.
4. **SOL Medium** — technically disciplined and practical, with very few distractions; lacks the two most important dependency/deployment discoveries.
5. **LUNA XHigh** — broad and useful, but includes one unverified runtime finding and modest overstatement.
6. **5.5 XHigh** — similarly broad, with strong timeout/capability analysis; penalized for the queue claim and missed current dependency/service-capability defects.
7. **LUNA High** — reliable core findings and good architecture awareness, but narrower coverage.
8. **5.5 High** — correct on the main source bugs, yet incomplete on packaging, dependency, host lifecycle, and observed-state integrity.
9. **GLM Max** — weakest because confident false deployment claims could lead maintainers to weaken systemd hardening and misunderstand masked-unit behavior.

## Recommended Consolidated Action Plan

### Critical

#### C1. Define and enforce a compatible `honor-tools` contract

- **Underlying problem:** The adapter sends fields unsupported by the allowed/resolved `honor-tools 0.1.0` constructor.
- **Evidence:** `pyproject.toml:27-30`; `hardware.py:816-824`; `.venv/.../honor/config.py:25-34`; direct probe returns `unexpected keyword argument 'turbo_enabled'`.
- **Impact:** Manual apply, startup reconciliation, and auto-switch fail before hardware mutation.
- **Recommended fix:** Pin the first known-compatible version and publish it, or adapt through capability/version detection. Do not expose turbo/max controls unless the backend applies and verifies them. Fail installation/preflight on an incompatible API.
- **Relevant files:** `pyproject.toml`, `hardware.py`, installer, dependency package.
- **Suggested tests:** Isolated matrix against minimum and maximum supported dependency versions; production-adapter constructor/result contract; explicit unsupported-field behavior.

#### C2. Replace the contradictory PPD ownership model

- **Underlying problem:** Startup masks PPD, but the apply result requires a successful PPD operation.
- **Evidence:** `application.py:155-165, 348-353`; `hardware.py:874-885`; dependency `_set_ppd()`.
- **Impact:** Full profile apply/reconciliation cannot succeed after a successful mask; the system's normal power manager can remain disabled after Honor Control is removed.
- **Recommended fix:** Choose one mode. Prefer PPD-coordinated mode unless exclusive ownership is proven necessary. If exclusive mode exists, remove PPD from that apply contract, make takeover explicit/admin-controlled, preflight all mechanisms, capture original unit/HWP state, check every manager result, roll back on failure, and restore on explicit disable/uninstall.
- **Relevant files:** `application.py`, `hardware.py`, service/installer/uninstaller, docs.
- **Suggested tests:** Mocked service-manager state matrix; failed/partial takeover rollback; uninstall restoration; disposable-VM PPD usability before/after install and removal.

#### C3. Correct and verify the RAPL MSR encoder

- **Underlying problem:** PL2 fields are placed at absolute positions and then shifted by 32 again.
- **Evidence:** `hardware.py:1004-1019`; deterministic arithmetic reproduction.
- **Impact:** The method returns success while PL2 is disabled/malformed, defeating the overhaul's main purpose and writing incorrect CPU policy.
- **Recommended fix:** Extract pure encode/decode functions with named masks, validate field widths/lock state, build each 32-bit half with local bit positions or set global positions once, preserve documented fields deliberately, and read back/decode after write.
- **Relevant files:** `hardware.py` or a dedicated Intel RAPL backend.
- **Suggested tests:** Known register vectors, PL1/PL2 enable/clamp/time fields, unit rounding, overflow, lock bit, short I/O, and readback mismatch.

### High

#### H1. Make raw-MSR deployment coherent and least-privileged

- **Underlying problem:** The service lacks `CAP_SYS_RAWIO`; capability probing does not know that, and failure is asynchronous/invisible.
- **Evidence:** `honor-control.service:23-26`; Linux x86 `msr_open()` capability check; `hardware.py:597-619, 988-1035`.
- **Impact:** Direct MSR enforcement cannot work under the standard unit even when the device exists.
- **Recommended fix:** Prefer a narrow helper or supported kernel interface. If raw MSR remains in-process, explicitly justify/add the minimum capability, arrange module/device availability outside runtime, check lockdown and device access in capability probing, and perform installed-unit integration tests.
- **Relevant files:** systemd unit, hardware backend, installer/docs.
- **Suggested tests:** Run the real unit in a VM with/without device, capability, module, and lockdown; verify structured unavailable/degraded results.

#### H2. Model profile application as verified convergence, not immediate success

- **Underlying problem:** The decisive delayed MSR/EPP operations occur after success/persistence and their normal failures are ignored.
- **Evidence:** `application.py:354-381, 391-421`.
- **Impact:** GUI/CLI can report and persist a profile that never reached hardware; hooks and later logic act on false state.
- **Recommended fix:** Introduce `pending -> verified_applied | partial | failed` with per-mechanism results. Either await a bounded settle/readback or publish completion asynchronously. Never set the verified marker until required readback succeeds.
- **Relevant files:** `application.py`, models/codec/client/GUI, hardware result types.
- **Suggested tests:** Delayed false return, exception, timeout, partial mechanism, state transition, client notification, and recovery/retry.

#### H3. Reconcile and observe complete effective state

- **Underlying problem:** Applied name is inferred from PPD only, and `_last_applied_power_profile` overwrites later observation.
- **Evidence:** `hardware.py:787-800`; `application.py:1023-1031, 1132-1136`.
- **Impact:** Startup can skip a needed apply; external drift and failed delayed work remain hidden; custom/edited definitions cannot be verified by name.
- **Recommended fix:** Keep desired, last attempted, last verified, and observed state separate. Compare all supported effective fields or a verified definition fingerprint, and always converge after ownership acquisition when observation is incomplete.
- **Relevant files:** `models.py`, `application.py`, `hardware.py`, D-Bus codec/UI.
- **Suggested tests:** Same name/different definition, PPD label match with wrong EPP/RAPL, external drift after success, custom profile, unknown observation.

#### H4. Gate destructive takeover on full capability and checked results

- **Underlying problem:** DMI match alone triggers daemon masks; command failures are discarded.
- **Evidence:** `application.py:155-165`; `hardware.py:865-896`; `get_power_capability()` at `597-619`.
- **Impact:** Honor Control can disable normal power management even when its dependency or hardware backend is unusable.
- **Recommended fix:** Build typed per-mechanism preflight, require rollback prerequisites before takeover, return structured manager results, and abort/rollback atomically. Do not mutate host policy during ordinary discovery.
- **Relevant files:** hardware/application/service management.
- **Suggested tests:** Missing dependency/API, missing systemctl/unit, permission failure, timeout, unsupported platform, partial mask, rollback failure.

#### H5. Repair persistence/apply transaction semantics

- **Underlying problem:** Active profile edits persist before apply and can return misleading persistence status; normal apply marks in-memory applied before persistence succeeds.
- **Evidence:** `application.py:354-365, 481-497`.
- **Impact:** Durable config, hardware, returned booleans, and snapshot can disagree.
- **Recommended fix:** Define explicit transaction stages and return each truth independently. For active edits, validate/preflight, persist a pending definition, attempt convergence, then report `persisted=True` and actual applied status; retain recovery state on failure.
- **Relevant files:** `application.py`, `ConfigStore`, result models/client/UI.
- **Suggested tests:** Config write failure after hardware success, active save apply failure, restart after partial transaction, and UI messaging for persisted-but-not-applied.

### Medium

#### M1. Make delayed work latest-wins and fully supervised

- **Underlying problem:** Multiple tasks can run; only the newest reference is retained/cancelled.
- **Evidence:** `application.py:367-373, 181-186`.
- **Impact:** Transient stale writes and difficult shutdown/restart behavior; final state can be stale when the newer generation fails or is cancelled.
- **Recommended fix:** One convergence controller with generation IDs, checks before every write/publication, and tracked completion. Gather it during shutdown; do not rely on cancellation of synchronous worker calls.
- **Suggested tests:** Rapid A→B→C applies, cancellation before/after worker entry, B failure, shutdown during settle.

#### M2. Correct EPP success and effective-governor semantics

- **Underlying problem:** Empty CPU sets succeed, governor write results are ignored, readback is not compared, and performance definitions are silently normalized to powersave.
- **Evidence:** `hardware.py:921-959`; `models.py:296-305`.
- **Impact:** False success and misleading profile state.
- **Recommended fix:** Require eligible CPUs, return per-CPU structured results, compare normalized readback, check governor operations, and represent requested versus effective governor or reject unsupported combinations.
- **Suggested tests:** No CPUs, missing cpufreq, write/read mismatch, governor failure, performance/EPP combinations, CPU hotplug.

#### M3. Align timeout budgets and retry policy

- **Underlying problem:** Four daemon commands can exceed the queue timeout; EPP retries can consume it; failed auto-switch repeats every two seconds with no backoff.
- **Evidence:** `hardware.py:874-883, 931-945`; `command_queue.py:26`; `application.py:1327-1377`.
- **Impact:** Startup failure, poisoned queue, repeated logs/writes, and slow recovery.
- **Recommended fix:** Use one operation-level deadline propagated to substeps, bounded total retry budgets, exponential/backoff health reporting, and no destructive work after caller timeout without generation validation.
- **Suggested tests:** Worst-case subprocess timeouts, many failing CPUs, queue timeout then late completion, auto-switch persistent failure/backoff.

#### M4. Harden and isolate privileged I/O

- **Underlying problem:** Absolute paths bypass the adapter root; descriptors and short I/O are unsafe; daemon commands are not injectable.
- **Evidence:** `hardware.py:889-894, 921-940, 988-1044`.
- **Impact:** Host-touching tests, leaked descriptors, uncaught malformed reads, false write success, and poor platform extensibility.
- **Recommended fix:** Inject typed sysfs/MSR/service-manager ports; use `try/finally` or context-managed helpers; require exact 8-byte I/O and readback; classify errors.
- **Suggested tests:** Fake root/device, short read/write, `struct.error`, lseek/open/write failures, service-manager call outcomes.

### Low

#### L1. Correct documentation and compatibility claims

- **Underlying problem:** README falsely says all MagicBooks are Intel and describes an AMD fallback that the gate prevents; hardware-support docs claim every mechanism is checked separately.
- **Evidence:** `README.md:11-16`; `docs/hardware-support.md:23-28`; `hardware.py:597-619, 778-783`.
- **Impact:** Users and maintainers misunderstand support, privilege, failure behavior, and host-service side effects.
- **Recommended fix:** Publish a tested model/backend matrix, state that non-allowlisted hardware gets no power writes, document ownership/rollback and raw-MSR requirements, and keep requested/observed semantics precise.
- **Suggested tests/checks:** Documentation assertions tied to capability tests; release checklist requiring installed-unit hardware validation.

#### L2. Add focused regression tests with production-like collaborators

This is not a substitute for fixing the design, but every item above should land with deterministic tests. The current fake returns success for the dangerous paths and therefore validates orchestration only. Add pure encoder tests, dependency-contract tests, injected service-manager/sysfs/MSR tests, two-phase application tests, and at least one disposable-VM installed-service test.

## Final Verdict

All nine reports correctly concluded that the overhaul is not release-ready, but they are not interchangeable. Use **SOL High** as the best primary review, merge in **LUNA Max's dependency/transaction findings**, and use **TERRA XHigh's capability and turbo/max observations**. Do not implement GLM Max's `ProtectSystem`/D-Bus-activation remedies.

The minimum credible release bar is:

1. a tested, pinned dependency contract;
2. one coherent and reversible power-manager ownership model;
3. corrected/read-back-verified MSR encoding under a least-privileged deployment;
4. explicit pending/verified application state with complete reconciliation;
5. focused tests for every privileged and delayed path.
