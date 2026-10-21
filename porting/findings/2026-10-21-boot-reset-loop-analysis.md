# The boot reset loop: what the logs say (2026-10-21)

## Status

**The qrtr crash loop is fixed and verified on the device; the reset is
postponed, not removed.**

`vendor.qrtr-ns` crash-looped for the whole boot because the Treble override
that gives it `CAP_NET_ADMIN` was installed in the `/system` subcontext and
init rejected it. The override now lives in the `/vendor` subcontext
(`/vendor/etc/init/qcrild.rc`), the crash loop is gone, and the 330 s reboot
request does not happen.

Measured on the flashed test image (`boot-test-vendorqrtr-padded.img`,
sha256 `78d35fb6e9fd302904c7396169d874d3f691d8d13a1c7dceea7222082555067f`):

| | broken image | fixed image |
| --- | --- | --- |
| `vendor.qrtr-ns` | restarts every ~5 s, exits status 1, whole boot | started once at 44.8 s (pid 717), never restarts |
| `CapEff` of `vendor.qrtr-ns` | `0x400` (NET_BIND_SERVICE only) | `0x1400` (NET_BIND_SERVICE **+ NET_ADMIN**) |
| reboot request | `sys.powerctl='reboot,bootloader'` at 330.13 s | none at 330 s; the same request at ~1367 s |
| uptime reached | 330 s | 1373 s, then the same adbd-watchdog reboot |

Two things are now established that were not before:

- **The reboot requester is `adbd`** - AOSP's adb watchdog
  (`packages/modules/adb/daemon/watchdog.cpp`) fires when no adb client has
  been connected for the watchdog timeout and executes
  `execl("/system/bin/reboot", "/system/bin/reboot", "bootloader", nullptr)`.
  It is not the ROM's rescue party, and not apexd.
- **The run320 boot's shutdown was a thermal emergency**, not the watchdog:
  the port's `kernel/reboot.c` forced a poweroff at 1676 s after a Geekbench
  run. The original explanation of the cooling-device topology below was
  incorrect; source review found CPU sensor-to-cooling-device binding gaps.

Evidence: `porting/artifacts/snapshot60/logs-2026-10-21/fixed-boot-vendorqrtr/`
(this boot) and `.../run320-boot/` against `porting/artifacts/snapshot60/logs-2026-10-20/`
(the broken boot).

## The symptom

The port kernel boots, Android comes up, and then the phone resets itself and
ends up in the ROM. Sometimes it sticks on the boot splash instead. The same
image does both.

## What the evidence shows

### The port kernel boots Android completely

`porting/artifacts/snapshot60/logs-2026-10-20/run317-logdump.bin`, text
region, first boot layer:

```
  0.161 s  ramoops: DIAG mark prev none (magic 00000000)
  6.19  s  mdss_mdp_probe: mdss version = 0x10100000, bootloader display is off
  21.4  s  DIAG: bootdevice guard installed read-only f2fs-only fstab and vendor contexts before policy load
  35.7  s  DIAG dsi_on: done ctrl=0 rc=0 state=0x4 pwr=1 clk_rate=802589760   <- panel on
  86.0  s  init: processing action (sys.boot_completed=1)
```

The display handover works, the guard wins its window, and `sys.boot_completed=1`
is reached. This boot was **not** a kernel failure.

### The reset is a userspace reboot request, not a kernel fault

At 330.13 s, in the same boot
(`logs-2026-10-20/run317-reboot-window.txt`):

```
init: Received sys.powerctl='reboot,bootloader' from pid: 6086 (/system/bin/reboot)
init: Got shutdown_command 'reboot,bootloader' Calling HandlePowerctlMessage()
init: reboot-bootloader: Error writing bootloader_message: Bootloader command pending.
init: Reboot start, reason: reboot,bootloader, reboot_target: bootloader
```

`/system/bin/reboot` (pid 6086) set `sys.powerctl`. init then ran a full
orderly shutdown: services SIGTERM/SIGKILLed, `vdc volume abort_fuse`,
`vdc volume shutdown`, apexes unmounted, `sync()`, `swapoff()`.

**The vold message is a consequence, not the cause.** The order in the log is:

| time | event |
| --- | --- |
| 330.132 s | `Received sys.powerctl='reboot,bootloader'` from pid 6086 |
| 330.136 s | `Reboot start, reason: reboot,bootloader` |
| 331.640 s | `init: Sending SIGKILL to service 'vold' (pid 365) process group...` |
| 331.973 s | `Service vold has 'reboot_on_failure' option and failed` |

vold was SIGKILLed *by* the shutdown that the reboot request started. Its
`reboot_on_failure reboot,vold-failed` guard then fired during the shutdown
that was already in progress. So the vold path is a **second, downstream
effect**, as the other session concluded — it is not the origin of the reset.

### Correction: the ROM's rescue party is NOT the reboot source

The previous revision of this document attributed the reboot to the Evolution X
rescue party (`server_configurable_flags` -> `/system/bin/reboot bootloader`).
**That attribution is wrong and is withdrawn.** Two independent facts kill it:

1. **The ROM's rescue path does not reboot.** The decoded ROM sources
   (`~/Downloads/flags_health_check-decoded.cc`,
   `disaster_recovery-decoded.cc`, `server_configurable_flags-decoded.cc`)
   show the whole path:

   ```
   flags_health_check.rc:  on property:sys.init.updatable_crashing=1
                               exec - system system -- /system/bin/flags_health_check UPDATABLE_CRASHING

   disaster_recovery.cc:   main() -> ServerConfigurableFlagsReset(UPDATABLE_CRASHING)

   server_configurable_flags.cc:
                           } else if (reset_mode == UPDATABLE_CRASHING) {
                             LOG(INFO) << "... updatable crashing detected, resetting flags.";
                             ResetAllFlags();
                           }
   ```

   `ResetAllFlags()` only clears `persist.device_config.*` properties and
   writes `/data/server_configurable_flags/reset_flags`. There is no reboot in
   that code path at all.

2. **That action never ran on the port.** Our own init removes the
   `on property:sys.init.updatable_crashing=1` stanza from
   `/system/etc/init/flags_health_check.rc`
   (`scripts/initramfs-diag/init.c:1175`, `filter_flags_health_check_rc()`).
   Both boot logs confirm it never fired - the only `flags_health_check` exec
   in the broken boot *and* in the fixed boot is the `BOOT_FAILURE` one:

   ```
   init: processing action (load_persist_props_action) from (/system/etc/init/flags_health_check.rc:1)
   init: starting service 'exec 28 (/system/bin/flags_health_check BOOT_FAILURE)'...
   ```

   There is no `processing action (sys.init.updatable_crashing=1)` line in
   either log.

So the ROM's flag-reset path was never the origin of the reset. What caused
the reset is the crash loop itself; *who* asked for the reboot is still
unattributed (see below).

### What PID 6086 was, and who spawned it

`init` logs the setter of `sys.powerctl` like this (upstream
`system/core/init/property_service.cpp:561`):

```cpp
    if (name == "sys.powerctl") {
        std::string cmdline_path = StringPrintf("proc/%d/cmdline", cr.pid);
        ...
        // Since cmdline is null deliminated, .c_str() conveniently gives us just the process path.
        process_log_string = StringPrintf(" (%s)", process_cmdline.c_str());
        LOG(INFO) << "Received sys.powerctl='" << value << "' from pid: " << cr.pid << process_log_string;
```

The `(...)` is `argv[0]` of the setting process. So PID 6086 was a process
whose `argv[0]` was `/system/bin/reboot`.

Upstream `system/core/reboot/reboot.c` is the whole of that binary:

```c
    prop_len = snprintf(property_val, sizeof(property_val), "%s,%s", cmd, optarg);
    ...
    ret = property_set(ANDROID_RB_PROPERTY, property_val);   // "sys.powerctl" = "reboot,bootloader"
    ...
    if (cmd == reboot) {
        while (1) { pause(); }                                // stay alive until the reboot lands
    }
```

It only *requests* the reboot; the decision was made by whoever spawned it.
That spawner is **not identified yet**. What the log and the device do say
about it:

- init did **not** track it as a service:

  ```
  init: Untracked process (pid: 6086 name: (reboot) ppid: 1 pgrp: 6086 state: Z) received SIGKILL
  ```

  For comparison, init's own exec services *are* tracked and logged with
  their command line - `init: starting service 'exec 28 (/system/bin/flags_health_check
  BOOT_FAILURE)'...`. So the spawner was not an `exec` stanza in an rc file.
  (The message format with `pid/name/ppid/pgrp/state` is the ROM's build of
  init; upstream AOSP prints `Untracked pid %d`,
  `system/core/init/sigchld_handler.cpp:97`.)

- `ppid: 1` and `pgrp: 6086`: on Linux an orphan is re-parented to PID 1, so
  `ppid 1` means the spawner had already exited when init reaped the zombie;
  `pgrp == pid` means the child was put in a new process group
  (`setpgid(0,0)`/`setsid`) before the exec. That is the daemonise pattern:
  fork, put the child in its own process group, exec `/system/bin/reboot
  bootloader`, let the parent exit.

- No rc file on the device execs the reboot binary:

  ```
  grep -rn "bin/reboot" /system/etc/init /vendor/etc/init /product/etc/init \
                         /system_ext/etc/init /apex --include=*.rc
  -> (nothing)
  ```

- Not apexd: upstream apexd only reboots after a **successful** revert, and
  the revert failed (see below).
- Not the AOSP Java framework: neither `RecoverySystem.java` nor
  `RescueParty.java` execs the reboot binary, and a Java caller that sets
  `sys.powerctl` itself would appear in the log with the system_server pid.

**The spawner is `adbd`, and it is AOSP's adb watchdog.** A device-wide search
for the string `bin/reboot` over `/system`, `/vendor`, `/system_ext`,
`/product`, `/odm` and `/apex` returns exactly one file:

```
/apex/com.android.adbd/bin/adbd
```

and that binary carries the two other strings that belong with it:

```
$ strings adbd | grep -nE "watchdog|bin/reboot|bootloader"
1043:adbd watchdog expired; rebooting...
1230:bootloader
1630:/system/bin/reboot 
2480:/system/bin/reboot
```

Upstream `packages/modules/adb/daemon/watchdog.cpp` is exactly that:

```cpp
static void UpdateWatchdog() {
    static std::once_flag once;
    std::call_once(once, []() {
        signal(SIGALRM, [](int) {
            LOG(WARNING) << "adbd watchdog expired; rebooting...";
            execl("/system/bin/reboot", "/system/bin/reboot", "bootloader", nullptr);
        });
    });
```

`argv[0]` is `/system/bin/reboot` - the exact string init printed - and the
`execl` runs in adbd's own process, which is why the reboot process is an
orphan in its own process group (libsubprocess double-forks and `setsid()`s)
with `ppid: 1` and `pgrp: 6086`.

The watchdog is armed by `persist.adb.watchdog=1` (or test-harness mode), with
a default timeout of 600 s (`persist.adb.watchdog.timeout_secs`), and it is
armed **while no adb client is connected** - `watchdog::Stop()` disarms it
when a client connects, `watchdog::Start()` re-arms it when the last one
disconnects. Its purpose is to recover devices that have fallen off the
network in an automated test lab.

So the chain is:

```
vendor.qrtr-ns crash-loops (no CAP_NET_ADMIN)
  -> init sets sys.init.updatable_crashing=1
  -> (the ROM's flag-reset path, which we filter out; it does not reboot)
  -> adbd has no client connected for the watchdog timeout
  -> adbd: execl("/system/bin/reboot", "/system/bin/reboot", "bootloader")
  -> init: Received sys.powerctl='reboot,bootloader' from pid: 6086 (/system/bin/reboot)
  -> init: Reboot start, reason: reboot,bootloader, reboot_target: bootloader
```

### The qrtr fix postpones the reboot; it does not remove it

The fixed image boots Android, the qrtr crash loop is gone, and the 330 s
reboot does not happen. But the phone still ends up in the bootloader, later.

The logdump partition carries the answer. Our diag init arms a ramoops region
at boot ("orderly reset capture armed offset=66256896 size=65536") and reads
the previous boot's reset note; the current boot found one:

```
ACKRESET1 timestamp_ns=1373460489162 action=1 pid=1 comm=init command=bootloader
...
[ 1373.466169][    T1] init: Reboot ending, jumping to kernel
[ 1373.466213][    T1] reboot: DIAG: kernel_restart_prepare enter cmd=bootloader
[ 1373.469346][    T1] ramoops: DIAG: orderly reset action=1 pid=1 comm=init command=bootloader
```

That is an **orderly reboot to the bootloader at 1373 s**, i.e. 273 s after
the shutdown sequence started and 6.27 s after the `sys.powerctl` request
(`init: powerctl_shutdown_time_ms:6274:2`). It is the same adbd-watchdog
reboot as before, just later in the boot.

Which boot it was, is settled by the service pids in the record, and they
match the fixed-image boot exactly and differ from both other boots:

| boot | adbd | logd | lmkd | tombstoned | vold |
| --- | --- | --- | --- | --- | --- |
| broken (run317) | 913 | 348 | 349 | 419 | 365 |
| **fixed image** | **921** | **346** | **347** | **417** | **363** |
| run320 | 915 | 347 | 348 | 419 | 365 |

The record's tail contains no `vendor.qrtr-ns` line at all, which excludes the
crash-looping boot.

So the qrtr fix moved the reset from 330 s to ~1367 s; it did not remove it.
The remaining trigger is the adbd watchdog, which fires when the phone has no
adb client attached for the timeout. Two ways to confirm the mechanism
directly, both cheap:

- connect an adb client and keep it connected: the watchdog is disarmed
  (`watchdog::Stop()`), and the phone survives;
- `persist.adb.watchdog=0` (or a large `persist.adb.watchdog.timeout_secs`):
  the watchdog never arms.

Neither property is set on the device today (`persist.adb.watchdog` is empty),
so the watchdog is armed by the *test-harness* path or by the property being
set during boot by the ROM. That is the next thing to check, and it is a
one-property experiment.

### The run320 boot's shutdown was a thermal emergency, not the watchdog

The run320 boot (`6.12.93-4k-gaeb37c4e232f`) was up for 1678 s and then died:

```
[ 1676.916405] reboot: HARDWARE PROTECTION shutdown (Temperature too high)
[ 1677.017335] reboot: Hardware protection timed-out. Trying forced poweroff
[ 1678.063221] reboot: Power down
```

This is the kernel's thermal emergency path, not adbd: `kernel/reboot.c`'s
`__hw_protection_shutdown()` and `hw_failure_emergency_poweroff_func()`, driven
by `thermal_zone_device_halt()` in `drivers/thermal/thermal_core.c:392` when a
**critical** trip point is crossed. The trigger was a Geekbench 7 run.

**Correction from source review (2026-10-21):** this is not evidence that CPU
throttling never worked. Commit `e04d51ef506e` and
`porting/artifacts/snapshot60/run304-thermal-stress.log` record cooling state 4
and both CPU frequency readings capped at 2304 MHz, with a peak of 91.6 C.

- All eight Cortex-A53 CPUs deliberately share one CPUFreq policy and coupled
  APCC clock transaction (`msm8953-cpu.dtsi`). One cooling device is expected;
  per-CPU cpufreq directories do not establish independent policies.
- `THERMAL_NO_LIMIT` means the full supported state range, not no throttling
  (`drivers/thermal/thermal_core.c`, `thermal_bind_cdev_to_trip()`).
- The source-level mismatch is that CPU1-7 zones reference CPU1-7, while the
  shared cooling device registers on CPU0. `of_cpufreq_cooling_register()`
  selects the policy CPU node; `thermal_of_get_cooling_spec()` requires exact
  DT-node equality. Those seven maps cannot bind to the reported CPU0 device.
  CPU0's sensor can still throttle the whole policy. Confirm live zone `cdev*`
  links before treating this mismatch as the cause of run320's shutdown.

The Tissot OC include now maps every CPU sensor to CPU0, with these initial,
**runtime-unverified** mitigation settings:

| CPU temperature | Action | Release |
| --- | --- | --- |
| 80 C | At least cooling state 8 (2016 MHz); step_wise may cool further | Below 78 C |
| 88 C | State 18 (480 MHz), conservative maximum-cooling backstop | Below 86 C |
| 100 C | Existing critical shutdown, unchanged | Not a performance control |

States are direct indices into the descending 19-entry OPP table, not CAF's
`THERMAL_MAX_LIMIT` arithmetic. The 88 C threshold is from donor
`oc-test/arch/arm64/boot/dts/vendor/qcom/mi8953/tissot/oc.dtsi`; 50 ms passive
and 100 ms normal polling come from its `msm8953-thermal.dtsi`
`deca-cpu-max-step` zone. The 80 C threshold and 2 C hysteresis are retained
from this port. Maximum cooling at 88 C is a conservative new policy, **not**
a claim of identical donor behaviour or calibrated thermal safety. GPU trips
remain 70/90 C. Other MSM8953 boards are unaffected.

The requested optimization target is balanced sustained performance: remove OC
headroom promptly, then let the governor adapt in the 80-88 C band. Do not
relax the 88 C backstop until repeated bounded measurements establish which
less restrictive cap actually arrests heating. No device was connected over
ADB during this change, so sustainable frequency and prevention of another
shutdown remain unverified.

Host verification: preprocess the board with `cpp`, check it with `dtc`, then
run `python3 porting/tests/test_cpu_thermal_maps.py <dtb>` and validate with
`dt-validate -s Documentation/devicetree/bindings/thermal/thermal-zones.yaml
-l thermal-zones <dtb>`. This checks all eight maps, OPP/state correspondence,
sensor IDs, polling, trip links and unchanged critical temperatures; it is not
a kernel build or runtime test.

These host checks passed. The regression check also rejects the HEAD baseline
and a DTB with CPU7 deliberately remapped to its own CPU node. DTC emitted the
same 14 diagnostic lines as the HEAD baseline, with no new diagnostics; focused
thermal-zone schema validation and strict checkpatch passed. AOSP's
[`android16-6.12` thermal_of.c](https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/drivers/thermal/thermal_of.c)
was cross-checked online and has the same exact-node matching requirement.
No kernel build, boot, load test or HAL change was performed.

Before a requested boot/test, follow `porting/REFERENCE-boot-testing.md` and use
the actual known-good base image. Verify the live DT, shared policy CPU mask,
all eight zones' `cdev*` links and trip associations. Record temperatures,
cooling states, policy limits and actual frequency under short bounded loads
and through cooldown; stop before critical temperatures and on continued
heating despite maximum cooling. Validate hot-sensor response and repeatable
recovery before attempting Geekbench. Do not emulate critical temperatures or
disable protection. Audit the ROM's thermal-engine/HAL naming and controls
separately; a HAL must not be the only thermal safety path. See also
[AOSP thermal mitigation](https://source.android.com/docs/core/power/thermal-mitigation)
and [upstream CPUFreq cooling](https://github.com/torvalds/linux/blob/master/drivers/thermal/cpufreq_cooling.c).

### `sys.init.updatable_crashing=1` alone does not reboot

This is a falsification that only the fixed boot could produce, and it
narrows the trigger considerably.

In the fixed boot, `vendor.bluetooth-1-0-qti` was killed by init seven times
between 99.4 s and 165.6 s, and init logged the same "updatable components"
message that the qrtr crash produced:

```
 132.149 s  init: process with updatable components 'vendor.bluetooth-1-0-qti' exited 4 times in 4 minutes
 157.726 s  init: process with updatable components 'vendor.bluetooth-1-0-qti' exited 4 times in 4 minutes
 165.594 s  init: process with updatable components 'vendor.bluetooth-1-0-qti' exited 4 times in 4 minutes
```

and on the live device `sys.init.updatable_crashing=1` with
`sys.init.updatable_crashing_process_name=vendor.bluetooth-1-0-qti`.

**No reboot followed.** The fixed boot's kernel log covers 0 - 930.6 s and
contains zero `Received sys.powerctl` and zero `Reboot start` lines, and the
device was still up at 1107 s.

So `sys.init.updatable_crashing=1` is *not* the trigger. The trigger is the
`vendor.qrtr-ns` crash loop specifically - about 58 crashes in five minutes,
every ~5 s - and it is gone with the override in place.

### apexd's failed revert is a consequence, not the trigger

```
apexd: Native process 'vendor.qrtr-ns' is crashing. Attempting a revert
apexd: Revert failed : Revert requested, when there are no active sessions.
```

This matches upstream `apexd.cpp` exactly: `RevertActiveSessions()` returns
`Error() << "Revert requested, when there are no active sessions."` when
there is nothing to revert, and `RevertActiveSessionsAndReboot()` only reboots
**after** a successful revert. So apexd did not reboot here, and its reboot
would have been a normal system reboot, not the `bootloader` target that was
observed. apexd is a bystander in this symptom.

In the fixed boot apexd does not report the bluetooth crash at all, because
init killed that service (SIGKILL) rather than letting it crash on its own.

### The Treble override of `vendor.qrtr-ns` is rejected, and it always was

The port's init injects an override of `vendor.qrtr-ns` into
`/system/etc/init/flags_health_check.rc` to give it `CAP_NET_ADMIN`. The ROM's
init rejects it:

```
init: /system/etc/init/flags_health_check.rc: 12: service 'vendor.qrtr-ns' overrides another service across the treble boundary.
init: /system/etc/init/flags_health_check.rc: 20: service 'vendor.per_mgr' overrides another service across the treble boundary.
init: /system/etc/init/flags_health_check.rc: 30: service 'qcamerasvr' overrides another service across the treble boundary.
```

The check compares the **subcontext** of the two definitions, so a `/system`
file cannot override a `/vendor` service. **None** of the three overrides in
the system-side file ever applied, in any image built so far.

The result was visible immediately afterwards:

```
init: Service 'vendor.qrtr-ns' (pid 708) exited with status 1
init: Service 'vendor.qrtr-ns' (pid 1106) exited with status 1
...  (every ~5 s, for the whole boot)
```

`vendor.qrtr-ns` crash-looped from 37 s to the end of the boot. 6.12's
`qrtr_port_assign()` (`net/qrtr/af_qrtr.c:736`) needs `CAP_NET_ADMIN` for a
specified port below `QRTR_MIN_EPH_SOCKET`, and the check is upstream, not new
in 6.12 (present in v5.15 `net/qrtr/qrtr.c` and v6.0 `net/qrtr/af_qrtr.c`).

After four crashes in four minutes, upstream init's service.cpp does:

```
init: process with updatable components 'vendor.qrtr-ns' exited 4 times in 4 minutes
```

which sets `sys.init.updatable_crashing=1` and
`sys.init.updatable_crashing_process_name=vendor.qrtr-ns` (both confirmed live
on the device), and apexd reacts:

```
apexd: Native process 'vendor.qrtr-ns' is crashing. Attempting a revert
apexd: Revert failed : Revert requested, when there are no active sessions.
```

The revert fails (there are no active APEX sessions), so **apexd does not
reboot**.

### The reset happens on a boot that completed

The reboot request at 330.13 s is **4.4 minutes after `sys.boot_completed=1`**.
Whatever asks for it is not reacting to an incomplete boot - it is reacting to
the qrtr crash loop, which by then has been running for five minutes.

`persist.sys.boot.reason.history` shows the same shape across boots:

```
bootloader,4028
bootloader,3291
bootloader,2759
bootloader,2219
reboot,shell,469
```

Four consecutive boots ended with the reason `bootloader`, the one before them
a shell reboot. The port's own boots are the ones ending in `bootloader`.

### The ROM's rescue party also has a boot-attempt counter

`server_configurable_flags.so` carries:

```
 attempted boot count reaches threshold, resetting flags.
 attempted boot count is under threshold, skipping reset.
 persist.device_config.attempted_boot_count
```

and the ROM's `flags_health_check.rc` resets that counter on
`sys.boot_completed=1`:

```
on property:sys.boot_completed=1
    setprop persist.device_config.attempted_boot_count 0
```

so the counter is about *failed* boots. It is not what produced the reboot
here (this boot completed), but it is the ROM's second line of defence, and it
means a boot that never completes is counted, not ignored.

## Fixes

### 1. Drop the UART console at packaging time (done, main tree)

`porting/tools/build-kernel.sh` now removes `earlycon` and
`console=ttyMSM0,115200` from the command line, which the base image carries
into every image. The tokens are filtered against the base's own command line
first, so a base without them still packages, and the post-package check fails
the build if either token survives.

This is the crash the port's own pstore recorded on the failed boot
(`failed-boot-ramoops-dmesg-0.log`): a synchronous external abort at 7.25 s in
`msm_serial_probe` -> `printk` -> `msm_serial_early_write_dm` ->
`readl_relaxed`. The UART is not accessible at that moment, and the early
console is what touches it.

### 2. Move the qrtr override into the vendor subcontext (done, verified on device)

`scripts/initramfs-diag/init.c` replaces the system-side `flags_health_check.rc`
override with `guard_vendor_qrtr()`, which appends the override to
`/vendor/etc/init/qcrild.rc`.

The parse order from the device's own init makes this work
(`logs-2026-10-20/run317-kernel-log.txt`):

```
 28.889 s  init: Parsing file /vendor/etc/init/hw/init.qcom.rc...    <- vendor.qrtr-ns defined here
 29.062 s  init: Parsing file /vendor/etc/init/qcrild.rc...          <- the override lands here
```

The override is in the same subcontext as the original definition and is
parsed after it, which is what the Treble check requires. On the device:

```
$ grep -A6 "service vendor.qrtr-ns" /vendor/etc/init/qcrild.rc
service vendor.qrtr-ns /vendor/bin/qrtr-ns -f
    class core
    user vendor_qrtr
    group vendor_qrtr
    capabilities NET_BIND_SERVICE NET_ADMIN
    override

$ grep -E "^(Name|CapEff|CapPrm|CapBnd)" /proc/$(pidof qrtr-ns)/status
Name:	qrtr-ns
CapPrm:	0000000000001400
CapEff:	0000000000001400
CapBnd:	0000000000001400
```

No kernel rebuild was needed for this: the fix is in the init binary. The
test image differs from run304 in exactly one ramdisk record (`init`) and in
the command line (no `earlycon`, no `console=ttyMSM0,115200`).

### 3. The vold reboot path is not the origin

`reboot,vold-failed` fires 1.84 s after the shutdown it was killed by had
already started. Fixing vold will remove the message, not the reset.

## Still open

- **Why the adb watchdog is armed on this device.** `persist.adb.watchdog` is
  empty and `persist.sys.test_harness` is empty on the phone, yet the
  watchdog fired (the 330 s reboot in the broken boot and the 1367 s reboot in
  the fixed boot). Either the ROM sets one of them during boot, or the
  watchdog arms through the `persist.adb.watchdog.timeout_secs` monitor path
  (`daemon/watchdog.cpp` arms with `alarm(g_watchdog_timeout_seconds)`, and
  the timeout is only set by that monitor callback). The next experiment is
  one property: set `persist.adb.watchdog=0` (or keep an adb client attached
  for the whole boot) and see whether the 1367 s reboot disappears.
- **The upstream QRTR introducing commit.** The check is upstream and old
  (`bdabad3e363d`, "net: Add Qualcomm IPC router", 2016, and the same in CAF
  4.19), so the fix belongs in the init/service definition, not the kernel.
  The kernel side is settled.
- **CPU sensor cooling-map gaps.** The single shared CPU policy is intentional,
  and `THERMAL_NO_LIMIT` permits throttling. CPU1-7 maps instead reference
  nodes without the shared cooling device. The Tissot OC include now fixes
  those bindings and adds stronger staged mitigation; runtime verification
  and balanced-performance calibration are still outstanding (see above).
- **`vendor.bluetooth-1-0-qti` crash-loops** (init SIGKILLs it every ~10 s
  until it settles). It sets `sys.init.updatable_crashing=1` but does not
  reboot the phone - see above. It is a separate defect.
- **`qrtr_ns_worker: failed to send del client cmd` spam** continues in the
  fixed boot (once per second). The name service is alive; the clients are
  not. Separate defect, not related to the reset.
- **The logdump recorder stops at ~930 s per boot** (`DIAG: EOF Android kmsg
  dump complete`), so the window in which the 1367 s reboot happened is not
  in the captured log. The reset note in the ramoops region is what closed it.

## Evidence files

| File | What |
| --- | --- |
| `logs-2026-10-20/run317-logdump.bin` | the boot that reached `sys.boot_completed=1` and was reset at 330 s |
| `logs-2026-10-20/run317-kernel-log.txt` | that boot's kernel log as text |
| `logs-2026-10-20/run317-reboot-window.txt` | the 329.9-330.3 s window, verbatim |
| `logs-2026-10-20/run318-logdump.bin` | the same boot, later, still running (qrtr-ns still crash-looping) |
| `logs-2026-10-20/failed-boot-ramoops-console-0.log` | the failed boot's console (the 7.25 s UART abort) |
| `logs-2026-10-20/failed-boot-ramoops-dmesg-0.log` | the failed boot's dmesg (the abort) |
| `logs-2026-10-20/failed-boot-ramoops-dmesg-1.log` | the failed boot's panic record |
| `logs-2026-10-21/fixed-boot-vendorqrtr/` | the fixed boot: 0-930 s kernel log, dmesg, boot properties, no reboot |
