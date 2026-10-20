#!/usr/bin/env bash
# Cycle the port kernel until a boot shows the failure we want to explain.
#
#   hunt.sh <first-run> <last-run> <image>
#
# Each cycle: boot, watch, reboot to stock, pull the logdump, and look for
# the markers of the stall and of the reboot path:
#
#   DIAG gpu_state        the GPU's power transitions
#   DIAG ME_INIT submit   a ringbuffer restart
#   DIAG irq slow         a slow GPU interrupt handler
#   DIAG: kernel_restart_prepare / DIAG: sysrq terminate
#                        the reboot path
#
# Stops when a logdump has the reboot-path markers (the interesting case),
# or when the last run is done, or when the phone stops coming back (a hang
# that needs a power cycle).
set -uo pipefail
SNAP=/home/kurision/development/kernel/ack-kgsl/porting/artifacts/snapshot60
FIRST="${1:?usage: hunt.sh <first-run> <last-run> <image>}"
LAST="${2:?usage: hunt.sh <first-run> <last-run> <image>}"
IMAGE="${3:?usage: hunt.sh <first-run> <last-run> <image>}"
LOG="$SNAP/hunt.log"

for run in $(seq "$FIRST" "$LAST"); do
	img="$SNAP/boot-run$run.img"
	if [ ! -f "$img" ]; then
		echo "$(date -u +%H:%M:%S) run$run: no image, stopping" | tee -a "$LOG"
		exit 1
	fi
	echo "$(date -u +%H:%M:%S) run$run: cycle start" | tee -a "$LOG"
	bash "$SNAP/cycle.sh" "$run" "$img" 260 >>"$LOG" 2>&1
	rc=$?
	echo "$(date -u +%H:%M:%S) run$run: cycle rc=$rc" | tee -a "$LOG"

	dump="$SNAP/run$run-logdump.log"
	if [ -f "$dump" ]; then
		summary="$SNAP/run$run-summary.txt"
		{
			echo "run$run"
			printf "gpu_state=%s\n" "$(grep -c 'DIAG gpu_state' "$dump")"
			printf "me_init=%s\n" "$(grep -c 'DIAG ME_INIT submit' "$dump")"
			printf "irq_slow=%s\n" "$(grep -c 'DIAG irq slow' "$dump")"
			printf "reboot_path=%s\n" "$(grep -cE 'DIAG: kernel_restart_prepare|DIAG: sysrq terminate' "$dump")"
			printf "fence_timeout=%s\n" "$(grep -c 'sync_fence_wait failed' "$dump")"
			printf "checkpoint_reboot=%s\n" "$(grep -c 'Checkpoint commit failed' "$dump")"
			printf "bytes=%s\n" "$(wc -c < "$dump")"
		} > "$summary"
		cat "$summary" | tee -a "$LOG"
		if grep -q 'reboot_path=[1-9]' "$summary"; then
			echo "$(date -u +%H:%M:%S) run$run: the reboot path was reached - stopping" | tee -a "$LOG"
			exit 0
		fi
	else
		echo "$(date -u +%H:%M:%S) run$run: no logdump (rc=$rc)" | tee -a "$LOG"
		if [ "$rc" = "3" ]; then
			echo "$(date -u +%H:%M:%S) run$run: the phone hung and did not come back - stopping" | tee -a "$LOG"
			exit 3
		fi
	fi
done
echo "$(date -u +%H:%M:%S) hunt done" | tee -a "$LOG"
