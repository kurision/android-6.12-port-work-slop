# 00 — Roadmap

> **Historical record - undated.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

Target: Xiaomi Mi A1 (`tissot`) on android-mainline. Definition of "usable" at
the end of each phase, and what must be true before starting it.

| # | Phase | Done when | Depends on | Risk |
|---|---|---|---|---|
| 1 | DTS builds | `make ARCH=arm64 msm8953-xiaomi-tissot.dtb` succeeds, image boots to a console | — | none |
| 2 | cpufreq | all 8 OPPs appear in `scaling_available_frequencies`, governor changes frequency | 1 | clock-driver plumbing in GCC |
| 3 | Display | DRM reports 1080×1920, backlight works, `modetest` shows the panel | 1 (+ pmi8950 lab/ibb) | new panel driver |
| 4 | WLAN | `wlan0` associates with the AP using firmware from `/lib/firmware` | 1 | firmware not on the device filesystem |
| 5 | Thermal / audio / sensors | CPU zones report sane temps and throttle; a sound card enumerates; touch/IMU work | 1 | new tsens + codec drivers |

## Will this reach a boot animation?

Depends entirely on which userspace you mean. Kernel-side scorecard:

| Requirement for pixels | Status |
|---|---|
| Panel driver (OTM1911, 1080×1920, 4-lane DSI) | exists in prior art (`linux-panel-drivers`), absent in android-mainline |
| MDP5/DSI/DSI-PHY host driver | upstream, unmodified |
| Early framebuffer from bootloader splash | `cont-splash_mem` + `simple-framebuffer` already used by the 6.12 prior-art DTS |
| Backlight | **no driver** for `qcom,pmi8950-wled` / `awinic,aw2013` — needs a driver or a fixed-backlight hack |
| GPU 3D (for SurfaceFlinger) | Adreno 506 = a5xx, supported upstream in principle, but no kernel-side blocker and no userspace driver on this port |

* **Mainline distro (postmarketOS, Arch, Ubuntu):** yes, comfortably. That is
  what the device already does today — the reference kernel brings up the panel
  and a framebuffer console. The port's job is to keep that working on a
  different base, plus backlight brightness control.
* **Android userspace boot animation:** the kernel is *not* the blocker. It
  needs `gralloc` + a hardware composer (drm_hwcomposer), a userspace GPU driver
  over the DRM backend, binder, dmabuf-heap, fscrypt/ext4-crypto and AVB — all
  of which are userspace/graphics-stack work on top of a working DRM master.
  Realistic first milestone is `modetest` + a userspace splash, not
  SurfaceFlinger.


## Ordering rationale

* **Phase 1 is a hard prerequisite**: nothing else can even be tested while the
  board file fails to preprocess.
* **Phase 3 before phase 4**: a headless kernel is fine for bring-up (use the
  UART console / `msm_serial`), so WLAN can be deferred; but you want a screen
  before you start chasing driver behaviour.
* **Phase 5 last**: thermal is the difference between "works" and "throttles or
  dies under load", but audio and thermal both need new drivers and neither is
  needed to prove the platform boots.

## Ground rules

* Collect device truth from the device, not from the 4.19 CAF tree: the live FDT
  (`artifacts/tissot-live.dts`) is authoritative for register layout, and the
  bootlog is authoritative for "does it bind".
* Prefer upstream-compatible compatibles over driver patches. Where the CAF
  string already matches upstream (`qcom,msm-qgic2`, `qcom,pronto-v3-pil`,
  `qcom,dsi-phy-14nm-8953`, …), keep it.
* Never port a CAF driver's behaviour implicitly; if a node exists but no driver
  binds it on mainline, that is a task, not a given.
* Verify each phase on hardware before starting the next: boot, capture
  `dmesg`, run the phase's check commands, save the log next to the plan.

## Where the numbers come from

| Data | Source |
|---|---|
| Memory map, register addresses, IRQ indices, MAC/BD addresses, panel wiring | `findings/01`, `artifacts/tissot-live.dts` |
| OPP frequencies and voltages | bootlog CPR4 table (lines 307-314) + `sysfs` scaling table |
| Thermal zones/trips/sensor map | bootlog + `sysfs` + DT (see `findings/02`) |
| Firmware versions/banner | bootlog (see `findings/03`) |
| Upstream state of every node | `findings/04`, verified against `upstream-refs/` |