#!/usr/bin/env bash
# Watch one device for reboots and keep the evidence of each.
#
#   watch-reboots.sh <serial> <outdir> [interval]
#
# It does three things, all read-only with respect to the device:
#
#   1. streams the kernel log (dmesg -w) into a file per boot, so the last
#      lines before a reset are kept;
#   2. samples the boot id, and when it changes, pulls the logdump
#      partition and decodes the reset note the diag init arms there, which
#      says whether the reset was a kernel panic or an orderly shutdown and
#      who asked for it;
#   3. samples the metrics (see metrics-poll.sh) so the state of the
#      machine before the reset is on record.
#
# The logdump pull needs the device to be up again; a reset that leaves it
# in the bootloader is caught when it comes back.
set -uo pipefail

SERIAL="${1:?usage: watch-reboots.sh <serial> <outdir> [interval]}"
OUT="${2:?usage: watch-reboots.sh <serial> <outdir> [interval]}"
INTERVAL="${3:-5}"
REPO=$(cd "$(dirname "$0")/../.." && pwd)

mkdir -p "$OUT"

boot_id() {
	adb -s "$SERIAL" shell 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null |
		tr -d '\r\n'
}

pull_evidence() {
	local tag="$1"
	adb -s "$SERIAL" shell 'dd if=/dev/block/by-name/logdump bs=1M 2>/dev/null' \
		>"$OUT/logdump-$tag.bin" 2>/dev/null
	python3 "$REPO/porting/logging/decode-reset.py" \
		"$OUT/logdump-$tag.bin" >"$OUT/reset-note-$tag.txt" 2>&1
	echo "--- reset note ($tag)" >>"$OUT/reboots.txt"
	head -1 "$OUT/reset-note-$tag.txt" >>"$OUT/reboots.txt"
	strings "$OUT/logdump-$tag.bin" >"$OUT/logdump-$tag.strings.txt" 2>/dev/null
}

# The kernel log of every boot, one file each.
stream_dmesg() {
	local tag="$1"
	adb -s "$SERIAL" shell 'dmesg -w' >"$OUT/dmesg-$tag.txt" 2>&1
}

current="$(boot_id)"
echo "$(date -u +%FT%TZ) watching $SERIAL, boot id $current" >>"$OUT/reboots.txt"
stream_dmesg "$current" &
DMSG_PID=$!

bash "$REPO/porting/tools/metrics-poll.sh" "$SERIAL" "$OUT/metrics.txt" "$INTERVAL" &
METRICS_PID=$!

trap 'kill $DMSG_PID $METRICS_PID 2>/dev/null; exit 0' TERM INT

while true; do
	sleep "$INTERVAL"
	new="$(boot_id)"
	if [ -z "$new" ]; then
		# the device is gone (a reset, or the bootloader)
		echo "$(date -u +%FT%TZ) device not answering" >>"$OUT/reboots.txt"
		continue
	fi
	if [ "$new" != "$current" ]; then
		echo "$(date -u +%FT%TZ) boot id changed $current -> $new" \
			>>"$OUT/reboots.txt"
		pull_evidence "before-$new"
		current="$new"
		stream_dmesg "$current" &
		DMSG_PID=$!
	fi
done
