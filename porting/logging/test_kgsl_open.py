#!/usr/bin/env python3
"""Exercise actual kgsl_open and target PM helpers without a kernel build."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def extract_function(source, name):
    match = re.search(r'^static (?:inline )?int ' + re.escape(name)
                      + r'\([^;]*?\)\s*\{', source, re.M)
    if match is None:
        raise ValueError(f'function definition not found: {name}')
    depth = 1
    tokens = r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]'
    for token in re.finditer(tokens, source[match.end():], re.S):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return source[match.start():match.end() + token.end()]
    raise ValueError(f'unterminated function: {name}')


HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define pr_err(...) ((void)0)
#define dev_err(...) ((void)0)
#define adreno_zap_stage(...) ((void)0)
#define RPM_GET_PUT 1

struct inode { unsigned int minor; };
struct file { void *private_data; };
struct device { int usage; };
struct platform_device { struct device dev; };
struct kgsl_device;
struct kgsl_device_private {
    struct kgsl_device *device;
    void *process_priv;
};
struct functable { struct kgsl_device_private *(*device_private_create)(void); };
struct kgsl_device { struct platform_device *pdev; struct functable *ftbl; };
struct adreno_device { bool zap_loaded; };
static struct adreno_device adreno;
#define ADRENO_DEVICE(d) (&adreno)
static struct kgsl_device device;
static struct kgsl_device_private private;
static int process;
static int resume_result, allocations, opens, frees, puts, noidle_puts;
enum scenario { SUCCESS, NO_DEVICE, RESUME_FAIL, ALLOC_FAIL, OPEN_FAIL, PROCESS_FAIL };
static enum scenario scenario;

static unsigned int iminor(struct inode *inode) { return inode->minor; }
static struct kgsl_device *kgsl_get_minor(unsigned int minor)
{
    assert(minor == 0);
    return scenario == NO_DEVICE ? NULL : &device;
}
static int __pm_runtime_resume(struct device *dev, int flags)
{
    assert(dev == &device.pdev->dev && flags == RPM_GET_PUT);
    dev->usage++;
    return resume_result;
}
static void pm_runtime_put_noidle(struct device *dev)
{
    assert(dev->usage > 0);
    dev->usage--;
    noidle_puts++;
}
static int pm_runtime_put(struct device *dev)
{
    assert(dev->usage > 0);
    dev->usage--;
    puts++;
    return 0;
}
static struct kgsl_device_private *create_private(void)
{
    allocations++;
    return scenario == ALLOC_FAIL ? NULL : &private;
}
static void kfree(void *p)
{
    if (p) {
        assert(p == &private && !frees);
        frees++;
    }
}
static int kgsl_open_device(struct kgsl_device *dev)
{
    assert(dev == &device);
    if (scenario == OPEN_FAIL)
        return -EIO;
    opens++;
    return 0;
}
static void kgsl_close_device(struct kgsl_device *dev)
{
    assert(dev == &device && opens == 1);
    opens--;
}
static void *kgsl_process_private_open(struct kgsl_device *dev)
{
    assert(dev == &device && opens == 1);
    return scenario == PROCESS_FAIL ? ERR_PTR(-ENOMEM) : &process;
}
static bool adreno_is_a5xx(struct adreno_device *dev) { return true; }
'''

CHECK = r'''
int main(void)
{
    static struct platform_device pdev;
    static struct functable ftbl = { .device_private_create = create_private };
    const int expected[] = {0, -ENODEV, -EIO, -ENOMEM, -EIO, -ENOMEM};

    device = (struct kgsl_device){ .pdev = &pdev, .ftbl = &ftbl };
    for (int trace = 0; trace <= 1; trace++)
    for (int baseline = 0; baseline <= 2; baseline += 2)
    for (int resumed = 0; resumed <= 1; resumed++)
    for (scenario = SUCCESS; scenario <= PROCESS_FAIL; scenario++) {
        struct inode inode = {0};
        struct file file = {0};

        pdev.dev.usage = baseline;
        private = (struct kgsl_device_private){0};
        adreno.zap_loaded = trace;
        allocations = opens = frees = puts = noidle_puts = 0;
        resume_result = scenario == RESUME_FAIL ? -EIO : resumed;
        assert(kgsl_open(&inode, &file) == expected[scenario]);
        assert(pdev.dev.usage == baseline + (scenario == SUCCESS));
        assert(noidle_puts == (scenario == RESUME_FAIL));
        if (scenario == NO_DEVICE || scenario == RESUME_FAIL) {
            assert(!allocations && !opens && !frees && !puts);
        } else if (scenario == SUCCESS) {
            assert(file.private_data == &private && private.device == &device);
            assert(private.process_priv == &process && opens == 1);
            assert(!frees && !puts);
            /* Successful open retains its reference for the later release. */
        } else {
            assert(!file.private_data && !opens && puts == 1);
            assert(frees == (scenario != ALLOC_FAIL));
        }
    }
    return 0;
}
'''


def main():
    pm = (ROOT / 'include/linux/pm_runtime.h').read_text()
    source = (ROOT / 'drivers/gpu/msm/kgsl.c').read_text()
    helpers = '\n'.join(extract_function(pm, name) for name in
                        ('pm_runtime_get_sync', 'pm_runtime_resume_and_get'))
    with tempfile.TemporaryDirectory(prefix='kgsl-open-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(HARNESS + helpers + extract_function(source, 'kgsl_open')
                         + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-Wno-unused-function',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(cfile), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL open PM-reference regression: PASS (48 cases)')


if __name__ == '__main__':
    main()
