#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host fault-injection checks for the production VIDC debugfs lifecycle."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "drivers/media/platform/msm/vidc_3x/msm_vidc_debug.c"


class VidcDebugfs(unittest.TestCase):
    def test_names_and_failure_cleanup(self):
        source = SOURCE.read_text()
        functions = []
        for name in ("msm_vidc_debugfs_init_core", "msm_vidc_debugfs_init_inst",
                     "msm_vidc_debugfs_deinit_inst"):
            functions.append(re.search(
                rf"^(?:struct dentry \*|void ){name}\(.*?^\}}",
                source, re.M | re.S)[0])
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#define MAX_DEBUGFS_NAME 50
#define GFP_KERNEL 0
#define FRAME_PROCESSING 0
#define dprintk(...) ((void)0)
#define ERR_PTR(n) ((struct dentry *)(intptr_t)(n))
static bool IS_ERR_OR_NULL(const void *p)
{
    return !p || (uintptr_t)p >= (uintptr_t)-4095;
}
typedef struct { unsigned int value; } atomic_t;
#define ATOMIC_INIT(n) { n }
#define atomic_inc_return(a) (++(a)->value)
struct inode { void *i_private; };
struct dentry {
    struct inode *d_inode;
    struct dentry *parent;
    char name[MAX_DEBUGFS_NAME];
    bool live;
};
struct msm_vidc_core { int id; };
struct msm_vidc_inst {
    struct msm_vidc_core *core;
    struct dentry *debugfs_root;
    struct { struct { bool sampling; } pdata[1]; } debug;
};
struct core_inst_pair { struct msm_vidc_core *core; struct msm_vidc_inst *inst; };
static int core_info_fops, ssr_fops, inst_info_fops;
static struct dentry nodes[128], root;
static struct inode inodes[128];
static unsigned int used, allocations, creates, removes, file_calls;
static bool allocation_fail, directory_fail;
static unsigned int file_fail_at;
static struct dentry *failure;

static void *kzalloc(size_t size, int flags)
{
    (void)flags;
    if (allocation_fail) return NULL;
    void *p = calloc(1, size);
    assert(p);
    allocations++;
    return p;
}
static void kfree(void *p)
{
    if (p) { assert(allocations); allocations--; free(p); }
}
/* Reproduce kernel %pK hiding pointer values from the media service. */
static int kernel_snprintf(char *dst, size_t size, const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    int ret = strcmp(fmt, "inst_%pK") ? vsnprintf(dst, size, fmt, args) :
              snprintf(dst, size, "inst_0000000000000000");
    va_end(args);
    return ret;
}
#define snprintf kernel_snprintf

static struct dentry *create(const char *name, struct dentry *parent, void *data)
{
    assert(!IS_ERR_OR_NULL(parent));
    for (unsigned int i = 0; i < used; i++)
        if (nodes[i].live && nodes[i].parent == parent &&
            !strcmp(nodes[i].name, name)) return ERR_PTR(-EEXIST);
    assert(used < 128);
    struct dentry *d = &nodes[used];
    d->d_inode = &inodes[used++];
    d->d_inode->i_private = data;
    d->parent = parent; d->live = true;
    snprintf(d->name, sizeof(d->name), "%s", name);
    return d;
}
static struct dentry *debugfs_create_dir(const char *name, struct dentry *parent)
{
    creates++;
    return directory_fail ? failure : create(name, parent, NULL);
}
static struct dentry *debugfs_create_file(const char *name, unsigned int mode,
                                         struct dentry *parent, void *data,
                                         const void *fops)
{
    (void)mode; (void)fops;
    if (IS_ERR_OR_NULL(parent)) return ERR_PTR(-EINVAL);
    return ++file_calls == file_fail_at ? failure : create(name, parent, data);
}
static void debugfs_remove_recursive(struct dentry *d)
{
    assert(!IS_ERR_OR_NULL(d) && d->live);
    removes++;
    d->live = false;
    for (unsigned int i = 0; i < used; i++)
        if (nodes[i].parent == d) nodes[i].live = false;
}
'''
        cases = r'''
int main(void)
{
    struct msm_vidc_core core = { .id = 0 };
    struct msm_vidc_inst a = { .core = &core }, b = { .core = &core };
    struct dentry *parent = msm_vidc_debugfs_init_core(&core, &root);
    assert(!IS_ERR_OR_NULL(parent));
    a.debugfs_root = msm_vidc_debugfs_init_inst(&a, parent);
    b.debugfs_root = msm_vidc_debugfs_init_inst(&b, parent);
    assert(!IS_ERR_OR_NULL(a.debugfs_root) && !IS_ERR_OR_NULL(b.debugfs_root));
    assert(strcmp(a.debugfs_root->name, b.debugfs_root->name));
    assert(a.debug.pdata[0].sampling && b.debug.pdata[0].sampling);
    assert(allocations == 2);
    msm_vidc_debugfs_deinit_inst(&a); msm_vidc_debugfs_deinit_inst(&b);
    assert(!a.debugfs_root && !b.debugfs_root && !allocations);
    msm_vidc_debugfs_deinit_inst(&a);
    debugfs_remove_recursive(parent);

    for (unsigned int error = 0; error < 3; error++) {
        failure = error == 0 ? NULL : ERR_PTR(error == 1 ? -EEXIST : -ENODEV);
        directory_fail = true;
        unsigned int before = file_calls;
        assert(!msm_vidc_debugfs_init_core(&core, &root));
        assert(!msm_vidc_debugfs_init_inst(&a, &root));
        assert(!allocations && file_calls == before);
        directory_fail = false;
        for (unsigned int nth = 1; nth <= 2; nth++) {
            file_calls = 0; file_fail_at = nth; before = removes;
            assert(!msm_vidc_debugfs_init_core(&core, &root));
            assert(removes == before + 1);
        }
        file_calls = 0; file_fail_at = 1; before = removes;
        assert(!msm_vidc_debugfs_init_inst(&a, &root));
        assert(!allocations && removes == before + 1);
        file_fail_at = 0;
    }

    unsigned int before = creates;
    assert(!msm_vidc_debugfs_init_core(&core, NULL));
    assert(!msm_vidc_debugfs_init_inst(&a, NULL));
    assert(!msm_vidc_debugfs_init_core(&core, ERR_PTR(-ENODEV)));
    assert(!msm_vidc_debugfs_init_inst(&a, ERR_PTR(-ENODEV)));
    assert(!msm_vidc_debugfs_init_core(NULL, &root));
    assert(!msm_vidc_debugfs_init_inst(NULL, &root));
    allocation_fail = true;
    assert(!msm_vidc_debugfs_init_inst(&a, &root));
    assert(!allocations && creates == before);
    for (unsigned int i = 0; i < used; i++) assert(!nodes[i].live);
    return 0;
}
'''
        compilers = [name for name in ("gcc", "clang") if shutil.which(name)]
        self.assertTrue(compilers, "A host C compiler is required")
        with tempfile.TemporaryDirectory(prefix="vidc-debugfs-test-") as tmp:
            src, exe = Path(tmp) / "debugfs.c", Path(tmp) / "debugfs"
            src.write_text("\n".join((harness, *functions, cases)))
            for compiler in compilers:
                with self.subTest(compiler=compiler):
                    result = subprocess.run([
                        compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-g", str(src),
                        "-o", str(exe),
                    ], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    # LeakSanitizer cannot run under a ptraced sandbox.
                    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                               UBSAN_OPTIONS="halt_on_error=1")
                    result = subprocess.run([str(exe)], env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
