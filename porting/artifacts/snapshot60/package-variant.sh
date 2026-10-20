#!/usr/bin/env bash
# Package a command-line variant of an existing kernel. No kernel build:
# the same Image.gz and DTB, the same base image, the same ramdisk and init,
# only the command line changes.
#
#   package-variant.sh <run> <source-kdir> <extra-cmdline>
#
# Example:
#   package-variant.sh 274 kdir-run273 "hardlockup_panic=1"
set -euo pipefail
REPO=/home/kurision/development/kernel/ack-kgsl
cd "$REPO"
SNAP="$REPO/porting/artifacts/snapshot60"
OUT_DIR=/home/kurision/development/kernel/ack-out-run261
BOOT="$OUT_DIR/arch/arm64/boot"

RUN="${1:?usage: package-variant.sh <run> <source-kdir> <extra-cmdline>}"
SRC="${2:?usage: package-variant.sh <run> <source-kdir> <extra-cmdline>}"
EXTRA="${3:-}"

out="$SNAP/boot-run$RUN.img"
report="$SNAP/package-run$RUN.json"
kdir="$SNAP/kdir-run$RUN"
test ! -e "$out"
test ! -e "$report"
test ! -e "$kdir"
test -f "$SNAP/$SRC/Image.gz"
test -f "$SNAP/$SRC/msm8953-xiaomi-tissot.dtb"
test -f "$SNAP/boot-run258.img"
test -f "$SNAP/init-run257"

mkdir "$kdir"
cp "$SNAP/$SRC/Image.gz" "$kdir/Image.gz"
cp "$SNAP/$SRC/msm8953-xiaomi-tissot.dtb" "$kdir/msm8953-xiaomi-tissot.dtb"
( cd "$kdir" && sha256sum Image.gz msm8953-xiaomi-tissot.dtb > SHA256SUMS )

python3 -B porting/logging/package-diag-boot.py --base-image "$SNAP/boot-run258.img" \
 --kernel-dir "$kdir" --stage-kernel "$BOOT" --init "$SNAP/init-run257" \
 --keep-stock-console ${EXTRA:+--append-cmdline " $EXTRA"} \
 --out "$out" --report "$report" >/dev/null

python3 - "$report" "${4:-$SNAP/package-run267.json}" <<'PY'
import json, sys, pathlib
new = json.loads(pathlib.Path(sys.argv[1]).read_text())
old = json.loads(pathlib.Path(sys.argv[2]).read_text())
for k in ('ramdisk_sha256', 'init_sha256', 'kernel_payload_sha256'):
    assert new[k] == old[k], k
print('cmdline tail:', new['cmdline'][-90:])
print('image sha256:', new['sha256'])
PY
