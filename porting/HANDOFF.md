# Handoff: tissot 6.12 port boot bringup (snapshots 28-32)

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

## Snapshot30 run 2: same FBE-window death (90s), keymaster never execs
- Re-ran the identical image: `fastboot boot` OKAY, but USB captured
  0 bytes (gadget matched, stream never started). On-device channels are
  authoritative: SD `snapshot30-run2-sd.log` (117,459 bytes, 1,117 lines),
  logdump `snapshot30-run2-logdump.bin` (SHA256 `5a360da0...66047a3`).
- Genuine run-2 stream (SD file): exec5 launched (pid 345), installkey
  dispatched, vdc reached vold, vold->keystore2 fails (not published),
  cutoff at t=90.0s. Zero QSEE errors. `starting service
  vendor.keymaster-3-0` logged at 88s but no pid/exit follows: cutoff came
  ~2s after the keymaster start request (run 1: ~1s after). ION still
  unproven in action on both runs.
- TOOLING LESSON: the logdump partition has no O_TRUNC. A fresh pull after
  run 2 contains run-2's prefix OVER run-1's remainder (two exec5 launches
  at 89s and 149s in one image). Never analyze the partition tail past the
  SD file's length; the SD file is the length authority. (`cmp` confirmed
  partition[:117459] == run-2 SD exactly.)
- No tombstones in /data/tombstones: no native crash was recorded.
- Battery ruled out: 98%, 4.29V, health Good, 33.7C on the ROM after.
- Timing table (fsck variance explains the speedup, not the kernel):
  mount_all --early at s29=138s, s30r1=65s, s30r2=79s; the gap sits between
  SD-ready and mount_all, i.e. userdata fsck after each unclean cutoff.
  Early kernel boot is identical across runs.
- Standing interpretation: alive-and-logging one instant, silent the next,
  no shutdown sequence, no panic, no recovery reason, good battery. Fits a
  secure-world-initiated reset during FBE-window TA activity (both s30
  cutoffs land 1-2s after keymaster start is requested) better than any
  Linux-side cause, but still unproven. s29's 326s death mid-retry-loop
  remains the out-of-pattern sample.

## Snapshot30 run 3: keymaster execs (ION works), death during first transaction
- USB captured 1,118 lines / 117,722 bytes to t=96.9s (`snapshot30-run3-usb.log`
  + `.status`); SD `snapshot30-run3-sd.log` (115,856 bytes, ends 0.5s earlier)
  is the length authority (partition prefix matches exactly);
  `snapshot30-run3-logdump.bin` SHA256 `a78dc2b6...ec08e`.
- `vendor.keymaster-3-0 ... has pid 331` at 95.8s: first exec under the new
  kernel, no instant status-1 death. ION fix VERIFIED in action (s29's 0.4s
  instant exits are gone).
- At 96.8-96.9s hwservicemanager routes keystore2's `IKeymasterDevice`
  request to live pid 331 (keymaster already running 1.1s), then all
  channels stop. No exit line, no publication confirm, no shutdown.
- Correlation now 5/5 deaths within seconds of keymaster activity
  (s28 +7s, s29 +1s, s30r1 +1s, s30r2 +2s, s30r3 +1s; three runs had exactly
  one start each, so this is not restart-loop base rate). Userspace was
  healthy at each cutoff (init forking, Binder flowing). The wedge is in
  the first TA-load/secure transaction, below everything Linux logs.
- Next: the TA image itself. Identify what `QSEECom_start_app` loads for
  keymaster on this device and verify that image is reachable/valid under
  the new kernel's storage/firmware view. No kernel-option guessing.

## Listener-callback audit: spill buffer has no TZ-shared backing (fix design)
- Read-only audit (port `drivers/misc/qseecom.c` vs donor) returned one
  mechanism that fits all evidence. Everything working on device is a
  <=4-arg SMC (register-passed: REGISTER_LISTENER 3, APP_START 3,
  probes 1-2, responses 2-4). The first TA data calls spill: 5-arg
  SEND_DATA and 7-arg WHITELIST copy args[3..] (rsp_ptr/len/sglistinfo)
  to a buffer TZ was never granted.
- Donor put that spill buffer in TZ-registered shmbridge memory + cache
  flushes. Our modern transport (`qcom_scm-smc.c`) spills to tzmem
  (CPU-coherent, fine for HLOS) but this device has no shmbridge
  (heaps 19/26/27 unavailable, port stubs it to no-op), so nothing
  programs TZ-side permission. TZ reads unpermitted phys -> secure
  abort/hang -> the SMC never returns, zero kernel lines. Exactly observed.
- Same defect class covers tzbuf itself: port `__qseecom_alloc_tzbuf`
  is plain `dma_alloc_coherent`, donor's was shmbridge-registered. The only
  memory TZ is known to share on this device is the reserved window
  `qseecom@84a00000` (25 MiB). Fix direction: back BOTH the legacy-shim
  >4-arg spill path and tzbuf from that window (shim accepts an optional
  spill allocator registered by qseecom at probe; native tzmem path for
  other clients untouched). Only qseecom uses the legacy shim (verified by
  grep), so the blast radius is one driver.
- Second item: port uses `dma_buf_*_unlocked` without the resv lock the
  variants require (donor uses locked versions). Same first-callback wedge
  shape via torn sb phys. Fix: match donor (locked variants).
- Self-correction: narrow our snapshot29 `-EIO -> -EOPNOTSUPP` remap
  (audit #3: masks real transport failures as 'unsupported'; currently only
  a triage-killer, not the wedge). Scope it to the listener probe or log
  the pre-remap value.
- #4 (clock livelock) refuted by absence: no `Unable to enable`/CLK lines
  in any stream (weak refutation only). #5 (dmac clean-only) closed, no action.
- Confirm/refute probe for #1 on next boot (no fix needed to run it):
  one `pr_info` on the >4-arg spill path logging smc_id/arglen/x5-phys;
  the wedge is confirmed if a spilled SEND_DATA is the last qseecom SMC.
  AWAITING USER CONFIRMATION before any source edit (repo rule).

## Snapshot31 implemented: ION carveout binding (awaiting VM build)
- Verified before implementing (not taken on trust): stock live DT has
  `qseecom_region@0` (16 MiB), `qseecom_ta_region` (8 MiB),
  `other_ext_region@0` (0x84a00000); stock `qcom,ion` binds heaps
  @27/@19/@25; heap@27 carries a `memory-region` property.
- Smoking gun in our own log: s30r3 prints `ION heap qsecom created`
  with NO address, which the driver prints exactly when base/size are
  zero (no `memory-region` -> early return). Heap 27 existed but had no
  dedicated memory, so keymaster's 40KB landed in generic CMA and the
  first TA transaction died on TZ XPU rejection. `msm_ion_of.c`
  (present, compiled under CONFIG_ION) implements the memory-region lane.
- Changes in `msm8953-xiaomi-tissot.dts`: restored both shared pools at
  stock sizes; heap@1b(27,DMA)->qseecom region, heap@13(19,DMA)->TA
  region, heap@19(25,SYSTEM); renamed our `qseecom@84a00000` to
  `other_ext_region` (kept no-map AND kept 0x1900000: stock's 0x1e00000
  would overlap smem@86300000/ramoops@86800000 in our layout).
  DT compiles; all phandle bindings verified in the compiled DTB.
  Corrected two plan details: the XPU range `0xff000000-...` is
  illustrative, not a verified fact; the expected boot marker is the
  driver's actual format `ION heap qsecom created at <addr>`.
- Dropped nothing else from the plan; driver section needed no port
  (msm_ion_of.c already in tree and compiled).
- VM: same section-1 flow as snapshot30 (existing OUT dir, olddefconfig,
  guard, rebuild kernel+DTB), stage to `~/snapshot31-build`, scp all six
  files. Decisive boot marker: `ION heap qsecom created at <addr>`
  followed by keymaster surviving its first transaction.

## Snapshot31 image packaged (carveout kernel)
- VM artifacts in repo checkout `porting/artifacts/snapshot31/`: all six
  SHA256SUMS entries verify (this time the VM concatenation is correct:
  Image.gz-dtb == Image.gz + DTB exactly). Source 2f5c7e101, `out`,
  6.12.93-4k-g2f5c7e1017e4.
- Image.gz 16,938,780 bytes SHA256
  `323ed240...9250f6a18`; DTB 40,915 bytes SHA256 `66bcc25e...168d9e7c6b7352026`
  with heaps 27/19/25 and 16+8 MiB regions confirmed in the transferred DTB.
- Ready image (parent workspace):
  `../porting/artifacts/boot-ack-snapshot31-qsee-carveout-tail-sd-screen.img`
  35,964,928 bytes, SHA256
  `d9768151...9ff4457aceb`. Re-read verified against the validated base.
- Packaged only, not booted. Decisive marker stays: `ION heap qsecom
  created at <addr>` (with address this time), then keymaster surviving
  its first transaction, keystore publish, enablefilecrypto exit 0.

## Snapshot31 boot: carveout bound, death unchanged -> spill path is next
- USB 1,175 lines / 126,664 bytes to t=94.7s (`snapshot31-usb.log`).
  Pools created as designed: `qseecom_region@0` at 0xff000000 (16 MiB),
  `qseecom_ta_region` at 0xfe800000 (8 MiB); rename to other_ext_region
  clean (25 MiB, no overlap). `ION heap qsecom/qsecom_ta/system created`
  (no addresses: expected, size field stays 0 by design).
- Code-verified (not log-provable): `ion_cma_heap_create` uses
  `dev_get_cma_area(priv-dev)`, bound by `of_dma_configure` to the
  memory-region pool. s30's heap silently fell back to default system CMA
  (no "cma not backed" either); s31's heap is carveout-backed by the same
  chain. The "created at <addr>" marker from the plan never fires by
  design; binding verified in-tree + DTB instead.
- Outcome: keymaster pid 335 started 93.5s, cutoff 94.7s, zero QSEE errors,
  phone off USB. IDENTICAL death with heap backing fixed.
- Disambiguation complete: heap backing does not decide it. The remaining
  TZ-unshared path is the SMC >4-arg SPILL buffer (audit #1, still tzmem
  in s31) and secondarily sb phys (#2). The reserved-window spill+tzbuf
  fix designed earlier is now the forced next change. AWAITING USER
  CONFIRMATION before source edits (repo rule).

## Snapshot31 on-device logs recovered
- SD `snapshot31-sd.log` (126,757 bytes, 1,177 lines, private ro mount),
  logdump `snapshot31-logdump.bin` (SHA256 `22fc3db9...5ba175`,
  partition prefix == SD exactly). All three channels end together at
  t=94.7s during the keystore2 lookup; pid 335 never exited. Record
  complete; still awaiting spill-fix approval.

## Snapshot32 implemented: carveout spill + tzbuf + locking (awaiting VM build)
- `HANDOFF-snapshot28.md` renamed to `porting/HANDOFF.md` (all snapshot
  history lives here now).
- `drivers/firmware/qcom/qcom_scm-smc.c`: optional spill allocator hook
  (`qcom_scm_set_spill_mem`, default NULL = native tzmem for all other
  clients). Override branch fills the identical 7-u64 layout, passes the
  carveout phys in x5, logs `qcom_scm: spilled %d args to carveout %pad`
  (the confirm/refute probe, permanent), frees on every exit path.
- `drivers/misc/qseecom.c`: probe attaches the shared carveout
  (`of_reserved_mem_device_init`, warn-and-continue) and registers a
  `dma_alloc_coherent(qseecom.dev)` spill pair; tzbuf follows automatically
  through the same device. Listener probe now treats `-EOPNOTSUPP` and
  `-EIO` as unsupported (site-local, replaces the blanket shim remap).
  Four `dma_buf_*_unlocked` calls converted to locked versions (6.12 has no
  `dma_buf_kmap`; locked `vmap` is the donor-faithful equivalent).
- `include/soc/qcom/scm.h`: blanket `-EIO -> -EOPNOTSUPP` reverted (pass
  through); spill struct mirrored with sync comment; kept errno.h (driver
  still needs E-codes) and added gfp.h.
- Board DT: `&qcom_seecom { memory-region = <&qseecom_mem>; };` (label
  verified against upstream `qcom_seecom:`). DT compiles; device phandle
  == pool phandle (0x79).
- NOT compiled on this Mac (no kernel toolchain here): VM build is the
  compile check. DT binding already proven in the compiled DTB.
- VM: pull, same section-1 flow, stage to `~/snapshot32-build`, scp six.
  Decisive markers: `qseecom: SMC spill buffers use the shared carveout`
  then `qcom_scm: spilled 7 args to carveout ...` then keymaster surviving
  its first transaction.

## Snapshot32 image packaged (spill-fix kernel)
- VM artifacts in repo checkout `porting/artifacts/snapshot32/`: all six
  SHA256SUMS entries verify, concatenation correct. Source 15218cbd4,
  6.12.93-4k-g15218cbd4976. Spill probe + carveout strings confirmed IN the
  binary; DTB carveout attach confirmed (device region == pool, 0x79).
- Ready image (parent workspace):
  `../porting/artifacts/boot-ack-snapshot32-spill-carveout-tail-sd-screen.img`
  35,964,928 bytes, SHA256
  `9b04908c...47915fd`. Re-read verified against the validated base.
- Packaged only, not booted. Watch for: `qseecom: SMC spill buffers use
  the shared carveout`, then `qcom_scm: spilled 7 args to carveout ...`,
  then keymaster surviving its first transaction.

## Snapshot32 on-device logs recovered
- SD `snapshot32-sd.log` (117,333 bytes, ends 0.04s before USB at exec5
  spawn; private ro mount), logdump `snapshot32-logdump.bin` (SHA256
  `33b7c987...d633f851`, prefix == SD). pid 338 started, never exited, in
  all channels. Spill-to-carveout confirmed working; death persists at the
  FBE transaction. Next: listener-roundtrip pr_info tracing (proposed,
  awaiting approval).

## Snapshot39 — per-daemon liveness probe (complete, with one open question)

### What was built

`scripts/initramfs-diag/init.c` only. No kernel change. The snapshot38 kernel
image is reused byte-for-byte (packaged payload verified identical; snapshot38's
whole-image SHA256 still `e797646f707c9b727224bb339070498c5427d6939c305257d7ff1b5eea9ceb27`).

* `daemon_watch[]`: keymaster@3.0, keystore2, vold, vdc, servicemanager, logd,
  matched by prefix against `/proc/<pid>/comm` (comm truncates to 15 bytes, so
  full-string equality would never fire).
* `/proc/<pid>/stat` parsed by locating the **last** `)` and splitting after it,
  because field 2 (comm) may itself contain spaces or parentheses. state=token0,
  ppid=token1, utime=token11, stime=token12, threads=token17.
* `wchan` read best-effort; EACCES/short read emits `-`, never fatal.
* Emission on change OR a **1 s** heartbeat. Probe lines go straight to the
  capture fd via `write_capture`, never through `/dev/kmsg`, so they survive a
  wedged printk. Confirmed present in both logdump and the SD mirror.
* Runs in the existing durable recorder child, same thread as `dump_log`, gated
  on `sampler != NULL` so the USB child never writes it.

### Defects found and fixed by the runs

1. **20 s heartbeat was too coarse.** Run 1's ticks landed at 23.6/43.6/63.6 s
   while keystore2 started at 65.2 s — no tick existed inside the stall window.
   Now 1 s (~600 KB of a 64 MiB partition).
2. **Uninitialised fields.** `daemon_probe_collect` reset pid/state/wchan but not
   ppid/threads/utime/stime, so absent daemons printed stack garbage.
3. **`state` assigned before the field count was validated**, so a truncated stat
   reported a real state with garbage pids.
4. **`errno` sampled on success**, reporting a stale value. Caught by the self-test.
5. **First-tick sentinel never set** — `daemon_probe_init` memset `comm_errno` to
   0 while the guard tests for −1, so the comm census never fired (run 4).
6. **Ramoops self-test was flaky** (10/25 failures) because it asserted the kmsg
   records were the *last* bytes of the capture; with a 1 s heartbeat a second
   boundary can land inside `dump_log`'s loop. Now position-independent.

### The finding

The probe is mechanically correct — the host self-check resolves all six names
against real processes, and the on-device census proves every `comm` read
succeeds (`comm_errno=0`). But **the recorder's `/proc` does not contain
Android's service processes.**

Run 5's one-shot census (`run5-proccomm-census.txt`) of the recorder's own
`/proc`: 161 entries, ~156 kernel threads, and exactly five userspace processes —
pid 1 `init` and pids 154/158/159/160, the ramdisk-init lineage the recorder
itself forks. Highest pid visible: **162**.

Android's init, in the same boot, reports:

    started service 'keystore2' has pid 334
    started service 'vendor.keymaster-3-0' has pid 336
    servicemanager ... Caller(pid=291 ...)
    vold ... Caller(pid=302 ...)

Entry count stays at 161 → 162 for the whole run while Android allocates pids
to 350, then collapses to 5 at teardown. So every `DIAG: daemon` line reads
`pid=0`: the daemons are **invisible**, not idle, blocked or crashed.

### What is ruled out

| hypothesis | verdict | evidence |
|---|---|---|
| watch names never match this kernel's comm | ruled out | census proves comm reads succeed; host resolves all six |
| SELinux denies the reads | ruled out | `comm_errno=0` on every tick, 161/161 reads succeeded |
| heartbeat too coarse | **was real, fixed** | run 1 ticks vs 65.2 s daemon start |
| `/proc` unmounted | ruled out | `opendir` succeeds, entries nonzero |
| probe lost with the printk path | ruled out | present in logdump *and* SD mirror |
| mount-namespace boundary | ruled out (run 6) | PID 1's mount namespace shows the same ~168 ceiling |
| PID-namespace boundary | **not confirmed** (run 7) | `setns` via `/proc/1/ns/pid` returns ENOENT |

### Open question

Why does the recorder's `/proc` ceiling at ~168 while Android allocates pids to
350, given PID 1 shares the mount namespace view and exposes no `ns/pid`?

**Next discriminating probe (one boot):** from the durable child, at the end of
the run, emit `ns_last_pid` (`/proc/sys/kernel/ns_last_pid`), the highest pid
in `/proc`, and `readlink` of `/proc/1/ns/pid` and `/proc/self/ns/pid`.

* `ns_last_pid` ≫ highest pid in `/proc` ⇒ the view is restricted or frozen and
  the probe must move to another source entirely.
* `ns_last_pid` ≈ highest pid ⇒ the recorder's `/proc` is correct and Android's
  reported pids are namespaced elsewhere; chase `ns_last_pid` instead.

If the probe cannot be fixed cheaply, `snapshot39/FINDINGS.md` option 2 avoids
`/proc` entirely: ask `servicemanager`/`hwservicemanager` whether
`android.system.keystore2.IKeystoreService/default` is registered, which proves
publication without process state.

### Two plan items that were wrong

* Probe lines can **never** appear in the kernel snapshot slots: the snapshotter
  copies the console ring, the probe writes the logdump block device. Disjoint
  channels.
* Run 2's SD logs are unrecoverable — the recorder opens
  `/sdlog/snapshot28-kmsg.log` with `O_TRUNC` each boot, so each run overwrites
  the last.

### Artifact hygiene

`porting/artifacts` went 4.4 G → 537 M: all snapshot ≤37 logs/dumps/images
deleted, and the 64 MiB `*-preboot-*` / zero-readback payloads pruned after
their sha256 were recorded in `snapshot39/manifest.json`.

Two new tools, both self-pruning:

* `porting/logging/clear-logdump.sh <tag>` — clears the partition, proves it is
  all zeros, records the verdict and pre-clear sha256, then **deletes the 64 MiB
  readback**.
* `porting/logging/pull-run-evidence.sh <run> <image>` — pulls logdump, SD card
  and both kernel snapshot slots, names everything `<tag>-run<N>-…`, prints the
  probe summary.

Every run's evidence is named and hashed in `snapshot39/manifest.json` (runs 1–7).
Full write-up in `snapshot39/FINDINGS.md`.

### Device state

Phone returned to ROM after every run; `sys.boot_completed=1`, slot `_a`, root
via Magisk `su`, battery 96%. The SD card is healthy this round — vold mounted
it normally at `/mnt/media_rw/5483-0F14`, no `mmc1: error -110`.

### Reproducing a run

    cd porting/artifacts/snapshot39
    ../../logging/pull-run-evidence.sh <n> boot-ack-snapshot39-daemon-probe.img
    ../../logging/clear-logdump.sh snapshot39-run<n>
    /tmp/snapshot33-capture-venv/bin/python ../../logging/usb-boot-capture.py \
        --image ../boot-ack-snapshot39-daemon-probe.img \
        --log snapshot39-run<n>-usb.log --adb-serial 2819f2320604 \
        --status snapshot39-run<n>-usb-capture.status

`fastboot boot` only; nothing is ever flashed and the slot is never changed.

## Snapshot40 run 1 — the /proc ceiling question is answered: there is no pid namespace to enter

### Build
`scripts/initramfs-diag/init.c` only, no kernel change; snapshot38/39 kernel
payload reused byte-for-byte (`Image.gz-dtb` SHA256 `5f941bdc…b3bbe9d`).
`daemon_probe_collect` now also reports the highest numeric pid in the view,
and `daemon_pidns_report()` emits one line on the first tick and again when
the capture window closes:

    DIAG: pidns entries=<n> highest=<n> ns_last_pid=<n> ns_pid_1=<link|errno> \
          ns_self=<link|errno> ns_open_errno=<n>

Host self-tests run for all six build variants; the daemon self-test gained
asserts for `highest=` and for every namespace field being present even when
the kernel refuses the read. Package gates: 665 records, only `init` differs,
DTB and kernel byte-identical, header diff limited to sizes + regenerated
SHA1. Image `porting/artifacts/boot-ack-snapshot40-pidns-probe.img`,
35,964,928 bytes, SHA256 `0cbe8e03…845d3a3`.

### Run
Pre-clear of `logdump` verified all-zero (pre-clear SHA256 `d2b0badd…3e12`),
`fastboot boot` OKAY/OKAY, nothing flashed. The phone rebooted itself out of
the kernel and came back on stock 4.19.325 within ~137 s of host time; it was
never seen in fastboot, so the reboot path is still unexplained. Pulled with
`porting/logging/pull-run-evidence.sh` (Magisk `su`) into
`porting/artifacts/snapshot40/`:

| artifact | bytes | sha256 (16) |
|---|---|---|
| `snapshot40-run1-logdump.bin` | 67108864 | `5416c3f7572738fe` |
| `snapshot40-run1-sd-snapshot28-kmsg.log` | 825782 | `ef48b7d04506f276` |
| `snapshot40-run1-kernel-snapshot-slot0.bin` | 1048576 | `cf72c88a79be5cc7` |
| `snapshot40-run1-kernel-snapshot-slot1.bin` | 1048576 | `47c57d5b2c0f19f3` |

Records 0–4561 run to t=100.418822 s. Both snapshot slots decode and contain
no panic/oops/BUG/watchdog/`Call trace` marker — the one hit in each is an
unrelated `mkdir /metadata/watchdog` failure. The stall is unchanged from
run 7: keymaster pid 339 reaches
`QSEECOM: native ioctl 0xc0209703 nr 3 enter` and the stream ends 0.4 ms later.
The end-of-run `pidns` line never fired — the run dies 800 s before the
capture window closes.

### Answer to the open question

    DIAG: pidns entries=160 highest=161 ns_last_pid=0 ns_pid_1=errno=2 \
          ns_self=errno=2 ns_open_errno=2

* `readlink /proc/self/ns/pid` → **ENOENT**, as does `/proc/1/ns/pid` and
  `open()` on it. There is no pid-namespace handle in this `/proc` at all,
  self included, so `setns()` can never be made to work.
* `guardns vantage=mntns` (the guard child already inside PID 1's mount
  namespace) reports **entries=5** — Android's ~340 processes are invisible
  from PID 1's own namespace too, not just from the recorder's.
* `ns_last_pid` parsed as 0, i.e. the read produced nothing usable.

Verdict per the snapshot39 decision rule: the `/proc` view is restricted or
foreign, so **the daemon-liveness probe is dead** — not "too coarse", not
SELinux, not a mount-namespace problem. `FINDINGS.md` option 1 (fork after
Android's init and `setns` into its pid namespace) is refuted with evidence
rather than left unconfirmed. Daemon liveness must come from a non-`/proc`
source: FINDINGS option 2 (ask `servicemanager` for
`android.system.keystore2.IKeystoreService/default`) or option 3 (instrument
the stall).

### Two side findings

* 3,064 SELinux denials this run, of which **3,041 are `sys_ptrace` from
  `u:r:kernel:s0` to `u:r:kernel:s0`** with `comm="init"` — our own diagnostic
  domain being denied ptrace-mode reads, near-certainly the `/proc` wchan/stat
  probes. Audit noise generated by the tooling, not an Android failure, but it
  is the same tooling that can no longer see anything, so it buys nothing.
* The snapshot35 kernel tracing **is** live in this image: the stall is
  visible down to `native ioctl 0xc0209703 nr 3 enter` for keymaster pid 339,
  app_id 65537, `sb_phys=0xf9370000`. No `snapshot35 scm_*` line fired,
  because the gate in `__scm_smc_call` only traces `owner 48 / svc 0 /
  cmd 1|6` and keymaster's failing call is cmd `0x3`. Widening that gate is
  the cheapest way to see whether its SMC ever returns — it needs the VM
  kernel rebuild, not another userspace probe.

### Device state
Phone on installed ROM 4.19.325, root via Magisk `su`. Nothing flashed, slot
untouched, SD card untouched.

## Snapshot41 prep — widened SCM gate + live `selinux=0` (awaiting VM build)

Two changes, no DT, no ramdisk, no config-fragment change:

* `drivers/firmware/qcom/qcom_scm-smc.c`: `trace_send` is now
  `owner == 48 && svc == 0`, was `cmd == 1 || cmd == 6`. The snapshot35 gate
  excluded cmd `0x3` — the exact call keymaster stalls in. `__scm_smc_do_quirk`'s
  `__ratelimit(HZ, 8)` still bounds `scm_pre` volume; `scm_send_desc` is not
  rate-limited and is therefore the reliable indicator.
* `scripts/build-ack-tissot.sh`: `CONFIG_SECURITY_SELINUX` and
  `CONFIG_SECURITY_SELINUX_BOOTPARAM` added to the required-symbol assertion,
  so a build that loses either fails before burning a boot.

Verified locally: `make O=out drivers/firmware/qcom/qcom_scm-smc.o` compiles
clean (NDK-independent, host clang 22.1.8, `ARCH=arm64 LLVM=1 LLVM_IAS=1`);
both trace templates survive in the object. `bash -n` on the build script
passes. No kernel `Image.gz` built on this host — the VM owns that.

### The inert `selinux=0`, now explained

The snapshot38 `Image.gz` embedded config says:

    CONFIG_SECURITY_SELINUX=y
    # CONFIG_SECURITY_SELINUX_BOOTPARAM is not set
    CONFIG_SECURITY_SELINUX_DEVELOP=y

`scripts/tissot-ack.config:137` has requested `BOOTPARAM=y` all along, so the
VM builds are not running the fragment: they reuse an existing output
directory seeded from the baseline config. That is why build14 saw the token
consumed yet enforcing anyway, and why `current-port-progress.md` §14 listed
three exhausted fork paths. The fix is not a rebuild-from-scratch, it is
enabling the symbol in the SAME `out` directory. Full recipe, transfer list,
six acceptance checks and the run-1 decision table:
`porting/BUILD-snapshot41.md`.

Expected decision table for the next boot is recorded there; short version:
`scm_send_desc cmd=3` present → the driver sent it and TZ never answered;
`scm_send_desc` absent → the stall is above `__scm_smc_call` and the ioctl
never reached SCM at all.

## Snapshot41 built locally (this machine) and packaged

Built here with host clang/LLD 22.1.8, seeded from the shipping kernel's own
embedded `IKCONFIG`, not from `out/`. See `porting/BUILD-snapshot42.md` for why
`out/` must not be used.

| check | result |
|---|---|
| `Image.gz-dtb == Image.gz + dtb` | PASS |
| `gzip -t` | PASS |
| embedded `IKCONFIG` has `SECURITY_SELINUX_BOOTPARAM=y`, no "not set" | **PASS — the gate that would have caught 14 builds** |
| `QSEECOM` / `ION` / `SELINUX` / F2FS / VFAT / EXT4 / FunctionFS all `=y` | PASS |
| `scm_send_desc` + `scm_pre` + `qsee_set_mem` + spill templates in the binary | PASS |
| board DTB vs shipping `18a1081e…7aae8` | byte-identical |

Config delta vs the shipping kernel: **5 symbols**, four toolchain bookkeeping
and one functional —

    # CONFIG_SECURITY_SELINUX_BOOTPARAM is not set
    -> CONFIG_SECURITY_SELINUX_BOOTPARAM=y

Release `6.12.93-4k-g51fb88d9cdcf-dirty`. `Image.gz` 16,991,737 B,
`Image.gz-dtb` 17,032,668 B, dtb 40,931 B.

Image `porting/artifacts/boot-ack-snapshot41-scm-all.img`, 35,964,928 bytes,
SHA256 `67c2887def1ae464b9da32b1d7e1ca1fb62662739b463e5bd8e915564c25200f`.
665 ramdisk records, only `init` differs from the validated snapshot40 base,
header diff limited to kernel size + regenerated SHA1, zero tail. Re-read from
the finished image: kernel payload byte-identical, ramdisk decodes to
45,170,104 B, `DIAG: pidns` probe present.

The experiment is now clean: one functional config symbol and one source
change (the widened trace gate) separate this kernel from the one that produced
snapshot40 run 1.
