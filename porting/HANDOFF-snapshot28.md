# Handoff: snapshot28 (capture the 355s reset)

## State (2026-10-07, phone on stock, rooted adb, nothing flashed)
- Commits in: `7bea83f` policy fix, `c3179f5` evidence, `c0c2406` findings doc.
- Boot image: `porting/artifacts/boot-ack-snapshot27-init-relabel-screen.img`
  (35,964,928 bytes, sha256 `3ef09286…f2e1dfb`). Reuse its kernel + policy.
- Verdict so far (`porting/findings/09-*.md`, `snapshot27-analysis.log`):
  guard installs, `mount_all --early` succeeds, `checkpoint markBootAttempt`
  exits 0. Phone resets at exactly ~355s; loggers stop ~300s after start,
  so USB ends 321.5s and durable ends 332.9s. Cause unknown (`panic=10`
  fits, unproven). qseecomd starts ~319s; its fate + keymaster/boot-qti +
  zygote all unobserved.
- Prepped: logdump partition (mmcblk0p48) zeroed + verified; SD card
  (mmcblk1p1, vfat, user-donated, kernel has VFAT+EXFAT=y) ready as log disk.

## Next step (user-approved, NOT built)
`scripts/initramfs-diag/init.c`:
1. `dump_log(kin, out, 300, 0)` (capture_usb, ~line 791) → `900`.
2. `dump_log(in, out, 300, 1)` (durable child, ~line 903) → `900`.
   (`DUMP_SECONDS` macro is only used by the non-capture path; leave it.)
3. SD file sink: poll `/dev/mmcblk1p1` (devtmpfs name, NOT /dev/block),
   `mkdir /sdlog`, mount vfat, open fixed-name file O_WRONLY|O_CREAT|O_TRUNC.
   Open it in the durable child only (single writer); promote to primary if
   the logdump open fails; pass as mirror fd to `dump_log` and disable on
   write error. `dump_log` needs the extra param at all 3 call sites.
- Checks: `gcc -std=gnu11 -Os -Wall -Wextra -Werror` all 4 variants
  (default/capture/heartbeat/guard-test) + guard selftest PASS + NDK r29
  android24 static ARM64 init.
- Repack ramdisk-only (kernel + policy + cmdline byte-identical; cmdline
  keeps `console=tty0 loglevel=8`; drop the duplicate `init` cpio entry like
  snapshot27 did). Temp `fastboot boot` only; deadline-free host capture
  (`timeout: 0`) matching USB identity 18d1:9008 serial tissot-diag @115200
  until `DIAG: EOF Android USB kmsg dump complete`; pull mmcblk0p48 as backup.

## Gotchas
- `AGENTS.md`: explain change + wait for confirmation before editing; no
  kernel build unless asked.
- Host killing the USB reader makes the gadget side fail with EAGAIN and
  detach USB (that's what killed run1's capture, not a device crash).
- Partition logger has no O_TRUNC: analyze only up to the FIRST EOF.
- A `permissive=1` AVC alone never identifies the failing logger syscall.
- Open todos: Snapshot28 phase (4 items) + TailCapture verify item.
