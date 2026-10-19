#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile actual APCC transaction/notifier code with host MMIO and rail faults.

Not a kernel build, CCF integration test, or hardware validation. Tests the
shared domain, including abort, readback, cold handoff and faulted rollback.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
source = (REPO / "drivers/clk/qcom/apcc-msm8953.c").read_text()
header = (REPO / "include/dt-bindings/clock/qcom,apcc-msm8953.h").read_text()
constants = "\n".join(re.findall(r"^#define APCC_.*$", header + "\n" + source, re.M))
constants += "\n" + re.search(r"^#define RPM_SMD_LEVEL_SVS\s+.*$",
                            (REPO / "include/dt-bindings/power/qcom-rpmpd.h").read_text(),
                            re.M)[0]
state = source[source.index("static const unsigned int apcc_pll_offsets"):
               source.index("static const char * const apcc_input_names")]
core = source[source.index("/* Lowest corner covering"):
              source.index("static const struct clk_ops apcc_cpu_ops")]
inputs = source[source.index("static const char * const apcc_input_names"):
                source.index("static const char * const apcc_rcg_names")]
pins = source[source.index("static int apcc_pin_inputs"):
              source.index("static int apcc_msm8953_probe")]

# Source contract guards complement, but do not replace, the executable checks.
assert "clk_alpha_pll_configure(" not in source
assert "clk_set_rate(" not in source
assert "init.flags = CLK_GET_RATE_NOCACHE;" in source
assert "devm_clk_get_enabled(" not in source
assert "devm_clk_notifier_register(dev, clock, &output->nb)" in source
assert "regulator_enable(apcc->supply)" in source
assert "clk_rate_exclusive_get(apcc_inputs[i].clock)" in source
assert "clocks->hws[i] = &apcc->output[APCC_CPU0_CLK].hw;" in source
assert '.recalc_rate = apcc_recalc_rate' in source
assert "devm_platform_ioremap_resource_byname(pdev, apcc_rcg_names[i])" in source
for name in ("apcc_pll_regmap_config", "apcc_mux_regmap_config"):
    config = re.search(r"const struct regmap_config " + name +
                       r" = \{(.*?)\n\s*\};", source, re.S)[1]
    for field, value in (("reg_bits", 32), ("val_bits", 32), ("reg_stride", 4)):
        assert re.search(r"\." + field + r"\s*=\s*" + str(value) + r"\s*,", config)
assert "opp-shared;" in (REPO / "arch/arm64/boot/dts/qcom/msm8953-cpu.dtsi").read_text()
assert "regulator_disable(" not in source
assert "devm_regulator_get(" not in source
assert "ramoops_cpuclk_c1_to_gpll0" not in (REPO / "fs/pstore/ram.c").read_text()
assert 'power-domains = <&rpmpd MSM8953_VDDMX_AO>;' in (
    REPO / "arch/arm64/boot/dts/qcom/msm8953-cpu.dtsi").read_text()
dts = (REPO / "arch/arm64/boot/dts/qcom/msm8953-cpu.dtsi").read_text()
for cpu in range(8):
    block = re.search(r"&CPU" + str(cpu) + r"\s*\{(.*?)\};", dts, re.S)[1]
    assert 'operating-points-v2 = <&msm8953_cpu_opp>;' in block
    assert 'cpu-supply' not in block
    assert 'clocks = <&apcc APCC_CPU' + ('0' if cpu < 4 else '4') + '_CLK>;' in block
assert list(map(int, re.findall(r"opp-hz = /bits/ 64 <(\d+)>;", dts))) == [
    652800000, 1036800000, 1401600000, 1689600000, 1804800000, 1958400000, 2016000000]

mock = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U << (l)) & (~0U >> (31 - (h))))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define max(a, b) ((a) > (b) ? (a) : (b))
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define PRE_RATE_CHANGE 0
#define POST_RATE_CHANGE 1
#define ABORT_RATE_CHANGE 2
#define NOTIFY_STOP_MASK 0x8000
struct regmap { u32 regs[16]; int id; };
struct device { void *of_node; };
struct regulator { int unused; };
struct clk_hw { int unused; };
struct clk { int id; };
struct notifier_block { int unused; };
struct mutex { bool locked; };
#define DEFINE_MUTEX(name) struct mutex name = {0}
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
/* Match the kernel's object-like current macro, even without kernel headers. */
#define current get_current()
struct clk_notifier_data { unsigned long old_rate, new_rate; };
struct clk_rate_request {
    unsigned long rate, min_rate, max_rate, best_parent_rate;
    struct clk_hw *best_parent_hw;
};
static void mutex_lock(struct mutex *m) { assert(!m->locked); m->locked = true; }
static void mutex_unlock(struct mutex *m) { assert(m->locked); m->locked = false; }
static u64 div_u64(u64 a, unsigned b) { return a / b; }
static int notifier_from_errno(int e) { return e ? NOTIFY_STOP_MASK | (1 - e) : 1; }
#define dev_warn(dev, ...) ((void)(dev))
#define dev_info(dev, ...) ((void)(dev))
#define dev_err(dev, ...) ((void)(dev))
#define dev_err_ratelimited(dev, ...) ((void)(dev))
#define mb() do { } while (0)
static void usleep_range(unsigned min, unsigned max) { assert(min <= max); }
static struct regmap maps[4];
static int rail, voltage_fail, op_count, fail_op, fail_map, safety_failures;
static int drop_map, drop_reg, drop_nth;
static unsigned long lock_fail_rate;
static int regmap_read(struct regmap *m, unsigned reg, u32 *out);
static int regmap_write(struct regmap *m, unsigned reg, u32 value);
static int regmap_update_bits(struct regmap *m, unsigned reg, u32 mask, u32 value);
static int regulator_set_voltage(struct regulator *r, int min, int max);
static int regulator_enable(struct regulator *r);
static int power_op, power_fail, supply_gets, mx_attaches, mx_detaches, mx_refs, mx_votes, rail_enables;
static bool mx_runtime_error;
static struct device fake_device, mx_device;
static struct regulator fake_supply;
static int power_step(void) { return ++power_op == power_fail ? -EIO : 0; }
static struct regulator *regulator_get(struct device *dev, const char *name)
{
    assert(dev == &fake_device && !strcmp(name, "vdd-cl"));
    if (power_step()) return (void *)(intptr_t)-EIO;
    supply_gets++; return &fake_supply;
}
static int of_property_match_string(void *node, const char *prop, const char *name)
{
    assert(!strcmp(prop, "power-domain-names") && !strcmp(name, "mx"));
    return power_step();
}
static struct device *genpd_dev_pm_attach_by_id(struct device *dev, int index)
{
    assert(dev == &fake_device && index == 0);
    if (power_step()) return (void *)(intptr_t)-EIO;
    mx_attaches++; return &mx_device;
}
static int pm_runtime_resume_and_get(struct device *dev)
{
    assert(dev == &mx_device);
    if (mx_runtime_error) return -EINVAL;
    if (power_step()) { mx_runtime_error = true; return -EIO; }
    mx_refs++; return 0;
}
static void dev_pm_domain_detach(struct device *dev, bool power_off)
{
    assert(dev == &mx_device && !mx_refs && !mx_votes && !power_off);
    mx_detaches++; mx_runtime_error = false;
}
static int dev_pm_genpd_set_performance_state(struct device *dev, unsigned level)
{
    assert(dev == &mx_device && level == 128);
    if (power_step()) return -EIO;
    assert(mx_refs == 1); mx_votes++; return 0;
}
static struct clk input_clocks[] = {{0}, {1}, {2}};
static int acquire_op, acquire_fail, enable_refs[3], exclusive_refs[3], gets[3];
static struct clk *clk_get(struct device *dev, const char *name)
{
    (void)dev;
    int id = !strcmp(name, "xo") ? 0 : !strcmp(name, "gpll0_early") ? 1 : 2;
    if (++acquire_op == acquire_fail) return (void *)(intptr_t)-EIO;
    gets[id]++;
    return &input_clocks[id];
}
static int clk_prepare_enable(struct clk *clock)
{
    if (++acquire_op == acquire_fail) return -EIO;
    enable_refs[clock->id]++;
    return 0;
}
static int clk_rate_exclusive_get(struct clk *clock)
{
    if (++acquire_op == acquire_fail) return -EIO;
    exclusive_refs[clock->id]++;
    return 0;
}
static unsigned long clk_get_rate(struct clk *clock)
{
    static unsigned long rates[] = {19200000, 600000000, 800000000};
    return rates[clock->id];
}
static void clk_put(struct clk *clock) { assert(!enable_refs[clock->id]); }
#define regmap_read_poll_timeout(map, reg, value, condition, delay, timeout) ({ \
    int _ret = -ETIMEDOUT; \
    for (unsigned _i = 0; _i <= (timeout); _i++) { \
        _ret = regmap_read(map, reg, &(value)); \
        if (_ret || (condition)) break; \
        _ret = -ETIMEDOUT; \
    } \
    _ret; \
})
'''

io = r'''
static struct apcc_msm8953 *domain;
static unsigned long raw_rate(int id)
{
    u32 cfg = maps[id + 1].regs[1];
    unsigned long parent;
    switch ((cfg >> 8) & 7) {
    case APCC_SRC_XO: parent = APCC_XO_RATE; break;
    case APCC_SRC_GPLL0: parent = domain->input_rates[1]; break;
    case APCC_SRC_GPLL2: parent = domain->input_rates[2]; break;
    case APCC_SRC_PLL:
        if (!(maps[0].regs[0] & APCC_PLL_LOCK)) return 0;
        parent = maps[0].regs[APCC_PLL_L / 4] * APCC_XO_RATE;
        break;
    default: return 0;
    }
    unsigned div = (cfg & 31) + 1;
    return (u64)parent * 2 / (div < 2 ? 2 : div);
}
static void check_voltage(void)
{
    if (!apcc_power.mx_active || !apcc_power.mx_voted) safety_failures++;
    for (int id = 0; id < APCC_NUM_CLOCKS; id++) {
        const struct apcc_plan *p = id == APCC_CCI_CLK ?
                                   &domain->cci_plan : &domain->cpu_plan;
        unsigned long rate = raw_rate(id);
        int required = apcc_plan_corner(p, rate);
        if (!rate || required < 0 || rail < required) safety_failures++;
    }
}
static int io_fault(struct regmap *m, bool write)
{
    op_count++;
    if (op_count == fail_op) { fail_op = -1; return -EIO; }
    if (write && m->id == fail_map) return -EIO;
    return 0;
}
static int regmap_read(struct regmap *m, unsigned reg, u32 *out)
{
    assert(!(reg & 3) && reg < sizeof(m->regs));
    if (io_fault(m, false)) return -EIO;
    *out = m->regs[reg / 4];
    return 0;
}
static int regmap_write(struct regmap *m, unsigned reg, u32 value)
{
    /* Only CPU4's branch control is documented by the donor early handoff. */
    if (m->id && reg == APCC_RCG_CBCR) assert(m->id == 2);
    if (io_fault(m, true)) return -EIO;
    if (m->id == drop_map && (int)reg == drop_reg && !--drop_nth) return 0;
    m->regs[reg / 4] = value;
    if (m->id == 0 && (reg == APCC_PLL_MODE || reg == APCC_PLL_L)) {
        if ((m->regs[0] & 6) == 6 &&
            m->regs[APCC_PLL_L / 4] * APCC_XO_RATE != lock_fail_rate)
            m->regs[0] |= APCC_PLL_LOCK;
        else
            m->regs[0] &= ~APCC_PLL_LOCK;
    }
    if (m->id && reg == APCC_RCG_CMD) m->regs[0] &= ~APCC_RCG_UPDATE;
    check_voltage();
    return 0;
}
static int regmap_update_bits(struct regmap *m, unsigned reg, u32 mask, u32 value)
{
    u32 old;
    int ret = regmap_read(m, reg, &old);
    if (ret) return ret;
    return regmap_write(m, reg, (old & ~mask) | (value & mask));
}
static int regulator_set_voltage(struct regulator *r, int min, int max)
{
    (void)r;
    assert(min == max && min > 0);
    if (voltage_fail) { voltage_fail = 0; return -EIO; }
    rail = min;
    check_voltage();
    return 0;
}
static int regulator_enable(struct regulator *r)
{
    assert(r == &fake_supply && rail > 0);
    if (power_step()) return -EIO;
    rail_enables++; return 0;
}
'''
# io uses the real plan helper; put that helper before the host IO definitions.
plan_end = core.index("static unsigned long apcc_cci_rate")

tests = r'''
static unsigned long cpu_rates[] = {0, 652800000, 1036800000, 1401600000,
                                   1689600000, 1804800000, 1958400000, 2016000000};
static unsigned long cci_rates[] = {0, 261120000, 414720000, 560640000,
                                   675840000, 721920000, 783360000, 806400000};
static int corners[] = {0, 1, 2, 3, 4, 5, 6, 7};
static void init(struct apcc_msm8953 *a, bool cold, int index)
{
    memset(a, 0, sizeof(*a)); memset(maps, 0, sizeof(maps));
    memset(&apcc_power, 0, sizeof(apcc_power));
    power_op = power_fail = supply_gets = mx_attaches = mx_detaches = mx_refs = mx_votes = rail_enables = 0;
    mx_runtime_error = false;
    domain = a;
    a->dev = &fake_device; a->supply = &fake_supply;
    a->cpu_plan = (struct apcc_plan){cpu_rates, corners, 8};
    a->cci_plan = (struct apcc_plan){cci_rates, corners, 8};
    a->input_rates[0] = APCC_XO_RATE;
    a->input_rates[1] = 600000000; a->input_rates[2] = 800000000;
    a->pll = &maps[0];
    rail = a->corner = cold ? 2 : index;
    apcc_power.corner = rail; apcc_power.supply = a->supply;
    apcc_power.enabled = apcc_power.mx_active = apcc_power.mx_voted = true;
    for (int i = 0; i < 4; i++) maps[i].id = i;
    maps[0].regs[APCC_PLL_USER / 4] = 0x109;
    maps[0].regs[APCC_PLL_CONFIG / 4] = 0x12345678;
    if (!cold) {
        maps[0].regs[0] = APCC_PLL_LOCK | APCC_PLL_ON;
        maps[0].regs[APCC_PLL_L / 4] = cpu_rates[index] / APCC_XO_RATE;
    }
    for (int i = 0; i < APCC_NUM_CLOCKS; i++) {
        a->mux[i] = &maps[i + 1]; a->output[i].apcc = a; a->output[i].id = i;
        maps[i + 1].regs[0] = 2;
        maps[i + 1].regs[1] = 0xa0000000 | ((cold ? APCC_SRC_GPLL0 : APCC_SRC_PLL) << 8) |
            (i == APCC_CCI_CLK ? (cold ? 3 : APCC_CCI_DIV) : APCC_CPU_DIV);
        maps[i + 1].regs[APCC_RCG_CBCR / 4] = 0x80000000 | APCC_RCG_ENABLE;
    }
    op_count = 0; fail_op = fail_map = -1; voltage_fail = safety_failures = 0;
    drop_map = drop_reg = -1; drop_nth = 0;
    lock_fail_rate = 0;
}
static void check_target(struct apcc_msm8953 *a, int index)
{
    assert(raw_rate(0) == cpu_rates[index] && raw_rate(1) == cpu_rates[index]);
    assert(raw_rate(2) == cci_rates[index]);
    assert(apcc_recalc_rate(&a->output[1].hw, 0) == cpu_rates[index]);
    assert(apcc_recalc_rate(&a->output[2].hw, 0) == cci_rates[index]);
    assert(!safety_failures && !a->faulted);
    assert(maps[2].regs[APCC_RCG_CBCR / 4] & APCC_RCG_ENABLE);
}
/*
 * The donor's boot handoff end state: CPU4 on the PLL at the boot rate with
 * its core branch enabled, while the running CPU0 cluster and the CCI keep
 * the firmware's configuration.
 */
static void check_handoff(struct apcc_msm8953 *a, unsigned long cpu0,
                          unsigned long cci)
{
    assert(raw_rate(1) == 652800000);
    assert(raw_rate(0) == cpu0 && raw_rate(2) == cci);
    assert(maps[2].regs[APCC_RCG_CBCR / 4] & APCC_RCG_ENABLE);
    assert(!safety_failures && !a->faulted);
}
int main(void)
{
    struct apcc_msm8953 a;
    struct regmap before[4];
    struct clk_rate_request req;
    struct clk_notifier_data change = { .new_rate = 2016000000 };
    int ret, operations;

    init(&a, false, 1);
    assert(apcc_plan_corner(&a.cpu_plan, 2016000001) == -ERANGE);
    assert(apcc_plan_corner(&a.cpu_plan, 652800001) == 2);
    req = (struct clk_rate_request){ .rate = 652800001, .max_rate = ULONG_MAX,
                                   .best_parent_hw = (void *)1, .best_parent_rate = 123 };
    assert(apcc_determine_rate(&a.output[0].hw, &req) == 0 && req.rate == 1036800000);
    assert(req.best_parent_hw == (void *)1 && req.best_parent_rate == 123);
    req.max_rate = 1000000000;
    assert(apcc_determine_rate(&a.output[0].hw, &req) == -ERANGE);
    assert(apcc_begin(&a, 672000000) == -ERANGE && op_count == 0);
    assert(apcc_begin(&a, 2208000000) == -ERANGE && op_count == 0);

    for (int from = 1; from < 8; from++) for (int to = 1; to < 8; to++) {
        init(&a, false, from);
        assert(apcc_begin(&a, cpu_rates[to]) == 0);
        check_target(&a, to);
        assert(rail >= from && rail >= to && a.pending);
        assert(apcc_set_rate(&a.output[0].hw, cpu_rates[to], 0) == 0);
        apcc_finish(&a, false);
        assert(rail == to && !a.pending);
        for (int i = 1; i < 4; i++) assert((maps[i].regs[1] & 0xa0000000) == 0xa0000000);
    }
    puts("PASS: all 49 stock transitions, both CPUs/CCI, voltage ordering, readback and bounds");

    init(&a, false, 1); a.input_rates[1] = 1036800000;
    assert(apcc_begin(&a, cpu_rates[1]) == 0 && rail == 2);
    apcc_finish(&a, false); check_target(&a, 1); assert(rail == 1);
    puts("PASS: parking source voltage requirement is held even above the target corner");

    for (int cold = 0; cold < 2; cold++) {
        init(&a, cold, 1); memcpy(before, maps, sizeof(maps));
        assert(!(apcc_rate_notify(&a.output[0].nb, PRE_RATE_CHANGE, &change) & NOTIFY_STOP_MASK));
        assert(a.pending);
        apcc_rate_notify(&a.output[0].nb, ABORT_RATE_CHANGE, &change);
        assert(!memcmp(before, maps, sizeof(maps)) && !a.pending && !a.faulted);
        assert(rail == (cold ? 2 : 1) && !safety_failures);
    }
    puts("PASS: warm/cold handoff, external veto ABORT restores full snapshot and old voltage");

    init(&a, false, 1); voltage_fail = 1; memcpy(before, maps, sizeof(maps));
    ret = apcc_rate_notify(&a.output[0].nb, PRE_RATE_CHANGE, &change);
    assert(ret & NOTIFY_STOP_MASK);
    assert(!memcmp(before, maps, sizeof(maps)) && rail == 1 && !a.pending);
    puts("PASS: voltage rejection vetoes PRE without hardware writes");

    for (int scenario = 0; scenario < 3; scenario++) {
        bool cold = scenario == 2;
        int from = scenario == 0 ? 7 : 1;
        int to = scenario == 0 ? 1 : 7;
        init(&a, cold, from);
        assert(apcc_begin(&a, cpu_rates[to]) == 0); operations = op_count;
        for (int n = 1; n <= operations; n++) {
            init(&a, cold, from); memcpy(before, maps, sizeof(maps)); fail_op = n;
            assert(apcc_begin(&a, cpu_rates[to]) < 0);
            assert(!memcmp(before, maps, sizeof(maps)) && rail == (cold ? 2 : from));
            assert(!a.pending && !a.faulted && !safety_failures);
        }
        printf("PASS: every one-shot MMIO fault in scenario %d (%d positions) restores both clusters/CCI\n",
               scenario, operations);
    }

    init(&a, false, 1); fail_map = 2;
    assert(apcc_begin(&a, cpu_rates[7]) < 0 && a.faulted && rail == 7);
    operations = op_count;
    assert(apcc_begin(&a, cpu_rates[1]) == -EIO && operations == op_count);
    assert(!safety_failures);
    puts("PASS: persistent rollback failure retains safe voltage and blocks further DVFS");

    init(&a, false, 7); memcpy(before, maps, sizeof(maps)); lock_fail_rate = cpu_rates[1];
    assert(apcc_begin(&a, cpu_rates[1]) == -ETIMEDOUT);
    assert(!memcmp(before, maps, sizeof(maps)) && rail == 7 && !safety_failures);
    puts("PASS: PLL lock timeout restores original integer L and all muxes");

    for (int test = 0; test < 3; test++) {
        bool cold = test == 2;
        init(&a, cold, 7); memcpy(before, maps, sizeof(maps));
        drop_map = test == 0 ? 2 : 0;
        drop_reg = test == 0 ? APCC_RCG_CFG : test == 1 ? APCC_PLL_L : APCC_PLL_MODE;
        drop_nth = cold ? 3 : 1;
        assert(apcc_begin(&a, cpu_rates[1]) == -EIO);
        assert(!memcmp(before, maps, sizeof(maps)) && !a.faulted && !safety_failures);
        assert(rail == (cold ? 2 : 7));
    }
    puts("PASS: silent RCG/L/output-enable write loss is detected and rolled back");

    init(&a, false, 1);
    assert(apcc_begin(&a, cpu_rates[7]) == 0);
    drop_map = 0; drop_reg = APCC_PLL_L; drop_nth = 1;
    apcc_finish(&a, true);
    assert(a.faulted && rail == 7 && !a.pending && !safety_failures);
    puts("PASS: silent rollback L write loss is detected before voltage can fall");

    init(&a, false, 7);
    assert(apcc_begin(&a, cpu_rates[1]) == 0);
    voltage_fail = 1; apcc_finish(&a, false);
    check_target(&a, 1); assert(rail == 7 && !a.pending);
    puts("PASS: failed POST voltage decrease keeps the higher safe vote");

    for (int cold = 0; cold < 2; cold++) {
        init(&a, cold, 7);
        if (cold) {
            maps[2].regs[1] = 0; /* actual firmware CPU4 XO handoff */
            maps[2].regs[APCC_RCG_CBCR / 4] = 0;
        }
        apcc_power.enabled = false;
        assert(apcc_handoff(&a) == 0);
        if (cold)
            check_handoff(&a, 600000000, 300000000);
        else
            check_handoff(&a, 652800000, 261120000);
        assert(rail == (cold ? 2 : 7) && rail_enables == 1 && apcc_power.enabled);
        assert(apcc_handoff(&a) == 0 && rail_enables == 1);
    }
    puts("PASS: warm and actual GPLL0/XO cold boot handoff, CPU4 branch enable, idempotent rail pin");

    /*
     * The handoff must not touch the mux of the running CPU0 cluster or the
     * live CCI: only the PLL and the CPU4 alias1 mux may change.
     */
    init(&a, true, 1);
    maps[2].regs[1] = 0;
    maps[2].regs[APCC_RCG_CBCR / 4] = 0;
    struct regmap cpu0_cfg = maps[1], cci_cfg = maps[3];
    assert(apcc_handoff(&a) == 0);
    assert(!memcmp(cpu0_cfg.regs, maps[1].regs, sizeof(cpu0_cfg.regs)) &&
           !memcmp(cci_cfg.regs, maps[3].regs, sizeof(cci_cfg.regs)));
    check_handoff(&a, 600000000, 300000000);
    puts("PASS: boot handoff leaves the running CPU0 mux and the CCI untouched");

    init(&a, true, 1); maps[2].regs[1] = 0;
    maps[2].regs[APCC_RCG_CBCR / 4] = 0;
    memcpy(before, maps, sizeof(maps));
    assert(apcc_handoff(&a) == 0); operations = op_count;
    for (int n = 1; n <= operations; n++) {
        init(&a, true, 1); maps[2].regs[1] = 0;
        maps[2].regs[APCC_RCG_CBCR / 4] = 0;
        fail_op = n;
        assert(apcc_handoff(&a) < 0);
        assert(!memcmp(before, maps, sizeof(maps)) && !a.faulted && !safety_failures);
    }
    printf("PASS: every cold split-handoff MMIO failure (%d positions) preserves/restores boot state\n", operations);

    init(&a, true, 1); maps[2].regs[1] = 0;
    maps[2].regs[APCC_RCG_CBCR / 4] = 0;
    memcpy(before, maps, sizeof(maps));
    drop_map = 2; drop_reg = APCC_RCG_CBCR; drop_nth = 1;
    assert(apcc_handoff(&a) == -EIO && !memcmp(before, maps, sizeof(maps)));
    assert(!a.faulted && !safety_failures);
    puts("PASS: lost CPU4 branch-enable write detected and complete split boot state restored");

    for (int bad = 0; bad < 4; bad++) {
        init(&a, false, 1);
        if (bad == 0) maps[0].regs[APCC_PLL_USER / 4] |= APCC_PLL_ALPHA_EN;
        if (bad == 1) maps[0].regs[0] = BIT(1);
        if (bad == 2) maps[2].regs[1] = 7 << 8;
        if (bad == 3) maps[0].regs[APCC_PLL_L / 4] = 120;
        memcpy(before, maps, sizeof(maps));
        assert(apcc_handoff(&a) < 0 && !memcmp(before, maps, sizeof(maps)));
    }
    puts("PASS: fractional/partial/unknown-source/above-stock handoff states fail without clock writes");

    init(&a, true, 1); apcc_power.enabled = false; power_fail = 1;
    memcpy(before, maps, sizeof(maps));
    assert(apcc_handoff(&a) == -EIO && !memcmp(before, maps, sizeof(maps)));
    assert(!apcc_power.enabled && rail_enables == 0);
    assert(apcc_handoff(&a) == 0 && rail_enables == 1);
    puts("PASS: failed rail enable prevents clock writes and retry enables exactly once");

    init(&a, true, 1); apcc_power.mx_voted = false;
    assert(apcc_handoff(&a) == -EIO && op_count == 0);
    assert(apcc_begin(&a, cpu_rates[1]) == -EIO && op_count == 0);
    apcc_power.mx_voted = true; apcc_power.mx_active = false;
    assert(apcc_handoff(&a) == -EIO && op_count == 0);
    puts("PASS: absent MX floor/activation blocks handoff and DVFS before MMIO");

    init(&a, false, 1); fail_map = 2;
    assert(apcc_begin(&a, cpu_rates[7]) < 0 && apcc_power.faulted);
    a.faulted = false; operations = op_count;
    assert(apcc_handoff(&a) == -EIO && op_count == operations && rail == 7);
    puts("PASS: failed rollback latches across fresh per-probe state; no retry can drop its safe vote");

    for (int failure = 1; failure <= 5; failure++) {
        init(&a, true, 1); memset(&apcc_power, 0, sizeof(apcc_power));
        power_fail = failure;
        assert(apcc_pin_power(&a) == -EIO);
        assert(op_count == 0);
        power_fail = 0;
        assert(apcc_pin_power(&a) == 0 && apcc_pin_power(&a) == 0);
        assert(supply_gets == 1 && mx_attaches - mx_detaches == 1 && mx_refs == 1 && mx_votes == 1);
        assert(mx_detaches == (failure == 4));
        assert(apcc_power.mx_active && apcc_power.mx_voted);
    }
    puts("PASS: rail/MX acquisition, attach, runtime-resume and SVS-vote failures retry without ref leaks");

    init(&a, true, 1); memset(&apcc_power, 0, sizeof(apcc_power));
    maps[2].regs[1] = 0; maps[2].regs[APCC_RCG_CBCR / 4] = 0;
    assert(apcc_pin_power(&a) == 0 && apcc_handoff(&a) == 0);
    /* Model discarding probe-local state after a later CCF registration error. */
    struct apcc_msm8953 retry = a;
    retry.supply = NULL; retry.corner = 0;
    domain = &retry;
    for (int i = 0; i < APCC_NUM_CLOCKS; i++) retry.output[i].apcc = &retry;
    assert(apcc_pin_power(&retry) == 0 && retry.corner == 2);
    assert(apcc_handoff(&retry) == 0); check_handoff(&retry, 600000000, 300000000);
    assert(supply_gets == 1 && rail_enables == 1 && mx_attaches == 1 && mx_refs == 1 && mx_votes == 1);
    puts("PASS: fresh probe after publication failure reuses powered CPU/PLL state and all power pins");

    for (int failure = 2; failure <= 3; failure++) {
        memset(apcc_inputs, 0, sizeof(apcc_inputs));
        memset(enable_refs, 0, sizeof(enable_refs));
        memset(exclusive_refs, 0, sizeof(exclusive_refs));
        memset(gets, 0, sizeof(gets));
        acquire_op = 0; acquire_fail = failure;
        assert(apcc_pin_inputs(NULL, a.input_rates) == -EIO);
        assert(enable_refs[0] == (failure == 3));
        acquire_fail = 0;
        assert(apcc_pin_inputs(NULL, a.input_rates) == 0);
        assert(apcc_pin_inputs(NULL, a.input_rates) == 0);
        for (int i = 0; i < 3; i++) assert(enable_refs[i] == 1 && exclusive_refs[i] == 1);
        assert(gets[0] == (failure == 2 ? 2 : 1) && gets[1] == 1 && gets[2] == 1);
    }
    puts("PASS: probe retries reuse lifetime input pins; failed acquisition cannot disable a live source");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="msm8953-apcc-", dir="/tmp/opencode") as tmp:
        path = Path(tmp)
        (path / "test.c").write_text(mock + constants + "\n" + state +
                                    inputs + core[:plan_end] + io + core[plan_end:] +
                                    pins + tests)
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                        "-Werror", "-Wno-sign-compare", "-Wno-unused-parameter",
                        str(path / "test.c"), "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    main()
