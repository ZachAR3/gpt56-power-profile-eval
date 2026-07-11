# Evaluation Comparison: Power-Profile Overhaul Reviews

## 1. Executive summary

**Best report overall: LUNA.**

**Final ranking:**

1. **LUNA** — 87.0/100
2. **SOL** — 76.0/100
3. **TERRA** — 60.0/100

The gap between first and second is meaningful but not enormous; the gap between second and third is large.

The most important reason for the ranking: LUNA uniquely identified and verified with a direct probe that the installed `honor-tools 0.1.0` `PowerProfile.__init__()` does not accept `turbo_enabled` or `max_perf_pct`, which means every real profile apply fails with a `TypeError` before reaching any hardware. This is the single most fundamental blocking issue in the codebase — the entire power-profile feature is non-functional on real hardware — and neither SOL nor TERRA found it, despite both inspecting the dependency. LUNA also found the most issues overall (14), including several unique findings (queue timeout aborting startup, auto-switch retry-forever, persistence/hardware ordering, reconciliation trusting PPD label).

SOL produced a strong, precise report with excellent analysis of the RAPL MSR encoding bug and two unique findings (EPP empty-CPU success, MSR FD leak), but missed the constructor failure and the CAP_SYS_RAWIO deployment issue.

TERRA uniquely found the CAP_SYS_RAWIO capability-bound issue — a valuable deployment-level finding no other report made — but missed the RAPL encoding bug entirely (a deterministic, high-severity arithmetic defect) and its PP-006 about turbo/max-performance was misleading: it claimed the values are "ignored in apply_profile()" when in reality the `PowerProfile` constructor fails before `apply_profile` is ever called.

No report is unsafe to rely on without re-verification, but TERRA requires the most re-verification due to the misleading PP-006 and the missed RAPL encoding bug. SOL and LUNA are largely reliable, with LUNA requiring the least re-verification.

A cost analysis of the Codex sessions that produced each report is included in Section 10. Excluding wasted sessions (failed runs due to prompt template errors and file-management sessions), LUNA's production run cost $1.20, TERRA's cost $3.04, and SOL's cost $1.29. LUNA had the lowest cost-per-finding at $0.09, while TERRA had the highest at $0.43. The user's workflow had $3.57 of wasted sessions from forgetting to move previous eval files out before starting the next model.

## 2. Repository and change scope

### Branch and commit

- Branch: `main` (tracks `origin/main`, is the default branch)
- Commit reviewed: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f` (`README: document Intel-only compatibility`)
- Working tree: clean except for the three untracked evaluation files

### Comparison base and merge base

All three reports correctly identified that the literal merge base of `main` with `origin/main` is `34d31f9` itself (the reviewed commit), which produces an empty diff and is useless as a behavioral baseline. All three independently chose the root commit `4d8994a` (`Initial commit`) as the defensible functional comparison base. This is correct: the four power-profile commits were committed directly to the default branch, and the root commit is the only defensible semantic baseline.

- Review range: `4d8994a..34d31f9`
- Relevant commits:
  1. `15f4d66` — Fix power profile application: RAPL, EPP, and UI snap-back
  2. `d391bb0` — Clean up power profile code: safety, simplicity, correctness
  3. `7213294` — Guard stop_competing_power_daemons behind platform detection
  4. `34d31f9` — README: document Intel-only compatibility

### Files changed

| File | Insertions | Deletions |
|---|---|---|
| `README.md` | 7 | 0 |
| `honor_control/backend/application.py` | 84 | 1 |
| `honor_control/backend/hardware.py` | 215 | 2 |
| `honor_control/frontend/gui/pages/power.py` | 20 | 4 |

No test files changed in the range.

### Major subsystems inspected

- `ApplicationService` lifecycle, mutation locking, startup reconciliation, auto-switching, snapshots, delayed rewrite scheduling (`application.py`)
- `HonorToolsAdapter`: platform detection, capability probing, `honor-tools` integration, `stop_competing_power_daemons`, `rewrite_epp`, `write_rapl_msr`, sysfs writes (`hardware.py`)
- `HardwareCommandQueue`: serialized worker thread, timeout/poison semantics (`command_queue.py`)
- Service composition and shutdown (`service.py`)
- Power models, validation, config persistence (`core/models.py`, `core/validation.py`, `config_store.py`)
- GUI power page dirty-selection fix (`frontend/gui/pages/power.py`)
- Systemd unit, install/uninstall scripts, documentation
- Installed `honor-tools 0.1.0` source: `honor.config.PowerProfile`, `honor.power.apply_profile`, `honor.power._set_ppd`, `honor.power.get_status`, `honor.power.read_ppd`
- Sibling `../honor-tools` source tree (has a newer `PowerProfile` with `turbo_enabled`/`max_perf_pct`)

### Commands and tests run

| Command | Result |
|---|---|
| `git status`, `git log`, `git diff --stat/numstat/name-status 4d8994a..HEAD` | Confirmed clean tree, 4 changed files, 326 insertions / 7 deletions |
| `git diff --check 4d8994a..HEAD` | Passed (no whitespace errors) |
| `.venv/bin/python -m pytest -q` | 221 passed in 8.58s |
| `.venv/bin/ruff check honor_control tests` | Passed |
| `.venv/bin/ruff check .` | 6 errors, all in pre-existing `Reverse engineering/capture_subscribers_driver.py` |
| `.venv/bin/python -m compileall -q honor_control tests` | Passed |
| `systemd-analyze verify packaging/systemd/honor-control.service` | Passed |
| `bash scripts/smoke-test.sh` | 7 checks passed |
| `bash -n scripts/*.sh` | All passed |
| RAPL encoding arithmetic verification (Python) | Confirmed PL2 enable bit and time window are dropped |
| `PowerProfile.__init__` signature inspection | Confirmed no `turbo_enabled`/`max_perf_pct` parameters |
| Direct adapter probe (`PowerProfile(turbo_enabled=..., max_perf_pct=...)`) | Confirmed `TypeError` before reaching hardware |
| `honor.power.apply_profile` / `_set_ppd` / `get_status` / `read_ppd` source inspection | Confirmed `powerprofilesctl set`/`get` usage and fixed `no_turbo`/`max_perf_pct` writes |

### Limitations and assumptions

- No real MRA-XXX hardware was available. Claims about hardware/driver/firmware behavior are based on code-path analysis, dependency source, kernel source documentation, and arithmetic verification.
- The CAP_SYS_RAWIO finding assumes the standard upstream Linux x86 MSR driver, which requires `CAP_SYS_RAWIO` in `msr_open()`.
- No system service was started, no daemon was stopped/masked, no MSR/sysfs was written, and no system configuration was changed.

## 3. Independent implementation assessment

### How the power-profile system actually works

**Startup:** `ApplicationService.initialize()` loads config, refreshes all domains (including reading PPD status via `honor.power.get_status()`), then calls `stop_competing_power_daemons()` through the hardware queue, and finally calls `_reconcile_power_profile()`.

**Daemon cleanup:** On a positively detected Honor platform, `stop_competing_power_daemons()` runs `systemctl stop` and `systemctl mask` for both `power-profiles-daemon` and `intel_lpmd` (4 sequential subprocess calls, each with a 5-second timeout), then writes `1` to `/sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost` if it exists. No prior state is captured; no restore path exists in shutdown or uninstall.

**Profile application:** `_apply_power_profile()` checks capability, builds a definition dict, and calls `HonorToolsAdapter.apply_power_profile()` through the queue. The adapter constructs an `honor.config.PowerProfile` with `turbo_enabled` and `max_perf_pct` kwargs, injects it into a `Config`, and calls `honor.power.apply_profile()`. The dependency writes RAPL sysfs, calls `powerprofilesctl set`, writes EPP/governor, and writes `no_turbo=0` / `max_perf_pct=100`. The adapter reduces the result to five booleans (`governor_ok`, `epp_ok`, `ppd_ok`, `rapl_ok`, `misc_ok`). If all are true, the application sets `_last_applied_power_profile`, optionally persists, refreshes, schedules a delayed task, and returns success.

**Delayed rewrite:** After 0.5 seconds, `_delayed_power_rewrite()` calls `write_rapl_msr()` (direct MSR 0x610 write) and `rewrite_epp()` (per-CPU sysfs EPP rewrite with governor manipulation) through the queue. Both return booleans; neither is checked. Exceptions are logged.

**Reconciliation:** `_reconcile_power_profile()` compares the persisted desired profile name to the PPD-derived `applied_profile` from the initial snapshot. If they match, it skips reapplication. It does not compare actual RAPL/EPP/governor values.

**Refresh overlay:** `_refresh_power()` uses `self._last_applied_power_profile or pw.applied_profile`, meaning once a profile is marked applied, the in-memory marker overrides the observed PPD profile indefinitely.

### Most important real issues independently found

1. **The `honor-tools` API mismatch is the first and most fundamental failure.** The installed `honor-tools 0.1.0` `PowerProfile.__init__` accepts only `pl1_uw`, `pl2_uw`, `governor`, `epp`, `ppd_profile`. The adapter passes `turbo_enabled` and `max_perf_pct`, causing a `TypeError` that is caught and returned as `{"error": "..."}`. Every real profile apply — manual, startup reconciliation, and auto-switch — fails before reaching hardware. This makes all other hardware-path issues (PPD masking, CAP_SYS_RAWIO, RAPL encoding) moot in the current code, though they would manifest if the constructor were fixed.

2. **PPD masking is a persistent, unowned system-state change.** The service masks `power-profiles-daemon` and `intel_lpmd` at startup with no capture, rollback, shutdown restore, or uninstall restore. The uninstall script (`scripts/uninstall-local.sh`) does not unmask either unit. This is a host-level side effect that persists after the service stops or is removed.

3. **The RAPL MSR encoder drops PL2 enable and time-window bits.** Verified arithmetically: `hi` is built with absolute bit positions (`1 << 47`, `tw2 << 49`) and then shifted left by 32, placing those bits above bit 63 where the `& 0xFFFFFFFFFFFFFFFF` mask discards them. PL1 fields are correct; PL2 power units are correct; PL2 enable and time window are zeroed.

4. **The systemd service lacks CAP_SYS_RAWIO.** `CapabilityBoundingSet=CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH` does not include `CAP_SYS_RAWIO`, which the standard Linux MSR driver requires to open `/dev/cpu/0/msr`. The MSR write would fail with `EPERM` in the deployed service.

5. **Success is returned before the decisive delayed enforcement.** The delayed task's boolean results are discarded; no post-settle verification occurs; `_last_applied_power_profile` overrides observed state.

6. **The queue timeout can abort startup.** `stop_competing_power_daemons` does up to 4 sequential `systemctl` calls (each 5s timeout = 20s worst case) through the queue's default 10s timeout. `initialize()` does not catch `CommandTimeoutError`.

7. **Failed auto-switch applies retry forever every 2 seconds** with no backoff or latching.

8. **Startup reconciliation trusts the PPD label** rather than comparing actual RAPL/EPP/governor values to the desired definition.

## 4. Finding-by-finding verification

### 4.1 SOL findings

| Finding | Classification | Severity appropriate? | Evidence sufficient? | Notes |
|---|---|---|---|---|
| **PP-001** PPD masking breaks apply + no restore | Correct but incomplete | Critical — appropriate | Yes — cites code lines, dependency source, uninstall script | Correctly identifies the design contradiction and persistent state change. However, does not mention that the constructor failure (LUNA PP-001) prevents `powerprofilesctl set` from ever being called, making the "apply fails because PPD is masked" failure mode moot in the current code. The persistent masking is still real. |
| **PP-002** RAPL MSR encoding drops PL2 enable/time-window | Correct | High — appropriate | Yes — precise bit-level analysis, line references | Verified arithmetically. The analysis is exactly correct: `hi` uses absolute positions then is shifted by 32, dropping bits above 63. |
| **PP-003** Success before delayed enforcement, failures discarded | Correct | High — appropriate | Yes — traces `_apply_power_profile` and `_delayed_power_rewrite` | Correctly identifies that boolean results are ignored, no post-settle verification, and `_last_applied_power_profile` overrides observation. |
| **PP-004** Performance governor → powersave while state claims applied | Correct | High — slightly high; Medium may be more appropriate | Yes — cites `rewrite_epp` lines 950-958 | The semantic mismatch is real. The code intentionally leaves `powersave` for `performance` governor as an Intel-pstate quirk. Whether this is High or Medium depends on whether one considers it a deliberate tradeoff or a contract violation. |
| **PP-005** Delayed rewrites not superseded | Correct | Medium — appropriate | Yes — traces `_pending_power_task` lifecycle | Correctly identifies that older tasks are not cancelled and the queue serializes but doesn't prevent stale writes. |
| **PP-006** Capability probing insufficient | Correct | Medium — appropriate | Yes — cites `get_power_capability` and docs | Correctly identifies that only honor-tools import, platform match, and `powerprofilesctl` binary are checked. Does not specifically identify the CAP_SYS_RAWIO bounding-set issue (TERRA PP-002). |
| **PP-007** EPP rewrite returns success without CPUs | Correct | Medium — appropriate | Yes — cites `cpu_dirs` glob and `all_ok` logic | Unique finding. If `cpu_dirs` is empty, `all_ok` stays `True`. Also notes that governor write results are ignored and read-back content is discarded. |
| **PP-008** MSR FD leak + short I/O not validated | Correct | Low — appropriate | Yes — traces `os.open`/`os.close` pairs and `struct.error` | Unique finding. `struct.error` is not `OSError` and would propagate unhandled. FDs leak on intermediate errors. |
| **PP-009** Documentation inaccurate | Correct | Low — appropriate | Yes — cites README and `docs/hardware-support.md` | Correctly identifies AMD "sysfs-only EPP" claim vs. actual unsupported behavior, and "every mechanism is checked separately" vs. actual probing. |

**SOL missed:**
- The `honor-tools` constructor API mismatch (the most critical blocking issue)
- The CAP_SYS_RAWIO deployment issue
- The queue timeout / startup abort issue
- The auto-switch retry-forever issue
- The persistence/hardware ordering issue
- The reconciliation trusting PPD label issue
- The injectable root bypass issue

### 4.2 TERRA findings

| Finding | Classification | Severity appropriate? | Evidence sufficient? | Notes |
|---|---|---|---|---|
| **PP-001** Startup masks daemon every profile application requires | Correct but incomplete | Critical — appropriate | Yes — cites code lines, dependency source | Same core issue as SOL PP-001 / LUNA PP-002. Also does not mention the constructor failure that makes the `powerprofilesctl` failure moot. |
| **PP-002** Service lacks CAP_SYS_RAWIO for MSR path | Correct | High — appropriate | Yes — cites systemd unit, kernel driver requirement | **Unique and valuable finding.** No other report specifically identified the capability bounding set issue. Correctly notes that `write_rapl_msr` catches `OSError` and returns `False`, but the delayed caller discards it. |
| **PP-003** Final RAPL/EPP outcome not verified | Correct | High — appropriate | Yes — traces `_apply_power_profile` and `_delayed_power_rewrite` | Same core issue as SOL PP-003 / LUNA PP-004. Correctly identifies that `_last_applied_power_profile` overrides observation. |
| **PP-004** Rapid profile changes apply obsolete delayed rewrite | Correct | Medium — appropriate | Yes — traces `_pending_power_task` | Same core issue as SOL PP-005 / LUNA PP-008. |
| **PP-005** Performance governor silently changed to powersave | Correct | Medium — appropriate (lower than SOL's High) | Yes — cites `rewrite_epp` lines | Same core issue as SOL PP-004 / LUNA PP-005. Medium is arguably more appropriate than SOL's High since it's a deliberate Intel-pstate tradeoff. |
| **PP-006** Turbo/max-performance persist but not applied | Partially correct / misleading | Medium — moot in practice | Insufficient — did not test the actual call path | **TERRA's most serious mistake.** Claims "Installed honor-tools 0.1.0 ignores both in `apply_profile()`" and implies the apply succeeds with fixed values. In reality, the `PowerProfile` constructor fails with `TypeError` before `apply_profile` is ever called. TERRA inspected `apply_profile`'s source and saw the fixed writes, but missed that the constructor call before it fails. If TERRA had run a direct adapter probe (as LUNA did), it would have discovered the constructor failure. |
| **PP-007** AMD compatibility statement conflicts with implementation | Correct | Low — appropriate | Yes — cites README and platform detection | Same core issue as SOL PP-009 / LUNA PP-014. |

**TERRA missed:**
- The RAPL MSR encoding bug entirely (a deterministic, high-severity arithmetic defect that SOL and LUNA both found)
- The `honor-tools` constructor API mismatch (the most critical blocking issue)
- The queue timeout / startup abort issue
- The auto-switch retry-forever issue
- The persistence/hardware ordering issue
- The reconciliation trusting PPD label issue
- The EPP empty-CPU success issue
- The MSR FD leak issue
- The injectable root bypass issue

### 4.3 LUNA findings

| Finding | Classification | Severity appropriate? | Evidence sufficient? | Notes |
|---|---|---|---|---|
| **PP-001** Resolved `honor-tools` API makes every real apply fail | Correct | Critical — appropriate | **Excellent** — direct adapter probe returning the `TypeError` | **Most valuable finding across all three reports.** Uniquely identified and verified with a direct probe. Correctly attributes to root commit via `git blame`. Also inspected the sibling `../honor-tools` source tree to understand the API discrepancy. |
| **PP-002** Startup masks system power managers, never restores | Correct | Critical — appropriate | Yes — cites code lines, dependency source, uninstall script | Same core issue as SOL PP-001 / TERRA PP-001. |
| **PP-003** RAPL encoder drops PL2 enable and time-window bits | Correct | High — appropriate | Yes — arithmetic verification, code snippet | Same core issue as SOL PP-002. Verified with a pure arithmetic check returning `pl2_enable=0` and `tw2_written=0`. |
| **PP-004** Apply success before delayed enforcement, failures lost | Correct | High — appropriate | Yes — traces `_apply_power_profile` and `_delayed_power_rewrite` | Same core issue as SOL PP-003 / TERRA PP-003. |
| **PP-005** Performance profile ends with powersave | Correct | High — slightly high; Medium may be more appropriate | Yes — cites `rewrite_epp` and profile definitions | Same core issue as SOL PP-004 / TERRA PP-005. |
| **PP-006** Startup reconciliation trusts PPD label | Correct | High — appropriate | Yes — traces `_reconcile_power_profile` and `read_power` | **Unique finding.** Correctly identifies that reconciliation only compares the PPD-derived profile name, not actual RAPL/EPP/governor values. Custom profiles sharing a PPD mode with built-ins are even less identifiable. |
| **PP-007** Daemon cleanup can exceed queue deadline and abort startup | Correct | High — slightly high; Medium may be more appropriate | Yes — calculates 20s worst case vs 10s timeout, traces uncaught exception | **Unique finding.** Correctly identifies that 4 × 5s = 20s exceeds the 10s queue timeout, `initialize()` doesn't catch `CommandTimeoutError`, and the worker thread continues after the async timeout. High is defensible but requires systemd to be slow; Medium is also reasonable. |
| **PP-008** Fire-and-forget rewrites not generation-safe | Correct | High — slightly high; Medium may be more appropriate | Yes — traces `_pending_power_task` lifecycle | Same core issue as SOL PP-005 / TERRA PP-004. LUNA provides more detail about the A/B interleaving scenario. High is defensible but the race window is 0.5s; Medium is also reasonable. |
| **PP-009** Capability probing much weaker than mechanisms | Correct | Medium — appropriate | Yes — cites `get_power_capability` and docs | Same core issue as SOL PP-006. |
| **PP-010** Failed auto-switch applies retry forever every 2 seconds | Correct | Medium — appropriate | Yes — traces `_auto_switch_loop` logic | **Unique finding.** Correctly identifies that `last_ac`/`last_policy` only update on success, causing indefinite retries. |
| **PP-011** Hardware success and persistence failure leave contradictory state | Correct | Medium — appropriate | Yes — traces `_apply_power_profile` and `save_power_profile` ordering | **Unique finding.** Correctly identifies both orderings: hardware-before-persist in `_apply_power_profile` and persist-before-hardware in `save_power_profile`. |
| **PP-012** New high-risk paths have no meaningful production-adapter tests | Correct | Medium — appropriate | Yes — cites test files and `FakeHardware` limitations | All three reports identify the test gap; LUNA is the most specific about what's missing. |
| **PP-013** New power I/O bypasses adapter's injectable root | Correct | Low — appropriate | Yes — cites hard-coded paths vs. `self._root` | **Unique finding.** Correctly identifies that `rewrite_epp`, `write_rapl_msr`, and `stop_competing_power_daemons` hard-code paths instead of using `self._root`. |
| **PP-014** AMD compatibility statement does not match behavior | Correct | Low — appropriate | Yes — cites README and platform detection | Same core issue as SOL PP-009 / TERRA PP-007. |

**LUNA missed:**
- The CAP_SYS_RAWIO deployment issue (TERRA PP-002)
- The MSR FD leak as a separate finding (SOL PP-008; LUNA mentions it in test suggestions but not as a finding)
- The EPP empty-CPU success as a separate finding (SOL PP-007; LUNA mentions the injectable root bypass which is related)

## 5. Missed issues and missed context

### Issues missed by each individual report

**SOL missed:**
- `honor-tools` constructor API mismatch (Critical) — the most fundamental blocking issue; verified by direct probe
- CAP_SYS_RAWIO bounding set (High) — the deployed service cannot open `/dev/cpu/0/msr`
- Queue timeout aborting startup (High/Medium) — 20s worst case vs 10s timeout
- Auto-switch retry-forever (Medium) — no backoff or latching
- Persistence/hardware ordering (Medium) — hardware-before-persist and persist-before-hardware inversions
- Reconciliation trusting PPD label (High) — only compares names, not actual values
- Injectable root bypass (Low) — hard-coded paths in new code

**TERRA missed:**
- RAPL MSR encoding bug (High) — a deterministic arithmetic defect; SOL and LUNA both found it
- `honor-tools` constructor API mismatch (Critical) — the most fundamental blocking issue
- Queue timeout aborting startup (High/Medium)
- Auto-switch retry-forever (Medium)
- Persistence/hardware ordering (Medium)
- Reconciliation trusting PPD label (High)
- EPP empty-CPU success (Medium)
- MSR FD leak (Low)
- Injectable root bypass (Low)

**LUNA missed:**
- CAP_SYS_RAWIO bounding set (High) — the deployed service cannot open `/dev/cpu/0/msr`
- MSR FD leak as a separate finding (Low) — mentioned in test suggestions but not as a finding
- EPP empty-CPU success as a separate finding (Medium) — partially covered by PP-013

### Issues missed by all three

- **The interaction between the constructor failure and the PPD masking failure mode.** SOL and TERRA claim that masking PPD makes `powerprofilesctl set` fail, causing partial applies. This is technically correct about the code path, but in practice the constructor `TypeError` fails first, so `powerprofilesctl set` is never called. The PPD masking is still a real problem (persistent state change with no restore), but the specific "apply fails because PPD is masked" failure mode described by SOL and TERRA is not the actual failure mode in the current code. No report explicitly noted this interaction.

- **The `ExecStopPost` hook only restores fan auto, not power state.** The service file has `ExecStopPost=-/usr/bin/honor-control-service --restore-fan-auto`, which restores fan state on stop but does not unmask PPD/`intel_lpmd` or restore HWP dynamic boost. SOL and LUNA mention that shutdown doesn't restore power state, but neither specifically notes that the `ExecStopPost` hook exists for fan restoration but not for power state, which would be the natural place to add it.

### Relevant architectural/historical context not fully considered

- **The sibling `../honor-tools` source tree has a newer `PowerProfile` with `turbo_enabled`/`max_perf_pct`.** Only LUNA inspected this. This suggests the adapter was written against a newer API than the declared `honor-tools>=0.1,<0.2` range resolves to. This is important context for understanding why the constructor call fails.

- **The `OVERHAUL_PLAN.md` rule 8 says "Do not duplicate `honor-tools` algorithms."** The delayed RAPL/EPP rewrite duplicates the dependency's RAPL/EPP writes with different semantics (e.g., leaving `powersave` governor for `performance` profiles). This is an architectural tension that all three reports touch on but could frame more explicitly as a violation of the project's own design rules.

### False assumptions shared by multiple reports

- SOL and TERRA both assume that the PPD masking causes `powerprofilesctl set` to fail during apply. While this would be true if the constructor bug were fixed, in the current code the constructor failure prevents `apply_profile` from being called at all. The PPD masking is still a real issue (persistent state change), but the described failure mode is not the actual one.

### Useful positive observations omitted by all three

- The `ExecStopPost` hook for fan restoration shows the project has a pattern for shutdown restoration that could be extended to power state. None of the reports noted this existing pattern as a potential foundation for fixing the PPD restore gap.
- The `FakeHardware` implementation correctly models the protocol shape of the new methods, which is useful for future test development even though it doesn't model failure semantics.

## 6. Scorecard

| Dimension | Weight | SOL | TERRA | LUNA |
|---|---|---|---|---|
| A. Technical correctness | 30% | 8 (2.4) | 6 (1.8) | 9 (2.7) |
| B. Coverage and issue discovery | 20% | 6 (1.2) | 5 (1.0) | 9 (1.8) |
| C. Evidence and verification | 15% | 8 (1.2) | 6 (0.9) | 9 (1.35) |
| D. Severity and priority calibration | 10% | 8 (0.8) | 6 (0.6) | 8 (0.8) |
| E. Architecture and context | 10% | 8 (0.8) | 7 (0.7) | 9 (0.9) |
| F. Fix quality and actionability | 10% | 8 (0.8) | 6 (0.6) | 8 (0.8) |
| G. Clarity and efficiency | 5% | 8 (0.4) | 8 (0.4) | 7 (0.35) |
| **Final weighted score** | **100%** | **76.0** | **60.0** | **87.0** |

### Score rationale

**SOL — Technical correctness (8):** Precise analysis of all 9 findings. RAPL encoding analysis is exactly correct. Missed the constructor failure and CAP_SYS_RAWIO. The PPD masking finding doesn't note the constructor failure makes the described failure mode moot.

**SOL — Coverage (6):** Found 9 findings including 2 unique (EPP empty-CPU, MSR FD leak). Missed 7 important issues including 2 critical/high (constructor failure, CAP_SYS_RAWIO, queue timeout, reconciliation trust, auto-switch retry, persistence ordering, injectable root).

**TERRA — Technical correctness (6):** Correctly found CAP_SYS_RAWIO (unique and valuable). But missed the RAPL encoding bug entirely, and PP-006 is misleading (claims values are "ignored in apply_profile" when the constructor fails first). The PP-006 error suggests TERRA inspected the dependency source but didn't test the actual call path.

**TERRA — Coverage (5):** Found 7 findings, fewest of any report. Missed the RAPL encoding bug (deterministic, high severity), the constructor failure (critical), and 6 other issues. Uniquely found CAP_SYS_RAWIO.

**LUNA — Technical correctness (9):** Found the constructor failure (most critical) and verified it with a direct probe. RAPL encoding analysis correct. Found 14 issues total. Missed CAP_SYS_RAWIO. No misleading findings.

**LUNA — Coverage (9):** Found 14 issues, most of any report. 6 unique findings (constructor failure, reconciliation trust, queue timeout, auto-switch retry, persistence ordering, injectable root). Missed CAP_SYS_RAWIO, FD leak as separate finding, EPP empty-CPU as separate finding.

**LUNA — Evidence (9):** Best evidence. Direct adapter probe returning the `TypeError`. Arithmetic verification of RAPL encoding. Read-only system checks (PPD active, MSR present). Inspected sibling source tree. All claims are auditable.

**TERRA — Evidence (6):** Good evidence for CAP_SYS_RAWIO (kernel source reference). But PP-006 shows insufficient verification — TERRA inspected `apply_profile` source but didn't test the actual call path, missing the constructor failure that a direct probe would have revealed.

## 7. Per-report assessment

### SOL

**Strongest aspects:** Precise, well-structured analysis with excellent bit-level RAPL encoding verification. The most disciplined severity calibration. Strong architectural assessment with a concrete 6-point refactor plan. Two unique findings (EPP empty-CPU success, MSR FD leak/`struct.error`).

**Weakest aspects:** Missed the most fundamental blocking issue (constructor API mismatch) despite inspecting the dependency. Missed the CAP_SYS_RAWIO deployment issue. The PPD masking finding doesn't note that the constructor failure makes the described `powerprofilesctl` failure mode moot.

**Most valuable valid finding:** PP-002 (RAPL MSR encoding) — precise, deterministic, verified, with a concrete fix.

**Most serious mistake/false positive:** No false positives, but the most serious miss is the constructor failure. SOL inspected `honor-tools` and confirmed `_set_ppd()` calls `powerprofilesctl set`, but didn't test the adapter's `apply_power_profile` end-to-end, which would have revealed the `TypeError`.

**Most important missed issue:** The `honor-tools` constructor API mismatch (LUNA PP-001).

**Manual verification required:** Moderate. SOL's 9 findings are all correct and well-supported. The main gap is what it missed, not what it got wrong. Acting on SOL's findings would fix real issues but would not make the feature functional (the constructor failure would remain).

### TERRA

**Strongest aspects:** Uniquely found the CAP_SYS_RAWIO deployment issue — a valuable finding that requires understanding both the systemd capability model and the kernel MSR driver's permission check. Concise and well-organized. Good architectural assessment.

**Weakest aspects:** Missed the RAPL encoding bug entirely — a deterministic arithmetic defect that SOL and LUNA both found. PP-006 is misleading: it claims `turbo_enabled`/`max_perf_pct` are "ignored in `apply_profile()`" when the `PowerProfile` constructor fails before `apply_profile` is called. This suggests TERRA inspected the dependency source but didn't test the actual call path.

**Most valuable valid finding:** PP-002 (CAP_SYS_RAWIO) — unique, specific, deployment-level, with a clear fix.

**Most serious mistake/false positive:** PP-006 is misleading. TERRA claims the apply succeeds with fixed `no_turbo=0`/`max_perf_pct=100` values, when in reality the apply fails entirely with a `TypeError`. This is not a false positive (the underlying observation about `apply_profile` writing fixed values is correct), but the framing implies a working apply path that doesn't exist. More importantly, TERRA was close to finding the constructor failure but stopped at inspecting `apply_profile` without testing the call path.

**Most important missed issue:** The RAPL MSR encoding bug (SOL PP-002 / LUNA PP-003) — a deterministic, high-severity arithmetic defect.

**Manual verification required:** Substantial. PP-006 needs re-evaluation. The missing RAPL encoding finding means TERRA's coverage of the hardware path is incomplete. TERRA's valid findings (PP-001, PP-002, PP-003, PP-004, PP-005, PP-007) are correct and actionable, but the report cannot be relied upon alone.

### LUNA

**Strongest aspects:** Found the most issues (14), including the most critical one (constructor failure). Verified the constructor failure with a direct adapter probe — the kind of evidence that makes a finding immediately actionable. Inspected the sibling `../honor-tools` source tree to understand the API discrepancy. Six unique findings. Best evidence and verification overall.

**Weakest aspects:** Missed the CAP_SYS_RAWIO deployment issue. Some findings could be more concise (PP-008 and PP-012 overlap on delayed-task issues). The report is long (1082 lines), which slightly reduces efficiency. A few severity ratings are slightly high (PP-007 queue timeout as High, PP-008 delayed tasks as High).

**Most valuable valid finding:** PP-001 (constructor API mismatch) — the single most important finding across all three reports. It is the first failure that blocks all real profile applies, and it was verified with a direct probe.

**Most serious mistake/false positive:** No false positives. The most serious miss is the CAP_SYS_RAWIO issue, which LUNA hints at (PP-004 mentions "a permissions error on `/dev/cpu/0/msr`") but doesn't specifically identify as a capability bounding set problem.

**Most important missed issue:** CAP_SYS_RAWIO bounding set (TERRA PP-002).

**Manual verification required:** Least of the three. LUNA's findings are well-supported with direct evidence. The main gap is the CAP_SYS_RAWIO issue, which would need to be added. Acting on LUNA's findings would address the most critical issues and make the feature potentially functional (after fixing the constructor, PPD masking, RAPL encoding, and CAP_SYS_RAWIO).

## 8. Final ranking and verdict

### 1st place: LUNA (87.0/100)

LUNA found the most real issues (14), had the fewest false positives (zero), best understood the architecture (inspected the sibling source tree, traced the full dependency contract), and gave the most actionable fixes (direct probe evidence for the constructor failure). LUNA's PP-001 is the single most important finding across all three reports: it is the first failure that blocks all real profile applies, and it was verified with a direct adapter probe returning the actual `TypeError`. No other report found this.

### 2nd place: SOL (76.0/100)

SOL produced a precise, well-structured report with excellent RAPL encoding analysis and two unique findings (EPP empty-CPU, MSR FD leak). SOL's severity calibration is the most disciplined. However, SOL missed the constructor failure (the most critical blocking issue) and the CAP_SYS_RAWIO deployment issue, and its PPD masking finding doesn't note that the constructor failure makes the described failure mode moot.

### 3rd place: TERRA (60.0/100)

TERRA uniquely found the CAP_SYS_RAWIO deployment issue — a valuable finding no other report made. However, TERRA missed the RAPL encoding bug entirely (a deterministic, high-severity arithmetic defect that both other reports found), and its PP-006 is misleading (claims values are "ignored in `apply_profile`" when the constructor fails first). TERRA found the fewest issues (7) and had the weakest coverage.

### Decisive factors

- **Which report found the most real issues?** LUNA (14), followed by SOL (9), then TERRA (7).
- **Which report had the fewest false positives?** LUNA (zero), followed by SOL (zero), then TERRA (one misleading finding, PP-006).
- **Which report best understood the architecture?** LUNA, which inspected the sibling source tree, traced the full dependency contract, and identified the split-ownership problem most precisely.
- **Which report gave the most actionable fixes?** LUNA, whose direct adapter probe for PP-001 provides immediately actionable evidence, and whose 14 findings cover the most ground.
- **Which report would you trust most for a merge or release decision?** LUNA, because it found the constructor failure that makes the entire feature non-functional, plus the most additional issues.
- **Which report offers the best signal-to-noise ratio?** SOL, which found 9 issues all correct and well-supported, with no misleading findings. LUNA has more findings but also more length and some overlap.

## 9. Best combined review

Consolidated from all three reports plus independent verification, corrected for severity and context.

### Must fix before merge or release

1. **Fix the `honor-tools` constructor API mismatch.** The installed `honor-tools 0.1.0` `PowerProfile.__init__` does not accept `turbo_enabled` or `max_perf_pct`. Every real profile apply fails with `TypeError` before reaching hardware. Either pin/require a compatible `honor-tools` version that includes these fields, or adapt the adapter to the older API. Add an integration test using the declared dependency. *(LUNA PP-001)*

2. **Remove or fully own/reverse the PPD and `intel_lpmd` masking.** The service masks both units at startup with no capture, rollback, shutdown restore, or uninstall restore. The uninstall script does not unmask them. Either keep PPD running and integrate with it, or implement a complete ownership lifecycle: capture prior state, use reversible runtime mechanisms, restore on shutdown/uninstall/failure, and gate on complete capability. At minimum, remove startup masking until that lifecycle exists. *(SOL PP-001, TERRA PP-001, LUNA PP-002)*

3. **Fix the RAPL MSR encoding.** PL2 enable bit (bit 47) and PL2 time window (bits 49-55) are dropped because `hi` is built with absolute positions and then shifted left by 32, placing them above bit 63 where the 64-bit mask discards them. Build the 64-bit register with global positions exactly once. Add table-driven pure encode/decode tests. *(SOL PP-002, LUNA PP-003)*

4. **Add CAP_SYS_RAWIO or remove the raw-MSR path.** The systemd service's `CapabilityBoundingSet` does not include `CAP_SYS_RAWIO`, which the standard Linux MSR driver requires to open `/dev/cpu/0/msr`. Either add the narrowly justified capability after security review, or remove the raw-MSR path from the standard service. Make raw-MSR support a separately probed optional mechanism. *(TERRA PP-002)*

5. **Do not report/persist success before delayed enforcement is verified.** The delayed task's boolean results are discarded; no post-settle verification occurs; `_last_applied_power_profile` overrides observed state. Await the required correction, check boolean results, read back and decode RAPL/governor/EPP, and classify full/partial/failure before marking applied or running hooks. *(SOL PP-003, TERRA PP-003, LUNA PP-004)*

6. **Make delayed rewrites generation-safe.** Older tasks are not cancelled when a newer apply overwrites `_pending_power_task`. Maintain a monotonically increasing apply generation; cancel and await the prior correction before a newer apply; recheck generation before each write. Cancel and await all owned tasks on shutdown. *(SOL PP-005, TERRA PP-004, LUNA PP-008)*

7. **Fix the queue timeout / startup abort issue.** `stop_competing_power_daemons` does up to 4 sequential `systemctl` calls (each 5s timeout = 20s worst case) through the queue's default 10s timeout. `initialize()` does not catch `CommandTimeoutError`. Use an explicit overall deadline longer than the maximum, or a dedicated reversible systemd ownership component. Catch cleanup failure during startup and publish degraded health. *(LUNA PP-007)*

8. **Add deterministic tests for the new behavior.** The current fake-only happy path is not a sufficient merge gate. Add: dependency compatibility test, RAPL encode/decode tests, systemd ownership/restore tests, delayed-failure tests, concurrency/cancellation tests, capability matrix tests, and GUI active-combo dirty-state tests. *(All three reports)*

### Should fix soon

1. **Resolve the performance governor → powersave semantic mismatch.** The delayed EPP rewrite leaves `powersave` governor for `performance` profiles while the profile definition and UI claim `performance`. Reject or normalize incompatible governor/EPP combinations at validation time, or model the actual effective governor. *(SOL PP-004, TERRA PP-005, LUNA PP-005)*

2. **Make startup reconciliation compare actual state, not just the PPD label.** Reconciliation only compares the PPD-derived profile name. If RAPL/EPP/governor were overwritten but PPD still reports the matching name, reconciliation is skipped. Compare the complete desired definition to per-mechanism observed values, or conservatively reapply. *(LUNA PP-006)*

3. **Expand capability probing.** Only honor-tools import, platform match, and `powerprofilesctl` binary are checked. Add non-mutating, per-mechanism probes for MSR device, cpufreq/governor/EPP files, Intel pstate controls, systemd units, and effective service capability. *(SOL PP-006, LUNA PP-009)*

4. **Fix EPP rewrite to handle empty CPU sets and verify read-back.** If `cpu_dirs` is empty, `all_ok` stays `True`. Governor write results are ignored. Read-back content is discarded. Require at least one eligible CPU, check governor results, compare read-back to requested value. *(SOL PP-007)*

5. **Fix MSR FD leak and short I/O handling.** FDs are not closed on intermediate errors. `struct.error` is not caught (not an `OSError`). `os.write` length is not checked. Use context-managed descriptors, require exactly 8 bytes, convert malformed I/O into structured failure. *(SOL PP-008)*

6. **Fix auto-switch retry-forever behavior.** Failed applies retry every 2 seconds with no backoff or latching. Separate source-event detection from apply retry state; record the failed transition, back off, and retry only on a new stable source event. *(LUNA PP-010)*

7. **Fix persistence/hardware ordering.** In `_apply_power_profile`, hardware is applied before persistence; if persistence fails, the exception propagates without rollback. In `save_power_profile`, the definition is persisted before re-application; if the apply fails, the new definition is already durable. Define an explicit transaction policy. *(LUNA PP-011)*

8. **Correct documentation.** README claims AMD "sysfs-only EPP" but code returns unsupported. `docs/hardware-support.md` claims "every mechanism is checked separately" but capability probing checks only three things. Document the actual platform gate, required resources, daemon side effects, and effective governor semantics. *(SOL PP-009, TERRA PP-007, LUNA PP-014)*

### Optional cleanup or longer-term improvement

1. **Use injectable root for new power I/O paths.** `rewrite_epp`, `write_rapl_msr`, and `stop_competing_power_daemons` hard-code `/sys/devices/system/cpu`, `/dev/cpu/0/msr`, and absolute sysfs paths instead of using `self._root`. This makes safe unit testing unnecessarily difficult. *(LUNA PP-013)*

2. **Extract a typed `PowerApplyResult` and `PowerApplyPlan`.** Define a typed result containing per-mechanism write status, settled observations, and effective profile. Let one layer execute the complete ordered plan. Remove `result.get(..., True)` defaults and asserted-profile overlay from observed state. *(All three reports, architecture sections)*

3. **Add diagnostics for applied-vs-observed mismatch, last apply generation, and external-manager ownership.** *(All three reports)*

4. **Pin or formally adapt to a tested `honor-tools` behavior/API.** Avoid relying on timing and untyped dictionaries across the whole `<0.2` range. *(SOL, LUNA)*

5. **Make repository-wide lint scope explicit** (exclude archival reverse-engineering scripts or clean them separately) and ensure the development environment actually installs test/build tools. *(SOL)*

## 10. Cost and token-usage analysis

### Methodology

I inspected the Codex session logs in `~/.codex/archived_sessions/` and `~/.codex/sessions/2026/07/11/` to find the sessions that produced each report. Each session's `event_msg` entries contain `total_token_usage` with `input_tokens`, `cached_input_tokens`, `output_tokens`, and `reasoning_output_tokens`. I used the final cumulative totals from each session.

API pricing was taken from the [OpenAI API pricing page](https://platform.openai.com/docs/pricing) (Standard tier, per 1M tokens, retrieved 2026-07-12):

| Model | Input | Cached input | Output |
|---|---|---|---|
| `gpt-5.6-sol` | $5.00 | $0.50 | $30.00 |
| `gpt-5.6-terra` | $2.50 | $0.25 | $15.00 |
| `gpt-5.6-luna` | $1.00 | $0.10 | $6.00 |

Cost = (non-cached input / 1M × input rate) + (cached input / 1M × cached rate) + (output / 1M × output rate). Output tokens include reasoning tokens.

### Session timeline and classification

Seven sessions on 2026-07-11 were relevant. I verified which sessions produced the final report files by comparing the patch titles against the on-disk files:

- Final `LUNA_EVAL.md` title: `# LUNA power-profile overhaul evaluation` — matches the 20:08 session, not the 18:17 session (`# LUNA Evaluation — Honor Control power-profile overhaul`).
- Final `TERRA_EVAL.md` title: `# TERRA engineering evaluation — power-profile overhaul` — matches the 21:52 session.
- Final `SOL_EVAL.md` title: `# Power-profile overhaul engineering review` — matches the 22:55 session.

The user's workflow had several failed/wasted sessions caused by forgetting to move the previous eval file out before starting the next model, or by prompt template errors (wrong filename in the prompt). These are excluded from production costs.

| Time | Model | Report | Classification | Input | Cached | Output | Cost |
|---|---|---|---|---|---|---|---|
| 18:17 | `gpt-5.6-luna` | LUNA | **Wasted** — first LUNA run; output overwritten by 20:08 re-run | 14,141,940 | 13,787,648 | 62,859 | $2.11 |
| 19:34 | `gpt-5.6-terra` | TERRA | **Wasted** — prompt said "LUNA_EVAL.md" (not updated); terra patched the wrong file | 2,405,517 | 2,251,520 | 30,554 | $1.41 |
| 20:08 | `gpt-5.6-luna` | LUNA | **Production** — re-ran LUNA to regenerate file corrupted by 19:34; produced final `LUNA_EVAL.md` | 6,137,618 | 5,853,440 | 55,643 | $1.20 |
| 21:06 | `gpt-5.6-luna` | — | **File management** — moved `LUNA_EVAL.md` to parent dir | 74,438 | 50,944 | 556 | $0.03 |
| 21:52 | `gpt-5.6-terra` | TERRA | **Production** — produced final `TERRA_EVAL.md` | 7,442,463 | 7,195,392 | 41,529 | $3.04 |
| 22:53 | `gpt-5.6-luna` | — | **File management** — moved `TERRA_EVAL.md` to parent dir | 73,129 | 62,976 | 606 | $0.02 |
| 22:55 | `gpt-5.6-sol` | SOL | **Production** — produced final `SOL_EVAL.md` (wrote to `TERRA_EVAL.md` due to prompt template error; user renamed) | 949,232 | 857,856 | 13,464 | $1.29 |

### Notes on session anomalies

- **18:17 (LUNA, wasted, $2.11):** The first LUNA run produced a report titled `# LUNA Evaluation — Honor Control power-profile overhaul`. This file was later overwritten by the 20:08 re-run (titled `# LUNA power-profile overhaul evaluation`), so its output did not contribute to the final report. The 14.1M input tokens reflect a full investigation, but the output was discarded.
- **19:34 (TERRA, wasted, $1.41):** The prompt template contained a contradiction: "deliverable is `LUNA_EVAL.md`" (not updated from the previous run) vs. "Create or replace only `TERRA_EVAL.md`". The terra model followed the first instruction and patched `LUNA_EVAL.md`, corrupting it. This forced the 20:08 LUNA re-run.
- **22:55 (SOL):** The prompt said "deliverable is `SOL_EVAL.md`" but also "Create or replace only `TERRA_EVAL.md`" (template not fully updated). The sol model wrote to `TERRA_EVAL.md`. The user manually renamed the file to `SOL_EVAL.md` afterward. The content is correct; only the filename was wrong.

### Per-report cost summary (production sessions only)

| Report | Production cost | Wasted/extra | Total cost | Findings | Cost per finding |
|---|---|---|---|---|---|
| LUNA | $1.20 | $2.14 | $3.34 | 14 | $0.09 |
| TERRA | $3.04 | $1.43 | $4.47 | 7 | $0.43 |
| SOL | $1.29 | $0.00 | $1.29 | 9 | $0.14 |
| **Total** | **$5.53** | **$3.57** | **$9.10** | 30 | — |

Wasted/extra breakdown: LUNA = 18:17 wasted run ($2.11) + 21:06 file move ($0.03); TERRA = 19:34 failed run ($1.41) + 22:53 file move ($0.02); SOL = none.

### Analysis

- **LUNA was the cheapest** production run at $1.20, with the lowest cost-per-finding ($0.09). Despite being the cheapest, LUNA found the most issues (14) including the most critical one (constructor API mismatch). However, LUNA's low production cost is partly because the 20:08 re-run benefited from cached tokens from the 18:17 run — the 18:17 run did the heavy investigation ($2.11) but its output was wasted, and the 20:08 re-run reused much of that cached context at a lower rate. LUNA's true investigation cost is closer to $3.31 if you count both sessions.
- **SOL cost $1.29** with a cost-per-finding of $0.14. SOL's lower token count (949K input vs. 6.1M for LUNA and 7.4M for TERRA) reflects a more focused but less thorough investigation — it missed the constructor failure and CAP_SYS_RAWIO.
- **TERRA was the most expensive** at $3.04, with the highest cost-per-finding ($0.43). TERRA consumed comparable token volume to LUNA's production run but found half as many issues (7 vs. 14) and had one misleading finding (PP-006). TERRA also had $1.43 of wasted cost from the failed 19:34 session and the 22:53 file move.
- **Token efficiency:** All three models had high cache hit rates (90-97%), indicating effective prompt caching. The wasted sessions (18:17 and 19:34) cost $3.52 total — 39% of the grand total — due to the user forgetting to move previous eval files out or update prompt templates.
- **Cost vs. quality:** LUNA delivered the best value: lowest production cost, most findings, most critical finding, zero false positives. SOL was efficient but missed critical issues. TERRA was the worst value: highest cost, fewest findings, one misleading result.
