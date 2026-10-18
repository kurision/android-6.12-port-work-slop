#!/usr/bin/env python3
"""Exercise actual KGSL mapping/cache C with DMA-coalesced physical SG entries."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm'


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2] + '\n'


def main():
    iommu = (ROOT / 'kgsl_iommu.c').read_text()
    sharedmem = (ROOT / 'kgsl_sharedmem.c').read_text()
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/types.h>
#define PAGE_SHIFT 12
#define PAGE_SIZE (1UL << PAGE_SHIFT)
#define BASE 0x100000UL
#define GFP_ATOMIC 0
#define KGSL_SPARSE_BIND_MULTIPLE_TO_PHYS 1
#define IS_ALIGNED(x, a) (!((x) & ((a) - 1)))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define dev_err(device, ...) ((void)(device))
#define EXPORT_SYMBOL(name)
typedef uint64_t phys_addr_t;
struct page { phys_addr_t phys; unsigned int cpu, gpu; };
struct scatterlist { struct page *page; size_t length; struct scatterlist *next; };
struct sg_table { struct scatterlist *sgl; unsigned int nents, orig_nents; };
#define for_each_sg(first, sg, count, i) \
    for ((i) = 0, (sg) = (first); (i) < (unsigned int)(count); (i)++, (sg) = (sg)->next)
#define sg_page(sg) ((sg)->page)
#define nth_page(page, n) ((page) + (n))
#define page_to_phys(page) ((page)->phys)
struct iommu_domain { phys_addr_t ptes[16]; };
struct kgsl_device { void *dev; };
struct kgsl_mmu { struct kgsl_device *device; };
struct kgsl_iommu_pt { struct iommu_domain *domain; };
struct kgsl_pagetable { struct kgsl_mmu *mmu; struct kgsl_iommu_pt *priv; };
struct kgsl_memdesc {
    uint64_t gpuaddr, size;
    struct page **pages;
    struct sg_table *sgt;
    void *hostptr;
};
#define KGSL_MMU_DEVICE(mmu) ((mmu)->device)
static void _iommu_sync_mmu_pc(bool on) { (void)on; }
/* Software page table implements the ACK physical IOMMU mapping contract,
 * independently of DMA addresses and the DMA-mapped segment count. */
static int iommu_map(struct iommu_domain *domain, uint64_t addr, phys_addr_t phys,
                     size_t size, unsigned int flags, int allocation)
{
    (void)flags; (void)allocation;
    assert(IS_ALIGNED(addr | phys | size, PAGE_SIZE));
    assert(addr >= BASE && addr + size <= BASE + sizeof(domain->ptes) / sizeof(phys_addr_t) * PAGE_SIZE);
    for (size_t i = 0; i < size / PAGE_SIZE; i++)
        domain->ptes[(addr - BASE) / PAGE_SIZE + i] = phys + i * PAGE_SIZE;
    return 0;
}
static ssize_t iommu_map_sg(struct iommu_domain *domain, uint64_t addr,
                            struct scatterlist *sg, int nents, unsigned int flags, int allocation)
{
    size_t mapped = 0;
    for (int i = 0; i < nents; i++, sg = sg->next) {
        int ret = iommu_map(domain, addr + mapped, page_to_phys(sg_page(sg)), sg->length, flags, allocation);
        if (ret)
            return ret;
        mapped += sg->length;
    }
    return mapped;
}
static int _iommu_unmap_sync_pc(struct kgsl_pagetable *pt, uint64_t addr, uint64_t size)
{
    for (size_t i = 0; i < size / PAGE_SIZE; i++)
        pt->priv->domain->ptes[(addr - BASE) / PAGE_SIZE + i] = 0;
    return 0;
}
static unsigned int _get_protection_flags(struct kgsl_pagetable *pt, struct kgsl_memdesc *memdesc)
{ (void)pt; (void)memdesc; return 0; }
static struct sg_table *kgsl_alloc_sgt_from_pages(struct kgsl_memdesc *memdesc)
{ (void)memdesc; assert(false); return NULL; }
static void kgsl_free_sgt(struct sg_table *table) { (void)table; assert(false); }
static int _iommu_map_guard_page(struct kgsl_pagetable *pt, struct kgsl_memdesc *memdesc,
                                uint64_t addr, unsigned int flags)
{ (void)pt; (void)memdesc; (void)addr; (void)flags; return 0; }
static int kgsl_memdesc_get_pagesize(struct kgsl_memdesc *memdesc)
{ (void)memdesc; return PAGE_SIZE; }
static uint64_t kgsl_memdesc_footprint(struct kgsl_memdesc *memdesc) { return memdesc->size; }
static int _map_to_one_page(struct kgsl_pagetable *pt, uint64_t addr, struct kgsl_memdesc *memdesc,
                            uint64_t offset, uint64_t size, unsigned int flags)
{ (void)pt; (void)addr; (void)memdesc; (void)offset; (void)size; (void)flags; assert(false); return -EINVAL; }
/* Model CPU dirty cache lines becoming visible to a GPU consumer. */
static unsigned int host_visible;
static int kgsl_do_cache_op(struct page *page, void *addr, uint64_t offset, uint64_t size, unsigned int op)
{
    (void)op;
    if (!page) {
        assert(addr && size == sizeof(host_visible));
        memcpy(&host_visible, (char *)addr + offset, size);
        return 0;
    }
    assert(IS_ALIGNED(offset | size, PAGE_SIZE));
    for (size_t i = offset / PAGE_SIZE; i < (offset + size) / PAGE_SIZE; i++)
        page[i].gpu = page[i].cpu;
    return 0;
}
'''
    checks = r'''
int main(void)
{
    /* Three physical entries; DMA can merge the first two contiguous
     * entries into one DMA segment without changing their physical lengths. */
    for (unsigned int dma_count = 2; dma_count <= 3; dma_count++) {
        struct page pages[6];
        for (unsigned int i = 0; i < 6; i++)
            pages[i] = (struct page) {
                .phys = i < 4 ? 0x10000 + i * PAGE_SIZE : 0x80000 + (i - 4) * PAGE_SIZE,
                .cpu = 100 + i,
            };
        struct scatterlist sg[3] = {
            { &pages[0], 2 * PAGE_SIZE, &sg[1] },
            { &pages[2], 2 * PAGE_SIZE, &sg[2] },
            { &pages[4], 2 * PAGE_SIZE, NULL },
        };
        struct sg_table table = { sg, dma_count, 3 };
        struct kgsl_memdesc memdesc = { .gpuaddr = BASE, .size = 6 * PAGE_SIZE, .sgt = &table };
        struct iommu_domain domain = {0};
        struct kgsl_iommu_pt iommu_pt = { &domain };
        struct kgsl_device device = {0};
        struct kgsl_mmu mmu = { &device };
        struct kgsl_pagetable pt = { &mmu, &iommu_pt };
        assert(kgsl_iommu_map(&pt, &memdesc) == 0);
        for (unsigned int i = 0; i < 6; i++)
            assert(domain.ptes[i] == pages[i].phys);

        domain = (struct iommu_domain) {0};
        assert(kgsl_iommu_map_offset(&pt, BASE, 0, &memdesc, 3 * PAGE_SIZE, 2 * PAGE_SIZE, 0) == 0);
        assert(domain.ptes[0] == pages[3].phys && domain.ptes[1] == pages[4].phys);
        assert(domain.ptes[2] == 0);

        assert(kgsl_cache_range_op(&memdesc, 3 * PAGE_SIZE, 3 * PAGE_SIZE, 0) == 0);
        for (unsigned int i = 0; i < 6; i++)
            assert(pages[i].gpu == (i < 3 ? 0 : pages[i].cpu));
    }
    /* Reject a wrapped host-cache endpoint before doing pointer arithmetic. */
    struct kgsl_memdesc host = {
        .hostptr = (void *)(uintptr_t)(UINTPTR_MAX - PAGE_SIZE + 1),
        .size = 2 * PAGE_SIZE,
    };
    assert(kgsl_cache_range_op(&host, 0, 2 * PAGE_SIZE, 0) == -ERANGE);
    assert(kgsl_cache_range_op(&host, PAGE_SIZE, 1, 0) == -ERANGE);
    unsigned int host_words[] = { 0x12345678, 0xabcdef01 };
    host.hostptr = host_words;
    host.size = sizeof(host_words);
    assert(kgsl_cache_range_op(&host, sizeof(host_words[0]), sizeof(host_words[1]), 0) == 0);
    assert(host_visible == host_words[1]);
    return 0;
}
'''
    functions = ''.join(function(iommu, name) for name in (
        'static int _iommu_map_sg_offset_sync_pc(',
        'static int _iommu_map_sg_sync_pc(',
        'static int\nkgsl_iommu_map(',
        'static int kgsl_iommu_map_offset(',
    )) + function(sharedmem, 'int kgsl_cache_range_op(')
    with tempfile.TemporaryDirectory(prefix='ack-kgsl-sg-test-', dir='/tmp/opencode') as tmp:
        root = Path(tmp)
        unit, binary = root / 'sg.c', root / 'sg'
        unit.write_text(harness + functions + checks)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(unit), '-o', str(binary)], check=True, timeout=20)
        subprocess.run([str(binary)], check=True, timeout=10)
    print('KGSL SG: merged/unmerged imports fully mapped, offset mapping and GPU cache visibility passed')


if __name__ == '__main__':
    main()
