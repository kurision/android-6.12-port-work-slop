#!/usr/bin/env bash
# From snapshot<number>: ../../logging/pull-run-evidence.sh <run> boot.img
# Capture status and failed pulls stay in scratch, never in the snapshot folder.
set -euo pipefail
exec python3 - "$@" <<'PY'
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import struct
import sys
import tempfile

if len(sys.argv) != 3 or not re.fullmatch(r'[1-9][0-9]*', sys.argv[1]):
    sys.exit('usage: pull-run-evidence.sh <positive-run-number> <image-path>')
folder = Path.cwd()
if not re.fullmatch(r'snapshot[0-9]+', folder.name):
    sys.exit('working directory must be named snapshot<number>')
tag = 'run' + sys.argv[1]
image = Path(sys.argv[2])
if not image.is_file():
    sys.exit(f'image unavailable: {image}')
owned = [folder / (tag + suffix) for suffix in
         ('-logdump.bin', '-logdump.log', '-sd.log', '-sd-unverified.log')]
if any(p.exists() or p.is_symlink() for p in owned):
    sys.exit(f'refusing to overwrite existing {tag} evidence before touching phone')
scratch = Path(tempfile.mkdtemp(prefix='ack-evidence-', dir=os.environ.get('TMPDIR', '/tmp')))
adb = ['adb', '-s', os.environ.get('ADB_SERIAL', '2819f2320604')]
print(f'== {folder.name}/{tag} image={image} sha256={hashlib.sha256(image.read_bytes()).hexdigest()}')
print(f'scratch retained: {scratch}')
# shell-v2 raw transport separates stderr and propagates remote exit status.
# exec-out does neither: dd statistics can contaminate the 64MiB payload.
try:
    features = subprocess.run(adb + ['features'], capture_output=True)
except OSError as exc:
    sys.exit(f'raw/SD unavailable: adb features failed: {exc}; scratch={scratch}')
(scratch / 'adb-features.stdout').write_bytes(features.stdout)
(scratch / 'adb-features.stderr').write_bytes(features.stderr)
if features.returncode or b'shell_v2' not in features.stdout.split():
    sys.exit(f'raw/SD unavailable: shell_v2 required for binary data and remote status; scratch={scratch}')


def pull(command, name):
    path = scratch / name
    with path.open('xb') as out, (scratch / (name + '.stderr')).open('xb') as err:
        try:
            result = subprocess.run(adb + ['shell', '-T', 'su -c ' + shlex.quote(command)], stdout=out, stderr=err)
            return result.returncode == 0, path
        except OSError as exc:
            err.write(str(exc).encode())
            return False, path


def publish(name, data):
    with (folder / (tag + name)).open('xb') as out:
        out.write(data)


def readable(data):
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        return False
    return all(c.isprintable() or c in '\n\r\t' for c in text)


record = re.compile(rb'^[0-9]+,[0-9]+,[0-9]+,[^;\r\n]*;[^\r\n]*\n', re.M)
banner = re.compile(rb'^[0-9]+,[0-9]+,[0-9]+,[^;\r\n]*;Linux version [^\r\n]+\n', re.M)
header = b'DIAG: Android capture ready; handing PID 1 to Android init\n'


def capture_format(data):
    return readable(data) and header in data and record.search(data) is not None


raw_ok, raw_path = pull('dd if=/dev/block/by-name/logdump bs=1048576 count=64', 'logdump.bin')
size = raw_path.stat().st_size
raw_ok = raw_ok and size == 67108864
prefix = b''
if raw_ok:
    blob = raw_path.read_bytes()
    publish('-logdump.bin', blob)
    candidate = blob[:62914560].split(b'\0', 1)[0]
    if readable(candidate):
        prefix = candidate
        publish('-logdump.log', prefix)
        print(f'raw success: {size} bytes; readable prefix: {len(prefix)} bytes')
    else:
        print(f'raw success: {size} bytes; readable prefix unavailable (nontext)')
    for idx, off in ((0, 62914560), (1, 63967232)):
        magic, seq, index, timestamp, offset, length, phys, slot, *reserved = struct.unpack_from('<QQQQ8I', blob, off)
        console = blob[off + 4096:off + 4100]
        valid = (magic == 0x52414d4f and seq > 0 and index == seq
                 and timestamp > 0 and offset == 4096 and length == 1048576
                 and phys == 0x86800000 and slot == idx and not any(reserved)
                 and console == b'DBGC')
        print(f'slot{idx}: magic=0x{magic:08x} seq={seq} timestamp_ns={timestamp} console={console!r} valid={valid}')
else:
    print(f'raw error: retrieval or exact-size validation failed ({size} bytes); retained {raw_path}')

# One root shell owns discovery, any temporary mount, cat, and trap cleanup.
# Compare block device identities as vold may use another node for the same SD.
sd_command = r'''
set -eu
card=''
for node in /sys/class/block/mmcblk*; do
    name=${node##*/}
    case "$name" in mmcblk*[!0-9]*|mmcblk) continue;; esac
    [ "$(cat "$node/device/type" 2>/dev/null)" = SD ] || continue
    [ -z "$card" ] || { echo 'SD unavailable: ambiguous cards' >&2; exit 1; }
    card=$name
done
[ -n "$card" ] || { echo 'SD unavailable: no SD card' >&2; exit 1; }
partition=/dev/block/${card}p1
[ -b "$partition" ] || { echo 'SD unavailable: no first partition' >&2; exit 1; }
identity=$(stat -c '%t:%T' "$partition")
root=''
while read -r source target fs options rest; do
    [ -b "$source" ] || continue
    [ "$(stat -c '%t:%T' "$source")" = "$identity" ] || continue
    [ "$fs" = vfat ] || { echo 'SD unavailable: non-vfat mount' >&2; exit 1; }
    [ -z "$root" ] || { echo 'SD unavailable: ambiguous mounts' >&2; exit 1; }
    root=$target
done < /proc/mounts
if [ -z "$root" ]; then
    root=$(mktemp -d /data/local/tmp/ack-sdpull.XXXXXX)
    mounted=0
    trap '[ "$mounted" = 0 ] || umount "$root"; rmdir "$root"' EXIT
    trap 'exit 1' HUP INT TERM
    mount -t vfat -o ro,nosuid,nodev,noexec "$partition" "$root"
    mounted=1
fi
cat "$root/ack-kmsg.log"
'''
sd_ok, sd_path = pull(sd_command, 'sd.log')
sd = sd_path.read_bytes()
sd_ok = sd_ok and capture_format(sd)
if sd_ok:
    common = min(len(prefix), len(sd))
    shared = prefix[:common]
    verified = (bool(common) and shared == sd[:common] and capture_format(shared)
                and banner.search(shared) is not None)
    publish('-sd.log' if verified else '-sd-unverified.log', sd)
    if verified:
        print(f'SD success: {len(sd)} bytes; common extent matches ({common} bytes including banner/kmsg)')
    else:
        reason = 'mismatch' if common and shared != sd[:common] else 'raw unavailable or common prefix too short'
        print(f'SD unverified: {len(sd)} bytes; {reason}; independent freshness not established')
else:
    print(f'SD unavailable/error: {len(sd)} bytes; command failed or invalid diagnostic capture; retained {sd_path}')
print('USB independently captured; collector does not modify USB evidence')
sys.exit(0 if raw_ok or sd_ok else 1)
PY
