#!/usr/bin/env python3
"""Exercise CPP publication readiness and probe failure resource ownership."""

import unittest
import re

from test_camera_pixel_pipeline import run_c
from test_camera_power_domains import CAM, function


class CppProbe(unittest.TestCase):
    def test_registration_requires_snapshot(self):
        source = (CAM / "pproc/cpp/msm_cpp.c").read_text()
        init = re.search(r"^static int __init msm_cpp_init_module\(void\)\n\{.*?^}",
                         source, re.M | re.S)[0]
        self.assertIn("late_initcall(msm_cpp_init_module);", source)
        self.assertNotIn("module_init(msm_cpp_init_module);", source)
        run_c(r'''
#include <assert.h>
#include <errno.h>
#define __init
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
static int camera_legacy_enable,ready,waits,registrations,registration_error;
static int cpp_driver;
static int ramoops_wait_snapshot_ready(unsigned int ms) {
    assert(ms==10000);waits++;return ready?0:-ETIMEDOUT;
}
static int platform_driver_register(int *d) {
    assert(d==&cpp_driver && ready);registrations++;return registration_error;
}
''' + init + r'''
int main(void) {
    assert(msm_cpp_init_module()==-ENODEV && !waits && !registrations);
    camera_legacy_enable=1;
    assert(msm_cpp_init_module()==-ETIMEDOUT && waits==1 && !registrations);
    ready=1;assert(!msm_cpp_init_module() && waits==2 && registrations==1);
    registration_error=-EIO;
    assert(msm_cpp_init_module()==-EIO && registrations==2);
}
''')

    def test_open_memory_failure_releases_hardware(self):
        source = (CAM / "pproc/cpp/msm_cpp.c").read_text()
        run_c(r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stddef.h>
#define CPP_DBG(...) ((void)0)
#define pr_err(...) ((void)0)
#define MAX_ACTIVE_CPP_INSTANCE 2
#define VBIF_CLIENT_CPP 1
#define CPP_STATE_IDLE 3
struct v4l2_subdev {void *data;};
struct v4l2_subdev_fh {int vfh;};
struct cpp_device {int mutex,cpp_open_cnt,state;
    struct {int active;int *vfh;} cpp_subscribe_list[2];};
static int hardware_error,memory_error,hardware,releases;
static void *v4l2_get_subdevdata(struct v4l2_subdev *sd) {return sd->data;}
static void mutex_lock(int *m) {assert(!*m);*m=1;}
static void mutex_unlock(int *m) {assert(*m);*m=0;}
static void legacy_cpp_vbif_error_handler(void) {}
static void legacy_msm_cpp_vbif_register_error_handler(struct cpp_device *c,
    int id,void (*handler)(void)) {(void)c;(void)id;(void)handler;}
static int cpp_init_hardware(struct cpp_device *c) {
    (void)c;if(hardware_error)return hardware_error;hardware++;return 0;
}
static int cpp_init_mem(struct cpp_device *c) {(void)c;assert(hardware==1);return memory_error;}
static void cpp_release_hardware(struct cpp_device *c) {
    (void)c;assert(hardware==1);hardware--;releases++;
}
''' + function(source, "cpp_open_node") + r'''
int main(void) {
    for(int mode=0;mode<3;mode++) {
        struct cpp_device c={0};struct v4l2_subdev sd={&c};struct v4l2_subdev_fh fh={0};
        hardware_error=mode==1?-EIO:0;memory_error=mode==2?-ENODEV:0;
        hardware=releases=0;
        int rc=cpp_open_node(&sd,&fh);
        assert(!c.mutex);
        if(mode) {
            assert(rc==(mode==1?-EIO:-ENODEV));
            assert(!hardware && !c.cpp_open_cnt && !c.cpp_subscribe_list[0].active);
            assert(!c.cpp_subscribe_list[0].vfh && releases==(mode==2));
        } else {
            assert(!rc && hardware==1 && c.cpp_open_cnt==1 && c.state==CPP_STATE_IDLE);
            assert(c.cpp_subscribe_list[0].vfh==&fh.vfh);
            /* A second opener shares the initialized hardware. */
            assert(!cpp_open_node(&sd,&fh) && c.cpp_open_cnt==2 && hardware==1);
            assert(cpp_open_node(&sd,&fh)==-ENODEV && !c.mutex);
        }
    }
}
''')

    def test_fault_matrix(self):
        source = (CAM / "pproc/cpp/msm_cpp.c").read_text()
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define GFP_KERNEL 0
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define CPP_DBG(...) ((void)0)
#define pr_err(...) ((void)0)
#define V4L2_SUBDEV_FL_HAS_DEVNODE 1
#define V4L2_SUBDEV_FL_HAS_EVENTS 2
#define MSM_CAMERA_SUBDEV_CPP 3
#define MSM_SD_CLOSE_3RD_CATEGORY 4
#define ISP_CPP 5
#define CPP_STATE_BOOT 6
#define CPP_STATE_OFF 7
#define CPP_IOMMU_STATE_DETACHED 8
#define MSM_CPP_MAX_TIMEOUT_TRIAL 9
#define MSM_CPP_MICRO_IRQGEN_MASK 0
#define MSM_CPP_MICRO_IRQGEN_CLR 4
#define CONFIG_COMPAT 1
struct device { int pm_domain; };
struct platform_device { struct device dev; const char *name; void *data; };
struct entity { const char *name; int initialized; };
struct fops { int unlocked_ioctl,compat_ioctl32; };
struct video_device { struct fops *fops; };
struct subdev { void *internal_ops; int flags,grp_id; char name[32];
    struct entity entity; struct video_device *devnode; void *data; };
struct msm_sd_subdev { struct subdev sd; int close_seq; };
struct work_struct { int ready; };
struct msm_cpp_work_t { struct work_struct work; };
struct msm_cpp_vbif_data { int unused; };
struct cpp_device {
    struct msm_sd_subdev msm_sd; struct platform_device *pdev;
    int mutex,tasklet_lock,eventData_q,processing_q,tasklet_q,cpp_tasklet;
    struct msm_cpp_vbif_data *vbif_data;
    void *base,*vbif_base,*cpp_hw_base,*camss_cpp_base,*irq;
    void *clk_info,*cpp_clk,*micro_iface_reset;
    int num_clks,bus_master_flag,state,cpp_open_cnt,is_firmware_loaded;
    int iommu_state,max_timeout_trial_cnt;
    struct device *power_domain; void *timer_wq; struct msm_cpp_work_t *work;
    char *fw_name_bin;
};
static struct { struct {int processed_frame_lock; struct cpp_device *cpp_dev;} data;
    int used,legacy_cpp_timer; } legacy_cpp_timer;
static struct msm_cpp_vbif_data cpp_vbif;
static struct fops legacy_msm_cpp_v4l2_subdev_fops;
static int msm_cpp_subdev_ops,msm_cpp_internal_ops;
#define msm_cpp_subdev_fops_ioctl 1
#define msm_cpp_subdev_fops_compat_ioctl 2
static struct video_device node;
enum { ALLOC=1,BASE,VBIF,HWBASE,IRQ,CLOCK,RESET,DOMAIN,PAYLOAD,BUS,
       WQ,WORK,HW,ENTITY,REGISTER };
static int fault,master,borrowed,allocs,mappings,clocks,resets,pdomains;
static int bandwidth,queues,tasklets,entities,registered,hardware,disables,detaches;
static int token;
#define IS_ERR(p) ((intptr_t)(p)<0)
#define IS_ERR_OR_NULL(p) (!(p)||IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define spin_lock_init(p) (*(p)=1)
#define mutex_init(p) (*(p)=1)
#define mutex_destroy(p) do {assert(*(p));*(p)=0;}while(0)
#define INIT_LIST_HEAD(p) (*(p)=1)
#define atomic_set(p,v) (*(p)=(v))
#define INIT_WORK(p,fn) ((p)->ready=1)
#define timer_setup(p,fn,flags) (*(p)=1)
#define tasklet_init(p,fn,data) do {*(p)=1;tasklets++;}while(0)
static void tasklet_kill(int *p) {assert(*p);*p=0;tasklets--;}
static void *allocate(size_t size,int stage) {
    if(fault==stage)return NULL;
    allocs++;return calloc(1,size);
}
#define kzalloc(n,f) allocate(n,ALLOC)
#define kmalloc(n,f) allocate(n,WORK)
static void kfree(void *p) {if(p){allocs--;free(p);}}
static void v4l2_subdev_init(struct subdev *sd,int *ops) {(void)sd;(void)ops;}
static void v4l2_set_subdevdata(struct subdev *sd,void *p) {sd->data=p;}
static void platform_set_drvdata(struct platform_device *p,void *data) {p->data=data;}
static void *legacy_msm_camera_get_reg_base(struct platform_device *p,
    const char *name,bool managed) {
    (void)p;(void)managed;
    int stage=!strcmp(name,"cpp")?BASE:!strcmp(name,"cpp_vbif")?VBIF:HWBASE;
    if(fault==stage)return NULL;
    mappings++;return &token;
}
static void legacy_msm_camera_put_reg_base(struct platform_device *p,void *addr,
    const char *name,bool managed) {
    (void)p;(void)name;(void)managed;if(addr)mappings--;
}
static void *legacy_msm_camera_get_irq(struct platform_device *p,const char *name) {
    (void)p;(void)name;return fault==IRQ?(void *)(intptr_t)-517:&token;
}
static int legacy_msm_camera_get_clk_info(struct platform_device *p,void **i,
    void **clk,int *count) {
    (void)p;(void)i;(void)clk;(void)count;
    if(fault==CLOCK)return -517;
    clocks++;return 0;
}
static void legacy_msm_camera_put_clk_info(struct platform_device *p,void **i,
    void **clk,int count) {(void)p;(void)i;(void)clk;(void)count;clocks--;}
static int legacy_msm_camera_get_reset_info(struct platform_device *p,void **r) {
    (void)p;if(fault==RESET)return -517;resets++;*r=&token;return 0;
}
static void reset_control_put(void *r) {if(r)resets--;}
static struct device virtual_domain;
static struct device *dev_pm_domain_attach_by_name(struct device *d,const char *n) {
    (void)d;assert(!strcmp(n,"cpp"));
    if(fault==DOMAIN)return (void *)(intptr_t)-517;
    pdomains++;return &virtual_domain;
}
static void pm_runtime_enable(struct device *d) {(void)d;pdomains++;}
static void pm_runtime_disable(struct device *d) {(void)d;pdomains--;disables++;}
static void dev_pm_domain_detach(struct device *d,bool power_off) {
    assert(d==&virtual_domain && power_off);pdomains--;detaches++;
}
static void legacy_msm_cpp_fetch_dt_params(struct cpp_device *c) {c->bus_master_flag=master;}
static int legacy_msm_cpp_read_payload_params_from_dt(struct cpp_device *c) {
    (void)c;return fault==PAYLOAD?-EINVAL:0;
}
static int msm_cpp_init_bandwidth_mgr(struct cpp_device *c) {
    (void)c;if(fault==BUS)return -EINVAL;bandwidth++;return 0;
}
static int legacy_msm_isp_init_bandwidth_mgr(void *p,int id) {
    (void)p;(void)id;return msm_cpp_init_bandwidth_mgr(NULL);
}
static void legacy_msm_cpp_deinit_bandwidth_mgr(struct cpp_device *c) {(void)c;bandwidth--;}
static void legacy_msm_isp_deinit_bandwidth_mgr(int id) {(void)id;bandwidth--;}
static void msm_queue_init(int *q,const char *name) {(void)name;*q=1;}
static void *create_workqueue(const char *name) {
    (void)name;if(fault==WQ)return NULL;queues++;return &token;
}
static void destroy_workqueue(void *q) {assert(q);queues--;}
static void ready(struct cpp_device *c) {
    assert(c->eventData_q && c->processing_q && c->tasklet_q && c->cpp_tasklet);
    assert(c->timer_wq && c->work && c->work->work.ready);
    assert(legacy_cpp_timer.legacy_cpp_timer && legacy_cpp_timer.data.cpp_dev==c);
}
static int cpp_init_hardware(struct cpp_device *c) {
    ready(c);assert(c->state==CPP_STATE_BOOT);
    if(fault==HW)return -EIO;
    hardware++;return 0;
}
static void cpp_release_hardware(struct cpp_device *c) {(void)c;hardware--;}
static void legacy_msm_camera_io_w(unsigned int value,void *addr) {
    (void)value;(void)addr;assert(hardware==1);
}
static int media_entity_pads_init(struct entity *e,int n,void *pads) {
    (void)n;(void)pads;if(fault==ENTITY)return -ENOMEM;
    e->initialized=1;entities++;return 0;
}
static void media_entity_cleanup(struct entity *e) {assert(e->initialized);entities--;}
static void legacy_msm_cam_copy_v4l2_subdev_fops(struct fops *f) {(void)f;}
static int legacy_msm_sd_register(struct msm_sd_subdev *sd) {
    struct cpp_device *c=sd->sd.data;ready(c);
    assert(c->state==CPP_STATE_OFF && !hardware && sd->sd.entity.initialized);
    if(fault==REGISTER)return -EIO;
    registered++;sd->sd.devnode=&node;return 0;
}
static int msm_cpp_enable_debugfs(struct cpp_device *c) {ready(c);return 0;}
'''
        harness += "\n".join(function(source, name) for name in (
            "cpp_get_power_domain", "cpp_put_power_domain", "cpp_probe"))
        harness += r'''
int main(void) {
    for(master=0;master<2;master++) for(borrowed=0;borrowed<2;borrowed++)
    for(fault=0;fault<=REGISTER;fault++) {
        if(borrowed && fault==DOMAIN)continue;
        struct platform_device p={.dev={borrowed},.name="cpp"};
        memset(&legacy_cpp_timer,0,sizeof(legacy_cpp_timer));
        disables=detaches=0;
        int rc=cpp_probe(&p);
        if(!fault) {
            assert(!rc && registered==1 && p.data);
            struct cpp_device *c=((struct subdev *)p.data)->data;
            assert(node.fops==&legacy_msm_cpp_v4l2_subdev_fops);
            registered--;media_entity_cleanup(&c->msm_sd.sd.entity);
            destroy_workqueue(c->timer_wq);tasklet_kill(&c->cpp_tasklet);
            kfree(c->work);cpp_put_power_domain(c);
            mappings=clocks=resets=bandwidth=0;kfree(c);
        } else {
            int expected=fault==IRQ||fault==CLOCK||fault==RESET||fault==DOMAIN?-517:
                fault==PAYLOAD||fault==BUS?-EINVAL:fault==HW||fault==REGISTER?-EIO:-ENOMEM;
            assert(rc==expected && !p.data && !legacy_cpp_timer.data.cpp_dev);
        }
        assert(!allocs && !mappings && !clocks && !resets && !pdomains);
        assert(!bandwidth && !queues && !tasklets && !entities && !hardware && !registered);
        assert(borrowed?!detaches:!disables);
    }
    puts("CPP probe readiness and 62 ownership/failure scenarios PASS");
}
'''
        for compat in (False, True):
            with self.subTest(compat=compat):
                run_c(harness if compat else
                      harness.replace("#define CONFIG_COMPAT 1", ""))

    def test_boot_cleanup_has_no_unregistered_irq(self):
        source = (CAM / "pproc/cpp/msm_cpp.c").read_text()
        init = function(source, "cpp_init_hardware")
        cleanup = init[init.index("pwr_collapse_reset:"):init.index("req_irq_fail:")]
        run_c(r'''
#include <assert.h>
#include <stdbool.h>
#define CPP_STATE_BOOT 1
struct cpp_device {int state;void *pdev,*irq;};
static int frees;
static void msm_cpp_update_gdscr_status(struct cpp_device *c,bool s) {(void)c;(void)s;}
static void legacy_msm_camera_unregister_irq(void *p,void *i,struct cpp_device *c) {
    (void)p;(void)i;(void)c;frees++;
}
static void cleanup(struct cpp_device *cpp_dev) {
    goto pwr_collapse_reset;
''' + cleanup + r'''
}
int main(void) {
    struct cpp_device c={.state=CPP_STATE_BOOT};cleanup(&c);assert(!frees);
    c.state=0;cleanup(&c);assert(frees==1);
}
''')


if __name__ == "__main__":
    unittest.main()
