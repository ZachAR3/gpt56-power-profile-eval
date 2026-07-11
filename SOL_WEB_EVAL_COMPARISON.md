# Independent comparison of `SOL_EVAL.md`, `TERRA_EVAL.md`, and `LUNA_EVAL.md`

## 1. Executive summary

**Best overall report: `LUNA_EVAL.md`.**

Final ranking:

1. **`LUNA_EVAL.md` — 90.1/100**
2. **`SOL_EVAL.md` — 83.7/100**
3. **`TERRA_EVAL.md` — 79.9/100**

The first-place result is decisive rather than cosmetic. LUNA is the only report that actually exercised the production adapter against the dependency resolved in this checkout and discovered the earliest failure in the real call path: `HonorToolsAdapter` passes `turbo_enabled` and `max_perf_pct` to `honor.config.PowerProfile`, but the installed and declared-compatible `honor-tools 0.1.0` constructor accepts neither argument. A real apply therefore returns a `PowerProfile.__init__()` error before `honor.power.apply_profile()` or any hardware write is reached.

LUNA also found the major PPD ownership contradiction, the PL2 register-encoding defect, the unverified delayed enforcement, and most of the important lifecycle and state-management problems. Its main weaknesses are severity inflation on several secondary findings, excessive length, and one important deployment miss: the packaged systemd service drops `CAP_SYS_RAWIO`, so the standard upstream x86 MSR driver will reject `/dev/cpu/0/msr` opens even after the dependency and PPD problems are fixed.

SOL is a strong, technically disciplined second. Its nine findings are almost all valid, well-evidenced, and sensibly prioritized. It has the best overall signal-to-noise ratio. It nevertheless misses both the actual dependency contract failure and the packaged-service MSR capability failure, so its description of the PPD contradiction as the first operative failure is incomplete.

TERRA is concise and makes the best unique deployment observation: the systemd unit cannot use the new MSR path because `CAP_SYS_RAWIO` is absent. That is a genuine high-severity issue missed by the other two reports. However, TERRA misses the deterministic PL2 encoder bug and the immediate `PowerProfile` constructor failure. Its `turbo_enabled`/`max_perf_pct` finding also describes a runtime path that the current adapter cannot reach; the underlying dependency limitation is real, but the stated failure scenario is not the current behavior.

**Reliance verdict:**

- `LUNA_EVAL.md` is the best primary review input, but it still needs targeted verification for packaging/privilege behavior and severity calibration before being used as the sole release decision.
- `SOL_EVAL.md` and `TERRA_EVAL.md` are **unsafe to rely on alone** for a merge or release decision because each omits at least one deterministic release blocker.
- The best defensible review is the consolidated list in section 9, not any single original report.

## 2. Repository and change scope

### Revision reviewed

| Item | Verified value |
|---|---|
| Current branch | `main` |
| Reviewed commit | `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f` — `README: document Intel-only compatibility` |
| Remote default branch | `origin/HEAD -> origin/main` |
| Working-tree state on extraction | Tracked tree clean; the three evaluation reports were untracked |
| Literal merge base with default branch | `34d31f9` (`HEAD`), because the checkout is already the default branch |
| Defensible functional base | `4d8994ab2eeb9595d1222ac4ad1789b8579a966f` — the root/initial commit |
| Reviewed range | `4d8994a..34d31f9` |

Relevant commits:

1. `15f4d66` — `Fix power profile application: RAPL, EPP, and UI snap-back`
2. `d391bb0` — `Clean up power profile code: safety, simplicity, correctness`
3. `7213294` — `Guard stop_competing_power_daemons behind platform detection`
4. `34d31f9` — `README: document Intel-only compatibility`

The range changes four tracked files: `README.md`, `honor_control/backend/application.py`, `honor_control/backend/hardware.py`, and `honor_control/frontend/gui/pages/power.py`, totaling 326 insertions and 7 deletions. No test file changed in the range.

### Major subsystems inspected

- Power-profile definitions, validation, persistence, and custom profile registry.
- `ApplicationService` startup, manual apply, delayed enforcement, reconciliation, refresh, auto-switch, shutdown, and fan-profile consumption.
- `HardwarePort`, `FakeHardware`, and `HonorToolsAdapter` capability, PPD, sysfs, EPP, HWP, and raw-MSR paths.
- `HardwareCommandQueue` timeout and poisoning behavior.
- `RuntimeSupervisor` lifecycle and failed-controller behavior.
- D-Bus, CLI, tray, and GUI propagation of desired/applied state.
- Systemd unit hardening and capability bounds.
- Install/uninstall and restore behavior.
- The archived resolved `honor-tools 0.1.0` source and metadata.
- Relevant tests, documentation, and `OVERHAUL_PLAN.md` acceptance criteria.

### Commands and checks run

| Check | Result |
|---|---|
| Git status, refs, remotes, default branch, log, merge base, commit shows, blame, and full range diff | Confirmed the revision, functional base, and four-commit overhaul range |
| `python3 -m pytest -q -p no:cacheprovider` with the archived venv site-packages on `PYTHONPATH` | **221 passed in 8.83s** |
| Archived `.venv/bin/ruff check honor_control tests` | **Passed** |
| `python3 -m compileall -q honor_control tests` | Passed |
| `git diff --check 4d8994a..HEAD` | Passed |
| `bash -n scripts/*.sh` | Passed |
| `systemd-analyze verify packaging/systemd/honor-control.service` | Parsed the unit but reported the expected sandbox-environment warning that `/usr/bin/honor-control-service` is not installed here; no source syntax defect was inferred |
| Dependency inspection | Confirmed `honor-tools 0.1.0`; `PowerProfile(pl1_uw, pl2_uw, governor, epp, ppd_profile)` has no turbo/max fields |
| Safe adapter probe using a temporary empty root | Returned `PowerProfile.__init__() got an unexpected keyword argument 'turbo_enabled'`; no apply or hardware write was reached |
| Pure reproduction of the MSR packing expression | Confirmed the written PL2 enable bit and PL2 time-window field are both zero |
| Systemd unit capability inspection | Confirmed `CapabilityBoundingSet=CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH`, with no `CAP_SYS_RAWIO` |
| Upstream Linux x86 MSR driver inspection | Confirmed `msr_open()` requires `CAP_SYS_RAWIO`; successful writes also pass through lockdown/filtering and taint the kernel `CPU_OUT_OF_SPEC` |

### Limitations and assumptions

No service was started, no unit was stopped or masked, no sysfs file was written, and no MSR was read or written. Hardware-state conclusions are based on code-path analysis, dependency source, register arithmetic, the packaged unit, and upstream kernel behavior. The archive's virtual environment was created for Python 3.14 while the analysis sandbox uses Python 3.13; its pure Python and ABI-stable packages were loaded explicitly to run the complete suite. No conclusion depends on mutating real hardware.

Because the root commit already contains some relevant design defects, findings are distinguished where practical as newly introduced, pre-existing but exposed, or latent behind an earlier failure. A downstream bug is not dismissed merely because the current constructor mismatch prevents reaching it; it remains a valid defect that will become operative after the first blocker is fixed.

## 3. Independent implementation assessment

### How the system actually works

`ConfigStore` owns the persisted manual desired profile, profile definitions, and AC/battery policy. `ApplicationService` sequences changes and projects snapshots. Production hardware work goes through one `HardwareCommandQueue` thread into `HonorToolsAdapter`; clients use D-Bus and never write hardware directly.

Startup performs the following sequence:

1. Load persisted state.
2. Refresh platform, capabilities, and observed domains.
3. Call `stop_competing_power_daemons()` through the 10-second hardware queue.
4. On a positively detected MRA-XXX/Intel platform, run `systemctl stop` and `systemctl mask` for `power-profiles-daemon` and `intel_lpmd`, then best-effort write `hwp_dynamic_boost=1`.
5. Compare the persisted desired name with `PowerSnapshot.applied_profile`, which production derives only from `powerprofilesctl get`/the PPD profile label.
6. Reapply only when those names differ.

A manual or automatic apply constructs a seven-field dictionary and calls `HonorToolsAdapter.apply_power_profile()`. The current adapter then attempts to instantiate the dependency's `PowerProfile` with all seven values. In this checkout, that constructor accepts only five. The adapter catches the resulting `TypeError` and returns an error dictionary, so current production apply, startup reconciliation, and auto-switch all fail before reaching `honor.power.apply_profile()`.

If that mismatch is fixed, the dependency's apply sequence writes RAPL sysfs, calls `powerprofilesctl set`, writes EPP/governors, and forces `no_turbo=0` plus `max_perf_pct=100`. The application requires all normalized result groups to be true. On success it marks the profile applied, optionally persists it, refreshes the snapshot, schedules a 0.5-second task, and immediately returns success. The delayed task writes MSR 0x610 and rewrites EPP/governors, but discards both Boolean results and performs no final verification.

### Ground truth: most important real issues

1. **Critical — Declared dependency contract is broken.** The resolved `honor-tools 0.1.0` cannot construct the profile object the adapter requests. This is the current first failure in every real apply path.
2. **Critical — Power-manager ownership is self-contradictory and irreversible.** Startup stops/masks PPD, but the delegated apply path still calls and requires `powerprofilesctl set`. Unit state and HWP boost are not restored on shutdown, failure, or uninstall.
3. **High — The packaged service cannot open the MSR device.** The upstream x86 MSR driver requires `CAP_SYS_RAWIO`; the systemd bounding set removes it. This is independent of ordinary file permissions and remains a blocker after the dependency/PPD problems are fixed.
4. **High — PL2 is encoded incorrectly.** PL2 enable and time-window bits are positioned as global bits inside a temporary upper word and shifted again, so both are discarded by the 64-bit mask.
5. **High — Public success precedes and ignores final enforcement.** The service persists and advertises an applied profile before delayed MSR/EPP work; false results and drift are not represented.
6. **Medium — Requested/effective governor semantics conflict.** A requested `performance` governor is deliberately left as `powersave`, while the stored profile and applied name continue to say `performance`.
7. **Medium — Delayed tasks are stale-write prone and incompletely owned.** Older tasks are not cancelled/versioned; shutdown only cancels the newest reference.
8. **Medium — Startup reconciliation compares a PPD label, not the complete profile.** Matching PPD names can suppress needed RAPL/EPP/governor reconciliation.
9. **Medium — Daemon cleanup can exceed the queue deadline.** Four sequential five-second subprocess limits sit behind a ten-second queue deadline, allowing startup failure and a poisoned queue.
10. **Medium — Capability modeling is materially incomplete.** It checks importability, platform identity, and the `powerprofilesctl` executable, not dependency API compatibility, PPD service state, MSR privilege/device/lockdown, EPP/governor paths, or rollback prerequisites.
11. **Medium — Auto-switch failure handling has two bad modes.** Structured partial results retry every two seconds forever; an exception such as a queue timeout escapes the loop, after which `RuntimeSupervisor` marks the controller failed and does not restart it.
12. **Medium — Profile persistence and hardware application are not one coherent transaction.** A successful hardware call followed by a save failure leaves hardware, memory, disk, and restart behavior inconsistent.
13. **Medium — Turbo/max-performance controls are not supported by the resolved dependency.** In the current build they cause constructor failure; merely deleting the unsupported arguments would still leave `honor.power.apply_profile()` forcing turbo enabled and 100% max performance.
14. **Medium — Production-risk paths have no meaningful adapter tests.** The 221-test suite passes because `FakeHardware` unconditionally succeeds for the new operations.
15. **Low/medium — EPP and MSR helpers have false-success and robustness gaps.** Empty CPU enumeration returns EPP success, governor results/readback values are ignored, MSR descriptors can leak on intermediate errors, and short I/O is not validated.

The intended architecture in `OVERHAUL_PLAN.md` is substantially better than the implementation: it explicitly calls for per-mechanism applicability, settled readback, updating applied state only after verification, and no repeated auto-switch retry. The reports should therefore judge these behaviors as implementation failures, not intentional architectural choices.

## 4. Finding-by-finding verification

### `SOL_EVAL.md`

| Finding | Classification | Severity | Evidence | Corrected interpretation / missing context |
|---|---|---:|---|---|
| PP-001 — Startup disables a required dependency and leaves services masked | **Correct but incomplete** | Critical is appropriate | Strong: startup ordering, dependency `_set_ppd()`, shutdown/uninstall paths | The contradiction is real, but the current adapter fails even earlier on the `PowerProfile` constructor. SOL describes the next blocker as though it were the first runtime failure. It also misses the packaged MSR capability problem. |
| PP-002 — RAPL encoder drops PL2 enable/time window | **Correct and well-supported** | High is appropriate | Deterministic source arithmetic | Exact reproduction confirms both fields become zero. This is one of SOL's strongest findings. |
| PP-003 — Success precedes delayed correction and discards failures | **Correct and well-supported** | High is appropriate | Direct control-flow and snapshot evidence | Correct. It is latent until initial apply succeeds, but remains release-blocking after the dependency/PPD fixes. |
| PP-004 — `performance` is changed to `powersave` | **Correct but overstated** | High should be Medium | Direct implementation evidence | The contract/state mismatch is real. The actual performance impact is driver-specific, and the source explicitly treats EPP as authoritative; the defect is primarily undisclosed normalization and false reporting, not necessarily catastrophic performance loss. |
| PP-005 — Delayed tasks are not superseded | **Correct and well-supported** | Medium is appropriate | Task ownership and queue ordering support the race | Correct. The queue prevents simultaneous calls but not obsolete calls. |
| PP-006 — Capability probe omits required resources | **Correct but incomplete** | Medium is appropriate | Capability implementation and new mechanisms | Correct broad diagnosis. It should have singled out the concrete packaged-service `CAP_SYS_RAWIO` blocker and dependency API compatibility, both stronger than a generic probe concern. |
| PP-007 — EPP can succeed with zero CPUs and lacks value verification | **Correct and well-supported** | Medium is reasonable | Empty-loop behavior and discarded readback content | Correct. Governor-write failures are also ignored. |
| PP-008 — MSR descriptor/short-I/O robustness | **Correct and well-supported; low-value** | Low is appropriate | Manual descriptor lifecycle and exception types | Valid defensive finding, properly kept low priority. |
| PP-009 — Compatibility/behavior docs are inaccurate | **Correct and well-supported** | Low is appropriate | README, hardware-support docs, and actual platform gate | Correct, including the unsupported AMD “sysfs-only EPP” claim and undocumented persistent service changes. |

SOL's grouped testing, architecture, and positive-observation sections are generally accurate. Its typed-result recommendation is especially good and indirectly recognizes the unsafe `result.get(..., True)` contract. The report has no major false-positive cluster; its principal weakness is omission rather than invention.

### `TERRA_EVAL.md`

| Finding | Classification | Severity | Evidence | Corrected interpretation / missing context |
|---|---|---:|---|---|
| PP-001 — Startup masks the daemon still required by apply | **Correct but incomplete** | Critical is appropriate | Strong dependency and lifecycle evidence | Real contradiction and persistent host effect. As with SOL, current real applies fail first on the constructor mismatch. |
| PP-002 — Packaged service lacks MSR capability | **Correct and well-supported** | High is appropriate | Systemd bounding set plus upstream x86 MSR `msr_open()` | This is TERRA's most valuable and most distinctive finding. Root UID and DAC capabilities do not replace `CAP_SYS_RAWIO`. It should be included in any release gate. |
| PP-003 — Final RAPL/EPP result is not represented | **Correct and well-supported** | High is appropriate | Direct control flow and snapshot overlay | Correct. |
| PP-004 — Rapid changes can run obsolete delayed rewrites | **Correct and well-supported** | Medium is appropriate | Task replacement without cancellation/generation | Correct. |
| PP-005 — Performance governor silently becomes powersave | **Correct and well-supported** | Medium is appropriate | Direct implementation evidence | Better calibrated than SOL/LUNA. The key defect is requested/effective-state mismatch. |
| PP-006 — Turbo/max controls persist but are not applied | **Partially correct; misleading as current runtime behavior** | Medium only after correction | Dependency `apply_profile()` does force `no_turbo=0` and `max_perf_pct=100` | The adapter never reaches that code with the installed dependency because constructing `PowerProfile` with those fields raises first. The underlying compatibility/semantics problem is valid, but the stated scenario “apply enables turbo and sets 100%” is not what the current adapter does; current behavior is complete apply failure. |
| PP-007 — AMD documentation conflicts with implementation | **Correct and well-supported** | Low is appropriate | README and exact Intel/MRA allowlist | Correct. |

TERRA's command evidence and concise presentation are strong. Its main technical failure is not following the adapter call far enough to execute or inspect the constructor boundary; that also leads it to misstate PP-006. It additionally misses the deterministic PL2 arithmetic bug despite focusing on the MSR path.

### `LUNA_EVAL.md`

| Finding | Classification | Severity | Evidence | Corrected interpretation / missing context |
|---|---|---:|---|---|
| PP-001 — Resolved dependency API makes every real apply fail | **Correct and well-supported** | Critical is appropriate | Exact constructor signature plus safe adapter probe | This is the most important finding in any report and establishes the true first failure in the current checkout. |
| PP-002 — Startup masks power managers and never restores them | **Correct and well-supported** | Critical is appropriate | Startup, systemctl loop, dependency, shutdown, uninstall | Correct. The HWP state is also changed without capture/restore. |
| PP-003 — Direct RAPL encoder drops PL2 fields | **Correct and well-supported** | High is appropriate | Exact arithmetic reproduction | Correct. |
| PP-004 — Success returned before delayed enforcement | **Correct and well-supported** | High is appropriate | Direct control flow, ignored Booleans, snapshot overlay | Correct. |
| PP-005 — Performance profile ends with powersave | **Correct but overstated** | High should be Medium | Direct implementation evidence | The state/contract mismatch is certain; real performance impact and whether `powersave`+EPP is undesirable are platform-specific. |
| PP-006 — Reconciliation trusts only PPD label | **Correct but overstated** | High should be Medium | `read_power()` mapping and name-only comparison | Correct and important for restart correctness, but subordinate to the immediate apply blockers and generally recoverable by conservative reapply. |
| PP-007 — Cleanup can exceed queue deadline and abort startup | **Correct but overstated** | High should be Medium | Four 5-second subprocess limits behind a 10-second queue deadline | The failure mode is real and can create a restart loop, but it requires slow/hung systemctl operations rather than ordinary execution. |
| PP-008 — Rewrites are not generation-safe/fully owned | **Correct but overstated** | High should be Medium | Task replacement, split queue calls, shutdown behavior | Correct race/lifecycle analysis; likely transient in ordinary use unless the newer task fails or shutdown intervenes. |
| PP-009 — Capability probe is weaker than mechanisms | **Correct and well-supported** | Medium is appropriate | Capability code and docs | Correct. It misses the most concrete manifestation: the systemd unit removes `CAP_SYS_RAWIO`. |
| PP-010 — Failed auto-switch retries every two seconds | **Correct but incomplete** | Medium is appropriate | State variables advance only on `result.applied` | Correct for structured partial/failure results. It misses the opposite exception path: queue/apply exceptions escape and permanently stop the supervised auto-switch task. |
| PP-011 — Hardware success plus persistence failure diverges state | **Correct and well-supported** | Medium is appropriate | Apply-before-save and save-before-reapply paths | Correct, though pre-existing rather than introduced by the four commits. It is still relevant to the overhaul's desired/applied guarantees. |
| PP-012 — High-risk paths lack production-adapter tests | **Correct and well-supported** | Medium is appropriate | No test changes; FakeHardware always succeeds | Correct. |
| PP-013 — New I/O bypasses injected root and duplicates ownership | **Correct and well-supported** | Low is appropriate | Hard-coded `/sys`, `/dev`, and direct subprocess paths | Correct maintainability/testability concern. |
| PP-014 — AMD compatibility statement is false | **Correct and well-supported** | Low is appropriate | README and platform gate | Correct. |

LUNA has no substantive fabricated finding. Its penalties come from ranking four secondary issues as High, repeating overlapping state/verification concerns, and missing the systemd capability boundary. Its breadth is nevertheless mostly useful rather than filler.

## 5. Missed issues and missed context

### Important misses by `LUNA_EVAL.md`

1. **High — Packaged-service `CAP_SYS_RAWIO` blocker.** The unit's capability bounding set excludes the capability required by the upstream x86 MSR driver. LUNA discusses missing devices/permissions generically but does not identify the deterministic packaged configuration failure.
2. **Medium — Turbo/max semantics after the constructor fix.** LUNA correctly finds the constructor mismatch, but it does not separately explain that simply dropping the two arguments would still make the dependency force turbo enabled and `max_perf_pct=100`.
3. **Low/medium — EPP false success and MSR short-I/O details.** It does not isolate zero-CPU success, ignored governor results/readback values, descriptor leaks, or short I/O as SOL does.

### Important misses by `SOL_EVAL.md`

1. **Critical — Actual resolved dependency constructor mismatch.** This is the largest omission in SOL and changes the current runtime interpretation of every downstream apply finding.
2. **High — Packaged-service `CAP_SYS_RAWIO` blocker.** SOL recommends capability checks but does not inspect the concrete systemd/kernel boundary.
3. **Medium — Name-only startup reconciliation.** It does not identify that matching PPD labels suppress full-state reconciliation.
4. **Medium — Cleanup timeout versus queue deadline.** It misses the 20-second internal worst case behind a 10-second queue timeout.
5. **Medium — Persistence failure and auto-switch failure-mode asymmetry.** It covers stale delayed tasks but not the full desired/applied transaction or retry/terminal-failure behavior.

### Important misses by `TERRA_EVAL.md`

1. **Critical — Actual resolved dependency constructor mismatch.** TERRA inspected the dependency but failed to validate the constructor used by the adapter.
2. **High — Deterministic PL2 encoding bug.** This is a direct arithmetic defect in the exact MSR path TERRA reviewed.
3. **Medium — Startup reconciliation is label-only.** It misses RAPL/EPP/governor drift hidden behind a matching PPD profile name.
4. **Medium — Cleanup/queue timeout mismatch and weak capability breadth.** Its capability finding is excellent but narrow; it omits the multi-command startup deadline and several other resources.
5. **Medium/low — EPP empty-set/readback behavior, descriptor robustness, and explicit production-adapter test gap.** These are valid secondary issues absent from the report.

### Issues or context missed by all three

1. **Medium — Auto-switch exceptions permanently stop the controller.** LUNA correctly identifies infinite retry for structured failure results, but none of the reports notes that `_auto_switch_loop` has no outer exception recovery. A queue timeout or other exception from `_apply_power_profile()` escapes; `RuntimeSupervisor` marks the task failed and does not restart it. The system therefore oscillates between aggressive repeated retry for ordinary partial results and permanent loss of auto-switch for exceptional failures.
2. **Medium operational context — Successful raw-MSR writes taint the kernel.** The upstream x86 MSR driver calls `add_taint(TAINT_CPU_OUT_OF_SPEC, ...)` on writes and applies lockdown/write filtering. Even a corrected, privileged implementation has a supportability and observability cost that should be explicit in architecture and release documentation. TERRA inspected the same driver for `CAP_SYS_RAWIO` but did not mention this consequence.
3. **Medium deployment context — The project does not provision the MSR device.** No installer or modules-load configuration ensures the `msr` module/device exists, while the service unit uses `ProtectKernelModules=true`, preventing the service from loading it itself. This is separate from file permissions and reinforces that the raw-MSR mechanism needs an explicit optional capability/deployment contract.
4. **Low — The encoder's field-preservation policy remains incomplete beyond the reported shift bug.** The code rebuilds the register rather than masking only intended fields; PL2 clamp and other non-target bits are not explicitly preserved or deliberately normalized. Fixing only the double shift is not sufficient for a robust register writer.

### Shared false assumptions

- **SOL and TERRA assume the dependency apply function is reached.** It is not reached with the resolved package because object construction fails first.
- **All reports sometimes discuss “applied” downstream behavior without consistently distinguishing current reachability from latent behavior.** Their downstream findings remain valid, but the comparison should state the prerequisite fixes explicitly.
- **The three reports generally treat a successful write syscall as hardware verification.** The code itself does this, but a defensible release gate needs decoded readback and a stated tolerance/driver model.

### Useful positive observations

No material positive implementation decision was missed by all three. Collectively they correctly recognize the platform guard, serialized hardware queue, desired/manual versus automatic policy distinction, GUI dirty-selection fix, direct RAPL bounds check, and the decision to avoid writes on unverified hardware. The most important additional positive context is that the current dependency mismatch is caught and converted into a structured error before any apply-stage hardware mutation; this limits immediate damage even though the feature is nonfunctional.

## 6. Scorecard

Each cell shows **raw score /10 → weighted points**.

| Dimension | Weight | SOL | TERRA | LUNA |
|---|---:|---:|---:|---:|
| A. Technical correctness | 30% | 8.3 → 24.9 | 7.9 → 23.7 | 9.2 → 27.6 |
| B. Coverage and issue discovery | 20% | 7.6 → 15.2 | 6.8 → 13.6 | 9.0 → 18.0 |
| C. Evidence and verification | 15% | 8.8 → 13.2 | 8.8 → 13.2 | 9.5 → 14.3 |
| D. Severity and priority calibration | 10% | 8.6 → 8.6 | 8.5 → 8.5 | 7.8 → 7.8 |
| E. Architecture and context | 10% | 8.6 → 8.6 | 8.0 → 8.0 | 9.4 → 9.4 |
| F. Fix quality and actionability | 10% | 8.8 → 8.8 | 8.3 → 8.3 | 9.1 → 9.1 |
| G. Clarity and efficiency | 5% | 8.8 → 4.4 | 9.2 → 4.6 | 7.9 → 4.0 |
| **Final weighted score** | **100%** | **83.7** | **79.9** | **90.1** |

Calculation example: LUNA technical correctness contributes `9.2 / 10 × 30 = 27.6` points. Totals use the unrounded weighted values; displayed contributions use one decimal place.

## 7. Per-report assessment

### `LUNA_EVAL.md`

**Strongest aspects:** It builds the most complete independent model of startup, application, delayed enforcement, persistence, auto-switch, and lifecycle. It verifies the actual dependency boundary rather than merely reading the dependency's later apply function. Its Git scope, safe probe, arithmetic reproduction, cross-file evidence, and remediation plan are the strongest of the three.

**Weakest aspects:** It is longer than necessary and separates several manifestations of the same unverified-state problem into individually High findings. It does not inspect the systemd capability boundary deeply enough.

**Most valuable valid finding:** PP-001, the resolved `honor-tools` constructor mismatch.

**Most serious mistake or false positive:** No major false positive. The largest judgment error is severity inflation for PP-005 through PP-008, especially the reconciliation and queue-timeout items.

**Most important missed issue:** Missing `CAP_SYS_RAWIO` in the packaged service.

**Manual verification required:** Targeted rather than wholesale. Recheck packaging/privilege assumptions, downgrade several severities, and add the turbo/max latent behavior. Most core findings can otherwise be acted on.

### `SOL_EVAL.md`

**Strongest aspects:** Excellent signal-to-noise ratio, accurate bit-level analysis, good state-verification reasoning, well-calibrated secondary severities, and concrete tests/fixes. Its low-priority findings remain genuinely useful instead of cosmetic.

**Weakest aspects:** It does not execute the production adapter against the declared dependency and does not trace systemd hardening into the kernel's MSR open requirement. Those are major holes for a report that otherwise claims broad verification.

**Most valuable valid finding:** PP-002, the PL2 enable/time-window encoding defect, closely followed by PP-001/PP-003.

**Most serious mistake or false positive:** No clear false positive; the serious mistake is presenting the PPD conflict as the operative first failure without discovering the earlier constructor exception.

**Most important missed issue:** The critical dependency contract mismatch.

**Manual verification required:** Substantial but focused. Every apply-path conclusion must be rebased on the constructor failure, and packaging privilege must be reviewed. The findings it does contain are mostly safe to retain.

### `TERRA_EVAL.md`

**Strongest aspects:** Best concision, clear prioritization, and the strongest unique deployment finding. It correctly connects the systemd capability bounding set to the upstream x86 MSR driver's `CAP_SYS_RAWIO` check.

**Weakest aspects:** Narrower coverage, no PL2 arithmetic validation, and incomplete dependency-boundary analysis despite inspecting `honor-tools`. PP-006 confuses a latent dependency semantic with current runtime behavior.

**Most valuable valid finding:** PP-002, the missing `CAP_SYS_RAWIO` blocker.

**Most serious mistake or false positive:** PP-006's current failure scenario is misleading. The dependency does force turbo/100% inside `apply_profile()`, but the current adapter raises while constructing `PowerProfile`, so that code is not reached.

**Most important missed issue:** The critical constructor mismatch; the PL2 encoder bug is the next-largest miss.

**Manual verification required:** High. The report is valuable as a focused supplement, especially for deployment, but is not broad enough to serve as the principal review.

## 8. Final ranking and verdict

### 1st — `LUNA_EVAL.md`

LUNA wins because it finds the true current blocker and still covers nearly all major latent defects. Its conclusions are the most auditably tied to the exact checkout, resolved dependency, Git range, and call path. Missing the systemd capability issue prevents an overwhelming score, but does not overturn the ranking.

### 2nd — `SOL_EVAL.md`

SOL is the most efficient and has almost no false-positive noise. It performs excellent bit-level and state-management review. It ranks below LUNA because missing the constructor mismatch means it does not fully understand what the current production adapter actually does. Its omission of `CAP_SYS_RAWIO` is also material.

### 3rd — `TERRA_EVAL.md`

TERRA deserves significant credit for the capability-boundary finding and its concise communication. It ranks third because it misses two deterministic high-impact defects—the dependency constructor and PL2 packing—and partially misstates turbo/max runtime behavior. Its coverage is meaningfully thinner than SOL's.

Explicit answers:

| Question | Verdict |
|---|---|
| Which report found the most real issues? | **LUNA** |
| Which report had the fewest false positives? | **SOL**, narrowly; LUNA has no major fabricated issue but more severity inflation and overlap |
| Which report best understood the architecture? | **LUNA** |
| Which report gave the most actionable fixes? | **LUNA**, with SOL close behind |
| Which report would I trust most for a merge/release decision? | **LUNA**, after adding the systemd/MSR privilege finding and recalibrating secondary severities |
| Which report offers the best signal-to-noise ratio? | **SOL** |
| How close is first place? | Not especially close: LUNA leads SOL by 6.4 points because of the unique current-runtime dependency verification |
| How close are second and third? | Relatively close: SOL leads TERRA by 3.8 points; TERRA's unique capability finding offsets some of its narrower coverage |

## 9. Best combined review

The following is the consolidated, corrected, non-duplicate review that should guide implementation.

### Must fix before merge or release

1. **Repair and pin the `honor-tools` contract.**
   - Require a dependency version whose `PowerProfile` and result schema are actually compatible, or adapt explicitly to 0.1.0.
   - Add an integration/contract test against every supported dependency version.
   - Do not treat importability as compatibility.

2. **Choose one coherent power-manager ownership model.**
   - Do not stop/mask PPD while still calling and requiring `powerprofilesctl`.
   - Prefer integrating with PPD, or remove PPD from the backend contract and implement a fully direct, verified backend.
   - Any takeover must capture and restore prior PPD, `intel_lpmd`, and HWP state on failed startup, shutdown, disable, crash recovery, and uninstall.

3. **Resolve the raw-MSR deployment/security design before relying on it.**
   - The packaged service currently lacks `CAP_SYS_RAWIO` and cannot open the standard x86 MSR device.
   - Decide whether adding that capability is acceptable; account for kernel lockdown, `msr` module/device provisioning, write filtering, and kernel taint.
   - If raw MSR is optional, represent it as an explicit unavailable/partial mechanism rather than silently ignoring failure.

4. **Replace the RAPL encoder with tested field-level code and verify readback.**
   - Correct PL2 enable/time-window placement.
   - Define masks for PL1/PL2 limit, enable, clamp, time-window, lock, and preserved fields.
   - Check exact 8-byte I/O, field overflow, locked registers, and decoded post-write values.

5. **Make profile apply a verified state transition.**
   - Do not return success, persist desired state, set `applied_profile`, select fan curves, or run transition hooks until required mechanisms have settled and verified.
   - If convergence must remain asynchronous, expose `pending`, then publish verified success/partial/failure.
   - Keep desired, attempted, effective, and last verified applied state distinct.

6. **Add a minimum production-adapter test gate.**
   - Dependency constructor/result compatibility.
   - PPD/systemd ownership and restoration.
   - Unit capability/MSR-open behavior.
   - RAPL encode/decode/readback.
   - Delayed false/exception outcomes.
   - No success on missing CPUs/resources.
   - Startup reconciliation and GUI dirty-selection behavior.

### Should fix soon

1. **Make delayed enforcement latest-wins and lifecycle-owned.** Cancel/await prior generations, combine the final hardware phase into one ordered operation, recheck generation before writes, and await all tasks on shutdown.
2. **Define governor/EPP compatibility explicitly.** Reject, normalize, or expose effective combinations; never store/display `performance` while intentionally leaving `powersave` without explanation.
3. **Reconcile complete observed state.** Compare RAPL, governor, EPP, PPD, turbo, and max-performance values; do not infer a custom or complete profile from the PPD label alone.
4. **Build per-mechanism capability results.** Include dependency API, PPD service, systemd operation, RAPL sysfs, EPP/governor files, Intel-pstate controls, MSR device/capability/lockdown, and rollback readiness.
5. **Fix daemon-cleanup deadline and result handling.** Use a coherent bounded transaction, inspect return codes/stderr, avoid the 20-second internal/10-second queue mismatch, and publish degraded health rather than aborting unpredictably.
6. **Fix auto-switch recovery.** Back off structured failures instead of retrying every two seconds; catch exceptional failures inside the loop or restart failed controllers deliberately.
7. **Define persistence transaction semantics.** Return a structured partial result when hardware changes but persistence fails; avoid leaving a newly saved active definition unapplied without explicit state.
8. **Implement or remove turbo/max controls.** After dependency compatibility is fixed, apply and verify the requested values rather than inheriting the dependency's hard-coded turbo-on/100% behavior.

### Optional cleanup or longer-term improvement

1. Use the adapter's injected root or dedicated injected ports for sysfs, MSR, and systemd so all paths are testable without host access.
2. Make EPP rewriting require at least one eligible CPU, check governor writes, compare readback content, and define CPU-hotplug behavior.
3. Use guaranteed descriptor cleanup and validate exact read/write lengths in the MSR helper.
4. Replace raw dictionary result contracts and fail-open `get(..., True)` defaults with typed, required fields.
5. Correct AMD/support documentation and document effective governor behavior, daemon ownership, raw-MSR requirements, kernel taint, persistence, rollback, and recovery.
6. Add focused GUI tests for `_active_combo_dirty`; retain the current fix, which is directionally sound.

**Combined release verdict: unsafe to merge or release until the Must-fix items are resolved and verified.**
