#!/usr/bin/env bash
# Pull every diagnostic channel after one temporary boot and name it for the
# snapshot and run. Run from the snapshot artifact directory:
#   ../../logging/pull-run-evidence.sh 5 boot-ack-snapshot39-daemon-probe.img
#
# The 64 MiB payloads that carry no verdict are deleted as they are verified;
# their sha256 and the verdict itself are what get archived.
set -euo pipefail

RUN="${1:?usage: pull-run-evidence.sh <run-number> <image-name>}"
IMG="${2:?usage: pull-run-evidence.sh <run-number> <image-name>}"
TAG="snapshot${SNAPSHOT:-39}-run${RUN}"
DIR="$(pwd)"
SERIAL="${ADB_SERIAL:-2819f2320604}"
MIB=1048576

echo "== $TAG ($IMG)"
sha256sum "$(dirname "$DIR")/$IMG"

echo "-- logdump partition (evidence, kept)"
adb -s "$SERIAL" exec-out "su -c 'dd if=/dev/block/by-name/logdump bs=$MIB count=64'" \
	> "${TAG}-logdump.bin.raw" 2>/dev/null
python3 - "${TAG}-logdump.bin.raw" "${TAG}-logdump.bin" <<'EOF'
import sys
from pathlib import Path
raw, out = Path(sys.argv[1]), Path(sys.argv[2])
data = raw.read_bytes()[:67108864]
assert len(data) == 67108864, f'short pull: {len(data)}'
out.write_bytes(data)
raw.unlink()
print(f'   {out.name}: {len(data)} bytes')
EOF

echo "-- SD card"
adb -s "$SERIAL" shell 'su -c "mkdir -p /data/local/tmp/sdpull"' >/dev/null
SDROOT=""
if adb -s "$SERIAL" shell 'su -c "mount -t vfat -o ro /dev/block/mmcblk1p1 /data/local/tmp/sdpull"' >/dev/null 2>&1; then
	SDROOT=/data/local/tmp/sdpull
elif adb -s "$SERIAL" shell 'su -c "grep vfat /proc/mounts"' | grep -q vold; then
	SDROOT="$(adb -s "$SERIAL" shell 'su -c "grep vfat /proc/mounts"' | awk '{print $2; exit}')"
fi
if [ -n "$SDROOT" ]; then
	for f in snapshot28-kmsg.log ramoops-a.bin ramoops-b.bin; do
		adb -s "$SERIAL" exec-out "su -c 'cat $SDROOT/$f'" > "${TAG}-sd-$f" 2>/dev/null || true
		[ -e "${TAG}-sd-$f" ] && printf '   %s %s bytes\n' "${TAG}-sd-$f" "$(wc -c < "${TAG}-sd-$f")"
	done
	adb -s "$SERIAL" shell 'su -c "umount /data/local/tmp/sdpull; rmdir /data/local/tmp/sdpull"' >/dev/null 2>&1 || true
else
	echo "   SD card unavailable; logdump remains the authoritative channel" >&2
fi

echo "-- kernel snapshot slots"
python3 - "${TAG}-logdump.bin" "$TAG" <<'EOF'
import sys
from pathlib import Path
blob = Path(sys.argv[1]).read_bytes()
tag = sys.argv[2]
for idx, off in ((0, 62914560), (1, 63967232)):
    magic = int.from_bytes(blob[off:off + 4], 'little')
    payload = blob[off + 4096:off + 4096 + 1048576]
    valid = magic == 0x52414d4f and payload[:4] == b'DBGC'
    print(f'   slot{idx}: magic=0x{magic:08x} console_sig={payload[:4]!r} valid={valid}')
    if valid:
        Path(f'{tag}-kernel-snapshot-slot{idx}.bin').write_bytes(payload)
        continue
    raise SystemExit(f'slot{idx} invalid: refusing to treat it as evidence')
EOF

echo "-- summary"
printf '   probe lines: %s\n' "$(grep -ac 'DIAG: daemon' "${TAG}-logdump.bin" || true)"
grep -a 'DIAG: procdir' "${TAG}-logdump.bin" | sed 's/^/   /' || true
grep -a 'DIAG: proccomm' "${TAG}-logdump.bin" | cut -c1-2000 | sed 's/^/   /' || true