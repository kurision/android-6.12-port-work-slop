# Handoff: MSM8953 CPU bring-up, session 3 (2026-10-20)

> **Superseded.** The current state is [CURRENT-STATE.md](CURRENT-STATE.md); the
> successor to this handoff is [HANDOFF-cpu-session3-2026-10-20.md](HANDOFF-cpu-session3-2026-10-20.md).
>
> The per-run evidence this document cites (boot images, kernel directories,
> init binaries, logdumps) is no longer in the repository; it is
> git-ignored and disposable, and the boot images are in
> ../ack-kgsl-artifacts.

**Read this file first.** It supersedes
`HANDOFF-cpu-session2-2026-10-19.md`; the run-by-run evidence is in
`findings/cpu-boot-failure-analysis-run265-2026-10-19.md`, which itself
lists the older files it supersedes.

Repo: `/home/kurision/development/kernel/ack-kgsl` (Linux 6.12.93-4k / ACK,
arm64, board `msm8953-xiaomi-tissot`). Donor tree with the hardware truth:
`/home/kurision/development/kernel/oc-test` (CAF 4.19, boots this phone).
Device serial `2819f2320604`.

Commits on top of the previous session:

| Commit | What |
|---|---|
| `536be9adb` | the kgsl fence-release diagnostic, on the path the display actually waits on; the port's DIAG console output bounded |
| `ff4000f0c` | the run265-267 evidence, the corrected facts, the boot procedure |
| `2718207ed` | the previous session's uncommitted SPM/regulator/diag-gadget work, kept in the tree |

## 1. Where we are

The port boots to the ROM and the display works. Two separate faults are
left, and this session established that they are separate:

1. **An intermittent early death.** In ~1 of 3 port boots the kernel
   freezes in the first 1-9 s, the phone is backlit and unreachable, it
   reboots itself about two minutes later, and the logdump is all zeros
   because the hang happens before the logdump sink exists (the snapshotter
   is ready at t=8.98 s; the APCC handoff is at t=8.07 s).
2. **An intermittent GPU stall.** The GPU stops retiring work, the display
   drops every frame that waits on the GPU fence, the Android display HAL
   turns that into a retry loop in system_server, and the phone dies of
   power/heat - run261 at ~326 s, run265 at ~581 s.

**Neither fault is a code regression.** Runs 261, 262, 263, 264, 266 and
267 all carry the same kernel payload or a strict superset of it, and the
successes and the failures are interleaved.

## 2. What is proven, with evidence

| Claim | Evidence |
|---|---|
| The last successful *scripted* boot was **run261**, not run262 | `run261-live/adb-timeline.jsonl`: 42 sightings of `6.12.93-4k`, `policy0` at 2016000 kHz, `/dev/ashmem`, `sys.boot_completed=running`, back on stock at t=453 s. run262/263/264 never enumerated and their logdumps are 0 bytes. |
| No code change separates the successes from the failures | `package-run261/262/263/264.json`: all six carry `kernel_payload_sha256 = 59eb2793a5f7993002f544864f18e46250f51395f1eec8b69b802374bfe33d15` and the same ramdisk and init. run263's image SHA256 equals run261's exactly. Only cmdline tokens differ (`cpufreq.off=1` in run262, `console=tty0` in run264, none in run263). |
| The APCC handoff works and is deterministic | `run265`/`run266`/`run267` logdumps: identical `boot state: pll 00000000 ... mux 00000401 00000000 00000403`, identical `shared CPU/CCI domain, speed bin 2, CPU 799999804 CCI 399999902 Hz, corner 2`, identical `cpufreq_online ... changing to: 1036800 KHz`. No `CPU transition to N Hz failed` in any boot. |
| The CPU is **not** saturated | run267 at 190 s: `cpu 18172 5408 28895 133356 6461 1936 467` = 67 % idle system-wide, ~86 % idle per core, load 4.61 on 8 CPUs. run265 at 123 s: 84 % idle, load 5.51. The "load average 63" of the stalling boots is **uninterruptible sleep**: `dma_fence_default_wait()` sleeps in `TASK_UNINTERRUPTIBLE`, so every thread waiting on the never-signalled fence is a D-state task. |
| A monitor's "CPU 100 %" is the **frequency**, not the utilisation | `scaling_cur_freq` is 2016000 kHz in every sample of every boot; `time_in_state` at 123 s put 9187 of 11620 ticks (79 %) at the top OPP, while the machine was 84 % idle. |
| Nothing can throttle the CPU | `run261-embedded.config:3697`: `# CONFIG_QCOM_TSENS is not set`. The thermal zones exist (`msm8953.dtsi:1985`) and the governors are registered, but the CPU nodes (`msm8953-cpu.dtsi:640-684`) have no `#cooling-cells`, so the zones' `cooling-device = <&CPU0 ...>` points at a node that is not a cooling device. The donor has `#cooling-cells = <2>` on all eight CPU nodes. The build takes its config from the **previous image's** embedded config, not from the defconfig, so the defconfig's `CONFIG_QCOM_TSENS=y` is dead. |
| The GPU really stops retiring work | run265: the kgsl interrupt rate fell 46/s -> 1.8/s while the machine stayed 52-84 % idle. run266/run267: steady 62/s. |
| The display's fence was retired but never signalled | run261: `mdss_wait_sync_fence: drv:kgsl-timeline ... seqno:530304 timeline:532096 queued:532096 retired:532096 status:0x1` then `sync_fence_wait failed! ret = ffffff92`. `status:0x1` is the fence's own `->signalled` callback saying "retired"; the dma-fence core bit, which `dma_fence_wait_timeout()` only looks at, was never set. |
| The fence release path | `adreno_dispatcher_work()` -> `kgsl_process_event_groups()` -> `_process_event_group()` -> `kgsl_sync_fence_event_cb()` -> `kgsl_sync_timeline_signal()` -> `dma_fence_is_signaled_locked()` -> `dma_fence_signal_locked()`. The **GPU dispatcher** is the only thing that can release the display's fence. |
| The instrument is on the right path and works | run267: 401 `DIAG sync_timeline_signal` from 60.6 s to 437.8 s, plus `sync_fence_event`, `event_group` and `dispatcher_timers`; `pending` between 1 and 119, `stale=1` never, `signalled=0` in 12 of 401. run266 proved the *previous* path (kgsl_timeline.c) is never used by this ROM's compositor. |
| The CPU burn is PowerManagerService | the user's logcat: `DIAG signal_generate sig=7 code=2 sender_pid=925 sender_tgid=839 sender_comm=PowerManagerSer` - a binder transaction that faults, retried without backoff. 6081 such records in the run265 logdump, and the last two seconds of that console were nothing else. |
| The port's own DIAG output was 59 % of the console | run265 logdump: 8114 of 13764 messages, and in the final two seconds 237 of 237 were signal records. The kgsl evidence the 1 MiB ring exists to hold had been evicted. |
| The early death correlates with the host-side poller | 4 deaths with the poller running during the boot window, 2 successes without. run266's first attempt had the poller running from before the `fastboot boot` and died with an all-zero logdump; the second attempt had **no host activity at all** for 210 s and came up. |
| The fastrpc defect is a uapi mismatch, not a missing DMA region | the port's `include/uapi/misc/fastrpc.h` and the stock userspace's disagree on every ioctl number (INVOKE 3 vs 1, MMAP 6 vs 2, INIT 5 vs 6, GET_DSP_INFO 13 vs 16), so the stock `adsprpcd` hits the port driver's `default:` arm and gets `-ENOTTY` - "Inappropriate ioctl for device", exactly what the userspace reports. `of_reserved_mem_device_init_by_idx()` parses a `memory-region` phandle, and the `qcom,fastrpc` binding does not allow a `reserved-memory` child. |
| There is no root on the port kernel | the ROM's enforcing policy is what applies and `adb root` does not stick. `/product/bin/su` exists (Magisk is installed) but magiskd never starts, because the port's boot image carries the diag ramdisk instead of Magisk's patched one. |

## 3. What is not proven

* Which link of the fence release chain breaks when the GPU stalls. The
  instrument answers it in one boot, but run266 and run267 both came up
  clean, so the failing boot has not been caught yet.
* Why the early death happens. The mechanism behind the poller
  correlation is not established.
* What PowerManagerService is retrying. The storm is downstream of the
  stall (it starts at t=40 s, the first fence timeout is at 238 s).
* Whether the fastrpc uapi mismatch is what makes `vendor.per_proxy`
  crash-loop.

## 4. Next actions, in order

1. **Boot until it stalls, with the instrument in.** The image is
   `boot-run267.img` and the procedure is below. When the boot stalls,
   the logdump's four DIAG lines say which link broke (section 10 of the
   findings file). This is the highest-value next step and it costs one
   boot cycle per attempt.
2. **Make the kgsl state readable without root.** The diag ramdisk's init
   is PID 1 and already root: it can `chmod` the kgsl sysfs attributes,
   and the packager can append CIL to the ramdisk's
   `userdebug_plat_sepolicy.cil` record (`package-diag-boot.py
   --policy-append FILE`) to let the `shell` domain read the kgsl debugfs
   and sysfs. That is a ramdisk rebuild, not a kernel build. Shizuku
   cannot substitute: over adb it runs as `shell`, which is exactly the
   identity that is already denied.
3. **The thermal path**, so the phone stops cooking and the boot cycles
   get longer. Two parts: a TSENS driver for this part (the tree's
   `drivers/thermal/qcom/tsens-v2.c` has no msm8953 sensor table), and the
   missing `#cooling-cells` / OPP `cooling-device` link. The interim is a
   maximum-frequency cap, which is a one-line OPP-table change but
   contradicts the "stock OPP table" claim, so it needs to be recorded as
   a debug cap.
4. **The fastrpc uapi mismatch**, if the DSP and the audio ports are to
   work. The userspace is the stock CAF one, so the port's driver has to
   speak the CAF ioctl numbers, or the port needs CAF's legacy-compute
   driver.
5. **The early hang**, with `initcall_blacklist=` (no rebuild needed) and
   the initcall names from the vmlinux: `kgsl_3d0_init`,
   `mdss_mdp_driver_init`, `mdss_fb_init`, `mdss_dsi_driver_init`,
   `mdss_smmu_driver_init`, `apcc_msm8953_driver_init`, `adsp_driver_init`,
   `fastrpc_init`, `remoteproc_init`.

## 5. Procedures

**Boot (the procedure that works - keep the host idle first):**

```sh
cd porting/artifacts/snapshot60
bash ../../logging/clear-logdump.sh runNNN      # on stock, needs su
adb -s 2819f2320604 reboot bootloader
sleep 15
fastboot -s 2819f2320604 boot boot-runNNN.img
# then leave the host COMPLETELY idle for ~200 s. A poller that runs
# `adb shell` every 3-4 s during this window correlates with every early
# death observed so far.
# after adb comes up, the poller is safe to start:
nohup bash run266-kgsl-poll.sh > runNNN-poll.log 2>&1 &
```

Nothing is flashed; the image is RAM-booted. To preserve the evidence,
reboot to stock and pull it:

```sh
adb -s 2819f2320604 reboot
bash ../../logging/pull-run-evidence.sh <run> boot-runNNN.img
```

**Build:** copy `porting/artifacts/snapshot60/run267-build-host.sh`, change
the run number and the changed-file assertion. It is incremental: it
reuses `/home/kurision/development/kernel/ack-out-run261` and the staged
tree `ack-staged-run239`, so no clean build and no new output directory.
`W=1` is used for the port's own objects only; the kgsl objects are
ported CAF code that does not satisfy `W=1` (missing prototypes on two
`kgsl_sync.c` helpers, a missing format attribute in `kgsl_events.c`, an
unused-but-set count in `adreno_dispatch.c` - all pre-existing).

**Read the logdump:** `porting/artifacts/snapshot60/compare-printk-timing.py`
compares two boots' printk timing, and
`run265-logdump-summary.py` summarises one.

## 6. Artifacts

Under `porting/artifacts/snapshot60/` (the `.img`, `.bin` and `.log` blobs
are gitignored; the JSON and text records are committed):

| Run | Image | Result |
|---|---|---|
| 261 | `boot-run261.img` `6b008c81b57f4099d24ae521dec84eab10d43d21000fb730062294df3c76a054` | booted, 272 s, died of heat |
| 262 | `boot-run262.img` `81d9a13f783831adb4e86d4e9dc813380f58e9e46554ab0c609ac67b8a7454b8` | died early (cmdline `cpufreq.off=1`) |
| 263 | byte-identical to run261 | died early |
| 264 | `boot-run264.img` `3b6e518f84a770b72fba825aa103177ac330fa47754113318a549759abc3b934` | died early (cmdline `console=tty0`) |
| 265 | the run264 image, booted by hand | booted, 581 s, GPU stalled, died |
| 266 | `boot-run266.img` `6d3846df4ac7e96e53eda3b16156ce66ebdb3c9676e882cd2bb0fec3150d2ee4` | died early with the poller running; booted clean without it, 480 s, **no GPU stall** |
| 267 | `boot-run267.img` `f7ea34704e30cf06d0510c31b618b0658cc73a5f629b53096ccfbddedb3e5a23` | booted clean, 489 s, **no GPU stall**, the diagnostic validated |

Kernel payloads: run261/262/263/264 `59eb2793a5f7993002f544864f18e46250f51395f1eec8b69b802374bfe33d15`,
run266 `cc3f65d7b5e17175847614cb63b6a7a6714d1476430444e02687a94297127921`,
run267 `db3acee2392c1f1625e2f2e364609e31551c0b7ff1a47aff2b045d3625b40b4b`.

Evidence: `run265-logdump.log`, `run266-logdump.log`, `run267-logdump.log`
(gitignored), the matching `-ramoops.json` (committed), and
`run266-earlyhang/` for the failed run266 attempt.

## 7. Rules

* Evidence first: a claim needs a named log, command or file. Say
  "unverified" when it is not proven.
* `AGENTS.md`: no `Signed-off-by`, no `Assisted-by`/co-authors in commits;
  do not discard the pre-existing uncommitted work; ask before a kernel
  build, a boot cycle, a push, or a rewrite of published history; do not do
  clean builds and use the default out dir.
* Do not reconstruct known-good artifacts: use the real `boot-run258.img`
  base and the real `init-run257`; the diag ramdisk is not rebuildable.
* Keep boot images, 64 MiB dumps and source-wide manifests out of git;
  commit the small verification records.
* A second-opinion review by an external model was requested and could not
  be obtained: the provider returned "Rate limit exceeded" on every
  attempt. If the provider is available later, run it before the next
  functional change.
