# Phase 5 — thermal, audio, sensors

Everything here is optional for "boots and displays", and each item is a new
driver rather than a DT edit.

## 5a — thermal (do this first: it protects the hardware)

DT is already correct upstream; only the driver is missing
(`findings/02`). Write `drivers/thermal/qcom/tsens-8953.c` on top of the existing
`tsens.c` core:

* register the pm8953 TSENS (`qcom,msm8953-tsens`, compatible `qcom,tsens-v2`),
  two regions: 0x4a9000 (TM) and 0x4a8000 (SROT);
* 16 sensors, 10-bit, 5 °C/LSB (compare `tsens-8960.c`);
* interrupts: `uplow` = 184, `critical` = 314, both rising;
* the DT names the zones and the sensor index per zone, so `tsens.c` will create
  the 9 CPU/GPU zones with the existing trip points (80/100 °C CPU, 70/90 °C GPU)
  and attach the cpufreq/devfreq cooling devices automatically.

**Open problem: calibration.** The device tree has no `qcom,tsens-opp`, so the
per-device fuse calibration must come from somewhere else. Options, in order of
effort: SMEM (CAF reads it there), the TSENS OTP/NVM interface, or hard-coding
typical pm8953 values and accepting ±5 °C. Validate by comparing against the
known-good readings on the reference kernel (idle ~30-32 °C CPU, ~30 °C GPU,
~33 °C pm8953).

The PMIC zone (`pm8953-thermal` via `qcom,spmi-temp-alarm` + VADC channel 8)
already works upstream. Drop the CAF `qcom-battery` zone — no driver.

## 5b — audio

Live machine: `sound-card@c051000` / `qcom,msm8953-qdsp6-sndcard` with
mic/spkr/pri/quin iomux, WCD analog codec at pmic@1 `f000`
(`qcom,pm8916-wcd-analog-codec`), WCD digital codec at 0xc0f0000
(`qcom,msm8916-wcd-digital-codec`), `qcom,q6adm-routing`, `qcom,q6voice-dais`,
MAX98927 amp on i2c_1 0x3a (`CONFIG_SND_SOC_MAX98927` exists upstream).

Work items:

1. A machine driver for the sound card (the CAF `msm-asoc-sndcard` equivalent for
   this topology) — model it on whatever msm8996 machine driver exists upstream.
2. Codec drivers for the two WCD nodes; current upstream only has
   `wcd9335`, `wcd934x`, `wcd937x`, `wcd-classh`, `wcd-mbhc`, `wcd-common` in
   `sound/soc/codecs/Makefile` (trunk; `drivers/sound/soc/codecs` on 6.12).
   The analog codec is the hard part.
3. `pm8953.dtsi`'s `pmic@1` is empty — add the codec node (and the sound card)
   to the board file.

Verification: `cat /proc/asound/cards` shows one card, `aplay -l` lists the
DAI links, a test tone plays through the amp.

## 5c — sensors (cheap wins)

Add the three nodes the live DT has and the upstream board file lacks:

| Address | Compatible | Bus |
|---|---|---|
| 0x0c | `ak8975` (accelerometer) | i2c_0 |
| 0x53 | `liteon,ltr579` (ALS/proximity) | i2c_0 |
| 0x38 | `edt,edt-ft5406` (touch) | i2c_3 — already in the board file |

Drivers: `edt-ft5x06` and `ak8975` exist upstream; confirm an `ltr579` driver
exists (I found no `ltr*` in `drivers/iio/illuminance`) — if not, ALS/proximity
is the lowest-value item on this list.

## 5d — charging (out of scope for now)

`qcom,pmi8996-smbchg` + `qcom,pmi8996-fg` on pmic@2 have no upstream driver, and
the reference kernel shows no battery/charger at all. Leave disabled.