#!/usr/bin/env python3
"""Exercise actual KGSL DMA-BUF import/release functions without a kernel build."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/kgsl.c'


def extract_function(source, name):
    match = re.search(r'^static (?:int|void) ' + re.escape(name)
                      + r'\([^;]*?\)\s*\{', source, re.M)
    if match is None:
        raise ValueError(f'function definition not found: {name}')
    depth = 1
    # Skip braces inside comments and string/character literals.
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
#include <stdlib.h>
#include <string.h>

#define GFP_KERNEL 0
#define DMA_BIDIRECTIONAL 3
#define DMA_ATTR_SKIP_CPU_SYNC 1
#define KGSL_MEMDESC_MAPPED 1
#define KGSL_MEMDESC_SECURE 2
#define KGSL_MEMFLAGS_IOCOHERENT 1
#define KGSL_MEMFLAGS_USE_CPU_MAP 2
#define KGSL_MEMFLAGS_USERMEM_ION 4
#define PAGE_ALIGN(n) (((n) + 4095ULL) & ~4095ULL)
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define container_of(p, t, member) ((t *)((char *)(p) - offsetof(t, member)))

struct page { int private; };
struct scatterlist { struct page *page; unsigned int length; struct scatterlist *next; };
struct sg_table { struct scatterlist *sgl; };
#define sg_page(s) ((s)->page)
#define sg_next(s) ((s)->next)
#define PagePrivate(p) ((p)->private)
struct kgsl_pagetable { int unused; };
struct kgsl_memdesc;
struct kgsl_memdesc_ops { void (*free)(struct kgsl_memdesc *); };
struct kgsl_memdesc {
    uint64_t size, flags;
    unsigned int priv;
    struct sg_table *sgt;
    struct kgsl_pagetable *pagetable;
    const struct kgsl_memdesc_ops *ops;
};
struct kgsl_mem_entry { struct kgsl_memdesc memdesc; void *priv_data; };
struct kgsl_device { void *dev; };
struct dma_buf { unsigned int refs; bool locked, attached, pinned; };
struct dma_buf_attachment { struct dma_buf *dmabuf; unsigned long dma_map_attrs; };
struct kgsl_dma_buf_meta {
    struct kgsl_mem_entry *entry;
    struct dma_buf_attachment *attach;
    struct dma_buf *dmabuf;
    struct sg_table *table;
};

enum scenario {
    NORMAL, SECURE, NONSECURE_MISMATCH, SECURE_MISMATCH,
    EMPTY_SG, ZERO_LENGTH, ATTACH_ERROR, MAP_ERROR, MAP_NULL, ALLOC_ERROR
};
static enum scenario scenario;
static struct dma_buf buffer;
static struct dma_buf_attachment attachment;
static struct sg_table table;
static struct kgsl_device device;
static void *metadata;
static unsigned int allocations, frees, attaches, detaches, maps, unmaps, puts;
static bool listed;

static void *kzalloc(size_t size, int flags)
{
    if (scenario == ALLOC_ERROR)
        return NULL;
    assert(!metadata);
    metadata = calloc(1, size);
    assert(metadata);
    allocations++;
    return metadata;
}
static void kfree(void *ptr)
{
    if (!ptr)
        return;
    assert(ptr == metadata && !buffer.attached && !buffer.pinned && !listed);
    frees++;
    free(ptr);
    metadata = NULL;
}
static struct dma_buf_attachment *dma_buf_attach(struct dma_buf *buf, void *dev)
{
    assert(buf == &buffer && buf->refs == 1 && dev == device.dev);
    assert(!buf->attached && !buf->locked);
    if (scenario == ATTACH_ERROR)
        return ERR_PTR(-EBUSY);
    buf->attached = true;
    attachment.dmabuf = buf;
    attaches++;
    return &attachment;
}
static struct sg_table *dma_buf_map_attachment(struct dma_buf_attachment *attach,
                                              int direction)
{
    assert(attach == &attachment && direction == DMA_BIDIRECTIONAL);
    /* The direct API requires the reservation lock, unlike its wrapper. */
    assert(buffer.locked && buffer.attached && !buffer.pinned);
    maps++;
    if (scenario == MAP_ERROR)
        return ERR_PTR(-EIO);
    /* The DMA-BUF core normalizes a NULL exporter result to -ENOMEM. */
    if (scenario == MAP_NULL)
        return ERR_PTR(-ENOMEM);
    buffer.pinned = true;
    return &table;
}
static struct sg_table *dma_buf_map_attachment_unlocked(
        struct dma_buf_attachment *attach, int direction)
{
    assert(!buffer.locked);
    buffer.locked = true;
    struct sg_table *result = dma_buf_map_attachment(attach, direction);
    buffer.locked = false;
    return result;
}
static void dma_buf_unmap_attachment(struct dma_buf_attachment *attach,
                                    struct sg_table *sgt, int direction)
{
    assert(attach == &attachment && sgt == &table);
    assert(direction == DMA_BIDIRECTIONAL);
    assert(buffer.locked && buffer.attached && buffer.pinned);
    buffer.pinned = false;
    unmaps++;
}
static void dma_buf_unmap_attachment_unlocked(struct dma_buf_attachment *attach,
                                             struct sg_table *sgt, int direction)
{
    assert(!buffer.locked);
    buffer.locked = true;
    dma_buf_unmap_attachment(attach, sgt, direction);
    buffer.locked = false;
}
static void dma_buf_detach(struct dma_buf *buf, struct dma_buf_attachment *attach)
{
    assert(buf == &buffer && attach == &attachment && attach->dmabuf == buf);
    /* Detaching a still-pinned mapping loses the matching unmap. */
    assert(buf->attached && !buf->pinned && !buf->locked);
    buf->attached = false;
    detaches++;
}
static void dma_buf_put(struct dma_buf *buf)
{
    assert(buf == &buffer && buf->refs == 1);
    assert(!buf->attached && !buf->pinned && !buf->locked);
    buf->refs--;
    puts++;
}
static void add_dmabuf_list(struct kgsl_dma_buf_meta *meta)
{
    assert(meta == metadata && meta->table == &table);
    assert(buffer.pinned && !listed);
    listed = true;
}
static void remove_dmabuf_list(struct kgsl_dma_buf_meta *meta)
{
    assert(meta == metadata && listed && buffer.pinned);
    listed = false;
}
'''

CHECK = r'''
int main(void)
{
    for (scenario = NORMAL; scenario <= ALLOC_ERROR; scenario++) {
        struct kgsl_pagetable pagetable = {0};
        struct kgsl_mem_entry entry = {0};
        struct page pages[2] = {{0}, {0}};
        struct scatterlist sg[2] = {
            { .page = &pages[0], .length = 1, .next = &sg[1] },
            { .page = &pages[1], .length = 4096 }
        };
        buffer = (struct dma_buf){ .refs = 1 };
        attachment = (struct dma_buf_attachment){0};
        table.sgl = sg;
        allocations = frees = attaches = detaches = maps = unmaps = puts = 0;
        assert(!metadata && !listed);
        device.dev = &device;
        entry.memdesc.flags = KGSL_MEMFLAGS_IOCOHERENT | KGSL_MEMFLAGS_USE_CPU_MAP;
        if (scenario == SECURE || scenario == SECURE_MISMATCH) {
            entry.memdesc.priv = KGSL_MEMDESC_SECURE;
            pages[0].private = pages[1].private = 1;
        }
        if (scenario == NONSECURE_MISMATCH || scenario == SECURE_MISMATCH)
            pages[1].private = !pages[1].private;
        if (scenario == EMPTY_SG)
            table.sgl = NULL;
        if (scenario == ZERO_LENGTH)
            sg[0].length = sg[1].length = 0;

        int ret = kgsl_setup_dma_buf(&device, &pagetable, &entry, &buffer);
        assert(!buffer.locked);
        if (scenario == NORMAL || scenario == SECURE) {
            assert(ret == 0 && entry.memdesc.size == 8192);
            assert(entry.memdesc.sgt == &table && entry.priv_data == metadata);
            assert(entry.memdesc.pagetable == &pagetable);
            assert(entry.memdesc.ops == &kgsl_dmabuf_ops);
            assert(!(entry.memdesc.flags & KGSL_MEMFLAGS_USE_CPU_MAP));
            assert(entry.memdesc.flags & KGSL_MEMFLAGS_USERMEM_ION);
            assert(attachment.dma_map_attrs & DMA_ATTR_SKIP_CPU_SYNC);
            assert(buffer.refs == 1 && buffer.pinned && listed);
            assert(allocations == 1 && attaches == 1 && maps == 1);
            assert(frees == 0 && unmaps == 0 && detaches == 0 && puts == 0);
            /* Still GPU-mapped: the destructor must leave ownership untouched. */
            entry.memdesc.priv |= KGSL_MEMDESC_MAPPED;
            entry.memdesc.ops->free(&entry.memdesc);
            assert(entry.priv_data == metadata && entry.memdesc.sgt == &table);
            assert(buffer.pinned && buffer.attached && buffer.refs == 1 && listed);
            assert(frees == 0 && unmaps == 0 && detaches == 0 && puts == 0);
            entry.memdesc.priv &= ~KGSL_MEMDESC_MAPPED;
            entry.memdesc.ops->free(&entry.memdesc);
            assert(unmaps == 1 && detaches == 1 && puts == 1 && frees == 1);
            assert(buffer.refs == 0);
        } else {
            int expected = -EINVAL;
            if (scenario == NONSECURE_MISMATCH || scenario == SECURE_MISMATCH)
                expected = -EPERM;
            else if (scenario == ATTACH_ERROR)
                expected = -EBUSY;
            else if (scenario == MAP_ERROR)
                expected = -EIO;
            else if (scenario == MAP_NULL || scenario == ALLOC_ERROR)
                expected = -ENOMEM;
            assert(ret == expected);
            assert(entry.memdesc.size == 0 && !entry.memdesc.pagetable);
            assert(!entry.memdesc.ops);
            assert(entry.memdesc.flags ==
                   (KGSL_MEMFLAGS_IOCOHERENT | KGSL_MEMFLAGS_USE_CPU_MAP));
            assert(!entry.priv_data && !entry.memdesc.sgt);
            assert(unmaps == (scenario <= ZERO_LENGTH ? 1U : 0U));
            assert(attaches == (scenario != ATTACH_ERROR && scenario != ALLOC_ERROR));
            assert(detaches == attaches);
            assert(maps == (scenario != ATTACH_ERROR && scenario != ALLOC_ERROR));
            assert(allocations == (scenario != ALLOC_ERROR) && frees == allocations);
            /* Failed imports must leave the caller's reference intact. */
            assert(buffer.refs == 1 && puts == 0);
            kgsl_destroy_ion(&entry.memdesc);
            assert(frees == allocations && puts == 0);
            dma_buf_put(&buffer);
        }
        assert(!buffer.attached && !buffer.pinned && !buffer.locked && !listed);
        assert(!entry.priv_data && !entry.memdesc.sgt && !metadata);
        /* A repeated destructor cannot unmap, detach, put or free twice. */
        unsigned int old_frees = frees, old_unmaps = unmaps, old_detaches = detaches;
        kgsl_destroy_ion(&entry.memdesc);
        assert(frees == old_frees && unmaps == old_unmaps && detaches == old_detaches);
        assert(puts == 1 && buffer.refs == 0);
    }
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    destroy = extract_function(source, 'kgsl_destroy_ion')
    setup = extract_function(source, 'kgsl_setup_dma_buf')
    ops = '\nstatic struct kgsl_memdesc_ops kgsl_dmabuf_ops = { .free = kgsl_destroy_ion };\n'
    with tempfile.TemporaryDirectory(prefix='ack-kgsl-dmabuf-test-', dir='/tmp/opencode') as tmp:
        root = Path(tmp)
        unit = root / 'dmabuf.c'
        unit.write_text(HARNESS + destroy + ops + setup + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        '-Wno-unused-parameter', '-Wno-unused-function', str(unit),
                        '-o', str(root / 'dmabuf')], check=True, timeout=20)
        subprocess.run([str(root / 'dmabuf')], check=True, timeout=10)
    print('KGSL DMA-BUF: locking, size, secure validation, failure cleanup, release passed')


if __name__ == '__main__':
    main()
