# Meta-Evaluation: Critical Review of Nine Code-Review Reports on the Honor Control Power-Profile Overhaul

**Review date:** 2026-07-12
**Repository:** `honor-control` at commit `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f`
**Working tree:** Clean (no code changes since reports were written — all issues remain unfixed)

---

## Pricing Summary

Per-report costs calculated from session token usage and official API pricing.

| Report | Model | Effort | Tokens | Cost |
|--------|-------|--------|--------|------|
| `5.5_HIGH_EVAL.md` | GPT-5.5 | high | 2.78M | $2.51 |
| `5.5_XHIGH_EVAL.md` | GPT-5.5 | xhigh | 6.91M | $5.23 |
| `GLM_MAX_EVAL.md` | GLM-5.2 | max | 4.08M | $1.79 |
| `LUNA_HIGH_EVAL.md` | GPT-5.6-Luna | high | 5.30M | $0.85 |
| `LUNA_MAX_EVAL.md` | GPT-5.6-Luna | max | 14.2M (messed up session) | $2.11 |
| `LUNA_XHIGH_EVAL.md` | GPT-5.6-Luna | xhigh | 8.95M | $1.39 |
| `SOL_HIGH_EVAL.md` | GPT-5.6-Sol | high | 6.74M | $5.08 |
| `SOL_MEDIUM_EVAL.md` | GPT-5.6-Sol | medium | 963K | $1.29 |
| `TERRA_XHIGH_EVAL.md` | GPT-5.6-Terra | xhigh | 7.48M | $3.04 |
| **Total** | | | | **$23.30** |

**Pricing sources:**

- **GPT models:** OpenAI Standard API pricing (platform.openai.com/docs/pricing) applied to
  token counts from Codex session logs (`~/.codex/state_5.sqlite` and per-session JSONL files).
  Cached input tokens billed at the cached rate; output tokens (including reasoning) billed at
  the output rate.
  - gpt-5.5: $5.00/1M input, $0.50/1M cached, $30.00/1M output
  - gpt-5.6-luna: $1.00/1M input, $0.10/1M cached, $6.00/1M output
  - gpt-5.6-sol: $5.00/1M input, $0.50/1M cached, $30.00/1M output
  - gpt-5.6-terra: $2.50/1M input, $0.25/1M cached, $15.00/1M output
- **GLM-5.2:** NeuralWatt API pricing (`api.neuralwatt.com/v1/models`):
  $1.45/1M input, $0.3625/1M cached input, $4.50/1M output. Token counts from opencode database
  (`~/.local/share/opencode/opencode.db`). The calculated cost ($1.79) matches the opencode session
  cost field exactly, confirming the pricing.
- **LUNA_MAX:** $2.11 per user instruction (the messed-up deleted session's cost; other broken
  max repeat sessions ignored per user instruction).

---

## Executive Summary

**Strongest report: SOL_HIGH_EVAL.md** — It identified the most complete set of real issues,
including the unique discovery that `CAP_SYS_RAWIO` is missing from the service unit (a
deployment-blocking finding that most other reports missed), and it correctly traced the PPD
ownership contradiction, MSR encoding bug, delayed rewrite race, and daemon lifecycle problem.
It also provided the most actionable fix recommendations.

**Weakest report: 5.5_HIGH_EVAL.md** — It was the only report to conclude "Requires significant
fixes" rather than "Unsafe to merge or release," understating the severity. It missed the
`CAP_SYS_RAWIO` deployment blocker, the `ProtectSystem=strict` vs `systemctl mask` incompatibility,
the honor-tools dependency API mismatch, and the performance governor substitution issue. It also
reported a command-queue timeout as a release blocker when it is actually a Python 3.14 sandbox
artifact.

**Most important reasons for the ranking:**

1. The MSR PL2 encoding bug is real and confirmed by arithmetic — all reports that mentioned it
   were correct.
2. The PPD ownership contradiction is real and confirmed by code tracing — all reports that
   mentioned it were correct.
3. The `CAP_SYS_RAWIO` missing capability is a real deployment blocker confirmed by the service
   unit file — only SOL_HIGH, SOL_MEDIUM, and TERRA_XHIGH caught it.
4. The `ProtectSystem=strict` vs `systemctl mask` incompatibility is real — only GLM_MAX caught
   it.
5. The honor-tools 0.1.0 API mismatch is real and confirmed by runtime testing — only LUNA_MAX
   caught it, though it is a development-environment issue, not a production issue
   (install-local.sh uses the sibling source).

---

## Issue Status Summary

**As of this evaluation, no code changes have been made.** The repository remains at commit
`34d31f9`. All issues identified across all nine reports remain **UNFIXED**.

### Consolidated Issue Tracker

| ID | Severity | Issue | Status | Files |
|----|----------|-------|--------|-------|
| C1 | Critical | PPD ownership contradiction: service masks PPD but apply still requires `ppd_ok=True` | **UNFIXED** | `application.py:164,353`, `hardware.py:836,874-885` |
| H1 | High | MSR PL2 encoding bug: PL2 enable and time-window bits shifted past bit 63 | **UNFIXED** | `hardware.py:1007-1019` |
| H2 | High | Missing `CAP_SYS_RAWIO` in service unit: MSR open will fail with EPERM in production | **UNFIXED** | `packaging/systemd/honor-control.service:24`, `hardware.py:990` |
| H3 | High | `ProtectSystem=strict` blocks `systemctl mask`: masking silently fails | **UNFIXED** | `packaging/systemd/honor-control.service:20`, `hardware.py:874-885` |
| H4 | High | Delayed rewrite race: stale tasks not cancelled; boolean failures ignored; success reported before enforcement | **UNFIXED** | `application.py:371-373,408-419,374-381` |
| H5 | High | No daemon restore on shutdown/uninstall: PPD/intel_lpmd remain masked | **UNFIXED** | `application.py:181-186`, `hardware.py:844-896`, `scripts/uninstall-local.sh` |
| H6 | High | Startup daemon cleanup can exceed 10s queue timeout (4×5s systemctl calls) | **UNFIXED** | `application.py:164`, `hardware.py:874-885`, `command_queue.py:26` |
| M1 | Medium | Performance governor substitution: `rewrite_epp` leaves `powersave` for performance profiles | **UNFIXED** | `hardware.py:950-958`, `models.py:301` |
| M2 | Medium | Startup reconciliation compares only PPD label, not actual hardware values | **UNFIXED** | `application.py:1029-1031` |
| M3 | Medium | `root_path` abstraction bypass: new methods use absolute paths | **UNFIXED** | `hardware.py:889-891,921-925,990` |
| M4 | Medium | Capability probe insufficiency: only checks `powerprofilesctl` binary, not MSR/EPP/sysfs | **UNFIXED** | `hardware.py:597-619` |
| M5 | Medium | File descriptor leak in `write_rapl_msr`: no `try/finally`; `struct.error` not caught | **UNFIXED** | `hardware.py:990-1025` |
| M6 | Medium | `_last_applied_power_profile` overrides live hardware observations indefinitely | **UNFIXED** | `application.py:1135` |
| M7 | Medium | Zero test coverage for all new methods | **UNFIXED** | All new methods in `hardware.py` and `application.py` |
| M8 | Medium | Honor-tools dependency contract: `>=0.1,<0.2` allows incompatible 0.1.0 from PyPI | **UNFIXED** | `pyproject.toml:20-23`, `hardware.py:822-823` |
| L1 | Low | Documentation mismatch: README claims AMD "sysfs-only EPP" but gate rejects non-MRA-XXX | **UNFIXED** | `README.md:10-16`, `hardware.py:597-619` |
| L2 | Low | `time.sleep(0.1)` in `rewrite_epp` blocks command queue worker thread | **UNFIXED** | `hardware.py:945` |
| L3 | Low | `rewrite_epp` returns success with empty CPU set | **UNFIXED** | `hardware.py:931` |
| L4 | Low | Auto-switch retry loop: failed applies retried every 2s with no backoff | **UNFIXED** | `application.py:1327-1377` |
| L5 | Low | Turbo/max-performance controls persisted but not applied by honor-tools 0.1.0 | **UNFIXED** | `hardware.py:822-823`, `honor/power.py:221-226` |
| L6 | Low | Misplaced `# -- Fan --` comment in FakeHardware | **UNFIXED** | `hardware.py:255` |
| L7 | Low | Redundant local imports of `pathlib` shadow module-level import | **UNFIXED** | `hardware.py:871,918` |
| L8 | Low | Inconsistent sysfs write helpers (`_write_sysfs` vs `_write_int` vs direct `write_text`) | **UNFIXED** | `hardware.py:889-896,1038-1044` |
| L9 | Low | Documentation/CHANGELOG not updated for the overhaul | **UNFIXED** | `docs/safety.md`, `docs/architecture.md`, `CHANGELOG.md` |

---

## Claim-by-Claim Verification

For each model, its major findings are classified as:
- **Confirmed** — correct and well-supported by repository evidence
- **Partially correct** — directionally correct but incomplete or overstated
- **Incorrect** — wrong or based on a misunderstanding
- **Unverifiable** — cannot be confirmed from the repository
- **Low-value / non-issue** — duplicative, trivial, or not actionable

---

### 5.5_HIGH_EVAL.md (GPT-5.5, high effort, $2.51)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: PPD masked but apply still requires `powerprofilesctl set` | **Confirmed** | Correctly traced the ownership contradiction. |
| PP-002: MSR PL2 enable/time-window bits shifted out | **Confirmed** | Arithmetic reproduction matches. |
| PP-003: Delayed rewrites can apply stale profile data | **Confirmed** | No cancellation before overwriting task reference. |
| PP-004: Delayed rewrite failures not reflected in results/snapshots | **Confirmed** | Boolean returns discarded at `application.py:408-419`. |
| PP-005: New hardware methods bypass `root_path` test boundary | **Confirmed** | Absolute paths used throughout new methods. |
| PP-006: Command queue fails in this environment | **Incorrect** | Python 3.14 sandbox artifact, not a code defect. Full suite passes outside sandbox (confirmed by GLM_MAX, LUNA_MAX, SOL_MEDIUM, TERRA_XHIGH). Overstated as a release blocker. |
| PP-007: Compatibility documentation overstates AMD support | **Confirmed** | README claims "sysfs-only EPP" but gate rejects non-MRA-XXX. |

**Missed by this report:**
- `CAP_SYS_RAWIO` missing from service unit (H2)
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- Honor-tools dependency API mismatch (M8)
- Performance governor substitution (M1)
- No daemon restore on shutdown/uninstall (H5)
- Startup daemon cleanup timeout (H6)
- File descriptor leak (M5)
- `time.sleep` blocking (L2)
- Empty CPU set returns success (L3)
- Auto-switch retry loop (L4)
- Turbo/max-performance not applied (L5)

**Verdict assessment:** "Requires significant fixes" understates severity. The MSR bug writes incorrect values to CPU hardware, the PPD contradiction breaks the core feature, and the deployment blockers (CAP_SYS_RAWIO, ProtectSystem) make the central mechanism non-functional in production. "Unsafe to merge or release" is the correct verdict.

---

### 5.5_XHIGH_EVAL.md (GPT-5.5, xhigh effort, $5.23)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: Startup disables PPD before apply path that still requires PPD | **Confirmed** | Same as 5.5_HIGH PP-001, with more detail. |
| PP-002: Service startup persistently masks system daemons without rollback | **Confirmed** | Correctly identified no restore on shutdown/uninstall. |
| PP-003: RAPL MSR PL2 enable/time bits written to wrong positions | **Confirmed** | Same MSR encoding bug. |
| PP-004: Delayed direct writes can fail after API reported success | **Confirmed** | Correctly identified silent failure path. |
| PP-005: Stale delayed rewrite tasks can race later profile changes | **Confirmed** | Same race condition. |
| PP-006: Power capability does not check new required resources | **Confirmed** | Capability probe only checks `powerprofilesctl` binary. |
| PP-007: Pre-existing command queue failure blocks validation | **Incorrect** | Same sandbox artifact as 5.5_HIGH PP-006. |
| PP-008: `stop_competing_power_daemons` can exceed queue timeout | **Confirmed** | 4×5s = 20s worst case vs 10s queue timeout. |
| PP-009: Applied-profile observation depends on PPD even when PPD is disabled | **Confirmed** | `read_power()` derives applied from PPD string. |
| PP-010: New direct hardware methods bypass injectable root path | **Confirmed** | Same as 5.5_HIGH PP-005. |
| PP-011: New overhaul paths have almost no direct tests | **Confirmed** | No tests changed in overhaul range. |
| PP-012: `write_rapl_msr` can leak file descriptors on non-OSError paths | **Confirmed** | No `try/finally`; `struct.error` not caught. |

**Missed by this report:**
- `CAP_SYS_RAWIO` missing from service unit (H2)
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- Honor-tools dependency API mismatch (M8)
- Performance governor substitution (M1)
- Auto-switch retry loop (L4)
- Turbo/max-performance not applied (L5)

---

### GLM_MAX_EVAL.md (GLM-5.2, max effort, $1.79)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: RAPL MSR PL2 enable bit and time window silently truncated | **Confirmed** | Most thorough MSR analysis, including PL2 clamp bit inconsistency. |
| PP-002: Stale delayed-rewrite task not cancelled before scheduling new one | **Confirmed** | Provided concrete test reproduction confirming both tasks fire. |
| PP-003: `systemctl mask` fails under `ProtectSystem=strict` | **Confirmed** | **Unique finding** — only GLM_MAX caught this deployment issue. |
| PP-004: PPD reactivated by D-Bus service activation when `powerprofilesctl set` called | **Confirmed** | Correctly traced D-Bus service activation chain. Compounds PP-003. |
| PP-005: `ProtectKernelModules=true` prevents loading `msr` module | **Partially correct** | `ProtectKernelModules=true` prevents `modprobe`, but if `msr` is already loaded (as on the review host), the device exists. The real blocker is `CAP_SYS_RAWIO` (which GLM_MAX did not identify). |
| PP-006: Zero test coverage for all new methods | **Confirmed** | Thorough enumeration of untested methods. |
| PP-007: `time.sleep` in `rewrite_epp` blocks command queue worker | **Confirmed** | **Unique finding** — only GLM_MAX caught this. |
| PP-008: No cleanup of stopped/masked daemons on shutdown or uninstall | **Confirmed** | Correctly identified lifecycle gap. |
| PP-009: New hardware methods bypass `root_path` abstraction | **Confirmed** | Same as other reports. |
| PP-010: `_delayed_power_rewrite` not coordinated with mutation lock | **Confirmed** | Correctly identified as separate from PP-002 (even after fixing stale task, current task can race with new apply). |
| PP-011: Delayed-rewrite failure not communicated to user | **Confirmed** | Same as other reports' delayed failure findings. |
| PP-012: File descriptor leak in `write_rapl_msr` on error | **Confirmed** | Same as 5.5_XHIGH PP-012. |
| PP-013: Misplaced `# -- Fan --` section comment in FakeHardware | **Low-value** | Trivial cosmetic issue. |
| PP-014: Redundant local imports of `pathlib` | **Low-value** | Trivial style issue. |
| PP-015: Inconsistent sysfs write helpers | **Low-value** | Minor duplication. |
| PP-016: Documentation and CHANGELOG not updated | **Confirmed** | Correct documentation drift finding. |

**Missed by GLM_MAX:**
- `CAP_SYS_RAWIO` missing from service unit (H2) — the most important deployment blocker
- Honor-tools dependency API mismatch (M8)
- Performance governor substitution (M1)
- Startup reconciliation compares only PPD label (M2)
- Capability probe insufficiency (M4)
- Auto-switch retry loop (L4)
- Turbo/max-performance not applied (L5)

**Notable strength:** GLM_MAX was the only report to catch both the `ProtectSystem=strict` vs `systemctl mask` incompatibility (PP-003) and the `time.sleep` blocking issue (PP-007). Its PPD D-Bus reactivation analysis (PP-004) was also unique and insightful.

---

### LUNA_HIGH_EVAL.md (GPT-5.6-Luna, high effort, $0.85)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: PL2 disabled by incorrect MSR bit construction | **Confirmed** | Correct MSR encoding analysis. |
| PP-002: Operation reports "applied" before delayed enforcement and ignores failures | **Confirmed** | Correctly identified both the premature success and ignored booleans. |
| PP-003: Startup permanently masks system power managers without reversible ownership | **Confirmed** | Correctly identified lifecycle/restore gap. |
| PP-004: Performance profiles end in `powersave` despite requesting `performance` | **Confirmed** | Correctly identified governor substitution. |
| PP-005: Startup reconciliation treats PPD label as proof of complete application | **Confirmed** | Correctly identified label-only comparison. |
| PP-006: Multiple delayed rewrite tasks not generation-safe or fully cancelled | **Confirmed** | Same race condition as other reports. |
| PP-007: Direct MSR I/O has weak short-read/short-write and descriptor handling | **Confirmed** | Same fd leak and `struct.error` issue. |
| PP-008: Compatibility documentation contradicts actual platform gate | **Confirmed** | Same documentation mismatch. |

**Missed by this report:**
- PPD ownership contradiction (C1) — did not identify that masking PPD breaks the apply path
- `CAP_SYS_RAWIO` missing from service unit (H2)
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- Honor-tools dependency API mismatch (M8)
- No daemon restore on shutdown/uninstall (H5) — partially covered by PP-003 but focused on masking, not restore
- Startup daemon cleanup timeout (H6)
- Capability probe insufficiency (M4)
- `time.sleep` blocking (L2)
- Empty CPU set returns success (L3)
- Auto-switch retry loop (L4)
- Turbo/max-performance not applied (L5)

**Notable strength:** Correctly identified the sandbox command-queue timeout as an environment limitation, not a code defect: "the sandbox rejecting asyncio's self-pipe write with `PermissionError: [Errno 1] Operation not permitted`."

---

### LUNA_MAX_EVAL.md (GPT-5.6-Luna, max effort, $2.11)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: Resolved `honor-tools` API makes every real profile apply fail | **Partially correct** | **Unique finding** — correctly discovered the `PowerProfile.__init__()` mismatch. However, this only affects development environments using PyPI honor-tools 0.1.0; production installs from sibling source via `install-local.sh`. Severity overstated as Critical. |
| PP-002: Startup masks system power managers and never restores them | **Confirmed** | Correctly identified lifecycle gap and PPD ownership contradiction. |
| PP-003: Direct RAPL encoder drops PL2 enable and time-window bits | **Confirmed** | Correct MSR encoding analysis. |
| PP-004: Apply success returned before delayed enforcement, delayed failures lost | **Confirmed** | Correctly identified premature success and ignored failures. |
| PP-005: Performance profile ends with `powersave`, not requested governor | **Confirmed** | Correctly identified governor substitution. |
| PP-006: Startup reconciliation trusts PPD profile label instead of hardware state | **Confirmed** | Correctly identified label-only comparison. |
| PP-007: Daemon cleanup can exceed hardware queue deadline and abort startup | **Confirmed** | Correctly identified 4×5s vs 10s timeout. |
| PP-008: Fire-and-forget rewrites not generation-safe or fully owned | **Confirmed** | Most thorough race analysis, including A/B interleaving within the queue. |
| PP-009: Capability probing much weaker than mechanisms being changed | **Confirmed** | Correctly identified capability probe insufficiency. |
| PP-010: Failed auto-switch applies retry forever every two seconds | **Confirmed** | **Unique finding** — only LUNA_MAX caught this. |
| PP-011: Hardware success and persistence failure can leave contradictory state | **Confirmed** | Correctly identified persistence ordering issue. |
| PP-012: New high-risk paths have no meaningful production-adapter tests | **Confirmed** | Thorough test gap analysis. |
| PP-013: New power I/O bypasses adapter's injectable root | **Confirmed** | Same as other reports. |
| PP-014: AMD compatibility statement does not match actual behavior | **Confirmed** | Same documentation mismatch. |

**Missed by LUNA_MAX:**
- `CAP_SYS_RAWIO` missing from service unit (H2)
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- `time.sleep` blocking (L2)
- Empty CPU set returns success (L3)
- Turbo/max-performance not applied (L5)

**Notable strengths:** Deepest investigation of any report. Uniquely discovered the honor-tools API mismatch through runtime testing. Uniquely caught the auto-switch retry loop. Most thorough test coverage analysis. Most detailed architectural recommendations.

---

### LUNA_XHIGH_EVAL.md (GPT-5.6-Luna, xhigh effort, $1.39)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: Overhaul disables PPD while apply contract still requires PPD | **Confirmed** | Correctly traced PPD ownership contradiction. |
| PP-002: System-wide daemon masks persist after shutdown, failure, or uninstall | **Confirmed** | Correctly identified lifecycle gap. |
| PP-003: PL2 enable and time-window bits shifted out of RAPL register | **Confirmed** | Correct MSR encoding analysis. |
| PP-004: Delayed EPP rewrite makes performance profile leave `powersave` | **Confirmed** | Correctly identified governor substitution. |
| PP-005: Delayed hardware failures ignored after state persisted and success returned | **Confirmed** | Correctly identified premature success and ignored failures. |
| PP-006: Startup can time out because daemon stop exceeds queue deadline | **Confirmed** | Correctly identified 4×5s vs 10s timeout. |
| PP-007: Power capability reported from executable check, not from required mechanisms | **Confirmed** | Correctly identified capability probe insufficiency. |
| PP-008: Raw MSR I/O not exception-safe or write-complete | **Confirmed** | Same fd leak and short I/O issue. |
| PP-009: Delayed tasks not fully owned or ordered by service lifecycle | **Confirmed** | Same race condition. |
| PP-010: Startup reconciliation compares only profile name, not definition | **Confirmed** | Correctly identified label-only comparison. |
| PP-011: New hardware paths bypass adapter's injectable root | **Confirmed** | Same as other reports. |
| PP-012: Existing command-queue test contract broken in reviewed environment | **Incorrect** | Same sandbox artifact. Correctly identified as pre-existing and environment-specific, but still listed as a finding. |
| PP-013: README compatibility wording does not match actual platform gate | **Confirmed** | Same documentation mismatch. |

**Missed by this report:**
- `CAP_SYS_RAWIO` missing from service unit (H2)
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- Honor-tools dependency API mismatch (M8)
- `time.sleep` blocking (L2)
- Empty CPU set returns success (L3)
- Auto-switch retry loop (L4)
- Turbo/max-performance not applied (L5)

---

### SOL_HIGH_EVAL.md (GPT-5.6-Sol, high effort, $5.08)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: Startup disables a dependency that every successful profile apply still requires | **Confirmed** | Correctly traced PPD ownership contradiction with precise line references. |
| PP-002: Direct MSR encoding silently writes PL2 disabled and loses time window | **Confirmed** | Correct MSR encoding analysis with mocked reproduction. |
| PP-003: Shipped service sandbox cannot open MSR device | **Confirmed** | **Unique among high-effort reports** — correctly identified `CAP_SYS_RAWIO` missing from `CapabilityBoundingSet`. Cited kernel source. |
| PP-004: Operation reports success before new required work runs, ignores normal failures, permits stale rewrites | **Confirmed** | Combined finding covering delayed race + ignored failures. |
| PP-005: Service startup persistently masks system power daemons with no ownership or restoration policy | **Confirmed** | Correctly identified lifecycle gap. |
| PP-006: Startup reconciliation compares only PPD label, not profile definition or hardware state | **Confirmed** | Correctly identified label-only comparison. |
| PP-007: New production methods bypass adapter's root abstraction | **Confirmed** | Same as other reports. |
| PP-008: Daemon shutdown can exceed command queue deadline and prevent service startup | **Confirmed** | Correctly identified 4×5s vs 10s timeout. |
| PP-009: EPP rewrite can return success without writing or verifying requested state | **Confirmed** | **Unique finding** — correctly identified empty CPU set returns success, readback content discarded, and governor write results ignored. |
| PP-010: Applied state can permanently hide external changes and delayed failures | **Confirmed** | Correctly identified `_last_applied_power_profile` override. |
| PP-011: Documentation describes behavior and compatibility that code does not provide | **Confirmed** | Most thorough documentation analysis, covering README, hardware-support, and architecture docs. |

**Missed by this report:**
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- Honor-tools dependency API mismatch (M8)
- Performance governor substitution (M1)
- `time.sleep` blocking (L2)
- Auto-switch retry loop (L4)
- Turbo/max-performance not applied (L5)

**Notable strengths:** Only report to identify both `CAP_SYS_RAWIO` (PP-003) and the empty CPU set issue (PP-009). Most actionable fix recommendations. Best severity prioritization. Most thorough documentation analysis. Correctly identified the command-queue timeout as a sandbox artifact.

---

### SOL_MEDIUM_EVAL.md (GPT-5.6-Sol, medium effort, $1.29)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: Startup disables a required dependency and leaves host power services persistently masked | **Confirmed** | Combined PPD ownership + lifecycle finding. |
| PP-002: RAPL MSR encoding drops PL2 enable and time-window bits | **Confirmed** | Correct MSR encoding analysis. |
| PP-003: API reports success before decisive correction and discards its failures | **Confirmed** | Combined delayed race + ignored failures finding. |
| PP-004: Performance profile intentionally changed to `powersave` governor while state claims fully applied | **Confirmed** | Correctly identified governor substitution. |
| PP-005: Delayed rewrites not superseded, stale profiles can overwrite newer selections | **Confirmed** | Same race condition. |
| PP-006: Capability probing does not cover resources required by new implementation | **Confirmed** | Correctly identified capability probe insufficiency. |
| PP-007: EPP rewrite can return success without any CPUs and does not verify requested values | **Confirmed** | Same as SOL_HIGH PP-009. |
| PP-008: MSR file descriptors can leak on intermediate errors and short I/O not validated | **Confirmed** | Same fd leak issue. |
| PP-009: Compatibility and behavior documentation inaccurate after overhaul | **Confirmed** | Same documentation mismatch. |

**Missed by this report:**
- `CAP_SYS_RAWIO` missing from service unit (H2) — despite SOL_HIGH catching it, the medium-effort run missed it
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- Honor-tools dependency API mismatch (M8)
- No daemon restore on shutdown/uninstall (H5) — partially covered by PP-001
- Startup daemon cleanup timeout (H6)
- Startup reconciliation label-only comparison (M2)
- `time.sleep` blocking (L2)
- Auto-switch retry loop (L4)
- Turbo/max-performance not applied (L5)

**Notable strength:** Best value-for-money report. At $1.29, it identified the governor substitution and EPP empty CPU set issue that several higher-cost reports missed. Compact and high signal-to-noise.

---

### TERRA_XHIGH_EVAL.md (GPT-5.6-Terra, xhigh effort, $3.04)

| Finding | Classification | Notes |
|---------|---------------|-------|
| PP-001: Startup masks the daemon every profile application still requires | **Confirmed** | Correctly traced PPD ownership contradiction. |
| PP-002: Packaged service lacks capability required by new MSR path | **Confirmed** | Correctly identified `CAP_SYS_RAWIO` missing. |
| PP-003: Final RAPL/EPP outcome neither verified nor represented in public state | **Confirmed** | Combined delayed failure + no readback finding. |
| PP-004: Rapid profile changes can apply an obsolete delayed rewrite | **Confirmed** | Same race condition. |
| PP-005: Configured performance governor silently changed to `powersave` | **Confirmed** | Correctly identified governor substitution. |
| PP-006: Turbo and max-performance controls persist but are not applied | **Confirmed** | **Unique finding** — only TERRA_XHIGH caught that honor-tools 0.1.0 unconditionally writes `no_turbo=0` and `max_perf_pct=100`, ignoring profile values. |
| PP-007: AMD compatibility statement conflicts with implementation | **Confirmed** | Same documentation mismatch. |

**Missed by this report:**
- `ProtectSystem=strict` blocks `systemctl mask` (H3)
- Honor-tools dependency API mismatch (M8) — identified the turbo/max-perf issue but not the constructor mismatch
- No daemon restore on shutdown/uninstall (H5)
- Startup daemon cleanup timeout (H6)
- Startup reconciliation label-only comparison (M2)
- Capability probe insufficiency (M4)
- `root_path` abstraction bypass (M3)
- File descriptor leak (M5)
- `time.sleep` blocking (L2)
- Empty CPU set returns success (L3)
- Auto-switch retry loop (L4)

**Notable strength:** Uniquely caught the turbo/max-performance controls not being applied (PP-006). Also correctly identified `CAP_SYS_RAWIO`. Good architectural recommendations despite fewer total findings.

---

## Missed Issues

### Issues missed by all reports:

1. **`_write_sysfs` does not use `self._rooted()`**: The `_write_sysfs` helper at
   `hardware.py:1038-1044` writes to absolute paths, but this is a pre-existing issue, not
   introduced by the overhaul. Low severity.

2. **`stop_competing_power_daemons` writes HWP dynamic boost without checking capability**: The
   HWP write at `hardware.py:889-896` happens unconditionally on supported platforms, even if
   the power capability is not writable. This means the service modifies HWP state even when
   power profiles are unavailable. Partially noted by some reports but not called out as a
   separate issue.

3. **`_delayed_power_rewrite` captures a `PowerProfileState` object by reference**: If the
   profile definition is edited between the apply and the delayed rewrite (0.5s later), the
   delayed rewrite writes the old definition. GLM_MAX mentioned this briefly in the architecture
   section but did not file it as a finding.

---

## Bad or Risky Recommendations

### 1. GLM_MAX PP-003: Add `ReadWritePaths=/etc/systemd/system` to the systemd unit

**Problem:** This reduces hardening and still doesn't solve the fundamental PPD ownership
contradiction. The service would be able to mask PPD, but PPD would still be reactivated by
D-Bus service activation when `powerprofilesctl set` is called.

**Better alternative:** Drop the masking approach entirely. Either keep PPD running and
coordinate with it, or remove PPD from the required apply path and rely on the direct MSR
write (after fixing the encoding and capability issues).

### 2. 5.5_HIGH PP-006: Treat command-queue timeout as a release blocker

**Problem:** The timeout is a Python 3.14 sandbox artifact, not a code defect. Blocking
release on an environment-specific issue would be incorrect.

**Better alternative:** Verify the test suite passes on supported Python versions (3.11-3.13)
and document that Python 3.14 may have sandbox compatibility issues.

### 3. LUNA_MAX PP-001: Treat the honor-tools API mismatch as Critical

**Problem:** The mismatch only affects development environments using PyPI honor-tools 0.1.0.
Production installations using `install-local.sh` install from the sibling source which has
the correct fields.

**Better alternative:** Rate it as Medium (dependency contract issue). Fix by either pinning
the dependency version or adding a compatibility test.

### 4. Multiple reports: Make delayed rewrite synchronous

**Problem:** Several reports suggested making the delayed rewrite synchronous (blocking the
apply return until it completes). This would add 0.5s+ latency to every profile change,
degrading user experience.

**Better alternative:** Use a pending/applied state machine: return "pending" immediately,
then publish "applied" or "failed" after the delayed rewrite completes. This preserves
responsiveness while ensuring correctness.

---

## Comparative Scorecard

Scored 0-10 on each criterion. Consistent standards applied across all nine reports.

| Criterion | 5.5_HIGH | 5.5_XHIGH | GLM_MAX | LUNA_HIGH | LUNA_MAX | LUNA_XHIGH | SOL_HIGH | SOL_MEDIUM | TERRA_XHIGH |
|-----------|----------|-----------|---------|-----------|----------|------------|----------|------------|-------------|
| Accuracy | 6 | 7 | 8 | 7 | 8 | 8 | 9 | 8 | 8 |
| Depth | 5 | 7 | 8 | 6 | 9 | 8 | 8 | 7 | 7 |
| Completeness | 5 | 7 | 7 | 6 | 8 | 8 | 9 | 7 | 7 |
| Prioritization | 5 | 7 | 7 | 7 | 8 | 8 | 9 | 8 | 8 |
| Fix quality | 6 | 7 | 8 | 7 | 8 | 8 | 8 | 7 | 7 |
| Arch. understanding | 6 | 7 | 8 | 7 | 8 | 8 | 9 | 8 | 8 |
| Signal-to-noise | 6 | 7 | 7 | 7 | 7 | 8 | 8 | 8 | 8 |
| Overall usefulness | 5 | 7 | 8 | 7 | 8 | 8 | 9 | 8 | 8 |

---

## Final Ranking

Ranked from best to worst, with concrete technical evidence.

### 1. SOL_HIGH_EVAL.md ($5.08, GPT-5.6-Sol, high)

**Best overall.** Uniquely caught the `CAP_SYS_RAWIO` deployment blocker (PP-003), which is
the single most important deployment issue and was missed by six of nine reports. Correctly
identified all major issues: PPD ownership contradiction, MSR encoding bug, delayed rewrite
race, daemon lifecycle, EPP empty CPU set, `_last_applied_power_profile` override. Strongest
fix recommendations with concrete code. Best severity prioritization. Most thorough
documentation analysis. Correctly identified the command-queue timeout as a sandbox artifact.
Only weakness: missed `ProtectSystem=strict` vs `systemctl mask` and the governor substitution.

### 2. LUNA_MAX_EVAL.md ($2.11, GPT-5.6-Luna, max)

**Deepest investigation.** Uniquely discovered the honor-tools dependency API mismatch
through runtime testing (PP-001). Uniquely caught the auto-switch retry loop (PP-010). Most
thorough test coverage analysis. Most detailed architectural recommendations. Identified the
persistence ordering issue (PP-011). Slightly overstated the dependency mismatch severity
(Critical instead of Medium for a dev-only issue). Missed `CAP_SYS_RAWIO` and
`ProtectSystem=strict`.

### 3. GLM_MAX_EVAL.md ($1.79, GLM-5.2, max)

**Most unique findings.** Only report to catch `ProtectSystem=strict` vs `systemctl mask`
incompatibility (PP-003) and `time.sleep` blocking (PP-007). Best PPD D-Bus reactivation
analysis (PP-004). Most thorough positive observations section. Provided concrete test
reproduction of the stale-task race. Missed `CAP_SYS_RAWIO` (the most important deployment
blocker), the governor substitution, and the honor-tools mismatch. Best value at $1.79.

### 4. SOL_MEDIUM_EVAL.md ($1.29, GPT-5.6-Sol, medium)

**Best value-for-money.** At $1.29, identified the governor substitution and EPP empty CPU
set issue that several higher-cost reports missed. Compact and high signal-to-noise. Missed
`CAP_SYS_RAWIO` (despite SOL_HIGH catching it) and `ProtectSystem=strict`. Less depth due to
lower reasoning effort, but every finding was correct.

### 5. LUNA_XHIGH_EVAL.md ($1.39, GPT-5.6-Luna, xhigh)

**Solid analysis.** Correctly identified all major issues it covered. Good architectural
recommendations. Did not catch `CAP_SYS_RAWIO`, `ProtectSystem=strict`, or the honor-tools
mismatch. Correctly identified the sandbox timeout as environmental.

### 6. TERRA_XHIGH_EVAL.md ($3.04, GPT-5.6-Terra, xhigh)

**Unique turbo finding.** Correctly identified `CAP_SYS_RAWIO` (PP-002). Uniquely caught
turbo/max-performance controls not being applied (PP-006). Good architectural recommendations.
Fewer total findings than top reports. Missed `ProtectSystem=strict`, honor-tools mismatch,
daemon lifecycle restore, startup timeout, and several other issues.

### 7. 5.5_XHIGH_EVAL.md ($5.23, GPT-5.5, xhigh)

**Good coverage but missed key deployment issues.** Identified most major issues but missed
`CAP_SYS_RAWIO`, `ProtectSystem=strict`, honor-tools mismatch, and governor substitution.
Overstated the command-queue timeout as a release blocker. Most expensive report per finding.

### 8. LUNA_HIGH_EVAL.md ($0.85, GPT-5.6-Luna, high)

**Concise but incomplete.** Good analysis of the issues it covered, including the governor
substitution that many reports missed. Correctly identified the sandbox timeout as
environmental. Missed the PPD ownership contradiction (the most important issue), `CAP_SYS_RAWIO`,
and `ProtectSystem=strict`. Least expensive report.

### 9. 5.5_HIGH_EVAL.md ($2.51, GPT-5.5, high)

**Weakest.** Only report to conclude "Requires significant fixes" instead of "Unsafe to merge
or release," understating severity. Missed `CAP_SYS_RAWIO`, `ProtectSystem=strict`, honor-tools
mismatch, governor substitution, daemon lifecycle restore, startup timeout, capability probe
insufficiency, fd leak, `time.sleep` blocking, empty CPU set, auto-switch retry, and turbo
controls. Overstated the command-queue timeout as a release blocker. Least depth and
completeness.

---

## Recommended Consolidated Action Plan

A deduplicated, severity-ordered list of findings worth addressing. All items are currently
**UNFIXED**.

### Critical

#### C1: PPD Ownership Contradiction

- **Problem:** Service masks PPD at startup but still requires `ppd_ok=True` for profile apply
  success.
- **Evidence:** `application.py:164` (mask), `application.py:353` (require ppd_ok),
  `hardware.py:836` (ppd_ok from powerprofilesctl), `hardware.py:874-885` (stop+mask)
- **User/system impact:** Every profile apply after startup returns partial failure; delayed
  rewrite never scheduled; desired state not persisted. Core feature is broken on every
  supported platform.
- **Recommended fix:** Choose one ownership model. Either keep PPD running and coordinate, or
  remove PPD from the mandatory success gate when direct control mode is active.
- **Relevant files:** `honor_control/backend/application.py`, `honor_control/backend/hardware.py`
- **Suggested tests:** Integration test with PPD active/stopped/masked; assert apply succeeds
  in the chosen ownership mode.

### High

#### H1: MSR PL2 Encoding Bug

- **Problem:** PL2 enable bit and time window are shifted past bit 63 and masked away.
- **Evidence:** `hardware.py:1014-1019`; arithmetic reproduction confirms PL2 enable=0, PL2
  time=0.
- **User/system impact:** PL2 burst power limit is disabled; profile does not deliver intended
  power envelope.
- **Recommended fix:** Build the 64-bit value with absolute bit positions in a single step:
  `val = pl1_units | (1<<15) | (1<<16) | (tw1<<17) | (pl2_units<<32) | (1<<47) | (tw2<<49)`.
- **Relevant files:** `honor_control/backend/hardware.py`
- **Suggested tests:** Pure unit test for MSR encoding with known values; verify PL1/PL2
  enable, units, and time windows.

#### H2: Missing `CAP_SYS_RAWIO` in Service Unit

- **Problem:** `CapabilityBoundingSet` omits `CAP_SYS_RAWIO`, which the Linux MSR driver
  requires to open `/dev/cpu/0/msr`.
- **Evidence:** `packaging/systemd/honor-control.service:24`; kernel `msr_open()` checks
  `capable(CAP_SYS_RAWIO)`.
- **User/system impact:** Every `write_rapl_msr` call fails with EPERM in production; failure
  is silently swallowed.
- **Recommended fix:** Either add `CAP_SYS_RAWIO` to `CapabilityBoundingSet` (after security
  review) or remove the direct MSR path and use sysfs only.
- **Relevant files:** `packaging/systemd/honor-control.service`, `honor_control/backend/hardware.py`
- **Suggested tests:** Packaging test comparing required capabilities vs. service unit;
  integration test under the production unit's hardening.

#### H3: `ProtectSystem=strict` Blocks `systemctl mask`

- **Problem:** `systemctl mask` writes to `/etc/systemd/system/` which is read-only under
  `ProtectSystem=strict`.
- **Evidence:** `packaging/systemd/honor-control.service:20`; `hardware.py:874-885` with
  `check=False, stderr=DEVNULL`.
- **User/system impact:** PPD is stopped but not masked; D-Bus reactivates it when
  `powerprofilesctl set` is called, defeating the purpose of stopping it.
- **Recommended fix:** Drop the masking approach. If daemon management is needed, perform it
  in `install-local.sh` (outside the sandbox) or use `systemctl mask --runtime` with
  `ReadWritePaths=/run/systemd/system`.
- **Relevant files:** `honor_control/backend/hardware.py`, `packaging/systemd/honor-control.service`
- **Suggested tests:** Verify no `systemctl mask` calls occur at runtime; if install-time
  masking is added, test it outside the sandbox.

#### H4: Delayed Rewrite Race and Silent Failures

- **Problem:** Stale delayed tasks can clobber newer profiles; boolean failures are ignored;
  success is reported before enforcement completes.
- **Evidence:** `application.py:371-373` (no cancel), `application.py:408-419` (return values
  discarded), `application.py:374-381` (success before delayed rewrite).
- **User/system impact:** Wrong power profile applied during rapid changes; user sees "applied"
  when hardware enforcement failed.
- **Recommended fix:** Cancel previous task before scheduling new one; add generation check
  before writing; inspect boolean returns; publish pending/applied/failed state.
- **Relevant files:** `honor_control/backend/application.py`
- **Suggested tests:** Apply A then B within 0.5s; assert only B's values reach hardware. Make
  delayed operations return False; assert failure is visible.

#### H5: No Daemon Restore on Shutdown/Uninstall

- **Problem:** PPD and `intel_lpmd` remain masked/stopped after service shutdown or uninstall.
- **Evidence:** `application.py:181-186` (no restore in shutdown);
  `scripts/uninstall-local.sh` (no unmask).
- **User/system impact:** System loses its standard power manager permanently after
  installing/uninstalling honor-control.
- **Recommended fix:** Add `restore_competing_power_daemons()` to shutdown and uninstall; or
  remove masking entirely.
- **Relevant files:** `honor_control/backend/application.py`,
  `honor_control/backend/hardware.py`, `scripts/uninstall-local.sh`
- **Suggested tests:** Test that shutdown/uninstall restores daemon state.

#### H6: Startup Daemon Cleanup Timeout

- **Problem:** `stop_competing_power_daemons` performs 4 sequential `systemctl` calls, each
  with 5s timeout, totaling up to 20s — exceeding the 10s queue timeout.
- **Evidence:** `hardware.py:874-885` (4×5s), `command_queue.py:26` (10s default),
  `application.py:164` (no explicit timeout override).
- **User/system impact:** Slow systemd can cause service startup to fail or enter a restart
  loop.
- **Recommended fix:** Use a bounded total timeout smaller than the queue timeout, or move
  daemon management to install-time.
- **Relevant files:** `honor_control/backend/application.py`,
  `honor_control/backend/hardware.py`
- **Suggested tests:** Mock slow `systemctl` calls; assert startup remains bounded.

### Medium

#### M1: Performance Governor Substitution

- **Problem:** `rewrite_epp` leaves governor at `powersave` for performance profiles while the
  API reports success.
- **Evidence:** `hardware.py:950-958`; `models.py:301` (governor="performance").
- **User/system impact:** Profile definition says `performance` but actual governor is
  `powersave`. Silent contract violation.
- **Recommended fix:** Document the effective governor in the profile definition, or return a
  partial result when the governor is substituted.
- **Relevant files:** `honor_control/backend/hardware.py`, `honor_control/core/models.py`
- **Suggested tests:** Assert final governor/EPP for every built-in profile combination.

#### M2: Startup Reconciliation Compares Only PPD Label

- **Problem:** Reconciliation skips when PPD label matches, ignoring actual RAPL/EPP/governor
  values.
- **Evidence:** `application.py:1029-1031`.
- **User/system impact:** After reboot, PPD label may match but hardware values may have
  drifted; service skips reapplication.
- **Recommended fix:** Compare full profile definition against observed hardware values, or
  always reapply on startup.
- **Relevant files:** `honor_control/backend/application.py`
- **Suggested tests:** Same PPD label but mismatched RAPL; assert reconciliation reapplies.

#### M3: `root_path` Abstraction Bypass

- **Problem:** New hardware methods use absolute paths, making them untestable with fake
  filesystems.
- **Evidence:** `hardware.py:889-891, 921-925, 990`.
- **User/system impact:** Cannot safely unit-test the new privileged methods; future tests may
  accidentally touch host hardware.
- **Recommended fix:** Route all sysfs paths through `self._rooted()`; inject MSR and systemctl
  collaborators.
- **Relevant files:** `honor_control/backend/hardware.py`
- **Suggested tests:** Fake-root tests for EPP rewrite, HWP, and MSR encoding.

#### M4: Capability Probe Insufficiency

- **Problem:** `get_power_capability` only checks for `powerprofilesctl` binary, not
  MSR/EPP/sysfs resources.
- **Evidence:** `hardware.py:597-619`.
- **User/system impact:** UI offers power profiles on systems where the direct write path
  cannot work.
- **Recommended fix:** Add per-mechanism capability probes for MSR, EPP, governor, HWP, and
  service permissions.
- **Relevant files:** `honor_control/backend/hardware.py`
- **Suggested tests:** Capability matrix for missing MSR, missing EPP, missing intel_pstate.

#### M5: File Descriptor Leak in `write_rapl_msr`

- **Problem:** No `try/finally` around `os.open/os.close`; `struct.error` not caught.
- **Evidence:** `hardware.py:990-1025`.
- **User/system impact:** Repeated failures could leak file descriptors; `struct.error`
  propagates uncaught.
- **Recommended fix:** Use `try/finally` or context managers; catch `struct.error` and
  `ValueError`.
- **Relevant files:** `honor_control/backend/hardware.py`
- **Suggested tests:** Mock short reads and mid-operation exceptions; assert no fd leak.

#### M6: `_last_applied_power_profile` Overrides Live Observations

- **Problem:** Once set, `_last_applied_power_profile` overrides live hardware observations
  indefinitely.
- **Evidence:** `application.py:1135`: `applied_profile=self._last_applied_power_profile or pw.applied_profile`.
- **User/system impact:** External changes to power state are hidden from the user; snapshots
  show stale applied profile.
- **Recommended fix:** Keep "last verified" and "currently observed" as separate fields.
- **Relevant files:** `honor_control/backend/application.py`
- **Suggested tests:** Apply profile, mutate observed state, refresh; assert drift is visible.

#### M7: Zero Test Coverage for New Methods

- **Problem:** No tests changed in the overhaul range; all new methods are untested.
- **Evidence:** `git diff --name-status 4d8994a..HEAD` shows no test file changes.
- **User/system impact:** MSR encoding bug, race condition, and deployment issues all
  undetectable by the test suite.
- **Recommended fix:** Add tests for MSR encoding, delayed rewrite scheduling/cancellation,
  startup reconciliation, daemon management, EPP rewrite, and GUI dirty flag.
- **Relevant files:** `tests/test_application.py`, `tests/test_hardware.py`, `tests/test_gui.py`
- **Suggested tests:** See individual findings above.

#### M8: Honor-Tools Dependency Contract

- **Problem:** `pyproject.toml` allows `honor-tools>=0.1,<0.2` but 0.1.0 from PyPI lacks
  `turbo_enabled`/`max_perf_pct`.
- **Evidence:** `pyproject.toml:20-23`; installed `honor/config.py:25-33` (5 fields); sibling
  source (7 fields).
- **User/system impact:** Development environments using PyPI honor-tools 0.1.0 cannot apply
  profiles. Production installs from sibling source are unaffected.
- **Recommended fix:** Pin to a specific version or add a compatibility test.
- **Relevant files:** `pyproject.toml`
- **Suggested tests:** Run adapter against minimum and maximum supported dependency versions.

### Low

#### L1: Documentation Mismatch

- **Problem:** README claims AMD "sysfs-only EPP" but platform gate rejects non-MRA-XXX
  hardware.
- **Evidence:** `README.md:10-16`; `hardware.py:597-619`.
- **Recommended fix:** Document actual fail-closed behavior for unsupported platforms.
- **Relevant files:** `README.md`, `docs/hardware-support.md`

#### L2: `time.sleep` in `rewrite_epp` Blocks Worker

- **Problem:** Blocking sleep on the command queue worker thread.
- **Evidence:** `hardware.py:945`.
- **Recommended fix:** Reduce retry count/sleep duration, or move retries to async code.
- **Relevant files:** `honor_control/backend/hardware.py`

#### L3: `rewrite_epp` Returns Success with Empty CPU Set

- **Problem:** `all_ok` remains `True` if no CPU directories are found.
- **Evidence:** `hardware.py:931`.
- **Recommended fix:** Return `False` or `unavailable` when `cpu_dirs` is empty.
- **Relevant files:** `honor_control/backend/hardware.py`

#### L4: Auto-Switch Retry Loop

- **Problem:** Failed auto-switch applies retried every 2 seconds with no backoff.
- **Evidence:** `application.py:1327-1377`.
- **Recommended fix:** Add backoff/latching; retry only on new stable source event.
- **Relevant files:** `honor_control/backend/application.py`

#### L5: Turbo/Max-Performance Controls Not Applied

- **Problem:** `honor-tools` unconditionally writes `no_turbo=0` and `max_perf_pct=100`,
  ignoring profile values.
- **Evidence:** `honor/power.py:221-226`; `hardware.py:822-823`.
- **Recommended fix:** Update the dependency or apply/verify these values in the adapter.
- **Relevant files:** `honor_control/backend/hardware.py`, `honor/power.py`

#### L6: Misplaced `# -- Fan --` Comment

- **Problem:** Section comment ended up on the same line as
  `stop_competing_power_daemons` log call.
- **Evidence:** `hardware.py:255`.
- **Recommended fix:** Move to its own line before `read_fan`.
- **Relevant files:** `honor_control/backend/hardware.py`

#### L7: Redundant Local Imports

- **Problem:** `pathlib` re-imported locally despite module-level import.
- **Evidence:** `hardware.py:871,918`.
- **Recommended fix:** Remove redundant local imports; move stdlib imports to module level.
- **Relevant files:** `honor_control/backend/hardware.py`

#### L8: Inconsistent Sysfs Write Helpers

- **Problem:** Three different patterns for the same sysfs write operation.
- **Evidence:** `hardware.py:889-896` (direct `write_text`), `1038-1044` (`_write_sysfs`),
  `1184-1189` (`_write_int`).
- **Recommended fix:** Use `self._write_sysfs` consistently; consider unifying `_write_int`.
- **Relevant files:** `honor_control/backend/hardware.py`

#### L9: Documentation/CHANGELOG Not Updated

- **Problem:** Overhaul adds significant new behavior but docs/CHANGELOG not updated.
- **Evidence:** `docs/safety.md`, `docs/architecture.md`, `CHANGELOG.md`.
- **Recommended fix:** Add safety section for daemon masking, MSR writes, EPP rewrite;
  add CHANGELOG entry.
- **Relevant files:** `docs/safety.md`, `docs/architecture.md`, `CHANGELOG.md`

---

## Per-Report Issue Coverage Matrix

The table below shows which reports identified each consolidated issue. **All issues remain
UNFIXED.**

| Issue | Sev | 5.5_H | 5.5_X | GLM_M | LUNA_H | LUNA_M | LUNA_X | SOL_H | SOL_M | TERRA_X |
|-------|------|-------|-------|-------|--------|--------|--------|-------|-------|---------|
| C1: PPD ownership contradiction | Crit | Yes | Yes | Partial | No | Yes | Yes | Yes | Yes | Yes |
| H1: MSR PL2 encoding bug | High | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | No |
| H2: Missing CAP_SYS_RAWIO | High | No | No | No | No | No | No | Yes | No | Yes |
| H3: ProtectSystem vs mask | High | No | No | Yes | No | No | No | No | No | No |
| H4: Delayed rewrite race + silent failures | High | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| H5: No daemon restore on shutdown/uninstall | High | No | Yes | Yes | Partial | Yes | Yes | Yes | Partial | No |
| H6: Startup daemon cleanup timeout | High | No | Yes | No | No | Yes | Yes | Yes | No | No |
| M1: Performance governor substitution | Med | No | No | No | Yes | Yes | Yes | No | Yes | Yes |
| M2: Reconciliation compares only PPD label | Med | No | No | No | Yes | Yes | Yes | Yes | No | No |
| M3: root_path abstraction bypass | Med | Yes | Yes | Yes | No | Yes | Yes | Yes | Partial | No |
| M4: Capability probe insufficiency | Med | No | Yes | No | No | Yes | Yes | No | Yes | No |
| M5: File descriptor leak | Med | No | Yes | Yes | Yes | No | Yes | No | Yes | No |
| M6: _last_applied override | Med | No | Partial | No | No | No | No | Yes | No | Yes |
| M7: Zero test coverage | Med | Partial | Yes | Yes | Partial | Yes | Yes | Yes | Yes | Partial |
| M8: Honor-tools dependency mismatch | Med | No | No | No | No | Yes | No | No | No | Partial |
| L1: Documentation mismatch | Low | Yes | No | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| L2: time.sleep blocking | Low | No | No | Yes | No | No | No | No | No | No |
| L3: Empty CPU set returns success | Low | No | No | No | No | No | No | Yes | Yes | No |
| L4: Auto-switch retry loop | Low | No | No | No | No | Yes | No | No | No | No |
| L5: Turbo/max-perf not applied | Low | No | No | No | No | No | No | No | No | Yes |
| L6: Misplaced comment | Low | No | No | Yes | No | No | No | No | No | No |
| L7: Redundant imports | Low | No | No | Yes | No | No | No | No | No | No |
| L8: Inconsistent sysfs helpers | Low | No | No | Yes | No | No | No | No | No | No |
| L9: Docs/CHANGELOG not updated | Low | No | No | Yes | No | No | No | No | No | No |

**Legend:** 5.5_H = 5.5_HIGH, 5.5_X = 5.5_XHIGH, GLM_M = GLM_MAX, LUNA_H = LUNA_HIGH,
LUNA_M = LUNA_MAX, LUNA_X = LUNA_XHIGH, SOL_H = SOL_HIGH, SOL_M = SOL_MEDIUM,
TERRA_X = TERRA_XHIGH

### Issue Count by Report

| Report | Critical | High | Medium | Low | Total Unique |
|--------|----------|------|--------|------|--------------|
| SOL_HIGH | 1 | 6 | 4 | 1 | 12 |
| LUNA_MAX | 1 | 5 | 6 | 2 | 14 |
| GLM_MAX | 1 | 3 | 3 | 5 | 12 |
| 5.5_XHIGH | 1 | 5 | 4 | 0 | 10 |
| LUNA_XHIGH | 1 | 5 | 4 | 1 | 11 |
| SOL_MEDIUM | 1 | 3 | 3 | 1 | 8 |
| TERRA_XHIGH | 1 | 2 | 1 | 1 | 5 |
| LUNA_HIGH | 0 | 3 | 3 | 1 | 7 |
| 5.5_HIGH | 1 | 2 | 1 | 1 | 5 |

---

## Methodology

### Repository evidence gathered

- **Git history:** `git log --oneline -20`, `git diff --stat 4d8994a..HEAD`,
  `git diff --name-status 4d8994a..HEAD`
- **Source code inspection:** Full read of `hardware.py:780-1040`, `application.py:140-440`
  and `1010-1150`, `models.py:285-310`, `config.py` (installed and sibling), `power.py`
  (installed), `packaging/systemd/honor-control.service`, `scripts/uninstall-local.sh`
- **Runtime verification:** Python script reproducing the MSR encoding arithmetic;
  `python3 -c "from honor.config import PowerProfile; PowerProfile(turbo_enabled=True)"`
  confirming the dependency API mismatch
- **Pricing data:** Codex session database (`~/.codex/state_5.sqlite`) for GPT model token
  counts; opencode database (`~/.local/share/opencode/opencode.db`) for GLM-5.2 token counts
  and cost; OpenAI pricing page for GPT rates; NeuralWatt API (`api.neuralwatt.com/v1/models`)
  for GLM-5.2 rates
- **System verification:** `ls -la /dev/cpu/0/msr`, `lsmod | grep msr`,
  `cat /sys/kernel/security/lockdown` to confirm MSR device and lockdown status

### Limitations

- No real Honor hardware was available. All claims about hardware behavior are inferred from
  code, kernel documentation, and arithmetic reproduction.
- The honor-tools dependency mismatch was confirmed against the PyPI-installed 0.1.0 version.
  Production installs from the sibling source may differ.
- Pricing calculations assume all tokens were billed at standard rates (no batch/flex
  discounts applied). Cached input tokens are billed at the cached rate.
