#!/usr/bin/env bash
# Clear the logdump partition before a temporary boot, prove it worked, and
# archive only the verdict.
#
# The 64 MiB readback is by construction all zeros once the dd succeeds, so
# keeping it costs a gigabyte per dozen runs and proves nothing new. Its sha256
# and the verdict go into the status file; the payload does not.
set -euo pipefail

TAG="${1:?usage: clear-logdump.sh <run-tag>}"
SERIAL="${ADB_SERIAL:-2819f2320604}"
MIB=1048576
DEV=/dev/block/by-name/logdump

{
	echo "== clear $DEV for $TAG"
	echo "-- pull current partition (discarded: it is the previous run's evidence, already archived)"
	before=$(adb -s "$SERIAL" exec-out "su -c 'sha256sum $DEV'" 2>/dev/null | awk '{print $1}')
	echo "pre_clear_sha256=$before"

	echo "-- write zeros"
	adb -s "$SERIAL" shell "su -c 'dd if=/dev/zero of=$DEV bs=$MIB count=64 && sync'" \
		> "${TAG}-preclear.stdout" 2>"${TAG}-preclear.stderr"
	tail -1 "${TAG}-preclear.stdout"

	echo "-- verify readback"
	adb -s "$SERIAL" exec-out "su -c 'dd if=$DEV bs=$MIB count=64'" \
		> "${TAG}-readback.tmp" 2>/dev/null
	python3 - "${TAG}-readback.tmp" <<'EOF'
import sys
from pathlib import Path
raw = Path(sys.argv[1])
blob = raw.read_bytes()[:67108864]
assert len(blob) == 67108864, f'short readback: {len(blob)}'
nonzero = sum(1 for b in blob if b)
assert nonzero == 0, f'{nonzero} non-zero bytes: partition not cleared'
raw.unlink()
print('   readback all zero: OK (payload discarded)')
EOF
	echo "zero_readback=verified_nonzero=0"
	echo "status=0"
} > "${TAG}-preclear.status" 2>&1

cat "${TAG}-preclear.status"
grep -q '^status=0$' "${TAG}-preclear.status" || {
	echo "clear FAILED: see ${TAG}-preclear.status" >&2
	exit 1
}