#!/usr/bin/env python3
"""Check real camera headers and converters against the donor's time32 ABI."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_camera_power_domains import CAM, ROOT
from test_camera_media_abi import function

DONOR = ROOT.parent / "oc-test/techpack/camera-legacy/include/media"


def declaration(source, name):
    start = source.index("struct " + name + " {")
    depth = 0
    for pos in range(source.index("{", start), len(source)):
        depth += (source[pos] == "{") - (source[pos] == "}")
        if depth == 0:
            return source[start:pos + 2]
    raise AssertionError(name)


class CompatTime(unittest.TestCase):
    def run_host(self, body):
        with tempfile.TemporaryDirectory(prefix="camera-time32-") as folder:
            path = Path(folder)
            (path / "linux").mkdir()
            (path / "media").symlink_to(ROOT / "include/media")
            (path / "uapi").symlink_to(ROOT / "include/uapi")
            # Compile the actual media headers; stub only kernel dependencies.
            (path / "linux/time32.h").write_text(
                "#pragma once\ntypedef int32_t s32;\n" +
                (ROOT / "include/vdso/time32.h").read_text())
            (path / "linux/compat.h").write_text(
                "#pragma once\n#include <linux/time32.h>\n"
                "typedef uint32_t compat_uint_t,compat_caddr_t;\n"
                "typedef int32_t compat_int_t,compat_long_t;\n")
            video = declaration((ROOT / "include/uapi/linux/videodev2.h").read_text(),
                                "__kernel_v4l2_timeval")
            old_time = declaration((ROOT / "include/uapi/linux/time_types.h").read_text(),
                                   "__kernel_old_timeval")
            prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <linux/types.h>
#define __user
#define CONFIG_COMPAT 1
'''
            prefix += old_time + "\n" + video + r'''
#include <media/msmb_generic_buf_mgr-legacy.h>
#include <media/msmb_isp-legacy.h>
#include <media/msmb_pproc-legacy.h>
'''
            cfile, exe = path / "test.c", path / "test"
            cfile.write_text(prefix + body)
            flags = ["-Wall", "-Wextra", "-Werror"]
            if os.environ.get("CAMERA_TEST_SANITIZERS"):
                flags += ["-fsanitize=" + os.environ["CAMERA_TEST_SANITIZERS"]]
            subprocess.run([os.environ.get("CC", "cc"), *flags, "-I" + str(path),
                            str(cfile), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=10)

    def test_donor_layouts_and_ioctl_numbers(self):
        self.assertTrue(DONOR.is_dir(), "donor headers required for ABI comparison")
        pairs = {
            "msmb_generic_buf_mgr-legacy.h": ["msm_buf_mngr_info32_t"],
            "msmb_isp-legacy.h": ["msm_isp_event_data32", "msm_isp32_event_data32"],
            "msmb_pproc-legacy.h": ["msm_cpp_frame_info32_t",
                                      "msm_pproc_queue_buf_info32_t"],
        }
        code = "#define compat_timeval old_timeval32\n"
        checks = []
        for header, names in pairs.items():
            text = (DONOR / header).read_text()
            for name in names:
                decl = declaration(text, name)
                for all_names in pairs.values():
                    for other in all_names:
                        decl = re.sub(r"\b" + other + r"\b", "donor_" + other, decl)
                code += decl + "\n"
                checks.append(f'_Static_assert(sizeof(struct {name}) == '
                              f'sizeof(struct donor_{name}), "{name} size");')
        for name, fields in {
            "msm_buf_mngr_info32_t": ["timestamp", "index", "user_buf"],
            "msm_isp_event_data32": ["mono_timestamp", "frame_id", "u"],
            "msm_isp32_event_data32": ["input_intf", "frame_id", "u"],
            "msm_cpp_frame_info32_t": ["timestamp", "inst_id", "in_time",
                                       "out_time", "cookie", "batch_info"],
        }.items():
            for field in fields:
                checks.append(f'_Static_assert(offsetof(struct {name}, {field}) == '
                              f'offsetof(struct donor_{name}, {field}), "{name}.{field}");')
        code += "\n".join(checks) + r'''
_Static_assert(sizeof(struct old_timeval32)==8, "time32");
_Static_assert(sizeof(struct msm_buf_mngr_info32_t)==100, "donor buffer size");
_Static_assert(sizeof(struct msm_buf_mngr_info)==112, "native buffer unchanged");
_Static_assert(VIDIOC_MSM_BUF_MNGR_GET_BUF32==0xc06456e1U, "GET_BUF32");
_Static_assert(VIDIOC_MSM_BUF_MNGR_PUT_BUF32==0xc06456e2U, "PUT_BUF32");
_Static_assert(VIDIOC_MSM_BUF_MNGR_BUF_DONE32==0xc06456e3U, "BUF_DONE32");
_Static_assert(VIDIOC_MSM_BUF_MNGR_FLUSH32==0xc06456e7U, "FLUSH32");
_Static_assert(offsetof(struct msm_isp_event_data32,frame_id)==16, "event frame");
_Static_assert(offsetof(struct msm_isp_event_data32,u)==20, "event payload");
_Static_assert(offsetof(struct msm_isp_event_data,frame_id)==32, "native event");
_Static_assert(sizeof(struct msm_isp_event_data32)<=64, "event payload capacity");
int main(void) {puts("Donor buffer, ISP/ISP32 and CPP compat layouts PASS");}
'''
        self.run_host(code)

    def test_buffer_ioctl_translation(self):
        source = (CAM / "msm_buf_mgr/msm_generic_buf_mgr.c").read_text()
        code = r'''
#define ENOIOCTLCMD 515
#define pr_err(...) ((void)0)
#define pr_debug(...) ((void)0)
struct v4l2_subdev {int unused;};
struct video_device {int unused;};
struct file {int unused;};
static struct video_device video;
static struct v4l2_subdev subdev;
static int copy_fault,core_error,calls;
static struct video_device *video_devdata(struct file *f) {(void)f;return &video;}
static struct v4l2_subdev *vdev_to_v4l2_subdev(struct video_device *v) {(void)v;return &subdev;}
static int copy_from_user(void *d,const void *s,size_t n) {
    if(copy_fault==1)return 1;
    memcpy(d,s,n);return 0;
}
static int copy_to_user(void *d,const void *s,size_t n) {
    if(copy_fault==2)return 1;
    memcpy(d,s,n);return 0;
}
static int core_ioctl(unsigned int cmd,void *arg) {
    struct msm_buf_mngr_info *b=arg;calls++;
    assert(cmd==VIDIOC_MSM_BUF_MNGR_GET_BUF || cmd==VIDIOC_MSM_BUF_MNGR_PUT_BUF ||
           cmd==VIDIOC_MSM_BUF_MNGR_BUF_DONE || cmd==VIDIOC_MSM_BUF_MNGR_FLUSH);
    assert(b->session_id==1 && b->stream_id==3 && b->frame_id==105);
    assert(b->timestamp.tv_sec==-1 && b->timestamp.tv_usec==999999);
    if(core_error)return core_error;
    b->index=7;b->user_buf.buf_cnt=1;b->user_buf.buf_idx[0]=9;return 0;
}
#define v4l2_subdev_call(sd,group,op,cmd,arg) ((void)(sd),core_ioctl(cmd,arg))
static long msm_camera_buf_mgr_internal_compat_ioctl(struct file *f,unsigned int c,
    unsigned long a) {(void)f;(void)c;(void)a;return -ENOIOCTLCMD;}
'''
        code += "\n".join(function(source, name) for name in (
            "msm_camera_buf_mgr_fetch_buf_info", "msm_camera_buf_mgr_update_buf_info",
            "msm_bmgr_subdev_fops_compat_ioctl"))
        code += r'''
int main(void) {
    struct file f={0};
    unsigned int cmds[]={0xc06456e1U,0xc06456e2U,0xc06456e3U,0xc06456e7U};
    for(unsigned int i=0;i<4;i++)for(copy_fault=0;copy_fault<=2;copy_fault++) {
        struct {uint32_t before;struct msm_buf_mngr_info32_t b;uint32_t after;} u={0};
        u.before=0x12345678;u.after=0xabcdef12;
        u.b.session_id=1;u.b.stream_id=3;u.b.frame_id=105;
        u.b.timestamp.tv_sec=-1;u.b.timestamp.tv_usec=999999;u.b.index=2;
        calls=0;
        int rc=msm_bmgr_subdev_fops_compat_ioctl(&f,cmds[i],(unsigned long)&u.b);
        assert(rc==(copy_fault?-EFAULT:0));assert(calls==(copy_fault!=1));
        if(!copy_fault)assert(u.b.index==7 && u.b.user_buf.buf_idx[0]==9);
        assert(u.before==0x12345678 && u.after==0xabcdef12);
    }
    struct msm_buf_mngr_info32_t b={.session_id=1,.stream_id=3,.frame_id=105,
        .timestamp={-1,999999}};
    copy_fault=0;core_error=-EIO;
    assert(msm_bmgr_subdev_fops_compat_ioctl(&f,cmds[0],(unsigned long)&b)==-EIO);
    calls=0;
    assert(msm_bmgr_subdev_fops_compat_ioctl(&f,0xc07056e1U,(unsigned long)&b)==-ENOIOCTLCMD);
    assert(!calls);
    puts("32-bit buffer ioctl dispatch, copies, canaries and errors PASS");
}
'''
        self.run_host(code)

    def test_isp_event_conversion(self):
        for filename, helper, native, compat in (
            ("msm_isp.c", "msm_isp_dqevent", "msm_isp_event_data", "msm_isp_event_data32"),
            ("msm_isp_32.c", "msm_isp_dqevent", "msm_isp32_event_data",
             "msm_isp32_event_data32")):
            with self.subTest(driver=filename):
                source = (CAM / "isp" / filename).read_text()
                wire = declaration((DONOR / "msmb_isp-legacy.h").read_text(), compat)
                code = wire.replace(compat, "daemon_event").replace(
                    "compat_timeval", "old_timeval32") + r'''
#define O_NONBLOCK 04000
struct file {int f_flags;};
struct v4l2_fh {int unused;};
static int compat_task,error;
static struct v4l2_event queued;
static int is_compat_task(void) {return compat_task;}
static int v4l2_event_dequeue(struct v4l2_fh *fh,struct v4l2_event *e,int nonblock) {
    (void)fh;(void)nonblock;if(error)return error;*e=queued;return 0;
}
'''
                code += function(source, helper)
                code += f"\n#define NATIVE {native}\n#define COMPAT {compat}\n#define DEQUEUE {helper}\n"
                code += r'''
int main(void) {
    struct file file={0};struct v4l2_fh fh={0};
    struct NATIVE *n=(void *)queued.u.data;
    n->timestamp.tv_sec=123;n->timestamp.tv_usec=456;
    n->mono_timestamp.tv_sec=789;n->mono_timestamp.tv_usec=987;
    n->frame_id=105;memset(&n->u,0x5a,sizeof(n->u));
    queued.type=0x1234;queued.sequence=42;
    for(compat_task=0;compat_task<=1;compat_task++) {
        struct {struct v4l2_event e;uint64_t canary;} out={.canary=0x123456789abcdefULL};
        assert(!DEQUEUE(&file,&fh,&out.e));
        assert(out.canary==0x123456789abcdefULL);
        assert(out.e.type==queued.type && out.e.sequence==42);
        if(compat_task) {
            struct daemon_event *c=(void *)out.e.u.data;
            assert(c->timestamp.tv_sec==123 && c->timestamp.tv_usec==456);
            assert(c->mono_timestamp.tv_sec==789 && c->mono_timestamp.tv_usec==987);
            assert(c->frame_id==105 && !memcmp(&c->u,&n->u,sizeof(c->u)));
        } else assert(!memcmp(out.e.u.data,queued.u.data,64));
        error=-EAGAIN;assert(DEQUEUE(&file,&fh,&out.e)==-EAGAIN);error=0;
    }
    puts("Native and compat ISP event timestamps, frame ID and payload PASS");
}
'''
                self.run_host(code)


if __name__ == "__main__":
    unittest.main()
