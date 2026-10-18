#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the actual C marker writer/next-boot copy, then corrupt its output."""
import importlib.util
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('reset_path', Path(__file__).with_name('decode-reset-path.py'))
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)


def main():
    source = (ROOT / 'fs/pstore/ram.c').read_text()
    header = (ROOT / 'include/linux/pstore_ram.h').read_text()
    record = re.search(r'struct ramoops_reset_record \{.*?\n\};', header, re.S).group()
    enum = re.search(r'enum ramoops_reset_path \{.*?\n\};', header, re.S).group()
    constants = '\n'.join(re.findall(r'^#define RAMOOPS_(?:RESET_MARK_OFFSET|RESET_MARK_MAGIC|DIAG_MARK_SIZE|DIAG_MARK_HDR|DIAG_MARK_MAGIC)\s+[^\n]+', header, re.M))
    writer = source[source.index('void ramoops_reset_mark('):source.index('EXPORT_SYMBOL_GPL(ramoops_reset_mark);')]
    recovery = source[source.index('static void ramoops_diag_dump_prev(void)'):source.index('\n/*\n * DEBUG run120')]
    harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint32_t __le32;
typedef uint64_t __le64;
typedef long long loff_t;
#define __iomem
#define SZ_4K 4096
#define CONFIG_PSTORE_RAM 1
#define CONFIG_BLOCK 1
#define IS_BUILTIN(x) (x)
#define IS_ENABLED(x) (x)
#define cpu_to_le32(x) (x)
#define cpu_to_le64(x) (x)
#define smp_load_acquire(p) (*(p))
#define wmb() __sync_synchronize()
#define pr_info(...) do {} while (0)
#define pr_err(...) assert(0)
static unsigned char page[4096], ramoops_reset_previous[4096];
static void *ramoops_diag_marks = page;
static bool ramoops_reset_ready, ramoops_reset_capture = true;
static unsigned long ramoops_reset_seen;
static u32 next_boot = 0x12345678;
static u32 get_random_u32(void) { return next_boot; }
static void *ramoops_diag_map(void) { return page; }
static u32 readl(const void *p) { u32 v; memcpy(&v, p, 4); return v; }
#define readl_relaxed readl
static u32 crc32_le(u32 crc, const u8 *data, size_t len) {
    while (len--) {
        crc ^= *data++;
        for (unsigned int i = 0; i < 8; i++)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    return crc;
}
static void writel(u32 v, void *p) {
    if (v == 0x31545352U) {
        assert(readl(p) == 0);
        assert(readl(p + 248) == (crc32_le(~0U, p + 4, 244) ^ ~0U));
    }
    memcpy(p, &v, 4);
}
#define writel_relaxed writel
#define memcpy_toio memcpy
#define memcpy_fromio memcpy
#define memset_io memset
static bool test_and_set_bit(unsigned int bit, unsigned long *bits) {
    unsigned long old = *bits;
    *bits |= 1UL << bit;
    return !!(old & (1UL << bit));
}
static uint64_t ktime_get_mono_fast_ns(void) { return 42000000001ULL; }
static unsigned int raw_smp_processor_id(void) { return 3; }
static struct { char comm[16]; } task = { "reset-check" };
#define current (&task)
#define task_pid_nr(p) 17
#define strscpy(dst, src, len) snprintf(dst, len, "%s", src)
'''
    checks = r'''
int main(void) {
    char reason[320];
    memset(reason, 'P', sizeof(reason));
    reason[sizeof(reason) - 1] = 0;
    ramoops_diag_dump_prev();
    ramoops_reset_mark(RAMOOPS_RESET_PANIC, "disabled");
    assert(readl(page + 0x100) == 0);
    ramoops_reset_ready = true;
    ramoops_reset_mark(0, "invalid");
    ramoops_reset_mark(5, "invalid");
    assert(ramoops_reset_seen == 0);
    ramoops_reset_mark(RAMOOPS_RESET_PANIC, reason);
    ramoops_reset_mark(RAMOOPS_RESET_PANIC, "must not overwrite first panic");
    ramoops_reset_mark(RAMOOPS_RESET_EMERGENCY, NULL);
    ramoops_reset_mark(RAMOOPS_RESET_PSCI, NULL);
    ramoops_reset_mark(RAMOOPS_RESET_PSHOLD, NULL);
    ramoops_reset_ready = false;
    next_boot = 0x87654321;
    ramoops_diag_dump_prev();
    assert(readl(page + 0x100) == 0);
    assert(readl(page + 4092) == next_boot);
    assert(readl(ramoops_reset_previous + 4092) == 0x12345678);
    assert(fwrite(ramoops_reset_previous, 1, 4096, stdout) == 4096);
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='reset-path-check-') as directory:
        c = Path(directory) / 'check.c'
        exe = Path(directory) / 'check'
        c.write_text(harness + constants + '\n' + enum + '\n' + record + '\n' + writer + recovery + checks)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', '-fsanitize=undefined', str(c), '-o', str(exe)], check=True)
        page = subprocess.check_output([str(exe)])
    report = decoder.decode_page(page)
    assert report['source_boot_id'] == '0x12345678'
    assert all(r['status'] == 'valid' for r in report['records'])
    assert report['records'][0]['reason'] == 'P' * 199
    assert report['records'][0]['pid'] == 17 and report['records'][0]['cpu'] == 3
    assert report['records'][1]['reason'] == ''
    missing = bytearray(page)
    missing[0x100:0x200] = bytes(256)
    assert decoder.decode_page(missing)['records'][0]['status'] == 'missing'
    for field, value in [(0, 0), (4, 2), (8, 2), (12, 0xdeadbeef), (24, 99), (252, 1)]:
        broken = bytearray(page)
        struct.pack_into('<I', broken, 0x100 + field, value)
        # Semantic identity checks must work even when CRC is self-consistent.
        if field in (4, 8, 12, 252):
            struct.pack_into('<I', broken, 0x100 + 248, zlib.crc32(broken[0x104:0x1f8]))
        assert decoder.decode_page(broken)['records'][0]['status'] == 'invalid', field
    blob = bytearray(67108864)
    offset = decoder.OFFSET
    struct.pack_into('<QQQQIIII4I', blob, offset, decoder.CONTAINER_MAGIC,
                     0, 0, 7000000000, 4096, 4096, 0x86876000, 0, 1, zlib.crc32(page), 0, 0)
    struct.pack_into('<I', blob, offset + 56, zlib.crc32(blob[offset:offset + 64]))
    blob[offset + 4096:offset + 8192] = page
    assert decoder.decode_logdump(blob)['records'][0]['reason'] == 'P' * 199
    for broken in [blob[:-1], bytes(67108864)]:
        try:
            decoder.decode_logdump(broken)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted absent or short recovery container')
    for at in [offset + 24, offset + 4096 + 64]:
        broken = bytearray(blob)
        broken[at] ^= 1
        try:
            decoder.decode_logdump(broken)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted corrupt recovery container')
    print('reset path: actual C write/first-event retention/next-boot copy, identity, truncation, torn records and recovery CRC checks passed')


if __name__ == '__main__':
    main()
