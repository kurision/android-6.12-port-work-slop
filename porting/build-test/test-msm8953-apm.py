#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the actual APM switch/read functions against host MMIO mocks.

No kernel build. This checks software behavior, not hardware timing, supplier
lifetime, probe or whether switching supplies is safe at a particular voltage.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
source = (REPO / "drivers/soc/qcom/msm8953-apm.c").read_text()
constants = "\n".join(re.findall(r"^#define MSM8953_APM_.*$", source, re.M))
state = source[source.index("struct msm_apm_ctrl_dev {"):source.index("/* The mapping")]
functions = source[source.index("static int msm8953_apm_read_supply"):
                   source.index("static void msm8953_apm_put_device")]

mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "include/soc/qcom/apm.h"
typedef uint32_t u32;
typedef int spinlock_t;
#define __iomem
#define GENMASK(h, l) ((~0U << (l)) & (~0U >> (31 - (h))))
#define EXPORT_SYMBOL_GPL(name)
#define spin_lock_irqsave(lock, flags) do { \
    (flags) = 0; assert(!*(lock)); *(lock) = 1; \
} while (0)
#define spin_unlock_irqrestore(lock, flags) do { \
    (void)(flags); assert(*(lock)); *(lock) = 0; \
} while (0)
static u32 registers[3];
static unsigned writes, reads, delay_reads;
static bool fail_switch;
static u32 readl(const void *address)
{
    assert(address == &registers[2]);
    reads++;
    if (!fail_switch && delay_reads && !--delay_reads)
        registers[2] = registers[0] == 2 ? 3 : 0;
    return registers[2];
}
static void writel(u32 value, void *address)
{
    assert(address == registers);
    registers[0] = value;
    writes++;
}
#define readl_poll_timeout_atomic(addr, val, condition, delay, timeout) ({ \
    int result = -ETIMEDOUT; \
    for (unsigned n = 0; n <= (timeout); n++) { \
        (val) = readl(addr); \
        if (condition) { result = 0; break; } \
    } \
    result; \
})
'''

tests = r'''
int main(void)
{
    struct msm_apm_ctrl_dev ctrl = { .base = registers };
    unsigned before;

    assert(MSM8953_APM_MODE == 0x2a8);
    assert(MSM8953_APM_DELAY == 0x2ac);
    assert(MSM8953_APM_STATUS == 0x2b0);
    assert(MSM8953_APM_TIMEOUT_US == 500);
    assert(msm_apm_get_supply(&ctrl) == MSM_APM_SUPPLY_MX);

    delay_reads = 3;
    assert(msm_apm_set_supply(&ctrl, MSM_APM_SUPPLY_APCC) == 0);
    assert(registers[0] == 2 && writes == 1);
    assert(msm_apm_get_supply(&ctrl) == MSM_APM_SUPPLY_APCC);
    registers[2] |= 0x80000000;
    assert(msm_apm_get_supply(&ctrl) == MSM_APM_SUPPLY_APCC);

    delay_reads = 2;
    assert(msm_apm_set_supply(&ctrl, MSM_APM_SUPPLY_MX) == 0);
    assert(registers[0] == 0 && writes == 2);
    assert(msm_apm_get_supply(&ctrl) == MSM_APM_SUPPLY_MX);

    before = writes;
    assert(msm_apm_set_supply(&ctrl, (enum msm_apm_supply)123) == -EINVAL);
    assert(writes == before);

    fail_switch = true;
    before = reads;
    assert(msm_apm_set_supply(&ctrl, MSM_APM_SUPPLY_APCC) == -ETIMEDOUT);
    assert(reads - before <= MSM8953_APM_TIMEOUT_US + 1);
    assert(msm_apm_get_supply(&ctrl) == MSM_APM_SUPPLY_MX);
    registers[2] = 1;
    assert(msm_apm_get_supply(&ctrl) == -EIO);
    assert(!ctrl.lock);
    puts("PASS: APM reads, both switch directions, mask, invalid request, timeout");
}
'''

with tempfile.TemporaryDirectory(prefix="msm8953-apm-", dir="/tmp/opencode") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(mock + constants + "\n" + state + functions + tests)
    subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                    "-Werror", "-I", str(REPO), str(path / "test.c"),
                    "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
