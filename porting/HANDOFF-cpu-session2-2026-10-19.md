# Handoff: MSM8953 CPU bring-up, session 2 (2026-10-19)

**Superseded by `HANDOFF-cpu-session3-2026-10-20.md`.** Read that one
instead; this file is kept for the history. The corrections are in
`findings/cpu-boot-failure-analysis-run265-2026-10-19.md`: the last
successful scripted boot was run261 (not run262), runs 261-264 all carry
the same kernel payload, the GPU stall is not CPU starvation, and the
fastrpc fault is a uapi mismatch rather than a missing DMA region.

**Read this file first.** It is a self-contained briefing for a fresh session:
state, what is proven, what is broken, the evidence paths, the next actions
and the working rules. The long history is in the older files listed at the
end; do not read them first.

Repo: `/home/kurision/development/kernel/ack-kgsl` (Linux 6.12.93-4k / ACK,
arm64, board `msm8953-xiaomi-tissot`). Donor tree with the hardware truth:
`/home/kurision/development/kernel/oc-test` (CAF 4.19, boots this phone).
Device serial `2819f2320604`.

## 1. Where we are

**The boot works.** The port kernel now boots with a working shared cpufreq
policy over all eight CPUs (seven stock OPPs) and reaches
`sys.boot_completed=1`. That is the first time in this port's history.
Before this session the same code produced a silent splash-and-reset with an
all-zero logdump.

**Two problems remain**, and they are separate:

1. **An intermittent early hang.** In ~2 of 4 boots the port kernel freezes
   within the first 1-6 s, the phone is backlit and unreachable, it reboots
   itself about two minutes later, and the logdump stays all zero because the
   hang happens before the logdump sink exists. It is *not* the command
   line and *not* the capture scripts: run263 used a byte-identical copy of
   the image that booted in run261 and still died early, and the user
   fastboot-booted the run262 image by hand and it came up.
2. **The GPU stops retiring work**, the display drops every frame that waits
   on the GPU fence, and the Android display HAL (inside system_server on
   this ROM) turns that into a 5.5-core retry loop. The system then sits at
   the top OPP with no thermal feedback and the phone dies of power/heat
   about 326 s in.

## 2. What is proven, with evidence

| Claim | Evidence |
|---|---|
| The APCC handoff works and ends in the donor's post-boot state | `run261-logdump.log`: `boot state: pll 00000000 ... mux 00000401 00000000 00000403` then `shared CPU/CCI domain, speed bin 2, CPU 799999804 CCI 399999902 Hz, corner 2` |
| One shared cpufreq policy over CPUs 0-7, seven stock OPPs | live probe: `policy0`, `related_cpus 0-7`, `652800..2016000`, `scaling_cur_freq 2016000`, governor `schedutil` |
| The port reaches a booted Android | `sys.boot_completed=1`, `init.svc.bootanim=stopped`, surfaceflinger and system_server running, `/dev/ashmem` present; the user saw the boot animation |
| The MDSS display port is **done** | `mdss_fb_register: FrameBuffer[0] 1080x1920 registered successfully!`, `Panel Name = otm1911 fhd video mode dsi panel`, `mdss_fb_open: mdssfb_80000 by android.hardwar`, DSI at 802.6 MHz, 1200 frame kickoffs |
| The coupled clock transaction is **not** what wedges the GPU | the user's manual boot of `cpufreq.off=1` (no policy, so no coupled transaction) still lit the panel with the animation stuck |
| The early hang is intermittent and not cmdline-related | run263 = a byte-identical copy of the run261 image, died early; run262 = the same image with one extra cmdline token, died early; the user's manual boot of run262 came up |
| The GPU stops retiring work | `kgsl-3d0: possible gpu syncpoint deadlock for context 4`, `queue=3123328, submit=3121536, start=3121536, retire=3121536`, `submit times: 8.544 6.984 ...` |
| The CPU saturation precedes the display stall | at 120 s (before the first fence failure at 238 s) system_server was already at 550 % CPU, 79 % system time |
| The display drops frames on a kgsl fence that is never signalled | `mdss-fence: sync_fence_wait failed! ret = ffffff92` with the fence's own `status:0x1` (already retired) - present in run261 and in run258 |
| The fastrpc has no DMA region | `qcom,fastrpc: no reserved DMA memory for FASTRPC` -> `adsprpcd` restarts every 25 ms (1372 times), audio's `listAudioPorts` fails 381 times; pre-existing (run258 too) |
| The OPP table is the stock one | the donor's `qcom,corner-frequencies` per fused bin; this phone's fused bin is 2, whose stock list is exactly the port's seven OPPs, with the stock corner voltages 715-1065 mV |

## 3. What is not proven

* **The cause of the early hang.** No durable evidence exists: the hang is
  before the logdump sink, the phone's ramoops is in RAM and dies with the
  watchdog reboot, there is no TTL earlycon capture on this host, and the
  adb shell cannot read the kgsl debugfs (adbd runs as `shell`; debugfs is
  0700).
* **Whether the GPU is genuinely stuck or merely starved** by the
  CPU-saturated system_server. The kgsl debugfs `events` node and the kgsl
  sysfs `snapshot` directory answer this; the latter is shell-readable.
* Whether the fastrpc's missing DMA region is the early hang's cause.

## 4. Next actions, in the order I would take them

1. **Make the early hang catchable, and read the kgsl state while the
   machine is alive.** The port's `kgsl/kgsl-3d0/snapshot` sysfs directory is
   readable by the shell (the diag SELinux policy allows it) and the kgsl
   debugfs `events` node shows each event group's `last=` processed timestamp
   and its pending events. A short poll of both, started as soon as adb
   appears, turns the next successful boot into a diagnosis of the GPU
   stall; the same poll also tells us whether the dispatcher work keeps
   running. If the early hang is the blocker, `initcall_blacklist=` can
   bisect it with command-line-only boots; the initcall names are in
   `../ack-out-run261/vmlinux` (`kgsl_3d_init`, `mdss_mdp_driver_init`,
   `mdss_fb_init`, `mdss_dsi_driver_init`, `mdss_smmu_driver_init`,
   `apcc_msm8953_driver_init`, `adsp_driver_init`, `fastrpc_init`,
   `remoteproc_init`).
2. **Fix the fastrpc's DMA region** (device tree): the rpmsg probe wants a
   reserved-memory child under the fastrpc node
   (`of_reserved_mem_device_init_by_idx`, `drivers/misc/fastrpc.c:2350`). The
   port has the 18 MiB `adsp@8d600000` region but no fastrpc node. This
   should stop the adsprpcd restart loop, fix the audio port list, and
   remove the DSP from the 1-6 s window where the hang happens.
3. **Then the GPU stall**, with the kgsl state in hand: whether the
   composer's context event group is being processed while its fence sits on
   the timeline's child list, and whether the dispatcher's periodic work is
   still being re-armed (`_dispatcher_update_timers()` ->
   `mod_timer(&dispatcher->timer, drawqueue->expires)`).
4. **Then the thermal gap** (it is what turns the stall into a dead phone):
   `CONFIG_QCOM_TSENS` is not set, the CPU nodes do not reference the
   thermal zones, and the shared OPP table has no `cooling-device`, so
   nothing can throttle the CPUs. Either cap the maximum frequency for the
   interim or port the thermal path.
5. **Only then** re-evaluate the APCC's coupled transaction. It is
   exonerated for the stall, but it still re-programs the CCI mux and the
   running CPU cluster's mux on every frequency change, and it lands in the
   same initcall level as the display and GPU bring-up, whereas the donor
   does its clock handoff one level earlier (`early_initcall`,
   `clock-cpu-8953.c:1099`).

## 5. Procedures

**Boot (the user's preferred simple flow - no capture scripts):**

```sh
cd porting/artifacts/snapshot60
adb -s 2819f2320604 reboot bootloader
sleep 10
fastboot -s 2819f2320604 boot boot-runNNN.img
```

Nothing is flashed; the image is RAM-booted. The logdump partition is
64 MiB; zero it before a boot if the previous run's content would confuse
the reading (`bash ../../logging/clear-logdump.sh <tag>`, needs `su` on the
stock kernel), and after the phone is back on stock pull the evidence with
`bash ../../logging/pull-run-evidence.sh <run-number> <image>`.

A passive poller that samples the load, `/proc/stat`, the GPU interrupt
count, the cpufreq state and the kgsl debugfs exists:
`porting/artifacts/snapshot60/run263-kgsl-poll.sh` (copy it and change the
output directory; it writes one file per sample, four seconds apart). It
needs `adb` and nothing else.

**Build:** copy `porting/artifacts/snapshot60/run261-build-host.sh`, change
`run261` to the new run number and the output directory, and keep the real
`boot-run258.img` base and `init-run257`. Per the current `AGENTS.md`, do not
do clean builds and use the default `out` directory rather than a per-run
output directory. The run261 build already compiles `W=1` objects for
`apcc-msm8953.o`, `qcom-apcs-ipc-mailbox.o`, `msm8953-spm.o`,
`fs/pstore/ram.o` and `kernel/reboot.o`, and runs `dt_binding_check` and
`CHECK_DTBS`.

## 6. Artifacts and commits

Commits on top of the earlier CPU work (`2d56bc749` binding, `22529fab4`
mailbox, `931064e41` APCC, `9c1bc7000` pstore declarations):

| Commit | What |
|---|---|
| `3b3f9f660` | the run258->run260 delta analysis (manifest-based) and the ranked suspects |
| `647bd6404` | the APCC hardening: donor-shaped boot handoff (PLL, then only the CPU4 alias1 mux and its core branch; the running CPU0 cluster and the CCI are left alone), donor-length PLL lock budget, the MX domain attached before any fallible probe step, a park/restore that do not rewrite an unchanged mux |
| `205e40537` | the run261 evidence and findings |
| `89cbc006a` | the GPU retirement stall analysis, and the display plan corrected |
| (this session) | the run262-264 evidence, the control results, and this handoff |

Images and evidence under `porting/artifacts/snapshot60/` (the `.img` and
`.bin`/`.log` blobs are gitignored; the JSON and text records are committed):
`boot-run261.img` `6b008c81b57f4099d24ae521dec84eab10d43d21000fb730062294df3c76a054`,
`boot-run262.img` `81d9a13f783831adb4e86d4e9dc813380f58e9e46554ab0c609ac67b8a7454b8`
(the `cpufreq.off=1` control), `boot-run263.img` (byte-identical to run261),
`boot-run264.img` `3b6e518f84a770b72fba825aa103177ac330fa47754113318a549759abc3b934`
(the same with `console=tty0`). Kernel payload for run261/262/263/264 is
`59eb2793a5f7993002f544864f18e46250f51395f1eec8b69b802374bfe33d15`.

Findings to read, in this order:

* `porting/findings/cpu-boot-failure-analysis-run261-264-2026-10-19.md` -
  the state of play, the run262-264 evidence, the control results, the
  corrections (see section 5 of that file).
* `porting/findings/cpu-boot-failure-analysis-run258-run260-2026-10-19.md` -
  the manifest-based delta analysis that produced the hardening.
* `porting/findings/gpu-retirement-stall-run261-2026-10-19.md` - the first
  analysis of the GPU stall and the CPU-saturation chain.
* `porting/HANDOFF-cpu-bringup-2026-10-19.md` - the long history of the CPU
  bring-up, and the run-by-run record.

## 7. Rules for this repo

* Evidence first: a claim needs a named log, command or file. Say
  "unverified" when it is not proven.
* `AGENTS.md`: no `Signed-off-by`, no `Assisted-by`/co-authors in commits;
  do not discard the pre-existing uncommitted work; ask before a kernel
  build, a boot cycle, a push, or a rewrite of published history; do not do
  clean builds and use the default `out` directory.
* Do not reconstruct known-good artifacts: use the real `boot-run258.img`
  base and the real `init-run257`; the diag ramdisk is not rebuildable.
* Keep boot images, 64 MiB dumps and source-wide manifests out of git; commit
  the small verification records.
* A second-opinion review by an external model was requested and could not be
  obtained: the provider returned "Rate limit exceeded" on every attempt,
  including a two-word probe. If the provider is available later, run it
  before the next functional change.
