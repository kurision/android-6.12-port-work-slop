# Phase 3 — display

> **Historical record - undated.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

**Goal:** a working 1080×1920 panel with backlight, driven by upstream msm DRM.

## Why this phase is the real work

Upstream msm8953.dtsi has the MDP5 DSI host (`mdss_dsi0 @1a94000`), the
14 nm PHY (`qcom,dsi-phy-14nm-8953`) and a `gpu` node — but the board file adds
**no panel node**, and there is no OTM1911 driver upstream (`drivers/gpu/drm/panel`
has `panel-orisetech-otm8009a.c`, which is a different chip). So:

* write `drivers/gpu/drm/panel/panel-otm1911.c` (mipi-dsi panel driver, four
  variants of init code are in the wild — take the sequence from the CAF driver
  or from any existing OTM1911 panel driver you can crib from), and
* add a `panel@0` node to the board file.

## Node data (from `artifacts/tissot-live.dts:1983-1998` + dsi host 1917-1999)

```
&mdss_dsi0 {
        panel@0 {
                compatible = "xiaomi,tissot-panel";   /* CAF also lists mdss,otm1911-fhd */
                reg = <0>;
                reset-gpios = <&tlmm 61 GPIO_ACTIVE_LOW>;
                backlight = <&pmi8950_wled>;          /* pmi8950 labibb/pmic@3 */
                vsp-supply = <&pmi8950_lab>;
                vsn-supply = <&pmi8950_ibb>;
                port { endpoint { remote-endpoint = <&dsi0_out>; data-lanes = <0 1 2 3>; }; };
        };
        /* DSI OPPs present in CAF: 131.25 / 210 / 262.5 MHz */
        status = "okay";
};
```

Also make sure `mdss`, `mdp`, `mdss_dsi0`, `mdss_dsi0_phy` are enabled (upstream
leaves them `status = "disabled"` by default) and that `dsi_phy` is fed by a
regulator — the live DT uses `vddio-supply` on the PHY node.

## Backlight: needs its own driver

`pmi8950_wled` has **no upstream driver** (`drivers/leds` contains nothing
Qualcomm or awinic). Two options:

1. Write `drivers/leds/leds-qcom-wled.c` for `qcom,pmi8950-wled`: single
   brightness register (two strings, external PFET, CABC), 20 mA current limit,
   29.5 V OVP, plus the `ovp`/`short` IRQs from phase 1's dtsi. Backlight
   brightness then shows up under `/sys/class/backlight/`.
2. Shortcut for bring-up: a `regulator-fixed` or a simple GPIO enable to at least
   light the panel at full brightness.

The `awinic,aw2013` LED controller at i2c_1 0x45 (present in the live DT and in
the upstream board file) also has no upstream driver — it is the notification
LED bank, not the backlight, so it can stay dead for now.

## GPU

Enable `&gpu` (upstream sets `status = "disabled"`). It declares
`qcom,adreno-506.0` and `firmware-name = "qcom/msm8953/xiaomi/tissot/a506_zap.mdt"`;
make sure that file exists in the firmware tree. Start with display-only
(`CONFIG_DRM_MSM_GPU` off) to rule out 3D issues, then re-enable if you need
render nodes. The `gpu-thermal` cooling device comes from the DRM devfreq, which
is what phase 5's thermal map wants.

## Risks

* Panel init sequence wrong → white/garbage screen but the DRM pipeline looks
  healthy. Keep a UART console available.
* Missing VSP/VSN rails → panel backlight on, no image. Phase 1's `labibb` nodes
  plus `vsp-supply`/`vsn-supply` must be right.
* Cont-splash reserved memory (`cont-splash@90001000`, 6,075 KiB) is what the
  bootloader draws on; if the kernel reuses it as a framebuffer you can get a
  "framebuffer is not in virtual address space" warning (`dmesg-live.txt:384`).

## Verification

```sh
dmesg | grep -E 'dpu|display-controller|dsi|Initialized msm|adreno|panel'
modetest -M msm                       # or /sys/kernel/debug/dri/0/state
cat /sys/class/drm/card0-HDMI-A-1/modes      # 1080x1920 expected
cat /sys/class/backlight/*/{brightness,max_brightness}
dmesg | grep -iE 'error|fail' | grep -i dsi
```

Accept when `modetest` shows a 1080×1920 mode, a test pattern appears on the
panel, and `brightness` writes change it.