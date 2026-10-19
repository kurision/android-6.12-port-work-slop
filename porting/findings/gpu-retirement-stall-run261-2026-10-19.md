# run261: the display stack is done, the GPU stops retiring work

Date: 2026-10-19. Evidence: `run261-logdump.log` (1.97 MB of port console),
`run261-live/logcat-100.log`, `run261-live/lag-sample-240.txt`,
`run261-live/adb-timeline.jsonl`.

## Short version

`porting/PLAN-mdss-display-port.md` says "Status: plan only, nothing ported
yet". That is out of date: the downstream MDSS fbdev driver is in the tree
(87 files, 96,660 lines, imported at run198) and it **works**. The boot
animation lags because the **GPU stops retiring work**, the compositor's
fence never signals, and the display drops every frame that waits on it.
The MDSS port is not the remaining milestone; the GPU retirement stall is.

## The display path is alive and working

From the run261 kernel log, in order:

```
mdss_smmu_probe: iommu v2 domain[0] mapping and clk register successful!
mdss_dsi_ctrl_probe: DSI Ctrl name = MDSS DSI CTRL->0
mdss_dsi_panel_init: Panel Name = otm1911 fhd video mode dsi panel
mdss_dsi_panel_timing_from_dt: found new timing "qcom,mdss_dsi_otm1911_fhd_video"
mdss_register_panel: adding framebuffer device 1a94000.qcom,mdss_dsi_ctrl0
mdss_dsi_ctrl_probe: Dsi Ctrl->0 initialized, DSI rev:0x10040002, PHY rev:0x2
mdss_fb_register: FrameBuffer[0] 1080x1920 registered successfully!
...
mdss_fb_open: mdssfb_80000 by android.hardwar pid=704 par=ok
DIAG dsi_on: done ctrl=0 rc=0 state=0x4 pwr=1 clk_rate=802589760
mdss_mdp_overlay_kickoff: DIAG123 kickoff count=1 / 2 / 600 / 1200
```

fb0 exists at the right resolution, the panel is the real otm1911 with the
donor's timing, the vendor composer opens the framebuffer, the DSI is clocked
at 802.6 MHz and the pipeline commits frames (1200 kickoffs). The user sees
the boot animation, so pixels arrive.

## Where the frames stop

The frame that the display waits on is a **kgsl timeline fence**, and it
never signals:

```
mdss_wait_sync_fence: drv:kgsl-timeline timeline:kgsl-3d0_6-s.nexuslauncher(1760)-RenderThread(2270) seqno:530304 timeline:532096 queued:532096 retired:532096 status:0x1
__mdss_fb_wait_for_fence_sub: mdp-fence: sync_fence_wait failed! ret = ffffff92
```

`status:0x1` means the fence's own `signaled` callback already reports the
timestamp as retired, yet the wait timed out: the dma-fence core's signalled
state was never set for it. That is not an MDSS bug - the MDSS is waiting for
a GPU fence that the GPU side never completed.

## The GPU is what stopped

The port's own kgsl watchdog says so, at 121.96 s:

```
kgsl kgsl-3d0: kgsl: possible gpu syncpoint deadlock for context 4 timestamp 0
kgsl kgsl-3d0:   context[4]: queue=3123328, submit=3121536, start=3121536, retire=3121536
kgsl kgsl-3d0:   possible deadlock. Context 4 might be blocked for itself
kgsl kgsl-3d0:   context[4]: submit times: 8.544 6.984 8.493 8.431 9.998 8.544 6.983
kgsl kgsl-3d0:       pending events:
```

The queue ran 1792 commands ahead of `submit`, and `submit`, `start` and
`retire` are all frozen at the same value: the **host stopped handing work
to the GPU**, and each host-side submit took 8-10 ms instead of
microseconds.

The port's DIAG submit trace shows the collapse (n = command count,
t_ns = monotonic):

| window | submits | gap |
|---|---|---|
| 62 s - 212 s | regular, ~64 commands per 300-500 ms | normal |
| 213 s - 219 s | 561, 333, 295, 396, 757, 2740 ms | degrading |
| 220 s - 227 s | 597, 6404 ms | collapsing |
| 226 s - 253 s | 26588 ms | stalled |

That is the same shape as a port that cannot reclaim retired command memory:
the host blocks in submit because the retired memory is only recycled when
the GPU's retirement is observed, and the port's dispatcher work
(`adreno_dispatch.c:2999` -> `kgsl_process_event_groups()`) is what observes
it.

## The chain to the symptoms

1. The GPU stops retiring work (kgsl dispatcher/event path).
2. The composer's fence never signals; the MDSS drops the frame
   (`sync_fence_wait failed! ret = ffffff92`).
3. SurfaceFlinger reports `Faking VSYNC due to driver stall for thread app`
   and `getSupportedContentTypes failed for display 0: UNSUPPORTED (8)`.
4. The Android display HAL lives inside system_server on this ROM, so the
   display stall turns into a syscall retry loop there: **system_server at
   566 % CPU**, 79 % of the system in *system* time, load average 19.96.
5. The spin keeps the CPUs at the top OPP: 24511 of roughly 26950 policy
   ticks at 2016 MHz (91 % of the run), with no thermal feedback in this
   port (`CONFIG_QCOM_TSENS` is not set, the CPU nodes do not reference the
   thermal zones, the shared OPP table has no cooling-device).
6. The phone dies at about 326 s of kernel uptime with no kernel-side fault
   record.

The same display stall existed in run258, which also ran with no DVFS policy
and survived 480 s at 800 MHz. The CPU repair moved the failure from
"splash and reset" to "boots, then dies of power/heat", and made it
observable.

## Smaller broken loops in the same boot

* `adsprpcd` restarts every 25 ms: 1372 restarts in the logcat window,
  rooted in `qcom,fastrpc remoteproc0:smd-edge.fastrpcsmd-apps-dsp: no
  reserved DMA memory for FASTRPC`, so the ADSP FastRPC device open fails
  with -1. Also present in run258 (270 restarts), so it is pre-existing.
* The audio HAL never builds its port list: 381 x `AudioSystem:
  listAudioPorts failed` -> `AudioManager: updateAudioPortCache` fails.
* The 1338 SIGSEGVs in the kernel trace are **not** a crash storm: the
  device's tombstones are all from 2026-10-09 and the faulting threads are
  all Java processes, so this is ART's implicit null-check trap.

## What is not the cause

* The MDSS driver: fb0 registers, the panel probes, the composer opens it,
  frames are committed.
* The APCC clock driver: the handoff is evidenced and the CPUFreq policy
  works with all seven stock OPPs over CPUs 0-7.
* The CPU frequency set: the OPP table is the stock bin-2 CPR corner
  frequency list (652.8 - 2016 MHz), copied verbatim from the donor's
  `qcom,corner-frequencies`, and the rate-to-corner-to-voltage chain is the
  stock one.

## Next step

The remaining milestone is the **GPU retirement stall in the ported kgsl**:
why `submit`/`start`/`retire` freeze while the queue runs ahead, and why the
host-side submit takes 8-10 ms. The port's dispatcher work is the only
caller of `kgsl_process_event_groups()`, so the question is whether the
dispatcher work keeps being re-armed (`_dispatcher_update_timers()` ->
`mod_timer(&dispatcher->timer, drawqueue->expires)`) and whether the
dispatcher is faulting and being reset.

Cheapest next evidence, all inside one boot:
* read the kgsl debugfs: the dispatcher's state, the fault count, the
  per-context queue/submit/start/retire counters, and the event groups'
  pending lists;
* correlate the first `submit` freeze with the kgsl fault/snapshot prints
  (the port already has a snapshot mechanism and a `possible gpu syncpoint
  deadlock` print that fires 100 s before the visible collapse);
* check whether the *host* is blocked in submit for retired-memory reclaim
  or for a fault/snapshot, which the 8-10 ms submit times point at.
