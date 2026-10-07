# Handoff: snapshot28 (capture the 355s reset)

## State (2026-10-07, phone on installed ROM, snapshot28 backups recovered, nothing flashed)
- Commits in: `7bea83f` policy fix, `c3179f5` evidence, `c0c2406` findings doc.
- Base boot image (parent workspace, not this checkout):
  `../porting/artifacts/boot-ack-snapshot27-init-relabel-screen.img`
  (35,964,928 bytes, SHA256
  `3ef09286cb11d88eab0560fd35dba4e833733ecdad15f027273621990f2e1dfb`).
- Verdict so far (`porting/findings/09-*.md`, `snapshot27-analysis.log`):
  guard installs, `mount_all --early` succeeds, `checkpoint markBootAttempt`
  exits 0. Phone resets at exactly ~355s; loggers stop ~300s after start,
  so USB ends 321.5s and durable ends 332.9s. Cause unknown (`panic=10`
  fits, unproven). qseecomd starts ~319s; its fate + keymaster/boot-qti +
  zygote all unobserved.
- Prepped: logdump partition (mmcblk0p48) zeroed + verified; SD card
  (vfat, user-donated, kernel has VFAT+EXFAT=y) ready as log disk. Block
  numbering swaps: stock SD is mmcblk1, snapshot27 ACK SD is mmcblk0.

## Snapshot28 built and temporarily booted
- Image (parent workspace):
  `../porting/artifacts/boot-ack-snapshot28-tail-sd-screen.img`
  (35,964,928 bytes, SHA256
  `90c2a9a046e3c7436697b63a3d7c3afbb5eb3c262875ecd245bccff712b6fe39`).
- `scripts/initramfs-diag/init.c`: both Android capture calls now use
  900 seconds; non-capture `DUMP_SECONDS` is unchanged. All three
  `dump_log` call sites supply the new optional mirror pointer.
- Durable child discovers the card via `/sys/class/block/mmcblk*/device/type`
  equal to `SD`, polls its first `/dev/mmcblkNp1` partition, mounts vfat
  privately at `/sdlog`,
  opens `snapshot28-kmsg.log` with O_WRONLY|O_CREAT|O_TRUNC, and fsyncs
  each mirrored chunk. Failed mirror writes/fsyncs close and disable the
  mirror without terminating the primary. Missing logdump promotes SD to
  the durable primary. Mount/open failure leaves partition+USB available.
- SD open happens after the guard/USB forks (single writer), but before
  the Android handoff, so policy cannot deny the mount/open. Missing SD
  can add up to 60 seconds before the handoff; boot timing is not assumed
  identical. No card format or partition changes.
- Checks exercised: NDK r29 Clang, android24 static ARM64,
  `-std=gnu11 -Os -Wall -Wextra -Werror`, all four variants
  (default/capture/heartbeat/guard-test). Guard selftest ran on stock
  phone `2819f2320604`: PASS. Throwaway on-device logger smoke: exact
  mirrored records, mirror write-error isolation, durable primary and
  primary error propagation PASS. The mirror case failed before the change.
- Safety correction before boot: hard-coded mmcblk1p1 was unsafe because
  snapshot27 logs identify mmcblk1 as eMMC, mmcblk0 as SD. Swapped-numbering
  smoke failed before and passed after sysfs-based selection. Mount attempts
  were intercepted in that smoke; no real partition was mounted or written.
- Linux GCC check from the original plan remains unrun: this host only
  provides Apple Clang as `gcc`. SD capture survived reboot and matches the
  recovered durable partition stream byte-for-byte.
- Repack verified by parsing the produced image: kernel, cmdline, every
  non-init cpio entry and its metadata byte-identical to snapshot27.
  Exactly one `init`; static ARM64 ELF with no PT_INTERP. Header changes
  limited to ramdisk size and regenerated boot-image SHA1.

## Current device run
- `fastboot -s 2819f2320604 boot` accepted corrected snapshot28:
  Sending OKAY, Booting OKAY. No flash or kernel build.
  Stock logdump PARTNAME verified and its first 64 bytes all zero before boot.
- Deadline-free host reader was waiting before boot; matched 18d1:9008,
  serial tissot-diag, `/dev/cu.usbmodemtissot_diag1` @115200.
- Capture: `porting/artifacts/snapshot28-usb.log`, 156,996 bytes, SHA256
  `48e7beabc8f0d1aeb5b47dae996cc68cc64c9faa5f5313a7b267228c37c9966c`;
  1,439 records, sequence 0–1438 with no gaps, final timestamp 422.288489s.
  `snapshot28-usb-capture.status`: host elapsed 486.356s from reader start;
  that is NOT device uptime. Reader ended on device-not-configured error,
  not a host deadline. No EOF, panic/oops/BUG/lockup/restart message captured.
- SD capture ready at 23.262598s; guard installed at 23.889276s; no SD mirror
  failure message in USB. This run eMMC is mmcblk0, SD is mmcblk1: numbering
  changed again, confirming sysfs selection is necessary.
- `mount_all --early` succeeds at 359.863563s. `markBootAttempt` exits 0 at
  362.413689s. QSEE listener registration has eight failures at 381–399s:
  SCM error -5, ioctl reported -12. The listeners property wait then completes;
  that does NOT prove the SCM registration succeeded.
- boot-qti and keymaster start around 415.8s; boot-qti reports its AIDL
  service running. No keymaster exit captured. `prepareCheckpoint` exits 0
  at 422.036869s. Final action launches `vdc --wait cryptfs enablefilecrypto`
  (PID 364); command dispatch succeeds, but its process completion is NOT
  captured. No zygote service start captured.
- Verdict: captured beyond the former 355s window, but cause of disconnect
  remains unknown. Timing changed; do not claim a fixed 355s reset or blame
  cryptfs from a truncated tail. Panic remains unproven.
- Backups recovered after the phone returned to installed 4.19.325:
  `snapshot28-logdump.bin` is exactly 67,108,864 bytes, SHA256
  `96e73a4c56ddadf46d74507774346e02992d391e5238ade0bd5eaa27aa0d3ed0`.
  Pulled via `by-name/logdump`, resolved/verified as mmcblk0p48 on stock.
  Remote dd status was separated into `snapshot28-logdump-pull.status`.
- `snapshot28-durable.log`: 157,329-byte text prefix; all remaining partition
  bytes are zero. `snapshot28-sd.log` recovered by a private read-only vfat
  mount is byte-identical. Both SHA256:
  `3c59f1f2705f3891f7c6a3e9215700220d453b2ade16005f7106ad32e7cb88f2`.
  Stock vold had not mounted the card; recovery helper unmounted/removed its
  temporary directory. No SD filesystem repair or writes.
- Both backups contain records 0–1440, extending USB by exactly two:
  1439 at 422.660621s: vdc binder service-name=vold message;
  1440 at 422.699903s: `vdc: Waited 0ms for vold`.
  Still no cryptfs process exit, logger EOF or panic/restart message.
  Thus USB-only loss does not explain the missing later kmsg records;
  the reason logging/device progress stopped is still unknown.
- `/sys/fs/pstore` empty on stock; `/proc/last_kmsg` absent.
- SD and Android vold must not write the same vfat filesystem concurrently;
  the private mount namespace alone does not provide filesystem isolation.

## Gotchas
- `AGENTS.md`: explain change + wait for confirmation before editing; no
  kernel build unless asked.
- Host killing the USB reader makes the gadget side fail with EAGAIN and
  detach USB (that's what killed run1's capture, not a device crash).
- Partition logger has no O_TRUNC: analyze only up to the FIRST EOF.
- A `permissive=1` AVC alone never identifies the failing logger syscall.
- Open work: identify why all three streams end at ~422.7s without a panic/EOF.

## Approved kernel/DT fixes for the next VM build
- `include/soc/qcom/scm.h`: restore the donor meaning of generic secure
  return -1 for legacy normal/atomic callers: modern -EIO becomes
  -EOPNOTSUPP. Native `drivers/firmware/qcom/` errno mapping is unchanged.
  This lets qseecom's existing SMCInvoke listener fallback attempt the
  legacy command; it does not establish that the next secure call succeeds.
- `drivers/misc/qseecom.c`: preserve DMA-buffer mapping and SCM failure
  errno through shared-buffer setup and listener registration. Keep
  failed-registration cleanup and pending-state rollback; actual allocation
  failures still return -ENOMEM and failed secure responses return -EPERM.
- `msm8953-xiaomi-tissot.dts`: connect touchscreen `iovcc-supply` to
  `pm8953_l6` (1.8 V), matching the donor's `vcc_i2c-supply`. Stock reports
  FocalTech IC 0x5422; no speculative compatible/protocol change was made.
- Verification: throwaway C smoke failed before each errno fix and passed
  afterward. The actual shim and extracted listener functions were compiled
  with kernel/SCM dependency stubs, then exercised on host and as static
  ARM64 NDK r29 binaries on stock phone 2819f2320604. Covered generic
  error translation, unchanged other errors/success, normal/retry/atomic
  wrappers, listener errno, mapped-buffer cleanup, pending rollback and
  genuine allocation failure. This is not a live TrustZone registration test.
- Board DTS preprocessing and standalone dtc compilation passed; compiled
  `iovcc-supply` resolves to the L6 regulator with min/max 1800000 uV.
  dtc emitted three unique-unit-address warnings for existing I2C/SPI
  alternate nodes in msm8953.dtsi (78b7000, 7af5000, 7af6000).
- Full Linux kernel/object build and next-kernel boot are NOT performed on
  this Mac. Pull on the VM and use the existing build configuration to
  rebuild the kernel AND board DTB. Repack with the newly built payload,
  retaining the validated snapshot28 diagnostic ramdisk; reusing the old
  kernel payload cannot incorporate these fixes.
- Next capture must establish successful listener fallback/registration,
  enablefilecrypto exit status 0, init_user0 and zygote/boot completion.
  Missing error messages alone are not proof. The ~422.7s cutoff/reset
  cause remains unproven; display/WLED, RCU/latency, diagnostic SELinux and
  ROM baseline warnings are not claimed fixed by this patch set.
- No watchdog enablement, encryption/fstab changes, formatting or flashing.

## Next-build input rejected: QSEECOM disabled
- Uploaded `porting/artifacts/Image.gz` is 16,814,477 bytes, SHA256
  `76a7f246749cda730003eed0657793782cf17f166c194801c02000d76dcec402`.
  Banner identifies 6.12.93-4k-ga17c54c4fea0, Fedora Clang/LLD 22.1.8,
  built Oct 7 at 15:44:42 +0545. Source commit alone is insufficient:
  its embedded IKCONFIG explicitly says `# CONFIG_QSEECOM is not set`,
  and the listener-registration diagnostic string is absent.
- Uploaded DTB is 40,462 bytes, SHA256
  `2900c1bfa7b58ca1abf7bd324c84b6a8ea62d16c492fc26aa1dc37ed5508f1c3`;
  its touchscreen I/O supply correctly resolves to L6 at 1.8 V.
- Repack preserved snapshot28 ramdisk/header fields and regenerated SHA1,
  but embedded-config verification rejected the kernel. The generated
  snapshot29 boot image and concatenation were removed; uploaded inputs
  and the validated snapshot28 base are untouched. No device boot or flash.
- Required next action: enable CONFIG_QSEECOM=y in the SAME output directory
  used for the next VM make, olddefconfig, verify the setting, rebuild and
  transfer fresh artifacts. See `porting/BUILD-snapshot29.md`.

## Snapshot29 rebuilt inputs accepted and image packaged
- Corrected VM artifacts are in the parent workspace
  `../porting/artifacts/snapshot29-build/`. All five SHA256SUMS entries
  verify; Image.gz passes gzip integrity. Build provenance:
  d770048e78add360585bdaaeda9c0eb14658a357, output directory `out`,
  6.12.93-4k-gd770048e78ad, Fedora Clang/LLD 22.1.8.
- Embedded IKCONFIG matches transferred kernel.config byte-for-byte.
  CONFIG_QSEECOM=y is present, along with built-in SCM/TZMEM, 4K pages,
  touchscreen, VFAT/F2FS/EXT4, devtmpfs and configfs ACM/FunctionFS.
  QSEE listener-registration diagnostic code is present in the kernel.
- Image.gz: 16,896,113 bytes, SHA256
  `d79ec66db8163903eca47ec444e736edc4740f408d90eae1473e1e6ae87734e4`.
  Board DTB is the same verified 40,462-byte L6-supply-fixed DTB as above.
  Image.gz-dtb: 16,936,575 bytes, SHA256
  `b5ee31a5117fc2a68959d1dbac895e5b370a003a7828f107798a38e12e16db6f`;
  exact compressed kernel plus raw board DTB concatenation verified.
- Ready image (parent workspace):
  `../porting/artifacts/boot-ack-snapshot29-qsee-compat-tail-sd-screen.img`
  35,964,928 bytes, SHA256
  `6817bb32b85de1f254a1ef9abc92c10624f2049983534e12497c5c8be139b748`.
- Re-read/parsed output: exact new kernel/DTB; snapshot28 ramdisk unchanged,
  SHA256 `380088e3343072c8a9a39f88d3b84bb0346136e30c5c663694d7ab1e2312bffe`.
  Valid gzip/newc, 664 entries, exactly one ARM64 ELF init. Policy and
  ramdisk metadata are preserved by retaining the entire compressed blob.
  Only kernel size and regenerated boot-header SHA1 changed; command line,
  load addresses, other header bytes, total image size and zero tail retained.
- Packaged only: no snapshot29 phone boot or flash performed yet. Next run
  must capture actual listener/FBE/zygote outcomes, not infer success from
  this packaging check. Retained logger still names its SD file
  `snapshot28-kmsg.log`; a next run overwrites that card file.

## Snapshot29 boot outcome: listener fix verified, keymaster now blocks FBE
- Booted via `fastboot boot` (RAM only, no flash). USB capture failed:
  this Mac lacked pyserial, so the reader thread died with
  ModuleNotFoundError while the main thread continued through reboot and
  boot. Fixed in e440ac640 (top-level serial import = fail fast before
  touching the phone; pyserial installed). No snapshot29 USB log exists.
- Recovered from OrangeFox (temporary `fastboot boot`, no flash) using
  `su` root: SD file `snapshot28-kmsg.log` (435,954 bytes, overwritten this
  run) pulled as `porting/artifacts/snapshot29-sd.log`; 64 MiB logdump
  partition streamed via dd as `porting/artifacts/snapshot29-logdump.bin`
  (SHA256 `a8393ed875e1acfcb36101026187da983e2e6f3df263f479541958aad2856345`).
  SD stream = 2,893 records to t=326.3s, no EOF marker; device left USB
  with black screen (no adb/fastboot/EDL), same abrupt-cutoff shape as
  snapshot28 but ~96s earlier. Reset mechanism still unproven.
- SCM compatibility fix VERIFIED: zero `qseecom_scm_call failed` /
  `failed qseecom_register_listener` lines (snapshot28 had 8x -5/-12).
  `vendor.sys.listeners.registered=true` wait completed in 3,257 ms
  (was 18,735 ms). Legacy fallback path is exercised and succeeding.
- Boot progressed 1,440 -> 2,893 records, 149s -> 326s of init timeline:
  `installkey /data` dispatched, vdc reached vold, prepareCheckpoint exit 0.
- New blocker: `vendor.keymaster-3-0` exits status 1 within ~0.5 s on every
  start (pids 335, 353, 355, ... 840). keystore2 starts (pid 333) but
  `IKeystoreService/default` never publishes; vold's FBE waits on it and
  lazy-start fails. No `exec 5` exit, no init_user0, no zygote.
  Only 24 AVC denials total, none on keymaster/keystore/tee/qsee/vold/hal,
  so this is not a policy denial on current evidence. Keymaster stderr goes
  to logd (not kmsg), so the crash reason is not in this stream.
- Next discriminating step: capture the keymaster HAL's own error (logd
  buffer dumped to SD/logdump, or run the HAL's startup by hand from a
  recovery/root shell against /dev/qseecom). Touchscreen iovcc fix still
  unverified on device (no input events this far into boot).

## Snapshot30 plan review: ION confirmed, policy/logcat parts dropped
- Verified against the running artifacts, not taken on trust:
  `# CONFIG_ION is not set` in the snapshot29 kernel.config;
  `libQSEEComAPI.so` contains `ion_open` + `Error::Cannot open ION device`;
  `keystore.msm8953.so` references `libQSEEComAPI.so` + `QSEECom_start_app`;
  all four ION Kconfig symbols exist with satisfiable dependencies
  (STAGING already y, DMA_CMA already y).
- The plan's `arch/arm64/configs/tissot_gki.fragment` does not exist.
  Implemented in the canonical `scripts/tissot-ack.config` instead
  (STAGING/ION/ION_LEGACY/ION_SYSTEM_HEAP/ION_CMA_HEAP), plus
  `porting/BUILD-snapshot30.md` with the VM enable/rebuild/scp recipe.
- SELinux CIL edit DROPPED: `porting/artifacts/fedora-build/*.cil` is never
  loaded onto the device (no init/build reference), so editing it changes
  nothing. Live policy already covers the need:
  `system_ext_sepolicy.cil` has
  `(allow hal_keymaster ion_device (chr_file (... open ...)))`.
  Snapshot29's 24 denials (none on secure services) are consistent.
- Logcat streamer in init.c DEFERRED: the capture child runs as
  u:r:kernel:s0 with no stock-policy path to the logd socket, so it would
  likely be SELinux-denied; and kmsg alone can verify the ION fix
  (keymaster stays alive, keystore publishes, exec 5 exits 0). Revisit only
  if keymaster still crashes with ION present.

## Snapshot30 image packaged (ION kernel)
- VM artifacts landed in the repo checkout
  `porting/artifacts/snapshot30/` (not `snapshot30-build/`): Image.gz
  16,938,520 bytes SHA256
  `7d375229a60b308b6df814ece10f67dcf7f112df45b77f4da475e7d9c34f13f4`,
  same 40,462-byte L6-fixed DTB, kernel.config and build-info
  (source 56aed9bb8, `out`, 6.12.93-4k-g56aed9bb8b8d).
- Transfer defect: the VM's `Image.gz-dtb` is byte-identical to `Image.gz`
  (DTB never appended), so its SHA256SUMS entry for it FAILED. Five of six
  entries verify; gzip integrity passes. Concatenation was performed locally
  instead: 16,978,982 bytes SHA256
  `212f01e7191dbf3318fe13ac63edc4ff1f02dd8695667c11b338cf6e70d3e1c1`.
- Embedded IKCONFIG matches transferred kernel.config byte-for-byte:
  ION/ION_LEGACY/ION_SYSTEM_HEAP/ION_CMA_HEAP all y, plus QSEECOM, SCM,
  4K pages, touchscreen, VFAT/F2FS/EXT4. DTB resolves iovcc-supply to L6.
- Ready image (parent workspace):
  `../porting/artifacts/boot-ack-snapshot30-ion-qsee-compat-tail-sd-screen.img`
  35,964,928 bytes, SHA256
  `26385cfb3cd72e6c7cfc635c4aa9344a6318c70881905010ab3e0842a2f118e0`.
  Re-read verified: exact new kernel+DTB, snapshot28 ramdisk unchanged
  (SHA256 `380088e3...2312bffe`, 664 newc entries, one ARM64 ELF init),
  header delta only kernel size + regenerated SHA1, zero tail.
- Packaged only: no snapshot30 boot yet. Next run uses the fixed
  `usb-boot-capture.py` (pyserial now installed, fail-fast). Required
  outcomes: /dev/ion present, keymaster stays alive, keystore publishes,
  enablefilecrypto exits 0, init_user0, zygote. Snapshot29's SD stream is
  already safe on Mac as snapshot29-sd.log; the next run truncates and
  reuses the card file.

## Snapshot30 boot: inconclusive, cutoff moved earlier (68s)
- Booted via fixed `usb-boot-capture.py` (pyserial present): `fastboot boot`
  OKAY, reader opened the gadget, captured 1,087 lines / 113,744 bytes, then
  `read failed: Device not configured`. Log: `porting/artifacts/snapshot30-usb.log`.
- Recovered from the booted ROM with root (no recovery needed this time):
  SD stream as `porting/artifacts/snapshot30-sd.log` (114,583 bytes, private
  ro vfat mount, mount stayed private); logdump partition as
  `porting/artifacts/snapshot30-logdump.bin` (SHA256
  `9a859482...707f2efc`, same 79-byte exec-out excess as s29).
- Both on-device channels stop at the same place as USB (t=68.3s): real
  cutoff, not USB flake. Listeners registered in 367 ms, zero SCM errors;
  boot reached `exec 5 enablefilecrypto` launch ~2x faster than s29, then
  silence 0.04 s later during a keystore2 manifest lookup. No vdc line for
  pid 347, no keymaster start, no ION evidence either way (ION is silent in
  kmsg; /dev/ion presence unobservable here).
- Early kernel boot is line-identical to s29 (reserved regions, CMA at
  0xfaa00000, 983040 pages): ION did not disturb memory layout. The 2x
  userspace speedup is unexplained variance, not a kernel change.
- Boot-reason history shows only `bootloader` entries: no init-requested
  recovery reboot. Mechanism still unknown; single sample, re-run needed
  before concluding ION regressed anything (more likely run-to-run variance
  of the same FBE-launch killer seen in s28).
