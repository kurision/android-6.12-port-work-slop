# Live component audit — 2026-10-18, after run234

## Identity and limits

Evidence directory: `../artifacts/snapshot60/live-audit-20261018T143526Z/`.
All evidence references below are relative to that directory unless specified.
The port identified itself as `6.12.93-4k #22`, build time Oct 18 16:37:36
+0545, boot ID `8dff5d55-967f-4d5c-afc9-1d23e46b1ff6`, uptime about
12,461–12,570 seconds. Android boot completion was 1; SELinux enforcing.
The precise boot-image hash was not established from the running device.
Do not assign this live boot to run232 solely from the user's description.

Read-only ADB collection, repeated samples, no build/flash/reboot/settings
changes. Shell was UID 2000; `su` was unavailable. Kernel dmesg, several
sysfs attributes and remoteproc state were permission denied. Permission
denied is not a component failure. Dumps were collected during user activity;
the initial parallel capture and other host-side activity contaminate any
claim of an idle baseline. No stock-versus-port performance benchmark exists.

The user subsequently returned the device to stock. Confirmed stock identity:
`4.19.325-cip136-st20-perf-mglru-next-g5835eacd666d`, boot ID
`6ee5491b-18f0-4ee5-a59a-f53c72610cc6`; `su -c id` gives UID 0,
`u:r:magisk:s0`. Stock has Magisk 30.7 (30700).

## CPU and performance: confirmed gaps, not a single-core kernel

- **Eight CPUs online and doing work.** `cpu.log:1-79` reports possible,
  present and online `0-7` and eight Cortex-A53 processor records.
  Per-CPU user/system counters advance on every CPU (`cpu.log:132-156`,
  `followup.log:66-90`). Foreground/top-app/background cpusets are all `0-7`
  (`cpu.log:169-171`). No evidence of a one-core scheduling restriction.
- **CPUFreq policies absent**, reproduced in `cpu.log:81-83` and
  `followup.log:4-8`. Live config has CPU_FREQ and schedutil but no
  CPUFREQ_DT / QCOM CPUFreq drivers (`config.log:664-691`). Current source
  CPU nodes lack clocks and OPP references (`arch/arm64/boot/dts/qcom/msm8953.dtsi:41-119`).
  Run188 already recorded the same issue (`../FAILING-COMPONENTS.md`, run188
  CPU row); commit `c94f76c81` explicitly records no CPU clock/cpufreq driver.
  This is not established as a new run232 regression. The diagnostic app's
  exact reason for showing one core remains unverified; missing frequency
  interfaces do not prove how that app counts cores.
- **CPUIdle driver absent:** `followup.log:8` is `none`; all eight per-CPU
  cpuidle directories are missing (`cpu.log:84-131`). PSCI CPUIdle is built,
  but current CPU nodes have no idle-state references. This does not mean
  architectural WFI is absent or prove that system suspend fails.
- **Important historical workaround:** `fs/pstore/ram.c:2152-2178` directly
  switches the CPU4–7 mux; called at `:2226-2228`. Commit `91c057f47`
  describes the run121 experiment. `../artifacts/snapshot60/run233-logdump.log:160-180`
  reproduces the before/after mux and loop measurements. Its printed zero
  frequency means unknown for that source, not a stopped CPU. Do not claim a
  present-day MHz value from those old, coarse loop measurements.
- **Power HAL GPU controls blocked by SELinux**, not simply missing:
  `logcat.log:2-14` includes writes denied to max/min_pwrlevel and force
  controls, source `hal_power_default`, target generic `sysfs`.
  libperfmgr also fails CPU frequency and DDR bandwidth paths. Repair labels
  and ABI paths only after tracing actual devices/policy; do not disable SELinux.
- **Diagnostic and retry overhead:** in follow-up top samples, adsprpcd uses
  15.5–17.5% and ramoops_snap 12.5–15% of ONE CPU
  (`followup.log:98-154`; top totals are scaled to 800%). Repeated, measurable
  overhead, not proof of the user's sluggishness. Do not stop evidence
  collection threads before a replacement kernel-log channel is established.
- **No active swap:** SwapTotal 0 (`performance.log:45-46`), no zram block
  device (`followup.log:156`); ZRAM is a module (`config.log:2081`). About
  953 MB MemAvailable in the first sample, so this is not proof of OOM or
  memory pressure causing the slowdown.
- **Interconnect coverage gap:** INTERCONNECT_QCOM_MSM8953 unset
  (`config.log:7503`), and perf HAL bandwidth writes fail. Functional effect
  and current DRAM/NoC rates unverified.

## Component inventory

| Component | Fresh evidence | Verdict / limits |
|---|---|---|
| GPU / display | `gpu.log:26-34`, `status-followup.log:135-138`: Adreno 506 GLES 3.2; HWC missed-frame count 28996 → 29034, GPU count stays 593 | Rendering baseline retained from run234 and user-visible usability. Frame misses occur, but counts are cumulative, not a controlled jank rate. GPU clock/power reads denied; no claim it remains pinned low. |
| FastRPC / ADSP userspace ABI | `logcat.log:24-36` and `logcat-followup.log:5-82`: repeated Inappropriate ioctl for device; adsprpcd remains running | **Broken transactions**, reproducing run149+ history / `0df15065a`. In the first ~43 s log window, 844 listener-open errors. Do not assume one missing ioctl or conclude all DSP services fail. |
| Audio | `audio.log:91`: AudioPolicyManager 0x0; `nodes.log:57-58`: only ALSA timer; 427 listAudioPorts failures in ~43 s; repeated in `status-followup.log:39` and follow-up logcat | **Audio initialization broken.** Separate sound-card/codec/HAL and FastRPC problems must be traced independently; fixing adsprpcd alone is not established as sufficient. |
| Cameras | `camera.log:4-15`, `status-followup.log:4-15`: zero devices; qcamerasvr restarting in `wifi.log:42`, `status-followup.log:152`; no video/media nodes | **Unavailable.** End-to-end camera stack not exposed; exact daemon exit cause not captured. |
| Bluetooth | `bluetooth.log:31` reports 10 crashes; `status-followup.log:74-88` records an additional crash, total 11 | **Repeatedly crashes**, not merely switched off. Exact transport/HAL crash cause unverified. |
| Wi-Fi | No WLAN interface in two listings; `wifi-errors.log:1-13,31-33` records repeated station-start failures and 7 interface-setup failures attributed to HAL | **Station initialization fails.** Current framework says disabled, which alone would not prove failure. Do not carry the old missing-firmware diagnosis forward without rooted remoteproc/firmware evidence. |
| Cellular / modem | `logcat.log:74-92` and later lines: ALLOW_DATA error 2 repeats; `status-followup.log:154-159`: blank baseband/SIM values, unknown network types, no device bound in qcom-q6v5-mss driver directory | **Radio initialization unresolved / failing requests.** Modem DT is historically disabled; calls/data/SMS/GNSS were not functionally tested. No inferred SIM diagnosis. |
| SoC thermal / Android thermal HAL | `power.log:31-39`: only PMIC, battery and bms zones; `config.log:3695`: TSENS unset; `performance.log:89`, `status-followup.log:132`: HAL Ready false | **SoC TSENS coverage absent; Android thermal HAL not ready.** PMIC/battery readings exist. Does not establish overheating or absence of firmware protection. |
| Fingerprint | `fingerprint.log:4,14`: one HAL death and crash-state history; expected Goodix/FPC nodes absent in sampled names | **Prior failure recorded; current authentication unverified.** Identify fitted sensor and capture HAL failure before proposing a driver. |
| Accelerometer / ambient light | `sensors.log:112-163,175-224` and `sensors-followup.log:112-224`: advancing timestamps and changing values | **Live data reaches Android.** Old blanket "sensors off" status is stale. No physical calibration test. |
| Gyroscope / magnetometer / proximity / fusion | Sensors advertised; gyro has earlier event history (`sensors.log:164-174`) | **Not fully tested**, not automatically broken because no local IIO driver was ported. DSP sensor path is distinct from adsprpcd. |
| Battery / gauge / charger | `power.log:1-24`, `status-followup.log:97-120`: real readings, USB present, charging status 2; three supplies exist | Telemetry works, historical charging fix retained. Counter falls 1487744 → 1485016 while status says charging, USB limit 100000 µA; **net charge gain/rate not validated**, possible load exceeding input. Do not reopen the solved charging-HAL registration issue. |
| Touch / keys | User can operate device | Basic usability reported; multitouch, all keys, gesture/wake tests outstanding. |
| Haptics | `vibrator.log:47-64`: HAL advertises vibrator/effects | Physical vibration untested; service presence is not proof. |
| Storage / microSD | `/data` mounted with ~34 GB free (`performance.log:76-77`) | eMMC works for Android; microSD read/write, suspend/resume and corruption checks untested. |
| USB | ADB works repeatedly on the port | Peripheral ADB works; OTG/host/role switching untested. |
| Ashmem | `nodes.log:9`, long-running boot/system_server | Present; no recurrence of run186 missing-ashmem boot blocker. |
| IR / notification LED / security | LED node exists; no sampled IR nodes; no keymaster exercise | IR historically unported; LED output, keystore/gatekeeper and FBE remain unverified. |

## Research and next checks

Cross-checked current upstream [CPUFreq](https://docs.kernel.org/admin-guide/pm/cpufreq.html)
and [CPUIdle](https://docs.kernel.org/admin-guide/pm/cpuidle.html) documentation,
and AOSP `android16-6.12` CPUFreq documentation / FastRPC UAPI. Source captures:
`aosp-cpufreq.txt`, `aosp-fastrpc-uapi.txt`, `upstream-fastrpc-uapi.txt`.
CPUFreq needs a registered scaling driver; online CPU count and policy count
are different. Current upstream FastRPC ioctl 12 is SET_OPTION, not evidence
that CAF ioctl-12 CONTROL is compatible. Read full local history before changes.

Priority: obtain root safely on a copy of the exact known-good image; establish
live kernel logs; capture CPU clock/OPP and idle initialization, deferred probes,
remoteproc state and policy labels. Then investigate CPUFreq/clock coverage and
power-HAL controls, followed by retry-loop overhead. Preserve baseline evidence
before changing diagnostics. Compare against rooted stock and the actual
known-good artifact, not a reconstructed ramdisk. No kernel build is authorized
by these notes.
