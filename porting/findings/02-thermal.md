# 02 — Thermal

Evidence: `sysfs` dumps taken over ssh (`/sys/class/thermal/*`), the live DT
(`artifacts/tissot-live.dts`), and the bootlog.

## Runtime state on the reference kernel

11 thermal zones, 2 cooling devices, all zones on the `step_wise` governor.

| Zone | Idle temp | Trips | Cooling map |
|---|---|---|---|
| `cpu0-thermal` … `cpu7-thermal` (8 zones, one per CPU) | 30.9 – 32.2 °C | passive 80 °C, critical 100 °C (hysteresis 2 °C) | `cpufreq-cpu0` cooling device |
| `gpu-thermal` | 29.9 °C | passive 70 °C, critical 90 °C | `devfreq-1c00000.gpu` |
| `pm8953-thermal` | 33.1 °C | passive 105 °C, hot 125 °C, critical 145 °C | none |
| `qcom-battery` | 29.0 °C | **none** | none |

Cooling devices: `cpufreq-cpu0` (max_state 7 = 8 OPPs) and `devfreq-1c00000.gpu`
(max_state 7). There is **no CPU-idle cooling device** even though
`cpuidle: using governor menu` (bootlog line 144) — idle depth is not thermally
gated on this reference kernel.

## DT structure

`artifacts/tissot-live.dts:3644-3931`:

* `thermal-zones` with per-zone `polling-delay-passive = <250>` (ms),
  `trips {}`, and `cooling-maps { map0 { trip = <&passive>;
  cooling-device = <&cpufreq 0xffffffff 0xffffffff> } }`.
* CPU zone → TSENS sensor indices: cpu0-3 → 9,10,11,12; cpu4-7 → 4,5,6,7;
  gpu → 15.
* `pm8953-thermal` uses an **SPMI VADC channel**, not TSENS:
  `thermal-sensors = <&pmic_adc>`, `io-channels = <... 0x8>`,
  `io-channel-names = "thermal"` (dts:2398-2401).
* `qcom-battery` zone has no trips and no cooling map.

Sensor node (`dts:1148-1156`):

```dts
thermal-sensor@4a9000 {
        compatible = "qcom,msm8953-tsens", "qcom,tsens-v2";
        reg = <0x4a9000 0x1000>, <0x4a8000 0x1000>;   /* TM, SROT */
        #qcom,sensors = <0x10>;                      /* 16 sensors */
        interrupts = <0 184 4>, <0 314 4>;           /* uplow, critical */
        interrupt-names = "uplow", "critical";
        #thermal-sensor-cells = <1>;
};
```

**There is no `qcom,tsens-opp` calibration property** — the fuse calibration is
not in the device tree. CAF sources it elsewhere (SMEM/OTP), which is the single
unknown for a mainline TSENS driver.

## What android-mainline has

* `upstream-refs/msm8953.dtsi:499` declares the identical TSENS node
  (`qcom,msm8953-tsens`, same regs, 16 sensors).
* `upstream-refs/msm8953.dtsi:2267-2451` declares the same 9 CPU/GPU zones with
  the same sensor indices and the same 80/100 °C and 70/90 °C trips.
* `upstream-refs/pm8953.dtsi:11-33` declares `pm8953-thermal` fed by
  `pm8953_temp: temp-alarm@2400` (`qcom,spmi-temp-alarm`) + `pm8953_vadc`
  (`qcom,spmi-vadc`) — that part **works on upstream today**.
* Driver gap: `drivers/thermal/qcom/` in current trunk contains
  `tsens.c`, `tsens-v0_1.c`, `tsens-v1.c`, `tsens-v2.c`, `tsens-8960.c`,
  `lmh.c`, `qcom-spmi-adc-tm5*.c`, `qcom-spmi-mbg-tm.c`,
  `qcom-spmi-temp-alarm.c`. **There is no `tsens-8953.c`** and no
  `msm_thermal`. So on upstream the CPU/GPU zones are declared but never bound:
  no CPU temperature, no CPU throttling.
* `qcom-battery` is CAF `qcom_battery_mdm` (driver does not exist upstream, and
  the phone has no fuel-gauge driver either) — drop that zone.

## Consequence for the port

Writing `drivers/thermal/qcom/tsens-8953.c` (register the pm8953 TSENS, 16
sensors, two register regions, uplow/critical interrupts) gives CPU + GPU
thermal zones for free, because the upstream DT and the upstream thermal core
already match. Until calibration is sourced, expect either bogus values or a
driver that refuses to register; `lmh.c` + a `tsens-alarm` node is the fallback
route to at least get critical-throttling events.