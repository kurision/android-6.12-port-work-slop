# Snapshot27: checkpoint blocker resolved, 355s reset unobserved

> **Historical record - 2026-10-07.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

Date: 2026-10-07. Image: `boot-ack-snapshot27-init-relabel-screen.img`
(sha256 `3ef09286…f2e1dfb`). No kernel build, no flash; all boots temporary.

## What changed
- `userdebug_plat_sepolicy.cil`: `(allow init tmpfs (file (relabelfrom)))`,
  `(allow init vendor_configs_file (file (relabelto)))`,
  `(allow init file_contexts_file (file (relabelto)))`.
- `vendor_file_contexts.ack`: staging rule for `ack-vendor-file-contexts` is
  now `file_contexts_file`; fstab staging stays `vendor_configs_file`.
- Rationale: post-policy init restorecon labels the staging inodes instead of
  pre-policy xattrs (snapshot26's approach failed: booted kernel has
  `CONFIG_TMPFS_XATTR` disabled; see `snapshot26-analysis.log`).

## Verified (two boots, USB + on-device logdump partition)
- Guard installs; `mount_all /vendor/etc/fstab.qcom --early` succeeds
  (userdata/persist/dsp/modem via `bootdevice/by-name`, zero skips).
- `vdc checkpoint markBootAttempt` exits 0. Snapshot25's blocker is gone.
- No fstab read denials (vold/hal_bootctl), no `Could not set context`.
- Logs: `snapshot27-run2-usb.log` (1462 recs, seq 0–1461, EOF) and
  `snapshot27-run2-durable.log` (partition mmcblk0p48 fresh region,
  byte-identical streams). Stale bytes past the first EOF are older runs.

## Open: reset at exactly 355s
Phone resets ~355s into boot. Both loggers stop ~300s after start
(`dump_log(kin, out, 300, 0)` + `DUMP_SECONDS 300`), so the reset was never
captured (USB ends 321.5s, durable 332.9s). pstore/last_kmsg empty under
stock; `panic=10` fits but is unproven. qseecomd starts ~319s; its fate,
keymaster/boot-qti/zygote are all unobserved.

## Next step (approved, not yet built)
1. `scripts/initramfs-diag/init.c`: USB window `300`→`900`,
   `DUMP_SECONDS` `300`→`900`. Ramdisk-only snapshot28, temp-boot,
   deadline-free capture. Expected: EOF log through 355s with the reset cause.
2. SD backup sink: user-donated card (mmcblk1p1, vfat; kernel has
   CONFIG_VFAT_FS=y and CONFIG_EXFAT_FS=y, verified in
   snapshot26-kernel.config). Mount it in diag init and append the kmsg
   stream to a file, so the card stays readable on any laptop. Tee in
   `dump_log`; if the mount/open fails, continue with partition+USB only.
3. Prep already done: logdump partition zeroed (`dd if=/dev/zero`,
   verified) so the next pull holds exactly one run.
