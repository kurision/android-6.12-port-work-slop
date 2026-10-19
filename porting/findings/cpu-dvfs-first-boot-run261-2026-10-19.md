# run261: the first port boot with a working CPUFreq policy

Date: 2026-10-19. Image SHA256
`6b008c81b57f4099d24ae521dec84eab10d43d21000fb730062294df3c76a054`.
Source delta against run260: `drivers/clk/qcom/apcc-msm8953.c` only, plus the
analysis and hardening commits (`3b3f9f660`, `647bd6404`).

## Result

**The splash/reset is gone.** The port kernel booted, the APCC handoff
succeeded, one shared cpufreq policy covered all eight CPUs with the seven
stock OPPs, and the system reached `sys.boot_completed=1` with the boot
animation stopped. The phone then died about 326 s of kernel uptime later,
with no kernel-side fault record.

For the first time in this port there is a kernel log for a boot that reached
userspace: the logdump partition read back 1,965,307 bytes of console text
plus two CRC32-verified snapshot slots and two verified periodic printk
tails. run260's logdump was 64 MiB of zeros.

## The evidence

From `run261-logdump.log` (the port kernel's own console):

```
qcom-apcc-msm8953 b116000.clock-controller: boot state: pll 00000000 00000000 00000000 0000000f mux 00000401 00000000 00000403
qcom-apcc-msm8953 b116000.clock-controller: shared CPU/CCI domain, speed bin 2, CPU 799999804 CCI 399999902 Hz, corner 2
cpufreq: cpufreq_online: CPU0: Running at unlisted initial frequency: 799999 KHz, changing to: 1036800 KHz
```

* The boot state is the measured firmware state: the APCS PLL off
  (mode 0, L 0, USER 0x0f), CPU0-3 on GPLL0 div 1, CPU4-7 on XO, the CCI on
  GPLL0 div 3. Identical to the run258 pstore diagnostic.
* The handoff ended in the donor's post-boot state: CPU4-7 on the APCS PLL at
  652.8 MHz, the running CPU0 cluster still on GPLL0 at 800 MHz, the CCI
  still on GPLL0 at 400 MHz, the rail at corner 2. The donor-shaped handoff
  did what the donor does.
* cpufreq then came up: the policy spans CPUs 0-7 with the seven stock OPPs
  (652.8, 1036.8, 1401.6, 1689.6, 1804.8, 1958.4, 2016 MHz), the governor is
  schedutil, `scaling_cur_freq` 2016000 kHz, `scaling_min_freq` 652800 kHz.
  The coupled CPU/CCI transaction ran successfully at policy creation and
  again under the governor.

Live state at kernel uptime 276.58 s (`run261-live/adb-timeline.jsonl`):
`sys.boot_completed=1`, `init.svc.bootanim=stopped`, surfaceflinger and
system_server running, `/dev/ashmem` present.

## What the hardening bought

The three changes in `647bd6404` are the difference between run260's silent
death and this boot:

1. the handoff no longer re-writes the mux of the running CPU0 cluster or
   the live CCI divider, which the donor never does at boot;
2. the PLL lock wait matches the donor's budget, so a lockable PLL is no
   longer reported as a timeout;
3. the MX domain is attached before the first fallible probe step, so a
   failed probe cannot power the shared MX rail off under its other users.

The run259 and run260 images had the same APCC source and both produced an
all-zero logdump. This image has a byte-identical DTB, config, ramdisk, init
and command line; only the driver differs.

## What is still broken

### 1. The UI lag is the run258 class of problem, not a clock problem

At 243.84 s (`run261-live/lag-sample-240.txt`): system_server at 566 % CPU
with 12:37 of CPU time, load average 19.96/8.70/3.33, 79 % sys, 716 % idle
of 800 %. The CPUs are now at 2.016 GHz instead of the 800 MHz of run258, and
the lag is no worse. The bottleneck is the port's graphics/display path
thrashing userspace, not the CPU frequency. This is the original porting
work and it is untouched by the CPU repair.

### 2. The death has no kernel-side fault record

* Last kernel message: 272.35 s of uptime, ordinary Android activity
  (services starting: qrtr-ns, qcamerasvr, per_mgr).
* Last successful ADB sample: host elapsed 348.3 s. Device gone at 353.3 s.
  Back on rooted stock at 453.3 s, after the user's force reboot.
* No panic record, no oops, no soft lockup, no hung task, no watchdog bite,
  no ACKRESET1 orderly-reset note, no reset-page record. The port arms no
  APPS watchdog (`DIAG apps_wdt en=00000000` throughout).
* The snapshotter's last successful commit was at 272.12 s.

A logless death of this kind is a power event, not software: a rail
collapse, a PMIC thermal/OTP shutdown, or a firmware-initiated reset.

### 3. The port has no thermal control loop at all

This is the leading hypothesis, and the port's own configuration says so:

* `CONFIG_QCOM_TSENS` is **not set** in the run261 config, so the
  `qcom,msm8953-tsens` sensor in the DT (`thermal-sensor@4a9000`) is never
  read.
* The CPU nodes carry `#cooling-cells` but no `thermal-zones` property, and
  the shared OPP table has no `cooling-device`, so cpufreq-dt registers no
  cooling device for the policy. The thermal zones in the DT are not
  connected to the CPU policy.
* The stock 4.19 kernel on the same phone has 30+ thermal zones with the
  per-CPU sensors (`apc0-cpu0-usr`, `apc1-cpu0-usr`, ...).

So the CPUs ran at 2016 MHz for 24511 of roughly 26950 policy ticks (91 % of
the run) with no sensor and no throttling, and the phone died four and a half
minutes in. run258, which had no cpufreq policy at all and therefore ran at
the firmware's 800 MHz, survived its whole observation window.

This is the risk the earlier handoff already named: "No sustained high-OPP
stress with TSENS still off". cpufreq-dt's policy init selects the highest
OPP, so the first policy creation puts the SoC straight into that state.

## Proposed next step

One variable, one boot cycle, and it is cheap because it needs no new
driver:

* **Cap the maximum frequency** so the SoC cannot sit at 2016 MHz, and see
  whether the phone survives the full observation window. The cleanest lever
  without touching the stock OPP set is a cpufreq cap; the simplest available
  one is to drop the top entries from the shared OPP table for the test
  build (a one-line DTS change, clearly marked as a test configuration), or
  to add a maximum-frequency limit to cpufreq-dt for this board. A governor
  override is not available from the command line: `default_governor` in
  `drivers/cpufreq/cpufreq.c` is a static array, not a module parameter.
  * If the capped image survives, the death was power/thermal, and the real
    work becomes porting TSENS and wiring the cooling device into the shared
    OPP table before the maximum OPP is used again.
  * If it still dies at the same point, the cause is inside the coupled clock
    transaction under repeated DVFS transitions, and the next step is to log
    every transition (the driver is silent there today) so the last
    transition before the death is visible.
* Add the transition log in the same build either way: it costs no
  behaviour and it is the only way to tell a clock-path hang from a power
  event in the next run.

If the goal is a usable phone rather than a diagnosis, the frequency cap is
a stopgap and the real blockers are the missing thermal loop and the
graphics/display path behind the system_server stall.

## Limits of this result

* The death cause is unverified. The thermal gap is a documented gap in this
  port and a plausible cause, not a proven one; the user's force reboot
  coincides with the return to stock, so an unsolicited reset cannot be
  distinguished from the user's action.
* The port kernel ran for about 326 s of uptime. Everything above is
  observation inside that window.
* No kernel build of the driver was needed for this run beyond the run261
  build itself: the W=1 object compile of `apcc-msm8953.o` is the first
  compile check the hardened driver ever had, and it is clean.
* The second-opinion review that was requested could not be obtained: the
  model provider returned a rate limit on every attempt.
