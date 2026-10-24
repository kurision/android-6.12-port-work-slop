#!/usr/bin/env python3
"""Exercise the actual routing dump against fake MMIO and PM failures."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SMMU = ROOT / "drivers/iommu/arm/arm-smmu"


class RoutingDump(unittest.TestCase):
    def test_registers_and_cleanup(self):
        source = (SMMU / "qcom_iommu.c").read_text()
        helper = re.search(
            r"^static void qcom_iommu_dump_static_routing\([^;{]*\)\n"
            r"\{.*?^}", source, re.M | re.S)[0]
        header = (SMMU / "arm-smmu.h").read_text()
        names = ("GR0_ID0", "ID0_NUMSMRG", "GR0_SMR", "GR0_S2CR",
                 "SMR_VALID")
        constants = "\n".join(re.search(
            r"^#define ARM_SMMU_" + name + r"(?:\(n\))?\s+.*$",
            header, re.M)[0] for name in names)
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define __iomem
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((~0U << (l)) & (~0U >> (31-(h))))
#define FIELD_GET(mask,value) (((value) & (mask)) >> __builtin_ctz(mask))
#define SZ_4K 4096
typedef uint32_t u32;
struct device { void *of_node; };
struct qcom_iommu_dev { struct device *dev; };
static u32 regs[1024];
static bool compatible, map_fail;
static int pm_error, refs, maps, unmaps, reads, puts, infos, warnings;
static bool of_device_is_compatible(void *node, const char *name) {
    (void)node; assert(!strcmp(name, "qcom,msm8953-iommu"));
    return compatible;
}
static void *devm_ioremap(struct device *dev, unsigned long base, int size) {
    (void)dev; assert(base==0x01e00000 && size==4096);
    maps++; return map_fail ? NULL : regs;
}
static void devm_iounmap(struct device *dev, void *addr) {
    (void)dev; assert(addr==regs); unmaps++;
}
static int pm_runtime_resume_and_get(struct device *dev) {
    (void)dev; if (pm_error) return pm_error; refs++; return 0;
}
static void pm_runtime_put_sync(struct device *dev) {
    (void)dev; assert(refs==1); refs--; puts++;
}
static u32 readl_relaxed(void *addr) {
    ptrdiff_t offset=(char *)addr-(char *)regs;
    assert(refs==1 && offset>=0 && offset<4096 && offset%4==0);
    /* Offset zero is sCR0, not the ID0 register. */
    assert(offset==0x20 || (offset>=0x800 && offset<0xffc));
    reads++; return regs[offset/4];
}
static void dev_info(struct device *dev, const char *fmt, ...) {
    (void)dev; (void)fmt; infos++;
}
static void dev_warn(struct device *dev, const char *fmt, ...) {
    (void)dev; (void)fmt; warnings++;
}
'''
        harness += constants + "\n" + helper + r'''
static void reset(void) {
    memset(regs,0,sizeof(regs)); compatible=true; map_fail=false;
    pm_error=refs=maps=unmaps=reads=puts=infos=warnings=0;
}
int main(void) {
    struct device dev={0}; struct qcom_iommu_dev iommu={&dev};
    reset(); compatible=false; qcom_iommu_dump_static_routing(&iommu);
    assert(!maps && !reads);
    reset(); map_fail=true; qcom_iommu_dump_static_routing(&iommu);
    assert(maps==1 && !unmaps && !reads);
    reset(); pm_error=-5; qcom_iommu_dump_static_routing(&iommu);
    assert(unmaps==1 && !reads && !puts && !refs && warnings==1);
    reset(); qcom_iommu_dump_static_routing(&iommu);
    assert(reads==1 && infos==1 && puts==1 && unmaps==1 && !refs);
    reset(); regs[0]=0; regs[0x20/4]=0xf0000003;
    regs[0x800/4]=BIT(31); /* Valid SID zero must be included. */
    regs[0x804/4]=0x123; /* Nonzero but invalid: no S2CR read. */
    regs[0x808/4]=BIT(31)|0x1c00;
    qcom_iommu_dump_static_routing(&iommu);
    assert(reads==6 && infos==3 && puts==1 && unmaps==1 && !refs);
    reset(); regs[0x20/4]=255;
    for(int i=0;i<255;i++) regs[(0x800+4*i)/4]=BIT(31)|i;
    qcom_iommu_dump_static_routing(&iommu);
    assert(reads==511 && infos==256 && puts==1 && unmaps==1 && !refs);
}
'''
        with tempfile.TemporaryDirectory(prefix="smmu-routing-") as folder:
            cfile, exe = Path(folder) / "test.c", Path(folder) / "test"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), "-Wall", "-Wextra",
                            "-Werror", str(cfile), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
