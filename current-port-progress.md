# Tissot ACK 6.12 port — current progress

> **Current state: porting/CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUILD_TISSOT.md](BUILD_TISSOT.md).
>
> The per-run evidence this document cites (boot images, kernel directories,
> init binaries, logdumps) is no longer in the repository; it is
> git-ignored and disposable, and the boot images are in
> ../ack-kgsl-artifacts.

Updated: 2026-10-05 (UTC+0545 device clock). Companion to
`docs/ack-6.18-boot-investigation.md` §14–§15; this file is the live status
log. Kernel tree: `../ack-kgsl` (branch `main`); the android16-6.12 checkout
`3a7d1771d4925a56f7eeb8a5ba1faff0c544a9ef`, whose image builds carry local
adaptations and identify as `6.12.93-4k-g3a7d1771d492-dirty`). AOSP baseline
cited for init behavior: `system/core` `a3b721a32242006b59cb12bd62c9133632af3a2d`.

## 1. Where the port stands

Milestone reached and evidenced (`boot-ack-android-policy-capture.img`):

- ACK kernel + appended DTB boots the installed Android user build.
- Debug policy mechanism (`/force_debuggable` +
  `/userdebug_plat_sepolicy.cil`, two added kernel-domain rules) selects and
  compiles the modified platform policy; `secilc` exit 0.
- SELinux switched to enforcing at boot time 56.639 s
  (`audit: type=1404 ... enforcing=1 old_enforcing=0 ... res=1`).
- Original Android second-stage init started at 56.788 s and kept scheduling
  services through 317.820 s; durable capture ends with its explicit EOF
  marker. 1,142 kernel records, sequence 0–1141, in order.
- Conclusion: **no global kernel stop at SELinux enforcement**. Android boot
  is not yet complete.

Evidence:

- `../ack-boot-test/ack-android-policy-capture-logdump.log` — 119,637 bytes,
  trimmed at EOF marker.
- `../ack-boot-test/ack-android-policy-capture-logdump.bin` — full 64 MiB raw
  `logdump` (mmcblk0p48), SHA256
  `0a2f4ea4fa0a87cfe43f21e03026effac0b6adccaf8dbff3f172e9df7020a601`.
- `../ack-boot-test/android-policy-capture/android-usb-live.log` — 8,192-byte
  partial native USB stream (recorder gave up on a blocked `EAGAIN` sink after
  ~1 s; later messages still reach the durable capture).

## 2. Current blockers, in order

### 2.1 `/dev/block/bootdevice` alias missing (top priority)

- Installed `/system/vendor/etc/init/hw/init.target.rc` lines 34–36 wait for
  `/dev/block/platform/soc/${ro.boot.bootdevice}` (= `7824900.mmc`), symlink
  it to `/dev/block/bootdevice`, then `mount_all --early`.
- ACK DT names the SoC node `soc@0`, so devices appear under
  `/dev/block/platform/soc@0/7824900.mmc`; the vendor `wait` times out
  (captured: `init: wait for '/dev/block/platform/soc/7824900.mmc' timed out`).
- fstab consumers (`userdata`, `persist`, `dsp`, `modem`) reference
  `/dev/block/bootdevice/by-name/*` and are skipped; `/data` is not mounted.
- Kernel GPT parsing is fine: `PARTNAME=logdump` works and `system_a` mounted
  via `/dev/block/by-name/system_a`. Only the legacy alias path is broken.

### 2.2 `vendor.qseecomd` exits 255 repeatedly (separate problem)

- init.target.rc lines 63–64 `start vendor.qseecomd` +
  `wait_for_prop vendor.sys.listeners.registered true`; the log shows repeated
  status-255 exits through end of capture.
- ACK `out/.config`: `# CONFIG_QCOM_QSEECOM is not set`. Even if enabled,
  upstream `qcom_qseecom.c` exposes only a uefisecapp auxiliary client — no
  `/dev/qseecom` char device, no legacy ioctl ABI.
- Installed `libQSEEComAPI.so` opens `/dev/qseecom` and depends on ION
  (`/dev/ion`, `ion_alloc_fd`). Stock kernel (4.9 recovery) provides both.
- Verdict: real driver/ABI port required (legacy QSEECom + ION or a shim);
  naming changes cannot fix it. Not started.

## 3. Approved fix being prepared (alias only)

User-approved two-line change (tested copy, not installed ROM):
`soc/${ro.boot.bootdevice}` → `soc@0/${ro.boot.bootdevice}` in the `wait` and
`symlink` lines of `init.target.rc`.

Host-side test copy state:

- `../ack-boot-test/android-policy-capture/init.target.rc` modified:
  md5 `6695a3077536d3e72529fcceac90670c` (installed original:
  `df9e7d7da4f43adf3c364056d025c8b7`).
- `../ack-boot-test/android-policy-capture/fstab.qcom` identical to installed
  (md5 `45652a9c8682bec4200fd11c750c5b26`).

**Simpler delivery plan found while checking constraints** (vendor content
lives on read-only `system_a`, mounted as `/system`; the boot ramdisk carries
no vendor files, so the modified rc cannot be shipped in the ramdisk):

- Preferred: extend `scripts/initramfs-diag/init.c` `ANDROID_CAPTURE` path
  with a tiny watcher child (shared mount namespace, like the existing USB
  capture fork): poll until
  `/dev/block/platform/soc@0/7824900.mmc` exists, then
  `symlink(..., "/dev/block/bootdevice")`. This makes vendor init's own
  `wait` succeed; its `symlink` then fails harmlessly (`File exists` logged).
  No `init.target.rc` override, no bind-mount machinery.
  The `soc@0` rc fix stays applied to the host copy for later use (e.g. an
  eventual overlay); the watcher alone should be sufficient for the test.

## 4. Safety review before any test boot

- Installed fstab f2fs `userdata` line is `wait,check,fileencryption=...`
  (no `formattable`). The **ext4 fallback line for the same block device is
  `formattable`**: if the f2fs mount/check fails, fs_mgr may proceed to the
  ext4 entry and, on failure, format userdata → **user-data loss risk**.
- Mitigating config on ACK (`out/.config`, verified):
  `CONFIG_FS_ENCRYPTION=y`, `CONFIG_FS_ENCRYPTION_ALGS=y`,
  `CONFIG_FS_ENCRYPTION_INLINE_CRYPT=y`, `CONFIG_F2FS_FS=y`,
  `CONFIG_F2FS_FS_SECURITY=y`. `mount(2)` of the existing f2fs userdata
  should therefore succeed; the formattable branch should not be reached.
  `fsck.f2fs` is present in the installed system image
  (`/system/bin/fsck.f2fs`, 341,832 bytes; `e2fsck` is also present).
  Remaining unverified: actual f2fs mount behavior on ACK — this is the
  reason the test boot is gated on explicit re-confirmation.
- First-stage fstab (`first_stage_ramdisk/fstab.qcom`) is a ramdisk file we
  fully control; the second-stage `/vendor/etc/fstab.qcom` is on read-only
  `system_a` and is **not** modifiable for a temporary boot.

## 5. Rebuild/flash status

- No kernel rebuild, no flashing, no installed-ROM writes during this phase.
  All Android-side tests are `fastboot boot` temporary images; recovery
  checks were read-only except recovery's own automatic `/data` mount
  (stock behavior, not caused by our tooling).
- Phone is currently in the temporary recovery reader (ADB `recovery`,
  serial `2819f2320604`), with `system_a` mounted read-only at
  `/tmp/ack-system` for evidence; it is unmounted when checks complete.

## 6. Next steps

0. Progress recorded in this file (`current-port-progress.md`, repo root)
   as requested before further edits; the main investigation doc remains at
   §15 until the alias test produces new evidence.
1. Confirm `fsck.f2fs` presence in `system_a` — **done, verified** (see §4).
2. On approval: add the symlink watcher to
   `scripts/initramfs-diag/init.c` (ANDROID_CAPTURE path only), rebuild the
   static init, repack as a new temporary image
   (e.g. `boot-ack-android-bootdevice-capture.img`), verify preservation
   checks (kernel/DTB unchanged, original ramdisk entries intact).
3. Temporarily boot; verify in the durable capture: alias exists, vendor
   `wait` succeeds, `mount_all --early` mounts `persist`/`dsp`/`modem`, and
   `--late` mounts `/data` (f2fs) without falling back to the ext4 entry.
4. Record results here and in the investigation doc; only then evaluate the
   qseecomd port as the next blocker.

## 7. 2026-10-05 evening tests; 2026-10-06 diagnosis corrections

### USB serial capture now fully works

- Root causes of the 8,192-byte cutoff, in order found:
  1. `write_all()` abandoned a nonblocking sink after one 1 s `poll()`.
  2. Worse: with the ACM port unopened the gadget side reports `POLLHUP`,
     so that single `poll()` returned instantly without `POLLOUT` — the
     "30 s patience" never waited. Fixed by polling through HUP wakes until
     a real 30 s deadline (`scripts/initramfs-diag/init.c`).
  3. `wait_usb_configured()` (UDC `configured` state) gates streaming until
     the host binds CDC; `TIOCM_CAR` gating was tried and removed — the
     SELinux policy denies `TIOCMGET` on `ttyGS0` to our kernel-domain init
     (`avc: denied { ioctl } ioctlcmd=0x5415`, seen live in the v5 log).
  4. Late `/dev/kmsg` opens fail with ENOENT after init switch-roots; all
     kmsg fds are now opened at t~=1 s (pre-enforcing, where opens provably
     succeed) and inherited across forks.
- Result: v8+ streams the whole boot from second 0 over USB
  (`bootdevice8-usb-part1.log` 97 KB, `bootdevice9-usb-part1.log` 107 KB,
  `link11-usb-part1.log` 115 KB).

### Alias: missing links observed; creation failure not yet explained

- Earlier claims that ueventd only creates first-stage-required links were
  incorrect. AOSP `init/devices.cpp`, `DeviceHandler::GetBlockDeviceSymlinks`
  and `HandleDevice`, revision `a3b721a32242006b59cb12bd62c9133632af3a2d`,
  attempt links for handled named partitions.
- A successful `symlink()` does not prove its target resolves. In v11,
  the vendor wait for `/dev/block/platform/soc/../..` still times out.
  The intermediate `soc` directory must exist even for `..` traversal.
- v10 probe (`/dev/block/by-name/userdata` ro-mounted at `/mnt/probe_top`
  with `first_stage_mount`): **mounted f2fs successfully**
  (`mmcblk1p49`, checkpoint replayed). This proves that specific mount
  path worked, not general fscrypt health or safe concurrent fsck.
- v11 (`emmc`-type lines) changed nothing: AOSP `first_stage_mount.cpp`
  skips `emmc` entries in the mount loop and they only feed vbmeta probing
  — `emmc` can never force general device-link creation. Discarded.
- The proposed real-type throwaway mounts are withdrawn: the separate
  vendor fstab still runs fsck on userdata/persist. Skipping first-stage
  entries does not prevent checking the same filesystem mounted elsewhere.
  Valid magic alone does not establish safety.
- Images (all `../ack-boot-test/`, kernel+DTB `50bea980...` throughout):
  `boot-ack-android-bootdevice{7,8,9}-capture.img`,
  `boot-ack-android-probe10-devmap.img` (SHA256 `a73bc812...`),
  `boot-ack-android-link11-devices.img` (SHA256 `fd31eb0e...`).
  Durable logs: `ack-android-bootdevice5-capture-logdump.{bin,log}`,
  `ack-android-probe10-logdump.{bin,log}` (raw SHA256 `235d9af9...`).

### Other findings

- MMC numbering flips: stock eMMC=`mmcblk0` (recovery reads correct);
  under ACK eMMC=`mmcblk1` (system_a=`mmcblk1p25`, userdata=`mmcblk1p49`).
  `by-name` paths insulate all test logic; never address raw `mmcblkN`.
- `edt_ft5x06 1-0038: probe failed -110` is real but peripheral-only, not
  boot-blocking; home is the 4.19 DT/regulator port, after boot.
- The saved GPT inventory contains 51 partitions and no `metadata`.
  Captured vendor fstab has no `/metadata` entry; a nonexistent block
  device cannot fix the read-only `/metadata` errors.
- Next blocker after mounts: `vendor.qseecomd` exit 255
  (`vendor.sys.listeners.registered` never set). 4.19 port options, cheapest
  first: DT `soc@0`->`soc` rename (needs DTB rebuild); `drivers/misc/
  qseecom.c` port (medium-large); ION resurrection (large, defer until
  proven needed — 255 may be only the missing `/dev/qseecom` node).
- Constraint: attach the USB host within ~60 s of boot; post-enforcing
  opens of new nodes from the kernel domain are unvalidated (policy has
  read/write but no `open` on device nodes).

### Phone state overnight

v11's full durable log was retrieved through the temporary recovery reader
on 2026-10-06: `../ack-boot-test/ack-android-link11-logdump.{bin,log}`.
Partition SHA256:
`4359c40c458b2c1bcb96c363eb7987786563483aa4cd5200b66aed6507d610a3`.
The text has 148,487 bytes and the recorder EOF marker.

- init fails relabeling `/dev/block/mmcblk1p1`; ueventd sees `tmpfs` and
  receives `getattr`/`setattr` denials.
- ueventd reports creating `/dev/block/platform/soc@0/7824900.mmc` failed
  with `EAGAIN`. The precise cause remains unverified.
- Installed vendor file contexts label `mmcblk1p1` as `sd_device`, while
  ACK enumerates `modem_a` there. Platform partition contexts still use
  `soc/7824900.sdhci`.
- ACK tissot DTS lacks `iovcc-supply`; the log confirms a dummy regulator.
  Vendor tissot's inherited Focaltech node uses `pm8953_l6` for I/O power.
  ACK's driver already asserts active-low reset then releases it and waits
  300 ms. Checked ACK `android16-6.12` commit `3a7d1771d4925a56f7eeb8a5ba1faff0c544a9ef`
  and vendor source commit `531cf5c373d7f65dcba19342030762c54c04f8f1`.

Approved next test: read-only block-path snapshots from Android's current
root after coldboot, using the existing recorder's pre-opened kmsg writer.
No probe mounts, SELinux remains enforcing, kernel/DTB unchanged.
Phone is in temporary recovery; the evidence-only system mount was unmounted.

### Snapshot12 preparation

- `scripts/initramfs-diag/init.c` now forks a read-only observer that
  attempts to enter PID 1's mount namespace/current root at uptime 75 s.
  It logs block-directory entries, device numbers, symlink targets,
  resolution errors and SELinux labels at 75 s and 105 s. Any namespace,
  root or filesystem access denial is logged with its operation and errno.
- Host smoke run exercised actual filesystem reads: a resolving symlink
  reports `stat_errno=0`, a dangling symlink reports `stat_errno=2`, and
  a missing directory reports both `lstat_errno=2` and `opendir_errno=2`.
  Throwaway smoke files removed.
- Static AArch64 diagnostic init compiled with NDK 29 clang, `-Os -Wall
  -Wextra -Werror -DANDROID_CAPTURE`; no kernel build.
- Image: `../ack-boot-test/boot-ack-android-snapshot12-capture.img`,
  34,146,304 bytes, SHA256
  `7952f600abc0442fa5c206fc690f582113c1d60b30ee92dc2f5b0c42679abbe6`.
- Preservation checks passed against v11: kernel/DTB, command line and
  every ramdisk record unchanged except `/init` and restoring the original
  first-stage fstab (removing the four ineffective `emmc` additions).
  Boot-header SHA1 verified. No new probe mounts or SELinux relaxation.
- Temporary `fastboot boot` succeeded (send and boot both OK). The host
  sees `18d1:9008` with both interfaces bound to `cdc_acm`, serial node
  `/dev/ttyACM10`. Host ACL was granted; open now succeeds. A 25 s serial
  read received only 1,733 bytes of early kernel records, with no observer
  result. Saved as `android-policy-capture/snapshot12-usb-part1.log` under
  `../ack-boot-test/`. This does not establish the Android observer outcome.
- Recovery reader temporarily booted successfully; full durable partition
  retrieved through recovery ADB. Phone is now in recovery.

### Snapshot12 exercised result

- Saved `../ack-boot-test/ack-android-snapshot12-logdump.{bin,log}`.
  Raw partition SHA256:
  `3295e0d5264e82ae524e97d96002f3edb065c80397b9d0428ecba891e56d0902`.
  Current decoded capture is 120,090 bytes, ending at the first recorder
  EOF marker. Data after that marker belongs to the previous partition
  contents and is excluded from the decoded current log.
- Exact diagnostic blocker at uptime 75.755600 s:
  `DIAG: block observer step=open mount namespace failed errno=2`.
  The observer could not open `/proc/1/ns/mnt`; it never reached `setns`,
  chroot or the block-directory snapshots. No link/label result inferred.
- SELinux switched to enforcing at uptime 62.815540 s.
  ueventd coldboot completed at 73.578116 s.
- Vendor `mount_all` still skipped userdata (both filesystem entries),
  persist, dsp and modem_a. `vendor.qseecomd` continued exiting with 255.
- Earlier v11 labeling/EAGAIN messages are not present in this current
  capture; do not carry them forward from stale partition tail records.
- Procfs-fd correction approved and implemented after this test: observer
  opens `/proc` before its 75 s wait, retains the directory fd, and uses
  `openat()` for `1/ns/mnt` and `1/root`. The fd is closed on success and
  failure. This corrected source has not been boot-tested on the phone.

### Procfs-fd correction verification

- Host smoke exercised the actual observer against a procfs fixture whose
  pathname was renamed immediately after opening its directory fd.
  Absolute namespace lookup failed with ENOENT; the corrected observer
  successfully opened the namespace and root through the retained fd,
  then reported `step=setns failed errno=1` under host restrictions.
  This proves descriptor-relative access survives pathname removal, not
  that Android SELinux permits later `openat`, `setns` or chroot.
- Static AArch64 diagnostic init compiled with NDK 29 clang,
  `-Os -Wall -Wextra -Werror -DANDROID_CAPTURE`. Throwaway smoke artifacts
  removed. No kernel build, new boot image or phone boot in this correction.
- Snapshot12 remains the latest on-device evidence. The original ENOENT
  cause is still unverified; another temporary boot is needed to determine
  whether the correction reaches snapshots or a subsequent access denial.

## 8. Fedora build and snapshot13 image preparation

- User completed a Fedora VM kernel build. The first Mac working-tree copy
  lacked case-colliding files (`xt_DSCP.c` and `xt_dscp.c`); exporting Git
  objects with `git archive HEAD` to the Linux filesystem restored them.
  Fedora also needed `elfutils-devel` for `gendwarfksyms`. A separate config
  selects SHA-256 module signatures after OpenSSL rejected SHA-1 generation.
- Retrieved build artifacts are under `../porting/artifacts/fedora-build/`.
  Build log identifies `6.12.93-4k`, Fedora clang/LLD 22.1.8. Gzip integrity,
  Xiaomi Mi A1 DTB model and exact kernel-plus-DTB concatenation verified.
  Combined kernel/DTB SHA256:
  `4ed94784ea5d2ec7fc104fdf7b2043807f83d82477b053d6d6613bef45aeacf2`.
- Phone is running installed 4.19.325, slot `_a`, boot completed and SELinux
  enforcing. Magisk root enabled read-only extraction of `boot_a` to
  `../porting/artifacts/boot-running-slot-a.img` (67,108,864 bytes).
  Local SHA256 matches the partition:
  `dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc`.
- Prepared `../porting/artifacts/boot-ack-fedora-snapshot13-capture.img`,
  34,990,080 bytes, SHA256
  `cb482824c82a170b3a86156d168cd0dc24fd7fca5c268d3ad79147c4e691f960`.
  Boot-header SHA1 was recalculated and independently verified. Header v0,
  2 KiB pages, addresses and OS metadata preserved. Kernel is exactly the
  transferred Fedora kernel/DTB. All 660 original ramdisk entries and
  metadata preserved except `/init`, replaced by the corrected static
  AArch64 capture wrapper. Original Android `/system/bin/init` and fstab
  unchanged. Magisk backup/overlay records remain but its `/init` is bypassed.
- Added only `/force_debuggable` and `/userdebug_plat_sepolicy.cil`; policy is
  the installed platform CIL plus the two rules documented in section 15 of
  the investigation. Full installed policy inputs compiled with `secilc`,
  policy version 30, exit zero. No policy was loaded. SELinux remains enforcing.
  `/proc/cmdline` reports `verifiedbootstate=orange`; Android properties
  report green/locked and are not reliable evidence of the raw boot state.
- Command line retains snapshot12's `androidboot.bootdevice=../..`,
  `androidboot.boot_devices=soc@0/7824900.mmc`, force-normal-boot and logging/
  watchdog arguments. No alias repair, probe mounts or qseecomd bypass added.
- A throwaway AArch64 harness exercised the actual corrected observer on
  installed Android: procfs-relative opens, `setns`, chroot, two directory
  snapshots, symlink resolution and SELinux-label reads succeeded under
  Magisk root. This does not prove access in the ACK boot's kernel domain or
  across first-stage root teardown. Harness and phone policy-check scratch
  files removed. Static wrapper compiled with NDK 29 and warnings as errors.
- No reboot, boot-image flashing or temporary ACK boot performed. Snapshot12
  remains the latest ACK boot evidence. Snapshot13 is prepared, not boot-proven.
  The diagnostic recorder will overwrite `logdump` when booted. Vendor fstab
  still has a formattable ext4 userdata fallback: temporary boot is not a
  guarantee against filesystem writes/data loss. Fedora compiler/config and
  the current installed ramdisk also differ from snapshot12's inputs.

## 9. Snapshot13 temporary boot and macOS serial capture

- User approved the temporary boot after the logdump/userdata risks were
  stated. Preboot `logdump` was read in full to
  `../porting/artifacts/logdump-before-snapshot13.bin`; its 64 MiB SHA256
  matches snapshot12: `3295e0d5264e82ae524e97d96002f3edb065c80397b9d0428ecba891e56d0902`.
  Installed `boot_a` still matched the saved boot image before reboot.
- Fastboot confirmed `current-slot: a` and `unlocked: yes`. Temporary
  `fastboot boot` of snapshot13 returned sending/booting OKAY. No flashing.
- macOS bound the CDC-ACM gadget `18d1:9008`, serial `tissot-diag`, as
  `/dev/cu.usbmodemtissot_diag1`. A watcher started before reboot and opened
  only that USB identity, with raw termios and DTR/RTS asserted.
- Saved `../porting/artifacts/snapshot13-macos-usb.log`, 90,613 bytes,
  SHA256 `b8d1dbfedcd8fb742d73089dd77b4fc67ef4aa65e64cb3129a7416ea06a58620`.
  Contains 892 kernel records, sequence 0–891 without gaps, ending at
  95.352278 s. No USB recorder EOF. Host read failed with errno 6
  (Device not configured), then reopened the serial node but received no
  additional bytes before the 430 s host deadline. This is a partial capture,
  not evidence that Android stopped at 95 s.
- Capture confirms Fedora `6.12.93-4k` booted; SELinux enforcing at
  51.670971 s and ueventd coldboot complete at 67.158787 s.
- Corrected observer failed at 75.187908 s with errno 13 opening PID 1's
  mount namespace. The adjacent AVC identifies `{ search } on PID 1's
  proc directory: source `u:r:kernel:s0`, target `u:r:init:s0`, class `dir`,
  `permissive=0`. Unlike snapshot12's ENOENT, this provides a concrete
  SELinux denial. No block-directory snapshots were collected.
- Legacy alias wait still timed out; userdata was skipped at 94.803428 s.
  Serial ended before later mount/qseecomd results, so those outcomes are
  not established for this boot. Full current durable logdump not retrieved.
- Host receiver exited normally and closed its port. No target-phone ADB
  appeared in the post-capture device list. Last observed target USB state
  was the diagnostic serial gadget. No recovery boot or reset performed.
  Root ADB in a working recovery can read `by-name/logdump` without an ACK
  recovery kernel; modifying OrangeFox is not inherently required.

### Snapshot13 full durable retrieval from recovery

- User returned the phone to recovery. Root ADB works with recovery kernel
  `4.9.337-perf-g742a6fa7e89d`; no recovery modification was needed.
  Read `/dev/block/by-name/logdump` directly without mounting filesystems.
- Saved `../porting/artifacts/ack-android-snapshot13-logdump.bin`, full
  67,108,864 bytes. SHA256 matches recovery's partition read:
  `f845975169cab1b8e1dfe3a353072a804fead9dc3b3c3a6acf00bb759a4816d7`.
- Decoded `../porting/artifacts/ack-android-snapshot13-logdump.log` ends at
  the first recorder EOF marker: 113,669 bytes, 1,120 records, sequence
  0–1119 without gaps, through 331.203061 s. Decoded SHA256:
  `1bd43626c8d3488e0eae0cfc6dbcc591c872f1e73f22533d465655b307cc3cd1`.
  All 892 serial records match the durable prefix exactly. Stale partition
  tail excluded. No kernel panic appears in the current decoded capture.
- Full log confirms both userdata entries, persist, dsp and modem_a skipped;
  early mount_all returned at 174.851808 s after 100,099 ms.
  `vendor.qseecomd` exited 255 32 times, 175.583771–331.200324 s; no late-fs
  action observed. Init kept scheduling services after the serial cutoff.
- Observer SELinux denial remains unchanged; no block snapshots. Next
  diagnostic policy experiment should address the evidenced PID 1 proc-dir
  search denial while keeping enforcing, then report any subsequent denial.
  No additional policy/image changes or boot attempted during retrieval.
- Phone remains in recovery with root ADB. No partition writes, mount
  commands, reboot or flashing performed by the retrieval.

## 10. Snapshot14: single proc-directory search rule

- Added exactly `(allow kernel init (dir (search)))` to snapshot13's
  diagnostic platform CIL. No other policy allowances, permissive domains,
  kernel/DTB, observer, fstab or command-line changes.
- Recovery's 4.9 kernel could not execute the installed policy compiler:
  bootstrap runtime aborted on `MADV_WIPEONFORK`. The temporary system_a
  mount used `ro,noload` and was unmounted. Returned to installed 4.19
  Android; full policy compiled with installed secilc, version 30, exit zero,
  without loading it. Validation scratch files removed. Snapshot13's live
  logdump hash still matched the saved raw capture before the next boot.
- Image `../porting/artifacts/boot-ack-fedora-snapshot14-proc-search.img`,
  34,990,080 bytes, SHA256
  `d6d6a7b75746680a27ca199d781c3d1f2a83b403897edec0df60bfe9ed77c05d`.
  Boot-header SHA1 `1d1276c02f33138f631981a9d1c84a60f2ecf8fb`.
  Independent parser verified the only changed ramdisk entry is the policy,
  differing by that one rule; all other inputs preserved. Temporary
  fastboot boot succeeded on slot a. No flashing.
- Initial Mac watcher exited on an ioreg USB-removal race before capturing
  bytes. Discovery now retries reported transient ioreg errors. Restarted
  watcher opened `/dev/cu.usbmodemtissot_diag1` and streamed to completion.
- Saved `../porting/artifacts/snapshot14-macos-usb-resumed.log`, 121,632 bytes,
  SHA256 `bc90a5ff7cf6a23c8bded2e6a102de901259f322af5dd6c2ede8b61cb4f8188a`.
  1,183 records, sequence 0–1182 without gaps, through 389.929005 s, with
  `DIAG: EOF Android USB kmsg dump complete`. Receiver exited normally and
  closed its fd. Empty initial log and temporary watcher removed.
- Modified userdebug policy was selected; enforcing at 74.934523 s.
  Observer still failed `open mount namespace` with errno 13 at 75.751222 s.
  No block snapshots or observer-specific AVC captured. At 80.595662 s
  kauditd reports 31 suppressed callbacks; audit suppression is a possible
  reason the next permission denial is not visible, not proof of its class.
  kdevtmpfs directory-write denials are present but are not observer AVCs.
- Alias wait still timed out. Both userdata entries, persist, dsp and modem_a
  skipped. Early mount_all returned at 202.766814 s after 100,232 ms.
  qseecomd exited 255 38 times, 204.563834–389.926570 s; no late-fs action
  or kernel panic observed. Android init remained active throughout capture.
- Next diagnostic experiment: delay observer past the first-stage policy/
  init audit burst to obtain an attributable denial, rather than guess more
  policy permissions. That timing change has not been implemented or booted.
  Snapshot14 durable raw logdump has not been retrieved. Last target state
  was ACK serial gadget; no target ADB after capture, no recovery reboot.

### Snapshot14 durable retrieval and delayed-observer preparation

- User returned phone to recovery. Root ADB read full logdump to
  `../porting/artifacts/ack-android-snapshot14-logdump.bin`, 67,108,864 bytes.
  SHA256 matches recovery partition:
  `3d19a2319527040f6e9a7aaccf96f61840d42d46c3dc907900d0065629b3128f`.
- Decoded current capture ends at first storage-recorder EOF:
  `../porting/artifacts/ack-android-snapshot14-logdump.log`, 114,130 bytes,
  SHA256 `da96163abbeb4945d4cbb94fbc525880373b2da0ab4066dcf2a65aa37d79cc74`.
  Records 0–1103 without gaps through 329.462720 s. Every durable record
  matches the corresponding USB prefix; USB continues longer because its
  recorder starts later. Storage capture has 25 qseecomd exit-255 events.
  No observer-specific AVC was recovered; namespace EACCES and audit
  suppression remain the only attributable observer evidence.
- `scripts/initramfs-diag/init.c` now uses one `first_snapshot = 120`
  constant for namespace entry and samples at 120/150 s.
  A throwaway static AArch64 harness with synthetic time exercised actual
  namespace/root entry and block-directory reads in enforcing recovery:
  before change, snapshots at 75/105; after change, 120/150, both completed.
  This tests scheduling and read paths, not ACK kernel-domain permissions.
  Harness files removed from host and recovery.
- Updated static init compiled with NDK 29, warnings as errors, to
  `../porting/artifacts/fedora-build/snapshot15-diag-init`. No snapshot15
  image or boot yet. Phone remains in recovery; retrieval made no mounts.
- User additionally requested bootdevice creation, broader init-directory
  read permissions, mount verification, and a repacked test image.
  Alias creation must occur in Android's namespace, not the recorder's
  private namespace, and must handle an existing dangling alias.
  Enabling mount attempts requires addressing the formattable ext4 fallback.
  GPT has neither cache nor metadata partitions and vendor fstab supplies
  neither mount: writable backing for those paths is a separate decision.
  No alias creation or broader policy change implemented at this point.

## 11. Snapshot15: guarded f2fs-only mount probe

- User selected a protected temporary fstab with no ext4 userdata fallback;
  installed ROM fstab remains unchanged. Cache/metadata acceptance is reported
  as unsupported backing, not replaced with synthetic mounts.
- `scripts/initramfs-diag/init.c` now forks an early guard with an input fd
  opened before Android switch-root deletes the ramdisk pathname. The guard
  joins PID 1's mount namespace/root, validates exactly one f2fs `/data` entry
  and no `formattable`, copies the input into Android's ephemeral `/dev`, and
  bind-mounts it read-only over `/vendor/etc/fstab.qcom`.
- Guard permits installation only while `/proc/self/attr/current` returns the
  initial NUL-terminated `kernel` SID, including after the bind. ACK source
  `security/selinux/ss/services.c` documents this pre-initialization contract.
  Do not use `status.policyload == 0`: an actual recovery mmap returned zero
  even with an enforcing loaded policy. Direct fd bind probes also showed
  that unlinked/foreign-namespace sources are unsuitable; copying into
  Android's current namespace avoids those failures.
- Only after the verified guard does it atomically install
  `/dev/block/bootdevice -> /dev/block/platform/soc@0/7824900.mmc`, repairing
  existing dangling symlinks but refusing regular files. It then provides the
  missing `/dev/block/platform/soc` intermediate directory for the installed
  `soc/${ro.boot.bootdevice}` wait, keeping `bootdevice=../..` unchanged.
  Failed guarding never enables the canonical alias. Observer remains
  read-only, with samples scheduled at 120/150 s; enforcement is not changed.
- Actual root recovery smoke exercised the production helpers in a private
  mount namespace: loaded-policy refusal without mutation; rejection of
  formattable, ext4, duplicate and missing userdata entries; read-only bind
  from a retained deleted input fd; atomic dangling-alias repair; regular-file
  preservation. The positive pre-policy context was synthetic; this does not
  establish early ACK timing or successful Android mounts.
- Final static AArch64 init compiled using NDK 29 Darwin clang with
  `-static -Os -Wall -Wextra -Werror -DANDROID_CAPTURE`; ELF64 AArch64 and
  absence of PT_INTERP verified. Final debug CIL adds
  `(allow kernel init (dir (search read open getattr)))` to the existing two
  recorder device rules.
- Rebooted installed 4.19.325 Android to run its compatible secilc runtime.
  Full installed platform/mapping/system_ext/product/vendor input set compiled
  with exit status 0, without loading the policy. Compiled policy:
  `../porting/artifacts/fedora-build/snapshot15-policy.bin`, 1,330,019 bytes,
  SHA256 `d7ceafd2e8c3f4a7e671e7f32e08729aba0719be617807c325e6001fa4628fc1`.
- Repacked `../porting/artifacts/boot-ack-fedora-snapshot15-protected-mounts.img`,
  34,988,032 bytes; SHA256
  `f880e6f21aac6a3d9ba2d5970c41e8f9ccbe63068994613fb53b4d50670af729`.
  Boot v0/page 2048; header SHA1 `90c9a53bcfb76dff653f9415b11745039dad37a2`.
  Kernel/DTB/cmdline and every unaffected ramdisk entry/metadata unchanged from
  snapshot14. Replaces init and debug CIL; adds only `ack-protected-fstab.qcom`.
- Snapshot15 temporarily booted successfully, slot a, without flashing.
  Guard installed at 22.693153 s; canonical alias/wait path ready at
  22.694330 s; SELinux enforcing at 50.987320 s.
- Actual mount acceptance passed: userdata f2fs at 76.371956 s, persist ext4
  at 76.962713 s, dsp ext4 at 76.977400 s, modem_a vfat at 76.988458 s.
  Early mount_all succeeded in 1,392 ms without the prior block wait timeout.
  No ext4 userdata fallback exists in the protected fstab.
- USB capture `../porting/artifacts/snapshot15-macos-usb.log`: 147,954 bytes,
  SHA256 `75905fe77f587f3723b724de55ce063a9477643f8328a01ec85515f0c3fb05b2`,
  records 0–1354 without gaps through 322.056343 s, with USB EOF.
- Delayed observer produced an attributable denial at 120.978135 s:
  kernel -> init, `lnk_file { read }`, name `mnt`. Directory permissions
  alone do not authorize the namespace symlink. No directory snapshots.
- Remaining evidence: vold cannot read the temporary fstab inode labeled
  tmpfs; this diagnostic overlay needs correct labeling for the next probe.
  qseecomd exited 255 49 times, with tee/block_device read/write denials on
  mmcblk1p4. /cache/lost+found failed with required key unavailable;
  /metadata directories failed on read-only backing. No synthetic mounts.
- At user's request, temporarily booted
  `../OrangeFox-R11.3_1-tissot/recovery.img` using fastboot boot. Root ADB,
  kernel `4.9.337-perf-g742a6fa7e89d`. Full durable logdump saved and checked
  against the recovery partition hash:
  `../porting/artifacts/ack-android-snapshot15-logdump.bin`, 67,108,864 bytes,
  SHA256 `bf80e809224a177ecf0a03384001d4439763cbb76bb2bbd5b7f5977f4d871389`.
  Decoded `.log`: 147,170 bytes, SHA256
  `a9e742793b849cb92bb64ac8429ba1a2cb43489c565b97a9da9e3638f1c8416d`,
  records 0–1348 without gaps through 320.773396 s, storage EOF.
  Every durable record matches the USB prefix. Phone remains in OrangeFox.

## 12. Legacy ION + `/dev/qseecom` port (built; startup not proven)

- Restored `include/uapi/linux/{ion,msm_ion,qseecom}.h` verbatim from
  `kernel_xiaomi_msm8953` (pinned ABI: `ION_IOC_MAGIC 'I'`, ALLOC nr 0,
  HEAP_QUERY nr 8, `TARGET_ION_ABI_VERSION 2`, MSM nrs 3/4, heap IDs
  14/19/20/26/28, `QSEECOM_IOC_MAGIC 0x97`); plus donor wrapper
  `include/linux/ion_kernel.h`.
- Ported `drivers/staging/android/ion/` in-tree (same relative path):
  6.12 `shrinker_alloc`+`shrinker_register`, 6.12 `dma_buf_ops`
  (iosys_map vmap), system+CMA heaps functional, carveout/chunk/secure
  creates `-ENODEV`+`pr_info_once`, `secure_buffer` calls stubbed
  `-ENODEV`, `compat_ioctl` + legacy nrs 0/1/2/4/5 kept,
  unhandled `-ENOIOCTLCMD`, `misc_register` name `"ion"`.
- Ported `drivers/misc/qseecom{,_kernel.h,_compat.h,compat_qseecom.c}`:
  full `0x97` dispatch incl. 64-bit + QTEEC + CE-pipe nrs, same-switch
  `compat_ioctl`, unknown `-ENOIOCTLCMD`, transport on ACK
  `__scm_smc_call` via new `include/soc/qcom/scm.h` shim
  (`qcom_scm_remap_error` errno propagation), bus scaling no-op 0,
  CE/ICE/key `-ENODEV`+`pr_debug`, `class_create()` 1-arg,
  `misc_register`/`compatible` `"qcom,qseecom"`.
- DT: `qcom_seecom: qseecom@84a00000` added in `msm8953.dtsi`
  (`secapp-region` 0x84A00000/0x1900000 = tissot `qseecom_mem`;
  `qcom,msm-bus/*` stripped; `no-clock-support` set since clocks are
  firmware-owned). Booted `msm8953-xiaomi-tissot.dtb` includes this dtsi.
- Kconfig/Makefile wired (`ION`, `QSEECOM`); new device fragment
  `arch/arm64/configs/tissot_gki.fragment`
  (`ION/ION_LEGACY/ION_SYSTEM_HEAP/ION_CMA_HEAP/QSEECOM=y`, built-in:
  qseecomd starts at post-fs). `gki_defconfig` untouched. Merge over the
  known-working snapshot15 Fedora config, which already has QCOM_SCM,
  DMA_CMA and STAGING built in; do not substitute the native QCOM_QSEECOM.
- Static acceptance holds: zero banned includes, all port includes
  resolve, no duplicate Kconfig symbols, secure-mask ALLOC fails
  `-ENODEV` by construction (`ion_alloc_dmabuf` NULL-heap path).
- NOT YET DONE (needs Fedora VM + device): kernel build with the
  fragment (`CONFIG_ION=y`, `CONFIG_QSEECOM=y`, `ion.o`+`qseecom.o`),
  temporary boot PASS (`/dev/qseecom 0660 system drmrpc`,
  `/dev/ion 0664 system system`, no qseecomd-255 loop,
  `vendor.sys.listeners.registered=true`, `late-fs` reached).
- Next-test configuration check found ION silently disabled by its obsolete
  `HAVE_MEMBLOCK` dependency, absent in ACK 6.12. Removed that dependency,
  keeping HAS_DMA/MMU. Actual olddefconfig now retains
  ION/ION_LEGACY/ION_SYSTEM_HEAP/ION_CMA_HEAP/QSEECOM plus
  QCOM_SCM/DMA_CMA/STAGING/COMPAT as built-in.
- Prepared and verified `../porting/artifacts/qseecom-next-test-overlay.tar.gz`,
  170,215 bytes, 41 source/config files plus the known-working base config
  and checksum manifest. SHA256
  `53cdbb1d109cceb9bf5ebf0690e8ffbd0fd43842724bcb82c820b243b5368061`.
  Includes driver, compatibility code, legacy ION subtree, ABI headers,
  DT and Kconfig/Makefile wiring. Excludes Mac case-colliding netfilter files.
  User requested transfer/build commands and will compile on Fedora.
  No kernel binary with this driver has been built or booted yet.
- User's first Fedora rebuild stopped during UAPI header installation, before
  Image.gz-dtb creation. Fetched `../porting/artifacts/qseecom-build/.config`
  and `build-qseecom.log`; log reports missing `WITH Linux-syscall-note`
  on `include/uapi/linux/{ion,msm_ion}.h`. No rebuilt kernel was fetched.
- Added the syscall-note annotation to those two SPDX lines only; header
  bodies, ABI declarations and copyright text are unchanged. Actual kernel
  `headers_install.sh` with compiled unifdef and GNU sed passed for ion,
  msm_ion and qseecom headers. BSD sed on Mac/OrangeFox was unsuitable for
  the Linux export script; installed GNU sed on Mac for the smoke.
- Incremental VM fix:
  `../porting/artifacts/qseecom-uapi-spdx-fix.tar.gz`, 4,896 bytes, SHA256
  `3e3160c45f5e56b2f05e9e7b9f70714c1121ad81395a80dfabdc623f0b90a195`.
  Contains only the two corrected headers and updated source manifest.
  Full source overlay also refreshed: 170,220 bytes, SHA256
  `e13461c666886d8cd968ae628c325e3d4fbe65ec8ae3d82de8a832212afca71c`.
  Resume the existing out-qseecom build; do not reset its config or clean.
  Full kernel compile/link and driver runtime remain unverified.
- Next fetched build passed the SPDX/header-export stage, but failed compiling
  drivers/misc/qseecom.o: missing protocol constants and incomplete request
  structs. qseecom.c omitted `soc/qcom/qseecomi.h`, which defines the reported
  symbols. Restored that include; a throwaway Clang -Werror protocol smoke
  compiled and ran using the real protocol header and exported Linux types.
  This is not a full kernel/object compilation result.
- Fetched Image.gz-dtb is invalid for boot: exactly 39,880 bytes, FDT magic
  d00dfeed and DTB total-size 39,880; it contains no gzip kernel.
  Do not repack/boot it. Build completion and gzip validation must precede
  concatenation; run the Fedora steps in one fail-fast bash script.
- Incremental correction `../porting/artifacts/qseecom-protocol-include-fix.tar.gz`
  contains the corrected driver and updated source manifest, 50,756 bytes,
  SHA256 `2c00f87cf800e00a2bf8e13846dd7414d969abd689938e2d07e672013d616745`.
  Full source overlay refreshed again: 170,227 bytes, SHA256
  `55018129f069c66871968f380927496f4a1b1c4685538c6ff3c4de112bc08aa2`.
  Full kernel build and driver runtime remain pending Fedora/device evidence.

## 13. Snapshot16 rebuilt-kernel test and early-startup failure

- User reported Fedora build success and fetched a real Image.gz-dtb:
  16,936,518 bytes, SHA256
  `b4bd964e617892ccaf9e33b2d904a11050d35a5ecb4322152fa15f6ddfc5a108`.
  Gzip stream integrity passed; decompressed ARM64 Image is 42,527,232 bytes.
  Kernel identifies as 6.12.93-4k, Fedora Clang/LLD 22.1.8. Updated QSEECOM
  logging strings are present. Appended DTB is 39,880 bytes, root compatible
  xiaomi,tissot/qcom,msm8953, with qcom,qseecom node at soc@0/qseecom@84a00000.
  Config retains ION/ION_LEGACY/system+CMA heaps/QSEECOM/QCOM_SCM/COMPAT=y.
  Fetched log includes old failed runs and a short up-to-date run; binary
  validation, not absence of historical error lines, establishes payload format.
- Repacked `../porting/artifacts/boot-ack-fedora-snapshot16-qseecom.img`,
  35,072,000 bytes, SHA256
  `0211ed5764b3014a59ed6537f3d84b047e8d544dd28198a6bd18e95b7383153d`.
  Boot v0/page 2048; header SHA1 63155df2ceac52fd33e55d6c33ee7ab4ab1dddfc.
  Snapshot15 ramdisk byte-identical (SHA256
  c728916fd92e8dab95097d5b902e73cd91b0b91e4dd56fd3185a9bea66c19ff0);
  command line/load addresses/OS version preserved. No observer/fstab-label
  changes: isolate the rebuilt kernel, not multiple simultaneous changes.
- Target 2819f2320604 was in OrangeFox 4.9.337; current slot a, unlocked yes.
  Temporary fastboot boot returned Sending/Booting OKAY, but target then
  exposed no ADB/fastboot/diagnostic USB. User saw retained fastboot picture.
  `snapshot16-macos-usb.log` is empty; receiver stopped, no runtime claims.
- User physically returned target to fastboot; temporary OrangeFox boot
  succeeded. Recovery logdump SHA256 remained snapshot15's exact
  bf80e809224a177ecf0a03384001d4439763cbb76bb2bbd5b7f5977f4d871389.
  No snapshot16 diagnostic start marker was written; do not relabel old
  snapshot15 logs as new capture. Recovery exposed no files in /sys/fs/pstore.
  Failure is before recorder startup; bootloader handoff vs early kernel
  failure remains unresolved. QSEECOM/device permissions/mount outcomes unknown.
- Installed boot_a SHA256 before/after:
  dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc;
  partition 64 MiB. No flashing.
- Prepared and temporary-booted the isolation image
  `../porting/artifacts/boot-ack-fedora-snapshot16-qseecom-probe-disabled.img`,
  35,072,000 bytes, SHA256
  `c00868469d1539d0504f7c9749dec591ba29f049093a2c8e504a9bf3a4149cf2`.
  Compressed kernel and ramdisk unchanged; property-by-property DTB comparison
  found only qseecom node status=disabled added, plus dependent size/header ID.
  This diagnoses the device probe; it is not a QSEECOM fix or acceptance pass.
  Isolation capture completed with recorder EOF at 318.030848 seconds.
  `snapshot16-probe-disabled-macos-usb.log`: 140,839 bytes, SHA256
  `9efd6f34acc697d60db937b75995c66cc3e5686f06d3e87b32737ed2e4504c50`.
  First line truncated (part of sequence 12); complete records 13–1307 have
  no internal gaps. Need durable capture to recover missing early records.
  Receiver exited and closed the port.
- Disabling just QSEECOM's DT node restored kernel/Android init startup.
  This implicates its device-probe path, not packing or compressed kernel.
  Exact failing stage remains unknown; no driver fix or acceptance claimed.
  Source probe queries firmware in qseecom_init_control before DT/clock/bus
  setup and has no qcom_scm_is_available defer check; source-level candidates,
  not proven causes. Do not substitute stubs or disable QSEECOM as a fix.
- Isolation run: guard/alias ready at 18.982487/18.983570 s; SELinux policy
  loaded around 66.35 s. Userdata f2fs mounted at 86.729640 s, persist ext4
  87.757736 s, dsp ext4 87.813703 s, modem_a vfat 87.827825 s. Early mount_all
  succeeded in 5,706 ms. vold fstab labeling denial and observer mnt lnk_file
  read denial remain, as expected with unchanged ramdisk. qseecomd still exits
  255 with block-device labeling AVCs; QSEECOM disabled means no driver pass.
- User returned target to real fastboot; temporary OrangeFox boot succeeded.
  Pulled `ack-android-snapshot16-probe-disabled-logdump.bin`: 67,108,864 bytes,
  SHA256 `ac573e0e80228639cfa2f9187d81f73e28527a9cb4fb34feb5dce1557d3299a4`,
  matching recovery's partition checksum. ADB exec-out mixed dd's final
  82-byte status with stdout; excluded it only after the raw prefix matched
  the independent partition hash.
- Decoded `ack-android-snapshot16-probe-disabled-logdump.log`: 141,075 bytes,
  SHA256 `29147d59102dc56a8604c96ba9e6c3377c1680d041257b896b74b96ee538aea9`.
  Storage EOF present; complete records 0–1301, no gaps, through 315.003622 s.
  All 1,289 overlapping USB records 13–1301 are byte-identical. Early records
  now confirm 6.12.93-4k and Xiaomi Mi A1 at runtime, not merely binary strings.
- Recovery's pstore is mounted but empty; its DT ramoops reg is
  0x91400000/0x400000, whereas ACK uses 0x86800000/0x100000. Empty OrangeFox
  pstore therefore does not establish absence of ACK panic/console records.
  Need aligned persistence or post-recorder probe instrumentation to locate
  the failing operation; no guessed SCM/probe fix applied.
- boot_a still matches dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc.
  Phone remains in temporary OrangeFox 4.9.337; no flashing or active receiver.

## 14. Step2 kernels and early pstore-reader preparation

- User supplied enabled/disabled step2 kernel payloads, verified exactly:
  enabled 16,936,043 bytes, SHA256
  `e753763f553c3af49bf426f270632e18065391c1a684b0d949caaaba05c6f4fc`;
  disabled 16,936,068 bytes, SHA256
  `2e850af0985d8e38aa1cde6bc775bb3f679134a73f42469a54c31c7236b71f71`.
  Both gzip streams/ARM64 headers/DTBs validate. DTBs differ only by added
  qseecom status=disabled; raw kernels differ by 28 bytes (do not claim
  byte-identical binaries). Both use ramoops 0x86800000/1 MiB.
- Added read-only early pstore dumping to scripts/initramfs-diag/init.c:
  mount pstore MS_RDONLY in the recorder's private namespace; dump records
  to durable storage before Android handoff and independently to USB before
  kmsg streaming. Do not unlink records. Mark per-file begin/end, byte count
  and read errno; distinguish mount/open/readdir failure from zero files.
  Sink failure is reported without skipping the f2fs guard/alias setup.
- Real compiled AArch64 reader fixture smoke passed in OrangeFox:
  multi-buffer binary contents exact, repeated reads leave files unchanged,
  symlinks/nonregular entries excluded, empty/missing directory and mount
  error reported, /dev/full failure returned nonzero. Android static init
  compiled with NDK29 -Os -Wall -Wextra -Werror -DANDROID_CAPTURE.
  Reader binary SHA256 a8889f066d81267b6cd576864e78dcbd55e40a65a43b320ac23b365e4625dfbd.
  Temporary fixture directories/binary/harness removed.
- Prepared enabled boot image
  `boot-ack-fedora-snapshot17-qseecom-enabled-step2.img`, 35,072,000 bytes,
  SHA256 `0b8583c4cd61c6add64104a3ca9f6e16f6c97d29b162c6c5debcf15be436feae`;
  snapshot15 ramdisk byte-identical; new supplied enabled kernel only.
- Prepared disabled early-reader image
  `boot-ack-fedora-snapshot17-qseecom-disabled-pstore-reader-step2.img`,
  35,074,048 bytes, SHA256
  `ad5b9b84130bcad22ed5f125e512e31f39a8b0029339d2fb6be48b484e658196`.
  Of 664 CPIO entries, only init data/filesize changed; other contents,
  metadata, archive trailer, boot addresses/command line/OS version preserved.
- Before test boot_a still dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc;
  logdump still verified snapshot16 isolation ac573e0e...3299a4. No flashing.
- Enabled snapshot17 temporary boot accepted; unlike snapshot16, it reached
  kernel/Android init and produced records from sequence 0. QSEECOM queried
  QSEE version 0x1001000 at 3.098822 s and continued past unavailable legacy
  ION shmbridge warnings. Later qseecomd still exits 255 with tee read/write
  denied on mmcblk1p4 labeled block_device. This is not a driver acceptance
  pass. Capture completed with recorder EOF and 120 seconds final quiet;
  receiver exited and closed its port. Saved snapshot17-enabled-step2-macos-usb.log,
  154,650 bytes, SHA256
  df986aea593c15bb439a3304aa4ee16e9760c7d226af1a6152a3a7e6cb96d0c7.
  Complete records 0–1422 without gaps, through 378.930306 s. No kernel panic
  marker observed; qseecomd exited 255 60 times. This enabled run is not the
  previous early-startup hang; reader will test persistence of the current boot.
  Requested screen character (static vs redraw/reboot cycling) from user.
- Disabled snapshot17 reader was temporary-booted directly via fastboot;
  no OrangeFox/installed-ROM boot intervened. USB capture completed with
  EOF and 120 seconds final quiet: records 0–1437 without gaps through
  373.434803 s, 156,870 bytes, SHA256
  bdd287515e53ce741a65b45b7cb63745b57a0699ad500888b340a1123705fce7.
  Saved snapshot17-disabled-step2-pstore-macos-usb-continuation.log.
  USB pstore reports mount_errno=0, errno=2 (ENOENT), files=0. The late
  pathname was unavailable after Android root handoff; this is NOT genuine
  empty-pstore evidence. Storage invoked the reader before handoff and
  remains authoritative pending retrieval. Async-debug fallback not used.
- Corrected source takes one early snapshot into an anonymous devtmpfs
  file and maps it read-only; both storage and USB use inherited bytes,
  avoiding late path and file permission checks. Static NDK build passed
  -Os -Wall -Wextra -Werror. Corrected binary SHA256
  fbae5e1231c391cf0e1dee40486be74449c06e8edb63bd9cc1ba8c669038e685.
  Staged boot-ack-fedora-snapshot17b-qseecom-disabled-pstore-reader-step2.img,
  35,074,048 bytes, SHA256
  2c5e0605094a2032b4f77f7b74a7f9cf6d01241ea9b571543d912b2a0956928a.
  Snapshot15's other 663 CPIO entries/tail and boot fields preserved except
  kernel/ramdisk sizes and image ID. NOT booted; root-removal runtime smoke
  still pending. The completed capture used the original reader image.
- Target has diagnostic USB only. Need manual Power+Volume Down return
  to fastboot; AFTER the completed reader, temporary-boot OrangeFox to
  retrieve durable logdump and run the snapshot regression smoke. No flash.
- Manual Power+Volume Down return, then temporary OrangeFox boot (fastboot
  boot OKAY, root adb). logdump SHA256
  6d71db8e1c6b59819418beadcc1fc51944f2ad4083eb1df385aa7cea593df486,
  67,108,864 bytes; boot_a still
  dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc.
  No flashing; temporary recovery boot only.
- Reader durable decode: pstore scan ran pre-handoff with mount_errno=0,
  no read error and files=0, i.e. genuinely empty pstore, unlike the USB
  ENOENT. Records 0–1347 through 313.187226 s, EOF, byte-identical to the
  USB overlap. ack-android-snapshot17-disabled-step2-logdump.log
  146,499 bytes SHA256
  fb7d2d14f5abd4a492a31aa8e3cd8c8021907a5810600f5fae2342f3cca1f000;
  raw .bin saved. Async-debug fallback not needed and not copied.
- Snapshot correction verified on device under root Linux: early snapshot
  survives path removal (2 records read, symlink skipped, files=2,
  exit 0), late read reproduces the original errno=2/files=0 failure.
  Root-path loss was the cause. Throwaway harness and target fixtures
  removed after the run.
- Newly supplied display-otm1911 payload verified, NOT booted:
  17,447,466 bytes SHA256
  7ce2a2d91dcb18ac862f125cae3b71679f41063541c47ed1ca41512067201c7d,
  43,915,776 B Image + 40,294 B DTB, same 6.12.93-4k clang 22.1.8
  builder, built 15:56:58 vs step2 15:20:35. Display enabled: mdss@1a00000,
  mdp5@1a01000, dsi@1a94000, phy@1a94400 okay; secondary DSI disabled; new
  panel@0 with orisetech,otm1911, backlight and vdd supplies.
  QSEECOM driver absent (QSEECOM strings 0 vs 334, qseecom_ioctl 0 vs 3,
  of-match qcom,qseecom 0 vs 1, shmbridge 0 vs 7) though the DT node
  remains; this image cannot serve as QSEECOM acceptance.
  Panel node carries no timing properties (zero qcom,mdss-dsi-* in the DTB)
  and the driver carries no hardcoded on/off sequences, so blank or failed
  panel probe is as likely as success. DRM-style panel via generic DSI.
  Staged boot-ack-fedora-snapshot18-display-otm1911.img, 35,584,000 bytes,
  SHA256 be499f3a049413c4ba1c0739d73b4a654d0dd70003e627cc737427e0a738eedd;
  snapshot15 ramdisk byte-identical, command line and other header fields
  unchanged. Not booted, not flashed.
- Rebuilt display payload re-verified (SHA256 changed to
  2309edf161f1cfad49a879411931a490fe8105b4f0275654f5ebf50f512988a3,
  17,534,080 bytes, 44,112,384 B Image + 40,294 B DTB). QSEECOM driver is
  back: all 43 source literals present, zero missing vs step2-enabled;
  counts identical (QSEECOM 334, qseecom_ioctl 3, of-match 1, shmbridge 7).
  Display stack and orisetech,otm1911 panel unchanged; panel timing still
  absent (zero qcom,mdss-dsi-* in DTB, no hardcoded on/off sequences).
  Staged boot-ack-fedora-snapshot18b-display-otm1911-qseecom.img,
  35,670,016 bytes, SHA256
  82228b276ce6e97d475160ebf6dd6e4f01cb32c2a461420852c905b1d04888b7;
  snapshot15 ramdisk byte-identical, command line and other header fields
  unchanged. Supersedes snapshot18 (which lacked QSEECOM). NOT booted.
- Snapshot18b temporary boot completed: fastboot boot OKAY, USB capture
  finished with recorder EOF and 120 s final quiet. Records 0–1468 without
  gaps through 376.462112 s, 162,532 bytes, SHA256
  d6d4628bb08f55df9086d5dd9416b1448486215533154e8a2ecd45568054b908.
  Build #6 SMP PREEMPT 16:14:35 +0545. QSEECOM probed (qsee_version
  0x1001000, expected shmbridge warnings, no ion node). Display bound:
  msm_mdp bound 1a94000.dsi, MDP5 v1.16, [drm] Initialized msm 1.12.0,
  panel-otm1911 1080x1920@60 24bpp dsi 4dl ready at 2.36 s, no DSI errors
  after. Zero backlight/fb0/modeset lines: black screen is unlit panel plus
  no modeset client (console=ttynull, no fbcon), not a link failure.
  qseecomd exited 255 58 times on the tee denial, this run on mmcblk0p4
  (step2 runs showed mmcblk1p4; same denial class, different node).
  No kernel panic/oops (only cmdline mentions). No flashing.
  Next: backlight driver (or fixed-regulator stand-in) plus fbcon or a
  minimal modeset test to prove pixels; durable logdump retrieval still
  pending a fastboot return + temporary OrangeFox boot.
- Durable logdump retrieved via temporary OrangeFox (fastboot boot OKAY,
  root adb): 67,108,864 bytes SHA256
  6f300f35a90df3b3514c885dc5ee4aec86361309716d03ad9da06362b4abcaf3.
  boot_a still dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc.
  Decoded 152,208 bytes SHA256
  d5625dcadcfeb43b1f036fec48a0002b37123aa01c3bf1086bb9ceefbdab796b;
  records 0–1378, no gaps, EOF, byte-identical to USB overlap.
  (Snapshot15 ramdisk has no pre-handoff pstore dump; expected.) No flash.
- Snapshot18c temporary boot completed (build #8, wled+fbcon): fastboot
  boot OKAY, USB capture EOF + 120 s quiet. Records 0–1692 without gaps
  through 391.603354 s, 178,178 bytes, SHA256
  205f36af9fa1513db99acb892100118c6e879aed047995bf94ba93672235a403.
  fbcon modeset done: Console switching to colour frame buffer 135x120,
  fb0 msmdrmfb, panel-otm1911 1080x1920@60 24bpp dsi 4dl ready, all at
  ~18 s. Single mdp5_irq_error_handler 04000000 at 17.79 s, no recurrence;
  no DSI/panel errors after ready; no panic/oops. QSEECOM probed
  (0x1001000); qseecomd 58x exit 255 on tee denial (mmcblk0p4).
  Screen state (text vs glow vs dark) still needed from user. No flashing.
  Panel identity to be read from recovery dmesg + boot_a DTB, not the ROM.
- Durable 18c logdump retrieved via temporary OrangeFox: 67,108,864 bytes
  SHA256 68418cd8dfafd35c33db887c56bb3aefaa28f723a4259055cfabc38ce044b572.
  boot_a still dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc.
  Decoded 167,854 bytes SHA256
  653ebeed3b907809f9c3a85bcef237331c3bd63d9bb09c72811bd35421f1d5b9;
  records 0–1602, no gaps, EOF, byte-identical to USB overlap. No flash.
- Panel identity settled from recovery (no ROM boot): bootloader cmdline
  selects qcom,mdss_dsi_otm1911_fhd_video; recovery probes "otm1911 fhd
  video mode dsi panel" with DT timing and continuous splash. Glass is
  OTM1911; wrong-glass theory dead. Dark screen = backlight never lit:
  panel backlight resolves to pmi8950-wled (okay); WLED OVP work fires at
  18.07 s with "Unbalanced enable for IRQ 38" WARN, then no registration
  or brightness lines; aw2013 present but never logs a probe. Next kernel
  work is WLED-first (OVP IRQ handling + applied brightness), then pixels.
- New build #9 verified, staged, NOT booted: payload 17,665,109 bytes
  SHA256 969a2fdaed3707ea7311c819c94bc94c4ccc3e01f0630467fa37b108cbf5aea2,
  Image 44,395,008 B (same size as #8), DTB 40,294 B. QSEECOM full
  (43/43 literals, counts identical). Display stack, panel node, WLED
  node all unchanged; still zero mdss-dsi-* timing props and no DCS
  sequences. New: `default-brightness` parsing support in kernel
  (backlight framework plumbing), but no DT node sets it yet — runtime
  must show whether WLED probes and applies a brightness. Staged
  boot-ack-fedora-snapshot18d-display-wled-brightness.img, 35,801,088
  bytes, SHA256 40398e08e832bdb8ed737ac997f92fe2a58dd919c1e00ba43c6f5bbc63275635;
  snapshot15 ramdisk byte-identical. Not booted, not flashed.
- Snapshot18e permissive boot: fastboot boot OKAY. Panel status readback
  WON: `panel-otm1911: panel status 0x9c (downstream expects 0x9c)` — link
  alive, OTM1911 glass confirmed on-device. fbcon modeset + fb0 again.
  BUT the permissive test was inconclusive: init logged
  `enforcing=1 old_enforcing=0` at policy load — user-build init forces
  enforcing and ignores `androidboot.selinux=permissive`. qseecomd still
  exits 255 on the same tee denial (this boot mmcblk1p4 again — node name
  flips between boots, sepolicy must cover the label not the node). So the
  fork is unresolved: need permissive via a path user builds honor
  (userdebug init) or go straight at the ROM sepolicy label fix.
  Auto-updating log: snapshot18e-selinux-permissive-macos-usb.log.
- Durable 18e logdump retrieved via temporary OrangeFox: 67,108,864 bytes
  SHA256 38f8afb7dc004b68769f4807358ca6c1cd7e12f5d95c2b0eeaa3b6c70beec3c9.
  boot_a still dd00ffdddc7ba9ae5c1bd573d1b0a558c2df06bbef60690d29fd25cfefd399dc.
  Decoded 151,092 bytes SHA256
  15d40c682280ac48bbaeb5dddf12c20e071ea1efbbc97f4e8f104c2049c0a660;
  records 0–1390, no gaps, EOF, byte-identical to USB overlap. Durable copy
  confirms both panel status 0x9c and enforcing=1 old_enforcing=0. No flash.
- Snapshot18g post-mortem correction: the pclk-hang call was WRONG. The
  durable dump retrieved after is the 18g boot itself (cmdline carries the
  appended selinux=0): full run, records 0–1390, EOF at 316.55 s, panel
  0x9c, fbcon modeset, fb0, qseecomd 47x exit 255. The kernel survived the
  pclk RCG WARNs; only the USB live stream died at 3.79 s (gadget/streamer,
  not the kernel). No panic exists in any evidence; the later reboot cause
  is unknown (post-EOF). pclk RCG stays a dark-screen suspect, not a proven
  hang cause.
- selinux=0 had NO effect: enforcing=1 old_enforcing=0 stands, 72 avc
  denials with permissive=0. Reason, read in our own tree
  (security/selinux/hooks.c:139-148): the token needs
  CONFIG_SECURITY_SELINUX_BOOTPARAM, which defaults to n — runtime proves
  the Fedora build lacks it. Kernel-cmdline isolation is exhausted for this
  build config. Remaining fork paths: (a) Fedora rebuild with BOOTPARAM=y,
  (b) userdebug init honoring androidboot.selinux=permissive, (c) skip
  isolation, fix the ROM sepolicy label for tee on the rpmb node directly.
  Dumps renamed to the boots they are: snapshot18f-boot (enforcing full
  run) and snapshot18g-boot (selinux0-ignored full run). No flashing.
- Second-token theory refuted with full-line evidence. 18g cmdline audit
  (976 chars, 46 tokens, from durable record 58, not a truncated paste):
  selinux=0 at [6] and [24], zero enforcing= tokens anywhere,
  androidboot.veritymode=enforcing is verity (unrelated), Unknown-params
  line is ONLY buildvariant/dm. Recovery /proc/cmdline (816 chars) has no
  selinux token at all. No override exists; last-wins cannot fire.
  Ordering also verified in-tree (init/main.c): parse_args("Booting
  kernel") at :1077 runs __setup handlers incl. selinux=, security_init()
  reads .enabled at :1221. Handler present + token consumed + ordering
  correct + init ran anyway ⇒ the Fedora tree neuters the flag downstream
  of parse (vendor anti-tamper pattern) or wires .enabled differently.
  Asked builder to diff selinux_enabled_setup/.enabled vs upstream or send
  BOOTPARAM+DEVELOP config proof. Pragmatic paths unchanged: userdebug
  init, or straight to the ROM sepolicy label fix.
- Build #14 verified, staged, NOT booted: payload 17,664,739 bytes SHA256
  a26d699fd39ff9d846981055f8a8669d24d5272f75672e02072dc7411ff16d61
  (18:01:07, overwrote the debug-selinux0 filename). QSEECOM 43/43,
  display/panel/WLED stack unchanged, still zero mdss-dsi-* timing props
  and no DCS sequences. SELinux compiled IN (Initializing present) but
  every cmdline/bootconfig selinux token stripped (selinux=0: 0,
  androidboot.selinux: 0) — disable strategy, if any, is inside the build
  (default mode? patched init path?) and only runtime can reveal it; watch
  for SELinux init block vs Disabled and avc noise on boot. Staged
  boot-ack-fedora-snapshot18h-selinux-build14.img, 35,801,088 bytes,
  SHA256 567dfbe1d4758819d6f1aa4b785ce938841c5dbfd3d9858f7cf10e21eac559fb;
  snapshot15 ramdisk byte-identical. Not booted, not flashed.





## 15. Build14 runtime evidence and ROM policy capture (2026-10-06)

This section supersedes the earlier build14 **staged-only/not-booted**
status and the earlier RPMB/missing-init interpretations; historical notes
above are retained. Build14 ran, but no newly applied source fixes have
been built or deployed, and neither an Android boot fix nor context-overlay
policy integration is verified.

### Authoritative build14 runtime

- Saved evidence: `porting/artifacts/ack-android-snapshot18h-build14-logdump-20261006-211656.bin`
  and matching `.log`. Raw dump: 67,108,864 bytes, SHA256
  `3b7d5492f66f03b72d4cb74b488b51c0a3a80e643c27c793abd62dd271abf6b3`.
  Decoded log: 162,104 bytes, SHA256
  `f52e4d178ed71bde5c41e81ec83f3236f907a92b04d5632274b87890b2b4600f`.
  Records 0–1569 run through 319.852645 s; the first EOF excludes stale
  tail data. No panic/oops was captured.
- DRM minor 0 registered at 6.577221 s, followed by a GPU warning;
  fbcon at 7.079499 s, msmdrmfb at 7.114878 s, and panel ready at
  7.115921 s. These events do not prove a working Android display.
- Android init first stage ran at 22.522773 s; `system_a` mounted
  read-only at 22.673220 s; enforcing became active at 63.931519 s;
  second stage ran at 64.084233 s. `/data` mounted as f2fs and early
  `mount_all` succeeded at 92.382047 s. Missing-init/storage-failure
  explanations are not supported by this run.
- `qseecomd` started at 93.208384 s. At 93.425765 s, `tee` was denied
  read/write on `mmcblk0p4` labeled `block_device`; exit 255 followed at
  93.432107 s, with 46 exits total. Partition p4 is **SSD, not RPMB**.
  Installed `init.target.rc` starts `vendor.qseecomd`, then waits for
  `vendor.sys.listeners.registered=true`; continued waiting is an
  **inference**, not an observed live property. No SurfaceFlinger crash
  is established by this evidence.

### Immutable installed-ROM SELinux inventory

- Saved `porting/artifacts/rom-sepolicy-system-a-b9cb6955d584.tar`:
  8,475,136 bytes, SHA256
  `b9cb6955d584602b4ef82bd0512cdf51cd37e60a7655da2f8dcb61d8cd3c7e59`.
  Full per-file byte/SHA/path manifest:
  `porting/artifacts/rom-sepolicy-system-a-b9cb6955d584.list`.
  The capture contains 93 regular files totaling 8,401,044 bytes:
  platform 27, vendor 18, ODM 7, product 17, system_ext 24.
- Source was `/dev/block/by-name/system_a`, mounted ext4 `ro,noload`
  in OrangeFox and subsequently unmounted; this is installed-ROM policy,
  **not live recovery policy**. Vendor `plat_sepolicy_vers.txt` is
  `202604`. Platform/product/system_ext stored input hashes each matched
  their precompiled companion files.
- `vendor_file_contexts:681` labels
  `/dev/block/platform/soc/7824900.sdhci/by-name/ssd` as `ssd_device`.
  `vendor_sepolicy.cil:13595` already permits `tee_202604` to access
  `ssd_device` `blk_file` (read/write/open/etc.). ACK instead exposes
  `/dev/block/platform/soc@0/7824900.mmc/by-name/ssd`. The label-path
  mismatch is the outstanding integration target; no generic TEE
  `block_device` allow or extra SELinux permission was added.

### Applied source changes — not built or deployed

- `drivers/misc/qseecom.c`: unlocked DMA-BUF APIs, platform-owned
  `dma_parms`, failed-open cleanup, and non-ICE key handling separated
  from unsupported ICE; `compat_qseecom.h`: 20-byte MDTP ioctl;
  `compat_qseecom.c`: fixed-width CE forwarding.
- `ion_cma_heap.c`: default-CMA selection and rejection of secure flags;
  tissot DTS: DMA heap 27; `scripts/initramfs-diag/init.c`: restored
  protected-fstab guards and context overlay; draft overlay:
  `porting/drafts/vendor_file_contexts.ack`.
- Checked pinned references: Google common `android16-6.12` at
  `3a7d1771d4925a56f7eeb8a5ba1faff0c544a9ef` (`drivers/base/platform.c`
  DMA-parameter ownership, `drivers/dma-buf/dma-buf.c` unlocked APIs,
  `msm8953.dtsi` GPU at `1c00000`, not `3d00000`, disabled);
  donor `android14-5.15` at `76efa001ea197723c0423fdb9136e83b483f7aa1`
  has no `qseecom.c` (the legacy driver is a local extension).
  AOSP `system/core` at `a3b721a32242006b59cb12bd62c9133632af3a2d`
  `init/devices.cpp` considers symlinks during label lookup.

### Exercised checks and limits

- Host `cc -std=gnu11 -Os -Wall -Wextra -Werror` passed for diagnostic
  default, `ANDROID_CAPTURE`, `HEARTBEAT_RECORDER`, and
  `ANDROID_CAPTURE+ANDROID_GUARD_TEST`; built-in guard safety selfcheck
  returned 0. Actual ACK compat-header ABI check passed: MDTP
  `0xc0149722`, encoded/payload 20 bytes versus native 32; CE layouts agree.
  Production QSEE helper excerpts passed GPCE/ICE return and failed-open
  ownership checks with controlled allocation failures.
- Standalone preprocessing + `dtc` + `fdtget` passed: `/ion` compatible
  `qcom,msm-ion`, DMA heap reg `0x1b`, GPU disabled at `1c00000`, QSEE
  reserved/reg `84a00000+1900000`. Existing duplicate I2C/SPI unit-address
  warnings remain; this was **not schema validation**.
- NDK static AArch64 guard smoke ran in OrangeFox 4.9 in an isolated
  mount namespace/chroot: loaded SID rejected; a synthetic initial SID
  exercised deleted-input read-only bind, dangling-alias repair, and
  regular-file preservation successfully. The synthetic SID does **not**
  prove an Android SELinux transition or an ACK boot.
- Throwaway binaries, DTB, and recovery temporary directory were removed.
  These checks involved no kernel build, flash, or ROM writes.

### Remaining prerequisites

- Integrate and verify the SSD label/context overlay against installed
  ROM policy and Android device-node/symlink labeling; integration remains
  **unverified**. Preserve existing type-specific permissions.
- Retain `hardware=qcom`: installed `init.rc` imports vendor
  `init.${ro.hardware}.rc`, and vendor has `init.qcom.rc`, not
  `init.tissot.rc`. `init.debug` support is unverified; init logs are already
  captured.
- A kernel build and subsequent ACK boot require explicit authorization.
  Only such a boot can establish that the applied fixes work together,
  SSD receives the intended label, and the listener/Android startup path
  progresses. No new kernel-boot success is claimed here.
