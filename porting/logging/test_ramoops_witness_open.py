#!/usr/bin/env python3
"""Exercise the real witness-open function with allocation failure; no hardware."""
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'fs/pstore/ram.c'


def main():
    source = SOURCE.read_text()
    start = source.index('static int ramoops_witness_open(void)')
    end = source.index('\n}\n', start) + 3
    function = source[start:end]
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
struct file { int unused; };
struct block_device { int unused; };
#define BLK_OPEN_READ 1
#define BLK_OPEN_WRITE 2
#define RAMOOPS_WITNESS_LEN 512
#define IS_ERR(p) false
#define PTR_ERR(p) (-EIO)
static int block_class, ramoops_snapper;
static struct file backing_file, *ramoops_witness_file;
static struct block_device backing_device, *ramoops_witness_bdev;
static void *ramoops_witness_buf;
static bool fail_alloc = true;
static bool class_ready;
static int opens, closes, allocations;
static int ramoops_snap_find_logdump(void) { return 0; }
static bool class_is_registered(void *c)
{ (void)c; return class_ready; }
static void class_for_each_device(void *c, void *s, dev_t *found, void *fn)
{ (void)c; (void)s; (void)fn; *found = 1; }
static struct file *bdev_file_open_by_dev(dev_t d, int flags, void *h, void *o)
{ (void)d; (void)flags; (void)h; (void)o; ++opens; return &backing_file; }
static struct block_device *file_bdev(struct file *f)
{ (void)f; return &backing_device; }
static void *vmalloc(size_t size)
{ ++allocations; return fail_alloc ? NULL : malloc(size); }
static void filp_close(struct file *f, void *owner)
{ (void)f; (void)owner; ++closes; }
'''
    check = r'''
int main(void)
{
    assert(ramoops_witness_open() == -ENODEV);
    assert(opens == 0 && allocations == 0);
    class_ready = true;
    assert(ramoops_witness_open() == -ENOMEM);
    assert(ramoops_witness_open() == -ENOMEM);
    assert(!ramoops_witness_file && !ramoops_witness_bdev && !ramoops_witness_buf);
    assert(opens == 2 && closes == 2);
    fail_alloc = false;
    assert(ramoops_witness_open() == 0);
    assert(ramoops_witness_file && ramoops_witness_bdev && ramoops_witness_buf);
    assert(opens == 3 && allocations == 3);
    assert(ramoops_witness_open() == 0);
    assert(opens == 3 && allocations == 3);
    free(ramoops_witness_buf);
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='ack-witness-test-') as tmp:
        root = Path(tmp)
        unit = root / 'witness.c'
        unit.write_text(harness + function + check)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', str(unit),
                        '-o', str(root / 'witness')], check=True)
        subprocess.run([str(root / 'witness')], check=True)
    print('witness allocation failure, retry cleanup, and successful caching passed')


if __name__ == '__main__':
    main()
