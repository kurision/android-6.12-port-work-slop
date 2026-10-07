# Snapshot30: VM build and copy to Mac

Build the ION fix on the Linux VM. Same rules as before: no macOS build, no
config reset, no clean, no flash, no encryption changes.

## 1. Linux VM: pull, enable ION, rebuild

Open a **Bash terminal in your existing kernel Git checkout**. `OUT` must be
the directory holding yesterday's working `.config` (`out` for the snapshot29
build; `out-qseecom` for the earlier one). Do not run
`scripts/build-ack-tissot.sh`: it starts from `gki_defconfig` instead of
preserving your current config.

```bash
set -euo pipefail

git switch port-work
git pull --ff-only

# Change only this setting if your existing .config is somewhere else.
OUT="${OUT:-out}"
test -f "$OUT/.config" || {
    printf "Existing config missing: %s/.config\nSet OUT to the last working build directory; do not create a fresh config.\n" "$OUT" >&2
    exit 1
}

export ARCH=arm64 LLVM=1 LLVM_IAS=1

# Snapshot30 fix: the vendor keymaster HAL needs /dev/ion at runtime.
# scripts/config edits the ACTUAL output config in place (same mechanism as
# the snapshot29 QSEECOM recovery), then olddefconfig resolves dependencies.
cp "$OUT/.config" "$OUT/.config.before-snapshot30"
scripts/config --file "$OUT/.config" --enable STAGING
scripts/config --file "$OUT/.config" --enable ION
scripts/config --file "$OUT/.config" --enable ION_LEGACY
scripts/config --file "$OUT/.config" --enable ION_SYSTEM_HEAP
scripts/config --file "$OUT/.config" --enable ION_CMA_HEAP
make O="$OUT" olddefconfig
for symbol in \
    CONFIG_ARM64_4K_PAGES \
    CONFIG_QCOM_SCM \
    CONFIG_QSEECOM \
    CONFIG_STAGING \
    CONFIG_ION \
    CONFIG_ION_LEGACY \
    CONFIG_ION_SYSTEM_HEAP \
    CONFIG_ION_CMA_HEAP \
    CONFIG_TOUCHSCREEN_EDT_FT5X06; do
    grep -qx "$symbol=y" "$OUT/.config" || {
        printf 'Required built-in missing after olddefconfig: %s\n' "$symbol" >&2
        exit 1
    }
done

# Both outputs must be rebuilt: ION is in the kernel; DT is unchanged but
# rebuild it anyway so kernel and DTB come from the same tree state.
make O="$OUT" -j"$(nproc)" Image.gz qcom/msm8953-xiaomi-tissot.dtb

BOOT="$OUT/arch/arm64/boot"
DTB="$BOOT/dts/qcom/msm8953-xiaomi-tissot.dtb"
test -s "$BOOT/Image.gz"
test -s "$DTB"
gzip -t "$BOOT/Image.gz"
grep -q 'CONFIG_ION=y' "$OUT/include/config/auto.conf"

# Stock boot payload format: gzip-compressed Image followed by the raw board DTB.
cat "$BOOT/Image.gz" "$DTB" > "$BOOT/Image.gz-dtb"

# Fixed transfer directory: scp does not need to know your checkout/output path.
DEST="$HOME/snapshot30-build"
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

## 2. Mac: copy the VM outputs

Run this in a Mac terminal (Bash or zsh). Keep `${VM}` braced before the
colon: zsh treats `$VM:...` as a parameter modifier. Keep each trailing
backslash so scp receives all six source files and the destination in one
command. Normal SSH host-key verification stays enabled.

```bash
set -euo pipefail

VM=sneha@192.168.4.114
DEST=/Users/anilkumal/Documents/Anil/AI/kernel/porting/artifacts/snapshot30-build
mkdir -p "$DEST"

scp \
    "${VM}:snapshot30-build/Image.gz" \
    "${VM}:snapshot30-build/Image.gz-dtb" \
    "${VM}:snapshot30-build/msm8953-xiaomi-tissot.dtb" \
    "${VM}:snapshot30-build/kernel.config" \
    "${VM}:snapshot30-build/build-info.txt" \
    "${VM}:snapshot30-build/SHA256SUMS" \
    "$DEST/"

# Run these only after scp succeeds.
(cd "$DEST" && shasum -a 256 -c SHA256SUMS)
gzip -t "$DEST/Image.gz"
grep -E "CONFIG_ION=|CONFIG_QSEECOM=" "$DEST/kernel.config"
cat "$DEST/build-info.txt"
```

The relative remote paths resolve under the SSH user's home directory.

## 3. Before the next temporary boot

Use the new `Image.gz-dtb` to replace the kernel payload in a repacked image,
retaining the validated snapshot28 diagnostic ramdisk. The existing base is:

`/Users/anilkumal/Documents/Anil/AI/kernel/porting/artifacts/boot-ack-snapshot28-tail-sd-screen.img`

Copying `Image.gz-dtb` alone does not create a boot image. Do not reuse the old
kernel payload or try to boot the raw concatenation directly.

Checks required on the next boot: `/dev/ion` present, `vendor.keymaster-3-0`
stays alive (no status-1 exits), `keystore2` publishes `IKeystoreService`,
`enablefilecrypto` exits 0, then `init_user0`, zygote and boot completion.
