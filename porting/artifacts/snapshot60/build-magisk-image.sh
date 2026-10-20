#!/usr/bin/env bash
# Build a boot image that runs the port kernel with Magisk in front of the
# port's diag init.
#
#   build-magisk-image.sh <port-boot.img> <out.img> <kdir> <dtb>
#
# The port image's ramdisk keeps the stock's ramdisk with the port's diag init
# as /init. Magisk's magiskinit replaces /init and execs the original init
# from /init.real (or /system/bin/init), so:
#
#   /init      -> magiskinit
#   /init.real -> the port's diag init
#
# Either way the phone boots: if magiskinit prefers /system/bin/init the ROM's
# init runs, and the port's harness is skipped. If it prefers /init.real the
# port's harness runs and magiskd is up, so the shell has root.
set -euo pipefail
SRC="${1:?usage: build-magisk-image.sh <port-boot.img> <out.img> <kdir> <dtb>}"
OUT="${2:?usage: build-magisk-image.sh <port-boot.img> <out.img> <kdir> <dtb>}"
KDIR="${3:?usage: build-magisk-image.sh <port-boot.img> <out.img> <kdir> <dtb>}"
DTB="${4:?usage: build-magisk-image.sh <port-boot.img> <out.img> <kdir> <dtb>}"
SNAP=/home/kurision/development/kernel/ack-kgsl/porting/artifacts/snapshot60
M="$SNAP/magisk-files"
T=/home/kurision/development/kernel/Lucifer-AnyKernel3/tools
WORK=/tmp/opencode/magisk-build

rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"
cp "$T/magiskboot" "$T/magiskpolicy" .
chmod +x magiskboot magiskpolicy

echo "== unpack the port image"
./magiskboot unpack "$SRC"
test -s kernel
test -s ramdisk.cpio
cp ramdisk.cpio ramdisk.cpio.work

echo "== the port kernel + dtb"
cat "$KDIR/Image.gz" "$DTB" > kernel
ls -l kernel

echo "== keep the port's diag init as /init.real"
cp "$SNAP/init-run257" init257
file init257 | head -1

echo "== Magisk's files"
cp "$M/magiskinit" .
cp "$M/magisk64" magisk
cp "$M/magisk32" .
cp "$M/init-ld" .
cp "$M/stub.apk" .
./magiskboot compress=xz magisk magisk.xz
./magiskboot compress=xz stub.apk stub.xz
./magiskboot compress=xz init-ld init-ld.xz

cat > config <<'EOF'
KEEPVERITY=1
KEEPFORCEENCRYPT=1
RECOVERYMODE=0
VENDORBOOT=0
EOF

echo "== the sepolicy: allow the suspend service to read the 6.12 suspend stats"
# The ROM's policy (Android 17 EvoX) was written for a 4.19 CAF kernel, which
# has no /sys/power/suspend_stats. The 6.12 kernel has them, they land on the
# generic sysfs type, and the ROM's policy denies system_suspend from reading
# them - 460 denials a boot, and the checkpoint commit that follows fails, so
# system_server asks for a reboot and the phone is left half dead.
#
# The ramdisk's sepolicy is the policy Magisk applies to the live one at
# boot, so the rules go in there - the same place the AnyKernel3 script puts
# its magiskpolicy line.
python3 /tmp/opencode/cpio-extract.py ramdisk.cpio.work sepolicy sepolicy.bin
test -s sepolicy.bin
# The host's magiskpolicy is MagiskBoot 20.4 and cannot parse the ROM's
# Android-17 policy. The device's own magiskpolicy can, so the policy patch
# is done on the device once it is rooted; see patch-sepolicy-on-device.sh.
if ./magiskpolicy --load sepolicy.bin --save sepolicy.bin \
	"allow system_suspend sysfs:file (getattr open read)" \
	"allow system_suspend sysfs_battery_supply:file (getattr open read)" \
	"allow system_suspend sysfs_usb_supply:file (getattr open read)" \
	"allow system_suspend sysfs:dir (search getattr open read)" \
	2>/dev/null; then
	echo "   the sepolicy was patched here"
	SEPOLICY_PATCHED=1
else
	echo "   the host magiskpolicy cannot parse this policy; it is patched on the device"
	SEPOLICY_PATCHED=0
fi
ls -l sepolicy.bin

echo "== patch the ramdisk"
./magiskboot cpio ramdisk.cpio.work \
"add 0750 init.real init257" \
"add 0750 init magiskinit" \
"mkdir 0750 overlay.d" \
"mkdir 0750 overlay.d/sbin" \
"add 0644 overlay.d/sbin/magisk.xz magisk.xz" \
"add 0644 overlay.d/sbin/stub.xz stub.xz" \
"add 0644 overlay.d/sbin/init-ld.xz init-ld.xz" \
"add 0600 sepolicy sepolicy.bin" \
"patch" \
"mkdir 000 .backup" \
"add 000 .backup/.magisk config" \
|| { echo "the ramdisk patch failed (a segfault after the dump is harmless)"; }
./magiskboot cpio ramdisk.cpio.work test || true

echo "== the ramdisk now has"
./magiskboot cpio ramdisk.cpio.work list 2>/dev/null || true
python3 /tmp/opencode/cpio-list.py ramdisk.cpio.work 2>/dev/null | \
	grep -E "init|magisk|backup|overlay" | head -20

cp ramdisk.cpio.work ramdisk.cpio
rm -f init257 magisk magisk32 init-ld stub.apk *.xz config

echo "== repack"
./magiskboot repack "$SRC" "$OUT"
ls -l "$OUT"
sha256sum "$OUT"
echo "== the image's cmdline and the ramdisk's init"
python3 - "$SRC" "$OUT" <<'PY'
import struct, sys
for p in sys.argv[1:]:
    d = open(p, "rb").read()
    cmd = d[64:64+512].split(b"\0")[0].decode(errors="replace")
    print(f"{p}: cmdline={cmd[:110]}...")
    print(f"   kernel_size={struct.unpack_from('<I', d, 8)[0]} ramdisk_size={struct.unpack_from('<I', d, 16)[0]}")
PY
