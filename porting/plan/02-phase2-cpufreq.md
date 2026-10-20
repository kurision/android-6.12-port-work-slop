# Phase 2 — cpufreq

> **Historical record - undated.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

**Historical plan; do not implement the assumptions below.** The independent
big/little policies, GCC CPUSS proposal and optional-voltage-control advice were
corrected in `../findings/06-verification.md`. Current donor-based scope,
implementation status and build/test gates are in
[CPU-oc-test-to-612.md](CPU-oc-test-to-612.md).

**Goal:** the 8 real OPPs on `cpu0-3` (big) and `cpu4-7` (little), governor
switching frequencies.

## Current state (verified)

* Upstream `msm8953.dtsi:44-140` declares the 8 CPU nodes with
  `#cooling-cells = <2>` but **no `clocks` and no `operating-points-v2`**.
* `include/dt-bindings/clock/qcom,gcc-msm8953.h` (238 lines) contains **no CPUSS
  ids** — only `APC0/APC1_DROPOOP_DETECTOR_GPLL0_CLK` and similar.
* `drivers/clk/qcom/gcc-msm8953.c` (4,252 lines) contains **zero** occurrences of
  `CPUSS`. For comparison `gcc-sm8250.c` has six.
* Consequence: even with an OPP table, `cpufreq-dt` cannot attach — the CPU nodes
  have no clock to set.

So phase 2 is clock-driver work first, DT second.

## Step 1 — add GCC CPU clocks

In `include/dt-bindings/clock/qcom,gcc-msm8953.h` define the APCS/CPUSS ids used
by the CAF clock controller, and add matching entries to
`drivers/clk/qcom/gcc-msm8953.c` (`gcc_mdm8953_chnls` / `gcc_mdm8953_pwrn_branches`),
taking the register offsets and hierarchy from the live DT's
`clock-controller@1800000` (GCC) node and from CAF's
`gcc-msm8953.c`. Minimum set for cpufreq:

* `GCC_CPUSS_0_CLOCK` (cpu0-3 cluster)
* `GCC_CPUSS_1_CLOCK` (cpu4-7 cluster)
* optionally `GCC_APC_0/1_CLOCK` for the performance state and DDR/CCI scaling.

Reference point: the CAF DT clocks the CPUs from `clock-controller@b011050`
(`qcom,apcs-cc-msm8953`, RCB) rather than GCC — upstream has no RCB driver at
all, so GCC's CPUSS gates are the only path. Expect to also need
`drivers/clk/qcom/apcs-rcc.c` wiring (`qcom,apcs-rcc`) if you want the RCB
voltage rails to be settable; it is optional.

## Step 2 — OPP table in the board/dtsi

Add to `msm8953-xiaomi-tissi.dtsi` (or the board file) two tables — big and
little — and point `cpu0..3` / `cpu4..7` at them with
`operating-points-v2` plus `clocks`/`clock-names = "cpu"`.

Frequencies and voltages measured on this device (CPR4 table from
`artifacts/dmesg-live.txt:307-314`, matching
`scaling_available_frequencies` = `652800 844800 1036800 1228800 1420800
1612800 1804800 2016000`):

| kHz | µV (CPR4) |
|---|---|
| 652800 | 650000 |
| 844800 | 675000 |
| 1036800 | 700000 |
| 1228800 | 735000 |
| 1420800 | 770000 |
| 1612800 | 805000 |
| 1804800 | 870000 |
| 2016000 | 955000 |

Notes on fidelity:

* These voltages are what CPR4 *asked for*, not fixed values; upstream has no
  CPU voltage regulator for this SoC (`qcom,msm8953-cpr4pd` is absent), so
  `cpufreq-dt` will simply report the pair. Add the CPR4 regulator later if you
  want real DVFS voltage control — it is a `power-controller@b018000` node with
  `nvmem-cells = fusing_rev, speed_bin`.
* The CAF table (`artifacts/tissot-live.dts:309-406`) also carries
  `opp-supported-hw` from nvmem cell `0x19` (PBL bin) and two extra OPPs
  (614400 suspend-only, 2208000 hw-bin 0x80). **Drop `opp-supported-hw`** —
  upstream msm8953.dtsi has no nvmem node — and skip 2208000 unless your silicon
  reports that speed bin.
* Put the OPPs on separate tables per cluster (or one shared table if you attach
  it to both) so little cores do not offer 2 GHz.

## Step 3 — governor and cooling

`#cooling-cells = <2>` is already there, so once phase 5 lands thermal the
cooling device appears automatically. For bring-up use `performance`, then check
`schedutil`/`userspace`.

## Risks

* Wrong CPUSS register offsets silently produce a kernel that boots at 748.8 MHz
  (the "unlisted initial frequency" seen on the reference kernel,
  `artifacts/dmesg-live.txt:315`) and never scales. Check the frequency actually
  changes before assuming success.
* Enabling the wrong power branch can hang a core. Add one clock at a time.

## Verification

```sh
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies   # expect 8 steps
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
echo 1228800 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq
cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq
dmesg | grep -i cpufreq
```

Accept when `scaling_cur_freq` follows `scaling_max_freq` within a second and the
big and little clusters show independent steps.
