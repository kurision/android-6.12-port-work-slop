# Stock-baseline performance comparison — port 6.12 vs 4.19 st20-perf, 2026-10-24

Companion to
[2026-10-24-performance-battery-analysis.md](2026-10-24-performance-battery-analysis.md),
which had no baseline to compare against. This adds the baseline side and the
first honest A/B.

## Evidence basis

- Baseline device state: the user flashed and booted their maintained 4.19
  daily-driver kernel — **`4.19.325-cip136-st20-perf-mglru-next-gdf4a1f863991
  #5`** (user-built, clang 21, MGLRU enabled). This is *not* OEM stock; it is
  the comparison kernel the port should ultimately beat.
- Port side: `6.12.96-4k-g0286193ba3c8-dirty #47` from the earlier analysis.
- Raw captures: `porting/artifacts/snapshot60/stock-perf-20261024T*/`
  (01-cpu-thermal.txt, 02-power-mem.txt, 03-settled-state.txt,
  04-benchmarks.txt; gitignored).
- Method parity: same serial (`2819f2320604`), same adb read-only sampling,
  same benchmark commands, both sessions **on charger**, screen on, load
  allowed to settle (port sampled at ~2032 s uptime / load 2.09; stock at
  ~798 s / load 2.08). Battery current is charging-state on both sides, so
  idle-drain comparison is still not possible.
- All deltas below are single-window observations. The exec benchmark and
  the governor-thread cost repeat twice with consistent numbers; everything
  else is one sample.

## Config deltas that matter (from live `/proc/config.gz` on both)

| Setting | Port 6.12.96 | Baseline 4.19 | Expected effect |
|---|---|---|---|
| `CONFIG_HZ` | 250 | 100 | Port takes 2.5x the timer ticks; feeds per-tick work incl. schedutil updates. |
| KASAN | `KASAN_HW_TAGS` on (diagnostic) | off (`KASAN_STACK=0` remnant only) | Allocation-path cost + memory reservation on the port. |
| LRU | standard | `LRU_GEN=y` + `LRU_GEN_ENABLED` (MGLRU) | Baseline has MGLRU reclaim; the 6.12 tree also carries MGLRU-capable mm but `CONFIG_LRU_GEN` was not found enabled in the port's live config — **unverified**; worth a config check. |
| PAN | `ARM64_SW_TTBR0_PAN` on | `ARM64_PAN=y` + `ARM64_SW_TTBR0_PAN=y` | Baseline sets both; software-PAN cost is common to both, so not an A/B factor. |
| `SCHEDSTATS` | on | on | Even. |

## Measured A/B

| Metric | Port 6.12.96 #47 | Baseline 4.19 st20 | Verdict |
|---|---|---|---|
| `sugov:0` thread CPU | **8.3–8.4%** of one core, twice sampled | **0.3%** | **~27x governor-thread burn on the port.** Same schedutil, same 19-OPP OC table (480 MHz–2784 MHz), same single policy0 over CPUs 0-7 on both, and neither exposes a `schedutil/rate_limit_us` tunable — so the empty-tunable directory is not the differentiator. The port's qcom cpufreq driver is firing updates ~27x more often. Top suspect for the elevated idle load and a real battery cost. |
| `ramoops_snap` thread | 1.4% (disabled in source by `e20f8035e2`, not yet built/booted) | n/a (feature does not exist) | Reclaimed once a post-`e20f8035e2` build is flashed. |
| 200 sequential execs | 5.64 s (28.2 ms/exec) | **3.34 s (16.7 ms/exec)** | **Port is ~1.7x slower** on fork+exec+page-in. Candidates, unverified: KASAN_HW_TAGS allocation cost, HZ=250 timer pressure, heavier 6.12 fork/exec paths, or the port's larger swap pressure (1.48 GiB vs 1.15 GiB in zram). Needs a controlled re-run (ideally KASAN-off build) before attributing. |
| md5 of 200 MB stream | 0.96 s | 0.95 s | Tie — pure compute+memcpy at boosted freq is equivalent. |
| 128 MB write through page cache | 487 MB/s | 506 MB/s | Within noise; memory bandwidth is not the problem. |
| kswapd0 | ~1.0–1.1% at 34 min uptime | 3.7–13.1% at 6–13 min uptime | Not comparable yet — stock was still settling from boot with app restore. Re-sample at matched uptime. |
| zram swap in use | 1.48 GiB (lzo-rle+zstd recomp) | 1.15 GiB (lzo default, zstd avail) | Port holds ~29% more swapped pages in a similar session; consistent with KASAN's footprint and different usage length. Compression ratio similar (~3.7x both). |
| Resched IPIs (IPI0) | ~78/s avg | ~2063/s avg | Not comparable — stock window had active UI interaction. Function-call IPIs ran the other way (~913/s port vs ~116/s stock); both consistent with workload difference, not evidence of a defect. |
| Wakeup sources | clean, no `prevent_suspend_time` | clean (`wlan` 108 ms total is the largest) | Even; no wakelock abuser on either side. |
| Suspend stats | 0 attempts (screen on) | 0 attempts (screen on) | Deep sleep remains **untested on both** — the overnight unplugged screen-off test is still the decisive battery experiment. |
| Fuel gauge while charging | `current_now` flips sign between samples (−10 mA … −195 mA … +35 mA) | stable positive (+453 mA charging) | Same `qpnp-fg` hardware reads sanely on 4.19 but is erratic on the port — the 6.12 `qpnp-fg` port's current reporting is suspect (calibration, sign convention, or sampling path). Fixing this is a prerequisite for any port-side battery measurement. |
| Thermal mitigation | CPU tsens zones bound to `cpufreq-cpu0` cdev, trips 80/88/100 °C | separate `*-usr` zones (`apc0-cpu*`, `apc1-l2`), mitgov-style | Different frameworks; both wired. Under-load throttle behavior unverified on both. |

## Follow-up: memory subsystem measurement (user-provided, same day)

User-reported numbers from the stock (4.19) boot, benchmark tool unrecorded:

- **CPU→DRAM bandwidth: 7095 MB/s.** SD625 ships single-channel LPDDR3-1866
  (theoretical ~14.9 GB/s = 1866 MT/s × 8 B), with practical single-channel
  stream results on this memory class typically ~5.3–7.5 GB/s
  (nanoreview/versus listings). 7095 MB/s is ~48% of theoretical — squarely
  normal for LPDDR3 stream efficiency on Cortex-A53.
- **cpu0→DRAM latency floor == cpu4→DRAM latency floor.** The two A53
  clusters both hang off the CCI-500 interconnect to a single memory
  controller, so there is no cluster-local memory advantage to find —
  equal floors are the expected hardware truth, and this measures it.

Implications for the port comparison:

1. Memory subsystem parity is confirmed from the hardware side; the port's
   1.7x exec-latency gap is not a DRAM bandwidth problem.
2. Scheduler placement on this SoC has no memory-locality dimension —
   cluster choice affects power/thermal headroom, not latency. Nothing to
   gain from cluster-affine placement work in the 6.12 port.
3. The port's remaining performance levers are the ones already identified:
   the sugov churn and the housekeeping-thread costs, not memory.

## Follow-up: dual-phase frequency traces (same day, ~10:00 +0545)

After the table above, the baseline was traced at 2 Hz through three phases on
one continuous session (`06-freq-trace-dual-phase.txt`,
`07-freq-trace-screenoff-idle.txt`): ~3 min in use, ~3 min untouched with the
screen on, ~3 min screen-off/dozing. Aggregate CPU busy fell 18.2% → 8.4% →
3.6% across the phases, and the requested frequency's median fell
2304 → 1958 → 1804 MHz with max-bin residency 45% → 22% → 13%.

Two corrections and one caveat came out of it:

1. **Residency percentages corrected.** The port's full `time_in_state`
   sums to ~179k ticks (~716 s) — the top bin (2784 MHz) is **52% of
   accounted time and the 480 MHz floor 42%**, not the "72%" first quoted
   (an addition error). The baseline's table covers ~100% of its 952 s
   session: floor 62%, max 26%, mid steps 12%. The directional conclusion
   is unchanged and now arithmetically checked: stock's floor:max ratio is
   2.4:1, the port's is 0.8:1 — the port really does live nearer the top.
   The port table covering only ~35% of its session remains unexplained
   (likely busy-time-only accounting in the 6.12 stats path).
2. **`scaling_cur_freq` is misleading during light load.** Even fully
   dozing (3.6% busy), the live readout never reported the 480 MHz floor —
   the 2 Hz sampler's own wakeups keep the cluster out of deep idle and
   pin the last requested frequency. Any live-trace methodology must
   account for this observer effect; `time_in_state` is the authoritative
   view of where time went.
3. The 2 Hz trace data and the phase timing chart are captured in
   `porting/artifacts/snapshot60/stock-perf-20261024T*/`; the same capture
   is to be repeated on the port with
   `porting/tools/freq-phase-trace.sh` (uses + idle + screen-off, one run
   per phase) after the next port flash.

## Conclusions

1. **The port's biggest measured defect is the `sugov:0` burn (8.3% vs 0.3%).**
   It is port-specific, reproducible in two samples, and cheap to chase:
   instrument the 6.12 cpufreq driver's update path (possibly per-CPU tick
   updates against the shared policy, or the missing ratelimit wiring noted
   earlier). Fixing it likely removes most of the port's elevated idle load.
2. **The exec-path gap (1.7x) is the second real target.** Re-run after a
   KASAN-off, post-`e20f8035e2` build; if the gap persists, profile
   `do_fork`/`exec` on-device (simpleperf is present on the baseline; the
   port has `PERF_EVENTS=y`).
3. **Compute and memory bandwidth are at parity** (md5, dd). The port's raw
   speed is fine; its overheads are in housekeeping threads and hot kernel
   paths.
4. **Battery conclusions remain blocked** on: (a) the erratic port fuel-gauge
   readings, (b) untested deep sleep on both kernels. Both are prerequisites
   before any mA comparison means anything.

## Re-run checklist for the next port build

Flash a post-`e20f8035e2` build and repeat: sugov PCPU over 10 s, the 200-exec
benchmark, `current_now` stability while charging, and — if possible — one
unplugged screen-off suspend/overnight drain window on each kernel.
