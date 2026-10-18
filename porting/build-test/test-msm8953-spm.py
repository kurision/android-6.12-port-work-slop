#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Test actual SAW4 C operations against host MMIO/IPI mocks, not hardware."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
source = (REPO / "drivers/soc/qcom/msm8953-spm.c").read_text()
constants = "\n".join(re.findall(r"^#define SAW4_.*$", source, re.M))
state = source[source.index("struct msm8953_spm {"):source.index("/* Callers hold")]
functions = source[source.index("static int msm8953_spm_update"):
                   source.index("static void msm8953_spm_put_device")]
mock = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;
typedef int raw_spinlock_t;
typedef unsigned cpumask_t;
#define __iomem
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U << (l)) & (~0U >> (31 - (h))))
#define EXPORT_SYMBOL_GPL(name)
#define raw_spin_lock_irqsave(lock, flags) do { \
    (flags) = 0; assert(!*(lock)); *(lock) = 1; \
} while (0)
#define raw_spin_unlock_irqrestore(lock, flags) do { \
    (void)(flags); assert(*(lock)); *(lock) = 0; \
} while (0)
static u32 regs[0x1000 / 4];
static unsigned writes, log_offsets[32], reads, poll_mode, delay_reads;
static unsigned hotplug_lock, dispatches;
static int dispatch_error, drop_write = -1;
static bool pending;
static u32 readl(const void *address);
static void writel(u32 value, void *address);
static void might_sleep(void) { assert(!hotplug_lock); }
static void cpus_read_lock(void) { assert(!hotplug_lock++); }
static void cpus_read_unlock(void) { assert(hotplug_lock-- == 1); }
static int smp_call_function_any(const cpumask_t *mask, void (*fn)(void *),
                                 void *data, bool wait)
{
    assert(hotplug_lock == 1 && *mask == 0xff && wait);
    dispatches++;
    if (dispatch_error) return dispatch_error;
    fn(data);
    return 0;
}
#define read_poll_timeout_atomic(op, val, condition, delay, timeout, before, addr) ({ \
    int result = -ETIMEDOUT; \
    assert((delay) == 1 && (before)); \
    for (unsigned n = 0; n <= (timeout); n++) { \
        (val) = op(addr); \
        if (condition) { result = 0; break; } \
    } \
    result; \
})
'''
io = r'''
static u32 readl(const void *address)
{
    unsigned offset = (const unsigned char *)address - (const unsigned char *)regs;
    assert(offset < sizeof(regs) && !(offset & 3));
    if (offset == SAW4_PMIC_STATUS) {
        reads++;
        if (pending && delay_reads && !--delay_reads) {
            u32 level = regs[SAW4_VCTL / 4] & SAW4_LEVEL_MASK;
            regs[offset / 4] = poll_mode == 1 ? BIT(16) | level :
                               poll_mode == 2 ? (level ^ 1) : BIT(31) | level;
            pending = false;
        }
    }
    return regs[offset / 4];
}
static void writel(u32 value, void *address)
{
    unsigned offset = (unsigned char *)address - (unsigned char *)regs;
    assert(offset < sizeof(regs) && !(offset & 3));
    assert(writes < sizeof(log_offsets) / sizeof(log_offsets[0]));
    log_offsets[writes++] = offset;
    if ((int)offset == drop_write) return;
    regs[offset / 4] = value;
    if (offset == SAW4_PMIC_DATA3) pending = true;
}
'''
tests = r'''
int main(void)
{
    struct msm8953_spm spm = { .base = regs, .cpus = 0xff };
    unsigned before, saved, count;

    assert(SAW4_VERSION == 0xfd0 && SAW4_TIMEOUT_US == 500);
    assert(SAW4_VCTL == 0x900 && SAW4_AVS_LIMIT == 0x908);
    assert(msm8953_spm_get_vlevel(&spm) == -EIO);
    regs[SAW4_AVS_CTL / 4] = 0x10;
    assert(msm8953_spm_set_avs(&spm, true) == -EINVAL && writes == 0);
    regs[SAW4_AVS_LIMIT / 4] = 0x5500aa00;
    assert(msm8953_spm_set_avs_limits(&spm, 80, 228) == 0);
    assert(regs[SAW4_AVS_LIMIT / 4] == 0x55e4aa50);
    before = writes;
    assert(msm8953_spm_set_avs_limits(&spm, 101, 100) == -EINVAL);
    assert(msm8953_spm_set_avs_limits(&spm, 80, 256) == -EINVAL);
    assert(writes == before);
    /* Min level 0 is the FTS2-family VSET floor and must be accepted. */
    assert(msm8953_spm_set_avs_limits(&spm, 0, 100) == 0);
    assert(regs[SAW4_AVS_LIMIT / 4] == 0x5564aa00);
    assert(msm8953_spm_set_avs(&spm, true) == 0);
    assert(regs[SAW4_AVS_CTL / 4] == 0x11 && msm8953_spm_avs_enabled(&spm));

    before = writes;
    assert(msm8953_spm_set_vlevel(&spm, 0) == -EINVAL);
    assert(msm8953_spm_set_vlevel(&spm, 256) == -EINVAL);
    assert(writes == before && dispatches == 0);
    assert(msm8953_spm_set_vlevel(&spm, 150) == -ENODEV);
    assert(writes == before && !hotplug_lock);
    regs[SAW4_ID / 4] = SAW4_PMIC_ARB;
    regs[SAW4_VCTL / 4] = 0xa5070011;
    regs[SAW4_PMIC_DATA3 / 4] = 0x5a070022;
    saved = regs[SAW4_AVS_LIMIT / 4];
    delay_reads = 3;
    assert(msm8953_spm_set_vlevel(&spm, 150) == 0);
    assert(writes == before + 3 && !hotplug_lock);
    assert(log_offsets[before] == SAW4_RESET);
    assert(log_offsets[before + 1] == SAW4_VCTL);
    assert(log_offsets[before + 2] == SAW4_PMIC_DATA3);
    assert(regs[SAW4_VCTL / 4] == 0xa5000096);
    assert(regs[SAW4_PMIC_DATA3 / 4] == 0x5a000096);
    assert(regs[SAW4_AVS_LIMIT / 4] == saved && regs[SAW4_AVS_CTL / 4] == 0x11);
    assert(msm8953_spm_get_vlevel(&spm) == 150);

    poll_mode = 1; /* Matching level, but FSM is still busy: not success. */
    delay_reads = 1;
    count = reads;
    assert(msm8953_spm_set_vlevel(&spm, 160) == -ETIMEDOUT);
    assert(reads - count <= SAW4_TIMEOUT_US + 1 && !hotplug_lock);
    poll_mode = 2; /* Idle FSM, wrong returned level: also not success. */
    delay_reads = 1;
    assert(msm8953_spm_set_vlevel(&spm, 170) == -ETIMEDOUT);
    before = writes;
    dispatch_error = -ENXIO;
    assert(msm8953_spm_set_vlevel(&spm, 180) == -ENXIO);
    assert(writes == before && !hotplug_lock);

    assert(msm8953_spm_set_avs(&spm, false) == 0);
    assert(regs[SAW4_AVS_CTL / 4] == 0x10 && !msm8953_spm_avs_enabled(&spm));
    drop_write = SAW4_AVS_CTL;
    assert(msm8953_spm_set_avs(&spm, true) == -EIO);
    drop_write = SAW4_AVS_LIMIT;
    assert(msm8953_spm_set_avs_limits(&spm, 90, 200) == -EIO);
    assert(!spm.lock && !hotplug_lock);
    puts("PASS: SAW4 request/idle/level handshake, errors, routing, AVS limits and masks");
}
'''
with tempfile.TemporaryDirectory(prefix="msm8953-spm-", dir="/tmp/opencode") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(mock + constants + "\n" + state + io + functions + tests)
    subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                    "-Werror", str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
