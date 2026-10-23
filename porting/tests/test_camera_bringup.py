#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host checks for run368camera's probe and firmware-staging failures."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAM = ROOT / "drivers/media/platform/msm/camera"


class CameraBringup(unittest.TestCase):
    def test_clock_release_indexes_clock_array(self):
        source = (CAM / "common/cam_soc_api.c").read_text()
        functions = "\n".join(re.search(
            r"^(?:static )?int " + name + r"\([^;{]*\)\n\{.*?^}",
            source, re.M | re.S)[0] for name in (
                "msm_camera_put_clk_info_internal", "legacy_msm_camera_put_clk_info_and_rates"))
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#define CDBG(...) ((void)0)
struct device { int unused; };
struct platform_device { struct device dev; };
struct clk { int unused; };
struct msm_cam_clk_info { int unused; };
static int released, freed;
static void devm_clk_put(struct device *dev,struct clk *p) { assert(p); ++released; }
static void devm_kfree(struct device *dev,void *p) { if (p) { ++freed; free(p); } }
'''
        harness += functions + r'''
int main(void) {
    struct platform_device p={0}; struct clk c;
    for (int rates=0;rates<2;rates++) for (int count=0;count<=9;count++) {
        struct msm_cam_clk_info *info=calloc(count+1,sizeof(*info));
        struct clk **clocks=calloc(count+1,sizeof(*clocks));
        uint32_t **table=calloc(2,sizeof(*table));
        table[0]=calloc(1,sizeof(**table)); table[1]=calloc(1,sizeof(**table));
        int expected=0;
        for (int i=0;i<count;i++) if (i%3) { clocks[i]=&c; ++expected; }
        released=freed=0;
        if (rates) {
            assert(!legacy_msm_camera_put_clk_info_and_rates(&p,&info,&clocks,&table,2,count));
            assert(!table && freed==5);
        } else {
            assert(!msm_camera_put_clk_info_internal(&p.dev,&info,&clocks,count));
            assert(freed==2); free(table[0]); free(table[1]); free(table);
        }
        assert(!info && !clocks && released==expected);
    }
}
'''
        with tempfile.TemporaryDirectory() as folder:
            cfile, exe = Path(folder) / "clock-put.c", Path(folder) / "clock-put"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=5)

    def test_csi_nodes_describe_all_sensor_routes(self):
        source = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi").read_text()
        header = (ROOT / "include/dt-bindings/clock/qcom,gcc-msm8953.h").read_text()
        for kind, addresses, irqs, version, count in (
                ("csid", (0x1b30000, 0x1b30400, 0x1b30800), (51, 52, 153), "3.5.1", 9),
                ("csiphy", (0x1b34000, 0x1b35000, 0x1b36000), (78, 79, 315), "3.5", 6)):
            nodes = re.findall(r"qcom," + kind + r"@([0-9a-f]+)\s*{([^}]+)};", source)
            self.assertEqual(len(nodes), 3)
            for slot, (address, node) in enumerate(nodes):
                with self.subTest(kind=kind, slot=slot):
                    self.assertEqual(int(address, 16), addresses[slot])
                    properties = dict(re.findall(r'([\w,\-]+)\s*=\s*([^;]+);', node))
                    self.assertEqual(properties["cell-index"], f"<{slot}>")
                    self.assertEqual(properties["compatible"], f'"qcom,{kind}-v{version}", "qcom,{kind}"')
                    self.assertIn(properties["status"], ('"ok"', '"okay"'))
                    self.assertEqual(properties["interrupts"], f'<GIC_SPI {irqs[slot]} IRQ_TYPE_LEVEL_HIGH>')
                    self.assertEqual(properties["interrupt-names"], f'"{kind}"')
                    self.assertIn(hex(addresses[slot]), properties["reg"])
                    self.assertIn(f'"{kind}"', properties["reg-names"])
                    clocks = re.findall(r'<&gcc (\w+)>', properties["clocks"])
                    self.assertEqual(len(clocks), count)
                    self.assertEqual(len(re.findall(r'"[^"]+"', properties["clock-names"])), count)
                    self.assertEqual(len(properties["qcom,clock-rates"].strip('<> ').split()), count)
                    for clock in clocks:
                        self.assertRegex(header, r'(?m)^#define\s+' + clock + r'\b')
                    if kind == "csid":
                        self.assertEqual(properties["qcom,mipi-csi-vdd-supply"], '<&pm8953_s3>')

    def test_csid_voltage_matches_fixed_s3_and_provider_steps(self):
        board = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts").read_text()
        rail = re.search(r'pm8953_s3: s3\s*{([^}]+)};', board)[1]
        low = int(re.search(r'regulator-min-microvolt = <(\d+)>', rail)[1])
        high = int(re.search(r'regulator-max-microvolt = <(\d+)>', rail)[1])
        self.assertEqual(low, high)
        source = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi").read_text()
        requests = re.findall(r'qcom,csi-vdd-voltage = <(\d+)>', source)
        self.assertEqual(len(requests), 3)
        for request in requests:
            self.assertEqual(int(request), low)
        provider = (ROOT / "drivers/regulator/qcom_smd-regulator.c").read_text()
        pm8953 = provider.split('rpm_pm8953_regulators[] = {', 1)[1].split('\n};', 1)[0]
        descriptor = re.search(r'"s3"[^\n]+&(\w+)', pm8953)[1]
        desc = provider.split(f'struct regulator_desc {descriptor} = {{', 1)[1].split('\n};', 1)[0]
        base, first, last, step = map(int, re.search(
            r'REGULATOR_LINEAR_RANGE\((\d+), (\d+), (\d+), (\d+)\)', desc).groups())
        self.assertIn(low, range(base, base + (last - first + 1) * step, step))
        self.assertNotIn(1225000, range(base, base + (last - first + 1) * step, step))

    def test_csi_irqs_are_not_enabled_during_probe(self):
        for kind, probe_name in (("csid", "csid_probe"), ("csiphy", "csiphy_probe")):
            with self.subTest(kind=kind):
                source = (CAM / f"sensor/{kind}/msm_{kind}.c").read_text()
                probe = re.search(r"^static int " + probe_name + r"\([^;{]*\)\n\{.*?^}",
                                  source, re.M | re.S)[0]
                request = re.search(r"rc = legacy_msm_camera_register_irq\(.*?;",
                                    probe, re.S)[0]
                self.assertNotIn("legacy_msm_camera_enable_irq(", probe)
                harness = r'''
#include <assert.h>
#define IRQF_TRIGGER_RISING 1
#define IRQF_NO_AUTOEN 0x80000
struct csi_device { void *irq; };
static int handler_calls;
static void msm_csid_irq(void) { ++handler_calls; }
static void msm_csiphy_irq(void) { ++handler_calls; }
static int legacy_msm_camera_register_irq(void *pdev, void *irq,
    void (*handler)(void), int flags, const char *name, void *state)
{
    if (!(flags & IRQF_NO_AUTOEN)) handler();
    return 0;
}
int main(void) {
    struct csi_device dev={0}, *new_csid_dev=&dev, *new_csiphy_dev=&dev;
    void *pdev=0;
    int rc;
'''
                harness += request + r'''
    assert(rc==0 && handler_calls==0);
}
'''
                with tempfile.TemporaryDirectory() as folder:
                    cfile, exe = Path(folder) / "csi-irq.c", Path(folder) / "csi-irq"
                    cfile.write_text(harness)
                    subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                                    "-o", str(exe)], check=True)
                    subprocess.run([str(exe)], check=True, timeout=5)

    def test_cci_provider_ready_for_synchronous_children(self):
        source = (CAM / "sensor/cci/msm_cci.c").read_text()
        probe = re.search(r"^static int msm_cci_probe\([^;{]*\)\n\{.*?^}",
                          source, re.M | re.S)[0]
        block = probe.split("\n\tnew_cci_dev->cci_state = CCI_STATE_DISABLED;", 1)[1]
        block = "\tnew_cci_dev->cci_state = CCI_STATE_DISABLED;" + block.split(
            '\n\tCDBG("%s cci subdev', 1)[0]
        # Model the previous order as a negative control, retaining the real setup.
        populate = re.search(r"\trc = of_platform_populate.*?\n\t\tpr_err\([^;]+;",
                             block, re.S)[0]
        old_block = populate + "\n" + block.replace(populate, "")
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#define MASTER_MAX 2
#define CCI_STATE_DISABLED 0
#define pr_err(...) (++errors)
struct v4l2_subdev { int unused; };
struct device { void *of_node; };
struct platform_device { struct device dev; };
struct cci_device {
    struct { struct v4l2_subdev sd; } msm_sd;
    int cci_state;
    void *write_wq[MASTER_MAX];
};
static struct v4l2_subdev *g_cci_subdev, *cached;
static struct cci_device *active;
static bool child_ready;
static int workqueues, populate_rc, errors, child_calls;
static void *create_singlethread_workqueue(const char *name) {
    assert(!strcmp(name,"msm_cci_wq"));
    return (void *)(size_t)++workqueues;
}
static int of_platform_populate(void *node,void *matches,void *aux,struct device *dev) {
    ++child_calls;
    cached=g_cci_subdev;
    child_ready=cached==&active->msm_sd.sd && active->cci_state==CCI_STATE_DISABLED;
    for (int i=0;i<MASTER_MAX;i++) child_ready=child_ready && active->write_wq[i];
    return populate_rc;
}
'''
        harness += "static void corrected(struct platform_device *pdev, struct cci_device *new_cci_dev) {\nint rc, i;\n" + block + "\n}\n"
        harness += "static void previous(struct platform_device *pdev, struct cci_device *new_cci_dev) {\nint rc, i;\n" + old_block + "\n}\n"
        harness += r'''
int main(void) {
    for (int old=0;old<2;old++) for (int failed_populate=0;failed_populate<2;failed_populate++) {
        struct platform_device p={0}; struct cci_device c={.cci_state=-1};
        active=&c; g_cci_subdev=NULL; cached=NULL; child_ready=false;
        workqueues=errors=child_calls=0; populate_rc=failed_populate ? -ENOMEM : 0;
        if (old) previous(&p,&c); else corrected(&p,&c);
        assert(child_calls==1 && workqueues==MASTER_MAX);
        assert(errors==failed_populate);
        assert(g_cci_subdev==&c.msm_sd.sd);
        if (old) assert(!cached && !child_ready);
        else assert(cached==g_cci_subdev && child_ready);
    }
}
'''
        with tempfile.TemporaryDirectory() as folder:
            cfile, exe = Path(folder) / "cci-order.c", Path(folder) / "cci-order"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), "-Wall", "-Werror",
                            str(cfile), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=5)

    def test_sensor_slots_have_complete_resources(self):
        source = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi").read_text()
        for slot, mclk in enumerate((0, 2, 1)):
            with self.subTest(slot=slot):
                node = re.search(r"\bqcom,camera@" + str(slot) + r"\s*{([^}]+)};",
                                 source, re.S)[1]
                properties = dict(re.findall(r'([\w,\-]+)\s*=\s*([^;]+);', node))
                for prop in ("cell-index", "reg", "qcom,csiphy-sd-index", "qcom,csid-sd-index"):
                    self.assertEqual(properties[prop].strip(), f"<{slot}>")
                self.assertEqual(properties["compatible"], '"qcom,camera"')
                self.assertIn(properties["status"], ('"okay"', '"ok"'))
                self.assertEqual(properties["clock-names"], '"cam_src_clk", "cam_clk"')
                self.assertEqual(properties["qcom,clock-rates"], '<24000000 0>')
                self.assertEqual(properties["qcom,gpio-reset"], '<1>')
                self.assertEqual(properties["pinctrl-names"], '"cam_default", "cam_suspend"')
                self.assertIn(f'&cam_sensor_mclk{mclk}_default', properties["pinctrl-0"])
                self.assertIn(f'&cam_sensor_mclk{mclk}_sleep', properties["pinctrl-1"])
                self.assertIn(f'MCLK{mclk}_CLK_SRC', properties["clocks"])
                self.assertIn(f'GCC_CAMSS_MCLK{mclk}_CLK', properties["clocks"])
                names = re.findall(r'"([^"]+)"', properties["qcom,cam-vreg-name"])
                for name in names:
                    self.assertIn(name + "-supply", properties)
                for prop in ("min-voltage", "max-voltage", "op-mode"):
                    self.assertEqual(len(properties["qcom,cam-vreg-" + prop].strip('<> ').split()),
                                     len(names))

    def test_camera_clock_sources_match_mclk_branches(self):
        source = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi").read_text()
        clocks = re.findall(r'clocks\s*=\s*<&gcc (\w+)>\s*,\s*<&gcc GCC_CAMSS_MCLK([012])_CLK>;',
                            source)
        self.assertEqual(len(clocks), 9)  # Six EEPROMs and three sensor slots.
        for clock, mclk in clocks:
            self.assertEqual(clock, f"MCLK{mclk}_CLK_SRC")
        gcc = (ROOT / "drivers/clk/qcom/gcc-msm8953.c").read_text()
        for mclk in range(3):
            branch = gcc.split(f'static struct clk_branch gcc_camss_mclk{mclk}_clk =', 1)[1]
            self.assertIn(f'&mclk{mclk}_clk_src.clkr.hw', branch.split('\n};', 1)[0])

    def test_sensor_slot_publication_and_failed_clock_cleanup(self):
        source = (CAM / "sensor/msm_sensor_driver.c").read_text()
        def extract(name):
            return re.search(r"^static [^\n]*\b" + name + r"\([^;{]*\)\n\{.*?^}",
                             source, re.M | re.S)[0]
        self.assertNotIn("g_sctrl[", extract("msm_sensor_driver_parse"))
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#define GFP_KERNEL 0
#define I2C_FUNC_I2C 1
#define MSM_CAMERA_PLATFORM_DEVICE 1
#define MSM_CAMERA_I2C_DEVICE 2
#define pr_err(...) ((void)0)
#define CDBG(...) ((void)0)
struct device { void *of_node; };
struct platform_device { struct device dev; void *data; int id; };
struct i2c_client { struct device dev; void *data, *adapter; const char *name; };
struct msm_camera_gpio_conf { void *gpio_num_info, *cam_gpio_req_tbl, *cam_gpio_set_tbl; };
struct msm_camera_power_ctrl_t {
    struct msm_camera_gpio_conf *gpio_conf;
    void *cam_vreg, *clk_info, *clk_ptr;
    size_t clk_info_size;
    struct device *dev;
};
struct board { struct msm_camera_power_ctrl_t power_info; void *sensor_info; };
struct sensor_client { void *cci_client; struct i2c_client *client; };
struct msm_sensor_ctrl_t {
    struct board *sensordata;
    struct sensor_client *sensor_i2c_client;
    void *msm_sensor_mutex, *of_node;
    struct platform_device *pdev;
    int id, sensor_device_type;
};
static struct msm_sensor_ctrl_t *g_sctrl[3];
static int live, parse_rc, clock_rc;
static bool fail_alloc;
static void *alloc(size_t n) {
    if (fail_alloc) return NULL;
    void *p = calloc(1,n); assert(p); ++live; return p;
}
#define kzalloc(n,f) alloc(n)
static void kfree(void *p) { if (p) { assert(live>0); --live; free(p); } }
static void platform_set_drvdata(struct platform_device *p,void *v) { p->data=v; }
static void i2c_set_clientdata(struct i2c_client *p,void *v) { p->data=v; }
static bool i2c_check_functionality(void *p,int f) { return true; }
static int msm_sensor_driver_parse(struct msm_sensor_ctrl_t *s) {
    if (parse_rc) return parse_rc;
    s->sensordata=alloc(sizeof(*s->sensordata));
    s->sensordata->sensor_info=alloc(1);
    s->msm_sensor_mutex=alloc(1);
    s->sensor_i2c_client=alloc(sizeof(*s->sensor_i2c_client));
    s->sensor_i2c_client->cci_client=alloc(1);
    struct msm_camera_power_ctrl_t *p=&s->sensordata->power_info;
    p->cam_vreg=alloc(1); p->gpio_conf=alloc(sizeof(*p->gpio_conf));
    p->gpio_conf->gpio_num_info=alloc(1);
    p->gpio_conf->cam_gpio_req_tbl=alloc(1);
    p->gpio_conf->cam_gpio_set_tbl=alloc(1);
    return 0;
}
static int legacy_msm_camera_get_clk_info(struct platform_device *p,
    void **info,void **ptr,size_t *cnt) {
    assert(!g_sctrl[0]);
    /* Failed clock helpers may leave freed addresses in their outputs. */
    *info=(void *)1; *ptr=(void *)2; *cnt=2;
    return clock_rc;
}
static int legacy_msm_camera_i2c_dev_get_clk_info(struct device *d,
    void **info,void **ptr,size_t *cnt) {
    return legacy_msm_camera_get_clk_info(NULL,info,ptr,cnt);
}
'''
        functions = "\n".join(extract(name) for name in (
            "msm_sensor_driver_free_parsed_data", "msm_sensor_driver_platform_probe",
            "msm_sensor_driver_i2c_probe"))
        main = r'''
int main(void) {
    for (int bus=0;bus<2;bus++) for (int scenario=0;scenario<5;scenario++) {
        struct platform_device p={0}; struct i2c_client c={0};
        parse_rc=scenario==1 ? -EINVAL : 0;
        clock_rc=scenario==2 ? -517 : scenario==3 ? -EINVAL : 0;
        fail_alloc=scenario==0;
        int rc=bus ? msm_sensor_driver_i2c_probe(&c) : msm_sensor_driver_platform_probe(&p);
        if (scenario==4) {
            assert(!rc && g_sctrl[0]);
            assert((bus ? c.data : p.data)==g_sctrl[0]);
            assert(g_sctrl[0]->sensordata->power_info.dev==(bus ? &c.dev : &p.dev));
            msm_sensor_driver_free_parsed_data(g_sctrl[0]);
            kfree(g_sctrl[0]); g_sctrl[0]=NULL;
        } else {
            assert(rc==(scenario==0 ? -ENOMEM : scenario==1 ? parse_rc : clock_rc));
            assert(!g_sctrl[0] && !p.data && !c.data);
        }
        assert(!live);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            cfile, exe = Path(folder) / "sensor.c", Path(folder) / "sensor"
            cfile.write_text(harness + functions + main)
            subprocess.run([os.environ.get("CC", "cc"), "-Wall", "-Werror",
                            str(cfile), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=5)

    def test_eeprom_power_sequence_lengths_match(self):
        dts = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi").read_text()
        for match in re.finditer(r"qcom,eeprom@\w+\s*{([^}]+)};", dts, re.S):
            with self.subTest(node=match[0].split("{", 1)[0]):
                counts = {}
                for prop in ("type", "val", "cfg-val", "delay"):
                    value = re.search(r"qcom,cam-power-seq-" + prop + r"\s*=\s*([^;]+);",
                                      match[1])[1]
                    counts[prop] = (len(re.findall(r'"[^"]+"', value))
                                    if prop in ("type", "val")
                                    else len(value.strip("<> \t\n").split()))
                self.assertEqual(len(set(counts.values())), 1, counts)

    def test_power_sequence_parser_and_eeprom_cleanup(self):
        source = (CAM / "sensor/io/msm_camera_dt_util.c").read_text()
        parser = re.search(r"^int legacy_msm_camera_get_dt_power_setting_data\(.*?^}",
                           source, re.M | re.S)[0]
        source = (CAM / "sensor/eeprom/msm_eeprom.c").read_text()
        caller = re.search(r"^static int msm_eeprom_get_dt_data\(.*?^}",
                           source, re.M | re.S)[0]
        parse_call = caller.split("\tif (e_ctrl->userspace_probe == 0) {", 1)[1]
        parse_call = "\tif (e_ctrl->userspace_probe == 0) {" + parse_call.split(
            "\n\tpower_info->gpio_conf =", 1)[0]
        cleanup = "ERROR2:" + caller.split("ERROR2:", 1)[1]
        constants = sorted(set(re.findall(r"\b(?:SENSOR_[A-Z0-9_]+|GPIO_OUT_(?:LOW|HIGH))\b",
                                         parser)))
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define GFP_KERNEL 0
#define CDBG(...) ((void)0)
#define pr_err(...) ((void)0)
struct device_node { int unused; };
struct camera_vreg_t { const char *reg_name; };
struct msm_sensor_power_setting { int seq_type, seq_val; long config_val; uint16_t delay; };
struct msm_camera_power_ctrl_t {
    struct msm_sensor_power_setting *power_setting, *power_down_setting;
    uint16_t power_setting_size, power_down_setting_size;
    struct camera_vreg_t *cam_vreg;
    int num_vreg;
};
static struct { void *ptr; bool freed; } allocations[8];
static int allocation_count, attempt, fail_at, malformed, bad_cfg;
static void *kzalloc(size_t n, int flags)
{
    if (++attempt == fail_at) return NULL;
    void *p = calloc(1, n);
    assert(p && allocation_count < 8);
    allocations[allocation_count++].ptr = p;
    return p;
}
static void kfree(void *p)
{
    if (!p) return;
    for (int i = 0; i < allocation_count; i++) {
        if (allocations[i].ptr == p) {
            assert(!allocations[i].freed);
            allocations[i].freed = true;
            return;
        }
    }
    abort();
}
static const char *types[] = {"sensor_gpio", "sensor_gpio", "sensor_vreg",
    "sensor_vreg", "sensor_vreg", "sensor_vreg", "sensor_clk", "sensor_gpio", "sensor_gpio"};
static const char *values[] = {"sensor_gpio_reset", "sensor_gpio_standby", "cam_vana",
    "cam_vdig", "cam_vio", "cam_vaf", "sensor_cam_mclk", "sensor_gpio_reset", "sensor_gpio_standby"};
static int of_property_count_strings(struct device_node *np, const char *prop)
{
    return strstr(prop, "seq-type") ? 9 : 9 - malformed;
}
static int of_property_read_string_index(struct device_node *np, const char *prop,
                                         int index, const char **value)
{
    bool type = strstr(prop, "seq-type") != NULL;
    if (index >= (type ? 9 : 9 - malformed)) return -ENODATA;
    *value = type ? types[index] : values[index + (malformed && index >= 5)];
    return 0;
}
static int of_property_read_u32_array(struct device_node *np, const char *prop,
                                      uint32_t *array, int count)
{
    if (bad_cfg) return -EINVAL;
    for (int i = 0; i < count; i++) array[i] = i;
    return 0;
}
'''
        harness += "enum {" + ",".join(constants) + "};\n" + parser + r'''
static int parse_eeprom(struct msm_camera_power_ctrl_t *power_info)
{
    struct { int userspace_probe; } ctrl = {0}, *e_ctrl = &ctrl;
    struct device_node node = {0}, *of_node = &node;
    int rc;
'''
        harness += parse_call + "\n    return 0;\n" + cleanup + r'''
int main(int argc, char **argv)
{
    int scenario = atoi(argv[1]);
    struct msm_camera_power_ctrl_t info = { .num_vreg = 4 };
    info.cam_vreg = kzalloc(4 * sizeof(*info.cam_vreg), 0);
    const char *names[] = {"cam_vdig", "cam_vio", "cam_vana", "cam_vaf"};
    for (int i = 0; i < 4; i++) info.cam_vreg[i].reg_name = names[i];
    attempt = 0;
    fail_at = scenario >= 1 && scenario <= 3 ? scenario : 0;
    malformed = scenario == 4;
    bad_cfg = scenario == 5;
    int rc = parse_eeprom(&info);
    if (!scenario) {
        assert(rc == 0 && info.power_setting_size == 9 && info.power_down_setting_size == 9);
        for (int i = 0; i < 9; i++)
            assert(!memcmp(&info.power_setting[i], &info.power_down_setting[8-i],
                           sizeof(*info.power_setting)));
        kfree(info.power_down_setting);
        kfree(info.power_setting);
        kfree(info.cam_vreg);
    } else {
        assert(rc == (scenario <= 3 ? -ENOMEM : scenario == 4 ? -EILSEQ : -EINVAL));
        assert(!info.power_setting && !info.power_setting_size);
    }
    for (int i = 0; i < allocation_count; i++) {
        assert(allocations[i].freed);
        free(allocations[i].ptr);
    }
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "power-parser.c", Path(tmp) / "power-parser"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            for scenario in range(6):
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(exe), str(scenario)], capture_output=True,
                                            timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_eeprom_waits_for_a_flushed_snapshot(self):
        ram = (ROOT / "fs/pstore/ram.c").read_text()
        eeprom = (CAM / "sensor/eeprom/msm_eeprom.c").read_text()
        self.assertIn("late_initcall(msm_eeprom_init_module);", eeprom)
        self.assertRegex(ram, r"#define RAMOOPS_PERIODIC_SNAPSHOTS\s+1\b")
        self.assertIn("static DECLARE_COMPLETION(ramoops_snapshot_ready);", ram)
        wait = re.search(r"^int ramoops_wait_snapshot_ready\(.*?^}",
                         ram, re.M | re.S)[0]
        init = re.search(r"^static int __init msm_eeprom_init_module\(.*?^}",
                         eeprom, re.M | re.S)[0]
        thread = ram.split("static int ramoops_snap_thread(", 1)[1]
        sample = thread.split("ret = ramoops_snap_take(s);", 1)[1]
        sample = "ret = ramoops_snap_take(s);" + sample.split(
            "\n\t\t/*\n\t\t * Every tenth", 1)[0]
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#define __init
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
#define CDBG(...) ((void)0)
#define RAMOOPS_SNAP_MAX_FAILURES 10
#define msecs_to_jiffies(ms) (ms)
struct completion { bool done; };
static struct completion ramoops_snapshot_ready;
static unsigned int waits, signals, registrations, commit_result;
static bool camera_legacy_enable = true;
static int msm_eeprom_platform_driver, msm_eeprom_spi_driver, msm_eeprom_i2c_driver;
static unsigned long wait_for_completion_timeout(struct completion *c,
                                                 unsigned long timeout)
{
    assert(timeout == 10000);
    waits++;
    return c->done ? 1 : 0;
}
static void complete_all(struct completion *c)
{
    assert(!c->done);
    c->done = true;
    signals++;
}
static int platform_driver_register(void *driver)
{
    assert(ramoops_snapshot_ready.done);
    registrations++;
    return 0;
}
#define spi_register_driver platform_driver_register
#define i2c_add_driver platform_driver_register
struct ramoops_snapper { unsigned int failures; bool warned; } snapshot;
static int ramoops_snap_take(struct ramoops_snapper *s) { return commit_result; }
static void sample_once(void)
{
    struct ramoops_snapper *s = &snapshot;
    int ret;
    for (int attempt = 0; attempt < 1; attempt++) {
'''
        harness += sample + "\n    }\n}\n" + wait + "\n" + init + r'''
int main(void)
{
    camera_legacy_enable = false;
    assert(msm_eeprom_init_module() == -ENODEV && !waits && !registrations);
    camera_legacy_enable = true;
    assert(msm_eeprom_init_module() == -ETIMEDOUT && !registrations);
    commit_result = EIO;
    sample_once();
    assert(!signals && !ramoops_snapshot_ready.done);
    assert(msm_eeprom_init_module() == -ETIMEDOUT && !registrations);
    commit_result = 0;
    sample_once();
    assert(signals == 1 && ramoops_snapshot_ready.done);
    assert(msm_eeprom_init_module() == 0 && registrations == 3);
    sample_once();
    assert(signals == 1);
    assert(ramoops_wait_snapshot_ready(10000) == 0);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "snapshot-ready.c", Path(tmp) / "snapshot-ready"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_gpio_count_uses_phandle_entries(self):
        source = (CAM / "msm_sd.h").read_text()
        function = re.search(r"^static inline int msm_camera_gpio_count\(.*?^}",
                             source, re.M | re.S)[0]
        harness = r'''
#include <assert.h>
#include <string.h>
struct device {};
struct device_node { int count, raw_cells; };
static int of_property_count_u32_elems(struct device_node *np, const char *p)
{
    return np->raw_cells;
}
static int of_count_phandle_with_args(struct device_node *np, const char *p,
                                      const char *cells)
{
    assert(!strcmp(p, "gpios") && !strcmp(cells, "#gpio-cells"));
    return np->count;
}
'''
        harness += function + r'''
int main(void)
{
    struct device_node cases[] = {{4, 12}, {2, 6}, {3, 8}, {0, 0}, {-2, -2}};
    for (int n = 0; n < 5; n++)
        assert(msm_camera_gpio_count(0, &cases[n]) ==
               (cases[n].count > 0 ? cases[n].count : 0));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "gpio.c", Path(tmp) / "gpio"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_cci_top_ahb_uses_its_own_clock_gate(self):
        dts = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi").read_text()
        cci = dts.split("cci: qcom,cci@1b0c000 {", 1)[1]
        clocks = re.search(r"clocks = (.*?);", cci, re.S)[1]
        self.assertEqual(re.findall(r"<&gcc (\w+)>", clocks), [
            "GCC_CAMSS_ISPIF_AHB_CLK", "CCI_CLK_SRC", "GCC_CAMSS_CCI_AHB_CLK",
            "GCC_CAMSS_CCI_CLK", "GCC_CAMSS_AHB_CLK", "GCC_CAMSS_TOP_AHB_CLK"])

    def test_regulator_failure_stops_power_sequence(self):
        source = (CAM / "sensor/io/msm_camera_dt_util.c").read_text()
        power_up = source.split("int legacy_msm_camera_power_up(", 1)[1]
        power_up = power_up.split("static struct msm_sensor_power_setting*", 1)[0]
        enable = power_up.split("case SENSOR_VREG:", 1)[1]
        enable = enable.split("case SENSOR_I2C_MUX:", 1)[0]
        unwind = power_up.split("power_up_failed:", 1)[1]
        unwind = unwind.split("case SENSOR_CLK:", 1)[1].split("case SENSOR_GPIO:", 1)[0]
        harness = r'''
#include <assert.h>
#include <errno.h>
#define SENSOR_VREG 1
#define INVALID_VREG 99
#define CAM_VREG_MAX 8
#define pr_err(...) ((void)0)
struct regulator {};
struct setting { int seq_val; void *data[1]; };
struct control {
    void *dev;
    int num_vreg, cam_vreg[8];
    void *gpio_conf, *clk_info, *clk_ptr;
    int clk_info_size;
};
static int result, regulator_calls, gpio_calls, clock_disables;
static void legacy_msm_camera_clk_enable(void *dev, void *info, void *ptr,
                                        int count, int enable)
{
    assert(!enable && count == 2);
    clock_disables++;
}
static int legacy_msm_camera_config_single_vreg(void *dev, int *vreg,
                                                struct regulator **p, int on)
{
    regulator_calls++;
    return result;
}
static int legacy_msm_cam_sensor_handle_reg_gpio(int val, void *conf, int on)
{
    gpio_calls++;
    return 0;
}
static int step(struct control *ctrl, struct setting *power_setting)
{
    int rc = 0;
    switch (SENSOR_VREG) {
    case SENSOR_VREG:
'''
        harness += enable + r'''
    }
    return 0;
power_up_failed:
    return rc;
}
static void unwind_clock(struct control *ctrl)
{
    switch (0) {
    case 0:
'''
        harness += unwind + r'''
    }
}
int main(void)
{
    struct control ctrl = { .num_vreg = 1, .clk_info_size = 2 };
    struct setting setting = {0};
    result = -ENODEV;
    assert(step(&ctrl, &setting) == -ENODEV);
    assert(regulator_calls == 1 && gpio_calls == 0);
    result = 0;
    assert(step(&ctrl, &setting) == 0);
    assert(regulator_calls == 2 && gpio_calls == 1);
    unwind_clock(&ctrl);
    assert(clock_disables == 1);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "power.c", Path(tmp) / "power"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_eeprom_registration_errors_precede_devnode_access(self):
        source = (CAM / "sensor/eeprom/msm_eeprom.c").read_text()
        probe = source.split("static int msm_eeprom_platform_probe(", 1)[1]
        probe = probe.split("static void msm_eeprom_platform_remove(", 1)[0]
        tail = re.search(r"^[ \t]+(?:rc = )?media_entity_pads_init.*?^}",
                         probe, re.M | re.S)[0]
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#define CONFIG_COMPAT 1
#define MSM_CAMERA_SUBDEV_EEPROM 8
#define CDBG(...) ((void)0)
#define kfree(p) ((void)0)
#define legacy_msm_camera_power_down(...) ((void)0)
struct node { void *fops; } node;
struct control {
    struct { struct { int entity, grp_id; struct node *devnode; } sd; } msm_sd;
    struct { void *mapdata, *map; } cal_data;
    void *eboard_info;
    struct { void *cci_client; } i2c_client;
    int is_supported;
};
struct platform_device { void *data; };
static int entity_result, register_result, registrations, entity_cleanups;
static int media_entity_pads_init(int *entity, int n, void *pads)
{
    return entity_result;
}
static void media_entity_cleanup(int *entity) { entity_cleanups++; }
static int legacy_msm_sd_register(void *sd)
{
    struct control *ctrl = sd;
    assert(ctrl->msm_sd.sd.grp_id == MSM_CAMERA_SUBDEV_EEPROM);
    registrations++;
    if (!register_result) ctrl->msm_sd.sd.devnode = &node;
    return register_result;
}
static void platform_set_drvdata(struct platform_device *pdev, void *data)
{
    pdev->data = data;
}
static struct { int (*compat_ioctl32)(void); } msm_eeprom_v4l2_subdev_fops;
static void legacy_msm_cam_copy_v4l2_subdev_fops(void *fops) {}
static int msm_eeprom_subdev_fops_ioctl32(void) { return 0; }
static int finish_probe(struct control *e_ctrl, struct platform_device *pdev)
{
    int rc = 0;
'''
        harness += tail + r'''
int main(void)
{
    for (int failure = 0; failure < 3; failure++) {
        struct control ctrl = {0};
        struct platform_device pdev = { .data = &ctrl.msm_sd.sd };
        entity_result = failure == 1 ? -ENOMEM : 0;
        register_result = failure == 2 ? -EIO : 0;
        registrations = entity_cleanups = 0;
        assert(finish_probe(&ctrl, &pdev) == (entity_result ?: register_result));
        assert(registrations == (failure != 1));
        assert(entity_cleanups == (failure == 2));
        if (failure) assert(!pdev.data && !ctrl.msm_sd.sd.devnode);
        else assert(pdev.data && node.fops == &msm_eeprom_v4l2_subdev_fops);
    }
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "eeprom.c", Path(tmp) / "eeprom"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_subdevice_registration_unwinds_failures(self):
        source = (CAM / "msm.c").read_text()
        internal = re.search(r"^static inline int __msm_sd_register_subdev\(.*?^}",
                             source, re.M | re.S)[0]
        public = re.search(r"^int legacy_msm_sd_register\(.*?^}",
                           source, re.M | re.S)[0]
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#define GFP_KERNEL 0
#define V4L2_SUBDEV_FL_HAS_DEVNODE 1
#define VFL_TYPE_SUBDEV 1
#define WARN_ON(x) (x)
#define strscpy(d, s, n) snprintf(d, n, "%s", s)
#include <stdio.h>
struct video_device;
struct v4l2_subdev {
    char name[32];
    int flags, owner;
    struct video_device *devnode;
};
struct video_device {
    char name[32];
    void *v4l2_dev, *fops;
    void (*release)(struct video_device *);
};
struct msm_sd_subdev { struct v4l2_subdev sd; };
static struct { void *dev; } core = { &core }, *msm_v4l2_dev = &core;
static int ordered_sd_mtx, ordered_sd_list, linked, registered, allocated;
static int fail_stage, unregisters;
#define mutex_lock(p) ((void)0)
#define mutex_unlock(p) ((void)0)
static void msm_add_sd_in_position(struct msm_sd_subdev *sd, int *list)
{
    assert(!linked);
    linked = 1;
}
static int v4l2_device_register_subdev(void *core, struct v4l2_subdev *sd)
{
    if (fail_stage == 1) return -ENODEV;
    registered = 1;
    return 0;
}
static void *kzalloc(size_t n, int flags)
{
    if (fail_stage == 2) return NULL;
    allocated++;
    return calloc(1, n);
}
static void kfree(void *p) { allocated--; free(p); }
#define video_set_drvdata(v, s) ((void)0)
#define msm_cam_get_v4l2_subdev_fops_ptr() NULL
static void msm_sd_unregister_subdev(struct video_device *v) { kfree(v); }
static int __video_register_device(struct video_device *v, int t, int n,
                                   int warn, int owner)
{
    return fail_stage == 3 ? -EIO : 0;
}
static void video_unregister_device(struct video_device *v) { kfree(v); }
static void v4l2_device_unregister_subdev(struct v4l2_subdev *sd)
{
    assert(registered);
    registered = 0;
    unregisters++;
    if (sd->devnode) {
        video_unregister_device(sd->devnode);
        sd->devnode = NULL;
    }
}
'''
        harness += internal + "\n" + public + r'''
int main(void)
{
    const int errors[] = {0, -ENODEV, -ENOMEM, -EIO};
    for (fail_stage = 0; fail_stage <= 3; fail_stage++) {
        struct msm_sd_subdev sub = { .sd = { .name = "eeprom", .flags = 1 } };
        linked = registered = allocated = unregisters = 0;
        assert(legacy_msm_sd_register(&sub) == errors[fail_stage]);
        if (fail_stage) {
            assert(!linked && !registered && !allocated && !sub.sd.devnode);
            assert(unregisters == (fail_stage >= 2));
        } else {
            assert(linked && registered && allocated == 1 && sub.sd.devnode);
            v4l2_device_unregister_subdev(&sub.sd);
        }
    }
    struct msm_sd_subdev sub = { .sd = { .name = "cci" } };
    linked = registered = allocated = unregisters = fail_stage = 0;
    assert(legacy_msm_sd_register(&sub) == 0);
    assert(linked && registered && !allocated && !sub.sd.devnode);
    v4l2_device_unregister_subdev(&sub.sd);
    msm_v4l2_dev = NULL;
    linked = 0;
    assert(legacy_msm_sd_register(&sub) == -EIO && !linked);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "register.c", Path(tmp) / "register"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_clock_failure_cleanup_stays_within_acquired_entries(self):
        source = (CAM / "common/cam_soc_api.c").read_text()
        single = source.split("static int msm_camera_get_clk_info_internal(", 1)[1]
        single = single.split("EXPORT_SYMBOL(legacy_msm_camera_get_clk_info);", 1)[0]
        multiple = source.split("int legacy_msm_camera_get_clk_info_and_rates(", 1)[1]
        multiple = multiple.split("EXPORT_SYMBOL(", 1)[0]
        cleanups = {
            "single-clock": single.split("err4:", 1)[1].split("err3:", 1)[0],
            "rate-allocation": multiple.split("if (!rates[i]) {", 1)[1]
                .split("goto err3;", 1)[0],
            "multiple-clocks": multiple.split("err5:", 1)[1].split("err4:", 1)[0],
        }
        for name, cleanup in cleanups.items():
            with self.subTest(cleanup=name):
                # Check each subscript before access, including unsigned wrap.
                cleanup = re.sub(
                    r"(?:\(\*clk_ptr\)|clks|rates)\[([^]]+)\]",
                    r"checked(\1)", cleanup)
                harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
static unsigned int acquired, expected, released;
static void *checked(uint32_t index)
{
    if (index >= acquired || !expected || index != expected - 1)
        exit(1);
    expected--;
    return (void *)(uintptr_t)(index + 1);
}
static void release(void *dev, void *entry) { released++; }
#define devm_clk_put release
#define devm_kfree release
int main(void)
{
    void *dev = NULL;
    struct { int dev; } device, *pdev = &device;
    for (acquired = 0; acquired < 5; acquired++) {
        uint32_t i = acquired;
        int rc = 0;
        expected = acquired;
        released = 0;
'''
                harness += cleanup + r'''
        assert(expected == 0 && released == acquired);
    }
}
'''
                with tempfile.TemporaryDirectory() as tmp:
                    cfile, exe = Path(tmp) / "cleanup.c", Path(tmp) / "cleanup"
                    cfile.write_text(harness)
                    subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                                    "-o", str(exe)], check=True)
                    result = subprocess.run([str(exe)], capture_output=True,
                                            timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_cci_irq_is_not_enabled_during_probe(self):
        source = (CAM / "sensor/cci/msm_cci.c").read_text()
        probe = source.split("static int msm_cci_probe(", 1)[1]
        probe = probe.split("static void msm_cci_exit(", 1)[0]
        request = re.search(r"rc = legacy_msm_camera_register_irq\(.*?;",
                            probe, re.S)[0]
        harness = r'''
#include <assert.h>
#define IRQF_TRIGGER_RISING 1
#define IRQF_NO_AUTOEN 0x80000
struct resource { int unused; };
struct cci_device { struct resource *irq; };
static int handler_called;
static void msm_cci_irq(void) { handler_called++; }
static int legacy_msm_camera_register_irq(void *pdev, struct resource *irq,
    void (*handler)(void), int flags, const char *name, void *state)
{
    /* Model a pending IRQ delivered synchronously by request_irq(). */
    if (!(flags & IRQF_NO_AUTOEN))
        handler();
    return 0;
}
int main(void)
{
    int rc;
    struct cci_device dev = {0}, *new_cci_dev = &dev;
    void *pdev = 0;
'''
        harness += request + r'''
    assert(rc == 0 && handler_called == 0);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "irq-race.c", Path(tmp) / "irq-race"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        # NO_AUTOEN already leaves disable depth at one, so don't disable twice.
        self.assertNotIn("legacy_msm_camera_enable_irq(", probe)
        init = source.split("static int32_t msm_cci_init(", 1)[1]
        init = init.split("static int32_t msm_cci_release(", 1)[0]
        self.assertLess(init.index("rc = legacy_msm_camera_clk_enable("),
                        init.index("legacy_msm_camera_enable_irq(cci_dev->irq, true)"))

    def test_irq_lookup_errors_and_handle(self):
        source = (CAM / "common/cam_soc_api.c").read_text()
        function = re.search(
            r"^struct resource \*legacy_msm_camera_get_irq\(.*?^}",
            source, re.M | re.S)[0]
        self.assertNotIn("platform_get_resource_byname", function)
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define GFP_KERNEL 0
#define IORESOURCE_IRQ 0x400
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define pr_err(...) ((void)0)
struct device { int unused; };
struct platform_device { struct device dev; };
struct resource { unsigned long start, end, flags; const char *name; };
static int irq_result, fail_alloc;
static struct resource handle;
static int platform_get_irq_byname(struct platform_device *p, char *name)
{
    assert(p && !strcmp(name, "cci"));
    return irq_result;
}
static void *devm_kzalloc(struct device *d, size_t n, int flags)
{
    assert(d && n == sizeof(handle));
    memset(&handle, 0, n);
    return fail_alloc ? NULL : &handle;
}
'''
        harness += function + r'''
int main(void)
{
    struct platform_device p = {0};
    struct resource *r;
    assert(legacy_msm_camera_get_irq(NULL, "cci") == ERR_PTR(-EINVAL));
    assert(legacy_msm_camera_get_irq(&p, NULL) == ERR_PTR(-EINVAL));
    irq_result = -517; /* EPROBE_DEFER must survive. */
    assert(legacy_msm_camera_get_irq(&p, "cci") == ERR_PTR(-517));
    irq_result = -ENXIO;
    assert(legacy_msm_camera_get_irq(&p, "cci") == ERR_PTR(-ENXIO));
    irq_result = 82;
    fail_alloc = 1;
    assert(legacy_msm_camera_get_irq(&p, "cci") == ERR_PTR(-ENOMEM));
    fail_alloc = 0;
    r = legacy_msm_camera_get_irq(&p, "cci");
    assert(r == &handle && r->start == 82 && r->end == 82);
    assert(r->flags == IORESOURCE_IRQ && !strcmp(r->name, "cci"));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / "irq.c", Path(tmp) / "irq"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), str(cfile),
                            "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
        callers = 0
        for path in CAM.rglob("*.c"):
            text = path.read_text()
            for match in re.finditer(
                    r"([\w>\-]+) = legacy_msm_camera_get_irq\([^;]+;", text):
                tail = text[match.end():match.end() + 350]
                self.assertIn(f"IS_ERR({match[1]})", tail, str(path))
                self.assertIn(f"PTR_ERR({match[1]})", tail, str(path))
                callers += 1
        self.assertEqual(callers, 9)

    def test_firmware_preflight(self):
        script = (ROOT / "porting/tools/build-kernel.sh").read_text()
        guard = script.split("# Firmware is gitignored", 1)[1]
        guard = guard.split("# --- the base image", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, FW_DIR=tmp, VENUS_FW_DIR=tmp)
            files = ["wcnss.mdt", "wcnss.b00", "wcnss.b01", "wcnss.b02",
                     "wcnss.b04", "wcnss.b06", "wcnss.b09", "wcnss.b10",
                     "wcnss.b11", "wcnss.b12",
                     "wlan/prima/WCNSS_qcom_wlan_nv.bin", "venus.mdt"]
            files += [f"venus.b{i:02d}" for i in range(5)]
            for name in files:
                p = Path(tmp) / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"firmware")
            def run():
                return subprocess.run(["bash", "-eu", "-c", "# Firmware is gitignored" + guard],
                                      env=env, capture_output=True)
            self.assertEqual(run().returncode, 0)
            for name in files:
                p = Path(tmp) / name
                p.unlink()
                self.assertNotEqual(run().returncode, 0, name)
                p.write_bytes(b"")
                self.assertNotEqual(run().returncode, 0, name)
                p.write_bytes(b"firmware")

    def test_core_and_media_prerequisites(self):
        dts = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi").read_text()
        self.assertIn('compatible = "qcom,msm-cam";', dts)
        for mode in ("standard", "fast", "custom", "fast_plus"):
            node = re.search(rf"qcom,i2c_{mode}_mode {{(.*?)}};", dts, re.S)[1]
            for prop in ("thigh", "tlow", "tsu-sto", "tsu-sta", "thd-dat",
                         "thd-sta", "tbuf", "scl-stretch-en", "trdhld", "tsp"):
                self.assertIn(f"qcom,hw-{prop}", node)
        for path in ("msm.c", "camera/camera.c"):
            text = (CAM / path).read_text()
            self.assertLess(text.index("->mdev->dev ="),
                            text.index("media_device_init("))
            self.assertLess(text.index("media_device_init("),
                            text.index("rc = media_device_register("))
        for path in ("msm.c", "camera/camera.c", "fd/msm_fd_dev.c",
                     "jpeg_dma/msm_jpeg_dma_dev.c"):
            self.assertIn("->device_caps =" if path in ("msm.c", "camera/camera.c")
                          else ".device_caps =", (CAM / path).read_text())

    def test_core_driver_name_is_not_drm_msm(self):
        # CONFIG_DRM_MSM registers a platform driver named "msm"
        # (drivers/gpu/drm/msm/msm_drv.c), so the camera core would fail
        # driver_register with -EBUSY before its probe could run. That
        # is what run371 measured: Error: Driver 'msm' is already
        # registered, aborting...
        source = (CAM / "msm.c").read_text()
        block = source.split("static struct platform_driver msm_driver",
                             1)[1]
        block = block.split("};", 1)[0]
        match = re.search(r'\.name = "([^"]+)"', block)
        self.assertIsNotNone(match)
        self.assertNotEqual(match[1], "msm")
        drm = ROOT / "drivers/gpu/drm/msm/msm_drv.c"
        self.assertIsNotNone(re.search(r'name\s+= "msm"', drm.read_text()),
                             "the conflicting DRM msm driver moved")

    def test_ahb_vote_client_carries_its_device(self):
        # The interconnect compat layer resolves votes through
        # pdata->dev (msm-bus-compat.c msm_bus_scale_register_client);
        # the DT-parse path sets it, cam_hw_ops did not.
        source = (CAM / "common/cam_hw_ops.c").read_text()
        block = source.split(
            "*data.pbus_data = (struct msm_bus_scale_pdata) {", 1)[1]
        block = block.split("};", 1)[0]
        self.assertIn(".dev = &pdev->dev", block)


if __name__ == "__main__":
    unittest.main()
