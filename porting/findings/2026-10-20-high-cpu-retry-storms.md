# High CPU on the running phone: measured cause is ROM retry loops over missing kernel features

**Date:** 2026-10-20 · **Tree:** `ack-kgsl` (6.12.93) · **Device:** tissot,
run294 on the phone, uptime ~10 min at the time of the measurement.

## What it settles

Removing the port's own logging and snapshots does **not** reduce the CPU
load, because the load is not in the logging path. It is a set of ROM-side
retry loops, each of which exists because this port does not yet provide the
kernel feature the ROM expects.

Measured on the phone, 10.25 s window, per-task CPU from `/proc/<pid>/stat`
deltas (HZ=100):

| task | CPU-s / 10 s | user | sys |
|---|---|---|---|
| `system_server` (pid 931) | 2.23 | 0.58 | 1.65 |
| `composer@2.1-service` (pid 698) | 2.22 | 0.22 | 2.00 |
| `[mdss_fb0]` (pid 724, stuck in D) | 1.78 | 0.00 | 1.78 |
| `init second_stage` (pid 1) | 1.44 | 0.09 | 1.35 |
| `kcompactd0` (pid 87) | 1.39 | 0.00 | 1.39 |
| `nexuslauncher` | 1.14 | 0.89 | 0.25 |
| `surfaceflinger` | 0.74 | 0.50 | 0.24 |
| `[sugov:0]` | 0.66 | 0.00 | 0.66 |

Total 14.68 CPU-s out of 80 CPU-s available = **18 % of the machine**, and it
is dominated by *system* time (113 % of 800 % in `top`, i.e. ~1.2 cores in
kernel mode).

The port's own initramfs processes are **not** part of this: the diag
initramfs children (pids 212/213/214/215/227) used 0.03 CPU-s in the same
window. Removing the log writes therefore cannot help, which matches what was
seen on the phone.

## The retry loops, and the kernel feature each one is missing

Counted over the last ~3000 logcat lines:

| count | loop | missing kernel feature (verified on the phone) |
|---|---|---|
| 276 | `AudioSystem: listAudioPorts failed` (10 Hz, `system_server` pid 931 thread 1461) | **no sound card at all**: `/proc/asound/cards` prints `--- no soundcards ---`, `/sys/class/sound` holds only `timer` |
| 310 | `PhoneSwitcher: resend modem command` / `RILJ: ALLOW_DATA error 2` | **no modem/rmtfs**: no `/dev/rmtfs*`, no `/sys/class/rmtfs`, nothing modem-related in `dmesg` |
| 141 | `libperfmgr: Failed to write to node` (`soc:qcom,cpu-cpu-ddr-bw/min_freq`, `/proc/sys/dev/xiaomi_msm8953_touchscreen/enable_dt2w`) | **only one devfreq node** (`1c00000.gpu`); no CPU devfreq, no `soc:qcom,cpu-cpu-ddr-bw`; no Xiaomi touchscreen DT2W sysctl |
| 29 | `HidlServiceManagement: Waited one second for vendor.qti.data.factory@2.0` | vendor-side data HAL never registers (not a kernel gap) |
| 20 | `flags_health_check: ... updatable crashing detected` (new pid each time) | GMS "updatable" module crash-looping; a consequence of the gaps above |
| 1+ | `Bluetooth HAL died` → `com.android.bluetooth` SIGABRT, service restarted | **no Bluetooth in the kernel**: no `/sys/class/bluetooth`, zero bluetooth lines in `dmesg` |

### Audio, in detail

`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts` has the ingredients but
not the machine:

* `&lpass` is enabled (line 450),
* `max98927_codec: audio-codec@3a` on `i2c_2` (line 160),
* the drivers are built: `CONFIG_SND_SOC_MAX98927=y`,
  `CONFIG_SND_SOC_MSM8952=y`, `CONFIG_SND_SOC_MSM_WCD9335=y`,

but there is **no `sound` node and no `mss`/DAI node** in the board file, and
no `msm-asoc-card` template exists anywhere in `arch/arm64/boot/dts/qcom/`
for this SoC. So the DAI never registers, no card is created, and
`AudioFlinger::listAudioPorts()` fails forever at 10 Hz.

That single gap is the largest CPU item on the phone: `system_server` burns
1.65 CPU-s of *system* time per 10 s retrying it.

### Memory pressure is a consequence, not the cause

`MemFree` was 119–233 MB of 3607 MB, swap 590–797 MB of 2705 MB used, and
`kcompactd0` burned 1.39 CPU-s/10 s (100 % system) compacting pages. `Slab`
is 775 MB with 492 MB reclaimable, and `CmaFree` is 0 of 40960 kB. The
zram device itself is healthy (`mm_stat` reports 0 failed writes), so the
compaction is the system reacting to the churn the crashing services create,
not a zram fault.

## Why the display stack shows up

`[mdss_fb0]` is in D state and burns 1.78 CPU-s/10 s, and
`composer@2.1-service` burns 2.00 CPU-s of system time per 10 s. The
display is being kicked at ~30/s (`DIAG123 kickoff count` advances 600 per
20 s) and the HAL is waiting on it. The port's `DIAG123` prints are already
rate limited to every 600th kickoff, so they are **not** the cause - they
are only the visible symptom that the display path is busy.

## What the logdump partition does when it fills

The partition is 64 MiB (`mmcblk0p48`, 131072 sectors) and the recorder caps
its own text at 60 MiB (`LOGDUMP_TEXT_LIMIT`, `scripts/initramfs-diag/init.c`),
so it can never reach a real `ENOSPC`:

* `write_all_limit()` refuses to write past the budget and returns `-1` with
  `errno=ENOSPC`;
* on that failure `write_capture()` retires the primary sink (`out = -1` in
  `dump_log()`), then tries the SD mirror `/sdlog/ack-kmsg.log`;
* if the mirror also fails, `sinks_dead()` makes `dump_log()` return and the
  recorder exits after writing `DIAG: Android capture failed`.

Consequences of the recorder exiting:

* nobody reads `/dev/kmsg` any more, so the printk ring fills and the kernel
  starts dropping messages (`printk: message dropped`). The rest of that
  boot's kernel log is lost; the phone keeps running;
* **there is no busy loop.** A full partition does not burn CPU: the
  recorder blocks in `read()`/`write()`.

Two related facts that matter when reading a logdump:

* the capture window is 900 s. After that the recorder writes
  `DIAG: EOF Android kmsg dump complete` and exits, so a logdump only ever
  covers the first 15 minutes of a boot;
* the partition is opened `O_WRONLY` **without** `O_TRUNC`, so each boot
  overwrites from offset 0 and the tail of the previous boot's text survives.

The only I/O the recorder adds is `fsync()` after every captured chunk
(`durable=1`) plus the ramoops sampler reading 1 MiB every 2 s. That is a few
flushes per second, not a CPU load.

## Work list, in the order the measurements justify

1. **Audio machine**: add the `sound` node to
   `msm8953-xiaomi-tissot.dts` (msm8952 asoc card, Q6 DAI, MAX98927,
   WCD9335, pinctrl) - needs the 4.19 donor topology as the reference; no
   in-tree template exists. Biggest single win (276 failures/10 s plus
   `system_server` at 37 % CPU).
2. **Modem/rmtfs**: port the rmtfs/mdm subsystem from the donor so the
   modem subsystem exists (310 retries/10 s).
3. **devfreq**: add the CPU devfreq and the DDR bandwidth devfreq node under
   the exact name the ROM's perf HAL expects,
   `soc:qcom,cpu-cpu-ddr-bw`, and the
   `/proc/sys/dev/xiaomi_msm8953_touchscreen/enable_dt2w` sysctl
   (141 failed writes/10 s).
4. **Bluetooth**: the kernel has none at all, so the ROM's BT HAL dies and
   the bluetooth service crash-loops.
5. Re-measure with the same method (per-task `/proc/<pid>/stat` deltas over
   10 s) after each step; expect `system_server`, `init second_stage`,
   `[mdss_fb0]` and `kcompactd0` to drop as the retry loops disappear.
