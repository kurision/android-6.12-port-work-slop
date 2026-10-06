# 01 — Live device inventory

Source: `artifacts/tissot-live.dts` (decoded from the FDT the running kernel
received) and `artifacts/dmesg-live.txt`. Line references are to those files.

## Platform

| Item | Value | Evidence |
|---|---|---|
| Board | Xiaomi Mi A1 (`xiaomi,tissot`) | dmesg `Machine model: Xiaomi Mi A1` |
| SoC | MSM8953 (Snapdragon 625), 8× Cortex-A53 @ up to 2.016 GHz | dtsi `cpus`, dmesg CPR4 table |
| GPU | Adreno 506, `qcom,adreno-506.0`, regs 0x1c00000 | dts:2133-2151 |
| PMICs | pmic@0 pm8953 (PON/PMIC RTC/GPIO/temp-alarm/VADC), pmic@1 (audio codec), pmic@2 pmi8950 (charger + fuel gauge), pmic@3 pmi8950 (haptics, WLED, lab/ibb) | dts:2475, 2512, 2630 |
| Reference kernel | `6.17.7-msm8953` (postmarketOS, Alpine 15.2 toolchain) | dmesg line 2 |
| Boot args | `quiet loglevel=2` + pmos UUID args | dmesg line 62 |
| KASLR | disabled, no seed | dmesg line 3 |
| Memory | RAM 0x10000000–0xffffffff (~3.5 GiB usable), 4 KiB pages, single NUMA node, only the DMA zone in use | dmesg lines 24-26, 46, 126 |

## reserved-memory (live, `artifacts/tissot-live.dts:901-992`)

| Node | Base | Size | Notes |
|---|---|---|---|
| `smem@86300000` | 0x86300000 | 1 MiB | `qcom,rpm-msg-ram = <0x32>`, `hwlocks = <0x33 0x03>` |
| `reserved@86400000` | 0x86400000 | 4 MiB | unnamed |
| `mpss@86c00000` | 0x86c00000 | 0x6a00000 (108 MiB) | modem firmware |
| `adsp@8d600000` | 0x8d600000 | 0x1200000 (18 MiB) | matches upstream `adsp_fw_mem` |
| `dfps-data@90000000` | 0x90000000 | 4 KiB | fingerprint |
| `cont-splash@90001000` | 0x90001000 | 0x5eec00 | bootloader splash, reused as panel framebuffer |
| `venus@91400000` | 0x91400000 | 7 MiB | |
| `mba@92000000` | 0x92000000 | 1 MiB | modem boot |
| `gps@93000000` | 0x93000000 | 2 MiB | |
| `zap@95000000` | 0x95000000 | 8 KiB | `shared-dma-pool` for GPU zap shader |
| `rmtfs@f2d00000` | 0xf2d00000 | 0x180000 | `qcom,rmtfs-mem`, client-id 1 |
| `qseecom@84a00000` | 0x84a00000 | 0x1900000 (25 MiB) | matches upstream `ssecmem` |
| `wcnss@8e800000` | 0x8e800000 | 7 MiB | matches upstream `wcnss_fw_mem` |
| `ramoops@9ff00000` | 0x9ff00000 | 1 MiB | record 4K / console 512K / ftrace 4K / pmsg 32K |

The four Android-relevant blocks (`qseecom`, `adsp`, `wcnss`, `ramoops`) match
android-mainline's tissot DTS byte-for-byte.

## Display

* DSI host `dsi@1a94000`, PHY `phy@1a94400` (`qcom,dsi-phy-14nm-8953`) — dts:1917-2013.
* Panel: `panel@0 { compatible = "mdss,otm1911-fhd", "xiaomi,tissot-panel" }`
  (dts:1983-1998). 1080×1920 (`U:1080x1920p-0`, dmesg line 390), DPU hw revision
  `0x10100000`, 4 data lanes, DSI OPPs 131.25 / 210 / 262.5 MHz.
* Panel rails: `backlight` → `pmi8950_wled` (pmic@3 `leds@d800`),
  `vsp-supply` → `pmi8950_lab`, `vsn-supply` → `pmi8950_ibb`; reset GPIO 61.
* Second DSI host exists but is `status = "disabled"` (dts:2028).

## Audio

* Machine: `sound-card@c051000`, `compatible = "qcom,msm8953-qdsp6-sndcard"`,
  mic/spkr/pri/quin iomux at 0xc051000/…/0xc052000 (dts:3397-3496).
* Codecs: `qcom,pm8916-wcd-analog-codec` at pmic@1 `audio-codec@f000`
  (dts:2475) and `qcom,msm8916-wcd-digital-codec` at 0xc0f0000 (dts:3498).
* Amplifier: `maxim,max98927` on i2c_1 0x3a, reset GPIO 86 (dts:2951).
* DAI components: `qcom,q6adm-routing` (dts:3613), `qcom,q6voice-dais` (dts:3624),
  plus the AFE/ASM DAIs under `remoteproc@c200000`.
* Runtime: `ALSA device list` shows one card, `xiaomi-tissot` (dmesg 321-322, 543).

## Input / sensors / misc

| Device | Node | Compatible | Notes |
|---|---|---|---|
| Touch | i2c_2 0x38 | `edt-ft5406` / ft5x06 | binds as `generic ft5x06 (3b)`, dmesg 366 |
| Accelerometer | i2c_0 0x0c | `ak8975` | dmesg 510, "mounting matrix not found: using identity" |
| IMU | i2c_0 0x68 | `bosch,bmi120` | present in DT, does **not** bind on the reference kernel |
| ALS/proximity | i2c_0 0x53 | `liteon,ltr579` | present in DT, does not bind |
| LED driver | i2c_1 0x45 | `awinic,aw2013` | panel backlight string driver |
| Speaker amp | i2c_1 0x3a | `maxim,max98927` | |
| Keys | — | `gpio-keys` | power GPIO 44, hall GPIO 85, dmesg 317 |
| PMIC keys | pmic@0 pon@800 | `qcom,pm8941-pwrkey`, `qcom,pm8941-resin` | dmesg 509-511 |
| Haptics | pmic@3 haptics@c000 | `qcom,pmi8950-haptics` | binds, dmesg 512 |
| Charger / fuel gauge | pmic@2 | `qcom,pmi8996-smbchg`, `qcom,pmi8996-fg` | in DT, **no driver on the reference kernel** (no battery/charger in dmesg) |
| MPSS | remoteproc@4080000 | `qcom,msm8953-mss-pil` | boots `mba.mbn` then `mpss` (dmesg 545-549) |
| ADSP | reserved `adsp@8d600000` + remoteproc | `qcom,msm8953-adsp-pil` | boots `adsp.mdt`, dmesg 519-522 |
| WCNSS | remoteproc@a204000 | `qcom,pronto-v3-pil` | boots `wcnss.mdt`, dmesg 515-517 |
| Storage | UFS `mmc@7824900` + SD `mmc@7864900` | `qcom,msm8953-sdhci`,`qcom,sdhci-msm-v4` | 58.2 GiB HCG8a4 UFS + 29.1 GiB SD, RPMB chardev present |
| USB | `usb@70f8800` (live node name `usb@7000000`) | `qcom,msm8953-dwc3` | gadget works on the reference kernel |

## What does *not* appear anywhere

No camera (no CSI/VIFIDEOC/sensor probes), no modem data path, no QRTR, no NFC,
no battery/charger driver, no fingerprint driver. These are absent in the
downstream 4.19 tree too (as CAF drivers), so none of them are in scope for a
mainline port.