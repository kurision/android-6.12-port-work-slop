#!/bin/sh
# Collect device facts from a running Mi A1 (pmos or Android) into a tarball.
#
#   sh collect-device-facts.sh [output.tar]
#
# Requires: root for /sys/firmware/fdt (use `doas sh collect-device-facts.sh`).
# The DT is pulled from the kernel's own FDT, not from the bootloader, so it is
# exactly what the running kernel saw (including bootloader modifications).
set -eu

OUT=${1:-device-facts.tar}
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

# --- device tree -----------------------------------------------------------
if [ -r /sys/firmware/fdt ]; then
	dd if=/sys/firmware/fdt of="$T/device.dtb" bs=1M status=none
	dtc -I dtb -O dts -o "$T/device.dts" "$T/device.dtb" 2>/dev/null || \
		echo "note: dtc unavailable, only the .dtb was captured" >&2
else
	echo "warning: /sys/firmware/fdt unreadable (need root?)" >&2
fi

# --- kernel logs -----------------------------------------------------------
dmesg            > "$T/dmesg.txt" 2>/dev/null || true
journalctl -b -k --no-pager > "$T/journal-kernel.txt" 2>/dev/null || true
journalctl -b --no-pager      > "$T/journal-all.txt"   2>/dev/null || true
cat /proc/cmdline            > "$T/cmdline.txt"       2>/dev/null || true
cat /proc/mounts             > "$T/mounts.txt"        2>/dev/null || true
cat /proc/iomem              > "$T/iomem.txt"         2>/dev/null || true
zcat /proc/config.gz         > "$T/kconfig.txt"       2>/dev/null || \
	cp /boot/config-* "$T/kconfig.txt" 2>/dev/null || true

# --- thermal ---------------------------------------------------------------
: > "$T/thermal.txt"
for z in /sys/class/thermal/thermal_zone*; do
	[ -e "$z" ] || continue
	printf '%s %s %s policy=%s\n' "$(basename "$z")" "$(cat "$z/type")" \
		"$(cat "$z/temp")" "$(cat "$z/policy")" >> "$T/thermal.txt"
	for t in "$z"/trip_point_*_temp; do
		[ -e "$t" ] || continue
		printf '  trip %s %s\n' "$(cat "${t%_temp}_type")" "$(cat "$t")" >> "$T/thermal.txt"
	done
done
for c in /sys/class/thermal/cooling_device*; do
	[ -e "$c" ] || continue
	printf '%s %s cur=%s max=%s\n' "$(basename "$c")" "$(cat "$c/type")" \
		"$(cat "$c/cur_state")" "$(cat "$c/max_state")" >> "$T/thermal.txt"
done

# --- cpufreq ---------------------------------------------------------------
: > "$T/cpufreq.txt"
for p in /sys/devices/system/cpu/cpufreq/policy*; do
	[ -e "$p" ] || continue
	{
		echo "$(basename "$p"): governor=$(cat "$p/scaling_governor")"
		echo "  available: $(cat "$p/scaling_available_frequencies" 2>/dev/null | tr '\n' ' ')"
		echo "  affected:  $(cat "$p/affected_cpus")"
		echo "  cur=$(cat "$p/scaling_cur_freq") max=$(cat "$p/scaling_max_freq")"
	} >> "$T/cpufreq.txt"
done

# --- storage, partitions, firmware ----------------------------------------
ls -l /dev/disk/by-partlabel/      > "$T/partitions.txt" 2>/dev/null || true
ls /sys/block/mmcblk0/device/     >> "$T/partitions.txt" 2>/dev/null || true
ls -lR /lib/firmware              > "$T/firmware.txt"    2>/dev/null || true
for m in /run/msm-firmware-loader/mnt/*; do
	[ -d "$m" ] || continue
	echo "== $m" >> "$T/firmware.txt"
	ls -la "$m" >> "$T/firmware.txt" 2>/dev/null || \
		echo "  (needs root)" >> "$T/firmware.txt"
done

# --- audio, i2c, display ---------------------------------------------------
{ echo "== cards"; cat /proc/asound/cards
  echo "== pcm"; cat /proc/asounds/pcm 2>/dev/null
  echo "== i2c"; ls /sys/bus/i2c/devices
  echo "== drm"; ls /sys/class/drm 2>/dev/null
  echo "== backlight"; ls /sys/class/backlight 2>/dev/null
} > "$T/devices.txt" 2>/dev/null || true

tar cf "$OUT" -C "$T" .
echo "wrote $OUT"