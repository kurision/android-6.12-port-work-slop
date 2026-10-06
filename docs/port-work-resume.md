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

Snapshot12 temporarily booted with the kernel/DTB unchanged and SELinux
**enforcing**. At uptime 75.755600 seconds the observer reported:

```
DIAG: block observer step=open mount namespace failed errno=2
```

It could not open `/proc/1/ns/mnt`, so it did **not** collect block-directory
snapshots. Vendor mounts still skipped userdata, persist, dsp and modem_a;
`vendor.qseecomd` still exited with 255. The phone was returned to recovery.
No kernel build or partition flashing was performed in this diagnostic phase.

The procfs-fd correction is now approved and implemented: the observer opens
procfs before its wait and uses `openat()` for PID 1's namespace/root. The fd
is closed on success and failure. A host smoke proved both opens survive removal
of the original procfs pathname; host `setns` then failed with EPERM. The corrected
static AArch64 init compiled successfully, but it has **not been boot-tested on
the phone**. Snapshot12 remains the latest on-device result. Android access
permissions and the exact original ENOENT cause remain unverified.

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
