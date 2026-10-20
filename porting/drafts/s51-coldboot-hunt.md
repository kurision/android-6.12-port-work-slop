# Snapshot51 coldboot hunt (34.3 s vs stock 2.8 s)

> **Current state: CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUILD_TISSOT.md](../../BUILD_TISSOT.md).

## Established (snapshot50 run1, no guessing)
- `mount_all --early` at t≈84 s because init blocks on
  `wait_for_coldboot_done`; ueventd reports `Coldboot took 34.309 s`.
- eMMC HS400 + SD SDR104: not an I/O-mode problem.
- Coldboot window (42–80 s) carries only ~54 KB of log: the stall is
  SILENT. Serial-backpressure theory dead by measurement (1.4 KB/s).
- Firmware/modprobe/apex suspects cleared: helper fallback off (fast
  fail), `kcmdlinemodprobe` 0.28 s, APEX scan 0.6 s.

## s51 boot 1 (same image as touch verdict boot)
- Record `Coldboot took` baseline re-measurement. No changes.
- If it reproduces ~30 s+, proceed to bisect below.

## Bisect matrix (one variable per boot, DT-only via dtc + repackage)
Order by suspicion (blocking-sysfs-attribute likelihood):
1. `&lpass` (ADSP/audio QDSP6: remoteproc + APR sysfs, pil relocs).
2. `&mdss` / `&mdss_dsi0` (DRM sysfs: dpms/state attributes).
3. `&gpu` (adreno sysfs/gpu-state).
4. `&qcom_seecom` / smd/rpm (qrtr,smd sysfs channels).
- Disable node (`status = "disabled"`), recompile dtb with
  `dtc`, repackage with `package-diag-boot.py`, boot, read coldboot.
- A drop to single digits names the subtree; then bisect inside it
  (child nodes / driver attributes) the same way.

## If bisect fails (no single subtree responsible)
- Suspect per-uevent fixed cost × device count: compare coldboot with
  `init` verbosity? Not available. Fallback: kernel `ftrace` via
  function_graph on `driver_probe_device`? Probes are done pre-coldboot;
  instead trace `sysfs` read handlers during the window — needs a
  builder kernel with ftrace + a trigger. Last resort, not first.
