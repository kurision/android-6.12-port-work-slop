#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-test the SPM rail's voltage/selector/step-rate arithmetic.

Extracts the real functions from drivers/regulator/qcom-msm8953-spm-regulator.c
and drives them against a tiny regmap mock.  The expected FTS2 step rate
(1200 uV/us) and initial voltage (870000 uV) come from the donor boot log
out-lto/dmesg-boot.txt:259, so a passing test cross-checks the ported
arithmetic against observed donor hardware behaviour.  It is not a hardware,
probe or regmap test.

Also checks that probe selects the 16-bit extended SPMI regmap API; this is
a source-level regression guard, not a test of bus transactions.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
SOURCE = (REPO / "drivers/regulator/qcom-msm8953-spm-regulator.c").read_text()

regmap_config = re.search(r"static const struct regmap_config "
                          r"spmi_regulator_regmap_config = \{.*?\n\};",
                          SOURCE, re.S).group(0)
assert re.search(r"\.reg_bits\s*=\s*16\s*,", regmap_config)
assert "devm_regmap_init_spmi_ext(" in SOURCE
assert "devm_regmap_init_spmi_base(" not in SOURCE

voltage_range = re.search(r"struct voltage_range \{.*?\n\};", SOURCE, re.S).group(0)
enums = re.search(r"enum qpnp_regulator_uniq_type \{.*?\n\};", SOURCE, re.S).group(0)
constants = "\n".join(re.findall(r"^#define (?:QPNP|SPM_REGULATOR|FTS2P5|ULT_SMPS)\S+.*$",
                                SOURCE, re.M))
ranges = SOURCE[SOURCE.index("static const struct voltage_range fts2_range0"):
                SOURCE.index("#define QPNP_SMPS_REG_TYPE")]
conversions = SOURCE[SOURCE.index("static int qcom_spm_reg_uv_to_vlevel"):
                     SOURCE.index("static int qpnp_smps_read_voltage")]
step_rate = SOURCE[SOURCE.index("static int qpnp_smps_init_step_rate"):
                   SOURCE.index("static int qpnp_smps_check_constraints")]

mock = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef unsigned int uint;

#define max(a, b) ((a) > (b) ? (a) : (b))
#define DIV_ROUND_UP(a, b) (((a) + (b) - 1) / (b))
#define roundup(x, y) ((((x) + ((y) - 1)) / (y)) * (y))

struct regmap { int unused; };

struct qcom_spm_reg {
	struct regmap			*regmap;
	const struct voltage_range	*range;
	enum qpnp_regulator_uniq_type	regulator_type;
	u16				spmi_base_addr;
	int				step_rate;
};

static struct regmap fake_regmap;
static unsigned int step_ctrl_value;
static unsigned int step_ctrl_reads;

static int regmap_read(struct regmap *regmap, unsigned int reg, unsigned int *val)
{
	(void)regmap;
	assert(reg == 0x2000 + QPNP_SMPS_REG_STEP_CTRL);
	step_ctrl_reads++;
	*val = step_ctrl_value;
	return 0;
}
'''

test = r'''
static void check_roundtrip(struct qcom_spm_reg *reg, int uv, int vlevel)
{
	assert(qcom_spm_reg_uv_to_vlevel(reg, uv) == vlevel);
	assert(qcom_spm_reg_vlevel_to_uv(reg, vlevel) == uv);
}

static void set_type(struct qcom_spm_reg *reg,
		     enum qpnp_regulator_uniq_type type,
		     const struct voltage_range *range)
{
	reg->regulator_type = type;
	reg->range = range;
}

static void check_range(const struct voltage_range *r)
{
	assert(r->step_uv > 0);
	assert(r->max_uv > r->set_point_min_uv);
	assert(r->set_point_min_uv >= r->min_uv);
	assert((r->set_point_min_uv - r->min_uv) % r->step_uv == 0);
	assert((r->max_uv - r->min_uv) % r->step_uv == 0);
}

int main(void)
{
	struct qcom_spm_reg reg = { .regmap = &fake_regmap, .spmi_base_addr = 0x2000 };

	/* Every donor range is well formed and grid-aligned. */
	check_range(&fts2_range0);
	check_range(&fts2_range1);
	check_range(&fts2p5_range0);
	check_range(&fts2p5_range1);
	check_range(&fts426_range);
	check_range(&hfs430_range);
	check_range(&ult_hf_range0);
	check_range(&ult_hf_range1);
	check_range(&hf_range0);
	check_range(&hf_range1);

	/* PM8953 S5 is an FTS2-family LV-range buck (donor dmesg-boot.txt:259). */
	set_type(&reg, QPNP_TYPE_FTS2, &fts2_range0);
	check_roundtrip(&reg, 870000, 174);
	/* VSET 0 is 0 V for FTS2; the usable 350 mV floor is level 70. */
	check_roundtrip(&reg, 350000, 70);
	check_roundtrip(&reg, 1275000, 255);
	assert(qcom_spm_reg_vlevel_to_selector(&reg, 70) == 0);
	assert(qcom_spm_reg_vlevel_to_selector(&reg, 174) == 104);

	set_type(&reg, QPNP_TYPE_FTS2p5, &fts2p5_range0);
	check_roundtrip(&reg, 870000, 158);
	assert(qcom_spm_reg_vlevel_to_uv(&reg, 0) == 80000);

	/* FTS426/HFS430 encode millivolts and round up onto their own grid. */
	set_type(&reg, QPNP_TYPE_FTS426, &fts426_range);
	assert(qcom_spm_reg_uv_to_vlevel(&reg, 872000) == 872);
	assert(qcom_spm_reg_uv_to_vlevel(&reg, 868000) == 868);
	assert(qcom_spm_reg_uv_to_vlevel(&reg, 870001) == 872);
	assert(qcom_spm_reg_vlevel_to_uv(&reg, 872) == 872000);

	set_type(&reg, QPNP_TYPE_HFS430, &hfs430_range);
	assert(qcom_spm_reg_uv_to_vlevel(&reg, 872000) == 872);
	assert(qcom_spm_reg_vlevel_to_selector(&reg, 872) ==
	       (872000 / 8000) - ((320000 - 0) / 8000));

	set_type(&reg, QPNP_TYPE_HF, &hf_range0);
	check_roundtrip(&reg, 375000, 0);
	check_roundtrip(&reg, 1562500, 95);

	set_type(&reg, QPNP_TYPE_ULT_HF, &ult_hf_range1);
	/* Range-1 ULT VSET keeps bit 5 set and drops it again on the way back. */
	assert(qcom_spm_reg_uv_to_vlevel(&reg, 1000000) ==
	       ((DIV_ROUND_UP(1000000 - 750000, 25000) & 0x1F) | ULT_SMPS_RANGE_SPLIT));
	assert(qcom_spm_reg_vlevel_to_uv(&reg, 0x60 | 10) == 1000000);

	/* FTS2 step rate: donor PM8953 S5 reports 1200 uV/us at delay=3, step=0. */
	set_type(&reg, QPNP_TYPE_FTS2, &fts2_range0);
	step_ctrl_value = 0x03;
	assert(qpnp_smps_init_step_rate(&reg) == 0);
	assert(reg.step_rate == 1200);
	step_ctrl_value = 0x00;
	assert(qpnp_smps_init_step_rate(&reg) == 0);
	assert(reg.step_rate == 9600);
	step_ctrl_value = 0x08; /* step=1, delay=0 */
	assert(qpnp_smps_init_step_rate(&reg) == 0);
	assert(reg.step_rate == 19200);

	/* HF uses a different step delay and margin but the same clock rate. */
	set_type(&reg, QPNP_TYPE_HF, &hf_range0);
	step_ctrl_value = 0x03;
	assert(qpnp_smps_init_step_rate(&reg) == 0);
	assert(reg.step_rate == 1200);

	assert(step_ctrl_reads == 4 && reg.step_rate > 0);
	puts("PASS: FTS2-family/HF voltage, selector and step-rate arithmetic");
	return 0;
}
'''

program = (voltage_range + "\n" + enums + "\n" + constants + "\n" + ranges + "\n" +
           mock + conversions + step_rate + test)

with tempfile.TemporaryDirectory(prefix="msm8953-spm-regulator-", dir="/tmp/opencode") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(program)
    subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                    "-Werror", str(path / "test.c"), "-o", str(path / "test")],
                   check=True)
    subprocess.run([str(path / "test")], check=True)
