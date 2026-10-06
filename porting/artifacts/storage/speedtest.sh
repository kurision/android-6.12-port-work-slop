#!/bin/sh
# Storage throughput test for the porting logs.
#
#   doas sh speedtest.sh [size_MiB] [test_dir]
#
# test_dir MUST be on the filesystem you want to measure — on this device /tmp is
# tmpfs (RAM), so a test file there measures memory, not the card. Defaults to the
# root filesystem of whichever device pmos is installed on.
#
# Writes a bounded temporary file, measures sequential write and read, then
# removes it. Reads are only meaningful with the page cache dropped.
set -u

SIZE=${1:-1024}
TESTDIR=${2:-/}
TEST="$TESTDIR/.iotest.bin"
MB=1048576

mbps() { sed -n 's/.*, \([0-9.]*\)\(MB\|GB\)\/s.*/\1/p' | tail -1; }

echo "=== device inventory ==="
printf '%-14s %10s %6s %s\n' name size_MiB ro model
for b in /sys/block/mmcblk*; do
	[ -e "$b" ] || continue
	n=$(basename "$b")
	sz=$(( $(cat "$b/size") * 512 / MB ))
	ro=$(cat "$b/ro")
	mdl=""
	for f in name cid manfid oemid date; do
		[ -r "$b/device/$f" ] && mdl="$mdl $(cat "$b/device/$f")"
	done
	[ -r "$b/device/vendor" ] && mdl="$mdl $(cat "$b/device/vendor")"
	printf '%-14s %10s %6s %s\n' "$n" "$sz" "$ro" "${mdl# }"
done

echo
echo "=== mmc bus timing ==="
for d in /sys/kernel/debug/mmc*; do
	[ -r "$d/ios" ] || continue

	{ echo "-- $d"; sed -e 's/^\t*/  /' "$d/ios" | grep -E "actual clock|bus width|timing spec|signal voltage"; } 2>/dev/null
done

echo
echo "=== filesystem usage ==="
df -h 2>/dev/null | sed -n '1,6p'
echo "test file will be created in $TESTDIR on $(df -h "$TESTDIR" 2>/dev/null | tail -1 | awk '{print $1}')"

echo
echo "=== sequential, ${SIZE} MiB ==="
sync
w_out=$(dd if=/dev/zero of="$TEST" bs=1M count="$SIZE" conv=fsync 2>&1)
echo "$w_out" | tail -2
w=$(printf '%s' "$w_out" | mbps)

sync
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
r_out=$(dd if="$TEST" of=/dev/null bs=1M 2>&1)
echo "$r_out" | tail -2
r=$(printf '%s' "$r_out" | mbps)

rm -f "$TEST"
sync

echo
echo "=== 4 KiB blocks, 64 MiB ==="
b_out=$(dd if=/dev/zero of="$TEST" bs=4k count=16384 conv=fsync 2>&1)
echo "$b_out" | tail -2
bw=$(printf '%s' "$b_out" | mbps)
sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
br_out=$(dd if="$TEST" of=/dev/null bs=4k 2>&1)
echo "$br_out" | tail -2
br=$(printf '%s' "$br_out" | mbps)
rm -f "$TEST"
sync

echo
echo "=== result ==="
printf 'sequential write : %s MB/s\n' "${w:-?}"
printf 'sequential read  : %s MB/s\n' "${r:-?}"
printf '4k-block write   : %s MB/s\n' "${bw:-?}"
printf '4k-block read    : %s MB/s\n' "${br:-?}"
echo "done"