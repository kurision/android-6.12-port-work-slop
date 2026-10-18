#!/usr/bin/env python3
"""Check actual KGSL page allocation/free does not charge slab statistics."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/kgsl_pool.c'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#define PAGE_SHIFT 12
#define PAGE_SIZE (1 << PAGE_SHIFT)
#define NR_SLAB_UNRECLAIMABLE_B 1
#define nth_page(p, n) ((p) + (n))
#define page_pgdat(p) (p)
#define compound_order(p) ((p)->order)
typedef unsigned int gfp_t;
struct page { unsigned int order; };
struct kgsl_memdesc { int unused; };
struct kgsl_page_pool {
    unsigned int pool_order;
    int page_count;
    bool allocation_allowed;
    unsigned int max_pages;
};
static struct page backing[16];
static struct kgsl_page_pool kgsl_pools[1];
static int kgsl_num_pools, kgsl_pool_max_pages;
static int frees, pooled, slab_updates;
static bool allocation_failure;
static int ilog2(unsigned int n) { return 31 - __builtin_clz(n); }
static int get_order(unsigned int n) { return ilog2(n >> PAGE_SHIFT); }
static gfp_t kgsl_gfp_mask(int order) { return 0; }
static struct page *alloc_pages(gfp_t mask, int order)
{
    if (allocation_failure)
        return NULL;
    for (unsigned int i = 0; i < 16; i++)
        backing[i].order = order;
    return backing;
}
static void kgsl_zero_page(struct page *p, int order) { assert(p == backing); }
static struct kgsl_page_pool *_kgsl_get_pool_from_order(unsigned int order)
{
    return kgsl_num_pools ? &kgsl_pools[0] : NULL;
}
static int kgsl_pool_idx_lookup(unsigned int order) { return 0; }
static int kgsl_pool_get_retry_order(unsigned int order) { return 0; }
static struct page *_kgsl_pool_get_page(struct kgsl_page_pool *pool) { return NULL; }
static int kgsl_get_page_size(size_t size, int align, struct kgsl_memdesc *m)
{
    return size;
}
static int kgsl_pool_size_total(void) { return 0; }
static void _kgsl_pool_add_page(struct kgsl_page_pool *pool, struct page *p)
{
    assert(p == backing && !frees);
    pooled++;
}
static void __free_pages(struct page *p, int order)
{
    assert(p == backing && order == (int)p->order && !pooled);
    frees++;
}
static void mod_node_page_state(struct page *p, int stat, long delta)
{
    assert(stat == NR_SLAB_UNRECLAIMABLE_B);
    slab_updates++;
}
'''

CHECK = r'''
int main(void)
{
    for (kgsl_num_pools = 0; kgsl_num_pools <= 1; kgsl_num_pools++)
    for (int order = 0; order <= 4; order++) {
        struct page *pages[16];
        struct kgsl_memdesc memdesc = {0};
        int size = PAGE_SIZE << order;
        unsigned int align = ilog2(size);

        frees = pooled = slab_updates = 0;
        kgsl_pools[0] = (struct kgsl_page_pool){
            .pool_order = order, .allocation_allowed = true, .max_pages = 10,
        };
        assert(kgsl_pool_alloc_page(&size, pages, 16, &align, &memdesc) == 1 << order);
        /* Check while active: balanced-but-wrong slab charges are still wrong. */
        assert(!slab_updates);
        for (int i = 0; i < 1 << order; i++)
            assert(pages[i] == &backing[i]);
        kgsl_pool_free_page(pages[0]);
        assert(!slab_updates && frees == !kgsl_num_pools && pooled == kgsl_num_pools);
    }
    kgsl_num_pools = 0;
    allocation_failure = true;
    int size = PAGE_SIZE;
    unsigned int align = PAGE_SHIFT;
    struct page *pages[1];
    struct kgsl_memdesc memdesc = {0};
    assert(kgsl_pool_alloc_page(&size, pages, 1, &align, &memdesc) == -ENOMEM);
    kgsl_pool_free_page(NULL);
    assert(!slab_updates);
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    functions = []
    for signature in ('int kgsl_pool_alloc_page(', 'void kgsl_pool_free_page('):
        start = source.index(signature)
        functions.append(source[start:source.index('\n}', start) + 2])
    with tempfile.TemporaryDirectory(prefix='kgsl-pool-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(HARNESS + '\n'.join(functions) + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-Wno-unused-function', '-Wno-sign-compare',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(cfile), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL pool non-slab accounting regression: PASS')


if __name__ == '__main__':
    main()
