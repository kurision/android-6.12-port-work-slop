#!/usr/bin/env python3
"""Check actual GPU user-pointer pin flags, unwind and dirty unpin paths."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/kgsl.c'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#define PAGE_SHIFT 12
#define PAGE_SIZE (1UL << PAGE_SHIFT)
#define GFP_KERNEL 0
#define FOLL_WRITE 1
#define FOLL_LONGTERM 2
#define KGSL_MEMFLAGS_GPUREADONLY 1
#define KGSL_MEMDESC_MAPPED 1
#define KGSL_CACHE_OP_FLUSH 1
#define nth_page(p, n) ((p) + (n))
#define sg_page(s) ((s)->page)
#define for_each_sg(first, sg, count, i) \
    for ((i) = 0, (sg) = (first); (i) < (count); (i)++, (sg) = (sg)->next)
struct page { int pins; bool dirty; };
struct scatterlist { struct page *page; unsigned int length; struct scatterlist *next; };
struct sg_table { struct scatterlist *sgl; unsigned int nents; };
struct kgsl_memdesc { uint64_t size, flags; unsigned int priv; struct sg_table *sgt; };
struct task { void *mm; };
static struct task task;
#define current (&task)
enum { NORMAL, PIN_ERROR, PARTIAL, SG_ERROR, CACHE_ERROR, VMA_ERROR,
       ARRAY_ERROR, HEADER_ERROR };
static int scenario, locked, allocations, pin_calls;
static bool readonly, merged;
static struct page backing[2];
static void *kvcalloc(size_t n, size_t size, int flags)
{
    if (scenario == ARRAY_ERROR)
        return NULL;
    void *p = calloc(n, size);
    assert(p);
    allocations++;
    return p;
}
static void *kmalloc(size_t size, int flags)
{
    if (scenario == HEADER_ERROR)
        return NULL;
    void *p = malloc(size);
    assert(p);
    allocations++;
    return p;
}
static void kfree(void *p)
{
    if (p) {
        assert(allocations > 0);
        allocations--;
        free(p);
    }
}
#define kvfree(p) kfree(p)
static void mmap_read_lock(void *mm) { assert(!locked); locked = 1; }
static void mmap_read_unlock(void *mm) { assert(locked); locked = 0; }
static bool check_vma(unsigned long address, uint64_t size)
{
    assert(locked && size == 2 * PAGE_SIZE);
    return scenario != VMA_ERROR;
}
static long pin_user_pages(unsigned long address, unsigned long count,
                           unsigned int flags, struct page **pages)
{
    assert(locked && count == 2);
    assert(flags == (FOLL_LONGTERM | (readonly ? 0 : FOLL_WRITE)));
    pin_calls++;
    if (scenario == PIN_ERROR)
        return -EFAULT;
    int pinned = scenario == PARTIAL ? 1 : 2;
    for (int i = 0; i < pinned; i++) {
        pages[i] = &backing[i];
        backing[i].pins++;
    }
    return pinned;
}
static void unpin_user_page(struct page *p)
{
    assert(p->pins == 1);
    p->pins--;
}
static void unpin_user_pages_dirty_lock(struct page **pages, unsigned long count,
                                        bool dirty)
{
    assert(count == 1 && dirty);
    pages[0]->dirty = true;
    unpin_user_page(pages[0]);
}
static int sg_alloc_table_from_pages(struct sg_table *sgt, struct page **pages,
                                     unsigned int count, unsigned int offset,
                                     unsigned long size, int flags)
{
    assert(!locked && count == 2 && offset == 0 && size == 2 * PAGE_SIZE);
    if (scenario == SG_ERROR)
        return -ENOMEM;
    sgt->nents = merged ? 1 : 2;
    sgt->sgl = calloc(sgt->nents, sizeof(*sgt->sgl));
    assert(sgt->sgl);
    allocations++;
    for (unsigned int i = 0; i < sgt->nents; i++) {
        sgt->sgl[i].page = pages[i];
        sgt->sgl[i].length = merged ? size : PAGE_SIZE;
        sgt->sgl[i].next = i + 1 < sgt->nents ? &sgt->sgl[i + 1] : NULL;
    }
    return 0;
}
static void sg_free_table(struct sg_table *sgt)
{
    kfree(sgt->sgl);
    sgt->sgl = NULL;
}
static int kgsl_cache_range_op(struct kgsl_memdesc *m, uint64_t offset,
                               uint64_t size, unsigned int op)
{
    assert(!locked && offset == 0 && size == m->size && op == KGSL_CACHE_OP_FLUSH);
    return scenario == CACHE_ERROR ? -ERANGE : 0;
}
'''

CHECK = r'''
int main(void)
{
    const int errors[] = {0, -EFAULT, -EINVAL, -ENOMEM, -ERANGE,
                          -EFAULT, -ENOMEM, -ENOMEM};
    for (int ro = 0; ro <= 1; ro++)
    for (int merge = 0; merge <= 1; merge++)
    for (scenario = NORMAL; scenario <= HEADER_ERROR; scenario++) {
        struct kgsl_memdesc m = { .size = 2 * PAGE_SIZE, .flags = ro };

        readonly = ro;
        merged = merge;
        backing[0] = backing[1] = (struct page){0};
        pin_calls = 0;
        assert(!locked && !allocations);
        assert(memdesc_sg_virt(&m, PAGE_SIZE) == errors[scenario]);
        assert(!locked);
        assert(pin_calls == (scenario <= CACHE_ERROR));
        if (scenario == NORMAL) {
            assert(backing[0].pins == 1 && backing[1].pins == 1);
            m.priv = KGSL_MEMDESC_MAPPED;
            kgsl_destroy_anon(&m);
            assert(backing[0].pins == 1 && backing[1].pins == 1);
            m.priv = 0;
            kgsl_destroy_anon(&m);
            assert(backing[0].dirty == !readonly && backing[1].dirty == !readonly);
            sg_free_table(m.sgt);
            kfree(m.sgt);
        } else {
            assert(!m.sgt && !backing[0].dirty && !backing[1].dirty);
        }
        assert(!backing[0].pins && !backing[1].pins && !allocations);
    }
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    functions = []
    for signature in ('static int memdesc_sg_virt(', 'static void kgsl_destroy_anon('):
        start = source.index(signature)
        functions.append(source[start:source.index('\n}', start) + 2])
    with tempfile.TemporaryDirectory(prefix='kgsl-userptr-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(HARNESS + '\n'.join(functions) + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-Wno-sign-compare', '-fsanitize=undefined',
                        '-fno-sanitize-recover=all', str(cfile), '-o', str(binary)],
                       check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL userptr long-term pins, partial unwind and dirty unpin: PASS (32 cases)')


if __name__ == '__main__':
    main()
