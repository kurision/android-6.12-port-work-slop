# Plan: DDR / bus bandwidth voting (interconnect) on tissot 6.12

**Written 2026-10-22** for an implementing session; a separate session
reviews each commit. Same working rules as
`2026-10-22-video-and-audio-port.md` (AGENTS.md, kernel development skill,
one change per boot, evidence path in every commit body, no
`Co-Authored-By`/`Assisted-by`, no build or flash unless the user asks).
Do this **before** the vidc_3x boot test in that plan: video decode is the
largest DDR consumer.

## 1. The problem (measured on run #55, 2026-10-22)

* The ROM's power HAL fails every boost write:
  `libperfmgr: Failed to write to node: /sys/class/devfreq/soc:qcom,cpu-cpu-ddr-bw/min_freq with value: 769, fd: -1`.
  `/vendor/etc/powerhint.json` node `CPUBWMinFreq` writes 9887 / 7759 /
  5126 / 769 there. On the port `/sys/class/devfreq/` holds only
  `1c00000.gpu`.
* Nothing votes bus bandwidth at all:
  `CONFIG_INTERCONNECT_QCOM_MSM8953` is not set
  (`porting/tools/kernel.config:7539`), the DT has no NoC nodes,
  `/sys/kernel/debug/interconnect/interconnect_summary` is empty and
  `clk_summary` has no RPM bus clocks. The DT says so itself
  (`msm8953-xiaomi-tissot.dts:608-609`,
  `msm8953-xiaomi-tissot-venus.dtsi:21`).
* The `msm-bus` shim (`drivers/gpu/msm/msm-bus-compat.c`, header
  `include/linux/msm-bus.h`) accepts every vote as success when no path
  exists. Its callers: KGSL (`adreno.c`, `kgsl.c`, `kgsl_pwrctrl.c`,
  `kgsl_gmu.c`, `adreno_snapshot.c`), MDSS (`mdss_mdp.c`, `mdss_dsi.c`,
  `mdss_dsi_host.c`, `mdss_rotator.c`) and `qseecom.c`. vidc_3x will add a
  fourth client family.
* So DDR/BIMC, SNOC and PCNOC run at whatever the bootloader and RPM left;
  **that rate has not been measured** (no RPM bus clock is exposed).

Idle CPU/GPU measurement taken at the same time (uptime 486 s, screen on,
untouched): one cpufreq policy covers CPUs 0-7 (`related_cpus 0 1 2 3 4 5 6
7`, `schedutil`); `time_in_state` shows 230.6 s at 2784000 kHz (max) and
130.2 s at 480000 kHz; five samples 2 s apart were all 2784000 while
`com.google.android.gms` used 138 % CPU and the system was 597 % idle of
800 %. The GPU was **not** at max: `simple_ondemand`, `cur_freq` 320 MHz,
busy 0 %, `trans_stat` dominated by 100 MHz. Whether missing DDR votes
raise CPU utilisation (memory stalls count as busy time for schedutil) is
**unverified**; section 6 measures it.

## 2. Donor behaviour (the specification)

`../oc-test/arch/arm64/boot/dts/vendor/qcom/msm8953.dtsi`:

* `cpu_cpu_ddr_bw: qcom,cpu-cpu-ddr-bw` (line 1109): `compatible =
  "qcom,devbw"`, `governor = "performance"`, `qcom,src-dst-ports =
  <MSM_BUS_MASTER_AMPSS_M0 MSM_BUS_SLAVE_EBI_CH0>`, `qcom,active-only`,
  `operating-points-v2 = <&ddr_bw_opp_table>` (769, 1611, 2124, 2929, 3221,
  4248, 5126, 5712, 6152, 6445, 7104 MB/s; line 1094).
* `cpu_cpu_ddr_bwmon` (`qcom,bimc-bwmon2`, line 1118) drives it via the
  `bw_hwmon` governor; `cpu0_cpu_ddr_latfloor` (line 1127) is a second
  devbw.
* Driver: `../oc-test/drivers/devfreq/devfreq_devbw.c` (237 lines), votes
  through `msm_bus_scale_client_update_request` with ib/ab in MB/s.
  `bimc-bwmon.c` (1291) and `governor_bw_hwmon.c` (1022) are the monitor.

Upstream `drivers/soc/qcom/icc-bwmon.c` supports bwmon v4/v5 only
(msm8998, sdm845 and later), not msm8953's bwmon2. Leave the monitor out
initially; the donor node's own governor is `performance`, and the power
HAL raises `min_freq` for boosts.

## 3. Upstream provider (already in this tree)

* `drivers/interconnect/qcom/msm8953.c`, compatibles `qcom,msm8953-bimc`,
  `-pcnoc`, `-snoc`, `-snoc-mm` (child of snoc); bindings header
  `include/dt-bindings/interconnect/qcom,msm8953.h` (`MAS_APPS_PROC 0`,
  `SLV_EBI 6`, …). Upstream series:
  https://lkml.iu.edu/2406.3/07778.html (driver),
  https://lkml.rescloud.iu.edu/2406.3/07356.html (binding),
  https://lkml.iu.edu/hypermail/linux/kernel/2504.0/08087.html (DT nodes and
  paths; reviewer asks for the active-only tag on CPU paths).
* Node shapes are also in the postmarketOS reference DT
  `porting/artifacts/tissot-live.dts:1141-1180`: bimc `0x400000 0x5a000`,
  pcnoc `0x500000 0x12080` with clock `pcnoc_usb3_axi`, snoc
  `0x580000 0x16080` with child `snoc-mm`; all `#interconnect-cells = <2>`.
* **sync_state:** `msm8953_noc_driver` has no `.sync_state`
  (`msm8953.c:1311`). In `drivers/interconnect/core.c:956-963` every node
  starts at `init_avg/init_peak` (INT_MAX unless the provider reads the
  hardware) and only `icc_sync_state()` (`core.c:1093`) drops them. So with
  this driver as-is, enabling it pins the buses at maximum: functionally
  safe, but a power cost. **Do not add `.sync_state` until every
  bandwidth-sensitive consumer (GPU, MDSS, CPU devbw, Venus, audio if it
  votes) holds a real vote**, or the display may underrun when the buses
  drop to their minimum.
* Check that the 6.12 RPM clock driver (`qcom,rpmcc-msm8953`,
  `msm8953.dtsi:206`) and `icc-rpm` (bus clocks via `bus_clk_desc`) do not
  both claim the bus clocks.

## 4. Sequence (each step one commit)

* **C1 — provider only.** `CONFIG_INTERCONNECT_QCOM_MSM8953=y`; add the four
  NoC nodes to `msm8953.dtsi` (or the tissot dts if the SoC dtsi is shared
  with other boards; AGENTS rule: board wiring in the board file, SoC
  description in the SoC file). No consumers yet. Boot test:
  `interconnect_summary` lists the nodes; `interconnect_graph` sane; dmesg
  free of `qcom-icc`/`rpm` errors; display, GPU, Wi-Fi and USB unaffected.
  Measure section 6 (expect buses pinned high: possibly better perf,
  higher idle current).
* **C2 — fix the msm-bus shim before giving it paths.** Today it keeps a
  single global `bus_path` looked up as `"gpu_icc_path"` on `bus_pdev`,
  and `bus_pdev` is whichever device last called `msm_bus_cl_get_pdata`
  (`msm-bus-compat.c:87`). Once paths exist, every client (GPU, MDSS,
  qseecom) would vote on one path and overwrite the others. Rework it to
  one `icc_path` per registered client, owned by the device that parsed
  the pdata, looked up from that device's `interconnects` /
  `interconnect-names` (map the donor `qcom,msm-bus,vectors-KBps` src/dst
  masters to msm8953 ICC endpoints with an explicit table), with
  `icc_put` on unregister. Keep the legacy API surface (zero handle on
  failure). Unit-reviewable without a boot.
* **C3 — consumers.** Add `interconnects` to the GPU (gfx3d →
  EBI), MDSS (mdp → EBI) and, when it lands, Venus nodes, using the donor's
  vector tables for the values. Boot test: `interconnect_summary` shows
  non-zero votes from each consumer while active and their drop when idle.
* **C4 — CPU devbw for the power HAL.** Port `devfreq_devbw.c` onto
  interconnect (`icc_set_bw` on `MAS_APPS_PROC → SLV_EBI`, active-only
  tag), with the donor OPP table and default governor `performance`
  (powerhint values above 7104 clamp to the top OPP, as on the donor).
  **ABI:** the power HAL writes the literal path
  `/sys/class/devfreq/soc:qcom,cpu-cpu-ddr-bw/min_freq`. devfreq names its
  class device after the parent device; a DT-instantiated node under this
  port's `soc@0` would be `soc@0:qcom,cpu-cpu-ddr-bw`, which does not
  match. Arrange the exact name (for example a driver-created device named
  `soc:qcom,cpu-cpu-ddr-bw`) and verify the path on the phone. **SELinux:**
  the ROM's vendor policy has no label for this node; check the AVC for
  the power HAL's write and add the minimal rule/label to
  `porting/policy/port-genfs-kgsl.cil` as the KGSL relabel did. Pass: the
  libperfmgr warning is gone and `min_freq` follows touch/launch boosts.
* **C5 — sync_state (last).** Only after C3/C4 votes are verified, add
  `.sync_state = icc_sync_state` (as other upstream icc-rpm drivers do) so
  unvoted bandwidth drops; boot-test display and playback for underruns.
* **Optional C6 — bwmon2.** Port the donor monitor only if C4's
  `performance` + power-HAL boosts measure worse than the donor.

## 5. Review targets

Per-client path ownership and teardown in the shim; ab/ib unit
conversions (donor KBps/MBps vs ICC kBps); active-only vs always tags;
votes held across suspend; RPM bus clock ownership; exact devfreq sysfs
name; no `.sync_state` before all consumers vote.

## 6. Measurements (before C1, after C1, after C5)

Same conditions each time (screen on, untouched 2 min; then screen off
2 min; then the YouTube URL from the video/audio plan for 60 s):

* `/sys/devices/system/cpu/cpufreq/policy0/stats/time_in_state` deltas;
* `/sys/class/devfreq/1c00000.gpu/trans_stat` deltas;
* `/sys/kernel/debug/interconnect/interconnect_summary`;
* `/sys/class/power_supply/battery/current_now` (several samples);
* `dumpsys gfxinfo com.google.android.youtube` janky frames;
* `top -b -n1` to name the load at the time.

This is what decides whether missing DDR votes contributed to the CPU
sitting at 2784000 kHz and to the video lag; do not claim it before.

## 7. Status and donor deviations (2026-10-22, after the C1-C5 review)

The donor (`../oc-test`) is the reference, not the specification: where
it lost a CAF feature or carries a bug, this port records it and adds
the feature on 6.12.

| Donor behaviour | Evidence | This port |
|---|---|---|
| CPU DDR vote held at the top OPP whenever the CPU is active (`cpu-cpu-ddr-bw`, governor `performance`) | `676e1fda9e3a` (2023 third-party change) replaced CAF's `qcom,cpubw` + `governor = "cpufreq"` + `cpu-to-dev-map`; the kept memlat/bwmon monitors point at `performance` nodes and never drive them | CAF's mapping restored as `opp-peak-kBps` on the CPU OPPs + CPU `interconnects` (`6f844d075`); devbw node on `powersave` as the power HAL's boost floor, peak-only vote (`b2134864e`) |
| ROM `init.qcom.post_boot.sh` (msm8953 branch) configures `soc:qcom,cpubw` + `bw_hwmon` | the donor renamed the node, so the script's globs match nothing | not reproduced either; would need the bwmon2 port (below) and a node of that name |
| OPP comments say 769 ... 7104 MB/s | the donor's own `MHZ_TO_MBPS` gives 762 ... 7095 (device `available_frequencies`) | comments corrected in `b2134864e` |
| power HAL boost 9887 rejected (`value > max_freq`) | donor baseline logcat: `Failed to write ... with value: 9887, fd: 13` | 6.12 clamps it to the top OPP |
| MDP bus voting compiled out unless `CONFIG_QCOM_BUS_SCALING` | donor sets it in `msm8953-perf_defconfig:579`; no Kconfig defines it here | guards removed (`410c96756`); verified on #62, the MDP votes 1.1-1.5 GB/s with the screen on |
| vidc_3x `alloc_dma_mem()` returns 0 after releasing the buffer when the iova is truncated, and leaks the mapping | `msm_smem.c:471-474` in the donor | fixed in `62176b8ec` |
| Venus crash: `subsystem_crashed()` only sets `do_ramdump_on_put` | `subsystem_restart.c:1287` | recovery is the driver's own release + reload, unchanged; the crash ramdump is not provided |

Still missing, candidates to add:

* **bwmon2** (`qcom,bimc-bwmon2` at 0x408000, IRQ 183; donor
  `bimc-bwmon.c` + `governor_bw_hwmon.c`): measured CPU traffic on top
  of the frequency mapping, which CAF used via post_boot. Upstream
  `icc-bwmon.c` supports v4/v5 only. Decide on the section 6
  measurements with the mapping in place.
* **Venus crash ramdump.**

Measure section 6 again on the build that carries `6f844d075` and
`b2134864e`: the CPU's DDR request should follow `scaling_cur_freq`
instead of sitting at 7439646 kB/s.

**C5 reverted (`6616a9e08`).** `icc_sync_state` took WLAN and Bluetooth
down from run347 (run346 without it associated on wlan0). Before C5
comes back, these masters need a vote, each verified on a boot:

* the crypto engine for PAS authentication (scm `interconnects` as on
  qcm2290/sm6115, but only with a guard for SCM users that run before
  the scm probe; see the x1e80100 thread, lkml 2603.1/11523);
* WCNSS/Pronto runtime traffic (no node in the msm8953 graph);
* SDCC, USB, BLSP, IPA.
