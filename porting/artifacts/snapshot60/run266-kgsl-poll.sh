#!/usr/bin/env bash
# Sample the GPU stall state every few seconds during a live port boot.
#
# Everything here is shell-readable on the port kernel: /proc/interrupts gives
# the GPU's interrupt rate (the retirement signal), /proc/stat and /proc/loadavg
# give the CPU load, the cpufreq policy shows the frequency, and the kgsl
# sysfs tree is world-readable (the debugfs "events" node is not: adbd runs as
# "shell" and debugfs is 0700, and this kernel has no su).
set -u
SNAP="$(cd "$(dirname "$0")" && pwd)"
OUT="$SNAP/run266-poll"
mkdir -p "$OUT"
SERIAL=2819f2320604
KG=/sys/devices/platform/soc@0/1c00000.gpu/kgsl/kgsl-3d0
i=0
while [ $i -lt 300 ]; do
	i=$((i + 1))
	ts=$(date -u +%H:%M:%S)
	f="$OUT/sample-$(printf '%04d' $i)-$ts.txt"
	{
		echo "=== $ts sample $i ==="
		adb -s "$SERIAL" shell "
			echo --uptime--; cat /proc/uptime; cat /proc/loadavg
			echo --stat--; head -n 9 /proc/stat
			echo --gpu-irq--; grep -iE 'kgsl|adreno|gpu' /proc/interrupts
			echo --cpufreq--; for p in /sys/devices/system/cpu/cpufreq/policy*; do
				echo POLICY=\$p; cat \$p/related_cpus \$p/scaling_cur_freq \$p/scaling_governor 2>/dev/null; done
			echo --kgsl-basic--; for f in gpu_busy_percentage gpubusy clock_mhz gpu_clock_stats max_clock_mhz min_clock_mhz num_pwrlevels default_pwrlevel current_pwrlevel ft_hang_intr_status; do
				printf '%s=' \$f; cat $KG/\$f 2>/dev/null || echo N/A; done
			echo --kgsl-snapshot-ls--; ls -l $KG/snapshot/ 2>&1 | head -40
			echo --kgsl-snapshot--; for f in $KG/snapshot/*; do
				echo \"### \$(basename \$f)\"; cat \$f 2>&1 | head -60; done
			echo --kgsl-dispatch--; ls -l $KG/dispatch/ 2>&1 | head; cat $KG/dispatch/* 2>&1 | head -30
			echo --kgsl-perf--; ls $KG/perfcounter/ 2>&1 | head -20
		" 2>&1
	} > "$f" 2>&1
	sleep 3
done
