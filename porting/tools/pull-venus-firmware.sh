#!/usr/bin/env bash
#
# Pull the Venus video codec firmware from the attached device into the
# staging directory. build-kernel.sh packages the venus.* files into the
# ramdisk: the Venus driver requests them at probe time, long before
# /vendor is mounted, so they cannot be read from the vendor partition
# when the driver needs them.
#
#   usage: pull-venus-firmware.sh [destination]
#
# The files come from the device's own partitions (the ROM keeps them on
# the firmware_mnt vfat partition); they are not part of this repository
# and are not redistributable.
#
# The device must be booted far enough that /vendor/firmware_mnt is
# mounted. Run `adb root` first if the adb shell is not root, or use
# `adb exec-out su -c cat ...` as below.
#
# The image is a split ELF: venus.mdt holds the ELF header and the hash
# segment, and the payload lives in venus.b00..b04. The MDT loader derives
# the segment names from the firmware name (venus.mdt -> venus.bNN), so
# the staged names must not be changed.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
DEST=${1:-$REPO/porting/artifacts/firmware-venus}
SRC_FW=/vendor/firmware_mnt/image

command -v adb >/dev/null || { echo "error: adb not on PATH" >&2; exit 1; }
adb get-state >/dev/null 2>&1 || { echo "error: no adb device" >&2; exit 1; }

mkdir -p "$DEST"

files=(
	venus.mdt
	venus.b00 venus.b01 venus.b02 venus.b03 venus.b04
)

for f in "${files[@]}"; do
	echo "pulling $SRC_FW/$f"
	adb exec-out su -c "cat '$SRC_FW/$f'" > "$DEST/$f"
done

echo
for f in "${files[@]}"; do
	size=$(stat -c %s "$DEST/$f")
	[ "$size" -gt 0 ] || { echo "error: $f is empty" >&2; exit 1; }
	printf '%10d  %s\n' "$size" "$f"
done

# The staged image has to be the split-ELF form the MDT loader reads:
# an ELF header, not an MDT header.
magic=$(head -c 4 "$DEST/venus.mdt" | od -An -tx1 | tr -d ' \n')
if [ "$magic" != "7f454c46" ]; then
	echo "error: venus.mdt is not an ELF image (magic $magic)" >&2
	exit 1
fi

echo
echo "staged under $DEST"
echo "build-kernel.sh picks it up automatically; override with"
echo "ACK_VENUS_FIRMWARE_DIR=<dir> if the files live elsewhere."
