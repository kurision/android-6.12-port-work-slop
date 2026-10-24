#!/usr/bin/env bash
# High-resolution CPU frequency phase trace for the schedutil A/B study.
#
#   freq-phase-trace.sh <serial> <outfile> [duration_s] [interval_s]
#
# Samples uptime, current cpufreq frequency and the aggregate /proc/stat CPU
# line every 500 ms. Run it twice per kernel — once while the phone is being
# used normally, once while it sits idle — and note the host start time of
# each run so the phases can be split. Read-only on the device.
set -uo pipefail
SERIAL="${1:?usage: freq-phase-trace.sh <serial> <outfile> [duration_s] [interval_s]}"
OUT="${2:?usage: freq-phase-trace.sh <serial> <outfile> [duration_s] [interval_s]}"
DURATION="${3:-360}"
INTERVAL="${4:-0.5}"
POLICY="${POLICY:-/sys/devices/system/cpu/cpufreq/policy0}"

echo "# start_utc $(date -u +%Y-%m-%dT%H:%M:%SZ) kernel $(adb -s "$SERIAL" shell uname -r | tr -d '\r')" >>"$OUT"
adb -s "$SERIAL" shell "
	while [ \$SECONDS -lt $DURATION ]; do
		printf '%s %s %s\n' \
			\"\$(cut -d' ' -f1 /proc/uptime)\" \
			\"\$(cat $POLICY/scaling_cur_freq)\" \
			\"\$(head -1 /proc/stat | cut -d' ' -f2- | tr ' ' '_')\"
		sleep $INTERVAL
	done
" >>"$OUT"
echo "# end_utc $(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$OUT"
