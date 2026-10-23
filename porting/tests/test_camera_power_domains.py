#!/usr/bin/env python3
"""Run the actual VFE/ISPIF power helpers with fault-injected PM providers."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CAM = ROOT / "drivers/media/platform/msm/camera"


def function(source, name):
    return re.search(r"^(?:static )?(?:int|void) " + name
                     + r"\([^;{]*\)\n\{.*?^}", source, re.M | re.S)[0]


class CameraPowerDomains(unittest.TestCase):
    def test_vfe_probe_preserves_resource_errors(self):
        source = (CAM / "isp/msm_isp.c").read_text()
        probe = function(source, "legacy_vfe_hw_probe")
        start = probe.index("rc = vfe_dev->hw_info->vfe_ops.platform_ops."
                            "get_platform_data(vfe_dev);")
        failure = re.search(r"if \(rc < 0\) \{.*?\n\t}", probe[start:], re.S)[0]
        harness = r'''
#include <assert.h>
#include <errno.h>
#define pr_err(...) ((void)0)
static int resource_failure(int rc) {
'''
        harness += failure + r'''
    return 0;
probe_fail3:
    return rc;
}
int main(void) {
    int errors[] = {-517, -ENOMEM, -ENODEV, -EINVAL};
    for(unsigned int i=0; i<sizeof(errors)/sizeof(errors[0]); i++)
        assert(resource_failure(errors[i])==errors[i]);
    assert(resource_failure(0)==0);
}
'''
        with tempfile.TemporaryDirectory(prefix="vfe-probe-error-") as folder:
            cfile, exe = Path(folder) / "probe.c", Path(folder) / "probe"
            cfile.write_text(harness)
            subprocess.run([os.environ.get("CC", "cc"), "-Wall", "-Wextra",
                            "-Werror", str(cfile), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=5)

    def test_faults_and_balanced_references(self):
        vfe = (CAM / "isp/msm_isp47.c").read_text()
        ispif = (CAM / "ispif/msm_ispif.c").read_text()
        header = (CAM / "ispif/msm_ispif.h").read_text()
        constants = "\n".join(re.findall(r"^#define ISPIF_(?:VFE_)?PD_MAX .*",
                                        header, re.M))
        functions = "\n".join([
            *(function(vfe, "legacy_msm_vfe47_" + name) for name in
              ("get_regulators", "put_regulators", "enable_regulators")),
            *(function(ispif, "msm_ispif_" + name) for name in
              ("put_power_domains", "get_power_domains", "set_power_domains")),
        ])
        core = (ROOT / "drivers/base/power/common.c").read_text()
        wrapper = re.search(r"^struct device \*dev_pm_domain_attach_by_name"
                            r"\([^;{]*\)\n\{.*?^}", core, re.M | re.S)[0]
        functions = wrapper + "\n" + functions
        reset = function(ispif, "msm_ispif_reset_hw")
        # Exercise the real cleanup tail with an earlier reset/clock failure.
        cleanup = reset[reset.index("clk_disable:"):]
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define IS_ERR_OR_NULL(p) (!(p) || (intptr_t)(p) < 0)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
struct device_node { int count; const char *names[5]; };
struct device {
    struct device_node *of_node;
    void *pm_domain;
    int id, attached, refs, runtime_enabled, borrowed;
};
struct platform_device { struct device dev; };
struct vfe_device {
    struct platform_device *pdev;
    struct device *power_domain;
    void *regulator_info;
    int vfe_num_regulators;
};
'''
        harness += constants + r'''
struct ispif_device {
    struct platform_device *pdev;
    struct device *ispif_pd[ISPIF_PD_MAX], *vfe_pd[ISPIF_VFE_PD_MAX];
    int ispif_pd_count, vfe_pd_count, clk_idx;
    void *clk_info, *clks;
    int num_clk;
};
static struct device domains[5];
static int attach_at, attach_error, attach_null, reads_fail_at;
static int resume_fail_id, put_fail_id, put_calls, clock_calls, clock_error;
static int regulator_calls, regulator_enable;
static int ispif_8626_reset_clk_info[2];
static int of_property_count_strings(struct device_node *np, const char *p) {
    assert(!strcmp(p,"power-domain-names")); return np->count;
}
static int of_property_read_string_index(struct device_node *np,
    const char *p, int index, const char **name) {
    assert(!strcmp(p,"power-domain-names"));
    if (index==reads_fail_at) return -EILSEQ;
    *name=np->names[index]; return 0;
}
static struct device *genpd_dev_pm_attach_by_name(struct device *dev,
    const char *name) {
    int n=attach_at++;
    (void)dev; assert(name); assert(n<5);
    if (n==attach_error) return ERR_PTR(-517);
    if (n==attach_null) return NULL;
    assert(!domains[n].attached); domains[n].attached=1;domains[n].runtime_enabled=1;
    return &domains[n];
}
static void dev_pm_domain_detach(struct device *pd, bool power_off) {
    assert(power_off && !pd->borrowed);
    assert(pd->attached && !pd->refs); pd->attached=0;pd->runtime_enabled=0;
}
static void pm_runtime_enable(struct device *pd) {
    assert(pd->attached && !pd->runtime_enabled);pd->runtime_enabled=1;
}
static void pm_runtime_disable(struct device *pd) {
    assert(pd->runtime_enabled && !pd->refs);pd->runtime_enabled=0;
}
static int pm_runtime_resume_and_get(struct device *pd) {
    assert(pd->attached && pd->runtime_enabled);
    if (pd->id==resume_fail_id) return -EIO;
    pd->refs++; return 0;
}
static int pm_runtime_put_sync(struct device *pd) {
    assert(pd->attached && pd->runtime_enabled && pd->refs>0); pd->refs--; put_calls++;
    return pd->id==put_fail_id ? -EPIPE : 1;
}
static int legacy_msm_camera_regulator_enable(void *info,int count,int enable) {
    assert(info==(void *)42 && count==2);
    regulator_calls++;regulator_enable=enable;return 0;
}
static int legacy_msm_camera_clk_enable(struct device *dev,void *info,
    void *clocks,int count,int enable) {
    (void)dev;(void)info;(void)clocks;(void)count;assert(!enable);
    clock_calls++;return clock_error;
}
static void reset_mock(void) {
    memset(domains,0,sizeof(domains));
    for(int i=0;i<5;i++) domains[i].id=i;
    attach_at=put_calls=clock_calls=clock_error=regulator_calls=0;
    attach_error=attach_null=reads_fail_at=resume_fail_id=put_fail_id=-1;
}
static void no_refs(void) {
    for(int i=0;i<5;i++) assert(!domains[i].refs);
}
static void detached(void) {
    no_refs();for(int i=0;i<5;i++) assert(!domains[i].attached);
}
'''
        harness += functions
        harness += r'''
static int reset_cleanup(struct ispif_device *ispif,int rc,int skip_clocks) {
    int cleanup_rc;
    void *reset_clk1[ARRAY_SIZE(ispif_8626_reset_clk_info)];
    if(skip_clocks) goto reg_disable;
    goto clk_disable;
'''
        harness += cleanup
        harness += r'''
int main(void) {
    struct device_node node={.count=4,.names={"vfe0","ispif0","vfe1","ispif1"}};
    struct platform_device p={.dev={.of_node=&node}};
    struct vfe_device vfe={.pdev=&p};
    /* Model platform_probe() attaching the single domain before our getter. */
    for(int failed_resume=0;failed_resume<2;failed_resume++) {
        reset_mock();p.dev.pm_domain=(void *)1;p.dev.attached=p.dev.borrowed=1;
        assert(PTR_ERR(dev_pm_domain_attach_by_name(&p.dev,"vfe"))==-EEXIST);
        assert(!legacy_msm_vfe47_get_regulators(&vfe));
        assert(vfe.power_domain==&p.dev && !attach_at && p.dev.runtime_enabled);
        if(failed_resume) {
            resume_fail_id=0;
            assert(legacy_msm_vfe47_enable_regulators(&vfe,1)==-EIO);
            assert(!p.dev.refs);
        }else{
            for(int i=0;i<2;i++)assert(!legacy_msm_vfe47_enable_regulators(&vfe,1));
            assert(p.dev.refs==2);
            for(int i=0;i<2;i++)assert(!legacy_msm_vfe47_enable_regulators(&vfe,0));
        }
        legacy_msm_vfe47_put_regulators(&vfe);legacy_msm_vfe47_put_regulators(&vfe);
        assert(!vfe.power_domain && !p.dev.runtime_enabled && !p.dev.refs);
        assert(p.dev.attached && p.dev.pm_domain==(void *)1 && !attach_at);
        p.dev.pm_domain=NULL;p.dev.attached=p.dev.borrowed=0;
    }
    for(int failure=0;failure<2;failure++) {
        reset_mock();if(failure)attach_null=0;else attach_error=0;
        assert(legacy_msm_vfe47_get_regulators(&vfe)==(failure?-ENODEV:-517));
        assert(!vfe.power_domain);legacy_msm_vfe47_put_regulators(&vfe);detached();
    }
    reset_mock();assert(!legacy_msm_vfe47_get_regulators(&vfe));
    resume_fail_id=0;assert(legacy_msm_vfe47_enable_regulators(&vfe,1)==-EIO);
    no_refs();resume_fail_id=-1;
    for(int i=0;i<2;i++)assert(!legacy_msm_vfe47_enable_regulators(&vfe,1));
    assert(domains[0].refs==2);
    for(int i=0;i<2;i++)assert(!legacy_msm_vfe47_enable_regulators(&vfe,0));
    assert(!legacy_msm_vfe47_enable_regulators(&vfe,1));put_fail_id=0;
    assert(legacy_msm_vfe47_enable_regulators(&vfe,0)==-EPIPE);
    legacy_msm_vfe47_put_regulators(&vfe);legacy_msm_vfe47_put_regulators(&vfe);detached();
    vfe.regulator_info=(void *)42;vfe.vfe_num_regulators=2;
    assert(!legacy_msm_vfe47_enable_regulators(&vfe,1));assert(regulator_enable==1);
    assert(!legacy_msm_vfe47_enable_regulators(&vfe,0));assert(regulator_calls==2);

    for(int kind=0;kind<3;kind++)for(int index=0;index<4;index++) {
        struct ispif_device ispif={.pdev=&p};reset_mock();
        if(kind==0)attach_error=index;
        else if(kind==1)attach_null=index;
        else reads_fail_at=index;
        assert(msm_ispif_get_power_domains(&ispif,&p)==
               (kind==0?-517:kind==1?-ENODEV:-EILSEQ));
        assert(!ispif.ispif_pd_count && !ispif.vfe_pd_count);
        msm_ispif_put_power_domains(&ispif);detached();
    }
    for(int count=-1;count<=5;count++) {
        struct ispif_device ispif={.pdev=&p};reset_mock();
        if(count>0 && count<5)continue;
        node.count=count;assert(msm_ispif_get_power_domains(&ispif,&p)==
                                (count<0?count:-EINVAL));assert(!attach_at);
    }
    node.count=3;
    for(int group=0;group<2;group++) {
        struct ispif_device ispif={.pdev=&p};reset_mock();
        for(int i=0;i<3;i++)node.names[i]=group?"ispif":"vfe";
        assert(msm_ispif_get_power_domains(&ispif,&p)==-EINVAL);detached();
    }
    node=(struct device_node){.count=4,.names={"vfe0","ispif0","vfe1","ispif1"}};
    for(int fail=-1;fail<4;fail++) {
        struct ispif_device ispif={.pdev=&p};reset_mock();
        assert(!msm_ispif_get_power_domains(&ispif,&p));
        assert(ispif.vfe_pd_count==2 && ispif.ispif_pd_count==2);
        for(int group=0;group<2;group++) {
            struct device **pd=group?ispif.ispif_pd:ispif.vfe_pd;
            resume_fail_id=fail;int rc=msm_ispif_set_power_domains(pd,2,1);
            if(fail>=0 && (fail%2)==group)assert(rc==-EIO);
            else {assert(!rc);assert(!msm_ispif_set_power_domains(pd,2,0));}
            no_refs();
        }
        resume_fail_id=-1;
        assert(!msm_ispif_set_power_domains(ispif.vfe_pd,2,1));
        put_fail_id=0;assert(msm_ispif_set_power_domains(ispif.vfe_pd,2,0)==-EPIPE);
        no_refs();put_fail_id=-1;
        for(int idx=1;idx<=2;idx++)for(int error=0;error<3;error++) {
            int original=error==1?-ETIMEDOUT:0;clock_error=error==2?-EIO:0;
            ispif.clk_idx=idx;clock_calls=0;
            assert(!msm_ispif_set_power_domains(ispif.vfe_pd,2,1));
            assert(reset_cleanup(&ispif,original,0)==(original?original:clock_error));
            assert(clock_calls==1);no_refs();
        }
        assert(!msm_ispif_set_power_domains(ispif.vfe_pd,2,1));
        clock_calls=0;assert(reset_cleanup(&ispif,-EIO,1)==-EIO);
        assert(!clock_calls);no_refs();
        msm_ispif_put_power_domains(&ispif);msm_ispif_put_power_domains(&ispif);detached();
    }
    puts("VFE/ISPIF attach faults, grouped bounds, runtime PM, reset cleanup and VFE48 fallback PASS");
}
'''
        with tempfile.TemporaryDirectory(prefix="camera-pd-") as folder:
            cfile, exe = Path(folder) / "power.c", Path(folder) / "power"
            cfile.write_text(harness)
            flags = ["-std=gnu11", "-Wall", "-Wextra", "-Werror"]
            if os.environ.get("CAMERA_TEST_SANITIZERS"):
                flags += ["-fsanitize=" + os.environ["CAMERA_TEST_SANITIZERS"]]
            subprocess.run([os.environ.get("CC", "cc"), *flags,
                            str(cfile), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
