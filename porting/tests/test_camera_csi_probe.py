#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inject acquisition failures into the actual CSI probe bodies on the host."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CAM = ROOT / "drivers/media/platform/msm/camera/sensor"

STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#define GFP_KERNEL 0
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define IRQF_TRIGGER_RISING 1
#define IRQF_NO_AUTOEN 0x80000
#define V4L2_SUBDEV_FL_HAS_DEVNODE 1
#define MAX_REGULATOR 8
#define MSM_CAMERA_SUBDEV_CSID 1
#define MSM_CAMERA_SUBDEV_CSIPHY 0
#define MSM_SD_CLOSE_2ND_CATEGORY 0x20000000
#define CSID_POWER_DOWN 13
#define CSIPHY_POWER_DOWN 14
#define CSI_3PHASE_HW 1
#define CDBG(...) ((void)0)
#define pr_err(...) ((void)0)
#define IS_ERR(p) ((intptr_t)(p)<0)
#define PTR_ERR(p) ((intptr_t)(p))
enum failure { NONE, ALLOC1, ALLOC2, CELL, VOLTAGE, CLOCK, VREG,
               VREG_COUNT, BASE, MUX, IRQ, REQUEST, VERSION, ENTITY,
               REGISTER, REGISTER_DEFER };
struct device_node { int unused; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; int id; void *data; };
struct resource { unsigned start; };
struct media_entity { int initialized; };
struct v4l2_file_operations { void (*compat_ioctl32)(void); };
struct video_device { struct v4l2_file_operations *fops; };
struct v4l2_subdev {
    void *data, *internal_ops; int flags, grp_id; char name[32];
    struct media_entity entity; struct video_device *devnode;
};
struct msm_sd_subdev { struct v4l2_subdev sd; int close_seq; };
struct controls { int csid_reg, csid_lane_assign, csiphy_reg, csiphy_3ph_reg; };
#define csid_ctrl_t controls
#define csiphy_ctrl_t controls
struct csi_device {
    struct msm_sd_subdev msm_sd;
    struct controls *ctrl_reg; struct platform_device *pdev;
    struct resource *irq; void *base,*clk_mux_base;
    int mutex,csid_3p_enabled,is_3_1_20nm_hw,csiphy_3phase,num_irq_registers;
    int hw_dts_version,csid_state,csiphy_state,regulator_count;
    void *csid_clk_info,*csid_clk,*csid_vreg;
    void *csiphy_all_clk_info,*csiphy_all_clk,*csiphy_vreg;
    size_t num_clk,num_all_clk;
};
#define csid_device csi_device
#define csiphy_device csi_device
static struct { uint32_t min_voltage,max_voltage; } csid_vreg_info[1];
static int msm_csid_subdev_ops,msm_csiphy_subdev_ops;
static int msm_csid_internal_ops,msm_csiphy_internal_ops;
static struct v4l2_file_operations msm_csid_v4l2_subdev_fops,msm_csiphy_v4l2_subdev_fops;
static void msm_csid_subdev_fops_ioctl32(void) {}
static void msm_csiphy_subdev_fops_ioctl(void) {}
static int fail,kind,allocs,live,regions,irq_owned,clocks,entity,published;
static struct resource irq;
static struct video_device node;
static void *kzalloc(size_t n,int flags) {
    ++allocs;
    if ((fail==ALLOC1 && allocs==1) || (fail==ALLOC2 && allocs==2)) return NULL;
    void *p=calloc(1,n); assert(p); ++live; return p;
}
static void kfree(void *p) { if (p) { assert(live>0 && !published); --live; free(p); } }
static void mutex_init(int *m) { *m=1; }
static void mutex_destroy(int *m) { assert(*m==1); *m=0; }
static void platform_set_drvdata(struct platform_device *p,void *d) { p->data=d; }
static void v4l2_subdev_init(struct v4l2_subdev *s,void *ops) {}
static void v4l2_set_subdevdata(struct v4l2_subdev *s,void *d) { s->data=d; }
static int of_property_read_u32(struct device_node *n,const char *name,uint32_t *v) {
    if (!strcmp(name,"cell-index")) { if (fail==CELL) return -EINVAL; *v=2; }
    else { assert(!strcmp(name,"qcom,csi-vdd-voltage")); if (fail==VOLTAGE) return -EINVAL; *v=1224000; }
    return 0;
}
static bool of_device_is_compatible(struct device_node *n,const char *name) {
    return fail!=VERSION && !strcmp(name,kind ? "qcom,csiphy-v3.5" : "qcom,csid-v3.5.1");
}
static int legacy_msm_camera_get_clk_info(struct platform_device *p,void **info,void **ptr,size_t *count) {
    assert(!published && !clocks); if (fail==CLOCK) return -517;
    clocks=1; *info=(void *)1; *ptr=(void *)2; *count=9; return 0;
}
static int msm_csiphy_get_clk_info(struct csi_device *d,struct platform_device *p) {
    return legacy_msm_camera_get_clk_info(p,&d->csiphy_all_clk_info,&d->csiphy_all_clk,&d->num_all_clk);
}
static int legacy_msm_camera_put_clk_info(struct platform_device *p,void **info,void **ptr,size_t count) {
    assert(clocks==1 && !irq_owned && !regions && !published);
    clocks=0; *info=*ptr=NULL; return 0;
}
static int legacy_msm_camera_get_dt_vreg_data(struct device_node *n,void **v,int *count) {
    if (fail==VREG) return -ENOMEM;
    *v=kzalloc(1,0); *count=fail==VREG_COUNT ? MAX_REGULATOR+1 : 1; return 0;
}
static void *legacy_msm_camera_get_reg_base(struct platform_device *p,char *name,int reserve) {
    bool mux=!strcmp(name,"csiphy_clk_mux");
    if ((mux && fail==MUX) || (!mux && fail==BASE)) return NULL;
    ++regions; return mux ? (void *)4 : (void *)3;
}
static void legacy_msm_camera_put_reg_base(struct platform_device *p,void *base,char *name,int reserve) {
    assert(base && regions>0 && !irq_owned && !published); --regions;
}
static struct resource *legacy_msm_camera_get_irq(struct platform_device *p,char *name) {
    return fail==IRQ ? (struct resource *)(intptr_t)-517 : &irq;
}
static void msm_csid_irq(void) {}
static void msm_csiphy_irq(void) {}
static int legacy_msm_camera_register_irq(struct platform_device *p,struct resource *r,
    void (*handler)(void),unsigned long flags,char *name,void *data) {
    assert(!published && (flags & IRQF_NO_AUTOEN));
    if (fail==REQUEST) return -ENOMEM;
    irq_owned=1; return 0;
}
static int legacy_msm_camera_unregister_irq(struct platform_device *p,struct resource *r,void *data) {
    assert(irq_owned && !published); irq_owned=0; return 0;
}
static int media_entity_pads_init(struct media_entity *e,int count,void *pads) {
    if (fail==ENTITY) return -ENOMEM;
    assert(!entity); entity=e->initialized=1; return 0;
}
static void media_entity_cleanup(struct media_entity *e) {
    assert(entity && !published); entity=e->initialized=0;
}
static int legacy_msm_sd_register(struct msm_sd_subdev *s) {
    struct csi_device *d=(void *)s;
    assert(clocks && regions==(kind ? 2 : 1) && irq_owned && entity && !published);
    assert(d->pdev && d->hw_dts_version && d->pdev->id==2);
    if (kind) assert(d->csiphy_state==CSIPHY_POWER_DOWN && d->ctrl_reg->csiphy_reg);
    else assert(d->csid_state==CSID_POWER_DOWN && d->ctrl_reg->csid_reg);
    if (fail==REGISTER) return -ENOMEM;
    if (fail==REGISTER_DEFER) return -517;
    published=1; s->sd.devnode=&node; return 0;
}
static void legacy_msm_cam_copy_v4l2_subdev_fops(struct v4l2_file_operations *f) {}
'''

MAIN = r'''
int main(void) {
    for (kind=0;kind<2;kind++) for (fail=NONE;fail<=REGISTER_DEFER;fail++) {
        if (kind && (fail==VOLTAGE || fail==VREG_COUNT)) continue;
        if (!kind && fail==MUX) continue;
        struct device_node n={0}; struct platform_device p={.dev.of_node=&n};
        allocs=live=regions=irq_owned=clocks=entity=published=0;
        int rc=kind ? csiphy_probe(&p) : csid_probe(&p);
        if (fail==NONE) {
            assert(!rc && published && p.data);
            struct csi_device *d=((struct v4l2_subdev *)p.data)->data;
            assert(d->msm_sd.sd.devnode==&node);
            /* Successful removal is outside this probe-failure test. */
            published=0; media_entity_cleanup(&d->msm_sd.sd.entity);
            legacy_msm_camera_unregister_irq(&p,d->irq,d);
            if (kind) legacy_msm_camera_put_reg_base(&p,d->clk_mux_base,"mux",1);
            legacy_msm_camera_put_reg_base(&p,d->base,"base",1);
            if (kind) legacy_msm_camera_put_clk_info(&p,&d->csiphy_all_clk_info,&d->csiphy_all_clk,d->num_all_clk);
            else legacy_msm_camera_put_clk_info(&p,&d->csid_clk_info,&d->csid_clk,d->num_clk);
            kfree(kind ? d->csiphy_vreg : d->csid_vreg); kfree(d->ctrl_reg); kfree(d);
        } else {
            assert(rc<0 && !p.data);
            if (fail==CLOCK || fail==IRQ || fail==REGISTER_DEFER) assert(rc==-517);
        }
        assert(!live && !regions && !irq_owned && !clocks && !entity && !published);
    }
}
'''


class CsiProbe(unittest.TestCase):
    def test_probe_acquisition_failures_and_publication(self):
        functions = []
        for kind in ("csid", "csiphy"):
            source = (CAM / kind / f"msm_{kind}.c").read_text()
            functions.append(re.search(r"^static int " + kind + r"_probe\([^;{]*\)\n\{.*?^}",
                                       source, re.M | re.S)[0])
        functions = "\n".join(functions)
        tables = sorted(set(re.findall(r"\blegacy_(?:csid|csiphy)_\w+", functions)))
        versions = sorted(set(re.findall(r"\b(?:CSID|CSIPHY)_VERSION_\w+", functions)))
        defines = "\n".join(f"#define {name} {i + 1}" for i, name in enumerate(tables + versions))
        with tempfile.TemporaryDirectory() as folder:
            cfile, exe = Path(folder) / "csi-probe.c", Path(folder) / "csi-probe"
            cfile.write_text(STUBS + defines + "\n" + functions + MAIN)
            for compat in (False, True):
                with self.subTest(compat=compat):
                    subprocess.run([os.environ.get("CC", "cc"), "-Werror", "-Wno-pointer-sign",
                                    *(["-DCONFIG_COMPAT"] if compat else []), str(cfile),
                                    "-o", str(exe)], check=True)
                    subprocess.run([str(exe)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
