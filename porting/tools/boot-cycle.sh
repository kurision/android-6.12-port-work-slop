#!/usr/bin/env bash
# One unattended port-boot cycle: clear the logdump, RAM-boot an image,
# watch it, reboot to stock and pull the evidence.
#
#   cycle.sh <run-number> <image> [observe-seconds]
#
# The host stays idle for the first 215 s of the boot, because the early
# hang lives in the 3-9 s window and the evidence for it does not exist
# until the logdump sink does. The poller is started only once adb is up.
#
# If the phone hangs (no adb within the window), the cycle reports it and
# stops: a hung kernel cannot be rebooted from the host, because the USB
# link is gone with it.
set -uo pipefail
REPO=/home/kurision/development/kernel/ack-kgsl
SNAP="$REPO/porting/artifacts/snapshot60"
SERIAL=2819f2320604
RUN="${1:?usage: cycle.sh <run-number> <image> [observe-seconds]}"
IMAGE="${2:?usage: cycle.sh <run-number> <image> [observe-seconds]}"
OBS="${3:-230}"
LOG="$SNAP/run$RUN-cycle.log"

cd "$SNAP"
say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$LOG"; }

say "=== cycle run$RUN image=$(basename "$IMAGE") observe=${OBS}s ==="

# 1. the device must be on stock before we start
for i in $(seq 1 40); do
	ver=$(timeout 10 adb -s "$SERIAL" shell 'uname -r' 2>/dev/null)
	case "$ver" in
	4.19*) break ;;
	esac
	if [ -z "$ver" ]; then
		say "waiting for the device (not on stock yet)"
	fi
	sleep 10
done
ver=$(timeout 10 adb -s "$SERIAL" shell 'uname -r' 2>/dev/null)
case "$ver" in
4.19*) say "on stock: $ver" ;;
*)
	say "ABORT: the device is not on stock ($ver); a hung kernel needs a power cycle"
	exit 2
	;;
esac

# 2. a fresh logdump, so the evidence is this boot's alone
if ! timeout 200 bash "$REPO/porting/logging/clear-logdump.sh" "run$RUN" >>"$LOG" 2>&1; then
	say "ABORT: could not clear the logdump"
	exit 2
fi
say "logdump cleared"

# 3. get to the bootloader and RAM-boot. The phone may already be there
# (a previous cycle was interrupted), and the stock path is the normal one.
if ! timeout 20 fastboot devices | grep -q "$SERIAL"; then
	timeout 60 adb -s "$SERIAL" reboot bootloader >>"$LOG" 2>&1
	# The phone can take a while to reach the bootloader; the fastboot
	# device has to be there before we can boot it.
	for i in $(seq 1 24); do
		if timeout 20 fastboot devices | grep -q "$SERIAL"; then
			break
		fi
		sleep 5
	done
fi
if ! timeout 40 fastboot devices | grep -q "$SERIAL"; then
	say "ABORT: no fastboot device"
	exit 2
fi
timeout 120 fastboot -s "$SERIAL" boot "$IMAGE" >>"$LOG" 2>&1
say "booted; host idle for 215 s"

# 4. no host activity at all while the early window passes
sleep 215

# 5. did it come up?
state=$(timeout 20 adb -s "$SERIAL" get-state 2>&1)
if [ "$state" != "device" ]; then
	say "HUNG: the phone did not come up (adb: $state). It needs a power cycle."
	say "the logdump for this boot is still on the phone; pull it after the power cycle"
	exit 3
fi
say "up: $(timeout 10 adb -s "$SERIAL" shell 'uname -r; cat /proc/uptime' 2>&1 | tr '\n' ' ')"

# 6. watch it, with a poller for this run
POLLER="$SNAP/run$RUN-kgsl-poll.sh"
sed "s#run266-poll#run$RUN-poll#" "$SNAP/run266-kgsl-poll.sh" > "$POLLER"
nohup bash "$POLLER" >"$SNAP/run$RUN-poll.log" 2>&1 &
POLLER_PID=$!
sleep "$OBS"
kill "$POLLER_PID" 2>/dev/null

say "observing done; rebooting to stock"
timeout 60 adb -s "$SERIAL" reboot >>"$LOG" 2>&1
for i in $(seq 1 30); do
	ver=$(timeout 10 adb -s "$SERIAL" shell 'uname -r' 2>/dev/null)
	case "$ver" in
	4.19*)
		say "back on stock"
		break
		;;
	esac
	sleep 10
done

# 7. pull the evidence
if timeout 600 bash "$REPO/porting/logging/pull-run-evidence.sh" "$RUN" "$IMAGE" >>"$LOG" 2>&1; then
	say "evidence pulled: run$RUN-logdump.log"
else
	say "WARNING: the evidence pull failed (see $LOG)"
	exit 4
fi
say "=== cycle run$RUN complete ==="
