#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise real JPEG dispatchers with usercopy restricted to a user buffer."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_camera_power_domains import CAM, ROOT


SOURCE = CAM / "jpeg_10/msm_jpeg_sync.c"


def function(source, name):
    return re.search(r"^(?:static )?(?:inline )?(?:int|long) " + name
                     + r"\([^;{]*\)\n\{.*?^}", source, re.M | re.S)[0]


STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __user
#define CONFIG_COMPAT 1
#include "include/uapi/media/msm_jpeg-legacy.h"
typedef uint32_t compat_uptr_t, compat_ulong_t;
#define JPEG_DBG(...) ((void)0)
#define JPEG_DBG_HIGH(...) ((void)0)
#define JPEG_PR_ERR(...) ((void)0)
#define pr_err_ratelimited(...) ((void)0)
#define KERN_INFO ""
#define GFP_ATOMIC 0
#define JPEG_BUS_UNVOTED(d) ((d)->jpeg_bus_vote = 0)
enum msm_jpeg_state { MSM_JPEG_INIT, MSM_JPEG_RESET, MSM_JPEG_STOPPED };
struct msm_jpeg_core_buf {
    struct msm_jpeg_buf vbuf;
    int ion_fd;
    uint32_t y_buffer_addr, cbcr_buffer_addr, pln2_addr;
    uint32_t y_len, cbcr_len, pln2_len, num_of_mcu_rows;
};
struct msm_jpeg_q { struct msm_jpeg_core_buf *buf; };
struct msm_jpeg_device {
    enum msm_jpeg_state state;
    uint8_t op_mode;
    void *base;
    unsigned res_size;
    int iommu_hdl, bus_client, jpeg_bus_vote;
    struct msm_jpeg_q input_buf_q, input_rtn_q;
    struct msm_jpeg_q output_buf_q, output_rtn_q, evt_q;
};
static unsigned char user_buffer[256];
static size_t user_size;
static bool read_fault, write_fault, alloc_fault, map_fault;
static int allocations, mappings, resets, reset_error, bus_updates, last_vote;
static unsigned reads, writes;
static bool user_range(const void *p, size_t n) {
    uintptr_t a = (uintptr_t)p, first = (uintptr_t)user_buffer;
    return a >= first && n <= user_size && a - first <= user_size - n;
}
static size_t copy_from_user(void *to, const void *from, size_t n) {
    ++reads;
    if (read_fault || !user_range(from, n)) return n;
    memcpy(to, from, n);
    return 0;
}
static size_t copy_to_user(void *to, const void *from, size_t n) {
    ++writes;
    if (write_fault || !user_range(to, n)) return n;
    memcpy(to, from, n);
    return 0;
}
static void *kmalloc(size_t n, int flags) {
    (void)flags;
    if (alloc_fault) return NULL;
    void *p = malloc(n);
    assert(p);
    ++allocations;
    return p;
}
static void kfree(void *p) {
    if (p) --allocations;
    free(p);
}
static void legacy_msm_jpeg_q_wait(struct msm_jpeg_q *q) { (void)q; }
static void *legacy_msm_jpeg_q_out(struct msm_jpeg_q *q) {
    void *p = q->buf;
    q->buf = NULL;
    return p;
}
static void legacy_msm_jpeg_q_in(struct msm_jpeg_q *q, void *p) {
    assert(!q->buf);
    q->buf = p;
}
static uint32_t legacy_msm_jpeg_platform_v2p(struct msm_jpeg_device *d,
                                          int fd, uint32_t len, int hdl) {
    (void)d; (void)hdl;
    assert(fd == 17 && len > 0);
    if (map_fault) return 0;
    ++mappings;
    return 0x10000;
}
static void legacy_msm_jpeg_platform_p2v(int hdl, int fd) {
    (void)hdl;
    assert(fd == 17 && mappings > 0);
    --mappings;
}
static int legacy_msm_camera_update_bus_vector(int client, int vote) {
    (void)client;
    ++bus_updates;
    last_vote = vote;
    return 0;
}
static int legacy_msm_jpeg_core_reset(struct msm_jpeg_device *d,
                                    uint8_t mode, void *base, int size) {
    (void)base; (void)size;
    assert(mode == MSM_JPEG_MODE_OFFLINE_ENCODE);
    ++resets;
    if (!reset_error) d->state = MSM_JPEG_RESET;
    return reset_error;
}
/* Unrelated hardware command ioctls are outside this usercopy regression. */
#define legacy_msm_jpeg_ioctl_hw_cmd(...) (-ENOTTY)
#define legacy_msm_jpeg_ioctl_hw_cmd32(...) (-ENOTTY)
#define legacy_msm_jpeg_ioctl_hw_cmds(...) (-ENOTTY)
#define legacy_msm_jpeg_ioctl_hw_cmds32(...) (-ENOTTY)
#define legacy_msm_jpeg_start(...) (-ENOTTY)
#define legacy_msm_jpeg_input_get_unblock(...) 0
#define legacy_msm_jpeg_output_get_unblock(...) 0
#define legacy_msm_jpeg_evt_get_unblock(...) 0
#define legacy_msm_jpeg_ioctl_test_dump_region(...) (-ENOTTY)
#define legacy_msm_jpeg_ioctl_set_clk_rate(...) (-ENOTTY)
long legacy___msm_jpeg_ioctl(struct msm_jpeg_device *, unsigned, unsigned long);
'''


CHECKS = r'''
_Static_assert(sizeof(struct msm_jpeg_ctrl_cmd32) == 12, "control32 ABI");
_Static_assert(sizeof(struct msm_jpeg_buf32) == 48, "buffer32 ABI");
_Static_assert(MSM_JPEG_IOCTL_RESET32 == 0x400c6702U, "reset32 ABI");
_Static_assert(MSM_JPEG_IOCTL_INPUT_BUF_ENQUEUE32 == 0x40306705U, "input32 ABI");
static struct msm_jpeg_buf sample = {
    .type = 9, .fd = 17, .vaddr = (void *)(uintptr_t)0xf1234567,
    .y_off = 3, .y_len = 1024, .framedone_len = 7,
    .cbcr_off = 11, .cbcr_len = 256, .num_of_mcu_rows = 13,
    .offset = 19, .pln2_off = 23, .pln2_len = 128,
};
static struct msm_jpeg_buf32 sample32 = {
    .type = 9, .fd = 17, .vaddr = 0xf1234567,
    .y_off = 3, .y_len = 1024, .framedone_len = 7,
    .cbcr_off = 11, .cbcr_len = 256, .num_of_mcu_rows = 13,
    .offset = 19, .pln2_off = 23, .pln2_len = 128,
};
static long dispatch(struct msm_jpeg_device *d, int mode, unsigned cmd) {
    return mode ? legacy___msm_jpeg_compat_ioctl(d, cmd,
                        (unsigned long)user_buffer)
                : legacy___msm_jpeg_ioctl(d, cmd, (unsigned long)user_buffer);
}
static void user_data(const void *p, size_t n) {
    assert(n <= sizeof(user_buffer));
    memcpy(user_buffer, p, n);
    user_size = n;
    reads = writes = 0;
}
static void check_buffer(const struct msm_jpeg_buf *b) {
    assert(b->type == sample.type && b->fd == sample.fd);
    assert(b->vaddr == sample.vaddr && b->y_off == sample.y_off);
    assert(b->y_len == sample.y_len && b->framedone_len == sample.framedone_len);
    assert(b->cbcr_off == sample.cbcr_off && b->cbcr_len == sample.cbcr_len);
    assert(b->num_of_mcu_rows == sample.num_of_mcu_rows);
    assert(b->offset == sample.offset && b->pln2_off == sample.pln2_off);
    assert(b->pln2_len == sample.pln2_len);
}
int main(void) {
    for (int mode = 0; mode < 3; ++mode) {
        /* Native, compat32 and native-size requests via the compat entry. */
        bool c32 = mode == 1;
        struct msm_jpeg_device d = { .state = MSM_JPEG_INIT };
        struct msm_jpeg_ctrl_cmd ctl = { .type = MSM_JPEG_MODE_OFFLINE_ENCODE };
        struct msm_jpeg_ctrl_cmd32 ctl32 = { .type = MSM_JPEG_MODE_OFFLINE_ENCODE };
        unsigned reset = c32 ? MSM_JPEG_IOCTL_RESET32 : MSM_JPEG_IOCTL_RESET;
        user_data(c32 ? (void *)&ctl32 : (void *)&ctl,
                  c32 ? sizeof(ctl32) : sizeof(ctl));
        int before = resets;
        --user_size;
        assert(dispatch(&d, mode, reset) == -EFAULT && resets == before);
        ++user_size;
        read_fault = true;
        assert(dispatch(&d, mode, reset) == -EFAULT && resets == before);
        read_fault = false;
        assert(dispatch(&d, mode, reset) == 0 && resets == before + 1);
        assert(reads == 3 && d.state == MSM_JPEG_RESET);
        assert(dispatch(&d, mode, reset) == -1 && resets == before + 1);
        d.state = MSM_JPEG_INIT;
        reset_error = -EBUSY;
        assert(dispatch(&d, mode, reset) == -EBUSY);
        reset_error = 0;

        for (int output = 0; output < 2; ++output) {
            unsigned enqueue = output ? MSM_JPEG_IOCTL_OUTPUT_BUF_ENQUEUE
                                      : MSM_JPEG_IOCTL_INPUT_BUF_ENQUEUE;
            unsigned get = output ? MSM_JPEG_IOCTL_OUTPUT_GET : MSM_JPEG_IOCTL_INPUT_GET;
            if (c32) {
                enqueue = output ? MSM_JPEG_IOCTL_OUTPUT_BUF_ENQUEUE32
                                 : MSM_JPEG_IOCTL_INPUT_BUF_ENQUEUE32;
                get = output ? MSM_JPEG_IOCTL_OUTPUT_GET32 : MSM_JPEG_IOCTL_INPUT_GET32;
            }
            struct msm_jpeg_q *queued = output ? &d.output_buf_q : &d.input_buf_q;
            struct msm_jpeg_q *returned = output ? &d.output_rtn_q : &d.input_rtn_q;
            for (int fault = 0; fault < 7; ++fault) {
                struct msm_jpeg_buf b = sample;
                struct msm_jpeg_buf32 b32 = sample32;
                if (fault == 3) b.y_len = b32.y_len = UINT32_MAX;
                user_data(c32 ? (void *)&b32 : (void *)&b,
                          c32 ? sizeof(b32) : sizeof(b));
                read_fault = fault == 1;
                if (fault == 2) --user_size;
                alloc_fault = fault == 4;
                map_fault = fault == 5;
                long rc = dispatch(&d, mode, enqueue);
                read_fault = alloc_fault = map_fault = false;
                if (fault >= 1 && fault <= 5) {
                    assert(rc == -EFAULT && !queued->buf);
                    assert(!allocations && !mappings);
                    continue;
                }
                assert(!rc && reads == 1 && allocations == 1 && mappings == 1);
                struct msm_jpeg_core_buf *core = queued->buf;
                check_buffer(&core->vbuf);
                assert(core->y_buffer_addr == 0x10000 + sample.offset + sample.y_off);
                assert(core->y_len == sample.y_len && core->pln2_len == sample.pln2_len);
                assert(core->cbcr_buffer_addr == core->y_buffer_addr + sample.y_len
                       + (output ? 0 : sample.cbcr_off));
                assert(core->pln2_addr == core->cbcr_buffer_addr + sample.cbcr_len
                       + (output ? 0 : sample.pln2_off));
                returned->buf = legacy_msm_jpeg_q_out(queued);
                reads = writes = 0;
                write_fault = fault == 6;
                assert(dispatch(&d, mode, get) == (write_fault ? -EFAULT : 0));
                assert(reads == 0 && writes == 1 && !allocations && !mappings);
                if (!write_fault) {
                    if (c32) {
                        memcpy(&b32, user_buffer, sizeof(b32));
                        assert(!memcmp(&b32, &sample32, sizeof(b32)));
                    } else {
                        memcpy(&b, user_buffer, sizeof(b));
                        check_buffer(&b);
                    }
                }
                write_fault = false;
                writes = 0;
                assert(dispatch(&d, mode, get) == -EAGAIN && writes == 0);
            }
        }
        unsigned event = c32 ? MSM_JPEG_IOCTL_EVT_GET32 : MSM_JPEG_IOCTL_EVT_GET;
        for (int fault = 0; fault < 2; ++fault) {
            struct msm_jpeg_core_buf *core = kmalloc(sizeof(*core), 0);
            core->vbuf.type = MSM_JPEG_EVT_SESSION_DONE;
            d.evt_q.buf = core;
            d.jpeg_bus_vote = 1;
            user_data(&ctl, c32 ? sizeof(ctl32) : sizeof(ctl));
            write_fault = fault;
            int updates = bus_updates;
            assert(dispatch(&d, mode, event) == (fault ? -EFAULT : 0));
            assert(!allocations && !d.jpeg_bus_vote && last_vote == 0);
            assert(bus_updates == updates + 1 && reads == 0 && writes == 1);
            if (!fault) {
                if (c32) {
                    memcpy(&ctl32, user_buffer, sizeof(ctl32));
                    assert(ctl32.type == MSM_JPEG_EVT_SESSION_DONE);
                    assert(ctl32.len == 0 && ctl32.value == 0);
                } else {
                    memcpy(&ctl, user_buffer, sizeof(ctl));
                    assert(ctl.type == MSM_JPEG_EVT_SESSION_DONE);
                    assert(ctl.len == 0 && ctl.value == NULL);
                }
            }
            write_fault = false;
            writes = 0;
            assert(dispatch(&d, mode, event) == -EAGAIN && writes == 0);
        }
        assert(!allocations && !mappings);
    }
    puts("JPEG native/compat reset, buffers, events and usercopy faults PASS");
}
'''


class CameraJpegCompat(unittest.TestCase):
    def run_harness(self, source):
        compat = source[source.index("#ifdef CONFIG_COMPAT"):
                        source.index("#endif", source.index("#ifdef CONFIG_COMPAT"))]
        compat += "\n#endif\n"
        names = ["msm_jpeg_add_u32_check", "legacy_msm_jpeg_ioctl_reset",
                 "legacy_msm_jpeg_input_buf_enqueue", "legacy_msm_jpeg_input_get",
                 "legacy_msm_jpeg_output_buf_enqueue", "legacy_msm_jpeg_output_get",
                 "legacy_msm_jpeg_evt_get", "legacy_msm_jpeg_get_ctrl_cmd32",
                 "legacy_msm_jpeg_put_ctrl_cmd32", "legacy_msm_jpeg_get_jpeg_buf32",
                 "legacy_msm_jpeg_put_jpeg_buf32", "legacy___msm_jpeg_ioctl",
                 "legacy___msm_jpeg_compat_ioctl"]
        code = STUBS + compat + "\n".join(function(source, name) for name in names)
        with tempfile.TemporaryDirectory(prefix="camera-jpeg-compat-") as folder:
            cfile, exe = Path(folder) / "jpeg.c", Path(folder) / "jpeg"
            cfile.write_text(code + CHECKS)
            flags = ["-Wall", "-Wextra", "-Werror"]
            if os.environ.get("CAMERA_TEST_SANITIZERS"):
                flags += ["-fsanitize=" + os.environ["CAMERA_TEST_SANITIZERS"],
                          "-fno-omit-frame-pointer"]
            subprocess.run([os.environ.get("CC", "cc"), *flags, "-I" + str(ROOT),
                            str(cfile), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=10)

    def test_native_and_compat_usercopy(self):
        self.run_harness(SOURCE.read_text())


if __name__ == "__main__":
    unittest.main()
