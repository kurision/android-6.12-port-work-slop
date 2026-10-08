#!/usr/bin/env python3
"""Snapshot35 init-only newc replacement and exact v0 boot package gates."""
import gzip
import hashlib
import json
import struct
import subprocess
from pathlib import Path

ROOT = Path('/home/kurision/development/kernel/ack-android16-6.12')
ART = Path(__file__).resolve().parent
TAG = ART.name
IMAGE = ROOT / f'porting/artifacts/boot-ack-{TAG}-pidns-probe.img'
CMDLINE = 'androidboot.hardware=qcom msm_rtb.filter=0x237 ehci-hcd.park=3 loop.max_part=7 androidboot.boot_devices=soc@0/7824900.mmc buildvariant=user ignore_loglevel printk.time=1 oops=panic panic=10 androidboot.force_normal_boot=1 rcupdate.rcu_cpu_stall_timeout=10 softlockup_panic=1 hung_task_panic=1 printk.devkmsg=on androidboot.bootdevice=../.. console=tty0 loglevel=8'


def put(path, data):
    with path.open('xb') as out:
        out.write(data)


def newc(raw):
    pos = 0
    rows = []
    while True:
        header = raw[pos:pos + 110]
        assert header[:6] == b'070701'
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        name_end = pos + 110 + fields[11]
        name = raw[pos + 110:name_end]
        assert name.endswith(b'\0')
        data_start = (name_end + 3) & ~3
        data_end = data_start + fields[6]
        end = (data_end + 3) & ~3
        rows.append((name[:-1], pos, data_start, data_end, end, fields))
        pos = end
        if name == b'TRAILER!!!\0':
            return rows, pos


def main():
    old = gzip.decompress((ART / 'base-ramdisk').read_bytes())
    rows, tail = newc(old)
    assert len(rows) == 665
    hits = [r for r in rows if r[0] == b'init']
    assert len(hits) == 1
    _, start, ds, de, end, fields = hits[0]
    assert fields[1] == 0o100755
    replacement = (ART / 'init').read_bytes()
    header = bytearray(old[start:ds])
    header[54:62] = f'{len(replacement):08x}'.encode()
    changed = bytes(header) + replacement + b'\0' * ((-len(replacement)) % 4)
    updated = old[:start] + changed + old[end:]
    after, newtail = newc(updated)
    assert len(after) == len(rows)
    for before, now in zip(rows, after):
        assert before[0] == now[0]
        if before[0] != b'init':
            assert old[before[1]:before[4]] == updated[now[1]:now[4]]
        else:
            assert updated[now[2]:now[3]] == replacement
            expected = before[5][:]
            expected[6] = len(replacement)
            assert now[5] == expected
    assert old[tail:] == updated[newtail:]
    ramdisk = gzip.compress(updated, compresslevel=9, mtime=0)
    put(ART / 'ramdisk.gz', ramdisk)
    kernel = (ART / 'Image.gz-dtb').read_bytes()
    assert kernel == (ART / 'Image.gz').read_bytes() + (ART / 'board.dtb').read_bytes()
    assert (ART / 'board.dtb').read_bytes() == (ART / 'base.dtb').read_bytes()
    args = ['mkbootimg', '--header_version', '0', '--os_version', '17.0.0', '--os_patch_level', '2026-09', '--pagesize', '2048', '--base', '0', '--kernel_offset', '0x80008000', '--ramdisk_offset', '0x81000000', '--second_offset', '0', '--tags_offset', '0x80000100', '--board', '', '--cmdline', CMDLINE, '--kernel', str(ART / 'Image.gz-dtb'), '--ramdisk', str(ART / 'ramdisk.gz'), '--output', str(ART / 'boot-unpadded.img')]
    put(ART / 'mkbootimg-command.json', (json.dumps(args) + '\n').encode())
    result = subprocess.run(args, capture_output=True)
    put(ART / 'mkbootimg.stdout', result.stdout)
    put(ART / 'mkbootimg.stderr', result.stderr)
    put(ART / 'mkbootimg.status', f'{result.returncode}\n'.encode())
    assert result.returncode == 0
    boot = (ART / 'boot-unpadded.img').read_bytes()
    assert len(boot) <= 35964928
    boot += b'\0' * (35964928 - len(boot))
    assert boot[:8] == b'ANDROID!'
    ks, ka, rs, ra, ss, sa, ta, page, version = struct.unpack_from('<9I', boot, 8)
    assert (ks, rs, ss, page, version) == (len(kernel), len(ramdisk), 0, 2048, 0)
    roundup = lambda n: (n + page - 1) // page * page
    roff = page + roundup(ks)
    assert boot[page:page + ks] == kernel
    assert boot[page + ks:roff] == b'\0' * (roff - page - ks)
    assert boot[roff:roff + rs] == ramdisk
    assert not any(boot[roff + rs:])
    ident = hashlib.sha1(kernel + struct.pack('<I', ks) + ramdisk + struct.pack('<I', rs) + struct.pack('<I', 0)).digest() + b'\0' * 12
    assert boot[576:608] == ident
    baseline = (ART / 'baseline-header.bin').read_bytes()
    header = bytearray(boot[:page])
    for lo, hi in [(8, 12), (16, 20), (576, 608)]:
        header[lo:hi] = baseline[lo:hi]
    assert header == baseline
    put(IMAGE, boot)
    report = {'image': str(IMAGE.relative_to(ROOT)), 'size': len(boot), 'sha256': hashlib.sha256(boot).hexdigest(), 'records': len(rows), 'non_init_records_byte_identical': True, 'config_changed': False, 'dtb_byte_identical': True, 'header_only_authorized_fields_changed': True, 'kernel_size': ks, 'ramdisk_size': rs}
    put(ART / 'package-verification.json', (json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
