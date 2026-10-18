#!/usr/bin/env python3
"""Check actual KGSL AWARE state and power cleanup without a kernel build."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'drivers/gpu/msm/kgsl_pwrctrl.c'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
enum { KGSL_STATE_NONE, KGSL_STATE_INIT, KGSL_STATE_SLUMBER, KGSL_STATE_RESET,
       KGSL_STATE_ACTIVE, KGSL_STATE_NAP, KGSL_STATE_AWARE, KGSL_STATE_SUSPEND };
enum { KGSL_PWRFLAGS_OFF, KGSL_PWRFLAGS_ON };
struct kgsl_device;
struct functable {
    int (*regulator_enable)(struct kgsl_device *);
    void (*regulator_disable)(struct kgsl_device *);
};
struct kgsl_pwrctrl {
    int wakeup_maxpwrlevel, max_pwrlevel, active_pwrlevel, default_pwrlevel;
};
struct kgsl_device {
    unsigned int state, requested_state;
    bool slumber;
    int submit_lock, idle_timer;
    struct kgsl_pwrctrl pwrctrl;
    struct functable *ftbl;
    void *l3_clk;
    unsigned long l3_freq[1];
    int cur_l3_pwrlevel;
};
#define IS_ERR_OR_NULL(p) (!(p))
#define dev_err(...) ((void)0)
#define trace_kgsl_pwr_set_state(...) ((void)0)
#define trace_kgsl_pwr_request_state(...) ((void)0)
#define spin_lock(p) ((void)(p))
#define spin_unlock(p) ((void)(p))
static bool gmu, rail, clock_on, axi, regulator;
static int scenario, disables, gmu_starts, irqs, timers;
static bool gmu_core_gpmu_isenabled(struct kgsl_device *d) { return gmu; }
static bool gmu_core_isenabled(struct kgsl_device *d) { return gmu; }
static bool kgsl_popp_check(struct kgsl_device *d) { return false; }
static void kgsl_pwrctrl_pwrlevel_change(struct kgsl_device *d, int level) {}
static int kgsl_pwrctrl_pwrrail(struct kgsl_device *d, int state)
{
    if (state && scenario == 1)
        return -EIO;
    rail = state;
    return 0;
}
static void kgsl_pwrctrl_clk(struct kgsl_device *d, int on, int state)
{
    if (on)
        assert(rail);
    clock_on = on;
}
static void kgsl_pwrctrl_axi(struct kgsl_device *d, int on) { axi = on; }
static int regulator_enable(struct kgsl_device *d)
{
    assert(rail && clock_on && axi);
    if (scenario == 2)
        return -ENODEV;
    regulator = true;
    return 0;
}
static void regulator_disable(struct kgsl_device *d)
{
    regulator = false;
    disables++;
}
static int gmu_core_start(struct kgsl_device *d)
{
    gmu_starts++;
    return scenario == 3 ? -ETIMEDOUT : 0;
}
static void gmu_core_stop(struct kgsl_device *d) { assert(0); }
static int clk_set_rate(void *clk, unsigned long rate) { return 0; }
static int _wake(struct kgsl_device *d)
{
    d->state = KGSL_STATE_ACTIVE;
    return 0;
}
static void kgsl_pwrctrl_irq(struct kgsl_device *d, int state) { irqs++; }
static void del_timer_sync(int *timer) { timers++; }
static void kgsl_pwrscale_midframe_timer_cancel(struct kgsl_device *d) {}
'''

CHECK = r'''
int main(void)
{
    const unsigned int states[] = {KGSL_STATE_INIT, KGSL_STATE_SLUMBER,
        KGSL_STATE_RESET, KGSL_STATE_ACTIVE, KGSL_STATE_NAP, KGSL_STATE_SUSPEND};
    struct functable ftbl = {regulator_enable, regulator_disable};

    for (int managed = 0; managed <= 1; managed++)
    for (unsigned int i = 0; i < sizeof(states) / sizeof(states[0]); i++)
    for (scenario = 0; scenario <= 3; scenario++) {
        unsigned int old = states[i];
        bool enabling = old == KGSL_STATE_INIT || old == KGSL_STATE_SLUMBER;
        int expected = old == KGSL_STATE_SUSPEND ? -EINVAL :
            managed && (enabling || old == KGSL_STATE_RESET) && scenario == 3 ?
                -ETIMEDOUT :
            !managed && enabling && scenario == 1 ? -EIO :
            !managed && enabling && scenario == 2 ? -ENODEV : 0;
        struct kgsl_device device = {
            .state = old, .requested_state = KGSL_STATE_AWARE, .ftbl = &ftbl,
            .slumber = old == KGSL_STATE_SLUMBER || old == KGSL_STATE_SUSPEND,
        };

        gmu = managed;
        rail = clock_on = axi = regulator = false;
        disables = gmu_starts = irqs = timers = 0;
        assert(_aware(&device) == expected);
        assert(device.requested_state == KGSL_STATE_NONE);
        assert(device.state == (!expected ? KGSL_STATE_AWARE :
                               managed ? KGSL_STATE_RESET : old));
        assert(device.slumber == (device.state == KGSL_STATE_SLUMBER ||
                                  device.state == KGSL_STATE_SUSPEND));
        if (!managed && enabling) {
            assert(rail == !expected && clock_on == !expected);
            assert(axi == !expected && regulator == !expected);
            assert(disables == !!expected);
        } else {
            assert(!disables);
        }
        assert(gmu_starts == (managed && (enabling || old == KGSL_STATE_RESET)));
        assert(irqs == (old == KGSL_STATE_ACTIVE || old == KGSL_STATE_NAP ||
                        (managed && old == KGSL_STATE_RESET)));
        assert(timers == (old == KGSL_STATE_ACTIVE || old == KGSL_STATE_NAP));
        if (!managed && enabling && expected) {
            int saved = scenario;

            scenario = 0;
            device.requested_state = KGSL_STATE_AWARE;
            assert(_aware(&device) == 0 && device.state == KGSL_STATE_AWARE);
            assert(rail && clock_on && axi && regulator);
            scenario = saved;
        }
    }
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    signatures = ('static void kgsl_pwrctrl_set_state(struct',
                  'static void kgsl_pwrctrl_request_state(struct',
                  'static int kgsl_pwrctrl_enable(struct',
                  'static void kgsl_pwrctrl_disable(struct', 'static int\n_aware(')
    functions = []
    for signature in signatures:
        # Skip the forward declarations near the top of the source.
        start = source.rindex(signature)
        functions.append(source[start:source.index('\n}', start) + 2])
    with tempfile.TemporaryDirectory(prefix='kgsl-aware-', dir='/tmp/opencode') as tmp:
        cfile = Path(tmp) / 'test.c'
        binary = Path(tmp) / 'test'
        cfile.write_text(HARNESS + '\n'.join(functions) + CHECK)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-Wno-unused-function', '-Wno-implicit-fallthrough',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(cfile), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('KGSL AWARE transition and power-cleanup regression: PASS (48 cases)')


if __name__ == '__main__':
    main()
