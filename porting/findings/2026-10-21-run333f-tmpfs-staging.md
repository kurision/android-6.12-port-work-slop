# run333f: remove the failed tmpfs staging approach

> Rolled back: after the user's report that run333f boots but run333g resets,
> both uncommitted init experiments were removed. `init.c` is restored to
> committed HEAD (the run333e retained-FD implementation); the new diagnostic
> policy fragment was removed. Existing images and evidence are preserved.
> Run333g is withdrawn, not a candidate for another boot.

## Hardware evidence

Evidence is in `porting/artifacts/snapshot60/run333f-live-t444a4ib/`:

- `logdump-prefix.log:855`: the new staging marker at 32.653 s reports
  `count=1 delay=60 errno=95` (EOPNOTSUPP).
- `state:14-15`: the directory exists, is still labelled `tmpfs`, and is
  empty. The service properties are absent (`:12-13`); the vendor rc
  contains no delayed services (`:16-43`). No machine module/card bind ran.

The raw logdump was not cleared between these boots: its later suffix
contains old run333e records. Those old 79.208 s EPERM messages are not a
second delayed load in run333f.

The live `/proc/config.gz` and `out/.config` both have TMPFS_XATTR disabled.
Without the shmem security xattr handlers, pre-policy fsetxattr falls back
to SELinux's in-core setter, which requires SBLABEL_MNT; that flag is not
ready before the initial policy (`security/selinux/hooks.c:3493-3506`).
The earlier analysis stopped at inode_setxattr's permission check and
missed this storage/setsecurity path.

Enabling TMPFS_XATTR alone is **not a complete fix**. Android's policy uses
`fsuse trans tmpfs`: initial inode labeling takes the transition branch,
not the xattr branch (`security/selinux/hooks.c:1465-1523`). A post-policy
restorecon alternative would need additional relabel permissions too.
The proposed kernel rebuild was therefore cancelled before changing any
configuration or starting a build; the user approved the narrow loader
policy alternative instead.

Cross-checks:

- [Upstream tmpfs Kconfig](https://github.com/torvalds/linux/blob/master/fs/Kconfig)
- [AOSP kernel-domain restrictions](https://android.googlesource.com/platform/system/sepolicy/+/refs/heads/main/private/kernel.te)
- [AOSP module-loader policy](https://android.googlesource.com/platform/system/sepolicy/+/refs/heads/main/vendor/vendor_modprobe.te)
- [AOSP module-origin restrictions](https://android.googlesource.com/platform/system/sepolicy/+/refs/heads/main/private/domain.te)

## Replacement: retained FDs and an explicit domain transition

Remove the staging directory, generated services, and associated refactor.
Keep the run333e loader's existing whole-list read and pre-opened module
FDs. Only the detached delayed child opens its own `/proc/self/attr/current`
read/write before policy load. After the requested delay, it checks that
policy has initialized, then writes `u:r:vendor_modprobe:s0` before loading
any module. An uninitialized policy is retried for at most 60 s. Any other
failure logs an error and exits without attempting a delayed module load.

`porting/policy/diag-late-modules.cil` is a diagnostic-only delta:

- Permit the source kernel domain to set its current context and transition
  to vendor_modprobe. Proc task attributes use the task SID, not proc_security.
- Permit vendor_modprobe to use the kernel-opened FDs and read/load the
  retained rootfs module files. This does not grant init_module from memory,
  arbitrary module origins, or sys_module to the kernel domain.
- Permit writes through the retained kmsg FD. Its devtmpfs inode is labelled
  `device`, unlike Android's separately created `kmsg_device` inode. No new
  device open/create permission is granted.

SELinux rules authorize a domain pair, not an individual PID. Other
kernel-domain processes technically receive the same transition permission;
only the delayed module-loader code opts into it. Existing vendor_modprobe
permissions still apply. Enforcement stays on.

Relevant target paths: setcurrent/dyntransition checks at
`security/selinux/hooks.c:6448-6450,6523-6557`; proc inode task labels at
`:4296-4305`; retained-FD/module-origin checks at `:4135-4149`.

## Verification and candidate

- `ANDROID_MODULE_TEST` checks the context payload, pre-policy retry,
  unexpected-context rejection and FD error handling. Existing guard tests
  also pass. Logs: `porting/artifacts/snapshot60/run333g-preflight/`.
- The phone's own secilc compiled both the **actual run333f ramdisk's CIL**
  and the candidate CIL against the phone's mapping/vendor/system_ext/product/
  ODM policies, using Android's boot flags (`-m -M true -G -N -c 30`).
  Neither compiled policy was loaded. Files and log:
  `run333f-live-t444a4ib/policy-check/`.
- Optional compilation with neverallow checking enabled timed out on the
  baseline after 60 s; no secilc process remained afterward. This check did
  not reach the candidate and is not claimed as passed. The normal boot-time
  compile above passed for both.
- No kernel build/configuration change or DT2W integration was made. Kernel,
  DTB, modules, load order, command line and existing ramdisk records remain
  unchanged; only `/init` and the appended diagnostic policy differ.

Candidate: `porting/artifacts/snapshot60/boot-run333g-late-domain.img`.
Packaging report: `package-run333g-late-domain.json` in the same directory.
The requested 60 s delay again starts at the early-loader fork, like run333e.

**Unverified on hardware.** After a user-authorized boot, look for
`DIAG: late module domain=vendor_modprobe`, then the machine module's result,
fresh SELinux denials and `/proc/asound/cards`. Preserve logdump before any
subsequent recorder starts. No new boot was performed while preparing it.

## Subsequent run333g report: reset, cause not recovered

The user reports that the candidate failed to boot and reset, followed by
another reset during fallback. ADB later returned on kernel `#35`,
`51cccf6d`, not the candidate's `#37`, `166d3b532`.

Evidence: `porting/artifacts/snapshot60/run333g-reset-ynaswhda/`.
`capture.json` verifies retrieval of the full 67108864-byte partition;
`state:1-3` identifies the fallback boot at 39.66 s. The retrieved primary
log starts with that fallback kernel, contains no new domain-transition
marker, and does not establish what happened in run333g. Recovered snapshot
slots are periodic samples, not panic/oops records (`raw-ramoops.json`).
`pstore.tar` is empty. The separately retrieved device file
`/data/local/tmp/logdump.bin` has no readable prefix or valid snapshot slots
(`saved-ramoops.json`); it is not usable evidence for this failure.

No cause is established. Do not attribute the fallback's early machine-module
load or its regulator warnings to run333g. Locate any grabber-preserved
pre-fallback logdump before planning another scarce boot cycle.

## Correction after the live F boot

The phone later came up on the candidate kernel `166d3b532` with the **F**
image (`/dev/ack-late-modules` present and empty, `errno=95` staging marker at
20.876 s). A full logdump from that boot is in
`porting/artifacts/snapshot60/run333g-live-current/` and shows init compiling
the **ramdisk** `userdebug_plat_sepolicy.cil`:

```
init: Using userdebug system sepolicy /debug_ramdisk/userdebug_plat_sepolicy.cil
init: Compiling SELinux policy
ramoops: DIAG process_exit pid=227 comm=secilc exit_code=0x0
```

So run333g's appended CIL was compiled and loaded; it did not silently fall
back to the precompiled vendor policy. That removes "the delta never took
effect" as an explanation.

It does **not** establish that the delta or the init change caused the reset.
`machine_dlkm.ko` was already known to reset this phone when it loads early
(`09e3154bf`, run332b/run333b), and run333g loads it at ~79 s, the same point
run333e hit EPERM. See
`2026-10-21-late-module-loading-research.md` for the full analysis, the
remaining options and the evidence-capture plan. The earlier conclusion that
the init experiment "broke the boot" is withdrawn as unproven; the source
revert stands, and run333g should not be repeated unchanged.
