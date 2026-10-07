# Snapshot29: VM build and copy to Mac

Build the fixes in `a17c54c4f` on the Linux VM. These commands do not build on
macOS, reset the config, clean the output tree, flash, or change encryption.

## 1. Linux VM: pull and rebuild

Open a **Bash terminal in your existing kernel Git checkout**. Use the same
Clang/toolchain PATH and output directory as yesterday's successful build.
`out-qseecom` is the earlier documented output directory; change `OUT` below
if yesterday's build used a different directory. Do not run
`scripts/build-ack-tissot.sh`: it starts from `gki_defconfig` instead of preserving
your current config.

```bash
set -euo pipefail

git switch port-work
git pull --ff-only
git merge-base --is-ancestor a17c54c4f HEAD

# Change only this setting if your existing .config is somewhere else.
OUT="${OUT:-out-qseecom}"
test -f "$OUT/.config" || {
    printf "Existing config missing: %s/.config\nSet OUT to yesterday's build directory; do not create a fresh config.\n" "$OUT" >&2
    exit 1
}

# Keep the existing toolchain PATH; do not switch compiler versions here.
export ARCH=arm64 LLVM=1 LLVM_IAS=1
command -v clang
clang --version
command -v ld.lld

# Preserve a copy before olddefconfig resolves any newly introduced symbols.
cp "$OUT/.config" "$OUT/.config.before-snapshot29"
make O="$OUT" olddefconfig
for symbol in CONFIG_ARM64_4K_PAGES CONFIG_QCOM_SCM CONFIG_QSEECOM CONFIG_TOUCHSCREEN_EDT_FT5X06; do
    grep -qx "$symbol=y" "$OUT/.config" || {
        printf 'Required built-in missing after olddefconfig: %s\n' "$symbol" >&2
        exit 1
    }
done

# Both outputs must be rebuilt: SCM/QSEE code is in the kernel; touch power is in DT.
make O="$OUT" -j"$(nproc)" Image.gz qcom/msm8953-xiaomi-tissot.dtb

BOOT="$OUT/arch/arm64/boot"
DTB="$BOOT/dts/qcom/msm8953-xiaomi-tissot.dtb"
test -s "$BOOT/Image.gz"
test -s "$DTB"
gzip -t "$BOOT/Image.gz"

# Stock boot payload format: gzip-compressed Image followed by the raw board DTB.
cat "$BOOT/Image.gz" "$DTB" > "$BOOT/Image.gz-dtb"

# Fixed transfer directory: scp does not need to know your checkout/output path.
DEST="$HOME/snapshot29-build"
mkdir -p "$DEST"
cp "$BOOT/Image.gz" "$BOOT/Image.gz-dtb" "$DTB" "$DEST/"
cp "$OUT/.config" "$DEST/kernel.config"
{
    printf 'source_commit=%s\n' "$(git rev-parse HEAD)"
    printf 'output_directory=%s\n' "$OUT"
    printf 'kernel_release=%s\n' "$(cat "$OUT/include/config/kernel.release")"
    printf 'built_utc=%s\n' "$(date -u +%FT%TZ)"
    clang --version
} > "$DEST/build-info.txt"
(
    cd "$DEST"
    sha256sum Image.gz Image.gz-dtb msm8953-xiaomi-tissot.dtb kernel.config build-info.txt > SHA256SUMS
    sha256sum -c SHA256SUMS
)
printf '\nReady for scp: %s\n' "$DEST"
```

Stop if any command fails. Do not package a previous build after a failed make.
The directory contains **kernel payloads, not a boot.img**.

### Recovery: uploaded kernel has QSEECOM disabled

The first uploaded kernel identifies commit `a17c54c4fea0`, but its embedded
config says `# CONFIG_QSEECOM is not set`. It cannot test the listener fixes.
In the VM checkout, enable the driver in the **same output directory that make
will use**, without resetting the rest of the config:

```bash
set -euo pipefail
OUT="${OUT:-out-qseecom}"
test -f "$OUT/.config"
cp "$OUT/.config" "$OUT/.config.before-qsee-enable"
scripts/config --file "$OUT/.config" --enable QSEECOM
export ARCH=arm64 LLVM=1 LLVM_IAS=1
make O="$OUT" olddefconfig
grep -qx 'CONFIG_QSEECOM=y' "$OUT/.config"
```

Then run section 1 again to rebuild and stage the fresh outputs, followed by
section 2 to copy **all six files**, including `kernel.config` and checksums.
If yesterday's actual output directory is not `out-qseecom`, change `OUT`
before running either block. The disabled-QSEE kernel must not be booted.

## 2. Mac: copy the VM outputs

Run this in a Mac terminal (Bash or zsh). The VM address below is the one supplied
for this build. Keep `${VM}` braced before the colon: zsh treats `$VM:...` as a
parameter modifier. Keep each trailing backslash so scp receives all six source
files and the destination in one command. Normal SSH host-key verification stays enabled.

```bash
set -euo pipefail

VM=sneha@192.168.4.114
DEST=/Users/anilkumal/Documents/Anil/AI/kernel/porting/artifacts/snapshot29-build
mkdir -p "$DEST"

scp \
    "${VM}:snapshot29-build/Image.gz" \
    "${VM}:snapshot29-build/Image.gz-dtb" \
    "${VM}:snapshot29-build/msm8953-xiaomi-tissot.dtb" \
    "${VM}:snapshot29-build/kernel.config" \
    "${VM}:snapshot29-build/build-info.txt" \
    "${VM}:snapshot29-build/SHA256SUMS" \
    "$DEST/"

# Run these only after scp succeeds.
(cd "$DEST" && shasum -a 256 -c SHA256SUMS)
gzip -t "$DEST/Image.gz"
cat "$DEST/build-info.txt"
```

The relative remote paths resolve under the SSH user's home directory. If the
VM build ran under another account, use that account in `VM` as well.

## 3. Before the next temporary boot

Use the new `Image.gz-dtb` to replace the kernel payload in a repacked image,
retaining the validated snapshot28 diagnostic ramdisk. The existing base is:

`/Users/anilkumal/Documents/Anil/AI/kernel/porting/artifacts/boot-ack-snapshot28-tail-sd-screen.img`

Copying `Image.gz-dtb` alone does not create a boot image. Do not reuse the old
kernel payload or try to boot the raw concatenation directly. No repack or
fastboot command is included here: this file covers building and transferring
artifacts, not flashing or starting a device run.

Checks still required on the next boot: successful legacy listener registration,
`enablefilecrypto` exit status 0, `init_user0`, zygote and boot completion. These
source fixes have not yet been verified with a full VM kernel build/device boot.
