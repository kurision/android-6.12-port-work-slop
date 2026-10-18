#!/usr/bin/env python3
"""Check actual MMU selection does not hide configured-IOMMU probe failures."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <string.h>
#define EPROBE_DEFER 517
#define KGSL_MMU_TYPE_NONE 0
#define KGSL_MMU_TYPE_IOMMU 1
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define MMU_OP_VALID(m, name) ((m)->mmu_ops && (m)->mmu_ops->name)
#define dev_info(...) ((void)0)
#define dev_err(...) ((void)0)
struct device_node { unsigned int refs; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
struct kgsl_mmu;
struct kgsl_device;
struct kgsl_mmu_ops {
    int (*probe)(struct kgsl_device *);
    int (*mmu_init)(struct kgsl_mmu *);
};
struct kgsl_mmu { unsigned int type; const struct kgsl_mmu_ops *mmu_ops; };
struct kgsl_device { struct kgsl_mmu mmu; struct platform_device *pdev; };
static struct device_node parent = {1}, node = {1};
static int present, setup_result, init_result, setups, inits, nommu_calls;
static struct device_node *of_node_get(struct device_node *np)
{
    np->refs++;
    return np;
}
static void of_node_put(struct device_node *np)
{
    if (np) {
        assert(np->refs > 1);
        np->refs--;
    }
}
static struct device_node *of_find_compatible_node(struct device_node *from,
                                                   const char *type, const char *compat)
{
    assert(!strcmp(compat, "qcom,kgsl-smmu-v2"));
    of_node_put(from); /* The real OF iterator consumes its starting reference. */
    return present ? of_node_get(&node) : NULL;
}
static int setup(struct kgsl_device *dev, struct device_node *np)
{
    assert(np == &node && np->refs == 2);
    setups++;
    return setup_result;
}
static int init(struct kgsl_mmu *mmu)
{
    inits++;
    return init_result;
}
static int nommu_probe(struct kgsl_device *dev)
{
    nommu_calls++;
    return 0;
}
static const struct {
    const char *compat;
    int (*probe)(struct kgsl_device *, struct device_node *);
} kgsl_dt_devices[] = {{"qcom,kgsl-smmu-v2", setup}};
'''

TABLE = r'''
static const struct kgsl_mmu_ops iommu_ops = {kgsl_iommu_probe, init};
static const struct kgsl_mmu_ops nommu_ops = {nommu_probe, init};
static const struct {
    const char *name;
    unsigned int type;
    const struct kgsl_mmu_ops *ops;
} kgsl_mmu_subtypes[] = {
    {"iommu", KGSL_MMU_TYPE_IOMMU, &iommu_ops},
    {"nommu", KGSL_MMU_TYPE_NONE, &nommu_ops},
};
'''

CHECK = r'''
int main(void)
{
    const int results[] = {0, -EPROBE_DEFER, -ENODEV, -ENOENT, -ENOMEM, -EIO, -EINVAL};
    struct platform_device pdev = { .dev.of_node = &parent };

    for (present = 0; present <= 1; present++)
    for (unsigned int i = 0; i < ARRAY_SIZE(results); i++) {
        struct kgsl_device dev = { .pdev = &pdev };

        setups = inits = nommu_calls = init_result = 0;
        setup_result = results[i];
        assert(kgsl_mmu_probe(&dev) == (present ? setup_result : 0));
        assert(parent.refs == 1 && node.refs == 1);
        assert(setups == present && nommu_calls == !present);
        assert(inits == (!present || setup_result == 0));
        if (!present || !setup_result)
            assert(dev.mmu.type == (unsigned int)present);
        else
            assert(!dev.mmu.mmu_ops);
    }
    present = 1;
    setup_result = 0;
    init_result = -EIO;
    struct kgsl_device dev = { .pdev = &pdev };
    assert(kgsl_mmu_probe(&dev) == -EIO);
    assert(parent.refs == 1 && node.refs == 1);
    return 0;
}
'''


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def main():
    iommu = (ROOT / 'drivers/gpu/msm/kgsl_iommu.c').read_text()
    mmu = (ROOT / 'drivers/gpu/msm/kgsl_mmu.c').read_text()
    header = (ROOT / 'drivers/gpu/msm/kgsl_mmu.h').read_text()
    absent = re.search(r'^#define KGSL_MMU_PROBE_NOT_FOUND .*$', header, re.M).group()
    unit = (absent + '\n' + HARNESS + function(iommu, 'static int kgsl_iommu_probe(') + TABLE
            + function(mmu, 'int kgsl_mmu_probe(') + CHECK)
    with tempfile.TemporaryDirectory(prefix='kgsl-probe-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(unit)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-Wno-unused-function', '-Wno-sign-compare',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(cfile), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL MMU probe selection, fatal errors and OF references: PASS')


if __name__ == '__main__':
    main()
