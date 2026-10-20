# The boot reset loop: what the logs say (2026-10-21)

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

### PID 6086 is the EvoX rescue party, and its parent is init

The 320-335 s window (`logs-2026-10-20/run317-reboot-window.txt`) shows the
sequence with nothing else in it:

```
 325.760  init: starting service 'vendor.qrtr-ns'...
 325.807  init: Service 'vendor.qrtr-ns' (pid 6070) exited with status 1
 325.809  init: process with updatable components 'vendor.qrtr-ns' exited 4 times in 4 minutes
   ...    (only the hwservicemanager "Could not find 'vendor.qti.data.factory'" line repeats)
 330.132  init: Received sys.powerctl='reboot,bootloader' from pid: 6086 (/system/bin/reboot)
 330.135  init: Reboot start, reason: reboot,bootloader, reboot_target: bootloader
```

The reboot request arrives **4.3 s after the last qrtr-ns crash**, with no
other actor in between.

`init` itself carries the property name and nothing else:

```
$ strings /system/bin/init | grep updatable_crashing
sys.init.updatable_crashing_process_name
sys.init.updatable_crashing
```

and the ROM's **rescue party** library carries the reaction:

```
$ strings /system/lib64/server_configurable_flags.so
 updatable crashing detected, resetting flags.
 attempted boot count reaches threshold, resetting flags.
 attempted boot count is under threshold, skipping reset.
 persist.device_config.attempted_boot_count
$ strings /system/bin/flags_health_check
system/server_configurable_flags/disaster_recovery/disaster_recovery.cc
disable_rescue_party
```

`/system/bin/flags_health_check` is the ROM's disaster-recovery entry point
(it is the `exec` line in the ROM's own `flags_health_check.rc`), and
`server_configurable_flags.so` is what detects "updatable crashing". So the
chain is:

```
vendor.qrtr-ns crash-loops (no CAP_NET_ADMIN)
  -> init sets sys.init.updatable_crashing=1
  -> the ROM's server_configurable_flags sees "updatable crashing detected"
  -> the rescue path runs /system/bin/reboot bootloader
  -> init: Reboot start, reason: reboot,bootloader
```

`/system/bin/reboot` only does one thing: it sets `sys.powerctl`
(`strings /system/bin/reboot` -> `sys.powerctl`, `usage: %s [-p] [rebootcommand]`).
That is why it appears as the requester of the property rather than as the
process that reboots: **the ROM asks for the reboot, init performs it.**

`init` does not fork it as a tracked service, which is consistent with what
the log shows:

```
init: Untracked process (pid: 6086 name: (reboot) ppid: 1 pgrp: 6086 state: Z) received SIGKILL
```

`ppid: 1` and `pgrp: 6086` mean the process was a session leader whose parent
had already exited and been re-parented to init. Upstream `init` has exactly
one path that forks a session leader and lets it outlive its parent:
`InitFatalReboot()` in `system/core/init/reboot_utils.cpp` forks a child that
sleeps 5 s and then calls `RebootSystem(ANDROID_RB_RESTART2,
init_fatal_reboot_target)`, with `init_fatal_reboot_target` defaulting to
`bootloader`. The device's init carries `androidboot.init_fatal_reboot_target`
and `Reboot start, reason: ` from `system/core/init/reboot_utils.cpp`.

**What is still open** is which of the two candidate parents it was:

- `init`'s own fatal path (`InitFatalReboot`), which does **not** go through
  `sys.powerctl` - the property path and the fatal path are different code,
  and the observed event is the property path, so this candidate does not fit
  what was logged;
- the ROM's rescue party, which does use `sys.powerctl`.

The evidence favours the rescue party: the request lands 4.3 s after the
qrtr crash, `/system/bin/reboot` is the requester, and the ROM ships a
library whose only string about this is "updatable crashing detected". The
open item is the ROM's `server_configurable_flags` source, which is not in
the shipped files (only the `.so` is) and is in the Evolution X `cnb` tree.

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

The result is visible immediately afterwards:

```
init: Service 'vendor.qrtr-ns' (pid 708) exited with status 1
init: Service 'vendor.qrtr-ns' (pid 1106) exited with status 1
...  (every ~5 s, for the whole boot)
```

`vendor.qrtr-ns` crash-loops from 37 s to the end of the boot. 6.12's
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
reboot**. But `apexd` has `android_reboot` and `Rebooting device` in its
strings, and it also has `Failed to reboot device` and `Device did not reboot
within 120 seconds`. Whether the Android 17 build turns the failed revert into
a reboot is the open item.

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

### 2. Move the qrtr override into the vendor subcontext (implemented, not yet booted)

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
parsed after it, which is what the Treble check requires.

**No packaged image contains this fix.** Every image from run303 to run316
carries the same `init` binary, `fc919bb425620e098f025d3e2383b73374c87b9a68fc5fa8932a2ac3770292e9`,
which is the broken one. The fix has never been built or booted.

Test image built for it (no kernel rebuild needed - the fix is in the init
binary and the command line):

| | |
| --- | --- |
| image | `../ack-kgsl-artifacts/boot-test-vendorqrtr.img` |
| sha256 | `0f93c9c2d061395e54a3afdd32a724186ab5638ae4e8d60dcde0eb4e3f7bbd88` |
| init | `4f310e13cf28521b166757784d27c17693f1522db9c3178acdaa8f95a310436e` |
| kernel | `c4e5e2551dae907ed06a7707a8bdbbda03aa0c957f80db09461e5f23f63c9f4b` (identical to run304) |
| ramdisk | 696 records, the same set as run304; **only `init` differs** |
| cmdline | no `earlycon`, no `console=ttyMSM0,115200` |

### 3. The vold reboot path is not the origin

`reboot,vold-failed` fires 1.84 s after the shutdown it was killed by had
already started. Fixing vold will remove the message, not the reset.

## Still open

- **The ROM's `server_configurable_flags` / `disaster_recovery` source.** The
  rescue party is identified from the shipped `.so` strings, but the code that
  decides to run `/system/bin/reboot bootloader` is in the Evolution X `cnb`
  tree (`system/server_configurable_flags/`), not in the shipped files. It is
  the one artifact that would close the chain end to end. It matters because
  the fix is now clear: the crash loop must stop, and the crash loop stops
  when `vendor.qrtr-ns` gets `CAP_NET_ADMIN`.
- **The upstream QRTR introducing commit.** The check is upstream and old
  (`bdabad3e363d`, "net: Add Qualcomm IPC router", 2016, and the same in CAF
  4.19), so the fix belongs in the init/service definition, not the kernel.
  The kernel side is settled.

## Evidence files

| File | What |
| --- | --- |
| `run317-logdump.bin` | the boot that reached `sys.boot_completed=1` and was reset at 330 s |
| `run317-kernel-log.txt` | that boot's kernel log as text |
| `run317-reboot-window.txt` | the 329.9-330.3 s window, verbatim |
| `run318-logdump.bin` | the same boot, later, still running (qrtr-ns still crash-looping) |
| `failed-boot-ramoops-console-0.log` | the failed boot's console (the 7.25 s UART abort) |
| `failed-boot-ramoops-dmesg-0.log` | the failed boot's dmesg (the abort) |
| `failed-boot-ramoops-dmesg-1.log` | the failed boot's panic record |
