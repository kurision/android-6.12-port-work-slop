#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Decode non-sleeping reset markers recovered by the next diagnostic boot."""
import argparse
import json
from pathlib import Path
import struct
import zlib

OFFSET = 0x3F40000
PAGE_SIZE = 4096
CONTAINER_MAGIC = 0x31485441504B4341
PAGE_MAGIC = 0x4B52414D
RECORD_MAGIC = 0x31545352
RECORD = struct.Struct('<IIIIQII16s200sII')
PATHS = {1: 'panic', 2: 'emergency_restart', 3: 'psci_reset', 4: 'pshold'}


def decode_page(page):
    if len(page) != PAGE_SIZE:
        raise ValueError('expected exactly 4096 marker-page bytes')
    magic, boot_id = struct.unpack_from('<II', page, PAGE_SIZE - 8)
    if magic != PAGE_MAGIC:
        raise ValueError('previous marker page has no valid MARK identity; retention unproven')
    records = []
    for path, name in PATHS.items():
        slot = page[0x100 + (path - 1) * RECORD.size:0x100 + path * RECORD.size]
        item = {'path': name, 'status': 'missing'}
        if any(slot):
            magic, version, stored_path, source_boot, ns, cpu, pid, comm, reason, crc, reserved = RECORD.unpack(slot)
            errors = []
            if magic != RECORD_MAGIC:
                errors.append('uncommitted or invalid magic')
            if version != 1:
                errors.append('unsupported version')
            if stored_path != path:
                errors.append('path does not match slot')
            if source_boot != boot_id:
                errors.append('record belongs to another boot')
            if not ns:
                errors.append('zero timestamp')
            if reserved:
                errors.append('nonzero reserved field')
            if zlib.crc32(slot[4:248]) != crc:
                errors.append('record CRC32 mismatch')
            if b'\0' not in comm or b'\0' not in reason:
                errors.append('unterminated text field')
            item['status'] = 'invalid' if errors else 'valid'
            if errors:
                item['errors'] = errors
            else:
                item.update(timestamp_ns=ns, cpu=cpu, pid=pid,
                            comm=comm.split(b'\0', 1)[0].decode(errors='replace'),
                            reason=reason.split(b'\0', 1)[0].decode(errors='replace'))
        records.append(item)
    return {'source_boot_id': f'0x{boot_id:08x}', 'records': records,
            'limit': 'Missing or invalid markers do not establish path nonexecution. '
                     'RAM retention requires a controlled fastboot recovery without an intervening stock boot.'}


def decode_logdump(blob):
    if len(blob) != 67108864:
        raise ValueError('expected exactly 67108864 logdump bytes')
    header = bytearray(blob[OFFSET:OFFSET + 64])
    magic, seq, index, ns, offset, size, phys, slot, version, payload_crc, header_crc, reserved = struct.unpack('<QQQQIIII4I', header)
    if (magic, seq, index, offset, size, phys, slot, version, reserved) != (
            CONTAINER_MAGIC, 0, 0, PAGE_SIZE, PAGE_SIZE, 0x86876000, 0, 1, 0):
        raise ValueError('absent, incomplete or unsupported ACKPATH1 recovery container')
    if not ns:
        raise ValueError('zero recovery timestamp')
    struct.pack_into('<I', header, 56, 0)
    if zlib.crc32(header) != header_crc:
        raise ValueError('recovery header CRC32 mismatch')
    page = blob[OFFSET + offset:OFFSET + offset + size]
    if zlib.crc32(page) != payload_crc:
        raise ValueError('recovery payload CRC32 mismatch')
    report = decode_page(page)
    report.update(recovery_timestamp_ns=ns, recovery_integrity='header-and-payload-CRC32-verified')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--page', action='store_true', help='decode an exact raw 4096-byte marker page instead')
    args = parser.parse_args()
    try:
        report = (decode_page if args.page else decode_logdump)(args.path.read_bytes())
    except (OSError, ValueError) as error:
        parser.exit(1, f'decode-reset-path: {error}\n')
    print(json.dumps(report, indent=2))
    return int(any(r['status'] == 'invalid' for r in report['records']))


if __name__ == '__main__':
    raise SystemExit(main())
