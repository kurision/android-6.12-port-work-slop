#!/usr/bin/env bash
# Sample the kernel-side metrics of the running port kernel.
#
#   metrics-poll.sh <serial> <outfile> [interval]
#
# Read-only. Every sample is one block of "key value" lines, so a reboot
# shows up as a drop of the uptime and a new boot id, and the block before
# it holds the last state of the machine.
set -uo pipefail

SERIAL="${1:?usage: metrics-poll.sh <serial> <outfile> [interval]}"
OUT="${2:?usage: metrics-poll.sh <serial> <outfile> [interval]}"
INTERVAL="${3:-5}"

sample() {
	local stamp
	stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
	{
		echo "=== $stamp"
		adb -s "$SERIAL" shell '
			echo "uptime $(cut -d" " -f1 /proc/uptime)"
			echo "boot_id $(cat /proc/sys/kernel/random/boot_id)"
			echo "state $(getprop sys.boot_completed) $(getprop dev.bootcomplete)"
			echo "cpufreq $(for p in /sys/devices/system/cpu/cpufreq/policy*; do printf "%s:%s/%s " "$(basename $p)" "$(cat $p/scaling_cur_freq 2>/dev/null)" "$(cat $p/scaling_max_freq 2>/dev/null)"; done)"
			echo "cpu_stat $(head -1 /proc/stat)"
			echo "loadavg $(cat /proc/loadavg)"
			echo "mem $(grep -E "MemTotal|MemAvailable|Slab|SReclaimable" /proc/meminfo | tr "\n" " ")"
			echo "temp $(for z in /sys/class/thermal/thermal_zone*; do printf "%s=%s " "$(cat $z/type 2>/dev/null)" "$(cat $z/temp 2>/dev/null)"; done)"
			echo "batt $(cat /sys/class/power_supply/battery/current_now 2>/dev/null) $(cat /sys/class/power_supply/battery/status 2>/dev/null) $(cat /sys/class/power_supply/battery/capacity 2>/dev/null)"
			echo "gpu $(cat /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq 2>/dev/null) $(cat /sys/class/kgsl/kgsl-3d0/gpu_busy_percentage 2>/dev/null) $(cat /sys/class/kgsl/kgsl-3d0/gpu_clock 2>/dev/null)"
			echo "icc $(cat /sys/kernel/debug/interconnect/interconnect_summary 2>/dev/null | tr "\n" "|")"
			echo "icc_err $(dmesg | grep -ciE "qcom_icc|interconnect.*error|icc.*failed" 2>/dev/null)"
			echo "rpm_err $(dmesg | grep -ciE "smd_rpm|rpm.*error|icc_units" 2>/dev/null)"
			echo "watchdog $(dmesg | grep -ciE "watchdog|petting|sysrq" 2>/dev/null)"
			echo "hung $(dmesg | grep -ciE "hung task|soft lockup|rcu.*stall|BUG:|Oops|Call Trace|panic" 2>/dev/null)"
			echo "oops_tail $(dmesg | grep -iE "BUG:|Oops|Call Trace|panic|watchdog|hung task|soft lockup|rcu.*stall|Unable to handle|reboot|restart" | tail -5 | tr "\n" "|")"
			echo "tail $(dmesg | tail -3 | tr "\n" "|")"
		' 2>&1
	} >>"$OUT"
}

trap 'exit 0' TERM INT
while true; do
	sample
	sleep "$INTERVAL"
done
