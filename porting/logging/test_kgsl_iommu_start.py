#!/usr/bin/env python3
"""Check actual KGSL IOMMU startup clocks and reject SMMU reset programming."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/kgsl_iommu.c'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#define KGSL_IOMMU_CONTEXT_USER 0
#define KGSL_IOMMU_SMMU_V500 1
#define KGSL_MMU_STARTED 0
struct kgsl_pagetable { int unused; };
struct kgsl_iommu_context { int unused; };
struct kgsl_iommu {
    struct kgsl_iommu_context ctx[1];
    unsigned char *regbase;
    bool qsmmu_configured;
};
struct kgsl_mmu {
    struct kgsl_iommu *priv;
    struct kgsl_pagetable *defaultpagetable;
    bool globalpt_mapped;
    int subtype;
    unsigned long flags;
};
#define _IOMMU_PRIV(mmu) ((mmu)->priv)
static int clocks, baseline, enables, disables, user_calls, secure_calls;
static int detaches, maps, sets, writes, barriers;
static int user_error, secure_error, map_error;
static struct kgsl_mmu *active;

static void kgsl_iommu_enable_clk(struct kgsl_mmu *mmu)
{
    assert(mmu == active && clocks == baseline);
    clocks++;
    enables++;
}
static void kgsl_iommu_disable_clk(struct kgsl_mmu *mmu)
{
    assert(mmu == active && clocks == baseline + 1);
    clocks--;
    disables++;
}
static int _setup_user_context(struct kgsl_mmu *mmu)
{
    assert(mmu == active && clocks == baseline + 1);
    user_calls++;
    return user_error;
}
static int _setup_secure_context(struct kgsl_mmu *mmu)
{
    assert(mmu == active && clocks == baseline + 1 && !user_error);
    secure_calls++;
    return secure_error;
}
static void _detach_context(struct kgsl_iommu_context *ctx)
{
    assert(ctx == &active->priv->ctx[0] && clocks == baseline + 1);
    detaches++;
}
#define _apply_impl_defs(mmu) \
    assert(0 && "KGSL startup must not halt/reprogram the SMMU")
static void writel_relaxed(unsigned int value, void *reg)
{
    assert(clocks == baseline + 1);
    assert((value == 2 && reg == active->priv->regbase + 0x6800) ||
           (value == 1 && reg == active->priv->regbase + 0x64a0));
    writes++;
}
static void wmb(void) { barriers++; }
static int kgsl_iommu_map_globals(struct kgsl_pagetable *pt)
{
    assert(pt == active->defaultpagetable && clocks == baseline + 1);
    maps++;
    return map_error;
}
static int kgsl_iommu_set_pt(struct kgsl_mmu *mmu, struct kgsl_pagetable *pt)
{
    assert(mmu == active && pt == mmu->defaultpagetable);
    assert(clocks == baseline + 1 && mmu->globalpt_mapped);
    sets++;
    return 0;
}
static void set_bit(int bit, unsigned long *flags)
{
    assert(bit == KGSL_MMU_STARTED && clocks == baseline);
    *flags |= 1UL << bit;
}
'''

CHECK = r'''
int main(void)
{
    unsigned char registers[0x6804];
    struct kgsl_iommu iommu = { .regbase = registers };
    /* The one-time flag deliberately survives stop/start within a boot. */
    struct kgsl_pagetable pt = {0};

    for (baseline = 0; baseline <= 2; baseline += 2)
    for (int subtype = 0; subtype <= 1; subtype++)
    for (int scenario = 0; scenario < 5; scenario++) {
        struct kgsl_mmu mmu = {
            .priv = &iommu, .defaultpagetable = &pt, .subtype = subtype,
            .globalpt_mapped = scenario == 4,
        };
        int expected = scenario == 0 ? -ENOMEM :
                       scenario == 1 ? -ENODEV : scenario == 2 ? -EIO : 0;

        active = &mmu;
        iommu.qsmmu_configured = false;
        clocks = baseline;
        enables = disables = user_calls = secure_calls = 0;
        detaches = maps = sets = writes = barriers = 0;
        user_error = scenario == 0 ? -ENOMEM : 0;
        secure_error = scenario == 1 ? -ENODEV : 0;
        map_error = scenario == 2 ? -EIO : 0;
        assert(kgsl_iommu_start(&mmu) == expected);
        assert(clocks == baseline && enables == 1 && disables == 1);
        assert(user_calls == 1 && secure_calls == (scenario != 0));
        assert(detaches == (scenario == 1));
        assert(maps == (scenario == 2 || scenario == 3));
        assert(sets == (expected == 0));
        assert(mmu.globalpt_mapped == (expected == 0));
        assert(mmu.flags == (unsigned long)(expected == 0));
        int register_setup = scenario >= 2 && subtype == 0;
        assert(writes == 2 * register_setup && barriers == register_setup);
        assert(iommu.qsmmu_configured == register_setup);
        if (scenario == 2) {
            /* A failed first mapping remains eligible for a balanced retry. */
            map_error = 0;
            assert(kgsl_iommu_start(&mmu) == 0);
            assert(clocks == baseline && enables == 2 && disables == 2);
            assert(maps == 2 && sets == 1 && mmu.globalpt_mapped);
            assert(mmu.flags == 1);
        }
        if (!expected) {
            /* A later GPU restart must not reintroduce the SMMU halt path. */
            mmu.flags = 0;
            assert(kgsl_iommu_start(&mmu) == 0);
            assert(clocks == baseline && enables == 2 && disables == 2);
            assert(maps == (scenario == 3) && sets == 2 && mmu.flags == 1);
            /* run231: QSMMU hazard/order programming happens exactly once. */
            assert(writes == 2 * register_setup && barriers == register_setup);
            assert(iommu.qsmmu_configured == register_setup);
        }
    }
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    start = source.index('static int kgsl_iommu_start(struct kgsl_mmu *mmu)\n{')
    function = source[start:source.index('\n}', start) + 2]
    with tempfile.TemporaryDirectory(prefix='kgsl-iommu-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(HARNESS + function + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-fsanitize=undefined',
                        '-fno-sanitize-recover=all', str(cfile), '-o', str(binary)],
                       check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL IOMMU clocks/no-reset programming: PASS (20 cases, 4 retries, 8 restarts)')


if __name__ == '__main__':
    main()
