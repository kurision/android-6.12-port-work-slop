#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-test actual memory-ACC selector functions; no kernel/hardware test."""
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
source = (REPO / "drivers/regulator/qcom-msm8953-mem-acc.c").read_text()
functions = source[source.index("struct msm8953_mem_acc {"):
                   source.index("static const struct regulator_ops")]
mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
typedef uint32_t u32;
#define __iomem
#define BIT(n) (1U << (n))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
struct regulator_dev { void *data; };
static void *rdev_get_drvdata(struct regulator_dev *rdev) { return rdev->data; }
static u32 registers[2];
static unsigned writes;
static bool ignore_l2;
static u32 readl(const void *address) { return *(const u32 *)address; }
static void writel(u32 value, void *address)
{
    assert(address == &registers[writes % 2]);
    writes++;
    if (!(ignore_l2 && address == &registers[1]))
        *(u32 *)address = value;
}
'''
tests = r'''
int main(void)
{
    struct msm8953_mem_acc acc = { .base = { &registers[0], &registers[1] } };
    struct regulator_dev rdev = { .data = &acc };

    registers[0] = 0xa1;
    registers[1] = 0xb1;
    assert(msm8953_mem_acc_get_sel(&rdev) == 0);
    assert(msm8953_mem_acc_set_sel(&rdev, 0) == 0 && writes == 0);
    assert(msm8953_mem_acc_set_sel(&rdev, 1) == 0);
    assert(writes == 2 && registers[0] == 0xa0 && registers[1] == 0xb0);
    assert(msm8953_mem_acc_get_sel(&rdev) == 1);
    assert(msm8953_mem_acc_set_sel(&rdev, 0) == 0);
    assert(writes == 4 && registers[0] == 0xa1 && registers[1] == 0xb1);
    assert(msm8953_mem_acc_set_sel(&rdev, 2) == -EINVAL && writes == 4);

    registers[1] &= ~1U;
    assert(msm8953_mem_acc_get_sel(&rdev) == -EIO);
    assert(msm8953_mem_acc_set_sel(&rdev, 1) == -EIO && writes == 4);
    registers[1] |= 1;
    ignore_l2 = true;
    assert(msm8953_mem_acc_set_sel(&rdev, 1) == -EIO && writes == 6);
    puts("PASS: memory-ACC corners, write order, unrelated bits, invalid/stuck states");
}
'''
with tempfile.TemporaryDirectory(prefix="msm8953-mem-acc-", dir="/tmp/opencode") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(mock + functions + tests)
    subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                    "-Werror", str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
