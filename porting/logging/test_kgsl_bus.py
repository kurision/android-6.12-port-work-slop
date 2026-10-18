#!/usr/bin/env python3
"""Check actual msm-bus parsing, cleanup and ICC units without a kernel build."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'drivers/gpu/msm/msm-bus-compat.c'


def extract_function(source, name):
    match = re.search(r'^(?:static )?(?:int|void|uint32_t) ' + re.escape(name)
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
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define GFP_KERNEL 0
#define MAX_CLIENTS 8
#define EPROBE_DEFER 517
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define dev_warn_ratelimited(dev, ...) ((void)(dev), warnings++)
#define dev_err(dev, ...) ((void)(dev), errors++)

static void *allocations[16];
static unsigned int alloc_calls, fail_alloc, live_allocs;
static int fail_index = -1;
static int num_cases_override, num_paths_override, count_override;

static void *kcalloc(size_t n, size_t size, int flags)
{
    if (++alloc_calls == fail_alloc)
        return NULL;
    for (unsigned int i = 0; i < 16; i++) {
        if (!allocations[i]) {
            void *p = calloc(n, size);

            assert(p);
            allocations[i] = p;
            live_allocs++;
            return p;
        }
    }
    abort();
}
static void kfree(void *p)
{
    if (!p)
        return;
    for (unsigned int i = 0; i < 16; i++) {
        if (allocations[i] == p) {
            allocations[i] = NULL;
            live_allocs--;
            free(p);
            return;
        }
    }
    assert(0 && "double free or unowned pointer");
}

struct device_node { int unused; };
struct device { int unused; };
struct platform_device { struct device dev; };
struct icc_path { int unused; };
static struct platform_device *bus_pdev;
static struct icc_path path;
static struct icc_path *bus_path, *lookup_result;
static bool path_warned;
static unsigned int lookups, warnings, errors;
static struct msm_bus_scale_pdata *clients[MAX_CLIENTS];
static const u32 vectors[][4] = {
    {26, 512, 0, 0},
    {26, 512, 0, 1689600},
    {26, 512, 123456, 7449600},
    {26, 512, UINT32_MAX, UINT32_MAX},
};
static unsigned int calls;
static u32 average, peak;

static struct icc_path *of_icc_get(struct device *dev, const char *name)
{
    assert(dev == &bus_pdev->dev && !strcmp(name, "gpu_icc_path"));
    lookups++;
    return lookup_result;
}

static int of_property_read_string(struct device_node *node,
                                  const char *name, const char **value)
{
    *value = "grp3d";
    return 0;
}
static int of_property_read_u32(struct device_node *node,
                               const char *name, int *value)
{
    if (!strcmp(name, "qcom,msm-bus,num-cases"))
        *value = num_cases_override ? num_cases_override :
                 (int)(sizeof(vectors) / sizeof(vectors[0]));
    else {
        assert(!strcmp(name, "qcom,msm-bus,num-paths"));
        *value = num_paths_override ? num_paths_override : 1;
    }
    return 0;
}
static int of_property_count_elems_of_size(struct device_node *node,
                                          const char *name, size_t size)
{
    assert(size == sizeof(vectors[0]));
    if (count_override)
        return count_override;
    return sizeof(vectors) / size;
}
static int of_property_read_u32_index(struct device_node *node,
                                     const char *name, int index, u32 *value)
{
    assert(index >= 0 && (size_t)index < sizeof(vectors) / sizeof(u32));
    if (index == fail_index)
        return -EINVAL;
    *value = vectors[index / 4][index % 4];
    return 0;
}
static int icc_set_bw(void *p, u32 ab, u32 ib)
{
    assert(p == &path);
    calls++;
    average = ab;
    peak = ib;
    return -EIO;
}
'''

CHECK = r'''
static void test_lookup(const char *name)
{
    struct platform_device pdev = {0};
    struct msm_bus_scale_pdata pdata[2] = {0};

    bus_pdev = &pdev;
    assert(msm_bus_scale_register_client(NULL) == 0 && !lookups);
    if (!strcmp(name, "lookup-null")) {
        lookup_result = NULL;
        assert(msm_bus_scale_register_client(&pdata[0]) == 1);
        assert(!bus_path && warnings == 1 && !errors);
        assert(msm_bus_scale_client_update_request(1, 0) == -EINVAL);
        /* A valid no-path request still preserves the existing no-op policy. */
        pdata[0].num_usecases = 1;
        assert(msm_bus_scale_client_update_request(1, 0) == 0 && !calls);
        assert(msm_bus_scale_register_client(&pdata[1]) == 2);
        assert(warnings == 1 && lookups == 2);
        return;
    }
    if (strcmp(name, "lookup-success")) {
        const int failures[] = {-EPROBE_DEFER, -EINVAL, -ENOMEM};

        for (unsigned int i = 0; i < 3; i++) {
            lookup_result = ERR_PTR(failures[i]);
            assert(msm_bus_scale_register_client(&pdata[0]) == 0);
            assert(!bus_path && errors == i + 1 && !warnings);
            for (unsigned int j = 0; j < MAX_CLIENTS; j++)
                assert(!clients[j]);
        }
        assert(lookups == 3);
    }
    /* Recovery after lookup errors must retry without consuming a slot. */
    lookup_result = &path;
    assert(msm_bus_scale_register_client(&pdata[0]) == 1);
    assert(bus_path == &path && !warnings);
    unsigned int previous_lookups = lookups;
    assert(msm_bus_scale_register_client(&pdata[1]) == 2);
    assert(lookups == previous_lookups);
}

int main(int argc, char **argv)
{
    struct platform_device pdev = {0};
    struct device_node node = {0};
    struct msm_bus_scale_pdata *pdata;

    if (argc > 1 && !strncmp(argv[1], "lookup-", 7)) {
        test_lookup(argv[1]);
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "dimensions")) {
        const int invalid[][3] = {
            {INT_MAX, 2, 4}, {2, INT_MAX, 4}, {INT_MAX, INT_MAX, 4},
            {2, 3, 4}, {1, 1, -EINVAL},
        };

        for (unsigned int i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
            pdata = kcalloc(1, sizeof(*pdata), GFP_KERNEL);
            num_cases_override = invalid[i][0];
            num_paths_override = invalid[i][1];
            count_override = invalid[i][2];
            assert(parse_table(&pdev, &node, pdata) == -EINVAL);
            assert(!pdata->num_usecases && !pdata->usecase);
            free_pdata(pdata);
            assert(!live_allocs);
        }
        return 0;
    }
    if (argc > 1) {
        int allocation_failure = !strcmp(argv[1], "allocation");
        int count = allocation_failure ? 5 : 16;

        for (int i = 0; i < count; i++) {
            assert(!live_allocs);
            fail_alloc = 0;
            pdata = kcalloc(1, sizeof(*pdata), GFP_KERNEL);
            alloc_calls = 0;
            fail_alloc = allocation_failure ? i + 1 : 0;
            fail_index = allocation_failure ? -1 : i;
            assert(parse_table(&pdev, &node, pdata) ==
                   (allocation_failure ? -ENOMEM : -EINVAL));
            free_pdata(pdata);
            assert(!live_allocs);
        }
        free_pdata(NULL);
        return 0;
    }

    pdata = kcalloc(1, sizeof(*pdata), GFP_KERNEL);

    assert(pdata && parse_table(&pdev, &node, pdata) == 0);
    assert(bus_pdev == &pdev && pdata->num_usecases == 4);
    clients[0] = pdata;
    bus_path = &path;
    for (int i = 0; i < pdata->num_usecases; i++) {
        struct msm_bus_vectors *v = pdata->usecase[i].vectors;

        assert(v->src == 26 && v->dst == 512);
        /* Vendor consumers, including KGSL, expect bytes per second. */
        assert(v->ab == (uint64_t)vectors[i][2] * 1000);
        assert(v->ib == (uint64_t)vectors[i][3] * 1000);
        assert(msm_bus_scale_client_update_request(1, i) == -EIO);
        assert(average == vectors[i][2] && peak == vectors[i][3]);
    }
    assert(calls == 4);
    /* Also exercise a caller updating the vendor byte/s fields directly. */
    pdata->usecase[1].vectors[0].ab = 123000;
    pdata->usecase[1].vectors[0].ib = 456000;
    assert(msm_bus_scale_client_update_request(1, 1) == -EIO);
    assert(average == 123 && peak == 456);
    assert(msm_bus_scale_client_update_request(0, 0) == -EINVAL);
    assert(msm_bus_scale_client_update_request(1, 4) == -EINVAL);
    assert(calls == 5);
    free_pdata(pdata);
    assert(!live_allocs);
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    header = (ROOT / 'include/linux/msm-bus.h').read_text()
    structs = '\n'.join(re.search(r'^struct ' + name + r' \{.*?^\};',
                                  header, re.M | re.S).group()
                        for name in ('msm_bus_vectors', 'msm_bus_paths',
                                     'msm_bus_lat_vectors', 'msm_bus_scale_pdata'))
    units = (ROOT / 'include/linux/interconnect.h').read_text()
    macro = re.search(r'^#define Bps_to_icc\(x\).*$', units, re.M).group()
    functions = '\n'.join(extract_function(source, name) for name in
                          ('parse_table', 'free_pdata',
                           'msm_bus_scale_register_client',
                           'msm_bus_scale_client_update_request'))
    with tempfile.TemporaryDirectory(prefix='kgsl-bus-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text('#include <stdint.h>\n' + structs + '\n' + macro
                         + '\n' + HARNESS + functions + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-Wno-sign-compare',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(cfile), '-o', str(binary)], check=True)
        failed = []
        for case in ([], ['allocation'], ['property'], ['dimensions'], ['lookup-null'],
                     ['lookup-error'], ['lookup-success']):
            result = subprocess.run([str(binary), *case])
            if result.returncode:
                failed.append(case or ['bandwidth'])
        if failed:
            raise SystemExit(f'KGSL bus regression failed: {failed}')
    print('KGSL bus bandwidth, cleanup and path-lookup regressions: PASS')


if __name__ == '__main__':
    main()
