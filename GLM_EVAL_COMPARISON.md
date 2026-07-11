# Evaluation Comparison: Power-Profile Overhaul Reviews

## 1. Executive summary

**Best report overall: LUNA_MAX.**

**Final ranking:**

1. **LUNA_MAX** — 87.0/100
2. **SOL** — 76.0/100
3. **LUNA_EXHIGH** — 73.5/100
4. **TERRA** — 60.0/100

The gap between first and second is meaningful but not enormous; the gap between second and third is small; the gap between third and fourth is large.

The most important reason for the ranking: LUNA_MAX uniquely identified and verified with a direct probe that the installed `honor-tools 0.1.0` `PowerProfile.__init__()` does not accept `turbo_enabled` or `max_perf_pct`, which means every real profile apply fails with a `TypeError` before reaching any hardware. This is the single most fundamental blocking issue in the codebase — the entire power-profile feature is non-functional on real hardware — and neither SOL, TERRA, nor LUNA_EXHIGH found it, despite all three inspecting the dependency. LUNA_MAX also found the most issues overall (14), including several unique findings (queue timeout aborting startup, auto-switch retry-forever, persistence/hardware ordering, reconciliation trusting PPD label).

SOL produced a strong, precise report with excellent analysis of the RAPL MSR encoding bug and two unique findings (EPP empty-CPU success, MSR FD leak), but missed the constructor failure and the CAP_SYS_RAWIO deployment issue.

LUNA_EXHIGH used the same `gpt-5.6-luna` model as LUNA_MAX but with `reasoning_effort: "xhigh"` instead of the default. Despite the higher reasoning effort, it performed worse than the default LUNA_MAX: it found 13 issues (vs. LUNA_MAX's 14) and missed the most critical finding (the constructor API mismatch) that default LUNA_MAX found. Its one unique finding (PP-012, command-queue test failure) was not reproducible — all 221 tests pass in the same environment. This is a notable result: higher reasoning effort did not improve review quality and actually missed the most important finding.

TERRA uniquely found the CAP_SYS_RAWIO capability-bound issue — a valuable deployment-level finding no other report made — but missed the RAPL encoding bug entirely (a deterministic, high-severity arithmetic defect) and its PP-006 about turbo/max-performance was misleading: it claimed the values are "ignored in apply_profile()" when in reality the `PowerProfile` constructor fails before `apply_profile` is ever called.

No report is unsafe to rely on without re-verification, but TERRA requires the most re-verification due to the misleading PP-006 and the missed RAPL encoding bug. SOL and LUNA_MAX are largely reliable, with LUNA_MAX requiring the least re-verification. LUNA_EXHIGH is reliable for the findings it made but requires verification of PP-012.

A cost analysis of the Codex sessions that produced each report is included in Section 10. LUNA_MAX's production run cost $2.11, TERRA's cost $3.04, SOL's cost $1.29, and LUNA_EXHIGH's cost $1.39. SOL had the lowest cost-per-finding at $0.14, while TERRA had the highest at $0.43.

## 2. Repository and change scope

### Branch and commit

- Branch: `main` (tracks `origin/main`, is the default branch)
- Commit reviewed: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f` (`README: document Intel-only compatibility`)
- Working tree: clean except for the three untracked evaluation files

### Comparison base and merge base

All four reports correctly identified that the literal merge base of `main` with `origin/main` is `34d31f9` itself (the reviewed commit), which produces an empty diff and is useless as a behavioral baseline. All three independently chose the root commit `4d8994a` (`Initial commit`) as the defensible functional comparison base. This is correct: the four power-profile commits were committed directly to the default branch, and the root commit is the only defensible semantic baseline.

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
| **PP-001** PPD masking breaks apply + no restore | Correct but incomplete | Critical — appropriate | Yes — cites code lines, dependency source, uninstall script | Correctly identifies the design contradiction and persistent state change. However, does not mention that the constructor failure (LUNA_MAX PP-001) prevents `powerprofilesctl set` from ever being called, making the "apply fails because PPD is masked" failure mode moot in the current code. The persistent masking is still real. |
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
| **PP-001** Startup masks daemon every profile application requires | Correct but incomplete | Critical — appropriate | Yes — cites code lines, dependency source | Same core issue as SOL PP-001 / LUNA_MAX PP-002. Also does not mention the constructor failure that makes the `powerprofilesctl` failure moot. |
| **PP-002** Service lacks CAP_SYS_RAWIO for MSR path | Correct | High — appropriate | Yes — cites systemd unit, kernel driver requirement | **Unique and valuable finding.** No other report specifically identified the capability bounding set issue. Correctly notes that `write_rapl_msr` catches `OSError` and returns `False`, but the delayed caller discards it. |
| **PP-003** Final RAPL/EPP outcome not verified | Correct | High — appropriate | Yes — traces `_apply_power_profile` and `_delayed_power_rewrite` | Same core issue as SOL PP-003 / LUNA_MAX PP-004. Correctly identifies that `_last_applied_power_profile` overrides observation. |
| **PP-004** Rapid profile changes apply obsolete delayed rewrite | Correct | Medium — appropriate | Yes — traces `_pending_power_task` | Same core issue as SOL PP-005 / LUNA_MAX PP-008. |
| **PP-005** Performance governor silently changed to powersave | Correct | Medium — appropriate (lower than SOL's High) | Yes — cites `rewrite_epp` lines | Same core issue as SOL PP-004 / LUNA_MAX PP-005. Medium is arguably more appropriate than SOL's High since it's a deliberate Intel-pstate tradeoff. |
| **PP-006** Turbo/max-performance persist but not applied | Partially correct / misleading | Medium — moot in practice | Insufficient — did not test the actual call path | **TERRA's most serious mistake.** Claims "Installed honor-tools 0.1.0 ignores both in `apply_profile()`" and implies the apply succeeds with fixed values. In reality, the `PowerProfile` constructor fails with `TypeError` before `apply_profile` is ever called. TERRA inspected `apply_profile`'s source and saw the fixed writes, but missed that the constructor call before it fails. If TERRA had run a direct adapter probe (as LUNA_MAX did), it would have discovered the constructor failure. |
| **PP-007** AMD compatibility statement conflicts with implementation | Correct | Low — appropriate | Yes — cites README and platform detection | Same core issue as SOL PP-009 / LUNA_MAX PP-014. |

**TERRA missed:**
- The RAPL MSR encoding bug entirely (a deterministic, high-severity arithmetic defect that SOL and LUNA_MAX both found)
- The `honor-tools` constructor API mismatch (the most critical blocking issue)
- The queue timeout / startup abort issue
- The auto-switch retry-forever issue
- The persistence/hardware ordering issue
- The reconciliation trusting PPD label issue
- The EPP empty-CPU success issue
- The MSR FD leak issue
- The injectable root bypass issue

### 4.3 LUNA_MAX findings

| Finding | Classification | Severity appropriate? | Evidence sufficient? | Notes |
|---|---|---|---|---|
| **PP-001** Resolved `honor-tools` API makes every real apply fail | Correct | Critical — appropriate | **Excellent** — direct adapter probe returning the `TypeError` | **Most valuable finding across all four reports.** Uniquely identified and verified with a direct probe. Correctly attributes to root commit via `git blame`. Also inspected the sibling `../honor-tools` source tree to understand the API discrepancy. |
| **PP-002** Startup masks system power managers, never restores | Correct | Critical — appropriate | Yes — cites code lines, dependency source, uninstall script | Same core issue as SOL PP-001 / TERRA PP-001. |
| **PP-003** RAPL encoder drops PL2 enable and time-window bits | Correct | High — appropriate | Yes — arithmetic verification, code snippet | Same core issue as SOL PP-002. Verified with a pure arithmetic check returning `pl2_enable=0` and `tw2_written=0`. |
| **PP-004** Apply success before delayed enforcement, failures lost | Correct | High — appropriate | Yes — traces `_apply_power_profile` and `_delayed_power_rewrite` | Same core issue as SOL PP-003 / TERRA PP-003. |
| **PP-005** Performance profile ends with powersave | Correct | High — slightly high; Medium may be more appropriate | Yes — cites `rewrite_epp` and profile definitions | Same core issue as SOL PP-004 / TERRA PP-005. |
| **PP-006** Startup reconciliation trusts PPD label | Correct | High — appropriate | Yes — traces `_reconcile_power_profile` and `read_power` | **Unique finding.** Correctly identifies that reconciliation only compares the PPD-derived profile name, not actual RAPL/EPP/governor values. Custom profiles sharing a PPD mode with built-ins are even less identifiable. |
| **PP-007** Daemon cleanup can exceed queue deadline and abort startup | Correct | High — slightly high; Medium may be more appropriate | Yes — calculates 20s worst case vs 10s timeout, traces uncaught exception | **Unique finding.** Correctly identifies that 4 × 5s = 20s exceeds the 10s queue timeout, `initialize()` doesn't catch `CommandTimeoutError`, and the worker thread continues after the async timeout. High is defensible but requires systemd to be slow; Medium is also reasonable. |
| **PP-008** Fire-and-forget rewrites not generation-safe | Correct | High — slightly high; Medium may be more appropriate | Yes — traces `_pending_power_task` lifecycle | Same core issue as SOL PP-005 / TERRA PP-004. LUNA_MAX provides more detail about the A/B interleaving scenario. High is defensible but the race window is 0.5s; Medium is also reasonable. |
| **PP-009** Capability probing much weaker than mechanisms | Correct | Medium — appropriate | Yes — cites `get_power_capability` and docs | Same core issue as SOL PP-006. |
| **PP-010** Failed auto-switch applies retry forever every 2 seconds | Correct | Medium — appropriate | Yes — traces `_auto_switch_loop` logic | **Unique finding.** Correctly identifies that `last_ac`/`last_policy` only update on success, causing indefinite retries. |
| **PP-011** Hardware success and persistence failure leave contradictory state | Correct | Medium — appropriate | Yes — traces `_apply_power_profile` and `save_power_profile` ordering | **Unique finding.** Correctly identifies both orderings: hardware-before-persist in `_apply_power_profile` and persist-before-hardware in `save_power_profile`. |
| **PP-012** New high-risk paths have no meaningful production-adapter tests | Correct | Medium — appropriate | Yes — cites test files and `FakeHardware` limitations | All four reports identify the test gap; LUNA_MAX is the most specific about what's missing. |
| **PP-013** New power I/O bypasses adapter's injectable root | Correct | Low — appropriate | Yes — cites hard-coded paths vs. `self._root` | **Unique finding.** Correctly identifies that `rewrite_epp`, `write_rapl_msr`, and `stop_competing_power_daemons` hard-code paths instead of using `self._root`. |
| **PP-014** AMD compatibility statement does not match behavior | Correct | Low — appropriate | Yes — cites README and platform detection | Same core issue as SOL PP-009 / TERRA PP-007. |

**LUNA_MAX missed:**
- The CAP_SYS_RAWIO deployment issue (TERRA PP-002)
- The MSR FD leak as a separate finding (SOL PP-008; LUNA_MAX mentions it in test suggestions but not as a finding)
- The EPP empty-CPU success as a separate finding (SOL PP-007; LUNA_MAX mentions the injectable root bypass which is related)

**LUNA_EXHIGH missed:**
- `honor-tools` constructor API mismatch (Critical) — the most fundamental blocking issue; especially notable because default LUNA_MAX found it
- CAP_SYS_RAWIO bounding set (High)
- Auto-switch retry-forever (Medium)
- Persistence/hardware ordering (Medium)
- EPP empty-CPU success (Medium)

### 4.4 LUNA_EXHIGH findings

LUNA_EXHIGH used `gpt-5.6-luna` with `reasoning_effort: "xhigh"` — the same model as LUNA_MAX but with higher reasoning effort.

| Finding | Classification | Severity appropriate? | Evidence sufficient? | Notes |
|---|---|---|---|---|
| **PP-001** PPD disabled while apply contract requires it | Correct but incomplete | Critical — appropriate | Yes — cites code lines, dependency source | Same core issue as SOL PP-001 / TERRA PP-001 / LUNA_MAX PP-002. Splits the contract contradiction (PP-001) from the persistent mask (PP-002), which is a useful separation. Does not mention the constructor failure that prevents `powerprofilesctl set` from being called. |
| **PP-002** Daemon masks persist after shutdown/uninstall | Correct | High — appropriate | Yes — cites code, service file, uninstall script | Same core issue as the "no restore" half of SOL PP-001 / LUNA_MAX PP-002. Separating the lifecycle/restore issue from the contract contradiction is reasonable. |
| **PP-003** RAPL PL2 bits shifted out | Correct | High — appropriate | Yes — arithmetic verification, code lines | Same core issue as SOL PP-002 / LUNA_MAX PP-003. |
| **PP-004** Performance governor left at powersave | Correct | High — slightly high; Medium may be more appropriate | Yes — cites `rewrite_epp` and profile definitions | Same core issue as SOL PP-004 / TERRA PP-005 / LUNA_MAX PP-005. |
| **PP-005** Delayed failures ignored after success | Correct | High — appropriate | Yes — traces `_apply_power_profile` and `_delayed_power_rewrite` | Same core issue as SOL PP-003 / TERRA PP-003 / LUNA_MAX PP-004. |
| **PP-006** Startup queue timeout | Correct | High — slightly high; Medium may be more appropriate | Yes — calculates 20s worst case vs 10s timeout | Same core issue as LUNA_MAX PP-007. |
| **PP-007** Capability from executable check only | Correct | Medium — appropriate | Yes — cites `get_power_capability` and docs | Same core issue as SOL PP-006 / LUNA_MAX PP-009. |
| **PP-008** MSR I/O not exception-safe | Correct | Medium — appropriate | Yes — traces `os.open`/`os.close` and `struct.error` | Same core issue as SOL PP-008. |
| **PP-009** Delayed tasks not owned/ordered | Correct | Medium — appropriate | Yes — traces `_pending_power_task` lifecycle | Same core issue as SOL PP-005 / TERRA PP-004 / LUNA_MAX PP-008. |
| **PP-010** Reconciliation compares name only | Correct | Medium — appropriate | Yes — traces `_reconcile_power_profile` | Same core issue as LUNA_MAX PP-006. |
| **PP-011** Hardware paths bypass injectable root | Correct | Medium — appropriate | Yes — cites hard-coded paths vs. `self._root` | Same core issue as LUNA_MAX PP-013. Rated Medium vs. LUNA_MAX's Low; Medium is arguably more appropriate. |
| **PP-012** Command-queue test broken in environment | Partially correct / not reproducible | Medium — overstated | Insufficient — claims test failure that I could not reproduce | **Unique finding, but not reproducible.** LUNA_EXHIGH reports that `tests/test_backend.py::TestCommandQueue::test_run_executes_function` fails under Python 3.14.6 with `CommandTimeoutError` after 10 seconds. I ran the same test with the same Python 3.14.6 and it passed in 0.03s. The full suite (221 tests) also passed. This was likely a transient sandbox/environment issue, not a real defect. The finding is correctly labeled as pre-existing and unrelated to the overhaul, but the severity should be Low or Informational given it's not reproducible. |
| **PP-013** README compatibility wording | Correct | Low — appropriate | Yes — cites README and platform detection | Same core issue as SOL PP-009 / TERRA PP-007 / LUNA_MAX PP-014. |

**LUNA_EXHIGH missed:**
- The `honor-tools` constructor API mismatch (Critical) — the most fundamental blocking issue; this is especially notable because the default LUNA_MAX found it
- CAP_SYS_RAWIO bounding set (High)
- Auto-switch retry-forever (Medium)
- Persistence/hardware ordering (Medium)
- EPP empty-CPU success (Medium)

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
- RAPL MSR encoding bug (High) — a deterministic arithmetic defect; SOL and LUNA_MAX both found it
- `honor-tools` constructor API mismatch (Critical) — the most fundamental blocking issue
- Queue timeout aborting startup (High/Medium)
- Auto-switch retry-forever (Medium)
- Persistence/hardware ordering (Medium)
- Reconciliation trusting PPD label (High)
- EPP empty-CPU success (Medium)
- MSR FD leak (Low)
- Injectable root bypass (Low)

**LUNA_MAX missed:**
- CAP_SYS_RAWIO bounding set (High) — the deployed service cannot open `/dev/cpu/0/msr`
- MSR FD leak as a separate finding (Low) — mentioned in test suggestions but not as a finding
- EPP empty-CPU success as a separate finding (Medium) — partially covered by PP-013

### Issues missed by all four

- **The interaction between the constructor failure and the PPD masking failure mode.** SOL, TERRA, and LUNA_EXHIGH claim that masking PPD makes `powerprofilesctl set` fail, causing partial applies. This is technically correct about the code path, but in practice the constructor `TypeError` fails first, so `powerprofilesctl set` is never called. The PPD masking is still a real problem (persistent state change with no restore), but the specific "apply fails because PPD is masked" failure mode described by SOL, TERRA, and LUNA_EXHIGH is not the actual failure mode in the current code. Only LUNA_MAX found the constructor failure that is the actual first failure.

- **The `ExecStopPost` hook only restores fan auto, not power state.** The service file has `ExecStopPost=-/usr/bin/honor-control-service --restore-fan-auto`, which restores fan state on stop but does not unmask PPD/`intel_lpmd` or restore HWP dynamic boost. SOL and LUNA_MAX mention that shutdown doesn't restore power state, but neither specifically notes that the `ExecStopPost` hook exists for fan restoration but not for power state, which would be the natural place to add it.

### Relevant architectural/historical context not fully considered

- **The sibling `../honor-tools` source tree has a newer `PowerProfile` with `turbo_enabled`/`max_perf_pct`.** Only LUNA_MAX inspected this. This suggests the adapter was written against a newer API than the declared `honor-tools>=0.1,<0.2` range resolves to. This is important context for understanding why the constructor call fails.

- **The `OVERHAUL_PLAN.md` rule 8 says "Do not duplicate `honor-tools` algorithms."** The delayed RAPL/EPP rewrite duplicates the dependency's RAPL/EPP writes with different semantics (e.g., leaving `powersave` governor for `performance` profiles). This is an architectural tension that all four reports touch on but could frame more explicitly as a violation of the project's own design rules.

### False assumptions shared by multiple reports

- SOL and TERRA both assume that the PPD masking causes `powerprofilesctl set` to fail during apply. While this would be true if the constructor bug were fixed, in the current code the constructor failure prevents `apply_profile` from being called at all. The PPD masking is still a real issue (persistent state change), but the described failure mode is not the actual one.

### Useful positive observations omitted by all four

- The `ExecStopPost` hook for fan restoration shows the project has a pattern for shutdown restoration that could be extended to power state. None of the reports noted this existing pattern as a potential foundation for fixing the PPD restore gap.
- The `FakeHardware` implementation correctly models the protocol shape of the new methods, which is useful for future test development even though it doesn't model failure semantics.

## 6. Scorecard

| Dimension | Weight | SOL | TERRA | LUNA_MAX | LUNA_EXHIGH |
|---|---|---|---|---|---|
| A. Technical correctness | 30% | 8 (2.4) | 6 (1.8) | 9 (2.7) | 7 (2.1) |
| B. Coverage and issue discovery | 20% | 6 (1.2) | 5 (1.0) | 9 (1.8) | 7 (1.4) |
| C. Evidence and verification | 15% | 8 (1.2) | 6 (0.9) | 9 (1.35) | 7 (1.05) |
| D. Severity and priority calibration | 10% | 8 (0.8) | 6 (0.6) | 8 (0.8) | 8 (0.8) |
| E. Architecture and context | 10% | 8 (0.8) | 7 (0.7) | 9 (0.9) | 8 (0.8) |
| F. Fix quality and actionability | 10% | 8 (0.8) | 6 (0.6) | 8 (0.8) | 8 (0.8) |
| G. Clarity and efficiency | 5% | 8 (0.4) | 8 (0.4) | 7 (0.35) | 8 (0.4) |
| **Final weighted score** | **100%** | **76.0** | **60.0** | **87.0** | **73.5** |

### Score rationale

**SOL — Technical correctness (8):** Precise analysis of all 9 findings. RAPL encoding analysis is exactly correct. Missed the constructor failure and CAP_SYS_RAWIO. The PPD masking finding doesn't note the constructor failure makes the described failure mode moot.

**SOL — Coverage (6):** Found 9 findings including 2 unique (EPP empty-CPU, MSR FD leak). Missed 7 important issues including 2 critical/high (constructor failure, CAP_SYS_RAWIO, queue timeout, reconciliation trust, auto-switch retry, persistence ordering, injectable root).

**TERRA — Technical correctness (6):** Correctly found CAP_SYS_RAWIO (unique and valuable). But missed the RAPL encoding bug entirely, and PP-006 is misleading (claims values are "ignored in apply_profile" when the constructor fails first). The PP-006 error suggests TERRA inspected the dependency source but didn't test the actual call path.

**TERRA — Coverage (5):** Found 7 findings, fewest of any report. Missed the RAPL encoding bug (deterministic, high severity), the constructor failure (critical), and 6 other issues. Uniquely found CAP_SYS_RAWIO.

**LUNA_MAX — Technical correctness (9):** Found the constructor failure (most critical) and verified it with a direct probe. RAPL encoding analysis correct. Found 14 issues total. Missed CAP_SYS_RAWIO. No misleading findings.

**LUNA_MAX — Coverage (9):** Found 14 issues, most of any report. 6 unique findings (constructor failure, reconciliation trust, queue timeout, auto-switch retry, persistence ordering, injectable root). Missed CAP_SYS_RAWIO, FD leak as separate finding, EPP empty-CPU as separate finding.

**LUNA_MAX — Evidence (9):** Best evidence. Direct adapter probe returning the `TypeError`. Arithmetic verification of RAPL encoding. Read-only system checks (PPD active, MSR present). Inspected sibling source tree. All claims are auditable.

**TERRA — Evidence (6):** Good evidence for CAP_SYS_RAWIO (kernel source reference). But PP-006 shows insufficient verification — TERRA inspected `apply_profile` source but didn't test the actual call path, missing the constructor failure that a direct probe would have revealed.

**LUNA_EXHIGH — Technical correctness (7):** All 13 findings are technically correct in their analysis. However, PP-012 (command-queue test failure) is not reproducible — I ran the same test with the same Python 3.14.6 and it passed in 0.03s, and the full 221-test suite passed. The finding was likely a transient sandbox issue. More importantly, LUNA_EXHIGH missed the constructor API mismatch despite using the same model as LUNA_MAX with higher reasoning effort, which is a significant correctness gap.

**LUNA_EXHIGH — Coverage (7):** Found 13 issues, more than SOL (9) and TERRA (7), but fewer than LUNA_MAX (14). Found the queue timeout, reconciliation trust, and injectable root issues that SOL missed. However, missed the most critical finding (constructor failure) that default LUNA_MAX found, plus auto-switch retry-forever, persistence/hardware ordering, EPP empty-CPU success, and CAP_SYS_RAWIO. Its one unique finding (PP-012) is not reproducible.

**LUNA_EXHIGH — Evidence (7):** Good code-level analysis with arithmetic verification of RAPL encoding. Inspected the sibling `honor-tools` source. However, did not perform a direct adapter probe (which would have revealed the constructor failure), and PP-012 claims a test failure that is not reproducible.

## 7. Per-report assessment

### SOL

**Strongest aspects:** Precise, well-structured analysis with excellent bit-level RAPL encoding verification. The most disciplined severity calibration. Strong architectural assessment with a concrete 6-point refactor plan. Two unique findings (EPP empty-CPU success, MSR FD leak/`struct.error`).

**Weakest aspects:** Missed the most fundamental blocking issue (constructor API mismatch) despite inspecting the dependency. Missed the CAP_SYS_RAWIO deployment issue. The PPD masking finding doesn't note that the constructor failure makes the described `powerprofilesctl` failure mode moot.

**Most valuable valid finding:** PP-002 (RAPL MSR encoding) — precise, deterministic, verified, with a concrete fix.

**Most serious mistake/false positive:** No false positives, but the most serious miss is the constructor failure. SOL inspected `honor-tools` and confirmed `_set_ppd()` calls `powerprofilesctl set`, but didn't test the adapter's `apply_power_profile` end-to-end, which would have revealed the `TypeError`.

**Most important missed issue:** The `honor-tools` constructor API mismatch (LUNA_MAX PP-001).

**Manual verification required:** Moderate. SOL's 9 findings are all correct and well-supported. The main gap is what it missed, not what it got wrong. Acting on SOL's findings would fix real issues but would not make the feature functional (the constructor failure would remain).

### TERRA

**Strongest aspects:** Uniquely found the CAP_SYS_RAWIO deployment issue — a valuable finding that requires understanding both the systemd capability model and the kernel MSR driver's permission check. Concise and well-organized. Good architectural assessment.

**Weakest aspects:** Missed the RAPL encoding bug entirely — a deterministic arithmetic defect that SOL and LUNA_MAX both found. PP-006 is misleading: it claims `turbo_enabled`/`max_perf_pct` are "ignored in `apply_profile()`" when the `PowerProfile` constructor fails before `apply_profile` is called. This suggests TERRA inspected the dependency source but didn't test the actual call path.

**Most valuable valid finding:** PP-002 (CAP_SYS_RAWIO) — unique, specific, deployment-level, with a clear fix.

**Most serious mistake/false positive:** PP-006 is misleading. TERRA claims the apply succeeds with fixed `no_turbo=0`/`max_perf_pct=100` values, when in reality the apply fails entirely with a `TypeError`. This is not a false positive (the underlying observation about `apply_profile` writing fixed values is correct), but the framing implies a working apply path that doesn't exist. More importantly, TERRA was close to finding the constructor failure but stopped at inspecting `apply_profile` without testing the call path.

**Most important missed issue:** The RAPL MSR encoding bug (SOL PP-002 / LUNA_MAX PP-003) — a deterministic, high-severity arithmetic defect.

**Manual verification required:** Substantial. PP-006 needs re-evaluation. The missing RAPL encoding finding means TERRA's coverage of the hardware path is incomplete. TERRA's valid findings (PP-001, PP-002, PP-003, PP-004, PP-005, PP-007) are correct and actionable, but the report cannot be relied upon alone.

### LUNA_MAX

**Strongest aspects:** Found the most issues (14), including the most critical one (constructor failure). Verified the constructor failure with a direct adapter probe — the kind of evidence that makes a finding immediately actionable. Inspected the sibling `../honor-tools` source tree to understand the API discrepancy. Six unique findings. Best evidence and verification overall.

**Weakest aspects:** Missed the CAP_SYS_RAWIO deployment issue. Some findings could be more concise (PP-008 and PP-012 overlap on delayed-task issues). The report is long (1082 lines), which slightly reduces efficiency. A few severity ratings are slightly high (PP-007 queue timeout as High, PP-008 delayed tasks as High).

**Most valuable valid finding:** PP-001 (constructor API mismatch) — the single most important finding across all four reports. It is the first failure that blocks all real profile applies, and it was verified with a direct probe.

**Most serious mistake/false positive:** No false positives. The most serious miss is the CAP_SYS_RAWIO issue, which LUNA_MAX hints at (PP-004 mentions "a permissions error on `/dev/cpu/0/msr`") but doesn't specifically identify as a capability bounding set problem.

**Most important missed issue:** CAP_SYS_RAWIO bounding set (TERRA PP-002).

**Manual verification required:** Least of the three. LUNA_MAX's findings are well-supported with direct evidence. The main gap is the CAP_SYS_RAWIO issue, which would need to be added. Acting on LUNA_MAX's findings would address the most critical issues and make the feature potentially functional (after fixing the constructor, PPD masking, RAPL encoding, and CAP_SYS_RAWIO).

### LUNA_EXHIGH

**Strongest aspects:** Well-organized report with good architectural understanding. Found 13 issues including the queue timeout, reconciliation trust, and injectable root issues. Useful separation of the PPD contract contradiction (PP-001) from the persistent mask lifecycle (PP-002). Inspected the sibling `honor-tools` source tree.

**Weakest aspects:** Missed the most critical finding (constructor API mismatch) despite using the same `gpt-5.6-luna` model as LUNA_MAX with `reasoning_effort: "xhigh"`. This is the most notable result: higher reasoning effort did not improve review quality and actually missed the most important finding that default LUNA_MAX found. Its one unique finding (PP-012, command-queue test failure) is not reproducible — all 221 tests pass in the same Python 3.14.6 environment.

**Most valuable valid finding:** PP-003 (RAPL MSR encoding) — correct arithmetic verification with clear explanation. Also valuable: PP-006 (startup queue timeout) and PP-010 (reconciliation compares name only), both of which SOL and TERRA missed.

**Most serious mistake/false positive:** PP-012 (command-queue test broken) is not reproducible. I ran `pytest -q tests/test_backend.py::TestCommandQueue::test_run_executes_function` with the same Python 3.14.6 and it passed in 0.03s. The full 221-test suite also passed. This was likely a transient sandbox issue. The finding is correctly labeled as pre-existing and unrelated to the overhaul, but it should not have been reported as a defect without re-running the test.

**Most important missed issue:** The `honor-tools` constructor API mismatch (LUNA_MAX PP-001) — the most critical finding in the codebase, which the default LUNA_MAX found with a direct adapter probe. LUNA_EXHIGH inspected the sibling `honor-tools` source but did not test the actual `PowerProfile` constructor call, which would have revealed the `TypeError`.

**Manual verification required:** Moderate. PP-012 needs to be discarded (not reproducible). The other 12 findings are correct and well-supported. The main gap is the constructor failure, which LUNA_EXHIGH missed despite using the same model as LUNA_MAX with higher reasoning effort.

## 8. Final ranking and verdict

### 1st place: LUNA_MAX (87.0/100)

LUNA_MAX found the most real issues (14), had the fewest false positives (zero), best understood the architecture (inspected the sibling source tree, traced the full dependency contract), and gave the most actionable fixes (direct probe evidence for the constructor failure). LUNA_MAX's PP-001 is the single most important finding across all four reports: it is the first failure that blocks all real profile applies, and it was verified with a direct adapter probe returning the actual `TypeError`. No other report found this.

### 2nd place: SOL (76.0/100)

SOL produced a precise, well-structured report with excellent RAPL encoding analysis and two unique findings (EPP empty-CPU, MSR FD leak). SOL's severity calibration is the most disciplined. However, SOL missed the constructor failure (the most critical blocking issue) and the CAP_SYS_RAWIO deployment issue, and its PPD masking finding doesn't note that the constructor failure makes the described failure mode moot.

### 3rd place: LUNA_EXHIGH (73.5/100)

LUNA_EXHIGH found 13 issues — more than SOL (9) and TERRA (7) — including the queue timeout, reconciliation trust, and injectable root issues that SOL missed. However, it missed the most critical finding (constructor API mismatch) despite using the same model as LUNA_MAX with `reasoning_effort: "xhigh"`, and its one unique finding (PP-012, command-queue test failure) is not reproducible. The higher reasoning effort did not improve review quality and actually missed the most important finding that default LUNA_MAX found. LUNA_EXHIGH is ranked below SOL because SOL's two unique findings (EPP empty-CPU, MSR FD leak) are both valid and reproducible, while LUNA_EXHIGH's unique finding is not.

### 4th place: TERRA (60.0/100)

TERRA uniquely found the CAP_SYS_RAWIO deployment issue — a valuable finding no other report made. However, TERRA missed the RAPL encoding bug entirely (a deterministic, high-severity arithmetic defect that both other reports found), and its PP-006 is misleading (claims values are "ignored in `apply_profile`" when the constructor fails first). TERRA found the fewest issues (7) and had the weakest coverage.

### Decisive factors

- **Which report found the most real issues?** LUNA_MAX (14), followed by LUNA_EXHIGH (13), then SOL (9), then TERRA (7).
- **Which report had the fewest false positives?** LUNA_MAX (zero), followed by SOL (zero), then LUNA_EXHIGH (one non-reproducible finding), then TERRA (one misleading finding, PP-006).
- **Which report best understood the architecture?** LUNA_MAX, which inspected the sibling source tree, traced the full dependency contract, and identified the split-ownership problem most precisely.
- **Which report gave the most actionable fixes?** LUNA_MAX, whose direct adapter probe for PP-001 provides immediately actionable evidence, and whose 14 findings cover the most ground.
- **Which report would you trust most for a merge or release decision?** LUNA_MAX, because it found the constructor failure that makes the entire feature non-functional, plus the most additional issues.
- **Which report offers the best signal-to-noise ratio?** SOL, which found 9 issues all correct and well-supported, with no misleading findings. LUNA_MAX has more findings but also more length and some overlap.

## 9. Best combined review

Consolidated from all four reports plus independent verification, corrected for severity and context.

### Must fix before merge or release

1. **Fix the `honor-tools` constructor API mismatch.** The installed `honor-tools 0.1.0` `PowerProfile.__init__` does not accept `turbo_enabled` or `max_perf_pct`. Every real profile apply fails with `TypeError` before reaching hardware. Either pin/require a compatible `honor-tools` version that includes these fields, or adapt the adapter to the older API. Add an integration test using the declared dependency. *(LUNA_MAX PP-001)*

2. **Remove or fully own/reverse the PPD and `intel_lpmd` masking.** The service masks both units at startup with no capture, rollback, shutdown restore, or uninstall restore. The uninstall script does not unmask them. Either keep PPD running and integrate with it, or implement a complete ownership lifecycle: capture prior state, use reversible runtime mechanisms, restore on shutdown/uninstall/failure, and gate on complete capability. At minimum, remove startup masking until that lifecycle exists. *(SOL PP-001, TERRA PP-001, LUNA_MAX PP-002)*

3. **Fix the RAPL MSR encoding.** PL2 enable bit (bit 47) and PL2 time window (bits 49-55) are dropped because `hi` is built with absolute positions and then shifted left by 32, placing them above bit 63 where the 64-bit mask discards them. Build the 64-bit register with global positions exactly once. Add table-driven pure encode/decode tests. *(SOL PP-002, LUNA_MAX PP-003)*

4. **Add CAP_SYS_RAWIO or remove the raw-MSR path.** The systemd service's `CapabilityBoundingSet` does not include `CAP_SYS_RAWIO`, which the standard Linux MSR driver requires to open `/dev/cpu/0/msr`. Either add the narrowly justified capability after security review, or remove the raw-MSR path from the standard service. Make raw-MSR support a separately probed optional mechanism. *(TERRA PP-002)*

5. **Do not report/persist success before delayed enforcement is verified.** The delayed task's boolean results are discarded; no post-settle verification occurs; `_last_applied_power_profile` overrides observed state. Await the required correction, check boolean results, read back and decode RAPL/governor/EPP, and classify full/partial/failure before marking applied or running hooks. *(SOL PP-003, TERRA PP-003, LUNA_MAX PP-004)*

6. **Make delayed rewrites generation-safe.** Older tasks are not cancelled when a newer apply overwrites `_pending_power_task`. Maintain a monotonically increasing apply generation; cancel and await the prior correction before a newer apply; recheck generation before each write. Cancel and await all owned tasks on shutdown. *(SOL PP-005, TERRA PP-004, LUNA_MAX PP-008)*

7. **Fix the queue timeout / startup abort issue.** `stop_competing_power_daemons` does up to 4 sequential `systemctl` calls (each 5s timeout = 20s worst case) through the queue's default 10s timeout. `initialize()` does not catch `CommandTimeoutError`. Use an explicit overall deadline longer than the maximum, or a dedicated reversible systemd ownership component. Catch cleanup failure during startup and publish degraded health. *(LUNA_MAX PP-007)*

8. **Add deterministic tests for the new behavior.** The current fake-only happy path is not a sufficient merge gate. Add: dependency compatibility test, RAPL encode/decode tests, systemd ownership/restore tests, delayed-failure tests, concurrency/cancellation tests, capability matrix tests, and GUI active-combo dirty-state tests. *(All four reports)*

### Should fix soon

1. **Resolve the performance governor → powersave semantic mismatch.** The delayed EPP rewrite leaves `powersave` governor for `performance` profiles while the profile definition and UI claim `performance`. Reject or normalize incompatible governor/EPP combinations at validation time, or model the actual effective governor. *(SOL PP-004, TERRA PP-005, LUNA_MAX PP-005)*

2. **Make startup reconciliation compare actual state, not just the PPD label.** Reconciliation only compares the PPD-derived profile name. If RAPL/EPP/governor were overwritten but PPD still reports the matching name, reconciliation is skipped. Compare the complete desired definition to per-mechanism observed values, or conservatively reapply. *(LUNA_MAX PP-006)*

3. **Expand capability probing.** Only honor-tools import, platform match, and `powerprofilesctl` binary are checked. Add non-mutating, per-mechanism probes for MSR device, cpufreq/governor/EPP files, Intel pstate controls, systemd units, and effective service capability. *(SOL PP-006, LUNA_MAX PP-009)*

4. **Fix EPP rewrite to handle empty CPU sets and verify read-back.** If `cpu_dirs` is empty, `all_ok` stays `True`. Governor write results are ignored. Read-back content is discarded. Require at least one eligible CPU, check governor results, compare read-back to requested value. *(SOL PP-007)*

5. **Fix MSR FD leak and short I/O handling.** FDs are not closed on intermediate errors. `struct.error` is not caught (not an `OSError`). `os.write` length is not checked. Use context-managed descriptors, require exactly 8 bytes, convert malformed I/O into structured failure. *(SOL PP-008)*

6. **Fix auto-switch retry-forever behavior.** Failed applies retry every 2 seconds with no backoff or latching. Separate source-event detection from apply retry state; record the failed transition, back off, and retry only on a new stable source event. *(LUNA_MAX PP-010)*

7. **Fix persistence/hardware ordering.** In `_apply_power_profile`, hardware is applied before persistence; if persistence fails, the exception propagates without rollback. In `save_power_profile`, the definition is persisted before re-application; if the apply fails, the new definition is already durable. Define an explicit transaction policy. *(LUNA_MAX PP-011)*

8. **Correct documentation.** README claims AMD "sysfs-only EPP" but code returns unsupported. `docs/hardware-support.md` claims "every mechanism is checked separately" but capability probing checks only three things. Document the actual platform gate, required resources, daemon side effects, and effective governor semantics. *(SOL PP-009, TERRA PP-007, LUNA_MAX PP-014)*

### Optional cleanup or longer-term improvement

1. **Use injectable root for new power I/O paths.** `rewrite_epp`, `write_rapl_msr`, and `stop_competing_power_daemons` hard-code `/sys/devices/system/cpu`, `/dev/cpu/0/msr`, and absolute sysfs paths instead of using `self._root`. This makes safe unit testing unnecessarily difficult. *(LUNA_MAX PP-013)*

2. **Extract a typed `PowerApplyResult` and `PowerApplyPlan`.** Define a typed result containing per-mechanism write status, settled observations, and effective profile. Let one layer execute the complete ordered plan. Remove `result.get(..., True)` defaults and asserted-profile overlay from observed state. *(All four reports, architecture sections)*

3. **Add diagnostics for applied-vs-observed mismatch, last apply generation, and external-manager ownership.** *(All four reports)*

4. **Pin or formally adapt to a tested `honor-tools` behavior/API.** Avoid relying on timing and untyped dictionaries across the whole `<0.2` range. *(SOL, LUNA_MAX)*

5. **Make repository-wide lint scope explicit** (exclude archival reverse-engineering scripts or clean them separately) and ensure the development environment actually installs test/build tools. *(SOL)*

## 10. Cost and token-usage analysis

### Methodology

I inspected the Codex session logs to find the sessions that produced each report. Each session's `event_msg` entries contain `total_token_usage` with `input_tokens`, `cached_input_tokens`, `output_tokens`, and `reasoning_output_tokens`. I used the final cumulative totals from each session.

API pricing was taken from the [OpenAI API pricing page](https://platform.openai.com/docs/pricing) (Standard tier, per 1M tokens, retrieved 2026-07-12):

| Model | Input | Cached input | Output |
|---|---|---|---|
| `gpt-5.6-sol` | $5.00 | $0.50 | $30.00 |
| `gpt-5.6-terra` | $2.50 | $0.25 | $15.00 |
| `gpt-5.6-luna` | $1.00 | $0.10 | $6.00 |

Cost = (non-cached input / 1M × input rate) + (cached input / 1M × cached rate) + (output / 1M × output rate). Output tokens include reasoning tokens.

### Per-report token usage and cost

| Report | Model | Input | Cached | Output | Cost | Findings | Cost per finding |
|---|---|---|---|---|---|---|---|
| LUNA_MAX | `gpt-5.6-luna` | 14,141,940 | 13,787,648 | 62,859 | $2.11 | 14 | $0.15 |
| TERRA | `gpt-5.6-terra` | 7,442,463 | 7,195,392 | 41,529 | $3.04 | 7 | $0.43 |
| SOL | `gpt-5.6-sol` | 949,232 | 857,856 | 13,464 | $1.29 | 9 | $0.14 |
| LUNA_EXHIGH | `gpt-5.6-luna` (xhigh) | 8,909,318 | 8,641,024 | 43,735 | $1.39 | 13 | $0.11 |
| **Total** | | | | | **$7.83** | **43** | — |

### Analysis

- **SOL was the cheapest** at $1.29, with the lowest cost-per-finding ($0.14). SOL's lower token count (949K input vs. 14.1M for LUNA_MAX and 8.9M for LUNA_EXHIGH) reflects a more focused but less thorough investigation — it missed the constructor failure and CAP_SYS_RAWIO.
- **LUNA_MAX cost $2.11** with a cost-per-finding of $0.15. Despite being the same base model as LUNA_EXHIGH, LUNA_MAX found the most issues (14) including the most critical one (constructor API mismatch) via a direct adapter probe.
- **LUNA_EXHIGH cost $1.39** with a cost-per-finding of $0.11. Despite using the same model as LUNA_MAX with `reasoning_effort: "xhigh"`, it found fewer issues (13 vs. 14) and missed the most critical finding (constructor API mismatch). The higher reasoning effort consumed more tokens (8.9M input vs. 14.1M for LUNA_MAX) but did not produce better results. This suggests that higher reasoning effort does not always improve code review quality and may cause the model to miss critical findings by over-analyzing less important code paths.
- **TERRA was the most expensive** at $3.04, with the highest cost-per-finding ($0.43). TERRA consumed comparable token volume to LUNA_EXHIGH but found half as many issues (7 vs. 13) and had one misleading finding (PP-006).
- **Token efficiency:** All four models had high cache hit rates (90-97%), indicating effective prompt caching.
- **Cost vs. quality:** LUNA_MAX delivered the best value: most findings (14), most critical finding, zero false positives, at $0.15 per finding. SOL was the cheapest but missed critical issues. LUNA_EXHIGH was slightly cheaper than LUNA_MAX but missed the most critical finding. TERRA was the worst value: highest cost, fewest findings, one misleading result.
- **Reasoning effort comparison:** The default LUNA_MAX (`reasoning_effort: "default"`) outperformed LUNA_EXHIGH (`reasoning_effort: "xhigh"`) on every quality metric: more findings (14 vs. 13), found the most critical issue, and zero false positives vs. one non-reproducible finding. This is a notable result suggesting that higher reasoning effort does not always improve code review quality.
