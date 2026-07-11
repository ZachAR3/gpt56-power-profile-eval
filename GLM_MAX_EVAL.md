# GLM-5.2 Engineering Review: Power-Profile Overhaul

Repository: `honor-control` (`git@github.com:ZachAR3/HonorControl.git`)
Review date: 2026-07-12
Reviewer: GLM-5.2 (automated)

---

## 1. Executive summary

The power-profile overhaul (commits `15f4d66`, `d391bb0`, `7213294`, `34d31f9`)
attempts to fix three real problems on the Honor MagicBook Art 14: a UI
snap-back bug, EPP being overwritten by `power-profiles-daemon` (PPD), and
RAPL PL1/PL2 limits being clobbered by competing daemons. The high-level
approach — a delayed RAPL MSR + EPP re-write, startup reconciliation, and
stopping competing daemons — is reasonable in direction.

However, the implementation contains one **critical correctness bug** in the
MSR bit-layout (PL2 enable and time-window bits are silently truncated), a
**concurrency race** in which stale delayed-rewrite tasks can clobber the
current profile, and a chain of **production-deployment failures** in which
`systemctl mask` is blocked by the service's own `ProtectSystem=strict`
hardening, PPD is reactivated by D-Bus service activation when
`powerprofilesctl set` is called, and the `msr` kernel module cannot be loaded
under `ProtectKernelModules=true`. None of the new methods has any test
coverage.

The existing 221 tests pass and `ruff` is clean, but the test suite exercises
only `FakeHardware` stubs; the overhaul's real hardware paths are completely
untested, and several of the new behaviors are unverifiable from the test
suite.

### Final verdict

**Requires significant fixes.**

The MSR bit-layout bug (PP-001) writes an incorrect value to CPU hardware.
The stale-task race (PP-002) can apply the wrong power profile. The
deployment-hardening incompatibilities (PP-003, PP-004, PP-005) mean the
overhaul's central mechanism — stopping PPD and writing the RAPL MSR — is
likely ineffective in the production systemd unit. These must be fixed and
covered by tests before merge.

---

## 2. Scope and methodology

### Branch and commit reviewed

- Branch: `main`
- HEAD: `34d31f9c7efc195d7be5e9e39a75a3d4f938f33f`
- Comparison base (merge base with `origin/main`): `34d31f9` (== HEAD, since
  `origin/main` points at the same commit). The only defensible base for
  isolating the overhaul is the initial commit `4d8994a`, since the entire
  repository was created in that commit and the three overhaul commits sit
  directly on top of it. **Assumption:** the diff `4d8994a..HEAD` represents
  the complete power-profile overhaul.

### Relevant commits

| Commit | Subject |
|--------|---------|
| `15f4d66` | Fix power profile application: RAPL, EPP, and UI snap-back |
| `d391bb0` | Clean up power profile code: safety, simplicity, correctness |
| `7213294` | Guard stop_competing_power_daemons behind platform detection |
| `34d31f9` | README: document Intel-only compatibility |

### Files changed by the overhaul

| File | Delta |
|------|-------|
| `honor_control/backend/application.py` | +85 / −7 |
| `honor_control/backend/hardware.py` | +217 / −2 |
| `honor_control/frontend/gui/pages/power.py` | +24 / −5 |
| `README.md` | +7 |

### Subsystems inspected (beyond the diff)

- `honor_control/backend/command_queue.py` — serialized hardware worker
- `honor_control/backend/config_store.py` — power profile persistence + validation
- `honor_control/backend/service.py` — service lifecycle (`initialize` / `shutdown`)
- `honor_control/backend/dbus/api.py` — D-Bus surface for power methods
- `honor_control/cli/honorctl.py` — CLI power commands
- `honor_control/core/models.py` — `PowerProfileEntry`, `POWER_PROFILES`, `PowerSnapshot`
- `packaging/systemd/honor-control.service` — systemd hardening
- `packaging/polkit/org.honorlinux.control.policy` — privilege tiers
- `scripts/install-local.sh`, `scripts/uninstall-local.sh` — install/cleanup
- `honor` (honor-tools) package: `honor.power.apply_profile`, `_write_rapl`,
  `_write_epp`, `_set_ppd`, `get_status`, `read_ppd` — the underlying
  hardware operations the overhaul builds on
- `tests/test_application.py`, `tests/test_hardware.py`, `tests/test_gui.py` —
  existing test coverage
- `docs/safety.md`, `docs/architecture.md`, `CHANGELOG.md` — documentation

### Commands run

| Command | Result |
|---------|--------|
| `.venv/bin/python -m pytest tests/ -q` | 221 passed in 8.56s |
| `.venv/bin/python -m ruff check honor_control/ tests/` | All checks passed |
| `.venv/bin/python -m ruff check --select ALL ...` (informational) | 236 errors (not enforced by project config) |
| `systemctl cat power-profiles-daemon.service` | `Type=dbus`, `BusName=org.freedesktop.UPower.PowerProfiles` |
| `cat /usr/share/dbus-1/system-services/net.hadess.PowerProfiles.service` | `SystemdService=power-profiles-daemon.service` (D-Bus activated) |
| Custom Python script simulating `write_rapl_msr` bit construction | Confirmed PL2 enable bit = 0, PL2 time window = 0 (bug) |
| Custom Python script applying two profiles in quick succession | Confirmed stale delayed-rewrite task is not cancelled |
| `which powerprofilesctl` | `/usr/bin/powerprofilesctl` |
| `systemctl is-active power-profiles-daemon` | active |
| `systemctl is-active intel_lpmd` | inactive |

### Limitations

- No real Honor hardware was available. All runtime verification used
  `FakeHardware` (in-memory stubs). Hardware-specific claims (e.g., whether
  PPD's sysfs writes reach the MSR) are inferred from code and documentation,
  not measured.
- No type checker (mypy/pyright) is configured in the project.
- The `honor-tools` package is a vendored dependency; its behavior was
  inspected via `inspect.getsource`, not via its own test suite.

---

## 3. Architecture and behavior overview

### Components and responsibilities

```
┌─────────────────────────────────────────────────────────┐
│ D-Bus API (dbus/api.py)                                 │
│   SetProfile, SavePowerProfile, DeletePowerProfile,      │
│   ConfigureAutoSwitch  ← polkit authorizer              │
└──────────────────────────┬──────────────────────────────┘
                           │ async call
┌──────────────────────────▼──────────────────────────────┐
│ ApplicationService (application.py)                      │
│   - set_power_profile (@_serialized_mutation)             │
│   - _apply_power_profile(name, persist_desired)          │
│   - _delayed_power_rewrite(profile)  ← fire-and-forget   │
│   - _reconcile_power_profile()  ← startup re-apply       │
│   - _auto_switch_loop()  ← AC/battery profile switching  │
│   - _mutation_lock (asyncio.Lock)                        │
│   - _pending_power_task (asyncio.Task ref)               │
└──────────────────────────┬──────────────────────────────┘
                           │ self._queue.run(name, fn, ...)
┌──────────────────────────▼──────────────────────────────┐
│ HardwareCommandQueue (command_queue.py)                 │
│   Single daemon thread, async lock, 10s default timeout  │
└──────────────────────────┬──────────────────────────────┘
                           │ synchronous call
┌──────────────────────────▼──────────────────────────────┐
│ HardwarePort (Protocol)                                 │
│   ├─ FakeHardware (tests, --session-bus dev mode)        │
│   └─ HonorToolsAdapter (production)                     │
│       - apply_power_profile → honor.power.apply_profile  │
│       - write_rapl_msr → /dev/cpu/0/msr (MSR 0x610)      │
│       - rewrite_epp → /sys/devices/system/cpu/cpuN/...   │
│       - stop_competing_power_daemons → systemctl + sysfs │
└─────────────────────────────────────────────────────────┘
```

### Control flow: profile apply

1. User (GUI/CLI/D-Bus) calls `set_power_profile(name)`.
2. `@_serialized_mutation` acquires `_mutation_lock`.
3. `_apply_power_profile(name, persist_desired=True)`:
   a. Probes `get_power_capability`; returns `unavailable` if not writable.
   b. Builds `definition` dict from `PowerProfileState`.
   c. `self._queue.run("power_apply", self._hw.apply_power_profile, name, definition)`
      — calls `honor.power.apply_profile`, which writes RAPL via sysfs,
      sets governor to `powersave`, calls `powerprofilesctl set`, writes EPP,
      sets target governor, sets `no_turbo=0` / `max_perf_pct=100`.
   d. Checks `governor_ok`, `epp_ok`, `ppd_ok`, `rapl_ok`, `misc_ok`.
   e. On full success: updates `_last_applied_power_profile`, persists desired
      state (if `persist_desired`), refreshes snapshot, schedules
      `_delayed_power_rewrite(profile)` via `asyncio.ensure_future`.
   f. On any failure: returns `OperationResult.partial(...)`.
4. `_delayed_power_rewrite(profile)` (0.5s later, fire-and-forget):
   a. `self._queue.run("rapl_msr", self._hw.write_rapl_msr, pl1, pl2)`.
   b. `self._queue.run("epp_rewrite", self._hw.rewrite_epp, epp, governor)`.

### Startup reconciliation

`initialize()`:
1. `self._config.load()`
2. `await self._refresh_all()` — reads all hardware state into snapshot.
3. `await self._queue.run("stop_daemons", self._hw.stop_competing_power_daemons)`
   — stops and masks PPD + intel_lpmd, enables HWP dynamic boost.
4. `await self._reconcile_power_profile()` — if persisted desired profile !=
   applied profile, re-applies it with `persist_desired=False`.

### State ownership

- **Desired profile**: `ConfigStore.state.power.profile` (persisted to
  `/var/lib/honor-control/state.toml`).
- **Applied profile**: `ApplicationService._last_applied_power_profile`
  (in-memory; falls back to hardware-reported `pw.applied_profile`).
- **Profile definitions**: `ConfigStore.state.power.profiles` dict
  (persisted; seeded from `POWER_PROFILES` defaults).
- **Snapshot**: `SnapshotStore` — monotonic sequence, published to D-Bus
  clients via `StateChanged` signal.

### Configuration and persistence

- Profiles are validated by `ConfigStore._validate_power_profile`: PL1
  3–100 W, PL2 ≥ PL1 and ≤ 150 W, governor ∈ {powersave, performance},
  EPP ∈ {power, default, balance_power, balance_performance, performance}.
- `write_rapl_msr` has its own bounds check (3–150 W for both PL1 and PL2),
  which is more permissive than the config store but acts as defense-in-depth.

### Hardware / OS integration

- **RAPL sysfs**: `honor.power._write_rapl` writes to
  `/sys/class/powercap/intel-rapl:0/constraint_{0,1}_power_limit_uw` and
  the `intel-rapl-mmio:0` tree.
- **RAPL MSR**: `HonorToolsAdapter.write_rapl_msr` writes PL1/PL2 directly
  to MSR 0x610 via `/dev/cpu/0/msr`, reading power units from MSR 0x606.
- **EPP**: `rewrite_epp` writes per-CPU
  `energy_performance_preference` with read-back + retries, and manages the
  governor (flips to `powersave` to make EPP writable, leaves `powersave` if
  requested governor is `performance`).
- **PPD**: `stop_competing_power_daemons` runs `systemctl stop` + `systemctl mask`
  for `power-profiles-daemon` and `intel_lpmd`, then writes `1` to
  `intel_pstate/hwp_dynamic_boost`.
- **Platform guard**: all new hardware methods are guarded by
  `_require_platform_or_none()` — they no-op on non-Honor hardware.

### Error and recovery paths

- `_apply_power_profile` returns `OperationResult.partial(...)` if any
  sub-operation fails; the delayed rewrite is **not** scheduled on partial.
- `_delayed_power_rewrite` catches `Exception` and logs a warning; failures
  are not communicated to the caller (the apply already returned success).
- `_reconcile_power_profile` catches `Exception` and logs a warning; never
  prevents service startup.
- `shutdown()` cancels `_pending_power_task` if still running.
- `write_rapl_msr` catches `OSError` and returns `False`.
- `stop_competing_power_daemons` catches `OSError` and
  `subprocess.TimeoutExpired` silently.

---

## 4. Findings

Findings are ordered by severity. Each has a stable identifier (PP-NNN).

---

### PP-001 — RAPL MSR PL2 enable bit and time window are silently truncated

- **Severity:** Critical
- **Confidence:** High
- **Category:** Functional bug / incorrect hardware write
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py`, `HonorToolsAdapter.write_rapl_msr`,
  lines 1007–1019

**Description.**

The 64-bit MSR 0x610 (`MSR_PKG_POWER_LIMIT`) is constructed by building a
`lo` word for PL1 (bits 0–23) and a `hi` word for PL2, then combining them
with `val = (lo | (hi << 32)) & 0xFFFFFFFFFFFFFFFF`. The `hi` word is
assembled with **absolute** bit positions (`1 << 47` for PL2 enable,
`tw2 << 49` for PL2 time window), but is then shifted left by 32 bits,
moving those bits to positions 79 and 81+ — which are truncated by the
64-bit mask. The PL2 power-limit value itself (`pl2_units` at bit 0 of `hi`)
lands correctly at bits 32–46, but the PL2 enable bit (bit 47) and PL2 time
window (bits 49–55) are lost.

Additionally, the PL2 clamp bit (bit 48) is never set, while the PL1 clamp
bit (bit 16) is — an undocumented inconsistency.

**Evidence.**

Source code (`hardware.py:1007-1019`):

```python
lo = (
    pl1_units
    | (1 << 15)  # PL1 enabled
    | (1 << 16)  # PL1 clamp
    | (tw1 << 17)
)
hi = (
    pl2_units
    | (1 << 47)  # PL2 enabled   ← absolute bit, but hi is shifted << 32 below
    | (tw2 << 49)                 ← same problem
)
val = (lo | (hi << 32)) & 0xFFFFFFFFFFFFFFFF
```

Verified with a simulation (PL1=35 W, PL2=55 W, power_unit=2):

```
PL1 power limit (bits 14:0)  = 140  ✓
PL1 enable (bit 15)           = 1    ✓
PL1 clamp (bit 16)            = 1    ✓
PL1 time window (bits 23:17)  = 97   ✓
PL2 power limit (bits 46:32) = 220  ✓
PL2 enable (bit 47)           = 0    ✗  (expected 1)
PL2 clamp (bit 48)            = 0    ✗  (inconsistent with PL1)
PL2 time window (bits 55:49)  = 0    ✗  (expected 97)
```

**Failure scenario.**

When the user selects the "performance" profile (PL1=35 W, PL2=55 W), the
MSR write sets PL1 correctly but writes PL2 with enable=0 and time_window=0.
Depending on the CPU's behavior when PL2 enable is 0, the short-term boost
power limit may be disabled (allowing unlimited boost) or may not take effect
at all. The time window being reset to 0 is also incorrect. This directly
contradicts the overhaul's goal of "35W PL1 / 55W PL2" sustained power.

**Recommended fix.**

Use absolute bit positions for the full 64-bit value (do not pre-shift `hi`):

```python
val = (
    pl1_units
    | (1 << 15)       # PL1 enabled
    | (1 << 16)       # PL1 clamp
    | (tw1 << 17)     # PL1 time window
    | (pl2_units << 32)
    | (1 << 47)       # PL2 enabled
    | (1 << 48)       # PL2 clamp (if desired — document the choice)
    | (tw2 << 49)     # PL2 time window
) & 0xFFFFFFFFFFFFFFFF
```

**Suggested tests.**

- Unit test `write_rapl_msr` with a mock `/dev/cpu/0/msr` that captures the
  written bytes; assert bit 47 (PL2 enable) is set, bits 49–55 preserve the
  old time window, and PL1/PL2 values are correct.
- Test with edge-case values (minimum/maximum PL1/PL2, zero time window,
  maximum time window).

---

### PP-002 — Stale delayed-rewrite task is not cancelled before scheduling a new one

- **Severity:** High
- **Confidence:** High
- **Category:** Concurrency race / incorrect state transition
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/application.py`,
  `ApplicationService._apply_power_profile`, lines 371–373

**Description.**

When `_apply_power_profile` succeeds, it schedules
`_delayed_power_rewrite(profile)` and stores the task in
`self._pending_power_task`. If a second apply happens within the 0.5 s
delay window, the previous task reference is **overwritten without being
cancelled**. The old task continues to run and writes the old profile's
RAPL/EPP values 0.5 s after the first apply — potentially **after** the
second apply has already set the hardware to the new profile.

The only place `_pending_power_task.cancel()` is called is `shutdown()`.
There is no cancellation in `_apply_power_profile` before
`asyncio.ensure_future`.

**Evidence.**

`application.py:371-373`:
```python
self._pending_power_task = asyncio.ensure_future(
    self._delayed_power_rewrite(profile)
)
```

No preceding cancel. Verified with a test that applies "performance" then
immediately "balanced":

```
task_a is task_b? False
task_a cancelled? False
write_rapl_msr calls: [(35000000, 55000000), (25000000, 35000000)]
```

Both delayed rewrites fire. If timing differs (task A fires after profile B
is applied), the hardware is temporarily (or permanently, if B's rewrite
fails) set to the wrong profile.

**Failure scenario.**

1. User applies "performance" → delayed rewrite A scheduled (fires at t+0.5s).
2. Auto-switch loop detects battery unplug at t+0.2s → applies "silent" →
   delayed rewrite B scheduled (fires at t+0.7s).
3. At t+0.5s, rewrite A fires and writes performance's 35 W / 55 W RAPL
   limits — clobbering the silent profile's 12 W / 18 W limits.
4. At t+0.7s, rewrite B fires and corrects to silent values.
5. Between t+0.5s and t+0.7s, the CPU draws 35 W on battery.

If rewrite B fails (e.g., EBUSY on all EPP writes), the hardware stays at
performance values indefinitely.

**Recommended fix.**

Cancel the previous task before scheduling a new one:

```python
if (
    self._pending_power_task is not None
    and not self._pending_power_task.done()
):
    self._pending_power_task.cancel()
self._pending_power_task = asyncio.ensure_future(
    self._delayed_power_rewrite(profile)
)
```

Additionally, `_delayed_power_rewrite` should re-check that the profile is
still the current one before writing (compare against
`self._last_applied_power_profile`).

**Suggested tests.**

- Apply profile A, then immediately profile B; assert only B's delayed
  rewrite fires (A's task is cancelled).
- Apply profile A, wait 0.6s (A's rewrite fires), then apply B; assert B's
  rewrite fires normally.
- Apply profile A, then shut down within 0.5s; assert no exception.

---

### PP-003 — `systemctl mask` fails under `ProtectSystem=strict`

- **Severity:** High
- **Confidence:** High
- **Category:** Deployment / OS assumption
- **Origin:** Newly introduced (interaction between `hardware.py` and
  `packaging/systemd/honor-control.service`)
- **Affected:** `honor_control/backend/hardware.py:874-885`;
  `packaging/systemd/honor-control.service` (`ProtectSystem=strict`)

**Description.**

`stop_competing_power_daemons` calls `systemctl mask power-profiles-daemon`
and `systemctl mask intel_lpmd`. The `mask` operation creates a symlink
from `/etc/systemd/system/<unit>.service` to `/dev/null`. The production
systemd unit has `ProtectSystem=strict`, which makes the entire filesystem
read-only except `/dev`, `/proc`, `/sys`, and the service's own
`StateDirectory` / `RuntimeDirectory`. `/etc/systemd/system/` is therefore
read-only, and `systemctl mask` fails with "Read-only file system".

The failure is silently swallowed (`stderr=DEVNULL`, `check=False`,
`except (OSError, subprocess.TimeoutExpired): pass`). The commit message
explicitly relies on masking: "Masking (not disabling) is used because it
prevents systemd from restarting the unit even if another service depends
on it." Without masking, `stop` alone is insufficient — PPD can be
restarted by D-Bus activation or dependency triggers.

**Evidence.**

`hardware.py:874-885`:
```python
for daemon in ("power-profiles-daemon", "intel_lpmd"):
    for action in ("stop", "mask"):
        try:
            subprocess.run(
                ["systemctl", action, daemon],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
```

`packaging/systemd/honor-control.service`:
```
ProtectSystem=strict
```

`systemd` documentation: `ProtectSystem=strict` mounts the entire file
system hierarchy read-only except for `/dev/`, `/proc/`, `/sys/`.

**Failure scenario.**

In production, the service stops PPD but cannot mask it. PPD is restarted
by D-Bus service activation (see PP-004) the next time `powerprofilesctl set`
is called — which is exactly what `apply_power_profile` does. The entire
"stop competing daemons" mechanism is a no-op in production.

**Recommended fix.**

One of:
1. Add `ReadWritePaths=/etc/systemd/system /run/systemd/system` to the
   systemd unit (reduces hardening).
2. Use `systemctl mask --runtime` and add `ReadWritePaths=/run/systemd/system`.
3. Drop the masking approach entirely and instead rely on the delayed MSR
   write to override PPD's values (if PPD's sysfs writes don't reach the MSR,
   as the docstring claims).
4. Perform the masking in `scripts/install-local.sh` (which runs as root
   outside the sandbox) rather than at service runtime.

**Suggested tests.**

- Integration test that runs the service under `systemd-run` with the
  production unit's hardening and verifies that `systemctl mask` succeeds or
  fails gracefully.
- Unit test that mocks `subprocess.run` and asserts the expected systemctl
  invocations.

---

### PP-004 — PPD is reactivated by D-Bus service activation when `powerprofilesctl set` is called

- **Severity:** High
- **Confidence:** High
- **Category:** OS assumption / logical contradiction
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py:844-896` (stop);
  `honor_control/backend/application.py:338-340` (apply calls
  `powerprofilesctl set` via `honor.power.apply_profile`)

**Description.**

`stop_competing_power_daemons` stops PPD during `initialize()`. Later,
`_apply_power_profile` calls `honor.power.apply_profile`, which calls
`_set_ppd`, which runs `powerprofilesctl set <profile>`. PPD's D-Bus service
file (`/usr/share/dbus-1/system-services/net.hadess.PowerProfiles.service`)
contains `SystemdService=power-profiles-daemon.service`, so D-Bus asks
systemd to start PPD when `powerprofilesctl` connects. Since PPD is only
stopped (not masked — see PP-003), systemd starts it. PPD then overwrites
RAPL and EPP with its own values, defeating the purpose of stopping it.

This creates a contradiction:
- If PPD is stopped → `powerprofilesctl set` fails or reactivates PPD.
- If `powerprofilesctl set` succeeds → PPD is running and overwrites values.
- The delayed MSR write (PP-001 aside) is only scheduled on full success,
  which requires `ppd_ok=True`, which requires PPD to be running.

**Evidence.**

```
$ systemctl cat power-profiles-daemon.service
Type=dbus
BusName=org.freedesktop.UPower.PowerProfiles

$ cat /usr/share/dbus-1/system-services/net.hadess.PowerProfiles.service
[D-BUS Service]
Name=net.hadess.PowerProfiles
Exec=/bin/false
SystemdService=power-profiles-daemon.service
```

The `SystemdService=` key causes D-Bus to start the systemd unit on demand.

**Failure scenario.**

1. Service starts → `stop_competing_power_daemons` stops PPD.
2. User applies "performance" → `powerprofilesctl set performance` → D-Bus
   reactivates PPD → `ppd_ok=True` → delayed MSR write scheduled.
3. PPD is now running and overwrites RAPL/EPP within ~1 second.
4. The delayed MSR write (0.5s later) writes directly to the MSR, but if
   PPD's sysfs writes also reach the MSR (contradicting the `write_rapl_msr`
   docstring), PPD overwrites them again.

**Recommended fix.**

- Do not call `powerprofilesctl set` when PPD has been intentionally stopped.
  The profile's `ppd_profile` field should be skipped (or `ppd_ok` should be
  treated as non-blocking) when PPD is stopped.
- Or: do not stop PPD at all, and rely solely on the delayed MSR write +
  EPP read-back to override PPD's values. The commit message claims the
  read-back causes PPD's competing EPP write to get `EBUSY`; if this works,
  stopping PPD is unnecessary for EPP. For RAPL, the MSR write bypasses
  sysfs entirely.
- Make `ppd_ok` non-blocking for the purpose of scheduling the delayed
  rewrite: the MSR/EPP re-write is the mechanism that makes values stick,
  and it should run regardless of whether PPD accepted the profile.

**Suggested tests.**

- Test that `_apply_power_profile` schedules the delayed rewrite even when
  `ppd_ok=False` (after the fix).
- Test that `apply_power_profile` does not call `powerprofilesctl set` when
  PPD is known to be stopped.

---

### PP-005 — `ProtectKernelModules=true` prevents loading the `msr` module

- **Severity:** High
- **Confidence:** High
- **Category:** Deployment / OS assumption
- **Origin:** Newly introduced (interaction between `hardware.py` and
  `packaging/systemd/honor-control.service`)
- **Affected:** `honor_control/backend/hardware.py:988-1036`
  (`write_rapl_msr` opens `/dev/cpu/0/msr`);
  `packaging/systemd/honor-control.service` (`ProtectKernelModules=true`)

**Description.**

`write_rapl_msr` opens `/dev/cpu/0/msr`, which is created by the `msr`
kernel module. The `msr` module is not loaded by default on many Linux
distributions. The production systemd unit has
`ProtectKernelModules=true`, which prevents the service from loading kernel
modules (including via `modprobe` or module auto-loading triggered by
accessing `/dev/cpu/0/msr`).

If the `msr` module is not already loaded when the service starts,
`/dev/cpu/0/msr` does not exist, `os.open` raises `OSError`, and
`write_rapl_msr` returns `False`. The failure is logged but the apply still
reports success (the delayed rewrite's failure is caught by
`_delayed_power_rewrite`'s `except Exception`).

**Evidence.**

`hardware.py:990`:
```python
fd = os.open("/dev/cpu/0/msr", os.O_RDONLY)
```

`packaging/systemd/honor-control.service`:
```
ProtectKernelModules=true
```

**Failure scenario.**

On a fresh install where `msr` is not loaded, the RAPL MSR write silently
fails on every profile apply. The user sees "Profile 'performance' applied"
but the 35 W PL1 limit is never written to the MSR. The sysfs RAPL write
(from `honor.power.apply_profile`) may or may not reach the MSR depending
on the driver, but the overhaul's specific fix (direct MSR write) is
bypassed.

**Recommended fix.**

- Document that the `msr` module must be loaded before starting the service
  (e.g., add `modprobe msr` to `scripts/install-local.sh` or add
  `msr` to `/etc/modules-load.d/`).
- Or: remove `ProtectKernelModules=true` from the systemd unit (reduces
  hardening).
- Or: have `write_rapl_msr` attempt to load the module via `modprobe` in a
  helper that runs outside the sandbox (e.g., a `ExecStartPre` systemd unit).
- Log the failure at `ERROR` level (not just `WARNING`) and surface it in
  the snapshot's `last_error` so the user knows the MSR write failed.

**Suggested tests.**

- Test that `write_rapl_msr` returns `False` and logs a clear error when
  `/dev/cpu/0/msr` does not exist.
- Test that the service reports degraded health when MSR writes fail
  consistently.

---

### PP-006 — Zero test coverage for all new methods

- **Severity:** High
- **Confidence:** High
- **Category:** Missing tests
- **Origin:** Newly introduced
- **Affected:** All new methods in `hardware.py` and `application.py`

**Description.**

None of the following methods has any test:

| Method | File |
|--------|------|
| `HonorToolsAdapter.stop_competing_power_daemons` | `hardware.py:844` |
| `HonorToolsAdapter.rewrite_epp` | `hardware.py:898` |
| `HonorToolsAdapter.write_rapl_msr` | `hardware.py:961` |
| `FakeHardware.stop_competing_power_daemons` | `hardware.py:254` |
| `FakeHardware.rewrite_epp` | `hardware.py:246` |
| `FakeHardware.write_rapl_msr` | `hardware.py:250` |
| `ApplicationService._delayed_power_rewrite` | `application.py:391` |
| `ApplicationService._reconcile_power_profile` | `application.py:1013` |
| `PowerPage._on_active_combo_changed` | `power.py:374` |

A grep for `rewrite_epp`, `write_rapl_msr`, `stop_competing`,
`_delayed_power_rewrite`, `_reconcile_power_profile`, `_pending_power_task`,
`_active_combo_dirty`, `stop_daemons`, `rapl_msr`, `epp_rewrite` in `tests/`
returns zero matches.

The existing `test_application.py` tests call `svc.initialize()` (which
invokes `stop_competing_power_daemons` on `FakeHardware`), but never assert
on the call log for `stop_competing_power_daemons`, `write_rapl_msr`, or
`rewrite_epp`. The `test_auto_switch_applies_selected_profile_and_runs_hook_once`
test sleeps 2.1s (long enough for the delayed rewrite to fire), but only
asserts on `apply_power_profile` call counts — not on whether the delayed
rewrite actually ran.

**Evidence.**

```
$ grep -rn "rewrite_epp\|write_rapl_msr\|stop_competing\|delayed_power\|reconcile_power\|pending_power\|active_combo_dirty\|rapl_msr\|epp_rewrite" tests/
(no output)
```

**Failure scenario.**

The MSR bit-layout bug (PP-001), the stale-task race (PP-002), and the
partial-apply gating issue (PP-004) were all undetectable by the current
test suite. Any future regression in these methods would also go undetected.

**Recommended fix.**

Add tests for:
- `write_rapl_msr` bit layout (see PP-001 suggested tests).
- `_delayed_power_rewrite` scheduling and cancellation (see PP-002).
- `_reconcile_power_profile` re-applies persisted profile on startup.
- `_reconcile_power_profile` no-ops when desired == applied.
- `_reconcile_power_profile` does not block startup on failure.
- `stop_competing_power_daemons` no-ops on non-Honor platform.
- `rewrite_epp` governor quirk (leaves `powersave` when `performance`
  requested).
- `PowerPage` active-combo dirty flag preserves user selection across
  snapshot refreshes.
- `PowerPage` dirty flag clears when user selection matches applied profile.

---

### PP-007 — `time.sleep` in `rewrite_epp` blocks the command queue worker thread

- **Severity:** Medium
- **Confidence:** High
- **Category:** Concurrency / performance
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py:935-945`

**Description.**

`rewrite_epp` uses `time.sleep(0.1)` in a retry loop for each CPU's EPP
write. This is a blocking sleep that runs on the `HardwareCommandQueue`
worker thread (a single daemon thread). If EPP writes fail for all CPUs,
the worker blocks for up to `5 retries × 0.1s × N_cpus`. On a 22-thread
CPU (e.g., i7-155H with 6P+8E+2LP cores × 2 threads), this is up to 11s,
exceeding the command queue's 10s default timeout.

The sleep only triggers on write failure, so the happy path is unaffected.
But the failure path is exactly when retries are needed, and the blocking
prevents all other hardware operations (fan reads, battery reads, etc.)
from running during the retry window.

**Evidence.**

`hardware.py:932-948`:
```python
for cpu in cpu_dirs:
    path = f"{cpu}/cpufreq/energy_performance_preference"
    ok = False
    for _attempt in range(5):
        if self._write_sysfs(path, epp):
            ...
            ok = True
            break
        time.sleep(0.1)
    if not ok:
        ...
```

The `honor.power._write_epp` function (in the dependency) uses the same
pattern with `time.sleep(0.05)` and 3 attempts, but the overhaul's version
is more aggressive (5 attempts, 0.1s).

**Failure scenario.**

If EPP writes fail on all CPUs (e.g., `intel_pstate` not loaded, or
permissions issue), the command queue worker blocks for up to 11s. During
this time, all other hardware reads/writes are queued and delayed. The
10s command queue timeout may fire, marking the command as timed out and
blocking subsequent commands with "A timed-out hardware command is still
running".

**Recommended fix.**

- Reduce the retry count or sleep duration.
- Or: move the retry loop to async code (using `asyncio.sleep` instead of
  `time.sleep`), running each CPU's write as a separate queued command.
- Or: set a per-method timeout on the `self._queue.run("epp_rewrite", ...)`
  call in `_delayed_power_rewrite` that is shorter than the default 10s.

**Suggested tests.**

- Test `rewrite_epp` with a mock sysfs that always fails; assert it returns
  `False` within a bounded time.

---

### PP-008 — No cleanup of stopped/masked daemons on shutdown or uninstall

- **Severity:** Medium
- **Confidence:** High
- **Category:** Resource lifecycle / system hygiene
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/application.py:181-186` (`shutdown`);
  `honor_control/backend/hardware.py:844-896`;
  `scripts/uninstall-local.sh`

**Description.**

`stop_competing_power_daemons` stops (and attempts to mask) PPD and
`intel_lpmd` during `initialize()`. Neither `ApplicationService.shutdown()`
nor `scripts/uninstall-local.sh` restarts or unmasks these daemons. The
systemd unit's `ExecStopPost` only runs `--restore-fan-auto`, not a PPD
restore.

If masking succeeded (see PP-003 for why it likely doesn't), PPD would
remain masked across reboots even after honor-control is uninstalled,
breaking the system's standard power management. Even with masking failing,
PPD remains stopped for the lifetime of the honor-control service and is
not restarted on shutdown.

**Evidence.**

`application.py:181-186`:
```python
async def shutdown(self) -> None:
    if self._pending_power_task is not None and not self._pending_power_task.done():
        self._pending_power_task.cancel()
    await self._supervisor.stop_all()
    self._queue.shutdown(wait=False)
```

No `systemctl unmask` or `systemctl start` for PPD/intel_lpmd.

`scripts/uninstall-local.sh` does not unmask or restart PPD/intel_lpmd.

**Failure scenario.**

1. User installs honor-control → PPD stopped (and masked if PP-003 is fixed).
2. User uninstalls honor-control → PPD remains stopped/masked.
3. System reboots → PPD is still masked → standard power management is broken.
4. User has no indication that honor-control caused this.

**Recommended fix.**

- Add a `restore_competing_power_daemons()` method that runs `systemctl unmask`
  and `systemctl start` for PPD and `intel_lpmd`.
- Call it from `shutdown()` and from `scripts/uninstall-local.sh`.
- Or: only stop (not mask) PPD, and restart it on shutdown. Masking is too
  invasive for a service that might be uninstalled.

**Suggested tests.**

- Test that `shutdown()` restarts PPD if it was stopped.
- Test that `uninstall-local.sh` unmasks and restarts PPD.

---

### PP-009 — New hardware methods bypass the `root_path` abstraction

- **Severity:** Medium
- **Confidence:** High
- **Category:** Abstraction / testability
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py:871-896` (stop_competing),
  `898-959` (rewrite_epp), `961-1036` (write_rapl_msr)

**Description.**

`HonorToolsAdapter` is designed around a `root_path` parameter
(`self._root`, defaulting to `/`) that allows tests to use a fake filesystem.
Existing methods use `self._rooted(path)` or `self._read_text(path)` to
respect this. The new methods use hardcoded absolute paths:

- `stop_competing_power_daemons`: `pathlib.Path("/sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost")`
- `rewrite_epp`: `glob.glob("/sys/devices/system/cpu/cpu[0-9]*")`
- `write_rapl_msr`: `os.open("/dev/cpu/0/msr", ...)`

This makes the new methods untestable with a fake filesystem and inconsistent
with the rest of the adapter.

**Evidence.**

`hardware.py:889-891`:
```python
hwp_path = pathlib.Path(
    "/sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost"
)
```

Compare with existing methods that use `self._rooted`:
```python
def _read_text(self, path: str) -> str:
    return self._rooted(path).read_text(encoding="utf-8").strip()
```

**Failure scenario.**

Any test that wants to verify `rewrite_epp` or `write_rapl_msr` behavior
must either use real hardware or mock at the `os.open` / `pathlib.Path`
level, which is brittle. The `root_path` abstraction that the rest of the
adapter uses is unavailable.

**Recommended fix.**

Use `self._rooted(path)` for all sysfs paths. For `/dev/cpu/0/msr`, use
`self._root / "dev/cpu/0/msr"`. For `glob.glob`, use
`(self._root / "sys/devices/system/cpu").glob("cpu[0-9]*")`.

**Suggested tests.**

- Test `rewrite_epp` with a fake sysfs tree under `tmp_path`.
- Test `write_rapl_msr` with a fake `/dev/cpu/0/msr` under `tmp_path`.

---

### PP-010 — `_delayed_power_rewrite` is not coordinated with the mutation lock

- **Severity:** Medium
- **Confidence:** Medium
- **Category:** Concurrency / state synchronization
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/application.py:391-421`

**Description.**

`_delayed_power_rewrite` runs as a fire-and-forget `asyncio.Task` outside
the `_mutation_lock`. It calls `self._queue.run(...)` which serializes on
the command queue, but does not acquire the mutation lock. This means the
delayed rewrite can run concurrently with a new `set_power_profile` call
(which holds the mutation lock). The command queue serializes the hardware
calls, but the logical consistency (which profile's values to write) is
not protected.

This is related to PP-002 but is a separate concern: even if the stale task
is cancelled, the delayed rewrite of the *current* task can race with a
*new* apply that happens during the 0.5s delay.

**Evidence.**

`_delayed_power_rewrite` (lines 391-421) does not acquire `self._mutation_lock`.
`_apply_power_profile` (decorated with `@_serialized_mutation`) does. The
delayed rewrite is scheduled inside `_apply_power_profile` but runs after
it returns (outside the lock).

**Failure scenario.**

1. t=0: apply "performance" → delayed rewrite scheduled for t+0.5s.
2. t=0.3: auto-switch loop acquires mutation lock, applies "silent".
3. t=0.5: delayed rewrite fires, writes "performance" RAPL/EPP (without
   mutation lock) — clobbers "silent" values.
4. t=0.5+: "silent" delayed rewrite scheduled for t+0.8s.
5. t=0.8: "silent" delayed rewrite fires, corrects values.

Between t=0.5 and t=0.8, the hardware has "performance" values despite
"silent" being the current profile.

**Recommended fix.**

- Have `_delayed_power_rewrite` re-check `self._last_applied_power_profile`
  before writing, and skip if the profile has changed.
- Or: acquire the mutation lock in `_delayed_power_rewrite` before writing
  (this would serialize with new applies, preventing the race).

**Suggested tests.**

- Apply profile A, then within 0.5s apply profile B via the auto-switch loop;
  assert the delayed rewrite for A does not write A's values after B is applied.

---

### PP-011 — Delayed-rewrite failure is not communicated to the user

- **Severity:** Medium
- **Confidence:** High
- **Category:** Faulty error handling / state inconsistency
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/application.py:374-381` (apply returns
  success), `391-421` (delayed rewrite fails silently)

**Description.**

`_apply_power_profile` returns `OperationResult.success(...)` immediately
after scheduling `_delayed_power_rewrite`. If the delayed rewrite fails
(e.g., MSR write fails because `msr` module isn't loaded, or EPP writes
fail), the failure is only logged at `WARNING` level. The user sees
"Profile 'performance' applied" even though the RAPL MSR write and/or EPP
rewrite failed, and the hardware may not have the correct values.

**Evidence.**

`application.py:374-381`:
```python
return OperationResult.success(
    message=f"Profile '{name}' applied",
    changed=True,
    persisted=persist_desired,
    applied=True,
    ...
)
```

`application.py:420-421`:
```python
except Exception as exc:  # noqa: BLE001
    log.warning("delayed power re-write failed: %s", exc)
```

**Failure scenario.**

User applies "performance" → sees "applied" → but `write_rapl_msr` failed
(PP-005) → CPU stays at default RAPL limits → user believes 35 W is active
but it isn't.

**Recommended fix.**

- After the delayed rewrite completes, update the snapshot with the actual
  RAPL/EPP values read back from hardware.
- If the delayed rewrite fails, mark the power domain as degraded in the
  snapshot and include the error in `last_error`.
- Or: make the delayed rewrite synchronous (block the apply return until
  the rewrite completes), so failures are reported in the `OperationResult`.
  This trades latency for correctness.

**Suggested tests.**

- Test that a failed `write_rapl_msr` in the delayed rewrite surfaces in the
  snapshot's `last_error` or service health.

---

### PP-012 — File descriptor leak in `write_rapl_msr` on error

- **Severity:** Medium
- **Confidence:** High
- **Category:** Resource leak / lifecycle
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py:990-1025`

**Description.**

`write_rapl_msr` opens `/dev/cpu/0/msr` three times (read units, read old
limits, write new limits). Each open/close pair is not protected by
`try/finally`. If any operation between `os.open` and `os.close` raises
`OSError`, the file descriptor leaks. The outer `except OSError` catches
the exception but does not close the fd.

**Evidence.**

`hardware.py:990-993`:
```python
fd = os.open("/dev/cpu/0/msr", os.O_RDONLY)
os.lseek(fd, MSR_RAPL_POWER_UNIT, os.SEEK_SET)
units_val = struct.unpack("<Q", os.read(fd, 8))[0]
os.close(fd)
```

If `os.lseek` or `os.read` raises, `os.close(fd)` is skipped. Same pattern
at lines 1000-1003 and 1022-1025.

**Failure scenario.**

If `os.read` returns fewer than 8 bytes (e.g., on a truncated MSR read),
`struct.unpack` raises `struct.error` (a `ValueError`, not `OSError`). This
propagates up without closing the fd, leaking it. Repeated failures could
exhaust the process's file descriptor limit.

**Recommended fix.**

Use `try/finally` or `contextlib.closing`:

```python
fd = os.open("/dev/cpu/0/msr", os.O_RDONLY)
try:
    os.lseek(fd, MSR_RAPL_POWER_UNIT, os.SEEK_SET)
    units_val = struct.unpack("<Q", os.read(fd, 8))[0]
finally:
    os.close(fd)
```

Also broaden the `except` to catch `struct.error` and `ValueError`.

**Suggested tests.**

- Test `write_rapl_msr` with a mock that raises mid-operation; assert no fd
  leak (check `/proc/self/fd` or mock `os.close`).

---

### PP-013 — Misplaced `# -- Fan --` section comment in `FakeHardware`

- **Severity:** Low
- **Confidence:** High
- **Category:** Dead code / misleading comments
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py:255`

**Description.**

The `# -- Fan --` comment, which was a section separator before
`read_fan`, ended up on the same line as the `stop_competing_power_daemons`
log call:

```python
def stop_competing_power_daemons(self) -> None:
    self._log("stop_competing_power_daemons")  # -- Fan --

def read_fan(self) -> FanSnapshot:
```

The comment is now misleading — it appears to label
`stop_competing_power_daemons` as a fan method, and `read_fan` lost its
section separator.

**Recommended fix.**

Move `# -- Fan --` to its own line before `read_fan`:

```python
def stop_competing_power_daemons(self) -> None:
    self._log("stop_competing_power_daemons")

# -- Fan --

def read_fan(self) -> FanSnapshot:
```

---

### PP-014 — Redundant local imports of `pathlib` shadow module-level import

- **Severity:** Low
- **Confidence:** High
- **Category:** Code quality / readability
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py:871` (stop_competing),
  `918` (rewrite_epp)

**Description.**

`pathlib` is already imported at module level (`hardware.py:17`), but both
`stop_competing_power_daemons` and `rewrite_epp` re-import it locally:
`import pathlib`. This is unnecessary (Python caches imports, so there's no
performance impact, but it adds visual noise and suggests the author was
unaware of the module-level import). Similarly, `os`, `struct`, `glob`,
`time`, and `subprocess` are imported locally inside methods rather than at
module level.

**Recommended fix.**

Move stdlib imports (`os`, `struct`, `glob`, `time`, `subprocess`) to the
module level. Remove the redundant `import pathlib` from method bodies.

---

### PP-015 — Inconsistent sysfs write helpers

- **Severity:** Low
- **Confidence:** High
- **Category:** Code quality / duplication
- **Origin:** Newly introduced
- **Affected:** `honor_control/backend/hardware.py:889-896` (direct
  `pathlib.Path.write_text`), `1038-1044` (`_write_sysfs`), `1184-1189`
  (`_write_int`)

**Description.**

`stop_competing_power_daemons` writes `hwp_dynamic_boost` via
`hwp_path.write_text("1")` directly, while `rewrite_epp` writes governor/EPP
via `self._write_sysfs(path, value)`. The `_write_sysfs` helper itself
duplicates `_write_int` (which does the same thing for integers). Three
different patterns for the same operation.

**Recommended fix.**

Use `self._write_sysfs` consistently for all string sysfs writes, including
`hwp_dynamic_boost`. Consider unifying `_write_sysfs` and `_write_int`.

---

### PP-016 — Documentation and CHANGELOG not updated for the overhaul

- **Severity:** Low
- **Confidence:** High
- **Category:** Documentation drift
- **Origin:** Newly introduced
- **Affected:** `docs/safety.md`, `docs/architecture.md`, `CHANGELOG.md`

**Description.**

The three overhaul commits add significant new behavior — stopping/masking
system daemons, direct MSR writes, EPP re-write with read-back, startup
reconciliation, delayed fire-and-forget rewrites — but none of this is
documented in `docs/safety.md`, `docs/architecture.md`, or `CHANGELOG.md`.
The safety doc lists power profiles as an "active local user" action but
does not mention that the service stops PPD on startup or writes directly to
CPU MSRs. The CHANGELOG's "Power profiles" entry (line 41-43) only describes
the initial commit's features.

**Recommended fix.**

- Add a safety section documenting: PPD/intel_lpmd stopping and masking,
  direct MSR writes (including bounds checking), EPP re-write with read-back,
  and the lack of restore on shutdown/uninstall.
- Add a CHANGELOG entry for the overhaul commits.
- Update `docs/architecture.md` to describe the delayed rewrite and
  reconciliation flow.

---

## 5. Test and validation assessment

### What is currently tested

- `tests/test_application.py::TestPowerMutation` — tests `set_power_profile`,
  `save_power_profile`, `delete_power_profile`, `configure_auto_switch`,
  and auto-switch with transition scripts. All use `FakeHardware`.
- `tests/test_application.py::test_auto_apply_does_not_replace_manual_profile`
  — verifies `persist_desired=False` does not overwrite the persisted
  desired profile.
- `tests/test_application.py::test_auto_switch_applies_selected_profile_and_runs_hook_once`
  — verifies the auto-switch loop applies the profile and runs the hook once.
- `tests/test_gui.py::test_power_page_construction` — verifies the power page
  renders a snapshot.
- `tests/test_gui.py::test_power_editor_preserves_unsaved_values_during_refresh`
  — verifies the profile editor's dirty flag preserves unsaved edits.
- `tests/test_hardware.py` — tests `HonorToolsAdapter` platform detection,
  battery discovery, and fan capability, but **not** any power methods on
  the real adapter.

### Important behavior that is not tested

1. **`write_rapl_msr` bit layout** — no test verifies that the written MSR
   value has PL2 enable set, PL2 time window preserved, etc. (PP-001).
2. **`_delayed_power_rewrite` scheduling and cancellation** — no test
   verifies that the delayed rewrite is scheduled on success, or that a
   previous task is cancelled before scheduling a new one (PP-002).
3. **`_reconcile_power_profile`** — no test verifies that the persisted
   profile is re-applied on startup, or that it no-ops when desired ==
   applied.
4. **`stop_competing_power_daemons`** — no test verifies the platform guard,
  the systemctl invocations, or the HWP dynamic boost write.
5. **`rewrite_epp`** — no test verifies the governor quirk (leaves
   `powersave` when `performance` requested), the read-back behavior, or
   the retry loop.
6. **`PowerPage._active_combo_dirty`** — no test verifies that the user's
   combo selection is preserved across snapshot refreshes (the UI snap-back
   fix that motivated the overhaul).
7. **Partial-apply behavior** — no test verifies what happens when
   `ppd_ok=False` (does the delayed rewrite run? does the user see "partial"?).
8. **Error propagation** — no test verifies that a failed `write_rapl_msr`
   or `rewrite_epp` is surfaced to the user or snapshot.
9. **`HonorToolsAdapter` power methods** — no test exercises
   `stop_competing_power_daemons`, `rewrite_epp`, or `write_rapl_msr` on the
   real adapter (even with a fake filesystem).

### Tests that appear weak or incomplete

- `test_auto_switch_applies_selected_profile_and_runs_hook_once` sleeps 2.1s,
  which is long enough for the delayed rewrite to fire, but only asserts on
  `apply_power_profile` call counts. It does not verify that
   `write_rapl_msr` or `rewrite_epp` were called. This test would pass even
   if the delayed rewrite were completely broken.
- `test_power_page_construction` checks `active_combo.currentData()` after a
  single snapshot, but does not test the snap-back scenario (user selects a
  different profile, snapshot refreshes, selection should be preserved).

### Prioritized list of additional tests

1. **PP-001:** `write_rapl_msr` bit-layout unit test (mock MSR, verify bits).
2. **PP-002:** Stale-task cancellation test (apply A then B, assert A cancelled).
3. **PP-006:** `_reconcile_power_profile` re-applies persisted profile.
4. **PP-006:** `_reconcile_power_profile` no-ops when desired == applied.
5. **PP-006:** `stop_competing_power_daemons` no-ops on non-Honor platform.
6. **PP-006:** `rewrite_epp` governor quirk test.
7. **PP-006:** `PowerPage` active-combo dirty-flag test (snap-back scenario).
8. **PP-004:** `_apply_power_profile` schedules delayed rewrite even when
   `ppd_ok=False` (after fix).
9. **PP-011:** Failed delayed rewrite surfaces in snapshot/health.
10. **PP-012:** `write_rapl_msr` fd leak test (mid-operation exception).

### Test failures / tooling failures encountered

- None. All 221 tests pass. `ruff` is clean. No type checker is configured.

---

## 6. Architecture and maintainability assessment

### Separation of responsibilities

The overall architecture is sound: `HardwarePort` protocol isolates hardware,
`HardwareCommandQueue` serializes all hardware I/O, `ApplicationService`
orchestrates, `ConfigStore` persists, `SnapshotStore` publishes. The D-Bus
and GUI layers are thin clients. This is a well-structured codebase.

The overhaul's new methods fit into `HonorToolsAdapter` appropriately (they
are hardware operations). The `_delayed_power_rewrite` and
`_reconcile_power_profile` methods fit into `ApplicationService`
appropriately (they are orchestration). The `PowerPage` dirty flag is a
pure UI concern and is correctly scoped.

### Abstraction quality

The `root_path` abstraction in `HonorToolsAdapter` is violated by the new
methods (PP-009). This is the most notable abstraction problem — it makes
the new methods untestable with the existing fake-filesystem pattern and
inconsistent with the rest of the adapter.

The `HardwarePort` protocol was correctly extended with the three new
methods, and `FakeHardware` implements them. This is good — the protocol
remains the single source of truth for the hardware interface.

### Coupling and cohesion

The `_delayed_power_rewrite` is tightly coupled to `_apply_power_profile` —
it receives a `PowerProfileState` directly, rather than re-reading the
current profile from config. This means if the profile definition changes
between the apply and the delayed rewrite (e.g., user edits the profile
within 0.5s), the delayed rewrite writes the old definition. This is a
minor concern but could be surprising.

The `stop_competing_power_daemons` method is coupled to systemd and the
`intel_pstate` sysfs interface, with no abstraction for the "competing
daemon" concept. If a new competing daemon appears (e.g., `tuned`), the
method must be edited directly. A configurable list of daemons would be
more extensible, but this is a minor concern given the current scope.

### State-management design

The separation of desired / applied / observed state is good. The
`_last_applied_power_profile` in-memory variable is a reasonable cache, but
it's not persisted — on restart, the service relies on `_reconcile_power_profile`
to re-apply the desired profile. This is correct.

The `_pending_power_task` reference is the only state management for the
delayed rewrite, and it's insufficient (PP-002): it doesn't cancel the
previous task, and it doesn't coordinate with the mutation lock (PP-010).

### Extensibility for future profiles or platforms

The profile system is extensible: custom profiles can be added via
`save_power_profile`, and the `POWER_PROFILES` tuple is the seed for
built-ins. The validation in `ConfigStore` is strict but allows custom PL1/PL2/governor/EPP combinations.

The new hardware methods are Intel-specific (MSR 0x610, `intel_pstate`
sysfs, EPP sysfs). The README documents this as Intel-only (commit
`34d31f9`). The platform guard (`_require_platform_or_none`) prevents the
methods from running on non-Honor hardware. This is a reasonable
limitation, but the methods are not abstracted behind an interface that
could support AMD in the future (e.g., AMD RAPL uses different MSRs and
sysfs paths).

### Duplication and complexity

- `_write_sysfs` / `_write_int` duplication (PP-015).
- The EPP retry loop in `rewrite_epp` duplicates the pattern in
  `honor.power._write_epp` (which the overhaul calls via
  `apply_power_profile` just 0.5s earlier). The two implementations have
  different retry counts and sleep durations, which could cause confusion.
- The MSR bit construction in `write_rapl_msr` is complex and error-prone
  (PP-001). A helper function with named fields and a test would reduce the
  risk.

### Naming and readability

- `_delayed_power_rewrite` is well-named (renamed from
  `_delayed_epp_rewrite` in commit `d391bb0`).
- `_active_combo_dirty` is clear.
- `stop_competing_power_daemons` is descriptive.
- `write_rapl_msr` is clear.
- The `hi` / `lo` variable names in `write_rapl_msr` are ambiguous — they
  don't make clear whether `hi` is the upper 32 bits or absolute bit
  positions. This contributed to PP-001.

### Whether a targeted refactor is justified

A targeted refactor of `write_rapl_msr` is justified to fix PP-001 (bit
layout) and PP-012 (fd leak). This should include:
- Named constants for bit positions.
- A helper function to build the MSR value.
- `try/finally` for fd cleanup.
- Unit tests for the bit layout.

A targeted refactor of `_delayed_power_rewrite` is justified to fix PP-002
(task cancellation) and PP-010 (mutation lock coordination). This should
include:
- Cancel previous task before scheduling.
- Re-check current profile before writing.

No broader rewrite is needed — the architecture is sound, and the issues
are localized to the new methods.

---

## 7. Positive observations

1. **Platform guard (commit `7213294`):** The `stop_competing_power_daemons`
   method correctly checks `_require_platform_or_none()` before doing
   anything. This prevents the service from stopping PPD on non-Honor
   hardware, where PPD is the standard power manager. This is a
   well-considered guard.

2. **Bounds checking on RAPL MSR writes (commit `d391bb0`):** The 3–150 W
   bounds check in `write_rapl_msr` is a good defense-in-depth measure,
   preventing dangerous values from reaching the CPU even if the config
   store validation is bypassed.

3. **MSR package-scoped write (commit `d391bb0`):** Writing to CPU 0 only
   (since MSR 0x610 is package-scoped) is correct and avoids unnecessary
   per-CPU writes. The cleanup commit correctly collapsed the
   `write_rapl_msr` / `_write_rapl_msr` indirection into one method.

4. **Task reference held to prevent GC (commit `15f4d66`):** The
   `_pending_power_task` reference is held to prevent the asyncio task from
   being garbage-collected before completion. This is a correct (if
   incomplete — see PP-002) awareness of asyncio task lifecycle.

5. **Reconciliation on startup (commit `15f4d66`):** `_reconcile_power_profile`
   correctly re-applies the persisted desired profile after service restarts,
   using `persist_desired=False` to avoid redundant state writes. The
   failure path (log and continue) is correct — reconciliation should never
   block service startup.

6. **UI dirty flag (commit `15f4d66`):** The `_active_combo_dirty` flag is a
   clean solution to the snap-back problem. The logic (clear when selection
   matches applied, preserve otherwise) is correct for the common case. The
   `currentIndexChanged` signal connection is properly guarded by
   `_loading`.

7. **Masking instead of disabling (commit `d391bb0`):** The choice of
   `systemctl mask` over `systemctl disable` is technically correct —
   masking prevents systemd from restarting the unit even if another service
   depends on it, and is cleanly reversible with `systemctl unmask`. (The
   execution is blocked by PP-003, but the reasoning is sound.)

8. **EPP governor quirk documentation (commit `15f4d66`):** The `rewrite_epp`
   docstring clearly explains the two intel_pstate quirks (read-back
   requirement, governor guard). The reasoning for leaving governor at
   `powersave` when `performance` is requested is documented and
   technically justified (EPP is the primary performance control on modern
   Intel CPUs).

9. **Cleanup commit (commit `d391bb0`):** The cleanup commit addressed
   several real issues: moving `stop_competing_power_daemons` from
   per-apply to `initialize()`, collapsing the MSR method indirection,
   renaming `_delayed_epp_rewrite` to `_delayed_power_rewrite`, and fixing
   stale docstrings. This shows good iterative refinement.

10. **README Intel-only documentation (commit `34d31f9`):** Clearly
    documenting the Intel-only limitation and the fail-safe behavior on AMD
    is good practice.

---

## 8. Prioritized remediation plan

### Must fix before merge or release

1. **PP-001 (Critical):** Fix the MSR PL2 bit-layout bug. Add a unit test
   that verifies all bit positions. This is a correctness bug that writes
   incorrect values to CPU hardware.

2. **PP-002 (High):** Cancel the previous `_pending_power_task` before
   scheduling a new one. Add a test that applies two profiles in quick
   succession and asserts the first task is cancelled.

3. **PP-003 (High):** Resolve the `systemctl mask` / `ProtectSystem=strict`
   incompatibility. Either move masking to `install-local.sh`, add
   `ReadWritePaths`, or drop masking and rely on the MSR write.

4. **PP-004 (High):** Resolve the PPD reactivation / `powerprofilesctl set`
   contradiction. Either skip `powerprofilesctl set` when PPD is stopped, or
   make `ppd_ok` non-blocking for the delayed rewrite, or drop PPD stopping
   entirely and rely on the MSR write + EPP read-back.

5. **PP-005 (High):** Resolve the `msr` module / `ProtectKernelModules`
   incompatibility. Either load `msr` in `install-local.sh`, remove
   `ProtectKernelModules=true`, or document the requirement and surface
   the failure in the snapshot.

6. **PP-006 (High):** Add tests for all new methods (see the prioritized
   list in section 5). At minimum, add tests for PP-001 and PP-002.

### Should fix soon afterward

7. **PP-010 (Medium):** Coordinate `_delayed_power_rewrite` with the
   mutation lock or re-check the current profile before writing.

8. **PP-011 (Medium):** Surface delayed-rewrite failures in the snapshot or
   service health.

9. **PP-008 (Medium):** Add cleanup of stopped/masked daemons on shutdown
   and uninstall.

10. **PP-007 (Medium):** Reduce the `time.sleep` blocking in `rewrite_epp`
    or move to async retries.

11. **PP-012 (Medium):** Fix the fd leak in `write_rapl_msr` with
    `try/finally`.

### Optional cleanup and longer-term improvements

12. **PP-009 (Medium):** Make new methods respect `root_path` for
    testability.

13. **PP-013 (Low):** Fix the misplaced `# -- Fan --` comment.

14. **PP-014 (Low):** Move stdlib imports to module level; remove redundant
    `import pathlib`.

15. **PP-015 (Low):** Unify sysfs write helpers.

16. **PP-016 (Low):** Update docs and CHANGELOG.

### Validation plan after fixes

1. Run `pytest tests/ -q` — all tests must pass.
2. Run `ruff check honor_control/ tests/` — must be clean.
3. Run the new tests added for PP-001 and PP-002.
4. On real Honor hardware (manual pre-release gate):
   - Apply "performance" profile; verify PL1=35 W and PL2=55 W in the MSR
     (read via `rdmsr 0x610`).
   - Apply "performance" then immediately "balanced"; verify the final
     RAPL values are balanced (not performance).
   - Restart the service; verify the persisted profile is reconciled.
   - Stop the service; verify PPD is restarted (if PP-008 is fixed).
   - Check `journalctl -u honor-control` for errors about MSR writes or
     systemctl failures.
5. Verify the systemd unit's hardening is compatible with the fixes
   (`systemd-analyze verify`, and a real `systemctl start` under the
   production unit).

---

## 9. Final verdict

**Requires significant fixes.**

The overhaul addresses real problems with a reasonable approach, but the
implementation has a critical MSR bit-layout bug (PP-001), a concurrency
race (PP-002), and a chain of deployment incompatibilities (PP-003,
PP-004, PP-005) that make the central mechanism — stopping PPD and writing
the RAPL MSR — likely ineffective in the production systemd unit. None of
the new methods has test coverage (PP-006).

### Minimum changes required to advance to "Ready with minor fixes"

1. Fix PP-001 (MSR bit layout) — correctness bug writing to CPU hardware.
2. Fix PP-002 (stale task cancellation) — race condition that can apply the
   wrong power profile.
3. Resolve PP-003 + PP-004 + PP-005 (deployment incompatibilities) — the
   `stop_competing_power_daemons` + `write_rapl_msr` chain must actually
   work under the production systemd unit's hardening, or the approach must
   be changed to one that does.
4. Add tests for PP-001 and PP-002 at minimum (PP-006).

Once these are fixed and verified on real hardware, the remaining findings
(PP-007 through PP-016) can be addressed as follow-up work.
