#!/usr/bin/env bash
#
# Pull the WCNSS firmware and NV blob from the attached device into the
# staging directory that build-kernel.sh packages into lib/firmware/.
#
#   usage: pull-wcnss-firmware.sh [destination]
#
# The files come from the device's own partitions; they are not part of
# this repository and are not redistributable. The NV blob is device
# calibration data and contains no MAC address (checked against both the
# persist MAC file and the serial-derived address), so staging it does not
# copy a captured MAC into the image. The MAC itself is derived at boot by
# the driver from the serial number (see qcom,mac-address-from-serial in
# msm8953-xiaomi-tissot.dts).
#
# The device must be booted far enough that /vendor/firmware_mnt is
# mounted. Run `adb root` first if the adb shell is not root.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
DEST=${1:-$REPO/porting/artifacts/firmware-wcnss}
SRC_FW=/vendor/firmware_mnt/image
SRC_NV=/mnt/vendor/persist/WCNSS_qcom_wlan_nv.bin

command -v adb >/dev/null || { echo "error: adb not on PATH" >&2; exit 1; }
adb get-state >/dev/null 2>&1 || { echo "error: no adb device" >&2; exit 1; }

mkdir -p "$DEST/wlan/prima"

files=(
	wcnss.mdt
	wcnss.b00 wcnss.b01 wcnss.b02 wcnss.b04
	wcnss.b06 wcnss.b09 wcnss.b10 wcnss.b11 wcnss.b12
)

for f in "${files[@]}"; do
	echo "pulling $SRC_FW/$f"
	adb exec-out su -c "cat '$SRC_FW/$f'" > "$DEST/$f"
done

echo "pulling $SRC_NV"
adb exec-out su -c "cat '$SRC_NV'" > "$DEST/wlan/prima/WCNSS_qcom_wlan_nv.bin"

echo
for f in "${files[@]}" wlan/prima/WCNSS_qcom_wlan_nv.bin; do
	size=$(stat -c %s "$DEST/$f")
	[ "$size" -gt 0 ] || { echo "error: $f is empty" >&2; exit 1; }
	printf '%10d  %s\n' "$size" "$f"
done

echo
echo "staged under $DEST"
echo "build-kernel.sh picks it up automatically; override with"
echo "ACK_WCNSS_FIRMWARE_DIR=<dir> if the files live elsewhere."
