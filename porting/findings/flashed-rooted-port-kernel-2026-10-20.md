# run266-282: a flashed, rooted port kernel, and the two policy defects

Date: 2026-10-20. Continues
`cpu-boot-failure-analysis-run265-2026-10-19.md` and
`cpu-boot-failure-analysis-run270-272-2026-10-20.md`.

## 1. What changed in the working method

The port kernel is now **flashed to the boot partition** (slot b) instead of
being RAM-booted every time, and it has **root**.

| Run | Image | What it is |
|---|---|---|
| 279 | `boot-run279.img` `8b6d9733f66a3e8c7ba207a9b398f516f002a2469f7cf3aef2f715bf10b16270` | the run267 kernel (the kgsl timeline and reboot-path diagnostics), flashed to `boot_b` |
| 281 | `boot-run281.img` `22babb28d4f6c5d421da071d63d90915c850c6fc298907a8e88373918eb42541` | run279 plus **KernelSU-Next v3.4.2 built into the kernel** |
| 282 | `boot-run282.img` | run281 plus the diag init that relabels the sysfs nodes (section 5) |
| 283 | `boot-run283.img` `205527e9852e8799fce693c788233379ac87608ae7bce488144a583f6ef71ccd` | the relabel moved in front of the guard; **it hangs the phone** (section 6) and was reverted on the device back to run282 |

Flashing is `fastboot flash boot_b <image padded to 64 MiB>`; the device's
bootloader is unlocked (`androidboot.verifiedbootstate=orange`), and
`fastboot getvar current-slot` says `b`. A backup of the phone's original
boot partition is in `stock-boot-live.bin` (sha256
`62159562302d5b74f07a2cfd9e11bc75f2ed1792f11aa560277ad6a626d5f345`).

**The consequence that matters: the phone now comes back on the port kernel
by itself after a power cycle.** The "boot the RAM image, watch it, reboot,
pull the logdump" dance - which needed a live host and cost ~12 minutes a
cycle - is gone. A hung port kernel is recovered with a long press on the
power button, and the next boot is the port kernel again.

## 2. KernelSU-Next in the port kernel

The driver is vendored in at `drivers/kernelsu/` (87 files from the v3.4.2
tag, plus the six shared `uapi/` headers under `drivers/kernelsu/uapi/`),
wired in with two lines in `drivers/Makefile` and `drivers/Kconfig`, and
selected with `CONFIG_KSU=y`.

Two details that are not optional:

* **The version must be pinned.** The driver computes its version as
  `30000 + <its own commit count>`, and it can only do that when it lives
  in a repository of its own. Vendored into this tree it would fall back to
  version 1, which no manager accepts. The build therefore passes
  `KSU_GIT_VERSION=3355 KSU_GIT_VERSION_VALID=1 KSU_GIT_TAG=v3.4.2`,
  which gives version 33355 - the version in the v3.4.2 release's manager
  APK name, and the version whose signing certificate hashes to the
  `79e59011...` the driver requires.
* **The driver only talks to a manager whose certificate matches.** The
  matching APK is `KernelSU_Next_v3.4.2_33355-release.apk` from the same
  release; a self-built manager will not be recognised.

With that, the adb shell can be root: the manager's **adb root** feature
(`KSU_FEATURE_ADB_ROOT`) makes `adb shell` come up as `uid=0` in the
`u:r:ksu:s0` domain, and from there the kgsl debugfs is readable:

```
$ adb shell 'su -c "cat /sys/kernel/debug/kgsl/events"'
event groups:
--------------
rb_events-1: last=10178
context-6: last=1489029
	6:1490816 age=25 func=kgsl_sync_fence_event_cb [retired=1489029]
	6:1490816 age=9 func=wait_callback [retired=1489029]
```

**That is the stall, in one place:** context 6's retired count is frozen at
**1489029** while the fence waits for timestamp **1490816**. The GPU stopped
retiring, so the fence that the display is waiting for is never released.

**Do not use the KernelSU-Next manager's grant-root flow on this port.** The
live-policy rewrite behind it (`KSU_IOCTL_SET_SEPOLICY`, which duplicates and
rewrites the whole policydb in the kernel) **deadlocks this kernel**: it
froze the phone on the first attempt, and the manager's "allow an app root"
does the same thing. The `adb root` feature is fine; the allowlist path is
not.

## 3. The early hang is a reboot that never finishes

`run278`'s logdump ends here:

```
131506222 init: Received sys.powerctl='reboot,Checkpoint commit failed' from pid: 903 (system_server)
131506439 init: Got shutdown_command 'reboot,Checkpoint commit failed' Calling HandlePowerctlMessage()
...
148718174 init: Remaining userspace processes except init:
148811720 sysrq: Terminate All Tasks
```

and nothing after it. So the early hang is **not** a kernel panic and **not**
a hang in the driver: `system_server` asked for a reboot, Android's init
shut its services down, the kernel was told to terminate all tasks, and the
reboot never reached the reset. The phone was left with a lit screen and no
adb.

Two things are missing from that trace, and both are the port's fault:

* The port's reboot path never ran. The port's own markers
  (`DIAG: kernel_restart_prepare`, `ramoops: DIAG: orderly reset action=`)
  are absent, so `kernel_restart_prepare()` was never reached: the 'e'
  sysrq killed the process that was going to call `reboot()`.
* The checkpoint commit failed, and the reason is visible in the same
  logdump: **460 SELinux denials** for the `system_suspend` domain reading
  the wakeup statistics.

## 4. The two policy defects, and what the 4.19 policy expected

The ROM is Android 17 EvoX. Its policy was written for the 4.19 CAF kernel,
and the port's 6.12 kernel puts two families of node where the policy does
not expect them.

### 4.1 The wakeup statistics: the checkpoint failure

The 6.12 kernel creates per-device wakeup statistics:

```
/sys/devices/platform/soc@0/c200000.remoteproc/wakeup/wakeup4/{name,active_count,
    event_count,expire_count,last_change_ms,max_time_ms,prevent_suspend_time_ms,
    total_time_ms,active_time_ms}
/sys/devices/platform/soc@0/200f000.spmi/spmi-0/0-02/...:qcom,fg/wakeup/wakeup18/...
```

The ROM's policy has the type for them and lets `system_suspend` read it -
but the rule was written for the 4.19 path:

```
(allow system_suspend sysfs_wakeup (file (ioctl read getattr lock map open watch watch_reads)))
```

The 4.19 kernel had those nodes under `/sys/devices/virtual/wakeup`; the
6.12 kernel has them per device, so they land on the **generic `sysfs`
type** and `system_suspend` is denied reading them. The suspend service's
snapshot then fails, the checkpoint commit fails, and the phone asks for a
reboot it cannot finish.

The fix is a *label*, not a policy change: the port's own base policy
already has

```
(genfscon sysfs "/devices/virtual/wakeup" (u object_r sysfs_wakeup ((s0) (s0))))
```

so `sysfs_wakeup` exists; the port's kernel just has to put the new nodes
under that type. Relabelling them by hand, live, with

```
setfattr -n security.selinux -v "u:object_r:sysfs_wakeup:s0" <file>
```

made the `system_suspend` denials stop, and the boot that followed had
**no "Checkpoint commit failed" and no reboot request**.

### 4.2 The kgsl power attributes: the HAL power service

The ROM's HAL power service (`hal_power_default`, `NodeLooperThread`) writes
the kgsl's `max_pwrlevel`, `min_pwrlevel`, `idle_timer`, `force_clk_on` and
`force_rail_on` once a second and is denied every time:

```
avc:  denied  { write } for  comm="NodeLooperThrea" name="idle_timer" dev="sysfs"
  scontext=u:r:hal_power_default:s0 tcontext=u:object_r:sysfs:s0 tclass=file permissive=0
```

The port's base policy has the type the ROM expects for the GPU -

```
(genfscon sysfs "/devices/platform/soc@0/1c00000.gpu/kgsl/kgsl-3d0/snapshot"
  (u object_r sysfs_gpu ((s0) (s0))))
```

- and the port's kgsl's `snapshot` directory does get `sysfs_gpu`, but the
power attributes next to it are on the generic `sysfs` type. Relabelling
them `sysfs_gpu` is what the port's diag init now does.

**This is not the stall.** The GPU kept working through all of it (62 %
busy, the clock at 133 MHz, submissions continuing), and the ROM's policy
does not let `hal_power_default` write `sysfs_gpu:file` either. It is
console noise - one denial per attribute per second - and it is worth fixing
because it is pure noise in the evidence channel, not because it causes the
stall.

### 4.3 Why not patch the policy at runtime

The obvious fix - add the rules to the live policy - is what
KernelSU-Next's `SET_SEPOLICY` supercall does, and it **froze this
kernel**. The port's own `--policy-append` mechanism (a CIL file appended to
the ramdisk's `userdebug_plat_sepolicy.cil`) is the safe route, but the
*effective* policy is the ROM's, loaded from its own precompiled file; the
port would have to patch that before the ROM's init reads it, which needs a
CIL compiler in the ramdisk. The label route needs neither, so that is what
the port does.

## 5. What the port does about it

`scripts/initramfs-diag/init.c` gained `relabel_sysfs_for_rom_policy()`: it
walks `/sys/devices/platform` for the per-device `wakeupN` directories and
labels their files `sysfs_wakeup`, and it labels the kgsl's sysfs files
`sysfs_gpu`. It runs eight times over sixteen seconds, because the devices
that own those nodes probe at their own pace.

Labelling the kgsl's sysfs `sysfs_gpu` has a second effect worth having:
the **adb shell can read the GPU state without root**, so the port's poller
can capture `gpu_busy_percentage`, `clock_mhz`, `dispatch/inflight` and the
rest as the `shell` user.

## 6. run283: a sixteen-second delay in the guard hangs the phone

Moving the relabel to the top of `install_android_guard()` - so that it
would run before the guard chroots into the ROM's root - hung the phone
on the first boot. It came up on a dim screen with no adb and no USB at
all, and needed a forced power-off to be recovered.

The cause is in the boot timeline, which the logdump partition records
for every boot. The good boot (run282) says:

```
 8.90 s  DIAG: Android init exec succeeded
24.44 s  DIAG: bootdevice guard installed read-only f2fs-only fstab and
         vendor contexts before policy load
25.79 s  init: Opening SELinux policy
25.86 s  init: Using userdebug system sepolicy /debug_ramdisk/...
28.80 s  init: Loading SELinux policy
29.64 s  KernelSU: initialize_fake_status ... policyload=1, enforcing=1
```

**The guard has a 1.35 second window.** It has to install the read-only
fstab and the vendor contexts *before* the ROM's init opens the policy,
because `guard_pre_policy()` refuses to run once a policy is loaded: the
check is that the calling process still has the pre-policy "kernel"
context, and a loaded policy turns that into `u:r:kernel:s0`, which the
check explicitly rejects.

The relabel loop in run283 sat in front of the guard for sixteen seconds
(t eight passes of two seconds). That put the guard's install at about
40 s, roughly fourteen seconds *after* the ROM's init opened the policy.
The guard then failed with `EPERM`, exited with "alias not released",
and the ROM's init waited for a boot device that nobody was going to
release. A dim screen, no userspace, no adb, no USB - the symptom
exactly.

**So the guard must not be delayed by any amount.** The relabel has to
run in a process of its own, in parallel, and the guard must not wait for
it.

### 6.1 Why the relabel never worked anyway

The same capture shows why the relabel was a no-op in run282:

```
34.36 s  DIAG: wakeup stats relabelled ret=-1
34.36 s  DIAG: kgsl sysfs relabelled ret=-1
```

`ret=-1` is the walk failing to open its directory at all. By the time
the relabel ran, the guard had chrooted into the ROM's root and joined
the ROM's init's mount namespace, and the ROM's `/sys` is not mounted
yet at that point (Android's init mounts it in its second stage). The
kernel's sysfs - the one with the wakeup statistics and the kgsl's
attributes on it - is only visible in the initramfs's own mount
namespace, before the switch.

That also explains the label check that started this: the kgsl's
`idle_timer` was still `u:object_r:sysfs:s0` after the run282 boot. The
walk never found it.

**⇒ The relabel has to run in a process that stays in the initramds's
mount namespace**, and it has to run before the ROM's init loads its
policy - the manual relabel from an adb root shell worked after the
policy was loaded, so the label itself is not the problem, but the
initramds's context before the policy load is the safe place to be.

**⇒ The shape of the fix**: fork a dedicated relabel child in
`launch_android()`, before the ROM's init is exec'd, so that it runs
concurrently with the whole boot in the initramds's namespace with the
kernel's sysfs mounted, and it must not delay the guard by even a
millisecond. The guard stays exactly where it is.

## 7. What is still not proven

* **Why the GPU stops retiring.** The debugfs shows the retired count
  frozen, and the instrument is on the right path now
  (`DIAG sync_timeline_signal`, `DIAG sync_fence_event`,
  `DIAG event_group`, `DIAG dispatcher_timers`), but the two boots with
  the instrument (run266, run267) both came up clean, so the failing boot
  still has to be caught. In the healthy boots the event path is barely
  used: the fence is usually created after its timestamp has already
  retired, and the direct path releases it; the *event* path is the rare one
  and it is the one that dies.
* **Why the GPU's retired count freezes.** `ft_hang_intr_status=1` says the
  fault detector saw a hang, and the handler costs 19 ms of
  interrupts-disabled time per interrupt in the stalling boot (the system
  tick rate fell from 204/s to 141/s). Which of the two is cause and which
  is effect is not established.
* **Whether the `hal_power_default` denials matter.** They do not stop the
  GPU, but the HAL power service is the thing that would otherwise pin the
  GPU's clock and rail, and the GPU sits at 133 MHz while it is denied.
* The fastrpc uapi mismatch (the stock `adsprpcd` issues ioctls the port's
  driver does not implement, so it restarts every 25 ms) is untouched.
