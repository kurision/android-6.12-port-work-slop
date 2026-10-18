#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-test the real APCC corner plan lookup and rail voting; no kernel or
hardware test. Extracts the shipped functions out of
drivers/clk/qcom/apcc-msm8953.c and links them against host mocks.
"""
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
source = (REPO / "drivers/clk/qcom/apcc-msm8953.c").read_text()

# The real state structs and the real corner/vote logic, copied verbatim.
structs = source[source.index("/* Ascending rate to corner table"):
                 source.index("/* Parent 0 is the local APCS PLL")]
plan = source[source.index("static int apcc_plan_corner"):
              source.index("/* Programs the highest voted corner.")]
commit = source[source.index("static int apcc_vdd_commit"):
                source.index("static int apcc_clk_determine_rate")]
functions = plan + commit

mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>

typedef uint32_t u32;
typedef unsigned long ulong;
#define BIT(n) (1U << (n))
#define max(a, b) ((a) > (b) ? (a) : (b))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define container_of(ptr, type, member) \
	((type *)((char *)(ptr) - offsetof(type, member)))
#define offsetof(t, m) __builtin_offsetof(t, m)

/* APCC_NUM_CLOCKS from include/dt-bindings/clock/qcom,apcc-msm8953.h */
#define APCC_CPU0_CLK	0
#define APCC_CPU4_CLK	1
#define APCC_CCI_CLK	2
#define APCC_NUM_CLOCKS	3

struct clk_hw { int unused; };
struct clk { int unused; };
struct clk_alpha_pll { int unused; };
struct clk_regmap_mux_div { int unused; };
struct platform_device { int unused; };
struct device { int unused; };
struct notifier_block { int unused; };
struct mutex { int unused; };
struct regulator { int unused; };

static void mutex_lock(struct mutex *m) { (void)m; }
static void mutex_unlock(struct mutex *m) { (void)m; }

static int rail = -1;		/* last programmed corner, -1 = never */
static int rail_error;		/* when set, regulator_set_voltage fails */
static int regulator_set_voltage(struct regulator *r, int min, int max)
{
	(void)r;
	assert(min == max);
	if (rail_error)
		return -EIO;
	rail = min;
	return 0;
}
'''

tests = r'''
/* The fused bin 2 stock plan from the donor DTS. */
static const unsigned long cpu_rates[] = {
	0, 652800000, 1036800000, 1401600000, 1689600000,
	1804800000, 1958400000, 2016000000,
};
static const int cpu_corners[] = { 0, 1, 2, 3, 4, 5, 6, 7 };

int main(void)
{
	struct apcc_plan plan = {
		.rates = (unsigned long *)cpu_rates,
		.corners = (int *)cpu_corners,
		.num = ARRAY_SIZE(cpu_rates),
	};
	struct apcc_msm8953 apcc = { .corner = -1 };
	struct apcc_vdd *cpu0 = &apcc.vdd[APCC_CPU0_CLK];
	struct apcc_vdd *cpu4 = &apcc.vdd[APCC_CPU4_CLK];
	struct apcc_vdd *cci = &apcc.vdd[APCC_CCI_CLK];
	int corner, i;

	for (i = 0; i < APCC_NUM_CLOCKS; i++) {
		apcc.vdd[i].apcc = &apcc;
		apcc.vdd[i].plan = &plan;
	}

	/* Exact rate, and a rate that only the next plan entry covers. */
	assert(apcc_plan_corner(&plan, 652800000, &corner) == 0 && corner == 1);
	assert(apcc_plan_corner(&plan, 652800001, &corner) == 0 && corner == 2);
	assert(apcc_plan_corner(&plan, 2016000000, &corner) == 0 && corner == 7);
	assert(apcc_plan_corner(&plan, 0, &corner) == 0 && corner == 0);

	/* Above the fused plan the driver must refuse rather than guess. */
	assert(apcc_plan_corner(&plan, 2016000001, &corner) == -ERANGE);

	/* First vote programs the rail. */
	assert(apcc_vdd_vote(cpu0, 1401600000) == 0 && rail == 3);

	/* A slower cluster must not pull the shared rail down. */
	assert(apcc_vdd_vote(cpu4, 652800000) == 0);
	assert(rail == 3 && cpu4->corner == 1);

	/* Releasing the higher voter drops the rail to the remaining one. */
	apcc_vdd_unvote(cpu0);
	assert(rail == 1 && cpu0->corner == 0);

	/* An unvote that cannot program the rail keeps the old corner. */
	rail_error = 1;
	apcc_vdd_unvote(cpu4);
	assert(cpu4->corner == 1 && rail == 1);
	rail_error = 0;

	/* CCI on the same rail raises it again. */
	assert(apcc_vdd_vote(cci, 2016000000) == 0);
	assert(rail == 7);

	/* An above-plan rate votes nothing and touches no hardware. */
	assert(apcc_vdd_vote(cpu0, 2016000001) == -ERANGE && rail == 7);
	assert(cpu0->corner == 0);

	/* Releasing CCI leaves the rail on the remaining CPU voter. */
	apcc_vdd_unvote(cci);
	assert(rail == 1 && cci->corner == 0);

	/* A regulator failure rolls the vote back instead of keeping it. */
	rail_error = 1;
	assert(apcc_vdd_vote(cpu0, 2016000000) == -EIO);
	rail_error = 0;
	assert(cpu0->corner == 0 && rail == 1);

	puts("PASS: plan lookup, above-plan refusal, shared-rail voting, rollback");
	return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="msm8953-apcc-", dir="/tmp/opencode") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(mock + structs + functions + tests)
    subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                    "-Werror", str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)