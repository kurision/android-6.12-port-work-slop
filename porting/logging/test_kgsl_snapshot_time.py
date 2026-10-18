#!/usr/bin/env python3
"""Check the actual snapshot timestamp calculation without a kernel build."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/kgsl_snapshot.c'


def main():
    source = SOURCE.read_text()
    start = source.index('/*\n\t * The timestamp is the seconds since boot')
    end = source.index('/* Store the instance', start)
    calculation = source[start:end]
    harness = r'''
#include <assert.h>
#include <stdint.h>
struct timespec64 { int64_t tv_sec; };
struct kgsl_snapshot { unsigned long timestamp; };
static int64_t elapsed, wall;
static int64_t ktime_get_real_seconds(void) { return wall; }
static int64_t ktime_get_boottime_seconds(void) { return elapsed; }
static void ktime_get_boottime_ts64(struct timespec64 *ts) { ts->tv_sec = elapsed; }
static void capture(struct kgsl_snapshot *snapshot)
{
'''
    check = r'''
}
int main(void)
{
    const int64_t clocks[] = {0, 1700000000, 1800000000};
    const int64_t uptimes[] = {0, 1, 42, 3600, 86400};
    struct kgsl_snapshot snapshot;

    for (unsigned int i = 0; i < sizeof(clocks) / sizeof(clocks[0]); i++)
    for (unsigned int j = 0; j < sizeof(uptimes) / sizeof(uptimes[0]); j++) {
        wall = clocks[i];
        elapsed = uptimes[j];
        capture(&snapshot);
        assert(snapshot.timestamp == (unsigned long)elapsed);
    }
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='kgsl-time-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(harness + calculation + check)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-function',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(cfile), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL snapshot boot-time timestamp: PASS (15 cases)')


if __name__ == '__main__':
    main()
