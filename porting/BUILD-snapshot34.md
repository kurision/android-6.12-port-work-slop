# Snapshot34 ioctl-completion diagnostic test — USB and durable evidence recovered

## Status

All seven stages completed, including prior-evidence preservation, successful logdump clearing/full all-zero readback, one temporary boot, and fresh logdump/SD recovery. USB proves query/set-memory completion and two complete native send paths. A third send enters SCM but no return is captured before USB disconnect. Durable evidence matches USB through sequence 1192 and adds no later tail. No FBE fix, diagnostic Android boot success, panic/reset or third-call root cause is established.

## Source and baseline

- Revision: `66fb1a0556a4aaff94db451f46da299a7a06a213`; existing uncommitted diagnostics and handoff changes preserved; no commit/push.
- Initial full tracked diff SHA256: `acfb818b5a8feec4ce6692b1c2b162d561927703dbdae76d2ef72ec69af2df66`, retained in `snapshot34/baseline-source-diff.stdout`.
- Snapshot33 manifest verified before edits. Sole binary baseline: `boot-ack-snapshot33-listener-roundtrip-tail-sd-screen.img`, 35,964,928 bytes, SHA256 `f614b06dfd172af1ba54e6ba9547a8500f8a236af9a1603d0b5d17da52b575a7`.
- Only driver changes: response cache begin/end and shared helper return in `__qseecom_send_cmd`; native/compat entry and completion for load-app, app-loaded query, set-memory, plain send and both modfd sends. Compat translation failures and native/copyback precedence retained, including query `-EEXIST`. Existing SCM/listener records unchanged. No ABI, cache operation, lock, timeout, retry, return semantics, whitelist, fence or encryption changes.
- LSP references returned only the helper declaration. Text caller inventory located plain send, both modfd paths and kernel send. Signature unchanged.

## Build and packaging verification

- Fresh `out-snapshot34` seeded from exact baseline embedded config. NDK29 Android clang/LLD 21.0.0, `ARCH=arm64 LLVM=1 LLVM_IAS=1`.
- `olddefconfig` exit 0; **all parsed CONFIG values identical**, required built-ins all `y`.
- Full `make O=out-snapshot34 -j12 Image.gz qcom/msm8953-xiaomi-tissot.dtb` exit 0. Full output: `snapshot34/build.log`; status: `snapshot34/build.status`. Compat compiled through its inclusion in qseecom.
- `gzip -t` exit 0; all nine new literal templates and 82 existing diagnostic strings selected by SCM/listener/spill/carveout terms present in compiled Image.
- Board DTB byte-identical to baseline, SHA256 `18a1081e6ed523e174e9070814dade0b1425c490996f7d2e325a7a7a9947aae8`.
- Release: `6.12.93-4k-g66fb1a0556a4-dirty`.
- Installed mkbootimg used with exact baseline binary ramdisk and approved v0 fields/cmdline. Binary assertions passed: exact new gzip+DTB payload, exact ramdisk, second_size 0, page-rounded offsets and zero padding; header page matches baseline except kernel_size and ID; recomputed payload SHA1 followed by 12 zero bytes.
- Image: `porting/artifacts/boot-ack-snapshot34-ioctl-completion-tail-sd-screen.img`, 35,964,928 bytes, SHA256 `5f5c624051a8db9686e556b114c317f85055587df4994855f71657d1ecd11dba`.
- Staged artifacts and image verified with `snapshot34/SHA256SUMS`. Compiled literals and packaging are not proof of runtime traversal.

## Preservation and verified zero baseline

- Initial Magisk root failures preceded device preservation operations. Logs showed missing `/proc/<pid>/cwd`; authorization denial was not established. Root later recovered without assistant changes to Magisk/security.
- Verified tissot serial `2819f2320604`, installed-ROM boot completion 1, slot `_a`, root uid 0 and exact stdout OUT/stderr ERR separation. Battery 95% during renewed preservation, 94% immediately before launch.
- Resolved logdump `/dev/block/mmcblk0p48`, sysfs PARTNAME=logdump and exact size 67,108,864. Prior full partition preserved twice (`preboot-logdump.bin`, `preboot-logdump-run2.bin`); SD preserved twice (`preboot-sd.log`, `preboot-sd-run2.log`). All SD bytes equal preserved raw prefix. Original partition SHA256 `cd1ea67672ae5b74436be20708bf2d46b97909a2d467b5f72633e9d3b57da989`; SD 121,682 bytes, SHA256 `13c1189efba37254325e352ea02c95bfdaf18f67d3668d1a1ff6163e4ea3163c`.
- SD discovered as mmcblk1, p1 major:minor 179:33. First namespace scan: 645 readable processes, no unreadable processes or mount; corrected private BusyBox RO recovery succeeded.
- After reconnection, slow per-line shell scan timed out. Optimized read-only scan found 717 readable namespaces, none unreadable, existing RW owner mount. No independent mount/remount/unmount was attempted. The owner-visible noatime log was read without mount changes and proved byte-identical to the already safely preserved SD copy.
- Earlier clear invocation exited 255. Renewed identity-guarded clear (`now-logdump-clear.*`) and sync exited 0. Entire binary-only readback `preboot-logdump-zero.bin` is exactly 67,108,864 zero bytes, SHA256 `3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351`.
- Detailed proof: `snapshot34/preboot-verification.txt`; stdout/stderr/status evidence retained separately.

## One temporary boot and capture

- Reused `/tmp/snapshot33-capture-venv/bin/python`, pyserial 3.5, and unchanged `porting/logging/usb-boot-capture.py`. Exact command/output in `snapshot34/capture-command.txt` and `capture-command-output.txt`; 1200-second host deadline.
- Only `fastboot boot` used: Sending OKAY (0.767s), Booting OKAY (1.024s), total 1.814s. Reader opened `/dev/ttyACM0`.
- Host process exit 0, but reader status is `reader-error: device reports readiness to read but returned no data (device disconnected or multiple access on port?)`; reader elapsed 106.5s. Not EOF or host deadline, not proof of reset.
- USB `porting/artifacts/snapshot34-usb.log`: 129,265 bytes, SHA256 `c6005921cb23c1eabbea1523d65693a0a8e27e7310d3285af007c7984c939699`. 1,195 records, sequences 0–1194 contiguous, endpoint 79.786599s. Line 2 confirms expected release/toolchain.
- Exact reader status: `porting/artifacts/snapshot34-usb-capture.status`. No flashing, slot change, encryption reset or firmware modification.

## Fresh runtime boundaries

All line numbers below refer to `snapshot34-usb.log`; caller T335 is the started keymaster PID 335.

| Time (s) | Lines / sequence | Observation |
|---:|---|---|
| 75.792190 | 1145 / 1116 | Keymaster started as PID 335 |
| 76.624556–76.625026 | 1182–1183 / 1153–1154 | enablefilecrypto PID 351 started; init waits |
| 79.254482–79.268190 | 1194–1198 / 1165–1169 | Native query nr 15: SCM transport/result 0, ioctl returns -17 (-EEXIST), intentional already-loaded outcome |
| 79.306883–79.309229 | 1199–1200 / 1170–1171 | Native set-memory nr 8 enters and returns 0 |
| 79.311710–79.347995 | 1201–1209 / 1172–1180 | First native send nr 3: SCM transport/result 0, response cache begin→end 0, helper return 0, native return 0 |
| 79.357391–79.388960 | 1210–1218 / 1181–1189 | Second native send nr 3: same complete chain, all returns 0 |
| 79.493127 | 1219 / 1190 | Keymaster still running at interface-start request; not proof of service registration |
| 79.697048 | 1221 / 1192 | Keystore2 found in VINTF manifest; not proof of completed registration |
| 79.786339–79.786599 | 1222–1223 / 1193–1194 | Third native send enters; final record is SCM `30000006 argc 7 call`, no return captured |

Two observed sends complete the full native path; no pending response-cache operation or helper/native housekeeping boundary remains for those sends. The third observed send's missing boundary is SCM return, but a disconnected capture does not prove a blocked SCM call or its cause. No compat entry/return, load-app marker, listener callback/response chain, keymaster exit, enablefilecrypto exit, zygote start, boot-complete, EOF or panic/reset marker captured. Result-success without listener callbacks is expected, not evidence of a listener bug. Earlier warnings remain unchanged and are not proven causal.

## Durable recovery completed

- The phone was absent from ADB/fastboot/USB immediately after capture. Later user-requested recovery found rooted installed ROM; final `sys.boot_completed=1`, slot `_a`, root uid 0. Installed-ROM readiness does not prove diagnostic-kernel boot completion.
- Reverified exact stdout OUT/stderr ERR, resolved logdump `/dev/block/mmcblk0p48`, sysfs PARTNAME=logdump, and 67,108,864-byte size. Binary pull exited 0 with stderr/status saved separately.
- Raw `porting/artifacts/snapshot34-logdump.bin`: 67,108,864 bytes, SHA256 `89b5114cb9e25a063d2289f4b36197340e9035c41fc40b9c0dda7f8ff819e552`.
- SD rediscovered as mmcblk1p1, major:minor 179:33. Namespace scan: 709 readable, none unreadable, existing RW noatime owner mount. No independent mount, remount or unmount attempted; read the existing owner-visible log only after verifying root-shell mount identity and file device ID. No repair/format or SD writes issued.
- SD `porting/artifacts/snapshot34-sd.log`: 129,159 bytes, SHA256 `f474779b89a87b6718e93c45fbb0f25cd0d82758d059132ae459d806afaaf494`; full bytes exactly equal raw prefix. `snapshot34-durable.log` derived only after this assertion and has identical size/hash.
- Durable sequences 0–1192 contiguous; line 1223 ends at 79.697048s with keystore2 found in the VINTF manifest. Initial 93-byte DIAG preamble is absent from USB; all remaining SD bytes, including record continuation lines, equal the USB prefix. All 1,193 overlapping records agree exactly.
- Raw first zero is offset 129,159; every remaining 66,979,705 byte is zero. Raw-only fresh extension is **0 bytes**. Verified zero preboot baseline and exact channel overlap establish freshness without stale-tail inference.
- USB alone adds sequences 1193–1194, ending at 79.786599s: third native send entry, then SCM call entry. Durable evidence adds no return, panic/reset or later userspace completion. Both channels prove the first two complete native sends; the third missing SCM return remains inconclusive.
- Full recovery proof: `snapshot34/recovery-verification.txt`; exact pull stderr/status, namespace scan, owner access and final ROM state retained in the artifact directory. Final refreshed manifest covers recovered channels and documentation. No second diagnostic boot, recovery clearing, flashing, slot/encryption change or auto-commit/push.
