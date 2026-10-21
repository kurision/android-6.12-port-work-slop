# Late module loading: what actually blocks it, and the AOSP-shaped fix

Research only. No source change, no build, no flash, no reboot was performed
for this document. Everything below is either primary-source code, AOSP
upstream, or a log pulled from the device.

Evidence added while writing this:
`porting/artifacts/snapshot60/run333g-live-current/` — a full 64 MiB logdump,
`probe.txt` (dmesg, `/proc/modules`, `/proc/asound/cards`, SELinux/mount
state) captured from the **F image** while it had been up 6982 s.

## 1. The live F boot proves the policy mechanism works

`run333g-live-current/logdump-prefix.log` (offset 164310, `caller=T1`):

```
init: Opening SELinux policy
init: Using userdebug system sepolicy /debug_ramdisk/userdebug_plat_sepolicy.cil
init: Compiling SELinux policy
init: Using /system/etc/selinux/plat_sepolicy_genfs_202604.cil for genfs labels
ramoops: DIAG process_exit pid=227 comm=secilc exit_code=0x0 group_exit=1
```

So on this device:

- `/proc/cmdline` has `androidboot.verifiedbootstate=orange`; the bootloader is
  unlocked, `AvbHandle::IsDeviceUnlocked()` is true, and init takes
  `GetUserdebugPlatformPolicyFile()` → it compiles the **ramdisk**
  `userdebug_plat_sepolicy.cil` itself.
- The precompiled `/vendor/etc/selinux/precompiled_sepolicy` path is therefore
  **not** used (init only falls back to it when no debug policy is selected —
  `system/core/init/selinux.cpp`, `OpenSplitPolicy()`).
- Policy appends to that ramdisk CIL do take effect at boot. The earlier
  worry "the append may be ignored" is disproved for this device.

Consequence for run333g: its CIL delta (`kernel self setcurrent/read/write`,
`kernel → vendor_modprobe dyntransition`, `vendor_modprobe` FD/rootfs/module
rules) was compiled by the phone's own `secilc` (verified offline against the
exact packaged bytes) and loaded. The delta was **active** during that boot.

## 2. run333g is not established as an init regression

The machine module has already reset this phone once, silently:

```
$ git log -1 --format=%b 09e3154bf
An "@late <seconds>" line in /ack-modules/load-order loads the modules
after it from a detached child after that long, once the recorder is
writing the kernel log to logdump, so a module that resets the phone
leaves its log behind (run332b and run333b reset before anything was
recorded).
```

`boot-run333b-loader-child.img` carries `machine_dlkm.ko` **in the early
list** (verified from the image's own `ack-modules/load-order`). That boot
reset with nothing recorded. So "machine_dlkm loads ⇒ phone resets" is an
observed property of this port, independent of any init/policy experiment.

The delayed child sleeps 60 s from `load_ack_modules()`, so the load fires at
about the same point run333e reported its EPERM (`79.208 s`). A reset at
~79 s while Android is already up is exactly what a crashing machine-driver
probe looks like.

Discriminating evidence is gone:

- The logdump is written sequentially from offset 0 and only reaches ~2.1 MB
  per boot (the F boot stopped at 920 s with `DIAG: EOF Android kmsg dump
  complete`). A boot loop overwrites the first ~79 s of the previous boot, so
  a g crash at 79 s is overwritten by the next boot's own first 79 s.
- The ACKRESET page in the current logdump is from the user's later
  `reboot bootloader` (`action=1 pid=1 comm=init command=bootloader`,
  `timestamp_ns=1511465759109`), not from the g boot.
- The pstore pulled on the fallback boot was empty, but that boot ran kernel
  `51cccf6d`, whose appended DTB is not the current one, so its ramoops view
  is not trustworthy. On the current F boot (kernel `166d3b532`, correct DTB)
  pstore is healthy — `86800000.ramoops` bound, `mem_size=1048576`,
  `record_size=4096`, `max_reason=4` — and `/sys/fs/pstore` is empty. That is
  *weak* evidence against a g panic, not proof: pstore records may have been
  overwritten by later panic/shutdown dumps, and Android mounts pstore at
  `post-fs` (`init.rc:462-471`).

Verdict: **unknown**, with "machine probe crashed at ~79 s" now at least as
likely as "init/policy broke the boot". Do not repeat either claim as fact.

## 3. Why each previous mechanism failed (each has a distinct cause)

| run | mechanism | failure | cause |
| --- | --- | --- | --- |
| 333e | `@late` child in `u:r:kernel:s0` | `EPERM` at 79.208 s | kernel domain has no `sys_module`; only `vendor_modprobe` does |
| 333f | native init services, staged `/dev/ack-late-modules` labelled `vendor_file` | `errno=95` (EOPNOTSUPP) | pre-policy `fsetxattr` needs `SBLABEL_MNT`, and `CONFIG_TMPFS_XATTR=n` removes tmpfs's own xattr handlers (`security/selinux/hooks.c:3493-3506`) |
| 333g | child dyntransitions to `vendor_modprobe`, loads retained rootfs FD | reset | **not established** (see §2) |

Two related dead ends confirmed this time, so they are not tried again:

- `context=`/`fscontext=` mount options are rejected before the initial
  policy: `selinux_set_mnt_opts()` returns `-EINVAL` whenever
  `!selinux_initialized() && opts` (`security/selinux/hooks.c:662-676`).
  A context-labelled tmpfs therefore cannot be created in the pre-policy
  window, which is the only window where the ramdisk modules are still
  addressable.
- Enabling `CONFIG_TMPFS_XATTR` would not have helped on its own: Android
  declares `(fsuse trans tmpfs ...)`, so initial inode labelling takes the
  transition branch, not the xattr branch (`hooks.c:1465-1523`).

Also disproved: the earlier idea that the ramdisk files are "deleted".
`SwitchRoot()` (`system/core/init/switch_root.cpp`) only moves every mount
under the new root and `chroot()`s; it deletes nothing. The modules become
unreachable by path, not freed — which is why an FD works and why a bind mount
under `/dev` survives (`/dev/ack-late-modules` still exists on the F boot).

## 4. What AOSP actually provides

`system/sepolicy/vendor/vendor_modprobe.te` (upstream `main`) is the whole
story:

```
allow vendor_modprobe self:global_capability_class_set sys_module;
allow vendor_modprobe { vendor_file }:system module_load;
r_dir_file(vendor_modprobe, { vendor_file })
allow vendor_modprobe proc_modules:file r_file_perms;
allow vendor_modprobe kmsg_device:chr_file w_file_perms;
```

- `vendor_modprobe` is the only general module loader that runs after policy.
  `ueventd`/`modprobe`/`kcmdlinemodprobe` also carry `sys_module`, none of
  which a diagnostic ramdisk process can arrange to become.
- **The module origin allow is `vendor_file` only.** The compile-time
  neverallow permits `system_file_type vendor_file_type rootfs
  system_dlkm_file_type` (compiled form:
  `(neverallow base_typeattr_248 base_typeattr_486 (system (module_load)))`,
  where `base_typeattr_486` is `(not (system_file_type system_dlkm_file_type
  vendor_file_type rootfs ...))`), but `rootfs` has no runtime allow, so
  loading from the ramdisk is denied even in the right domain.
- On this ROM, `vendor_modprobe` has **no** rules for `rootfs`, `tmpfs` or
  `device` at all (checked against `userdebug-run33.cil`), so a module path
  under `/dev` needs four new allows, not one.

The ROM itself shows the supported pattern
(`/vendor/etc/init/netmgrd.rc:16-77`):

```
exec u:r:vendor_modprobe:s0 -- /vendor/bin/modprobe -a -d /vendor/lib/modules rmnet_ctl
```

`exec <seclabel> -- <cmd>` is an init action command, i.e. the module is
loaded by init-run modprobe in exactly the domain the policy expects, from
`/vendor/lib/modules`, with no dyntransition and no threaded child. This is
what a production-shaped fix should look like.

## 5. Options, ranked, with exact cost

### A. `vendor_modprobe` + a real `vendor_file` module (no new policy)

Requires `machine_dlkm.ko` to exist at a `vendor_file` path. `/vendor` is a
directory inside the system partition (`/system/vendor`, ext4 on the system
block device), mounted `ro`; the boot log says `AVB is not enabled, skip
verity setup for '/system'`, so a one-time `remount,rw` + push is likely
possible. Then:

- append to any vendor rc via the existing pre-policy overlay
  (`guard_bind_config()`, already used for `/vendor/etc/init/qcrild.rc`):

  ```
  on property:sys.boot_completed=1
      exec u:r:vendor_modprobe:s0 -- /vendor/bin/modprobe -a -d /vendor/lib/modules machine_dlkm
  ```

- policy delta: **none**; `init.c` module-loader code: **none**.
- cost: one write to the user's system partition (needs explicit approval),
  one boot.

### B. `vendor_modprobe` + bind-mounted rootfs modules (4 allows)

Pre-policy: `mkdir /dev/ack-late-modules` and `mount --bind /ack-modules
/dev/ack-late-modules` (the pattern that already survives switch_root), plus
the rc action above pointing at `/dev/ack-late-modules`. Modules keep the
`rootfs` label. Delta:

```
(allow vendor_modprobe tmpfs (dir (search)))
(allow vendor_modprobe rootfs (dir (search read open getattr)))
(allow vendor_modprobe rootfs (file (read getattr open map)))
(allow vendor_modprobe rootfs (system (module_load)))   ; neverallow-legal
```

No kernel-domain grant, no dyntransition, no FD passing, no tmpfs staging.
cost: init.c staging + one boot.

### C. Kernel-domain grant + retained FD (2 allows, smallest delta)

Keep run333e's loader unchanged and only make the load legal:

```
(allow kernel self (system (module_load)))
(allow kernel self (capability (sys_module)))
```

No rule forbids this (`base_typeattr_284` for the sys_module neverallow
expands to `(and (appdomain ...))`, which `kernel` is not), so it compiles
with neverallow checking on. It does hand the whole `kernel` domain the
ability to load modules — acceptable in a throwaway diagnostic image, not
production. cost: policy only, one boot.

### D. Early load (no delay) — ruled out

`run333b` did exactly this and reset before anything was recorded. Not
repeatable without a way to preserve the panic.

## 6. Evidence preservation is now the bottleneck, not the loader

For every option above, if the machine probe crashes, the useful record is:

- **pstore**: healthy on this port (`86800000.ramoops`, `max_reason=4`
  includes panic/oops). A kernel panic should leave
  `/sys/fs/pstore/dmesg-ramoops-0` readable on the *next* boot. This has
  never been demonstrated on this port — verify it before spending a boot.
- **logdump**: the recorder streams until `sys.boot_completed`, so the log up
  to the reset is on the partition, but a boot loop overwrites its first
  ~80 s on the next boot.

Minimal mitigation, independent of which loader option is chosen: make the
late load **single-shot** using the logdump block device the diag init already
holds open. Before `finit_module`, `pwrite` a marker at a fixed logdump
offset and `fsync`; at early boot, read that offset pre-policy and skip the
late load if it is set. One crash then costs exactly one boot instead of a
loop, and the crash's pstore record survives into the next (clean) boot.

## 7. Recommended next step

Do not repeat run333g unchanged, and do not re-flash on the assumption that
"the init change broke the boot" — that is unverified.

Cheapest informative boot: **option A or B**, i.e. load from `vendor_modprobe`
with the ROM's own `exec` action, plus the single-shot latch from §6. It
removes the dyntransition (the only genuinely new SELinux mechanism g used)
and loads from an allowed origin, so a reset can only mean the machine driver.

Before that boot, verify pstore panic capture with something trivial (e.g.
`echo c > /proc/sysrq-trigger` on a disposable boot) so the next crash is not
lost.

## Open questions

- Did the run333g reset happen immediately (black screen, before the boot
  animation) or after roughly a minute of normal boot? Immediate points at
  init/policy or an early crash; ~60-80 s points at the machine module.
- May `/system` (`/system/vendor`) be remounted read-write once, so option A
  needs no policy at all? That is the only option with a zero-sized policy
  delta.
