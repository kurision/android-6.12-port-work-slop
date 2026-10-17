#!/usr/bin/env python3
"""Exercise actual DSI selection/policy C with host-only OF/init boundaries."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    source = (ROOT / 'drivers/video/fbdev/msm/mdss_dsi.c').read_text()
    naming = (ROOT / 'drivers/of/base.c').read_text()
    implementation = function(naming, 'bool of_node_name_eq(') + '\n'
    implementation += '\n'.join(function(source, signature) for signature in (
        'static struct device_node *mdss_dsi_pref_prim_panel(',
        'static struct device_node *mdss_dsi_find_panel_of_node(',
        'static struct device_node *mdss_dsi_config_panel(',
    ))
    harness = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define IS_ENABLED(option) (option)
#define CONFIG_MACH_XIAOMI_MIDO 0
#define XIAOMI_MSM8953_MACH_TISSOT 1
#define XIAOMI_MSM8953_MACH_MIDO 2
#define MDSS_MAX_PANEL_LEN 256
#define CMDLINE_DSI_CTL_NUM_STRING_LEN 2
#define OVERRIDE_CFG "override"
#define NONE_PANEL "none"
#define pr_debug(...) ((void)0)
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
struct device_node { const char *full_name, *label; };
struct mdss_panel_info { int sim_panel_mode; char panel_name[MDSS_MAX_PANEL_LEN]; };
struct mdss_dsi_ctrl_pdata {
    struct {
        struct mdss_panel_info panel_info;
        char dsc_cfg_np_name[MDSS_MAX_PANEL_LEN];
    } panel_data;
};
struct platform_device {
    int id;
    struct { struct device_node *of_node; } dev;
};
static struct mdss_dsi_ctrl_pdata ctrl;
static struct device_node controller = { "/dsi", "controller" };
static struct device_node mdss = { "/mdss", "mdss" };
static struct device_node panels[] = {
    { "/mdss/qcom,mdss_dsi_td4310_fhd_video", "td4310 human label" },
    { "/mdss/qcom,mdss_dsi_otm1911_fhd_video", "otm1911 fhd video mode dsi panel" },
    { "/mdss/qcom,mdss_dsi_ft8716_fhd_video", "ft8716 human label" },
    /* A known-looking human label must not choose policy for an unknown node. */
    { "/mdss/unknown_panel", "qcom,mdss_dsi_otm1911_fhd_video" },
};
static struct platform_device pdev = { 1, { &controller } };
static struct device_node *preferred, *cmdline;
static const char *configuration;
static int machine, preferred_reads, initialized, init_reset, init_power;
static int panel_suspend_reset_flag, panel_suspend_power_flag;
static int xiaomi_msm8953_mach_get(void) { return machine; }
static const char *kbasename(const char *path)
{
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}
static int strscpy(char *dest, const char *src, size_t size)
{
    size_t len = strlen(src);
    assert(len < size);
    memcpy(dest, src, len + 1);
    return (int)len;
}
static char *strnstr(const char *s, const char *needle, size_t count)
{
    char *found = (char *)strstr(s, needle);
    return found && (size_t)(found - s) + strlen(needle) <= count ? found : NULL;
}
static char *strnchr(const char *s, size_t count, int c)
{
    return (char *)memchr(s, c, strnlen(s, count));
}
static struct mdss_dsi_ctrl_pdata *platform_get_drvdata(struct platform_device *p)
{
    assert(p == &pdev);
    return &ctrl;
}
static int mdss_dsi_get_panel_cfg(char *cfg, struct mdss_dsi_ctrl_pdata *data)
{
    assert(data == &ctrl);
    return strscpy(cfg, configuration, MDSS_MAX_PANEL_LEN);
}
static int mdss_dsi_set_override_cfg(char *override,
        struct mdss_dsi_ctrl_pdata *data, char *cfg)
{
    (void)override; (void)data; (void)cfg;
    assert(0 && "override parsing is outside this regression");
    return -1;
}
static struct device_node *of_parse_phandle(struct device_node *node,
        const char *property, int index)
{
    assert(node == &controller && index == 0);
    if (!strcmp(property, "qcom,mdss-mdp"))
        return &mdss;
    assert(!strcmp(property, "qcom,dsi-pref-prim-pan"));
    preferred_reads++;
    return preferred;
}
bool of_node_name_eq(const struct device_node *node, const char *name);
static struct device_node *of_find_node_by_name(struct device_node *node,
        const char *name)
{
    assert(node == &mdss);
    return of_node_name_eq(cmdline, name) ? cmdline : NULL;
}
static void of_node_put(struct device_node *node) { (void)node; }
static int mdss_dsi_panel_init(struct device_node *node,
        struct mdss_dsi_ctrl_pdata *data, int ndx)
{
    assert(data == &ctrl && ndx == 0);
    initialized++;
    init_reset = panel_suspend_reset_flag;
    init_power = panel_suspend_power_flag;
    strscpy(data->panel_data.panel_info.panel_name, node->label, MDSS_MAX_PANEL_LEN);
    return 0;
}
'''
    check = r'''
static void select_panel(const char *cfg, struct device_node *lookup,
        struct device_node *fallback, struct device_node *want,
        int reset, int power, int fallback_reads)
{
    configuration = cfg;
    cmdline = lookup;
    preferred = fallback;
    preferred_reads = initialized = 0;
    panel_suspend_reset_flag = 7;
    panel_suspend_power_flag = 9;
    assert(mdss_dsi_config_panel(&pdev, 0) == want);
    assert(preferred_reads == fallback_reads);
    assert(panel_suspend_reset_flag == reset && panel_suspend_power_flag == power);
    assert(initialized == (want != NULL));
    if (want) {
        /* The first consumer must see policy before it initializes the panel. */
        assert(init_reset == reset && init_power == power);
        assert(!strcmp(ctrl.panel_data.panel_info.panel_name, want->label));
    }
}
int main(void)
{
    machine = XIAOMI_MSM8953_MACH_TISSOT;
    const int policy[] = { 1, 2, 3, 0 };
    for (unsigned int i = 0; i < sizeof(panels) / sizeof(panels[0]); i++) {
        char cfg[MDSS_MAX_PANEL_LEN];
        snprintf(cfg, sizeof(cfg), "0:%s", kbasename(panels[i].full_name));
        select_panel(cfg, &panels[i], &panels[3], &panels[i], policy[i], policy[i], 0);
        select_panel("", NULL, &panels[i], &panels[i], policy[i], policy[i], 1);
    }
    /* A named TD4310 that cannot be resolved must inherit the actual OTM1911
     * fallback policy, not the requested node's policy or stale globals. */
    select_panel("0:qcom,mdss_dsi_td4310_fhd_video", NULL,
                 &panels[1], &panels[1], 2, 2, 1);
    select_panel("0:missing_panel", NULL, &panels[1], &panels[1], 2, 2, 1);
    select_panel("1:qcom,mdss_dsi_td4310_fhd_video", NULL,
                 &panels[1], &panels[1], 2, 2, 1);
    /* No selected panel means no initialization and no policy reassignment. */
    select_panel("0:none", NULL, &panels[1], NULL, 7, 9, 0);
    select_panel("", NULL, NULL, NULL, 7, 9, 1);
    /* Keep the runtime machine condition even without a compile-time gate. */
    machine = 0;
    select_panel("0:qcom,mdss_dsi_otm1911_fhd_video", &panels[1],
                 NULL, &panels[1], 7, 9, 0);
    select_panel("", NULL, &panels[1], &panels[1], 7, 9, 1);
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='ack-panel-policy-test-') as tmp:
        root = Path(tmp)
        unit = root / 'panel_policy.c'
        unit.write_text(harness + implementation + check)
        for enabled in (0, 1):
            executable = root / f'panel_policy_{enabled}'
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            f'-DCONFIG_MACH_XIAOMI_TISSOT={enabled}', str(unit),
                            '-o', str(executable)], check=True, timeout=20)
            subprocess.run([str(executable)], check=True, timeout=10)
    print('panel policy: cmdline/DT fallback, mapping, stale defaults and runtime guard passed')


if __name__ == '__main__':
    main()
