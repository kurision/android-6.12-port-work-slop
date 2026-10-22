#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise ION's production partial-sync helper with a merged IOVA mapping."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "drivers/staging/android/ion/ion.c"


class IonPartialSync(unittest.TestCase):
    def test_callers_pass_original_entries(self):
        calls = re.findall(r"ion_sgl_sync_(?:range|mapped)\(([^;]+)\);",
                           SOURCE.read_text())
        table_calls = [call for call in calls if "table->sgl" in call]
        self.assertEqual(len(table_calls), 8)
        for call in table_calls:
            self.assertIn("table->orig_nents", call)

    def test_partial_sync_preserves_physical_boundaries(self):
        helper = re.search(r"static int ion_sgl_sync_range\(.*?^\}",
                           SOURCE.read_text(), re.M | re.S)[0]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <errno.h>
typedef uint64_t dma_addr_t;
enum dma_data_direction { DMA_TO_DEVICE, DMA_FROM_DEVICE, DMA_BIDIRECTIONAL };
struct device { int unused; };
struct scatterlist {
    unsigned int length, dma_length;
    dma_addr_t dma_address, physical;
};
#define sg_dma_len(sg) ((sg)->dma_length)
#define sg_dma_address(sg) ((sg)->dma_address)
#define for_each_sg(sgl, sg, nents, i) \
    for ((i) = 0, (sg) = (sgl); (i) < (int)(nents); (i)++, (sg)++)
#define pr_warn_ratelimited(...) ((void)0)
static struct scatterlist entries[] = {
    { 0x20000, 0x60000, 0xc6800000, 0x814b0000 },
    { 0x10000, 0, 0, 0x90000000 },
    { 0x30000, 0, 0, 0xb0000000 },
};
static unsigned int count;
static bool expect_cpu;
static enum dma_data_direction expect_dir;
static struct { dma_addr_t addr; unsigned long size; } calls[3];

static void sync_range(struct device *dev, dma_addr_t addr,
                       unsigned long offset, unsigned long size,
                       enum dma_data_direction dir, bool for_cpu)
{
    dma_addr_t cursor = entries[0].dma_address;
    unsigned int i;
    (void)dev;
    addr += offset;
    assert(for_cpu == expect_cpu && dir == expect_dir);
    assert(size && count < 3);
    /* Model the IOMMU backend: translate the start, then sync a physical span. */
    for (i = 0; i < 3; i++) {
        if (addr >= cursor && addr < cursor + entries[i].length) {
            unsigned long within = addr - cursor;
            assert(size <= entries[i].length - within);
            assert(entries[i].physical + within + size <=
                   entries[i].physical + entries[i].length);
            calls[count].addr = addr;
            calls[count++].size = size;
            return;
        }
        cursor += entries[i].length;
    }
    assert(0 && "sync outside mapping");
}
#define dma_sync_single_range_for_cpu(d, a, o, s, dir) \
    sync_range(d, a, o, s, dir, true)
#define dma_sync_single_range_for_device(d, a, o, s, dir) \
    sync_range(d, a, o, s, dir, false)
'''
        cases = r'''
static int run(unsigned long offset, unsigned long length)
{
    count = 0;
    return ion_sgl_sync_range(NULL, entries, 3, offset, length,
                              expect_dir, expect_cpu);
}

int main(void)
{
    unsigned int cpu, dir;
    for (cpu = 0; cpu < 2; cpu++) {
        expect_cpu = cpu;
        for (dir = 0; dir < 3; dir++) {
            expect_dir = dir;
            assert(run(0, 0x60000) == 0 && count == 3);
            assert(calls[0].addr == 0xc6800000 && calls[0].size == 0x20000);
            assert(calls[1].addr == 0xc6820000 && calls[1].size == 0x10000);
            assert(calls[2].addr == 0xc6830000 && calls[2].size == 0x30000);
            assert(run(0x1f000, 0x12000) == 0 && count == 3);
            assert(calls[0].addr == 0xc681f000 && calls[0].size == 0x1000);
            assert(calls[1].addr == 0xc6820000 && calls[1].size == 0x10000);
            assert(calls[2].addr == 0xc6830000 && calls[2].size == 0x1000);
            assert(run(0x30020, 0x30) == 0 && count == 1);
            assert(calls[0].addr == 0xc6830020 && calls[0].size == 0x30);
            assert(run(0x20000, 0x10000) == 0 && count == 1);
            assert(calls[0].addr == 0xc6820000 && calls[0].size == 0x10000);
            assert(run(0, 0) == 0 && count == 0);
            assert(run(0x60000, 0) == 0 && count == 0);
            assert(run(0x60001, 0) == -EINVAL && count == 0);
            assert(run(0x60000, 1) == -EINVAL && count == 0);
            assert(run(0x5ffff, 2) == -EINVAL && count == 0);
            assert(run(ULONG_MAX, 1) == -EINVAL && count == 0);
            assert(run(1, ULONG_MAX) == -EINVAL && count == 0);
        }
    }
    entries[1].dma_length = entries[1].length;
    assert(run(0, 0x60000) == -EINVAL && count == 0);
    entries[1].dma_length = 0;
    entries[0].dma_length = entries[0].length;
    count = 0;
    assert(ion_sgl_sync_range(NULL, entries, 1, 0, entries[0].length,
                              expect_dir, expect_cpu) == 0 && count == 1);
    return 0;
}
'''
        compilers = [name for name in ("gcc", "clang") if shutil.which(name)]
        self.assertTrue(compilers, "A host C compiler is required")
        with tempfile.TemporaryDirectory(prefix="ion-sync-test-") as tmp:
            src, exe = Path(tmp) / "sync.c", Path(tmp) / "sync"
            src.write_text("\n".join((harness, helper, cases)))
            for compiler in compilers:
                with self.subTest(compiler=compiler):
                    result = subprocess.run([
                        compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-g", str(src),
                        "-o", str(exe),
                    ], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    # LeakSanitizer cannot run under a ptraced sandbox.
                    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                               UBSAN_OPTIONS="halt_on_error=1")
                    result = subprocess.run([str(exe)], env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
