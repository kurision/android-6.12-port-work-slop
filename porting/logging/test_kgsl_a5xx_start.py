#!/usr/bin/env python3
"""Run actual A5xx startup C: failed ZAP must leave the CP microengine halted."""
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/adreno_a5xx.c'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


def main():
    source = SOURCE.read_text()
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define EPROBE_DEFER 517
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define lower_32_bits(n) ((uint32_t)(n))
#define upper_32_bits(n) ((uint32_t)((uint64_t)(n) >> 32))
#define SCM_ARGS(n) (n)
#define SCM_SIP_FNID(service, command) ((service) * 256 + (command))
#define SCM_SVC_BOOT 1
#define dev_err(...) ((void)0)
enum {
    ADRENO_FW_PM4, ADRENO_FW_PFP, ADRENO_CPZ_RETENTION,
    A5XX_CP_PM4_INSTR_BASE_LO, A5XX_CP_PM4_INSTR_BASE_HI,
    A5XX_CP_PFP_INSTR_BASE_LO, A5XX_CP_PFP_INSTR_BASE_HI,
    ADRENO_REG_CP_RB_RPTR_ADDR_LO, ADRENO_REG_CP_RB_RPTR_ADDR_HI,
    ADRENO_REG_CP_RB_CNTL, ADRENO_REG_CP_RB_BASE,
    ADRENO_REG_CP_RB_BASE_HI, ADRENO_REG_CP_ME_CNTL,
    A5XX_CP_RB_CNTL_DEFAULT, ZAP_STAGE_UNSECURE_DONE,
    ZAP_STAGE_POST_START_ENTER, ZAP_STAGE_POST_START_DONE
};
struct memdesc { uint64_t gpuaddr; };
struct adreno_firmware { struct memdesc memdesc; };
struct device { int unused; };
struct platform_device { struct device dev; };
struct kgsl_device {
    struct { bool secured; } mmu;
    struct platform_device *pdev;
    struct device *dev;
};
struct adreno_ringbuffer { unsigned int id; struct memdesc buffer_desc; };
struct adreno_device {
    struct kgsl_device dev;
    struct adreno_firmware fw[2];
    bool zap_loaded, retention;
    struct adreno_ringbuffer rb;
};
struct adreno_a5xx_core { const char *zap_name; };
struct scm_desc { uint64_t args[2]; unsigned int arginfo; };
static struct adreno_a5xx_core core;
static void *load_result;
static int resume_result;
static unsigned int loads, resumes, engine_starts;
#define KGSL_DEVICE(adreno) (&(adreno)->dev)
#define ADRENO_FW(adreno, id) (&(adreno)->fw[id])
#define ADRENO_FEATURE(adreno, feature) ((void)(feature), (adreno)->retention)
#define ADRENO_CURRENT_RINGBUFFER(adreno) (&(adreno)->rb)
#define SCRATCH_RPTR_GPU_ADDR(device, id) ((void)(device), (uint64_t)(id) * 4096)
#define adreno_zap_stage(...) ((void)0)
static const struct adreno_a5xx_core *to_a5xx_core(struct adreno_device *adreno)
{ (void)adreno; return &core; }
static void *adreno_zap_subsystem_get(struct device *device, const char *name)
{ (void)device; (void)name; loads++; return load_result; }
static int scm_call2(unsigned int command, struct scm_desc *desc)
{
    assert(command == SCM_SIP_FNID(SCM_SVC_BOOT, 0xA));
    assert(desc->args[0] == 0 && desc->args[1] == 13);
    resumes++;
    return resume_result;
}
static void kgsl_regwrite(struct kgsl_device *device, unsigned int reg, uint32_t value)
{ (void)device; (void)reg; (void)value; }
static void adreno_writereg64(struct adreno_device *adreno,
                             unsigned int low, unsigned int high, uint64_t value)
{ (void)adreno; (void)low; (void)high; (void)value; }
static void adreno_writereg(struct adreno_device *adreno, unsigned int reg, uint32_t value)
{
    (void)adreno;
    if (reg == ADRENO_REG_CP_ME_CNTL && value == 0)
        engine_starts++;
}
static void a5xx_dump_bringup(struct adreno_device *adreno, const char *stage)
{ (void)adreno; (void)stage; }
static int a5xx_send_me_init(struct adreno_device *adreno, struct adreno_ringbuffer *rb)
{ (void)adreno; (void)rb; return 0; }
static int adreno_set_unsecured_mode(struct adreno_device *adreno, struct adreno_ringbuffer *rb)
{ (void)adreno; (void)rb; return 0; }
static int a5xx_gpmu_init(struct adreno_device *adreno)
{ (void)adreno; return 0; }
static int a5xx_post_start(struct adreno_device *adreno)
{ (void)adreno; return 0; }
'''
    checks = r'''
static struct platform_device pdev;
static struct adreno_device reset(bool secured)
{
    struct adreno_device adreno = {
        .dev = { .mmu = { .secured = secured }, .pdev = &pdev },
        .retention = true,
    };
    core.zap_name = "a506_zap";
    load_result = &pdev;
    resume_result = 0;
    loads = resumes = engine_starts = 0;
    return adreno;
}
int main(void)
{
    /* Both secure-MMU and Tissot's non-secure-MMU path must stop before
     * starting the CP if firmware lookup, MDT loading or PAS auth fails. */
    const int errors[] = { -ENOENT, -ENOMEM, -EINVAL, -EIO, -EPROBE_DEFER, -ENODEV };
    for (unsigned int secured = 0; secured < 2; secured++) {
        for (unsigned int i = 0; i < sizeof(errors) / sizeof(errors[0]); i++) {
            struct adreno_device adreno = reset(secured);
            load_result = ERR_PTR(errors[i]);
            assert(a5xx_rb_start(&adreno) == errors[i]);
            assert(!adreno.zap_loaded && engine_starts == 0);
        }
        struct adreno_device adreno = reset(secured);
        load_result = NULL;
        assert(a5xx_rb_start(&adreno) == -ENODEV);
        assert(!adreno.zap_loaded && engine_starts == 0);

        /* Successful authentication is cached across A506 restarts;
         * CPZ retention requires neither reloading nor SCM resume. */
        adreno = reset(secured);
        assert(a5xx_rb_start(&adreno) == 0);
        assert(adreno.zap_loaded && engine_starts == 1);
        assert(a5xx_rb_start(&adreno) == 0);
        assert(adreno.zap_loaded && engine_starts == 2);
        assert(loads == 1 && resumes == 0);
    }
    /* Preserve the existing no-firmware and non-retention paths. */
    struct adreno_device adreno = reset(false);
    core.zap_name = NULL;
    assert(a5xx_rb_start(&adreno) == 0);
    assert(!adreno.zap_loaded && engine_starts == 1 && loads == 0);
    adreno = reset(true);
    adreno.zap_loaded = true;
    adreno.retention = false;
    resume_result = -EIO;
    assert(a5xx_rb_start(&adreno) == -EIO);
    assert(engine_starts == 0 && resumes == 1 && loads == 0);
    return 0;
}
'''
    unit_text = (harness + function(source, 'static int a5xx_microcode_load(')
                 + function(source, 'static int a5xx_rb_start(') + checks)
    with tempfile.TemporaryDirectory(prefix='ack-a5xx-start-test-') as tmp:
        root = Path(tmp)
        unit = root / 'a5xx_start.c'
        binary = root / 'a5xx_start'
        unit.write_text(unit_text)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(unit), '-o', str(binary)], check=True, timeout=20)
        subprocess.run([str(binary)], check=True, timeout=10)
    print('A5xx startup: ZAP failures halt CP startup; authentication cache and CPZ retention passed')


if __name__ == '__main__':
    main()
