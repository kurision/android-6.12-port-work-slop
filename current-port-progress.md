# Tissot ACK 6.12 port — current progress

Updated: 2026-10-05 (UTC+0545 device clock). Companion to
`docs/ack-6.18-boot-investigation.md` §14–§15; this file is the live status
log. Kernel tree: `../ack-android16-6.12` (android16-6.12 checkout
`3a7d1771d4925a56f7eeb8a5ba1faff0c544a9ef`, image builds carry local
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
- Next diagnostic candidate, not yet approved or proven: retain an open
  procfs directory fd before init's root switch, then use `openat()` for
  PID 1's namespace/root instead of resolving `/proc` from the observer's
  old root. Exact ENOENT cause remains unverified.
