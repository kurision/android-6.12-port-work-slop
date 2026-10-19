# run261-264: what the boot fix bought, and what is still broken

Date: 2026-10-19. Companion to
`cpu-boot-failure-analysis-run258-run260-2026-10-19.md` (the delta analysis
that led to the hardening) and `gpu-retirement-stall-run261-2026-10-19.md`
(the first look at the GPU stall).

## 1. The boot is fixed (run261)

Image `boot-run261.img`, SHA256
`6b008c81b57f4099d24ae521dec84eab10d43d21000fb730062294df3c76a054`, kernel
payload `59eb2793a5f7993002f544864f18e46250f51395f1eec8b69b802374bfe33d15`,
banner `#1 ... Mon Oct 19 21:50:01 +0545 2026`. The only source difference
against run260 is `drivers/clk/qcom/apcc-msm8953.c`; the DTB, config,
ramdisk, init and command line are identical, and the 332 DT schema messages
are identical.

What the port kernel itself recorded:

```
qcom-apcc-msm8953: boot state: pll 00000000 00000000 00000000 0000000f mux 00000401 00000000 00000403
qcom-apcc-msm8953: shared CPU/CCI domain, speed bin 2, CPU 799999804 CCI 399999902 Hz, corner 2
cpufreq: cpufreq_online: CPU0: Running at unlisted initial frequency: 799999 KHz, changing to: 1036800 KHz
```

* The APCC handoff succeeded and ended in the donor's post-boot state: CPU4-7
  on the APCS PLL at 652.8 MHz, the running CPU0 cluster still on GPLL0 at
  800 MHz, the CCI still on GPLL0 at 400 MHz, the rail at corner 2.
* One cpufreq policy (policy0) covers CPUs 0-7 with the seven stock OPPs
  (652800..2016000 kHz), governor schedutil, `scaling_cur_freq` 2016000.
* `sys.boot_completed=1`, `init.svc.bootanim=stopped`, surfaceflinger and
  system_server running, `/dev/ashmem` present. The user saw the boot
  animation.
* The logdump finally has content: 1,965,307 readable bytes, two
  CRC32-verified snapshot slots (seq 277/276), two verified periodic printk
  tails. run260's logdump was 64 MiB of zeros.

This is the first boot in the port's history with a working CPUFreq policy.

## 2. The early hang is intermittent, and it is not the command line

| Run | Image | Result |
|---|---|---|
| 261 | run261 kernel, plain cmdline | **booted**, ran 272 s, died of power/heat at ~326 s |
| 262 | run261 kernel + `cpufreq.off=1` | died in the first seconds, phone rebooted itself ~2 min later, logdump all zero |
| 263 | byte-identical copy of the run261 image | died in the first seconds, logdump all zero |
| 264 | run261 kernel + `console=tty0` | died in the first seconds, logdump all zero |

run263 is the decisive one: **the same image as run261**, no cmdline change,
and it still died early. So the early death is an intermittent port fault, not
something the command line caused, and not something the capture scripts
cause (the user fastboot-booted the same run262 image by hand and it came up).

The symptom is the same in all three failures: the phone is frozen and
unreachable, the panel is backlit, and the logdump stays all zero. The
host-side USB timeline shows the port kernel taking over from fastboot and
then never enumerating again:

```
22:36:41  USB disconnect (adb reboot bootloader)
22:37:01  18d1:d00d  fastboot session ("Booting OKAY")
22:37:04  USB disconnect  <- the port kernel takes over
22:39:23  18d1:4e11 bcd 4.19  <- the phone is back on the stock kernel
```

`18d1:d00d` is the fastboot interface, so the port kernel started at
22:37:04 and died silently; the ~2 min gap is the phone's own watchdog
rebooting it (or `panic=60` plus the bootloader's own boot time). Nothing
durable is written because the hang is at ~1-6 s, before the logdump
snapshotter's first commit at ~5 s and before the ramoops console can be
flushed anywhere durable.

Two things follow:

* The "static splash, then reset" reports from runs 259/260 were very likely
  this same intermittent hang, not the APCC's boot-time clock writes. The
  hardening in `647bd6404` is still correct on its own terms (it removed
  writes the donor never makes, and it fixed the PLL lock budget), but the
  evidence no longer supports attributing runs 259/260 to it.
* The early hang is in the window 1-6 s, which contains, in run261's order:
  the MDSS/MDP probe (3.06 s), the SCM/QSEE (4.2 s), the CPR4 regulator
  (4.19 s), the MDSS SMMU (4.25 s), the APCC handoff and cpufreq (4.56 s),
  the remoteproc/ADSP (6.7 s), and the GPU firmware (12 s+).

The ordering difference against the donor is real and worth acting on: the
donor does its CPU clock handoff in an `early_initcall`
(`clock-cpu-8953.c:1099`, `cpu_clock_pwr_init`), i.e. a full initcall level
*before* any display or GPU driver probes. The port can only do it from the
APCC's `device_initcall` probe, because its handoff waits for the CPR4
regulator and the MX domain, which are themselves level-6 providers. So in
the port the clock surgery lands in the same level as the display and GPU
bring-up, and in run261 it landed *after* the DSI was already live
(MDSS at 3.06 s, APCC at 4.56 s) - i.e. the CCI mux and the shared GCC
were being re-programmed while the panel was running.

## 3. The GPU stall, and what the control proved

`cpufreq.off=1` was the control for the leading hypothesis (that the new
driver's coupled rate-change transaction - the CCI mux and the running CPU
cluster's mux - was what wedged the GPU). The user's manual boot of that
image came up with **no cpufreq policy at all** (the poll shows no policy
block), so the coupled transaction never ran, and the panel still lit with
the boot animation **stuck**.

**The coupled clock transaction is exonerated for the display stall.** The
stall is a kgsl-side problem.

The stall itself, from run261:

```
kgsl-3d0: possible gpu syncpoint deadlock for context 4 timestamp 0
kgsl-3d0:   context[4]: queue=3123328, submit=3121536, start=3121536, retire=3121536
kgsl-3d0:   context[4]: submit times: 8.544 6.984 8.493 8.431 9.998 8.544 6.983
```

The host queued 1792 commands ahead of the GPU and `submit`, `start` and
`retire` froze at the same value; each command took 8-10 ms to retire
instead of microseconds. The port's own DIAG submit trace shows the
collapse: regular 300-500 ms gaps until 212 s, then 561, 757, 2740, 6404 and
finally 26588 ms.

The display's part of it is a fence that never gets signalled:

```
mdss_wait_sync_fence: drv:kgsl-timeline timeline:kgsl-3d0_6-s.nexuslauncher(1760)-RenderThread(2270) seqno:530304 timeline:532096 queued:532096 retired:532096 status:0x1
__mdss_fb_wait_for_fence_sub: mdp-fence: sync_fence_wait failed! ret = ffffff92
```

`status:0x1` means the fence's own `signaled` callback already reports the
timestamp as retired, yet the dma-fence core's signalled bit was never set
for it, so the MDSS's wait timed out and the frame was dropped. SurfaceFlinger
then reports `Faking VSYNC due to driver stall for thread app`, and because
the Android display HAL lives inside system_server on this ROM, the stall
becomes a syscall retry loop there: **system_server at 566 % CPU**, 79 % of
the system in system time, load average 19.96.

**Causality runs from the CPU, not from the GPU:** at 120 s - before the
first fence failure at 238 s - system_server was already at 550 % CPU. The
GPU's dispatcher work is the only caller of `kgsl_process_event_groups()`, so
a CPU-saturated machine starves exactly the thing that observes GPU
retirement, which makes the fences time out, which makes the display stall,
which makes system_server spin harder. A feedback loop.

The same fence failure exists in run258 (three occurrences, the same
`ret = ffffff92`), so the fence-signalling defect is pre-existing and not
caused by the CPU work.

The port's kgsl_sync.c is byte-identical to the donor's, and the fence core
semantics (`__dma_fence_enable_signaling`, `dma_fence_is_signaled_locked`,
`dma_fence_default_wait`) are the same in the 4.19+CAF tree and in 6.12, so
the defect is not an obvious API break in those files. The open questions are
(a) whether the event group for the composer's context is processed while the
fence is on the timeline's child list, and (b) whether the dispatcher work
keeps running. Both are observable from the kgsl debugfs `events` node
(`/sys/kernel/debug/kgsl/events`: each group's `last=` processed timestamp
and its pending events) - which the adb shell cannot read, because adbd
runs as `shell` on the port kernel and debugfs is 0700. The kgsl's own sysfs
`snapshot` directory *is* readable by the shell (the diag SELinux policy
allows it).

## 4. The fastrpc is broken independently, and it is a concrete defect

```
qcom,fastrpc remoteproc0:smd-edge.fastrpcsmd-apps-dsp.-1.-1: no reserved DMA memory for FASTRPC
```

`fastrpc_rpmsg_probe()` (`drivers/misc/fastrpc.c:2350`) calls
`of_reserved_mem_device_init_by_idx(rdev, rdev->of_node, 0)`; the port's
msm8953 device tree has no fastrpc node with a reserved-memory child, so the
DSP gets no DMA region. The user-space consequence is visible and is a
restart loop:

```
adsprpcd: fastrpc_apps_user.c:2968: Error 0xffffffff: open_dev (-1) failed
adsprpcd: adsp daemon will restart after 25ms...
```

1,372 restarts in one logcat window, and it is pre-existing (run258 had 270
of them). The audio HAL fails with it: 381 x `AudioSystem: listAudioPorts
Failed` -> `AudioManager: updateAudioPortCache: listAudioPorts failed`, so the
audio port list is never built.

This is also the best candidate for the early hang: the ADSP firmware loads
at 6.7 s and the DSP's DMA mappings are wrong. It is the same 1-6 s window
as the hang, and the port's own history has a board reset at the first GPU
start (`run203 reset the board ~41 s into boot, at the first GPU start`).

## 5. Corrections to earlier statements in this session

* The 1,338 SIGSEGVs in the kernel trace are **not** a crash storm. The
  device's tombstones are all from 2026-10-09 and every faulting thread is a
  Java process, so this is ART's implicit null-check trap. Only two real
  crashes appear in the logcat (`android.hardware.*` faulting at 0xc0, and a
  SIGABRT in `droid.bluetooth`).
* "The APCC's boot-time clock writes caused runs 259/260" is **not
  established**. The hardening is still right, but run263 shows the same
  image dying early, so the intermittent hang is a separate fault that the
  hardening did not address.
* The OPP frequencies are the **stock** ones: the donor's
  `qcom,corner-frequencies` per fused speed bin. This phone's fused bin is
  2, whose stock list is exactly 652.8/1036.8/1401.6/1689.6/1804.8/1958.4/
  2016 MHz, which is what the port's shared OPP table holds, with the stock
  corner voltages 715/790/860/865/920/990/1065 mV. The 19-entry table up to
  2784 MHz that the poll saw is the **stock 4.19** kernel's policy, not the
  port's.
* The MDSS display port is **done**; `PLAN-mdss-display-port.md` ("plan
  only, nothing ported yet") is out of date and has been corrected.

## 6. What is still unproven

* The cause of the early hang. No durable evidence exists for it: the hang
  is before the logdump sink exists, the phone's own ramoops is in RAM and
  is lost on the watchdog reboot, the port has no TTL earlycon capture
  available (no serial adapter on the host), and the adb shell cannot read
  the kgsl debugfs.
* Whether the GPU is genuinely stuck or merely starved by the CPU-saturated
  system_server. The kgsl debugfs `events` node and the kgsl sysfs snapshot
  are the views that would settle it, and the latter is shell-readable.
* Whether the 8-10 ms submit-to-retire latency is a real GPU hang or the
  dispatcher work being delayed.
* Whether the fastrpc's missing DMA region is the early hang's cause.
