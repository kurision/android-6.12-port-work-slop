#!/system/bin/sh
#
# kgsl-stall-watch.sh - catch the retirement stall on the flashed port kernel.
#
# The stall is a frozen retired count: the GPU stops retiring, so a fence
# that is not already retired is never released and the display waits for
# it forever. This watcher samples the kgsl debugfs event list and, when
# the retired count of a context stops advancing while a fence is still
# pending, it captures the evidence into /data/local/tmp/kgsl-stall/.
#
# It runs on the phone, so it survives the "the phone is dead" case: the
# last capture stays on disk and the next boot's logdump partition has the
# rest.
#
# usage: kgsl-stall-watch.sh [seconds-between-samples]

OUT=/data/local/tmp/kgsl-stall
INTERVAL=${1:-5}
SAMPLES=0

mkdir -p $OUT

sample() {
	# The retired count of every context, and the pending fences.
	cat /sys/kernel/debug/kgsl/events 2>/dev/null
}

stalled=0
frozen=0
prev=""

while :; do
	now=$(sample)
	SAMPLES=$((SAMPLES + 1))
	ts=$(date +%s)

	# The pending fences are the lines with "age=" - they name the
	# context, the timestamp being waited for and the retire count.
	pending=$(echo "$now" | grep "age=")
	# The retired count per context.
	retired=$(echo "$now" | grep "last=")

	if [ -n "$pending" ]; then
		# Is the retired count of the context with a pending fence
		# still moving? Compare against the previous sample.
		for line in $pending; do
			ctx=$(echo "$line" | cut -d: -f1)
			want=$(echo "$line" | grep -o "retired=[0-9]*" | cut -d= -f2)
			have=$(echo "$retired" | grep "^$ctx:" | grep -o "last=[0-9]*" | cut -d= -f2)
			if [ -n "$want" ] && [ -n "$have" ] && [ "$want" = "$have" ]; then
				frozen=$((frozen + 1))
			else
				frozen=0
			fi
			if [ "$frozen" -ge 6 ]; then
				stalled=1
				break
			fi
		done
	fi

	if [ "$stalled" = "1" ]; then
		stalled=0
		frozen=0
		dir=$OUT/stall-$ts
		mkdir -p $dir
		echo "$now" > $dir/kgsl-events.txt
		dmesg > $dir/dmesg.txt 2>&1
		cat /proc/interrupts > $dir/interrupts.txt 2>&1
		cat /proc/softirqs > $dir/softirqs.txt 2>&1
		cat /proc/stat > $dir/stat.txt 2>&1
		cat /proc/uptime > $dir/uptime.txt 2>&1
		ls -lZ /sys/devices/platform/soc@0/1c00000.gpu/kgsl/kgsl-3d0/ \
			> $dir/kgsl-sysfs.txt 2>&1
		for f in gpu_busy_percentage clock_mhz default_pwrlevel max_pwrlevel \
			min_pwrlevel idle_timer force_clk_on force_rail_on; do
			echo "$f = $(cat /sys/devices/platform/soc@0/1c00000.gpu/kgsl/kgsl-3d0/$f 2>&1)" \
				>> $dir/kgsl-sysfs.txt
		done
		echo "stall at $ts" > $dir/SUMMARY
		# Leave the phone's log alone: the logdump partition and the
		# ramoops snapshot have the rest.
		# A marker so the host can see it without adb.
		echo "$ts" > $OUT/LAST-STALL
	fi

	sleep $INTERVAL
done
