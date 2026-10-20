# run302: the crash-loop overlay is in the image but did not install — 2026-10-20

This is the run302 verification of the fixes described in
[qrtr-ns-and-crash-loops-20261020.md](qrtr-ns-and-crash-loops-20261020.md)
and the KSU/NFC/ramoops commits.  The kernel side landed.  The initramfs
overlay that carries the health-check removal and the qrtr/camera/dataqti
overrides did not.

## The image

```
Linux localhost 6.12.93-4k-gda553ac9776d #8 SMP PREEMPT Tue Oct 20 16:20:03 +0545 2026 aarch64
slot _b
sys.boot_completed=1
sys.init.updatable_crashing=1
sys.boot.reason=reboot,checkpoint_commit_failed
```

The image is `porting/artifacts/snapshot60/boot-run302.img`, built at 16:20.
Its ramdisk `/init` is the rebuilt guard:

```
init-run302 sha256        86ff42b597f3019e914b191deaa3914c06d4a0719ec08bed292bf014f0d49bbe
boot-run302.img ramdisk /init
                          86ff42b597f3019e914b191deaa3914c06d4a0719ec08bed292bf014f0d49bbe
```

and `strings init-run302` contains `DIAG: flags_health_check rc override
errno=%d`, the qrtr `capabilities NET_BIND_SERVICE NET_ADMIN` override, and
the camera/dataqti stops.  The boot image is not carrying a stale init, and
the package record agrees (`package-run302.json: init_sha256`).

## What still happens

The ROM's original `flags_health_check.rc` is still in effect.  Its action
is still at lines 10/11 and still executes:

```
init: processing action (sys.init.updatable_crashing=1) from (/system/etc/init/flags_health_check.rc:10)
init: starting service 'exec 217 (/system/bin/flags_health_check UPDATABLE_CRASHING)'...
init: Command 'exec - system system -- /system/bin/flags_health_check UPDATABLE_CRASHING' ... succeeded
```

At 6 minutes the counter was already at exec 217, roughly one health-check
exec per 1.7 s.  The service states are still the pre-overlay ones:

```
vendor.qrtr-ns=restarting          (exit 1 every ~5 s)
vendor.per_mgr=restarting
vendor.per_proxy=restarting
qcamerasvr=restarting
vendor.dataqti=running             (QTI_SDM_INFO retry flood)
sys.init.updatable_crashing=1
```

`vendor.qrtr-ns` still does not have `NET_ADMIN` (the service definition is
still the vendor one; there is no new `avc: denied { net_admin }` because
the capability is absent before SELinux is consulted).  `qcamerasvr` and
the peripheral-manager stack are still restarting; `vendor.dataqti` is
still running and retrying; the `QTI_SDM_INFO` lines are still in logcat.
The camera/dataqti stops and the qrtr capability override are all in the
same missing overlay, so this is one failure, not several.

## What did land

* **KernelSU:** zero soft-lockup/BUG lines in the current boot.  The
  `tp_marker` per-thread logging is gone from the kernel; the grant path
  has not been exercised on this image, so the one-summary-line check is
  still pending.  The `KernelSU: hook_manager: unmark` lines are the normal
  exec hook, not the grant path.
* **NFC:** `# CONFIG_NFC is not set` in the embedded config; no
  `/sys/class/nfc` and no `/dev/nfc*`.
* **ramoops:** `ramoops_snap` is present and sleeping
  (`State: S (sleeping)`, 20 voluntary context switches); the periodic
  snapshot polling is gone.  The `ramoops: DIAG signal_first` lines are the
  orderly-reset signal diagnostics, not a periodic snapshot.  The pstore
  is empty on this boot (the reboot reason is a userspace checkpoint
  failure, not a kernel panic).
* **Policy fragment:** `package-run302.json` records the
  `port-genfs-kgsl.cil` append, so the fragment is in the boot image.  The
  runtime relabel diagnostics still showed
  `DIAG: wakeup stats relabelled labels=0 ... skipped=1` and
  `DIAG: kgsl sysfs relabelled labels=0 ... skipped=1` earlier in the boot
  (the kernel ring has since rotated past them).  That is the separate
  wakeup/checkpoint path owned by the boot-reliability work; it is recorded
  here only so it is not confused with this overlay failure.

The diagnostic services from the base image are also still running:
`ack-early-logcat` and `ack-sync-loop` (the latter runs `sync` every 5 s).
They are not part of this change set.

## Why the overlay did not install

This is the working explanation.  The exact errno line was not captured, so
treat the errno as unverified; the ordering and the observed effects are
verified.

The guard did run: the detached children logged (`DIAG: adsprpc compat:
fastrpc-adsp never appeared` at 282.9 s, and the relabel loop earlier), and
the `ack-early-logcat` overlay from the same guard is live.  The guard is
the rebuilt one.

`guard_flags_health_check()` used to be the last step of
`install_android_guard()` (`scripts/initramfs-diag/init.c`), after
`guard_firmware()`, `harvest_modem_firmware()`, `adsprpc_compat_fork()` and
`guard_debuggable()`.  It could not take effect for two reasons:

1. **Parse order.** `flags_health_check.rc` lives in
   `/system/etc/init`.  AOSP's init imports
   `/{system,system_ext,vendor,odm,product}/etc/init` in that order,
   alphabetically inside each directory, immediately after
   `/system/etc/init/hw/init.rc`
   ([init/README.md, Imports](https://raw.githubusercontent.com/aosp-mirror/platform_system_core/master/init/README.md)).
   The file is therefore read early in second-stage init, before the
   vendor init files and before the late guard steps.  By the time the
   late call ran, the ROM had already parsed the original file.
2. **Pre-policy window.** `guard_bind_config()` only installs a bind if
   `guard_pre_policy()` still sees PID 1 as the pre-policy `kernel` SID
   (`scripts/initramfs-diag/init.c:966,1004`).  That window is the first
   ~1.35 s after the guard starts.  The last call was after the firmware
   and debuggable passes, so the second pre-policy check was too late even
   if the parse-order problem were absent.

The function logs `DIAG: flags_health_check rc override errno=N` in every
path, including success (`errno=0`).  The line was emitted too early for
the 6-minute kernel ring: the current ring starts at 248 s, while the
health-check runs in the guard's early window.  logd starts after the
guard, and the pstore record is empty, so there is no surviving copy.  A
next boot with the call moved earlier can show `errno=0` directly.

The same file carries `crashloop_rc`, so the qrtr, camera and dataqti
changes fail with it.  That exactly matches the observation: the
health-check removal is missing, the qrtr capability is missing, the
camera stack is not disabled, and dataqti is not stopped.

A related documentation correction: the `crashloop_rc` comment said the
system file is parsed after the vendor files.  It is the other way round.
The system-side `override` definitions are the ones init keeps; the later
vendor definitions for the same names are duplicates and are ignored.  The
behavior the overlay relies on is still correct, but the reason is the
import order above.

## Fix in the tree

The call is moved from the end of the sequence to immediately after the
USB-controller bind and before the early-logcat overlay:

```c
if (guard_usb_controller(proc, log))
	goto failed;
guard_flags_health_check(proc, log);
#ifdef ANDROID_EARLY_LOGCAT
guard_early_logcat(proc, log);
#endif
```

Both files are in `/system/etc/init`, so both overlays now install in the
same pre-policy pass; `flags_health_check.rc` is alphabetically before
`logd.rc`, and the health-check is installed first.  The fstab, vendor
contexts and bootdevice release are unchanged.  The `crashloop_rc`
comment was corrected to describe the actual import order.

## Verification after the next flash

1. `dmesg | grep 'DIAG: flags_health_check rc override'` shows `errno=0`
   (or names the real errno).
2. `dmesg | grep 'flags_health_check UPDATABLE_CRASHING'` has no new entry
   after the first boot transition; `sys.init.updatable_crashing` may
   still read `1`.
3. `init.svc.vendor.qrtr-ns` is `running`; no
   `bind control socket: Permission denied`, and no
   `avc: denied { net_admin }`.
4. `init.svc.vendor.per_mgr`, `vendor.per_proxy` and `qcamerasvr` are
   stopped; `vendor.dataqti` is stopped; no `QTI_SDM_INFO` retry flood.
5. The kernel QRTR NS remains active on the control port.
6. The ramoops/NFC/KSU checks stay as recorded above; the KSU grant path
   still needs a manual toggle with an app other than FKM.

## Why these particular changes

The design rationale is in
[qrtr-ns-and-crash-loops-20261020.md](qrtr-ns-and-crash-loops-20261020.md):
qrtr needs both the init capability and the SELinux allow; the camera stack
is out of scope and is disabled rather than left looping; dataqti's
`/dev/rmnet_ctrl0`, `/dev/smdcntl8` and MHI pipes do not exist until the
modem data path is up, so it is stopped rather than retried.  The
health-check loop is not a service crash; it is init reacting to
`sys.init.updatable_crashing=1` on every vendor crash, which is why the
overlay keeps `BOOT_FAILURE` and the boot-count reset and removes only the
`UPDATABLE_CRASHING` action.
