# run333e: delayed module load denied before card bind

> Superseded: run333f booted, but tmpfs staging failed with EOPNOTSUPP.
> The service design below is a failed experiment, not the current fix.
> See `2026-10-21-run333f-tmpfs-staging.md` for the retained-FD domain
> transition used by the new, hardware-unverified run333g candidate.

## Evidence

Local evidence: `porting/artifacts/snapshot60/run333e-live/`.

- `state:1-13`: 6.12.93, uptime 197.90 s, boot completed, seven early
  audio modules present, no soundcards; `machine_dlkm` is absent.
- `logdump-prefix.log:5180-5184`: at 79.208 s the delayed loader reports
  `machine_dlkm.ko failed errno=1`, then an enforcing SELinux denial of
  `sys_module` for `u:r:kernel:s0`. The loader exits normally.
- `logdump-prefix.log:554-560`: earlier platform DAI registration also
  reports unnamed DAIs. This is a separate follow-up, not evidence that
  the machine driver's card bind ran.

This boot did not test card bind. The earlier ENOENT fix retained the input,
but did not give the sleeping diagnostic child an authorized SELinux domain.
Commit `09e3154bf` describes that earlier failure and its compile-only fix.

## Init-only change

Read the list once before forking the early loader, retaining the delayed
module FDs for the existing pre-policy Android guard. In PID 1's mount
namespace, the guard copies those inputs and minimal modprobe metadata into
`/dev/ack-late-modules`, labelled `vendor_file`. This directory survives
ramdisk deletion and is outside `/dev/block`, which Android recursively
restorecons during SELinux setup.

Append two disabled, oneshot services to the existing vendor rc overlay:

1. An asynchronous shell-domain sleep, started at Android `early-init`.
2. On its stopped property, native `/vendor/bin/modprobe` in
   `u:r:vendor_modprobe:s0`, with `SYS_MODULE`, reading the retained list.

The delay is now measured from Android `early-init`, not the original early
module-loader fork; do not assume the old exact 79.2 s timestamp. Neither
service blocks Android's action queue. SELinux remains enforcing, with no
policy additions. Early module loads keep their isolated child and 30 s
parent wait. Staging failure logs an error and leaves the original rc intact.

The device's policy grants this domain `sys_module`, `vendor_file` reads and
`module_load`, with an init transition through `vendor_toolbox_exec`.
See `device-module-policy.log` and the saved upstream references:

- [AOSP vendor_modprobe policy](https://android.googlesource.com/platform/system/sepolicy/+/refs/heads/main/vendor/vendor_modprobe.te)
- [AOSP init service semantics](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/README.md)
- [AOSP modprobe option parsing](https://android.googlesource.com/platform/system/core/+/refs/heads/main/toolbox/modprobe.cpp)
- [AOSP SELinux setup / restorecon](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/selinux.cpp)

The target kernel permits owner-set SELinux xattrs before policy load in
`security/selinux/hooks.c:3240-3241`; the labels are revalidated after policy
initialization (`:3344-3349`). Runtime staging remains unverified.

## Checks and candidate

- New `ANDROID_MODULE_TEST`: parser validation, generated asynchronous rc,
  and failure rollback / retained-FD cleanup pass.
- Existing `ANDROID_GUARD_TEST`: both checks pass.
- `ANDROID_RAMOOPS_TEST` fails at the procdir-log assertion, identically in
  the unchanged HEAD baseline. Logs: `loader-checks.log`, `baseline-checks.log`.
- Static arm64 diagnostic init compiles; warnings are in unchanged code.
  The same compiler flags reproduce run333e's baseline init byte-for-byte
  when the source basename is kept as `init.c` (SHA256 `8db46e02...`).
- Native device modprobe dependency-only test recognizes the minimal
  `modules.dep`: `modprobe-dependency-dryrun.log`. No module was loaded.
  An earlier `-D --all=...` check was rejected as incompatible modes;
  `modprobe-dryrun.log` preserves that failed check, not a loading attempt.
- New image: `porting/artifacts/snapshot60/boot-run333f-late-service.img`.
  SHA256: `eee5b53706b2a32392c927bcc16f4eb03d2194fddd16d8573bcfcb80910a3b2c`.
  Packaged directly from the actual run333e image, replacing only `/init`;
  the packager verifies other records. Kernel, modules, policy and command
  line are unchanged. No kernel build or new boot was performed.

Hardware verification is pending: check the staging marker, both service
states, module presence, SELinux denials, kernel card-bind messages and
`/proc/asound/cards`. Preserve logdump before any subsequent recorder starts.
