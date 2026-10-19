#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute the real APCS probe/send path with host resource and regmap mocks.

No kernel build or device access. Checks exact reservation and IPC addresses,
including unchanged behavior for the other APCS match-data variants.
"""
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
source = (REPO / "drivers/mailbox/qcom-apcs-ipc-mailbox.c").read_text()
body = source[source.index("#define QCOM_APCS_IPC_BITS"):
              source.index("static void qcom_apcs_ipc_remove")]
assert '.compatible = "qcom,msm8953-apcs-kpss-global", .data = &msm8953_apcs_data' in source

mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#define GFP_KERNEL 0
#define __iomem
#define BIT(n) (1U << (n))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define PLATFORM_DEVID_AUTO (-1)
#define IORESOURCE_MEM 0x200
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define dev_err(dev, ...) ((void)(dev))
#define dev_err_probe(dev, err, ...) (err)
typedef uint32_t u32;
struct device { const void *data; void *drvdata; };
struct platform_device { struct device dev; };
struct resource { unsigned long start, end, flags; const char *name; };
struct regmap { int unused; };
struct regmap_config { unsigned reg_bits, reg_stride, val_bits, max_register; bool fast_io; };
struct mbox_controller;
struct mbox_chan { struct mbox_controller *mbox; void *con_priv; };
struct mbox_chan_ops { int (*send_data)(struct mbox_chan *, void *); };
struct mbox_controller {
    struct device *dev;
    const struct mbox_chan_ops *ops;
    struct mbox_chan *chans;
    unsigned num_chans;
};
static struct resource resource;
static struct regmap map;
static struct platform_device child;
static struct regmap_config mapped_config;
static void *allocation;
static unsigned long mapped_start, mapped_end, write_address;
static u32 write_value;
static int map_calls, child_calls, map_error, regmap_error, mbox_error, send_error;
static bool missing_resource;
static unsigned long resource_size(const struct resource *r) { return r->end - r->start + 1; }
static void *devm_kzalloc(struct device *dev, size_t n, int flags)
{
    allocation = calloc(1, n); assert(allocation); return allocation;
}
static const void *of_device_get_match_data(struct device *dev) { return dev->data; }
static struct resource *platform_get_resource(struct platform_device *pdev, int type, int index)
{
    assert(type == IORESOURCE_MEM && index == 0);
    return missing_resource ? NULL : &resource;
}
static void *devm_ioremap_resource(struct device *dev, const struct resource *res)
{
    map_calls++; mapped_start = res->start; mapped_end = res->end;
    assert(res->flags == IORESOURCE_MEM);
    return map_error ? (void *)(intptr_t)map_error : &map;
}
static void *devm_platform_ioremap_resource(struct platform_device *pdev, int index)
{
    return devm_ioremap_resource(&pdev->dev, &resource);
}
static struct regmap *devm_regmap_init_mmio(struct device *dev, void *base,
                                          const struct regmap_config *config)
{
    assert(base == &map); mapped_config = *config;
    return regmap_error ? (void *)(intptr_t)regmap_error : &map;
}
static int devm_mbox_controller_register(struct device *dev, struct mbox_controller *mbox)
{
    for (unsigned i = 0; i < mbox->num_chans; i++) mbox->chans[i].mbox = mbox;
    return mbox_error;
}
static struct platform_device *platform_device_register_data(struct device *dev,
                const char *name, int id, const void *data, size_t size)
{
    child_calls++; return &child;
}
static void platform_set_drvdata(struct platform_device *pdev, void *data) { pdev->dev.drvdata = data; }
static int regmap_write(struct regmap *m, unsigned reg, u32 value)
{
    assert(m == &map && reg <= mapped_config.max_register);
    write_address = mapped_start + reg; write_value = value;
    return send_error;
}
'''

tests = r'''
static void reset(void)
{
    free(allocation); allocation = NULL;
    resource = (struct resource){0xb011000, 0xb011fff, IORESOURCE_MEM, "apcs"};
    map_calls = child_calls = map_error = regmap_error = mbox_error = send_error = 0;
    missing_resource = false;
}
int main(void)
{
    const struct qcom_apcs_ipc_data *variants[] = { &msm8953_apcs_data,
        &ipq6018_apcs_data, &msm8916_apcs_data, &msm8994_apcs_data,
        &msm8996_apcs_data, &apps_shared_apcs_data, &sdx55_apcs_data };
    struct platform_device pdev = {0};
    for (unsigned i = 0; i < ARRAY_SIZE(variants); i++) {
        reset(); pdev.dev.data = variants[i];
        /* The SDX55 IPC register is beyond the first 4 KiB. */
        resource.end = resource.start + 0x1fff;
        assert(qcom_apcs_ipc_probe(&pdev) == 0 && map_calls == 1);
        struct qcom_apcs_ipc *apcs = pdev.dev.drvdata;
        assert(apcs->mbox.num_chans == 32);
        for (unsigned bit = 0; bit < 32; bit++) {
            assert(qcom_apcs_ipc_send_data(&apcs->mbox_chans[bit], NULL) == 0);
            assert(write_address == resource.start + variants[i]->offset && write_value == BIT(bit));
        }
        assert(resource.start == 0xb011000 && resource.end == 0xb012fff);
        assert(child_calls == !!variants[i]->clk_name);
        if (!i) {
            assert(mapped_start == 0xb011008 && mapped_end == 0xb01100b);
            assert(mapped_end < 0xb011050 && mapped_config.max_register == 0);
            assert(apcs->offset == 0);
        } else {
            assert(mapped_start == resource.start && mapped_end == resource.end);
            assert(mapped_config.max_register == 0x1008 && apcs->offset == variants[i]->offset);
        }
        send_error = -EIO;
        assert(qcom_apcs_ipc_send_data(&apcs->mbox_chans[0], NULL) == -EIO);
    }
    puts("PASS: exact MSM8953 IPC reservation/send address; six other variants unchanged");
    for (int failure = 0; failure < 5; failure++) {
        reset(); pdev.dev.data = &msm8953_apcs_data;
        if (failure == 0) missing_resource = true;
        if (failure == 1) resource.end = resource.start + 10;
        if (failure == 2) map_error = -EBUSY;
        if (failure == 3) regmap_error = -ENOMEM;
        if (failure == 4) mbox_error = -EIO;
        int expected[] = {-EINVAL, -EINVAL, -EBUSY, -ENOMEM, -EIO};
        assert(qcom_apcs_ipc_probe(&pdev) == expected[failure]);
        assert(map_calls == (failure >= 2) && !child_calls);
    }
    puts("PASS: missing/short resources and mapping/regmap/controller errors propagate");
    reset(); pdev.dev.data = &msm8953_apcs_data;
    resource.end = resource.start + 11;
    assert(qcom_apcs_ipc_probe(&pdev) == 0);
    free(allocation);
    puts("PASS: minimum resource ends exactly after IPC; DT resource is not mutated");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="msm8953-apcs-", dir="/tmp/opencode") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(mock + body + tests)
    subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", "-Wno-sign-compare", str(path / "test.c"),
                    "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
