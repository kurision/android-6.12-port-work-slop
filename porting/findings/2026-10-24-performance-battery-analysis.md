# Performance and battery analysis — port kernel on tissot, 2026-10-24

First performance/battery baseline for the port. No prior dedicated analysis
exists in the repo; the closest prior evidence is the CPU bring-up handoffs
(`HANDOFF-cpu-bringup-2026-10-19.md`, `HANDOFF-cpu-session3-2026-10-20.md`)
which record the DVFS bring-up and the (then-broken) thermal path.
A 4.19 baseline comparison captured the same day is in
[2026-10-24-stock-baseline-perf-comparison.md](2026-10-24-stock-baseline-perf-comparison.md).

## Evidence basis

- Device: Xiaomi Mi A1 (tissot), serial `2819f2320604`, connected via adb,
  **on charger** (`/sys/class/power_supply/usb/online` = 1) for the whole
  sampling window — battery current numbers are charging-state, not idle drain.
- Kernel: `6.12.96-4k-g0286193ba3c8-dirty #47`, built 2026-10-24 14:27 +0545
  (first build after the 6.12.96 LTS sync merge; carries the diag driver
  `0286193ba3`). All sampling was read-only adb shell.
- Uptime at sampling: ~2032 s (~34 min) of mixed user interaction (the user
  was running `flar2.devcheck` during parts of the window).
- Source config referenced: `porting/tools/kernel.config`. Note the
  session-3 handoff warning that the *embedded* config
  (`/proc/config.gz`) can trail the image config, so the source config is
  treated as authoritative for build flags.

Everything below states its own confidence; per repo rules, single-run
observations are labeled as such.

## Headline findings

1. **`sugov:0` burns ~8.3% of one core continuously** and the policy
   frequency bounces between 1.2 GHz and 2.8 GHz within seconds. A healthy
   schedutil governor thread is near-zero. This is a real, measurable
   battery cost at "idle" and the top suspect for the elevated idle load
   (loadavg 1.3–1.9 with ~97% total idle). **Unverified cause** — no
   `schedutil/rate_limit_us` tunable is exposed under
   `/sys/devices/system/cpu/cpufreq/policy0/schedutil/` (the directory
   exists but is empty), which suggests the driver may not be wiring the
   update ratelimit; needs investigation against the qcom cpufreq driver
   and the shared 8-core policy's update path.
2. **The port's diagnostic `ramoops_snap` thread consumes ~1.4% of a core
   permanently** (PID 82, `RAMOOPS_PERIODIC_SNAPSHOTS=1` in
   `fs/pstore/ram.c`, per CURRENT-STATE.md). It is a diagnostic setting,
   and this is its measured cost.
3. **Thermal throttling is wired again.** The run261-era gap ("nothing can
   throttle the CPU", `HANDOFF-cpu-session3-2026-10-20.md`) is fixed in
   this build: `tsens_tz_sensor10/11/12` (CPU sensors) are bound to
   `cooling_device1` = `cpufreq-cpu0` (18 states, matching the 19-entry
   freq table) with `step_wise`, trips at 80/88/100 °C. Not yet exercised
   under sustained load — **throttle behavior under heat is unverified**.
4. **The overclock is the everyday operating point.** Freq residency
   (`stats/time_in_state`, 2032 s window) is bimodal: 93k ticks (~372 s,
   18%) at 2784 MHz and 75k ticks (~300 s) at 480 MHz, almost nothing in
   between. The OC ceiling (2784 MHz vs the stock honest range
   652.8–2016 MHz from the bring-up history) is being used constantly in
   mixed use. Long-term battery and silicon-margin implications are
   unquantified; no voltage table was re-audited in this pass.
5. **Memory pressure is real:** 1.48 GB of 2.65 GB zram swap in use,
   `kswapd0` at ~1% CPU steady-state. Contributes to both performance
   (recompression/refault) and battery.
6. **Wakeup sources look clean:** no persistent wakelock, all
   `active_since`=0, negligible `prevent_suspend_time` across the table.
   Whether the device actually suspends is **unverified** — suspend stats
   show 0 success / 0 fail (no attempts recorded during the screen-on
   window).

## Kernel configuration costs (source: `porting/tools/kernel.config`)

| Setting | Value | Cost |
|---|---|---|
| `CONFIG_KASAN` + `CONFIG_KASAN_HW_TAGS` | on (diagnostic) | Known from history to cost image size (~1 MiB class with UBSAN off); runtime cost on a non-MTE CPU is **unverified** — A53 has no MTE, so hw-tags KASAN may bail at init (no init lines were found in the rotated dmesg). Memory reservation contribution to the 3.6 GiB `MemTotal` (4 GiB part) not attributed. |
| `CONFIG_HZ` | 250 | Good battery default; no change recommended. |
| `CONFIG_PREEMPT` (+`PREEMPT_RCU`, no dynamic) | on | Latency-friendly; negligible cost. |
| `CONFIG_SCHEDSTATS`, `CONFIG_SCHED_DEBUG` | on | Small per-task accounting overhead; fine during bring-up, candidates to drop post-stabilization. |
| `CONFIG_DEBUG_INFO_BTF[_MODULES]` | on | Image size only, no runtime cost. |
| `CONFIG_SLUB_DEBUG` | compiled, off at runtime (`SLUB_DEBUG_ON` unset) | No runtime cost. |
| `CONFIG_UBSAN` | off | Deliberate, image-size driven (measured −1 MiB per memory note). |
| `CONFIG_FTRACE`, `CONFIG_KPROBES` | on, no tracers enabled | Near-zero when idle. |
| `CONFIG_ARM64_SW_TTBR0_PAN` | on | A53 has no ARMv8.1 PAN; software TTBR0 switching on every uaccess is an inherent CPU-generation cost, not a config regression. |

## Measured numbers (charging, mixed use, single window)

### CPU/DVFS

- One shared cpufreq policy (`policy0`, CPUs 0–7, all online), governor
  `schedutil`, table 480 MHz → 2784 MHz (19 OPPs).
- 10 s frequency trace: 2496, 2784, 2208, 2400, 2208, 2400, 1248, 2208,
  2304, 2400 MHz — continuous bouncing, corroborating the sugov load.
- Top thread CPU during sampling: `sugov:0` 8.3–8.4%, `ramoops_snap`
  1.4%, `kswapd0` 1.0–1.1%; total system 6–17% user / 12–23% sys with
  ~76–78% idle across 800% capacity.
- IPI counts (35 min): function-call IPIs ~1.9 M total, resched IPIs
  ~162 k — normal orders of magnitude for Android; no scheduler storm.

### Micro-benchmarks (no stock baseline — absolute capability numbers only)

| Test | Result | Caveat |
|---|---|---|
| `dd 200 MB \| md5sum` | 0.96 s (~208 MB/s) | toybox md5 is not SIMD-optimized; use only for build-to-build A/B. |
| 128 MB write through zram | 487 MB/s | zstd/lzo-rle path, steady-state. |
| 200 sequential process execs | 5.64 s (28 ms/exec) | Includes flash I/O and page cache misses; not a syscall-latency measure. |

### Memory / swap

- `MemTotal` 3.61 GiB, `MemAvailable` 1.51 GiB, `Slab` 405 MiB,
  `ShadowCallStack` 16 MiB, `Percpu` 15 MiB.
- zram: 2.65 GiB disksize, default lzo-rle with zstd recompression
  (`ZRAM_MULTI_COMP`), 1.48 GiB in swap, compressed to ~401 MiB
  (~3.7:1). `mm_stat` recorded in the sampling transcript.

### Battery / power state

- Gauge: `current_now` while charging flipped sign between samples
  (−10 mA … −195 mA … +35 mA) — the fuel gauge is too noisy at low
  current for idle-drain conclusions while plugged in. `capacity` 49%,
  28.5 °C, health Good.
- Wakeup sources: nothing above noise (largest: `event3`, 2400 acquires
  over 34 min, 525 ms total active). No `prevent_suspend_time`.
- Suspend: `/sys/power/suspend_stats` exists, `success`=0, `fail`=0 —
  no suspend attempt recorded during the screen-on window. **Deep-sleep
  (mem) capability of the port remains untested** and is the single
  biggest unknown for real battery life.

## Recommended next measurements (in order)

1. **Suspend test (unplugged, screen off):** wait for idle, confirm
   `success` increments and measure overnight drain. This decides whether
   the port can be a daily driver at all from a battery standpoint.
2. **Idle-drain A/B, charger unplugged:** 30 min screen-off baseline vs
   `RAMOOPS_PERIODIC_SNAPSHOTS=0` build; isolates the `ramoops_snap`
   cost in mA.
3. **Chase the sugov load:** check the qcom cpufreq driver's
   `rate_limit_us` wiring and whether every core's tick triggers a
   shared-policy update; compare with the donor 4.19 behavior.
4. **Thermal load test:** sustained 8-core load, watch
   `tsens_tz_sensor10-12` temps and `cooling_device1/cur_state` engage
   before 100 °C trips; verifies the fixed cooling path end-to-end.
5. **Post-stabilization config shed:** KASAN off, SCHEDSTATS/SCHED_DEBUG
   off — then repeat the micro-benchmarks for the honest daily-driver
   numbers.

## Raw command trace

All values above were captured via read-only adb shell against serial
`2819f2320604` on 2026-10-24 ~15:00–15:20 +0545: `uname`, `top`/`ps -AT`,
`/sys/devices/system/cpu/cpufreq/policy0/*` (incl. `stats/time_in_state`),
`/sys/class/thermal/*`, `/sys/class/kgsl/kgsl-3d0/*`,
`/sys/class/power_supply/*`, `/sys/kernel/debug/wakeup_sources`,
`/sys/power/suspend_stats`, `/proc/meminfo`, `/proc/swaps`,
`/sys/block/zram0/*`, `/proc/interrupts`, `/proc/vmstat`, timed
micro-benchmarks. No writes to the device; no settings changed.
