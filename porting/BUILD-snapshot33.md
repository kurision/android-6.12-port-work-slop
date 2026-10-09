# Snapshot33 listener-roundtrip diagnostic test

## Observed outcome

One temporary `fastboot boot` accepted the new image. USB captured SCM transport and secure-response fields, then cut off in the FBE window. No listener callback was observed. Android boot success, kernel panic/reset, and a root cause are not established.

Durable recovery completed after the phone returned to rooted installed ROM. SD equals the raw logdump prefix exactly; its endpoint precedes USB and does not change the observed boundary. No flashing, logdump clearing, SD repair, encryption or slot changes were performed.

## Build and packaging proof

- Source revision: `66fb1a0556a4aaff94db451f46da299a7a06a213`; existing SCM call/return tracing retained. Uncommitted `drivers/misc/qseecom.c` changes add only the approved result and listener messages. Diagnostic diff: `porting/artifacts/snapshot33/source-diagnostics.diff`, SHA256 `698bab945ea951a34b9ab9de3813c7a104673e57d000056c7b1c0adaa154443c`.
- Base: `boot-ack-snapshot32-spill-carveout-tail-sd-screen.img`, SHA256 `9b04908c5956f450d4a2688b2e7a38ec07f6e24245c29829892833d0947915fd`; size 35,964,928, header v0, page size 2048, no second payload. Extracted kernel 16,978,788 bytes, ramdisk 18,147,071 bytes, appended DTB 40,931 bytes, embedded config 231,671 bytes. Existing `/tmp/snapshot33-base-unpack` kernel and ramdisk matched exact base bytes.
- Fresh `out-snapshot33` seeded from embedded snapshot32 config; `out` untouched. `olddefconfig` and full `make O=out-snapshot33 -j12 Image.gz qcom/msm8953-xiaomi-tissot.dtb` exited 0. Full output/status retained in `snapshot33/olddefconfig.log`, `build.log`, and `build.status`.
- Test variable: NDK29 Android clang/LLD 21.0.0 instead of baseline Fedora clang/LLD 22.1.8. Only compiler/assembler/linker/pahole/rust version and capability settings changed; exact list in `snapshot33/config-changes.txt`. Required built-ins all `y`; all other feature settings preserved.
- Release: `6.12.93-4k-g66fb1a0556a4-dirty` (built artifact; release banner not present in captured USB).
- Gzip validation, new diagnostic literals, existing spill/carveout literals, concatenation and manifest checks passed. Rebuilt DTB byte-identical, SHA256 `18a1081e6ed523e174e9070814dade0b1425c490996f7d2e325a7a7a9947aae8`.
- Packaged with installed `mkbootimg`, original binary ramdisk and exact header fields; zero padded to base length. Binary checks passed: new kernel payload, exact base ramdisk, all header bytes unchanged except kernel size and ID, zero second size, valid padding, recomputed payload SHA1 plus 12 zero bytes.
- Image: `porting/artifacts/boot-ack-snapshot33-listener-roundtrip-tail-sd-screen.img`, 35,964,928 bytes, SHA256 `f614b06dfd172af1ba54e6ba9547a8500f8a236af9a1603d0b5d17da52b575a7`.

## Device and capture proof

Preflight and launch checks: serial `2819f2320604`, tissot, rooted installed ROM, boot-completed `1`, slot `_a`, battery 97%. Preserved prior SD log (117,333 bytes) in `snapshot33/preboot-sd.log` and prior logdump (67,108,864 bytes) in `snapshot33/preboot-logdump.bin`. Verified logdump PARTNAME and size; shell-v2 probe separated exact stdout `OUT` from stderr `ERR`. Existing read-only SD mount was reused without mount changes. Isolated capture Python imported pyserial 3.5.

Command: `/tmp/snapshot33-capture-venv/bin/python porting/logging/usb-boot-capture.py --image porting/artifacts/boot-ack-snapshot33-listener-roundtrip-tail-sd-screen.img --log porting/artifacts/snapshot33-usb.log --adb-serial 2819f2320604`.

Fastboot: Sending OKAY (0.764s), Booting OKAY (1.024s), total 1.796s. Reader opened `/dev/ttyACM0`. Process exited 0, but status is `reader-error: device reports readiness to read but returned no data (device disconnected or multiple access on port?)`, host elapsed 94.8s. This is not EOF or a host deadline (1200s), nor proof of kernel reset.

USB: `snapshot33-usb.log`, 113,474 bytes, SHA256 `755c96e2486793ce41850f1ba51ebd833f8d9bf93a217141197c34a7a9f4da68`; 1,048 records, sequence 112–1159 without internal gaps, timestamp 0.033749–72.226678s. Initial records 0–111 are unavailable. Capture command output, status, preflights and checksums are preserved.

## Fresh observed boundaries

Line references below are in `porting/artifacts/snapshot33-usb.log`; timestamps are device log microseconds converted to seconds, not host elapsed time.

| Time (s) | Lines | Observation |
|---:|---:|---|
| 1.836130 | 113 | Shared carveout enabled for SCM spill buffers |
| 70.127309–70.386487 | 937–986 | Listener registration command `0x4`: transport 0, secure result 0, type/data 0; preceding `32000206` probes return transport -5 before successful `32000201` calls |
| 70.127337–70.401046 | 938–988 | Listeners 8192, 12288, 16384, 11, 10, 28672, 36864, 4352 registered and enter receive waiting |
| 71.327714 | 1021 | `vendor.keymaster-3-0` started, PID 338 |
| 71.952836 | 1057 | `vdc --wait cryptfs enablefilecrypto` PID 346 started; init waits |
| 72.124286 | 1061 | Command `0x3`: transport 0, secure result 0, type `0xee01`, data `0x10001` |
| 72.137055–72.147346 | 1062–1065 | First seven-argument `30000006` call spills to carveout `0xff011000`, returns transport 0; command `0x1c` secure result 0, type `0xee01`, data `0x10001` |
| 72.148878–72.158694 | 1066–1069 | Second seven-argument call also spills and returns transport 0; command `0x1c` has the same secure fields |
| 72.192045 | 1073 | Keymaster still running when interface start requested; no keymaster exit captured |
| 72.226678 | 1076 | Last USB record: `vdc: Waited 0ms for vold` |

No callback ID, request wake/delivery, response-ready/ioctl, response-wait-complete, or post-lock response-wake record exists in this fresh capture. Initial TA-related calls do have successful transport returns and secure result 0; no observed incomplete-result callback chain begins. Thus this capture does not locate a listener response wait or lock-reacquisition blockage. It cannot exclude later callbacks beyond the missing tail.

No `enablefilecrypto` exit, zygote service start, boot-complete, EOF, panic, or explicit reset marker was captured. Zygote RC parsing is not service start. Spill-to-carveout and transport return are proven; successful Android boot and a secure-world-reset/spill-buffer diagnosis are not.

## Durable recovery completed

- Reconfirmed tissot serial, root, logdump `/dev/block/mmcblk0p48`, sysfs `PARTNAME=logdump`, and 67,108,864-byte size. Shell-v2 probe again separated `OUT` stdout and `ERR` stderr.
- Read-only binary pull: `adb -s 2819f2320604 shell -T 'su -c "dd if=/dev/block/by-name/logdump bs=1048576 count=64"'`; successful exit, remote stderr retained separately in `snapshot33-logdump-pull.status`.
- Raw artifact: `porting/artifacts/snapshot33-logdump.bin`, 67,108,864 bytes, SHA256 `cd1ea67672ae5b74436be20708bf2d46b97909a2d467b5f72633e9d3b57da989`.
- SD discovered by sysfs type `SD` as mmcblk1, partition mmcblk1p1, major:minor `179:33`. Namespace scan checked 647 process mountinfo files, including PID1 and root shell; no matching mount or unreadable process was found. A rescan before retry also found no mount or visibility failure.
- Initial private-mount setup failed before mounting: Toybox `mount --make-rprivate /` reported `bad /etc/fstab`. Empty `snapshot33-sd.log` and its failure status retained. Retried with installed Magisk BusyBox equivalent `mount -o rprivate / /` inside `unshare -m`, then mounted vfat `ro,nosuid,nodev,noexec`, streamed the log, and unmounted/removed only the new `/tmp/sdrec33` via exit trap. Successful exit, empty stderr; no SD writes.
- Successful SD artifact: `porting/artifacts/snapshot33-sd-run2.log`, 121,682 bytes, SHA256 `13c1189efba37254325e352ea02c95bfdaf18f67d3668d1a1ff6163e4ea3163c`. Exact raw logdump prefix equality verified; `snapshot33-durable.log` contains only these verified bytes, with the same size/hash. Raw partition bytes beyond this length were not analyzed.
- Durable sequences 0–1141, contiguous. Line 4 confirms the expected kernel release and NDK21 compiler. Last record, line 1172, timestamp 71.953300s: `init: Command 'installkey /data' ... took 85ms and succeeded`.
- All 1,030 overlapping records (sequences 112–1141) match USB exactly, including record continuation lines. USB extends through sequence 1159 at 72.226678s; no additional fresh durable tail exists in the SD log. No callback/response chain, EOF, panic, zygote start or boot-complete in durable evidence.
- Recovery preflight, process namespace scans and verification are retained in `snapshot33/`; recovered artifacts/statuses are included in its refreshed `SHA256SUMS`.

## Next-test preflight requirement

Before the next temporary boot, preserve existing logdump evidence, then clear logdump and verify the cleared baseline as requested by the user. Do not clear it during recovery. Verify partition identity and size before any write; retain the SD baseline too.
