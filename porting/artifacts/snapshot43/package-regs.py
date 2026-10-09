#!/usr/bin/env python3
"""Snapshot43 run 2: same ramdisk and header as run 1, new kernel payload.

Reuses the run-1 image's ramdisk (init + all other cpio records, byte
identical) and header baseline, so the only difference from run 1 is the
kernel: out-snapshot43/arch/arm64/boot/Image.gz-dtb (register capture added).
"""
import hashlib
import json
import struct
import subprocess
from pathlib import Path

ROOT = Path('/home/kurision/development/kernel/ack-android16-6.12')
ART = ROOT / 'porting/artifacts/snapshot43'
OUT = ROOT / 'out-snapshot43'
IMAGE = ROOT / 'porting/artifacts/boot-ack-snapshot43-regs.img'
CMDLINE = ('androidboot.hardware=qcom msm_rtb.filter=0x237 ehci-hcd.park=3 '
           'loop.max_part=7 androidboot.boot_devices=soc@0/7824900.mmc '
           'buildvariant=user ignore_loglevel printk.time=1 oops=panic panic=10 '
           'androidboot.force_normal_boot=1 rcupdate.rcu_cpu_stall_timeout=10 '
           'softlockup_panic=1 hung_task_panic=1 printk.devkmsg=on '
           'androidboot.bootdevice=../.. console=tty0 loglevel=8')

ramdisk = (ART / 'run1-ramdisk.gz').read_bytes()
kernel = (OUT / 'arch/arm64/boot/Image.gz-dtb').read_bytes()
assert kernel == (OUT / 'arch/arm64/boot/Image.gz').read_bytes() + \
    (OUT / 'arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb').read_bytes()

run1 = (ART / 'boot.img').read_bytes()
ks, ka, rs, ra, ss, sa, ta, page, ver = struct.unpack_from('<9I', run1, 8)
roundup = lambda n: (n + page - 1) // page * page
roff = page + roundup(ks)
assert run1[roff:roff + rs] == ramdisk, 'run-1 ramdisk must be reused exactly'
baseline = run1[:page]

args = ['mkbootimg', '--header_version', '0', '--os_version', '17.0.0',
        '--os_patch_level', '2026-09', '--pagesize', '2048', '--base', '0',
        '--kernel_offset', '0x80008000', '--ramdisk_offset', '0x81000000',
        '--second_offset', '0', '--tags_offset', '0x80000100', '--board', '',
        '--cmdline', CMDLINE, '--kernel', str(OUT / 'arch/arm64/boot/Image.gz-dtb'),
        '--ramdisk', str(ART / 'run1-ramdisk.gz'), '--output', str(ART / 'boot-unpadded.img')]
(ART / 'mkbootimg-command.json').write_text(json.dumps(args) + '\n')
result = subprocess.run(args, capture_output=True)
(ART / 'mkbootimg.stdout').write_bytes(result.stdout)
(ART / 'mkbootimg.stderr').write_bytes(result.stderr)
(ART / 'mkbootimg.status').write_text(f'{result.returncode}\n')
assert result.returncode == 0, result.stderr.decode()

boot = (ART / 'boot-unpadded.img').read_bytes()
size = (len(boot) + page - 1) // page * page
assert size <= 67108864, f'{size} exceeds the boot_a partition'
boot += b'\0' * (size - len(boot))
assert boot[:8] == b'ANDROID!'
nks, nka, nrs, nra, nss, nsa, nta, npage, nver = struct.unpack_from('<9I', boot, 8)
assert (nrs, nss, npage, nver) == (rs, 0, page, ver)
assert nks < ks, 'kernel shrank?'
nroff = npage + roundup(nks)
assert boot[npage:npage + nks] == kernel
assert boot[npage + nks:nroff] == b'\0' * (nroff - npage - nks)
assert boot[nroff:nroff + nrs] == ramdisk
assert not any(boot[nroff + nrs:])
ident = hashlib.sha1(kernel + struct.pack('<I', nks) + ramdisk +
                     struct.pack('<I', nrs) + struct.pack('<I', 0)).digest() + b'\0' * 12
assert boot[576:608] == ident

header = bytearray(boot[:page])
for lo, hi in [(8, 12), (16, 20), (576, 608)]:
    header[lo:hi] = baseline[lo:hi]
assert header == baseline, 'header differs from run 1 beyond authorized fields'
IMAGE.write_bytes(boot)

report = {
    'image': str(IMAGE.relative_to(ROOT)),
    'size': len(boot),
    'sha256': hashlib.sha256(boot).hexdigest(),
    'kernel_payload_sha256': hashlib.sha256(kernel).hexdigest(),
    'ramdisk_identical_to_run1': True,
    'header_identical_outside_authorized_fields': True,
    'kernel_size': nks,
    'kernel_size_run1': ks,
    'ramdisk_size': nrs,
    'change': 'bounded post-SMC register capture (x0..x7, 3 attempts, owner-48 svc-0)',
}
(ART / 'package-verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
