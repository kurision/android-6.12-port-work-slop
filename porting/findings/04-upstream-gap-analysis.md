# 04 — android-mainline gap analysis

Base: `kernel/common` branch `upstream-master`, currently **7.2.0**. Sources
vendored under `upstream-refs/` (`msm8953.dtsi`, `pm8953.dtsi`,
`msm8953-xiaomi-tissot.dts`). Line numbers below refer to those files.

## Blocker 0 — the board file does not build

`msm8953-xiaomi-tissot.dts:10` does `#include "pmi8950.dtsi"`, and overrides
`&pmi8950_wled` at line 148. No `pmi8950.dtsi` exists anywhere in the tree, and
`pm8953.dtsi` stops at an empty `pmic@1`. Reproduced locally:

```
$ sh build-test/build-dts.sh build-test/dts-upstream msm8953-xiaomi-tissot.dts /tmp/o.dts
dts-upstream/msm8953-xiaomi-tissot.dts:10:10: fatal error: 'pmi8950.dtsi' file not found
```

Everything else the board file references resolves: 37 of 38 `&label`
references exist (the regulator stubs `pm8953_l1..l23`, `pm8953_s1/s3/s4`,
`vph_pwr` and the pinctrl states are defined inside the board file itself).

Fix drafted and verified: `drafts/pmi8950.dtsi` (haptics + WLED + lab/ibb) —
with it the tree compiles to a 76,593-byte decompiled DTS with only style
warnings (three `duplicate unit-address` pairs where an I2C and a SPI QUP share
an address, plus one `avoid_unnecessary_addr_size` on `dsi@1a94000`).

## Present upstream, identical to the live device

CAF compatible strings were copied wholesale, so there is almost no driver-name
churn to fight:

* CPU topology: 8 `cpu@…` nodes, `enable-method = "psci"`, `cpu-map`, and
  `#cooling-cells = <2>` on every CPU.
* `qcom,smem` with `qcom,rpm-msg-ram` + `hwlocks` (296-350); `smp2p-adsp`
  (smem 443/429), `smp2p-modem`, `smp2p-wcnss` (451/431); `smsms`.
* `gcc-msm8953`, `qcom,msm8953-pinctrl` (tlmm), `bimc`/`pcnoc`/`snoc`/`snoc-mm`
  interconnects, all four IOMMUs (`qcom,msm-iommu-v1/v2` + contexts).
* `qcom,msm8953-tsens` + 9 CPU/GPU thermal zones with the same sensor indices.
* `qcom,pshold` at 0x4ab000 (CAF calls it `restart`).
* MDP5 display: `qcom,mdss`, `qcom,msm8953-mdp5`, two `qcom,mdss-dsi-ctrl`
  hosts and two `qcom,dsi-phy-14nm-8953` PHYs.
* GPU node `gpu@1c00000` `qcom,adreno-506.0`, `reg-names = "kgsl_3d0_reg_memory"`,
  `#cooling-cells = <2>` — same as the live DT, plus interconnects/OPP table, and
  `status = "disabled"`.
* RPM: `qcom,msm8953-rpm-proc`, `qcom,rpm-msm8953` (rpm_requests), `qcom,rpmcc-msm8953`
  with OPP table, `qcom,msm8953-rpmpd` with 8 OPPs.
* Remoteprocs: `qcom,msm8953-mss-pil`, `qcom,msm8953-adsp-pil` with the full APR
  service tree (`qcom,apr-v2`, `qcom,q6core`, `qcom,q6afe` + `-clocks` + `-dais`,
  `qcom,q6asm` + `-dais`, `qcom,q6adm` + `qcom,q6adm-routing`).
* `qcom,pronto-v3-pil` wcnss with the same `qcom,wcnss` / `-wlan` / `-bt`
  subtree and identical SMEM state indices.
* Peripherals: `qcom,msm8953-sdhci`/`qcom,sdhci-msm-v4` (UFS + SD),
  `qcom,i2c-qup-v2.2.1`, `qcom,spi-qup-v2.2.1`, `qcom,msm-uartdm-v1.4`,
  `qcom,msm8953-dwc3`, `qcom,msm8953-qusb2-phy`, `qcom,prng`.
* Interrupts: `qcom,msm-qgic2` (upstream keeps the CAF string).
* Board file content: gpio-keys (44 power, 85 hall), `maxim,max98927` @0x3a,
  `awinic,aw2013` @0x45, `edt,edt-ft5406` @0x38, resin key, `pmi8950_wled`
  override, rpm_requests supplies, UFS/SD supplies + CD gpio 133, uart console,
  usb3 + dwc3.

## Missing / broken, in port order

| Subsystem | Live device has | Upstream state | Work |
|---|---|---|---|
| PMI8950 PMIC | pmic@3: haptics, WLED, lab, ibb, pwm | **absent** → board file cannot build | add `pmi8950.dtsi` (drafted) |
| cpufreq | 8 OPPs, 652.8 kHz – 2.016 GHz, CPR4 voltage table | CPU nodes have **no** `clocks` and **no** `operating-points-v2`; `qcom,gcc-msm8953.h` has no CPUSS ids and `drivers/clk/qcom/gcc-msm8953.c` has zero CPUSS entries | add GCC CPUSS/APC clocks (header + driver) then OPP tables |
| CPR4 | `qcom,msm8953-cpr4pd` @0xb018000 (fusing_rev, speed_bin) | absent | optional; needed for accurate DVFS voltages |
| Panel | OTM1911 FHD DSI panel node | DSI host/PHY exist, **no panel node and no driver** (`panel-orisetech-otm8009a.c` is a different chip) | write a DSI panel driver + node |
| Backlight | `qcom,pmi8950-wled` (2 strings, 20 mA limit, 29.5 V OVP, ext-PFET, CABC) | no Qualcomm LED driver in `drivers/leds`; no `awinic,aw2013` driver either | write a WLED driver (or fall back to a fixed backlight) |
| GPU | adreno 506, a506 zap firmware present | node present but `status = "disabled"` | enable once display works |
| WLAN | wcnss + wcn36xx working | node present but `status = "disabled"`, no firmware in tree | enable + supply firmware from `persist` |
| Bluetooth | stack loads, no HCI device | `qcom,wcnss-bt` node exists, no firmware | out of scope unless firmware is extracted |
| Thermal CPU/GPU | 9 zones, trips, cpufreq+devfreq cooling maps | DT identical, **no `tsens-8953` driver** | write `tsens-8953.c`; find calibration source |
| Thermal PMIC | `pm8953-thermal` via VADC ch 8 | works upstream | — |
| Audio | sound-card machine, WCD analog + digital codec, q6adm/q6voice, MAX98927 | APR DAIs exist; `pmic@1` empty; no `msm8916-wcd-*` codec in `sound/soc/codecs` (only wcd9335/934x/937x/classh); `qcom,msm8953-qdsp6-sndcard` machine absent | port machine driver + codec driver |
| Sensors | ak8975 (0x0c), bmi120 (0x68), ltr579 (0x53) | nodes absent from the board file | add 3 nodes; `edt-ft5x06` exists for touch |
| Charger / fuel gauge | `qcom,pmi8996-smbchg`, `qcom,pmi8996-fg` on pmic@2 | absent | out of scope (no upstream driver) |
| Camera, modem | nothing on this reference kernel | nothing | out of scope |

## reserved-memory caveat

The upstream board file opens with

```dts
/delete-node/ &adsp_fw_mem;
/delete-node/ &qseecom_mem;
/delete-node/ &wcnss_fw_mem;
```

i.e. it assumes the **Android bootloader** already reserved those regions in the
DTB it appends. If you boot with your own DTB (lk2nd, fastboot with an explicit
dtb, U-Boot), delete those three lines: the sizes upstream declares (18 MiB adsp,
25 MiB ssecem, 7 MiB wcnss) match this hardware exactly.

## Naming note for 6.12 vs trunk

Current trunk moved `drivers/sound/` to `sound/`. When targeting 6.12 the codec
Makefile lives at `drivers/sound/soc/codecs/Makefile`. Same symbol list either
way (`CONFIG_SND_SOC_MAX98927`, `CONFIG_SND_SOC_WCD934X`, …).