# Tissot ACK 6.12 port: work resumption

## Start here

Read `current-port-progress.md` first. It supersedes older hypotheses in
`docs/ack-6.18-boot-investigation.md`, `docs/project-mainline.md`, and
`docs/handoff-ack-mainline.md`; those files preserve the investigation history.

This branch contains the complete tracked source snapshot from Google Android
kernel common `android16-6.12`, commit
`3a7d1771d4925a56f7eeb8a5ba1faff0c544a9ef`, followed by the local tissot DTS
change, diagnostic tooling, findings and logs. It does not contain the 4.19
kernel tree or upstream Git history. Upstream source remains fetchable from
https://android.googlesource.com/kernel/common/.

The baseline snapshot and later local adaptation are separate commits. The
DTS adaptation relocates ramoops from `0x9ff00000` to `0x86800000`; its evidence
and limitations are recorded in the investigation documents.

## Last exercised result

Snapshot14 temporarily booted the Fedora ACK kernel with exactly one rule added
to snapshot13's debug policy: `(allow kernel init (dir (search)))`. All other
inputs unchanged and SELinux **enforcing**. At 75.751222 s the observer reported:

```
DIAG: block observer step=open mount namespace failed errno=13
```

No block snapshots or observer-specific AVC were captured. kauditd subsequently
reported 31 suppressed callbacks. The next denied permission is not identified;
do not infer a rule from the errno alone. Snapshot15 subsequently booted its
guarded f2fs-only mount probe successfully; see section 11 of
`current-port-progress.md` for exact mount timings and remaining denials.

macOS streamed `18d1:9008`, serial `tissot-diag`, through
`/dev/cu.usbmodemtissot_diag1`. The first watcher hit a transient ioreg race;
the restarted watcher completed successfully. Saved
`../porting/artifacts/snapshot14-macos-usb-resumed.log`: 121,632 bytes,
records 0–1182 without gaps, through 389.929005 s, with USB recorder EOF.
Userdata (both entries),
persist, dsp and modem_a were skipped; qseecomd exited 255 38 times.
No late-fs action or kernel panic observed.

Receiver has exited and closed its port. User returned phone to recovery;
root ADB retrieved snapshot14 durable logdump under
`../porting/artifacts/ack-android-snapshot14-logdump.{bin,log}`. Raw SHA256:
`3d19a2319527040f6e9a7aaccf96f61840d42d46c3dc907900d0065629b3128f`.
Decoded storage capture has records 0–1103 without gaps through 329.462720 s,
with EOF, and matches the USB prefix. No observer AVC recovered.
No flashing. After policy validation on installed 4.19 Android and the
snapshot15 test, temporarily booted OrangeFox R11.3_1. Phone now has root ADB
in OrangeFox, kernel 4.9.337. Snapshot15 full durable dump retrieved:
`../porting/artifacts/ack-android-snapshot15-logdump.{bin,log}`.
Raw SHA256 `bf80e809224a177ecf0a03384001d4439763cbb76bb2bbd5b7f5977f4d871389`.
Records 0–1348 without gaps and storage EOF; every record matches USB.

## Latest exercised probe and next kernel inputs

`../porting/artifacts/boot-ack-fedora-snapshot15-protected-mounts.img`
(34,988,032 bytes), SHA256
`f880e6f21aac6a3d9ba2d5970c41e8f9ccbe63068994613fb53b4d50670af729`.
Static init compiled with warnings as errors; full debug policy compiled with
secilc exit 0, never loaded during validation. Temporary guard removes the
formattable ext4 userdata fallback before exposing the canonical alias.
f2fs/fsck may still write userdata. No cache or metadata backing mounts exist;
report this limitation, do not substitute tmpfs or repartition.
Actual snapshot15 mounts passed: userdata f2fs, persist, dsp and modem_a;
early mount_all took 1,392 ms. Observer still needs init namespace
lnk_file read permission. Temporary fstab's tmpfs label blocks vold;
fix labeling in the next probe. qseecomd still exits 255.

User completed the legacy ION/QSEECOM Fedora build. Fetched Image.gz-dtb
is 16,936,518 bytes, SHA256
`b4bd964e617892ccaf9e33b2d904a11050d35a5ecb4322152fa15f6ddfc5a108`.
Validated gzip integrity, ARM64 Image header, Tissot DTB and port-specific
QSEECOM strings. ION/system+CMA heaps/QSEECOM/QCOM_SCM/COMPAT are built in.
Earlier header/API fixes and DTB-only outputs are historical, not current.

Snapshot16 `../porting/artifacts/boot-ack-fedora-snapshot16-qseecom.img`
is 35,072,000 bytes, SHA256
`0211ed5764b3014a59ed6537f3d84b047e8d544dd28198a6bd18e95b7383153d`.
Only snapshot15's kernel was replaced; its ramdisk remains byte-identical.
Temporary fastboot boot returned OKAY but no target USB or recorder output
appeared. After manual bootloader return, temporary OrangeFox recovered:
logdump is unchanged from snapshot15 and pstore exposed no files. Do not
claim kernel/driver runtime or relabel snapshot15 logs as snapshot16.
Installed boot_a hash unchanged; no flashing.

The isolation image `boot-ack-fedora-snapshot16-qseecom-probe-disabled.img`
has the same compressed kernel/ramdisk; only qseecom DT node status is
disabled. SHA256
`c00868469d1539d0504f7c9749dec591ba29f049093a2c8e504a9bf3a4149cf2`.
Isolation restored kernel and Android init startup; its USB recorder reached
EOF at 318.03 s. Log `snapshot16-probe-disabled-macos-usb.log`: 140,839 bytes,
SHA256 `9efd6f34acc697d60db937b75995c66cc3e5686f06d3e87b32737ed2e4504c50`.
Complete records 13–1307 have no internal gaps; early prefix is truncated.
Data f2fs, persist/dsp ext4 and modem_a vfat mount successfully; early
mount_all takes 5,706 ms. Existing fstab/observer labeling denials persist.
QSEECOM probe is implicated, but exact hanging operation is unproven.
Receiver exited. User returned to fastboot; temporary OrangeFox is running.
Full isolation durable dump retrieved and hash-matched against the partition:
`ack-android-snapshot16-probe-disabled-logdump.bin`, 67,108,864 bytes, SHA256
`ac573e0e80228639cfa2f9187d81f73e28527a9cb4fb34feb5dce1557d3299a4`.
Decoded `.log`, 141,075 bytes, SHA256
`29147d59102dc56a8604c96ba9e6c3377c1680d041257b896b74b96ee538aea9`;
records 0–1301 without gaps, storage EOF, byte-identical USB overlap.
Runtime confirms 6.12.93-4k/Xiaomi Mi A1. boot_a unchanged, no flashing.
OrangeFox ramoops reads 0x91400000/4 MiB, ACK uses 0x86800000/1 MiB; empty
recovery pstore cannot rule out an ACK failure record. No probe/SCM fix applied.

Step2 payloads fetched and hash-verified. Enabled temporary boot now reaches
kernel/Android init, with QSEE version 0x1001000 logged at 3.10 s; qseecomd
still exits 255 with SELinux block-device access denial. Capture completed
through 378.93 s with recorder EOF and 120 s final quiet: records 0–1422,
no gaps, 154,650 bytes; SHA256
`df986aea593c15bb439a3304aa4ee16e9760c7d226af1a6152a3a7e6cb96d0c7`.
Enabled receiver exited; disabled reader subsequently booted directly via
fastboot, without an intervening recovery/installed-ROM boot.
Enabled boot image SHA256
`0b8583c4cd61c6add64104a3ca9f6e16f6c97d29b162c6c5debcf15be436feae`.
Disabled reader image SHA256
`ad5b9b84130bcad22ed5f125e512e31f39a8b0029339d2fb6be48b484e658196`.
Both live in ../porting/artifacts/ as snapshot17 step2 images. Early reader
mounts pstore read-only in the private recorder namespace, dumps previous
records to logdump before Android handoff. Its late USB read failed with
ENOENT after root handoff; `files=0` does not establish empty pstore.
Reader USB capture completed with records 0–1437, no gaps, EOF and 120 s
final quiet: 156,870 bytes, SHA256
`bdd287515e53ce741a65b45b7cb63745b57a0699ad500888b340a1123705fce7`.
After a manual fastboot return and temporary OrangeFox boot, the durable
logdump confirms a genuinely empty pstore: pre-handoff storage scan had
mount_errno=0, no read error, files=0, records 0–1347 through 313.187226 s,
EOF, byte-identical to the USB overlap. logdump SHA256
`6d71db8e1c6b59819418beadcc1fc51944f2ad4083eb1df385aa7cea593df486`;
decoded log SHA256
`fb7d2d14f5abd4a492a31aa8e3cd8c8021907a5810600f5fae2342f3cca1f000`.
boot_a unchanged; nothing flashed. Async-debug fallback not needed.
Root-path loss confirmed as the cause of the late USB ENOENT. Source now
snapshots pstore once into an anonymous devtmpfs file and maps it read-only
before handoff; storage/USB consume inherited bytes without late pathname
or file reads. Smoke-tested on device: the early snapshot survives path
removal while a late read still fails with errno=2/files=0. Corrected image
staged, not booted:
`boot-ack-fedora-snapshot17b-qseecom-disabled-pstore-reader-step2.img`,
SHA256 `2c5e0605094a2032b4f77f7b74a7f9cf6d01241ea9b571543d912b2a0956928a`.
Newly supplied display-otm1911 kernel verified, not booted: display stack
and orisetech,otm1911 panel enabled, but the QSEECOM driver is absent from
that build and the panel node carries no timing properties. Staged as
`boot-ack-fedora-snapshot18-display-otm1911.img`, SHA256
`be499f3a049413c4ba1c0739d73b4a654d0dd70003e627cc737427e0a738eedd`.





## Evidence layout

- `evidence/logs/`: saved decoded durable captures.
- `evidence/serial/`: USB serial captures, including incomplete reads.
- `evidence/raw/`: gzip-compressed 64 MiB logdump partition captures. Decompression
  preserves every original byte, including stale data after the current EOF.
- `evidence/capture/`: captured init/ueventd/fstab files. `init.target.rc` is an
  edited temporary test copy, **not proof of the installed vendor init file**.
  Running-image logs show the installed `soc/${ro.boot.bootdevice}` wait.
- `evidence/tissot-partitions.txt`: saved GPT inventory; no metadata partition.
- `evidence/manifest.json`: source/destination mappings, hashes and sizes.
- `configs/tissot-ack-resolved.config`: resolved config saved from the ACK out
  directory, not a new config resolution/build.

Important: the recorder writes from partition offset zero without clearing the
remaining partition. Stop decoded current-boot analysis at the **first**
`DIAG: EOF Android kmsg dump complete` marker. Later text can be old captures.
Snapshot12's published decoded log is already cut at its first EOF; other
historical decoded files are byte-preserved and require this interpretation.

Snapshots12 raw SHA256:
`3295e0d5264e82ae524e97d96002f3edb065c80397b9d0428ecba891e56d0902`

v11 raw SHA256:
`4359c40c458b2c1bcb96c363eb7987786563483aa4cd5200b66aed6507d610a3`

## Using this standalone checkout

Historical scripts default to sibling directories from the original 4.19
workspace. In this standalone ACK checkout, override paths explicitly.

To build later, only when requested:

```sh
ACK_TREE="$PWD" LLVM_BIN=/path/to/llvm/bin bash scripts/build-ack-tissot.sh
```

The fragment is `scripts/tissot-ack.config`. To reproduce the saved resolved
configuration instead, use `configs/tissot-ack-resolved.config` as the config
input and verify it against the intended toolchain; no rebuild is claimed here.

The latest static diagnostic init can be compiled with the Android NDK:

```sh
NDK=/path/to/android-ndk
"$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android21-clang" \
  -static -Os -Wall -Wextra -Werror -DANDROID_CAPTURE \
  scripts/initramfs-diag/init.c -o /tmp/tissot-diag-init
```

`repack-tissot-probe.sh` is historical tooling: its default bootdevice argument
is older than the latest experiments, and it does not recalculate the boot-header
SHA1 when replacing payloads. Do not treat its defaults as Snapshot12's packing
recipe. Latest experiments used preservation-checked packing with an updated
SHA1; image hashes are recorded in `current-port-progress.md`.

ROM/vendor images, userdebug policy, compiled kernels, temporary boot images,
private SSH keys, NDK binaries and generated initramfs archives are not bundled.
Bring a known-good ROM boot image and the matching policy from the device when
resuming boot tests. Re-read the source and recorded constraints before editing;
use temporary `fastboot boot`, not partition flashing, for diagnostic tests.
