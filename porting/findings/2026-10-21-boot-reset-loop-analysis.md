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

### PID 6086's parent is still unknown, but its shape is known

```
init: Untracked process (pid: 6086 name: (reboot) ppid: 1 pgrp: 6086 state: Z) received SIGKILL
```

- `ppid: 1` — its parent was init (pid 1): it was a **direct child of init**,
  and init does not track it as a service. `init` only execs
  `/system/bin/reboot` through a `service`/`exec` line in an rc file, and a
  tracked one would have been named.
- `pgrp: 6086` — it was in its own process group, i.e. it called `setsid()`.
- `/system/bin/reboot` itself only does one thing: it sets `sys.powerctl`
  (`strings /system/bin/reboot` -> `sys.powerctl`, `usage: %s [-p] [rebootcommand]`).

So an unnamed, session-leading child of init ran `/system/bin/reboot
bootloader`. No ROM binary on the device contains the string
`/system/bin/reboot` or `reboot bootloader`
(`grep -ral` over `/system/lib64`, `/vendor/lib64`, `/system/bin`, `/vendor/bin`,
`/system_ext/lib64` -> no hit), and no rc file execs it
(`grep -rn "bin/reboot"` over every init directory -> no hit). That is why the
ROM source is needed: the caller is either a native binary that resolves the
path at runtime, or a code path not visible in the shipped files.

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
Whatever asks for it is not reacting to an incomplete boot. Combined with
`persist.sys.boot.reason.history`:

```
bootloader,4028
bootloader,3291
bootloader,2759
bootloader,2219
reboot,shell,469
```

four consecutive boots ended in the **bootloader** target, with the one before
them a shell reboot. The port's own boots are the ones ending in `bootloader`.

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

- **Parent and argv of PID 6086.** An unnamed, session-leading direct child of
  init ran `/system/bin/reboot bootloader`. Needs the ROM's init/native source
  (Evolution X `cnb` branch) or an `execve` trace.
- **The Android 17 `apexd` path** from a failed `RevertActiveSessions()` to
  `sys.powerctl=reboot,bootloader`.
- **The upstream QRTR introducing commit** and the CAF 4.19 equivalent, to
  decide whether the fix belongs in the kernel or in the init.

## Evidence files

| File | What |
| --- | --- |
| `run317-logdump.bin` | the boot that reached `sys.boot_completed=1` and was reset at 330 s |
| `run317-kernel-log.txt` | that boot's kernel log as text |
| `run317-reboot-window.txt` | the 329.9-330.3 s window, verbatim |
| `run318-logdump.bin` | the same boot, later, still running (qrtr-ns still crash-looping) |
| `run315/316-logdump.bin` | earlier pulls of the same partition |
| `failed-boot-ramoops-console-0.log` | the failed boot's console (the 7.25 s UART abort) |
| `failed-boot-ramoops-dmesg-0.log` | the failed boot's dmesg (the abort) |
| `failed-boot-ramoops-dmesg-1.log` | the failed boot's panic record |
