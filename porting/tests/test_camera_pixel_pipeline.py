#!/usr/bin/env python3
"""Check translated pixel resources and synchronous SMMU probe failures."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_camera_power_domains import CAM, ROOT, function


def run_c(source):
    with tempfile.TemporaryDirectory(prefix="camera-pixel-") as folder:
        path, exe = Path(folder) / "test.c", Path(folder) / "test"
        path.write_text(source)
        flags = ["-std=gnu11", "-Wall", "-Wextra", "-Werror"]
        if os.environ.get("CAMERA_TEST_SANITIZERS"):
            flags += ["-fsanitize=" + os.environ["CAMERA_TEST_SANITIZERS"]]
        subprocess.run([os.environ.get("CC", "cc"), *flags, str(path),
                        "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)


class PixelPipeline(unittest.TestCase):
    def test_vfe_parent_defers_without_partial_common_setup(self):
        source = (CAM / "isp/msm_isp.c").read_text()
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#define MAX_VFE 2
#define EPROBE_DEFER 517
typedef unsigned int u32;
struct device { void *of_node,*platform_data;int refs; };
struct platform_device { struct device dev;int ready; };
struct device_node { int id; };
static struct {int common_dev_data_lock,common_dev_axi_lock;} vfe_common_data;
static struct platform_device children[2];
static struct device_node nodes[2]={{0},{1}};
static int mode,which,common_calls,lock_calls,node_refs;
static int of_property_read_u32(void *node,const char *name,u32 *count) {
    (void)node;assert(!strcmp(name,"num_child"));
    *count=mode==2?0:mode==3?3:2;return mode==1?-EINVAL:0;
}
static struct device_node *of_find_node_by_name(void *from,const char *name) {
    (void)from;int id=!strcmp(name,"qcom,vfe0")?0:1;
    if(mode==4 && id==which)return NULL;
    node_refs++;return &nodes[id];
}
static struct platform_device *of_find_device_by_node(struct device_node *node) {
    if(mode==5 && node->id==which)return NULL;
    children[node->id].dev.refs++;return &children[node->id];
}
static void of_node_put(struct device_node *node) {assert(node);node_refs--;}
static void *platform_get_drvdata(struct platform_device *p) {return p->ready?p:NULL;}
static void put_device(struct device *dev) {assert(dev->refs==1);dev->refs--;}
#define spin_lock_init(l) do {*(l)=1;lock_calls++;}while(0)
static int vfe_set_common_data(struct platform_device *p) {
    assert(p->ready && p->dev.platform_data==&vfe_common_data);
    common_calls++;return 0;
}
'''
        harness += function(source, "vfe_probe") + r'''
int main(void) {
    struct platform_device parent={0};
    for(mode=0;mode<=6;mode++)for(which=0;which<2;which++) {
        memset(children,0,sizeof(children));
        for(int i=0;i<2;i++)children[i].ready=!(mode==6 && which==i);
        common_calls=lock_calls=node_refs=0;
        int rc=vfe_probe(&parent);
        if(!mode)assert(!rc && common_calls==2 && lock_calls==2);
        else {assert(rc==(mode<=3?-EINVAL:mode==4?-ENODEV:-EPROBE_DEFER));
              assert(!common_calls && !lock_calls);}
        assert(!node_refs && !children[0].dev.refs && !children[1].dev.refs);
    }
    puts("VFE parent DT bounds, deferred children, reference cleanup and shared-state readiness PASS");
}
'''
        run_c(harness)

    def test_vfe_probe_publication_and_unwind(self):
        source = (CAM / "isp/msm_isp.c").read_text()
        probe = function(source, "legacy_vfe_hw_probe")
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define GFP_KERNEL 0
#define MAX_VFE 2
#define ISP_VFE0 0
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define pr_err(...) ((void)0)
#define ISP_DBG(...) ((void)0)
#define V4L2_SUBDEV_FL_HAS_DEVNODE 1
#define V4L2_SUBDEV_FL_HAS_EVENTS 2
#define MSM_CAMERA_SUBDEV_VFE 3
#define MSM_SD_CLOSE_1ST_CATEGORY 16
#define MSM_SD_NOTIFY_REQ_CB 1
struct driver { void *of_match_table; };
struct device { void *of_node; struct driver *driver; };
struct platform_device { struct device dev; int id; void *data; const char *name; };
struct msm_isp_statistics { int dummy; };
struct msm_isp_ub_info { int dummy; };
struct isp_proc { int vfeid; };
struct msm_sd_req_vb2_q { int ready; };
struct msm_isp_buf_mgr { int init_done,num_iommu_secure_ctx; };
struct entity { int live; const char *name; };
struct fops { void (*unlocked_ioctl)(void),(*compat_ioctl32)(void),(*mmap)(void); };
struct video { struct fops *fops; };
struct subdev {
    void *internal_ops,*data;char name[16];int flags,grp_id;
    struct entity entity;struct video *devnode;
};
struct msm_sd_subdev { struct subdev sd; int close_seq; };
struct vfe_device;
struct platform_ops {
    int (*get_platform_data)(struct vfe_device *);
    void (*put_clks)(struct vfe_device *),(*put_regulators)(struct vfe_device *);
};
struct axi_info { int scratch_buf_range; };
struct msm_vfe_hardware_info {
    struct { struct platform_ops platform_ops; } vfe_ops;
    struct axi_info *axi_hw_info;int num_iommu_secure_ctx;
};
struct of_device_id { void *data; };
struct device_id { uintptr_t driver_data; };
struct vfe_device {
    struct platform_device *pdev;
    struct msm_isp_statistics *stats;struct msm_isp_ub_info *legacy_ub_info;
    struct msm_vfe_hardware_info *hw_info;struct msm_sd_subdev subdev;
    struct msm_isp_buf_mgr *buf_mgr;struct isp_proc *isp_page;
    int tasklet_q,vfe_tasklet,realtime_mutex,core_mutex,tasklet_lock;
    int shared_data_lock,reg_update_lock,reset_completion_lock,halt_completion_lock;
    void *vfe_irq;
};
static struct msm_sd_req_vb2_q vfe_vb2_ops;
static struct msm_isp_buf_mgr vfe_buf_mgr;
static struct fops msm_isp_v4l2_fops;
static struct video video;
static int msm_vfe_v4l2_subdev_ops,msm_vfe_subdev_internal_ops,req_history_lock;
static int msm_isp_bw_request_history;
static int failure,step,allocations,irq_live,clocks_live,power_live,bw_live,published;
static void *kzalloc(size_t n,int flags) {
    (void)flags;step++;
    if(failure==step && step<=3)return NULL;
    void *p=calloc(1,n);assert(p);allocations++;return p;
}
static void kfree(void *p) { if(p){assert(allocations>0);allocations--;free(p);} }
static unsigned long get_zeroed_page(int flags) {
    (void)flags;if(failure==6)return 0;
    void *p=calloc(1,sizeof(struct isp_proc));assert(p);allocations++;
    return (unsigned long)p;
}
static void free_page(unsigned long p) { kfree((void *)p); }
static int of_property_read_u32(void *np,const char *name,int *id) {
    (void)np;(void)name;*id=failure==9?2:0;return 0;
}
static int get_platform(struct vfe_device *v) {
    if(failure==4)return -517;
    v->vfe_irq=(void *)42;irq_live=clocks_live=power_live=bw_live=1;return 0;
}
static void put_clks(struct vfe_device *v) {(void)v;assert(clocks_live);clocks_live=0;}
static void put_power(struct vfe_device *v) {(void)v;assert(power_live);power_live=0;}
static struct axi_info axi;
static struct msm_vfe_hardware_info hw={
    .vfe_ops={.platform_ops={get_platform,put_clks,put_power}},.axi_hw_info=&axi};
static struct of_device_id match={.data=&hw};
static struct of_device_id *of_match_device(void *table,struct device *dev) {
    (void)table;(void)dev;return failure==10?NULL:&match;
}
static struct device_id *platform_get_device_id(struct platform_device *p) {
    static struct device_id id;(void)p;id.driver_data=(uintptr_t)&hw;return &id;
}
#define INIT_LIST_HEAD(p) (*(p)=1)
#define tasklet_init(t,f,v) do {(void)(f);(void)(v);*(t)=1;}while(0)
static void legacy_msm_isp_do_tasklet(void) {}
static void v4l2_subdev_init(struct subdev *sd,void *ops) {(void)sd;(void)ops;}
static void v4l2_set_subdevdata(struct subdev *sd,void *data) {sd->data=data;}
static void platform_set_drvdata(struct platform_device *p,void *data) {p->data=data;}
#define mutex_init(m) (*(m)=1)
#define mutex_destroy(m) do {assert(*(m)==1);*(m)=0;}while(0)
#define spin_lock_init(l) (*(l)=1)
static int media_entity_pads_init(struct entity *e,int n,void *pads) {
    (void)n;(void)pads;if(failure==5)return -ENOMEM;e->live=1;return 0;
}
static void media_entity_cleanup(struct entity *e) {e->live=0;}
static int legacy_msm_isp_create_isp_buf_mgr(struct msm_isp_buf_mgr *m,
    struct msm_sd_req_vb2_q *q,struct device *dev,int range) {
    (void)m;(void)q;(void)dev;(void)range;return failure==7?-EIO:0;
}
static int legacy_msm_sd_register(struct msm_sd_subdev *sd) {
    struct vfe_device *v=sd->sd.data;
    assert(v->isp_page && v->isp_page->vfeid==v->pdev->id);
    assert(v->buf_mgr->init_done && sd->sd.entity.live && v->vfe_tasklet);
    assert(v->core_mutex && v->realtime_mutex);
    if(failure==8)return -EAGAIN;
    published++;sd->sd.devnode=&video;return 0;
}
static void legacy_msm_cam_copy_v4l2_subdev_fops(struct fops *f) {(void)f;}
static void msm_isp_v4l2_fops_ioctl(void) {}
static void msm_isp_v4l2_fops_mmap(void) {}
static void v4l2_subdev_notify(struct subdev *sd,int cmd,void *q) {
    (void)sd;(void)cmd;(void)q;assert(published==1);
}
static void msm_isp_enable_debugfs(struct vfe_device *v,int history) {(void)v;(void)history;}
static void legacy_msm_isp_deinit_bandwidth_mgr(int id) {
    assert(id==0 && bw_live);bw_live=0;
}
static void legacy_msm_camera_unregister_irq(struct platform_device *p,
    void *irq,void *id) {assert(p && irq==(void *)42 && id && irq_live);irq_live=0;}
'''
        harness += probe + r'''
int main(void) {
    for(failure=0;failure<=10;failure++) {
        struct driver driver={0};struct platform_device p={.dev={.of_node=&driver,.driver=&driver}};
        step=allocations=irq_live=clocks_live=power_live=bw_live=published=0;
        vfe_buf_mgr=(struct msm_isp_buf_mgr){0};
        int rc=legacy_vfe_hw_probe(&p);
        if(failure) {
            int expected=failure==4?-517:failure==7?-EIO:failure==8?-EAGAIN:
                         failure>=9?-EINVAL:-ENOMEM;
            assert(rc==expected && !p.data && !published);
            assert(!allocations && !irq_live && !clocks_live && !power_live && !bw_live);
        }else{
            struct subdev *sd=p.data;struct vfe_device *v=sd->data;
            assert(!rc && published==1 && allocations==4);
            free_page((unsigned long)v->isp_page);kfree(v->legacy_ub_info);kfree(v->stats);kfree(v);
        }
    }
    puts("VFE allocation/resource/entity/registration failures and publication readiness PASS");
}
'''
        for compat in (False, True):
            run_c(("#define CONFIG_COMPAT 1\n" if compat else "") + harness)

    def test_compiled_dt_resources(self):
        dtc = ROOT / "out/scripts/dtc/dtc"
        if not dtc.exists():
            dtc = shutil.which("dtc")
        if not dtc or not shutil.which("cpp"):
            self.skipTest("dtc/cpp unavailable")
        with tempfile.TemporaryDirectory(prefix="camera-dt-") as folder:
            path = Path(folder)
            pp = subprocess.run([
                "cpp", "-nostdinc", "-undef", "-D__DTS__", "-x",
                "assembler-with-cpp", "-Iinclude",
                "-Iscripts/dtc/include-prefixes", "-Iarch/arm64/boot/dts/qcom",
                "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts",
            ], cwd=ROOT, capture_output=True, check=True)
            (path / "board.dts").write_bytes(pp.stdout)
            subprocess.run([str(dtc), "-I", "dts", "-O", "dtb", "-o",
                            str(path / "board.dtb"), str(path / "board.dts")],
                           capture_output=True, check=True)
            dt = subprocess.run([str(dtc), "-I", "dtb", "-O", "dts",
                                 str(path / "board.dtb")], capture_output=True,
                                check=True).stdout.decode()
        gcc = re.search(r"clock-controller@1800000 \{.*?phandle = <(.*?)>;",
                        dt, re.S)[1]
        iommu = re.search(r"iommu@1e20000 \{.*?phandle = <(.*?)>;", dt, re.S)[1]
        # Resolve the provider's real ASID from its existing VFE context bank.
        self.assertRegex(dt, r"iommu-ctx@14000\s*\{")
        context = re.search(r"vfe-context \{(.*?)\n\s*};", dt, re.S)[1]
        self.assertIn(f"iommus = <{iommu} 0x14>;", context)
        self.assertIn('label = "vfe";', context)
        self.assertIn("qcom,scratch-buf-support;", context)
        for node, base, vbif, irq, domain in (
                ("vfe0", "1b10000", "1b40000", 57, 8),
                ("vfe1", "1b14000", "1ba0000", 29, 9)):
            body = re.search(r"qcom," + node + "@" + base + r" \{(.*?)\n\s*};",
                             dt, re.S)[1]
            self.assertIn(f"reg = <0x{base} 0x1000 0x{vbif} 0x200>;", body)
            self.assertIn(f"interrupts = <0x00 0x{irq:x} 0x04>;", body)
            self.assertIn(f"power-domains = <{gcc} 0x{domain:02x}>;", body)
            self.assertIn('power-domain-names = "vfe";', body)
            self.assertIn('status = "okay";', body)
            self.assertIn(f"max-clk-turbo = <0x{465000000:x}>;", body)
        body = re.search(r"qcom,ispif@1b31000 \{(.*?)\n\s*};", dt, re.S)[1]
        self.assertIn(f"power-domains = <{gcc} 0x08 {gcc} 0x09>;", body)
        self.assertIn('power-domain-names = "vfe0", "vfe1";', body)
        self.assertIn("interrupts = <0x00 0x37 0x04>;", body)
        self.assertIn("num_child = <0x02>;", dt)
        config = (ROOT / "porting/tools/kernel.config").read_text()
        self.assertIn("\nCONFIG_MSM_CAMERA_VFE=y\n", config)
        self.assertIn("\nCONFIG_MSM_CAMERA_CPP=y\n", config)
        context = re.search(r"cpp-context \{(.*?)\n\s*};", dt, re.S)[1]
        self.assertIn(f"iommus = <{iommu} 0x12>;", context)
        self.assertIn('label = "cpp";', context)
        self.assertNotIn("qcom,scratch-buf-support", context)
        bank = re.search(r"iommu-ctx@12000 \{(.*?)\n\s*};", dt, re.S)[1]
        self.assertIn('compatible = "qcom,msm-iommu-v1-ns";', bank)
        self.assertIn("reg = <0x12000 0x1000>;", bank)
        self.assertIn("interrupts = <0x00 0x6d 0x04>;", bank)
        body = re.search(r"qcom,cpp@1b04000 \{(.*?)\n\s*};", dt, re.S)[1]
        self.assertIn('compatible = "qcom,cpp";', body)
        self.assertIn('status = "okay";', body)
        self.assertIn("reg = <0x1b04000 0x100 0x1b80000 0x200 0x1b18000 0x18>;", body)
        self.assertIn('reg-names = "cpp", "cpp_vbif", "cpp_hw";', body)
        self.assertIn("interrupts = <0x00 0x31 0x04>;", body)
        self.assertIn(f"power-domains = <{gcc} 0x00>;", body)
        self.assertIn('power-domain-names = "cpp";', body)
        self.assertIn(f"resets = <{gcc} 0x00>;", body)
        self.assertIn('reset-names = "micro_iface_reset";', body)
        clocks = [27, 112, 29, 75, 76, 77, 111, 72]
        self.assertIn("clocks = <" + " ".join(f"{gcc} 0x{x:02x}" for x in clocks)
                      + ">;", body)
        self.assertIn('clock-names = "camss_ahb_src", "camss_top_ahb_clk", '
                      '"cpp_core_clk", "camss_vfe_cpp_ahb_clk", '
                      '"camss_vfe_cpp_axi_clk", "camss_vfe_cpp_clk", '
                      '"micro_iface_clk", "camss_ahb_clk";', body)
        donor = (ROOT.parent / "oc-test/arch/arm64/boot/dts/vendor/qcom/"
                 "msm8953-camera.dtsi").read_text()
        donor = donor[donor.index("qcom,cpp@1b04000 {"):]
        for prop in ("qcom,clock-rates", "qcom,min-clock-rate", "qcom,bus-master",
                     "qcom,src-clock-rates", "qcom,msm-bus,vectors-KBps",
                     "qcom,stripe-base", "qcom,plane-base", "qcom,stripe-size",
                     "qcom,plane-size", "qcom,fe-ptr-off", "qcom,we-ptr-off"):
            def numbers(text):
                value = re.search(re.escape(prop) + r"\s*=\s*(.*?);", text, re.S)[1]
                return [int(n, 0) for n in re.findall(r"0x[0-9a-f]+|\d+", value)]
            self.assertEqual(numbers(body), numbers(donor), prop)
        gcc_source = (ROOT / "drivers/clk/qcom/gcc-msm8953.c").read_text()
        table = re.search(r"ftbl_cpp_clk_src\[\] = \{(.*?)\n};", gcc_source, re.S)[1]
        self.assertEqual([int(x) for x in re.findall(r"F\((\d+),", table)],
                         [100000000, 200000000, 266670000, 320000000, 400000000, 465000000])

    def test_smmu_probe_fault_matrix(self):
        source = (CAM / "common/cam_smmu_api.c").read_text()
        functions = "\n".join(function(source, name) for name in (
            "cam_smmu_setup_cb", "cam_populate_smmu_context_banks", "cam_smmu_probe"))
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR_OR_NULL(p) (!(p) || (intptr_t)(p)<0)
#define pr_err(...) ((void)0)
#define CDBG(...) ((void)0)
#define SCRATCH_ALLOC_START 0
#define SCRATCH_ALLOC_END 0x10000000
#define VA_SPACE_END 0x80000000
#define SZ_128K 0x20000
#define CAM_SECURE 1
#define CAM_NON_SECURE 0
#define EBADHANDLE 521
enum cam_iommu_type { CAM_ARM_SMMU, CAM_QSMMU };
struct device_node { int root; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
struct iommu_domain { int present; };
struct scratch_mapping { void *bitmap; };
struct cam_context_bank_info {
    const char *name;struct device *dev;struct iommu_domain *domain;
    int scratch_buf_support,is_secure;unsigned long va_start,va_len;
    struct scratch_mapping scratch_map;
};
static struct {
    struct cam_context_bank_info *cb_info;
    unsigned int cb_num,cb_init_count;
    int smmu_work,payload_list_lock,payload_list;
} iommu_cb_set;
static struct cam_context_bank_info cb;
static struct iommu_domain domain;
static int fail,label_error,scratch_error,handler_calls,scratch_calls,alloc_error;
static int msm_cam_smmu_dt_match[1];
static struct iommu_domain *iommu_get_domain_for_dev(struct device *dev) {
    assert(dev);if(fail==1)return NULL;
    if(fail==2)return (void *)(intptr_t)-517;
    return &domain;
}
static int cam_smmu_init_scratch_map(struct scratch_mapping *s,
    unsigned long start,unsigned long size,int order) {
    (void)start;(void)size;(void)order;scratch_calls++;
    if(scratch_error)return -ENOMEM;
    s->bitmap=malloc(1);assert(s->bitmap);return 0;
}
static int of_property_read_string(struct device_node *np,
    const char *p,const char **name) {
    (void)np;assert(!strcmp(p,"label"));
    if(label_error)return -EINVAL;
    *name="vfe";return 0;
}
static bool of_property_read_bool(struct device_node *np,const char *p) {
    (void)np;return !strcmp(p,"qcom,scratch-buf-support");
}
static bool of_device_is_compatible(struct device_node *np,const char *p) {
    return !strcmp(p,np->root?"qcom,msm-cam-smmu":"qcom,msm-cam-smmu-cb");
}
static void cam_smmu_iommu_fault_handler(void) {
    assert(iommu_cb_set.smmu_work && iommu_cb_set.payload_list_lock &&
           iommu_cb_set.payload_list);
}
static void iommu_set_fault_handler(struct iommu_domain *d,
    void (*handler)(void),void *name) {
    assert(d==&domain && name==cb.name);handler_calls++;handler();
}
static int cam_alloc_smmu_context_banks(struct device *dev) {
    (void)dev;return alloc_error;
}
#define INIT_WORK(w,f) do { (void)(f);*(w)=1; } while(0)
#define mutex_init(m) (*(m)=1)
#define INIT_LIST_HEAD(l) (*(l)=1)
static void cam_smmu_page_fault_work(void) {}
static int cam_populate_smmu_context_banks(struct device *,enum cam_iommu_type);
static int of_platform_populate(struct device_node *np,void *match,
    void *lookup,struct device *parent) {
    struct device_node child={0};struct device dev={.of_node=&child};
    (void)np;(void)match;(void)lookup;(void)parent;
    assert(iommu_cb_set.smmu_work && iommu_cb_set.payload_list_lock &&
           iommu_cb_set.payload_list);
    /* Child probe failure does not make device creation fail. */
    cam_populate_smmu_context_banks(&dev,CAM_ARM_SMMU);return 0;
}
'''
        harness += functions + r'''
int main(void) {
    struct device_node root={.root=1},child={0};
    struct platform_device p={.dev={.of_node=&root}},c={.dev={.of_node=&child}};
    for(int scenario=0;scenario<6;scenario++) {
        memset(&cb,0,sizeof(cb));memset(&iommu_cb_set,0,sizeof(iommu_cb_set));
        iommu_cb_set.cb_info=&cb;iommu_cb_set.cb_num=1;
        fail=scenario<3?scenario:0;label_error=scenario==3;
        scratch_error=scenario==4;alloc_error=scenario==5?-ENOMEM:0;
        handler_calls=scratch_calls=0;
        int rc=cam_smmu_probe(&p);
        assert(rc==(alloc_error?-ENOMEM:0));assert(iommu_cb_set.cb_info==&cb);
        if(!scenario) {
            assert(handler_calls==1 && iommu_cb_set.cb_init_count==1);
            assert(cb.dev && cb.domain==&domain);
            assert(cam_smmu_probe(&c)==-EBADHANDLE);
        }else {
            assert(!handler_calls && !iommu_cb_set.cb_init_count);
            assert(!cb.domain && !cb.dev && !cb.scratch_map.bitmap);
            if(fail)assert(!scratch_calls);
            if(!alloc_error)assert(cam_smmu_probe(&c)==
                (fail==1?-ENODEV:fail==2?-517:label_error?-EINVAL:-ENOMEM));
        }
        free(cb.scratch_map.bitmap);
    }
    assert(cam_smmu_setup_cb(NULL,&p.dev)==-EINVAL);
    assert(cam_populate_smmu_context_banks(NULL,CAM_ARM_SMMU)==-ENODEV);
    puts("SMMU NULL/deferred domain, allocation/label failures, immediate fault and table preservation PASS");
}
'''
        run_c(harness)


if __name__ == "__main__":
    unittest.main()
