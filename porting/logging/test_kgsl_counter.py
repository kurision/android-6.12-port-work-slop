#!/usr/bin/env python3
"""Exercise actual KGSL busy-counter sampling without a kernel build."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/adreno.h'

HARNESS = r'''
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
enum { ADRENO_REG_RBBM_PERFCTR_RBBM_0_LO = 7,
       ADRENO_REG_RBBM_PERFCTR_RBBM_0_HI, OTHER_COUNTER };
struct adreno_device { bool a5xx; };
struct kgsl_device { struct adreno_device adreno; };
#define ADRENO_DEVICE(d) (&(d)->adreno)
#define dev_warn_once(...) ((void)0)
static unsigned int low, high, high_reads;
static bool adreno_is_a5xx(struct adreno_device *d) { return d->a5xx; }
static unsigned int adreno_getreg(struct adreno_device *d, unsigned int reg)
{
    return reg;
}
static void kgsl_regread(struct kgsl_device *d, unsigned int reg,
                         unsigned int *value)
{
    assert(reg == ADRENO_REG_RBBM_PERFCTR_RBBM_0_LO || reg == OTHER_COUNTER);
    *value = low;
}
static void adreno_readreg(struct adreno_device *d, unsigned int reg,
                           unsigned int *value)
{
    assert(reg == ADRENO_REG_RBBM_PERFCTR_RBBM_0_HI);
    high_reads++;
    *value = high;
}
'''

CHECK = r'''
int main(void)
{
    struct kgsl_device device = { .adreno.a5xx = true };
    unsigned int counter = 0;
    unsigned int reg = ADRENO_REG_RBBM_PERFCTR_RBBM_0_LO;

    low = 100;
    assert(counter_delta(&device, reg, &counter) == 0 && counter == 100);
    low = 110;
    assert(counter_delta(&device, reg, &counter) == 10 && counter == 110);
    /* A backward sample without rollover loses only the current interval. */
    low = 90;
    assert(counter_delta(&device, reg, &counter) == 0 && counter == 90);
    low = 95;
    assert(counter_delta(&device, reg, &counter) == 5 && counter == 95);
    low = 20;
    assert(counter_delta(&device, reg, &counter) == 0 && counter == 20);
    low = 25;
    assert(counter_delta(&device, reg, &counter) == 5 && counter == 25);
    assert(counter_delta(&device, reg, &counter) == 0 && counter == 25);

    /* Preserve existing rollover arithmetic; it is not part of this fix. */
    counter = 0;
    low = UINT_MAX - 3;
    high = 0;
    assert(counter_delta(&device, reg, &counter) == 0);
    low = 4;
    high = 1;
    assert(counter_delta(&device, reg, &counter) == 7 && counter == 4);
    low = 6;
    assert(counter_delta(&device, reg, &counter) == 2 && counter == 6);

    /* Resetting the software baseline still suppresses the first interval. */
    counter = 0;
    high = 0;
    low = 50;
    assert(counter_delta(&device, reg, &counter) == 0 && counter == 50);
    low = 55;
    assert(counter_delta(&device, reg, &counter) == 5 && counter == 55);

    /* The change must not affect other counters or non-A5xx devices. */
    unsigned int previous_reads = high_reads;
    counter = UINT_MAX - 3;
    low = 4;
    assert(counter_delta(&device, OTHER_COUNTER, &counter) == 7 && counter == 4);
    device.adreno.a5xx = false;
    counter = UINT_MAX - 3;
    assert(counter_delta(&device, reg, &counter) == 7 && counter == 4);
    assert(high_reads == previous_reads);
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    functions = []
    for signature in ('static inline bool is_power_counter_overflow(',
                      'static inline unsigned int counter_delta('):
        start = source.index(signature)
        functions.append(source[start:source.index('\n}', start) + 2])
    with tempfile.TemporaryDirectory(prefix='kgsl-counter-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(HARNESS + '\n'.join(functions) + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(cfile), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL busy-counter baseline and rollover regression: PASS')


if __name__ == '__main__':
    main()
