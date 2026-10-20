# run196 — display pipeline result, taken live over ADB

> **Historical record - 2026-10-17.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../../../CURRENT-STATE.md).

Date: 2026-10-17. Image `boot-run196.img`, kernel payload
`39f3c9b9e7476afafdb0fa44b24e940fab786db4f7ff771258a6f6…` (see
`package-run196.json`), booted from `boot-run195.img`, cmdline
`mdss_mdp_cold_boot=1`. Device stayed on the port kernel for the whole
analysis window (`6.12.93-4k`, uptime past 530 s).

## 1. The display bring-up now completes (was -ETIMEDOUT in run194)

From `run196-logdump.log`:

```
DIAG dsi_on: ctrl=0 cold bring-up, cur_power_state=0
mdss_dsi_panel_power_on: PANEL_PM enable rc=-110, continuing anyway
DIAG dsi_on: done ctrl=0 rc=0 state=0x4 pwr=1 clk_rate=802589760
```

* `state=0x4` = `CTRL_STATE_DSI_ACTIVE`, `pwr=1` = panel powered.
* `mdss_fb_open` failure count in the whole log: **0** (run194: 1, with
  `can't turn on fb0! rc=-110`).
* `DIAG123 kickoff count=` reaches 3000, i.e. the MDP is still being committed
  continuously, with `dma0 src0=ff00f000 size=07800438` — a real 1080x1920
  RGBA buffer.

Cause of the original failure, from run194's logdump:

```
mdss_dsi_panel_power_on: failed to enable vregs for PANEL_PM
mdss_dsi_on:Panel power on failed. rc=-110          (-ETIMEDOUT)
mdss_mdp_video_display: intf #2 link ready error (-110)
mdss_mdp_display_commit: ctl 0 error displaying frame
mdss_fb_open: can't turn on fb0! rc=-110
WARNING ... unbalanced disables for l6  (_regulator_disable)
```

The `vdd` rail is an RPM-served pm8953 LDO (`qcom,rpm-pm8953-regulators`).
Its enable request is never acked, so the RPM write path returns
`-ETIMEDOUT`. CAF treats that as fatal and aborts `mdss_dsi_on()` before the
PHY, clock source or DSI controller are touched. run196 makes it non-fatal;
run197 additionally stops the tissot power-off branch from disabling rails
that were never enabled (`acc_vreg > 0` is now the only condition).

**Not proven**: that the panel VDD rail is actually on. The enable request
still fails; the fix only stops that failure from killing the bring-up. The
bootloader is assumed to have supplied the rails.

## 2. The composited framebuffer is uniformly black — screencap IS usable here

`screencap -p` on this port boot returns an 8161-byte 1080x1920 PNG. Decoded
(PNG inflate + defilter): **42,625 sampled pixels, one distinct colour,
`#000000`**. Three captures three seconds apart are byte-identical
(`d1d094a55ed05212d1b2c7525c6fa4f28ec4f437869e85b51854b7ced3bba88f`).

This corrects the handoff's claim that `screencap` "provably returns a
constant image regardless of display state". It returns a constant image
*while the content is constant*; run171's white and run196's black are
different constants. It is usable as a content check.

## 3. Why it is black: there is almost nothing left to draw

`dumpsys SurfaceFlinger` at uptime ~530 s:

* `Total missed frame count: 42`, `HWC missed frame count: 42`,
  `GPU missed frame count: 1`
* `Display{#0 state=ON size=1080x1920}`
* **Only 4 active layers**: `PointerEventDispatcherOverlay0`, `Dim layer`
  x2, `WallpaperService-com.android.systemui`. No launcher, no app windows,
  no status/navigation bar content.
* `mFocusedApp = com.google.android.apps.nexuslauncher/.NexusLauncherActivity`
  but `pidof com.android.launcher*` returns nothing — the process is gone.

Full logcat (47,622 lines) shows the launcher dying and not coming back:

```
WindowManager: WIN DEATH: Window{... com.google.android.apps.nexuslauncher/.NexusLauncherActivity}
ActivityManager: Process com.google.android.apps.nexuslauncher (pid 22240) has died: fg  BFGS
ActivityManager: Scheduling restart of crashed service .../TouchInteractionService
```

## Conclusion

The MDP/DSI/panel bring-up defect is found and fixed. It was never the whole
story: with the pipeline now provably complete and continuously committed, the
screen is black because **nothing renders**. The launcher process is killed in
a loop, leaving only dim and wallpaper layers, and those composite to
`#000000`.

The remaining blocker to a visible display is the KGSL/UCHE fault, which is a
separate investigation from the display stack. Artifacts:
`screencap-black.png`, `logcat-tail.log`, `full-logcat.log`, `poll.jsonl`.
## 4. Follow-up at ~660 s: the launcher comes back, the frame stays black

`pidof com.google.android.apps.nexuslauncher` now returns a pid (23652) — the
launcher restarted after the death recorded above — but three further
` screencap` samples, four seconds apart, are byte-identical to the first and
still decode to a single colour, `#000000`. So a running launcher does not
change the composited output.

Apps *are* drawing. From `full-logcat.log`:

```
HWUI: Davey! duration=2585ms; ... SwapBuffersCompleted=...
HWUI: Davey! duration=3121ms; ...
Choreographer: Skipped 125 frames!
HWUI: Davey! duration=2513ms; ... (pid 22269, SystemUI)
HWUI: Davey! duration=3305ms; ...
Choreographer: Skipped 102 frames!
```

This is the handoff's "frames ARE composed, just at ~0.3 fps" observation,
confirmed again. The frames complete — HWUI reports `GpuCompleted` and
`SwapBuffersCompleted`, so the fences signal — and the result is still black.

**That is the shape of the UCHE fault**: the GPU accepts the commands, signals
completion, and produces no correct pixels. It is not a starvation or a
fence problem, which is why the display stack being fixed changed nothing
about what is on the panel.

## 5. Second run196 boot — kernel log (`run196-logdump.log`, 33.8 MB, ~700 s uptime)

**Display side: completely clean.**

```
DIAG dsi_on: ctrl=0 cold bring-up, cur_power_state=0
DIAG dsi_on: done ctrl=0 rc=0 state=0x4 pwr=1 clk_rate=802589760
```

Counts in the entire log: `turn on fb0` **0**, `link ready error` **0**,
`unbalanced disables` **0**. The `continuing anyway` line is **absent** on this
boot, i.e. `msm_mdss_enable_vreg()` returned 0 — the RPM request for the panel
`vdd` rail **succeeded**. That corrects the run194 reading: the RPM request
path is intermittent, not permanently broken. run196's first boot hit
`-ETIMEDOUT`, this one did not.

**GPU side: still broken, and now quantified.**

| | count |
|---|---|
| `GPU hang detected` | **816** |
| `gpu fault ctx` | **517** |
| `gpu fault threshold exceeded` | **2** |
| first / last fault | t = 42.39 s / t = 702.77 s |

```
kgsl-3d0: surfaceflinger[709]: gpu fault threshold exceeded 3 faults in 3000 msecs
kgsl-3d0: s.nexuslauncher[1595]: gpu fault threshold exceeded 3 faults in 3000 msecs
```

First fault, same signature as run188:

```
UCHE: Out of bounds access addr=0000000000139000
DIAG uche-oob: cp_status=80423c68 hw_fault=00000000 ib2=0000000000260140/0 addr_mode=1
DIAG cp-stall: rptr=fd wptr=fd ahb=0903a284 protect=00000000 int0=00000000
surfaceflinger[709]: gpu skipcmd ctx 2 ts 16896 policy 80
```

The driver now emits `gpu skipcmd` after a fault, i.e. it is dropping
commands rather than executing them.

## Verdict

The display bring-up defect is fixed and the pipeline is verified end to end.
What remains is the KGSL/UCHE fault: SurfaceFlinger and the launcher both hit
the fault threshold, the launcher restarts in a loop, and the composited
output is `#000000`. A correctly driven display pipeline showing a black frame
is exactly the reported "dimly backlit, nothing else".

## 6. run197 (regulator-counter fix) — same result, confirms the fix is neutral

Booted from `boot-run196.img` with payload `ef64a61b…`; port kernel confirmed
up by `port-boot-retry.py`. At uptime 361 s:

| | value |
|---|---|
| `sys.boot_completed` | 1 |
| SurfaceFlinger / system_server / launcher | 710 / 1120 / 12502 |
| active layers | 3 |
| total / HWC / GPU missed frames | 32 / 32 / 1 |
| `screencap` sha256 | `d1d094a5…` — **byte-identical to run196's black frame** |

So `acc_vreg > 0` did not change the outcome, as expected: it was a latent
refcount bug, not the cause. The screen is still a uniform black frame.

Independent confirmation that the display *output* is static and black, not
just that `screencap` is blind: `screenrecord --time-limit 5 --size 540x960`
produced a 5343-byte file, all 6 recorded frames byte-identical
(`framemd5 f39cbc14…`), and the frame scaled to 1x1 RGB is `(0, 0, 4)`.
`screenrecord` goes through a VirtualDisplay and SurfaceFlinger, a different
path from `screencap`'s framebuffer read, and both say black.

## GPU clock observations (from `run196-logdump.log`)

`DIAG bringup[...]` reports `gfx_rate` read back from the hardware at each
bring-up point: `650000000` (650 MHz) on most, `319999921` (~320 MHz) on some,
and **`99999975` (~100 MHz, the floor) at least once**. Userspace cannot
manage it — from the live logcat:

```
libperfmgr: Failed to write to node: /sys/class/kgsl/kgsl-3d0/max_pwrlevel with value: 0, fd: -1
libperfmgr: Failed to write to node: /sys/class/kgsl/kgsl-3d0/force_rail_on with value: 0, fd: -1
libperfmgr: Failed to write to node: /sys/class/kgsl/kgsl-3d0/idle_timer with value: 80, fd: -1
```

`fd: -1` is an open failure, so the perf HAL never sets a clock. This is a real
divergence from stock but a low clock should mean slow, not wrong; it is not
established as the cause.
