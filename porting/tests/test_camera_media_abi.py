#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the camera's legacy media ioctls using the real core functions."""

from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CAM = ROOT / "drivers/media/platform/msm/camera"
CORE = ROOT / "drivers/media/mc/mc-device.c"


def function(source, name):
    return re.search(r"^static [^\n]*\b" + name + r"\(.*?^}",
                     source, re.M | re.S)[0]


STUBS = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#define __user
#include "include/uapi/linux/media.h"
typedef uint32_t u32;
typedef uint32_t compat_uptr_t;
#define U32_MAX UINT32_MAX
#define GFP_KERNEL 0
#define ENOIOCTLCMD 515
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define MEDIA_IOC_FL_GRAPH_MUTEX 1
#define QCAMERA_VNODE_GROUP_ID 2
#define MSM_CAMERA_SUBDEV_CPP 9
#define MSM_CAMERA_SUBDEV_VPE 5
struct media_device;
struct media_device_ops;
struct media_pad;
struct list_head { struct list_head *next, *prev; };
struct media_entity {
    struct { struct media_device *mdev; u32 id; } graph_obj;
    struct media_entity *next;
    const char *name;
    unsigned obj_type, function, flags, num_pads, num_links, num_backlinks;
    int internal_idx;
    struct media_pad *pads;
    struct list_head links;
    union { struct { u32 major, minor; } dev; } info;
};
struct video_device { int num; };
struct v4l2_subdev { struct media_entity entity; u32 grp_id; struct video_device *devnode; };
struct media_pad { struct media_entity *entity; unsigned index, flags; };
struct media_link { struct list_head list; struct media_pad *source, *sink; u32 flags; };
struct media_device { const struct media_device_ops *ops; struct media_entity *entities; int graph_mutex; };
struct media_devnode { struct media_device *media_dev; };
struct file { struct media_devnode *node; };
static bool copy_fault;
static unsigned lock_calls, setup_calls;
static void mutex_lock(int *m) { assert(!*m); ++*m; ++lock_calls; }
static void mutex_unlock(int *m) { assert(*m == 1); --*m; }
static u32 media_entity_id(struct media_entity *e) { return e->graph_obj.id; }
static bool is_media_entity_v4l2_subdev(struct media_entity *e) { return e->obj_type == 2; }
static bool is_media_entity_v4l2_video_device(struct media_entity *e) { return e->obj_type == 1; }
#define media_entity_to_v4l2_subdev(e) ((struct v4l2_subdev *)(e))
#define media_device_for_each_entity(e,m) for ((e)=(m)->entities; (e); (e)=(e)->next)
#define entry(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(e,h,m) \
    for (struct list_head *p_=(h)->next; p_!=(h) && ((e)=entry(p_,__typeof__(*(e)),m),1); p_=p_->next)
static void init_list(struct list_head *h) { h->next=h->prev=h; }
static void add_link(struct list_head *h, struct list_head *l) {
    l->next=h; l->prev=h->prev; h->prev->next=l; h->prev=l;
}
static size_t copy_to_user(void *d, const void *s, size_t n) {
    if (copy_fault || !d) return n;
    memcpy(d,s,n); return 0;
}
static size_t copy_from_user(void *d, const void *s, size_t n) {
    if (copy_fault || !s) return n;
    memcpy(d,s,n); return 0;
}
#define get_user(v,p) ((v)=*(p),0)
#define compat_ptr(p) ((void *)(uintptr_t)(p))
#define kmalloc(n,f) malloc(n)
#define kfree(p) free(p)
#define media_devnode_data(f) ((f)->node)
#define strscpy(d,s,n) snprintf(d,n,"%s",s)
static struct media_link *media_entity_find_link(struct media_pad *a, struct media_pad *b) {
    struct media_link *l;
    list_for_each_entry(l,&a->entity->links,list)
        if (l->source==a && l->sink==b) return l;
    return NULL;
}
static int __media_entity_setup_link(struct media_link *l, u32 flags) {
    ++setup_calls; l->flags=flags; return 0;
}
'''

CHECKS = r'''
int main(void) {
    struct media_device m={0};
    struct media_entity video={.graph_obj={&m,1},.name="video0",.obj_type=1,
        .function=MEDIA_ENT_F_IO_V4L,.internal_idx=1};
    struct v4l2_subdev sensor={.entity={.graph_obj={&m,4},.name="v4l-subdev0",
        .obj_type=2,.function=MEDIA_ENT_F_V4L2_SUBDEV_UNKNOWN,.internal_idx=2},.grp_id=14};
    struct v4l2_subdev actuator={.entity={.graph_obj={&m,9},.name="v4l-subdev2",
        .obj_type=2,.function=MEDIA_ENT_F_V4L2_SUBDEV_UNKNOWN,.internal_idx=3},.grp_id=7};
    struct media_pad pads[2]={{&sensor.entity,0,MEDIA_PAD_FL_SOURCE},
                              {&actuator.entity,0,MEDIA_PAD_FL_SINK}};
    struct media_link link={.source=&pads[0],.sink=&pads[1],.flags=MEDIA_LNK_FL_ENABLED};
    struct media_devnode node={&m}; struct file f={&node};
    struct media_entity_desc desc;
    struct media_pad_desc out_pad;
    struct media_link_desc out_link;
    struct media_links_enum links={.entity=4,.pads=&out_pad,.links=&out_link};
    struct media_links_enum32 links32={.entity=2};
    const struct media_device_ops native_ops={0}, camera_ops={.legacy_entity_info=msm_legacy_entity_info};
    _Static_assert(sizeof(struct media_entity_desc)==256,"entity ABI");
    _Static_assert(offsetof(struct media_entity_desc,group_id)==48,"group ABI");
    _Static_assert(MEDIA_IOC_ENUM_ENTITIES==0xc1007c01U,"installed ARM HAL ioctl");
    video.info.dev.major=81; video.info.dev.minor=0;
    sensor.entity.info.dev.major=81; sensor.entity.info.dev.minor=1;
    m.entities=&video; video.next=&sensor.entity; sensor.entity.next=&actuator.entity;
    init_list(&video.links); init_list(&sensor.entity.links); init_list(&actuator.entity.links);
    add_link(&sensor.entity.links,&link.list);
    sensor.entity.pads=&pads[0]; sensor.entity.num_pads=1; sensor.entity.num_links=1;
    actuator.entity.pads=&pads[1]; actuator.entity.num_pads=1;
    /* The unmodified sparse graph reproduces the HAL's first failure. */
    for (unsigned mode=0;mode<2;mode++) {
        m.ops=mode?&native_ops:NULL;
        desc=(struct media_entity_desc){.id=2};
        assert(media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc)==-EINVAL);
        desc.id=4; assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
        assert(desc.id==4 && desc.group_id==0 && desc.dev.minor==1);
        assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_LINKS,(unsigned long)&links));
        assert(out_pad.entity==4 && out_link.source.entity==4 && out_link.sink.entity==9);
    }
    m.ops=&camera_ops;
    for(unsigned id=1;id<=3;id++) {
        desc=(struct media_entity_desc){.id=id};
        assert(!media_device_compat_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
        assert(desc.id==id);
        assert(desc.group_id==(id==1?2:id==2?14:7));
        if(id==2) assert(!strcmp(desc.name,"v4l-subdev0") && desc.type==0x20000 && desc.dev.minor==1);
    }
    desc.id=4; assert(media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc)==-EINVAL);
    desc.id=0; assert(media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc)==-EINVAL);
    /* NEXT must choose the lowest ID even after an internal ID is reused. */
    video.next=&actuator.entity; actuator.entity.next=&sensor.entity; sensor.entity.next=NULL;
    desc.id=MEDIA_ENT_ID_FLAG_NEXT|1;
    assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
    assert(desc.id==2 && desc.group_id==14);
    desc.id=MEDIA_ENT_ID_FLAG_NEXT|3;
    assert(media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc)==-EINVAL);
    links.entity=2;
    assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_LINKS,(unsigned long)&links));
    assert(out_pad.entity==2 && out_link.source.entity==2 && out_link.sink.entity==3);
    assert(out_pad.index==0 && out_pad.flags==MEDIA_PAD_FL_SOURCE);
    out_link.flags=0;
    assert(!media_device_compat_ioctl(&f,MEDIA_IOC_SETUP_LINK,(unsigned long)&out_link));
    assert(setup_calls==1 && link.flags==0);
    out_link.source.index=1;
    assert(media_device_ioctl(&f,MEDIA_IOC_SETUP_LINK,(unsigned long)&out_link)==-EINVAL);
    out_link.source.index=0; out_link.sink.entity=99;
    assert(media_device_ioctl(&f,MEDIA_IOC_SETUP_LINK,(unsigned long)&out_link)==-EINVAL);
    memset(links32.reserved,0xa5,sizeof(links32.reserved));
    assert(!media_device_compat_ioctl(&f,MEDIA_IOC_ENUM_LINKS32,(unsigned long)&links32));
    for(unsigned i=0;i<4;i++)assert(!links32.reserved[i]);
    links32.entity=99;
    assert(media_device_compat_ioctl(&f,MEDIA_IOC_ENUM_LINKS32,(unsigned long)&links32)==-EINVAL);
    copy_fault=true; desc.id=2;
    assert(media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc)==-EFAULT);
    copy_fault=false;
    /* CPP stores revision, then opens /dev/v4l-subdev<revision>. */
    struct video_device cpp_node={.num=16};
    actuator.devnode=&cpp_node;
    actuator.entity.info.dev.major=81;actuator.entity.info.dev.minor=19;
    for(unsigned group=0;group<2;group++) {
        actuator.grp_id=group?MSM_CAMERA_SUBDEV_VPE:MSM_CAMERA_SUBDEV_CPP;
        for(unsigned compat=0;compat<2;compat++) {
            desc=(struct media_entity_desc){.id=3,.revision=0xa5a5a5a5};
            assert(!(compat?media_device_compat_ioctl:media_device_ioctl)(
                &f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
            assert(desc.revision==16 && desc.dev.minor==19);
            char selected[32];snprintf(selected,sizeof(selected),"/dev/v4l-subdev%u",desc.revision);
            assert(!strcmp(selected,"/dev/v4l-subdev16"));
        }
        /* Lookup/link paths do not request a revision output. */
        u32 id,group_id;
        media_device_legacy_entity_info(&actuator.entity,&id,&group_id,NULL);
        assert(id==3 && group_id==actuator.grp_id);
        cpp_node.num=7;
        desc.id=3;assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
        assert(desc.revision==7);
        cpp_node.num=16;actuator.devnode=NULL;
        desc.id=3;assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
        assert(!desc.revision);
        actuator.devnode=&cpp_node;
    }
    /* Native devices keep revision zero even for a CPP-shaped entity. */
    m.ops=NULL;desc.id=9;
    assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
    assert(!desc.revision && !desc.group_id && desc.id==9);
    m.ops=&native_ops;desc.id=9;
    assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
    assert(!desc.revision);
    m.ops=&camera_ops;actuator.grp_id=7;
    for(unsigned id=1;id<=3;id++) {
        desc.id=id;assert(!media_device_ioctl(&f,MEDIA_IOC_ENUM_ENTITIES,(unsigned long)&desc));
        assert(!desc.revision);
    }
    assert(video.graph_obj.id==1 && sensor.entity.graph_obj.id==4 && actuator.entity.graph_obj.id==9);
    assert(!m.graph_mutex && lock_calls>10);
    puts("native defaults, HAL scan, CPP/VPE revision paths, NEXT, links and compat faults PASS");
}
'''


class CameraMediaABI(unittest.TestCase):
    def test_donor_group_metadata_is_preserved(self):
        expected = {
            "isp/msm_isp.c": ("VFE", 3, 1),
            "ispif/msm_ispif.c": ("ISPIF", 2, 1),
            "msm_buf_mgr/msm_generic_buf_mgr.c": ("BUF_MNGR", 13, 1),
            "pproc/cpp/msm_cpp.c": ("CPP", 9, 1),
            "pproc/vpe/msm_vpe.c": ("VPE", 5, 1),
            "sensor/actuator/msm_actuator.c": ("ACTUATOR", 7, 2),
            "sensor/cci/msm_cci.c": ("CCI", 10, 1),
            "sensor/csid/msm_csid.c": ("CSID", 1, 1),
            "sensor/csiphy/msm_csiphy.c": ("CSIPHY", 0, 1),
            "sensor/eeprom/msm_eeprom.c": ("EEPROM", 8, 3),
            "sensor/flash/msm_flash.c": ("FLASH", 16, 2),
            "sensor/ir_cut/msm_ir_cut.c": ("IR_CUT", 18, 1),
            "sensor/ir_led/msm_ir_led.c": ("IR_LED", 17, 1),
            "sensor/msm_sensor_driver.c": ("SENSOR", 6, 2),
            "sensor/msm_sensor_init.c": ("SENSOR_INIT", 14, 1),
            "sensor/ois/msm_ois.c": ("OIS", 15, 2),
        }
        header = (ROOT / "include/uapi/media/msmb_camera-legacy.h").read_text()
        for path, (name, value, count) in expected.items():
            with self.subTest(path=path):
                constant = "MSM_CAMERA_SUBDEV_" + name
                self.assertRegex(header, r"#define " + constant + r"\s+" + str(value) + r"\b")
                assigned = re.findall(r"\.grp_id = (MSM_CAMERA_SUBDEV_\w+);",
                                      (CAM / path).read_text())
                self.assertEqual(assigned, [constant] * count)

    def test_real_media_ioctl_functions(self):
        source = CORE.read_text()
        header = (ROOT / "include/media/media-device.h").read_text()
        ops = re.search(r"^struct media_device_ops {.*?^};", header, re.M | re.S)[0]
        ops = ops.replace("struct media_device_ops {", "struct media_request;\nstruct media_device_ops {")
        code = STUBS + ops + "\n"
        code += function((CAM / "msm.c").read_text(), "msm_legacy_entity_info")
        for name in ("media_device_legacy_entity_info", "find_entity",
                     "media_device_enum_entities", "media_device_kpad_to_upad",
                     "media_device_enum_links", "media_device_setup_link",
                     "copy_arg_from_user", "copy_arg_to_user"):
            code += "\n" + function(source, name)
        code += re.search(r"^struct media_ioctl_info {.*?^};", source, re.M | re.S)[0]
        code += r'''
static const struct media_ioctl_info ioctl_info[] = {
 [1]={MEDIA_IOC_ENUM_ENTITIES,1,media_device_enum_entities,copy_arg_from_user,copy_arg_to_user},
 [2]={MEDIA_IOC_ENUM_LINKS,1,media_device_enum_links,copy_arg_from_user,copy_arg_to_user},
 [3]={MEDIA_IOC_SETUP_LINK,1,media_device_setup_link,copy_arg_from_user,copy_arg_to_user},
};
'''
        code += function(source, "media_device_ioctl")
        code += re.search(r"^struct media_links_enum32 {.*?^};", source, re.M | re.S)[0]
        code += "\n#define MEDIA_IOC_ENUM_LINKS32 _IOWR('|',2,struct media_links_enum32)\n"
        code += function(source, "media_device_enum_links32")
        code += function(source, "media_device_compat_ioctl") + CHECKS
        with tempfile.TemporaryDirectory(prefix="camera-media-abi-") as directory:
            c = Path(directory) / "check.c"
            exe = Path(directory) / "check"
            c.write_text(code)
            flags = os.environ.get("CAMERA_ABI_CFLAGS", "").split()
            subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", *flags, "-I", str(ROOT),
                            str(c), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_arm32_and_arm64_uapi_layout(self):
        source = (ROOT / "include/uapi/linux/media.h").read_text()
        code = "#define __user\ntypedef unsigned int __u32; typedef unsigned short __u16; typedef unsigned char __u8;\n"
        for name in ("media_entity_desc", "media_links_enum"):
            code += re.search(r"^struct " + name + r" {.*?^};", source, re.M | re.S)[0]
        code += '\n_Static_assert(sizeof(struct media_entity_desc)==256,"entity size");\n'
        code += '_Static_assert(__builtin_offsetof(struct media_entity_desc,revision)==40,"revision offset");\n'
        code += '_Static_assert(__builtin_offsetof(struct media_entity_desc,group_id)==48,"group offset");\n'
        with tempfile.TemporaryDirectory(prefix="camera-media-layout-") as directory:
            c = Path(directory) / "layout.c"
            for target, size in (("armv7a-linux-gnueabi", 28), ("aarch64-linux-gnu", 40)):
                c.write_text(code + f'_Static_assert(sizeof(struct media_links_enum)=={size},"links size");\n')
                subprocess.run(["clang", "--target=" + target, "-nostdinc",
                                "-fsyntax-only", "-Werror", str(c)], check=True)


if __name__ == "__main__":
    unittest.main()
