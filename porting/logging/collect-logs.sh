#!/bin/sh
# Collect porting logs from the device into a tarball.
#
#   doas sh collect-logs.sh [output.tar]
#
# Run this after every boot attempt that failed. pstore contents survive the
# reboot, so this is the only record of a crashed boot — pull it before the
# next attempt (pstore records are overwritten by the next crash).
set -u

OUT=${1:-/tmp/port-logs.tar}
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/pstore" "$T/sysfs"

# --- identity / configuration ---------------------------------------------
{
	echo "collected: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
	echo "uname: $(uname -a)"
	echo "cmdline: $(cat /proc/cmdline 2>/dev/null)"
	echo "printk (console default min): $(cat /proc/sys/kernel/printk)"
	echo "consoles:"
	sed 's/^/  /' /proc/consoles 2>/dev/null
	echo "uptime: $(cat /proc/uptime)"
	echo "psstore module params:"
	for f in /sys/module/pstore/parameters/*; do
		[ -e "$f" ] && echo "  $(basename "$f") = $(cat "$f")"
	done
} > "$T/meta.txt"

# --- kernel ring buffer ----------------------------------------------------
dmesg          > "$T/dmesg.txt"      2>/dev/null
dmesg -T       > "$T/dmesg-human.txt" 2>/dev/null

# --- journals (all boots) -------------------------------------------------
journalctl --list-boots --no-pager > "$T/journal-boots.txt" 2>/dev/null
journalctl -b --no-pager -k          > "$T/journal-boot-kernel.txt" 2>/dev/null
journalctl -b --no-pager             > "$T/journal-boot.txt"       2>/dev/null
journalctl -b -1 --no-pager -k       > "$T/journal-prev-kernel.txt" 2>/dev/null || true
journalctl -b -1 --no-pager          > "$T/journal-prev.txt"        2>/dev/null || true

# --- pstore: the crash records (root only) --------------------------------
if [ -d /sys/fs/pstore ]; then
	cp -a /sys/fs/pstore/. "$T/pstore/" 2>/dev/null || \
		echo "warning: /sys/fs/pstore not readable (need root?)" >> "$T/meta.txt"
fi

# --- subsystem state, for diffing against a good boot ---------------------
for z in /sys/class/thermal/thermal_zone*; do
	[ -e "$z" ] || continue
	{
		echo "$(basename "$z") type=$(cat "$z/type") temp=$(cat "$z/temp") policy=$(cat "$z/policy")"
		for t in "$z"/trip_point_*_temp; do
			[ -e "$t" ] && echo "  trip $(cat "${t%_temp}_type") $(cat "$t")"
		done
	} >> "$T/sysfs/thermal.txt" 2>/dev/null
done
for p in /sys/devices/system/cpu/cpufreq/policy*; do
	[ -e "$p" ] || continue
	{
		echo "$(basename "$p") governor=$(cat "$p/scaling_governor")"
		echo "  available: $(cat "$p/scaling_available_frequencies" 2>/dev/null | tr '\n' ' ')"
		echo "  cur=$(cat "$p/scaling_cur_freq") max=$(cat "$p/scaling_max_freq")"
	} >> "$T/sysfs/cpufreq.txt" 2>/dev/null
done
[ -r /sys/kernel/debug/regulator/regulator_summary ] && \
	cp /sys/kernel/debug/regulator/regulator_summary "$T/sysfs/regulator_summary.txt"
cat /proc/iomem        > "$T/sysfs/iomem.txt"        2>/dev/null
cat /proc/interrupts   > "$T/sysfs/interrupts.txt"   2>/dev/null
lsmod                 > "$T/sysfs/modules.txt"       2>/dev/null
{ ls /sys/bus/i2c/devices; echo; ls /sys/class/drm; echo; cat /proc/asound/cards; } \
	                     > "$T/sysfs/devices.txt"     2>/dev/null
ip -brief addr         > "$T/sysfs/network.txt"      2>/dev/null

# --- summary --------------------------------------------------------------
{
	echo "pstore records:"
	ls -l "$T/pstore" 2>/dev/null | tail -n +2 || echo "  (none — no crash recorded)"
	echo "dmesg lines: $(wc -l < "$T/dmesg.txt" 2>/dev/null || echo 0)"
	echo "last 15 kernel lines:"
	tail -15 "$T/dmesg.txt" 2>/dev/null | sed 's/^/  /'
} > "$T/summary.txt"

tar cf "$OUT" -C "$T" .
chmod 644 "$OUT" 2>/dev/null
cat "$T/summary.txt"
echo "wrote $OUT ($(wc -c < "$OUT") bytes)"