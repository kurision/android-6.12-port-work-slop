#!/usr/bin/env python3
"""Exercise actual hyp_assign_table ownership transfers without a kernel build."""
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/secure_buffer_compat.c'


def main():
    source = SOURCE.read_text()
    start = source.index('int hyp_assign_table(')
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stddef.h>
typedef uint64_t u64;
typedef uint64_t phys_addr_t;
#define BIT(n) (1UL << (n))
#define BIT_ULL(n) (1ULL << (n))
struct scatterlist {
    phys_addr_t phys;
    unsigned int length;
    struct scatterlist *next;
};
struct sg_table {
    struct scatterlist *sgl;
    unsigned int nents, orig_nents;
};
#define for_each_sg(first, sg, count, i) \
    for ((i) = 0, (sg) = (first); (i) < (count); (i)++, (sg) = (sg)->next)
#define sg_phys(sg) ((sg)->phys)
struct qcom_scm_vmperm { int vmid; int perm; };
struct owned_range {
    phys_addr_t start;
    size_t length;
    u64 owner;
};
static struct owned_range memory[3];
static unsigned int attempts[3], calls;
static int retry_at = -1, retries, fail_at = -1, failure;
static int expected_perm;

/* SCM checks current ownership, transfers it, then mutates the source mask.
 * EAGAIN leaves both ownership and the in/out mask untouched. */
static int qcom_scm_assign_mem(phys_addr_t address, size_t length, u64 *source,
                               const struct qcom_scm_vmperm *dest, int count)
{
    unsigned int i;
    assert(++calls < 30); /* Bound an accidentally infinite retry loop. */
    for (i = 0; i < 3; i++)
        if (memory[i].start == address && memory[i].length == length)
            break;
    assert(i < 3);
    attempts[i]++;
    assert(count == 1 && dest && source);
    assert(dest->vmid >= 0 && dest->vmid < 32);
    assert(dest->perm == expected_perm);
    assert(memory[i].owner == *source);
    if ((int)i == retry_at && retries) {
        retries--;
        return -EAGAIN;
    }
    if ((int)i == fail_at)
        return failure;
    memory[i].owner = BIT_ULL(dest->vmid);
    *source = memory[i].owner;
    return 0;
}
'''
    check = r'''
struct guarded_vmid { int vmid; unsigned int canary; };
static struct scatterlist entries[3];
static struct sg_table table;
static struct guarded_vmid src, dst;
static int perms;
static void reset(int from, int to)
{
    for (unsigned int i = 0; i < 3; i++) {
        entries[i] = (struct scatterlist) {
            .phys = 0x10000 + i * 0x10000,
            .length = 0x1000 * (i + 1),
            .next = i < 2 ? &entries[i + 1] : NULL,
        };
        memory[i] = (struct owned_range) {
            entries[i].phys, entries[i].length, BIT_ULL(from),
        };
        attempts[i] = 0;
    }
    table = (struct sg_table) { entries, 3, 3 };
    src = (struct guarded_vmid) { from, 0xa5b6c7d8 };
    dst = (struct guarded_vmid) { to, 0x12345678 };
    perms = expected_perm = 6;
    calls = 0;
    retry_at = fail_at = -1;
    retries = 0;
}
static int transfer(void)
{
    return hyp_assign_table(&table, &src.vmid, 1, &dst.vmid, &perms, 1);
}
static void callers_unchanged(int from, int to)
{
    assert(src.vmid == from && src.canary == 0xa5b6c7d8);
    assert(dst.vmid == to && dst.canary == 0x12345678);
    assert(perms == 6);
}
static void all_owned(u64 owner)
{
    for (unsigned int i = 0; i < 3; i++)
        assert(memory[i].owner == owner);
}
int main(void)
{
    /* Each distinct physical extent must start with the original source mask,
     * not the destination mask SCM wrote after the preceding extent. */
    reset(3, 10);
    assert(transfer() == 0);
    all_owned(1ULL << 10);
    callers_unchanged(3, 10);
    assert(calls == 3);
    src.vmid = 10;
    dst.vmid = 3;
    assert(transfer() == 0);
    all_owned(1ULL << 3);
    callers_unchanged(10, 3);
    assert(calls == 6);

    reset(3, 10);
    retry_at = 1;
    retries = 2;
    assert(transfer() == 0);
    assert(calls == 5 && attempts[0] == 1 && attempts[1] == 3 && attempts[2] == 1);
    all_owned(1ULL << 10);
    callers_unchanged(3, 10);

    /* Failed assignment means unknown ownership to KGSL, even after partial
     * success: report EADDRNOTAVAIL so KGSL does not free secure pages. */
    const int errors[] = { -EIO, -EINVAL, -EADDRNOTAVAIL };
    for (unsigned int e = 0; e < sizeof(errors) / sizeof(errors[0]); e++) {
        for (int failed = 0; failed < 2; failed++) {
            reset(3, 10);
            fail_at = failed;
            failure = errors[e];
            assert(transfer() == -EADDRNOTAVAIL);
            assert(calls == (unsigned int)failed + 1);
            for (int i = 0; i < 3; i++) {
                assert(memory[i].owner == (i < failed ? (1ULL << 10) : (1ULL << 3)));
                assert(attempts[i] == (unsigned int)(i <= failed));
            }
            callers_unchanged(3, 10);
        }
    }

    /* Validation must reject without invoking SCM or changing ownership. */
#define INVALID(expr) do { \
    assert((expr) == -EINVAL); \
    assert(calls == 0); \
    all_owned(1ULL << 3); \
} while (0)
    reset(3, 10);
    const int counts[] = { -1, 0, 2 };
    for (unsigned int i = 0; i < sizeof(counts) / sizeof(counts[0]); i++) {
        INVALID(hyp_assign_table(&table, &src.vmid, counts[i], &dst.vmid, &perms, 1));
        INVALID(hyp_assign_table(&table, &src.vmid, 1, &dst.vmid, &perms, counts[i]));
    }
    INVALID(hyp_assign_table(NULL, &src.vmid, 1, &dst.vmid, &perms, 1));
    INVALID(hyp_assign_table(&table, NULL, 1, &dst.vmid, &perms, 1));
    INVALID(hyp_assign_table(&table, &src.vmid, 1, NULL, &perms, 1));
    INVALID(hyp_assign_table(&table, &src.vmid, 1, &dst.vmid, NULL, 1));
    table.sgl = NULL;
    INVALID(transfer());
    table.sgl = entries;
    table.nents = 0;
    INVALID(transfer());
    table.nents = 3;
    const int invalid_sources[] = { -1, 64, 127 };
    const int invalid_destinations[] = { -1, 32, 63 };
    for (unsigned int i = 0; i < 3; i++) {
        src.vmid = invalid_sources[i];
        INVALID(transfer());
        src.vmid = 3;
        dst.vmid = invalid_destinations[i];
        INVALID(transfer());
        dst.vmid = 10;
    }
    callers_unchanged(3, 10);
    /* Source uses the full u64 mask; destination is limited by SCM's int. */
    reset(0, 31);
    assert(transfer() == 0);
    all_owned(1ULL << 31);
    callers_unchanged(0, 31);
    reset(63, 0);
    assert(transfer() == 0);
    all_owned(1ULL);
    callers_unchanged(63, 0);
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='ack-secure-buffer-test-') as tmp:
        root = Path(tmp)
        unit = root / 'secure_buffer.c'
        unit.write_text(harness + source[start:end] + check)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-sign-compare', str(unit), '-o', str(root / 'secure_buffer')],
                       check=True, timeout=20)
        subprocess.run([str(root / 'secure_buffer')], check=True, timeout=10)
    print('secure buffer: ownership, mutable masks, retries, failure and validation passed')


if __name__ == '__main__':
    main()
