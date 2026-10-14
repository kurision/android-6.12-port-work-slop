# Tracker: tissot (MSM8953 / Mi A1) hardware on ACK 6.12

Last update: 2026-10-14. Baseline evidence is run123
(`6.12.93-4k-ge1f984e30348`). The USB controller overlay, Rust ashmem
reselection and DSI PLL lifecycle repair are source changes with no device
verdict yet. Kernel builds and boots are done on the user's build host.

Status words: **Working** = function proven on ACK; **Probes** = driver binds,
function unproven; **Partial** = some runtime evidence, known blocker;
**Built** = selected, no device proof; **Off** = not enabled; **Unported** =
no ACK implementation; **N/A** = hardware absent.

Abbreviations: `B` = `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts`,
`S` = `arch/arm64/boot/dts/qcom/msm8953.dtsi`,
`D` = `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-mdss.dtsi`,
`K` = `porting/artifacts/snapshot60/run123/kernel.config`,
`L` = `porting/artifacts/snapshot60/run123-logdump.log`,
`R` = `porting/artifacts/tissot-live.dts` (postmarketOS 6.17 reference,
not ACK), `Donor` = `../kernel_xiaomi_msm8953_fork` (4.19, not proven equal
to the booted stock kernel). Retained logcat rotations
`run123-retained-ack-early-logcat.log*` may include older boots.

See `porting/REPORT-stock-to-target-msm8953.md` for the stock-to-target
adaptation analysis.

## Platform

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| RPM + rpmpd | Built, regulators initialize | `S:193-255`; `drivers/pmdomain/qcom/rpmpd.c`; `K:6315,6597,6658`; `L:249+` | Prove domain votes and suspend/resume |
| GCC / clocks | Partial | `drivers/clk/qcom/gcc-msm8953.c`; `drivers/clk/qcom/mdss-dsi-pll-8953.c` | PLL repair unbooted; no CPU clock/cpufreq/CPR driver (`TRACKER-kgsl-port.md:1976-1979`) |
| Interconnect / NoC | Off | `drivers/interconnect/qcom/msm8953.c` exists; `INTERCONNECT_QCOM_MSM8953` unset (`K:7480-7486`); no DT providers | Add providers/paths; GPU master path missing |
| SMMU / IOMMU | Partial | `S:1136-1255`; `drivers/iommu/arm/arm-smmu/qcom_iommu.c:188-220`; `L:485-493` | MDSS fault handler read unclocked CB_FSR (run119); GPU legacy IOMMU falls back to NOMMU on `gpu_ahb_clk` (`L:529-534`) |
| SPMI / PMIC (PM8953 + PMI8950) | Working (SPMI, RTC, PON) | `DT/pm8953.dtsi`, `DT/pmi8950.dtsi`; `L:186-217` | PMI8950 VADC VDD channel missing; SPM not enabled (`QCOM_SPM=n`) |
| TSENS | Off | `S:473-484,1985-2197`; generic `tsens-v2` matches; `QCOM_TSENS=n` (`K:3680`) | Validate v2 model, enable, prove readings/trips |
| QFPROM | Built, no node | `NVMEM_QCOM_QFPROM=y` (`K:7460`); reference `R:1114-1131` | Add node/cells, verify speed-bin and fusing values |
| BAM DMA | Built | `drivers/dma/qcom/bam_dma.c`; `S` BLSP nodes; `K:6073` | Prove DMA transfers (not PIO) |
| QRTR / SMD / GLINK | Partial | `net/qrtr/smd.c`; `K:1609-1610`; GLINK unset | `vendor.qrtr-ns` exits 1 (`L:3608-3661`); no remote peers until ADSP/MPSS run |

## Display and graphics

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| MDSS MDP5 / DSI (legacy fbdev) | Partial | `drivers/video/fbdev/msm/`; `D`; `porting/PLAN-mdss-display-port.md`; `FrameBuffer[0] 1080x1920` registers | PLL0 never locks in run123 (`L:271-475`); repair unbooted; prove VSYNC and scanout |
| Panel OTM1911 + WLED backlight | Partial | `D:367-430`; `drivers/video/backlight/qcom-wled.c`; LAB/IBB regulators | Re-prove panel init on the legacy path after PLL lock |
| Adreno 506 + Zap | Partial | `drivers/gpu/msm/`; `TRACKER-kgsl-port.md` | Probes; CP init timeout (`-110`, run85); Zap auth unproven; no rendering |
| HDMI / external display | N/A | No board endpoint; USB 2.0 Type-C per [Xiaomi FAQ](https://www.mi.com/global/support/faq/details/KA-07254/) | None |

## Audio

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| Codec: PM8953 integrated WCD (msm8916 analog + digital) + MAX98927 amp | Amp probes; WCD off | `sound/soc/codecs/msm8916-wcd-analog.c`, `msm8916-wcd-digital.c` exist but are unset (`K:5153-5154`); amp rev 0x42 (`L:514-516`); topology `R:2470-2502,3397-3510` | Enable codecs and add machine card; `No soundcards found` (`L:763-764`). Not WCD9335 |
| Q6 / ADSP / APR | Partial | `drivers/remoteproc/qcom_q6v5_pas.c`; `B:426-443` | `adsp.mdt` request fails `-2` (`L:523-525,777-787`) |
| Slimbus | N/A for identified path | Reference card uses MI2S (`R:3397-3496`) | Port only if a real Slimbus endpoint is found |
| Routing / UCM / HAL | Unported | Donor `techpack/audio/asoc/msm8952*.c` | Match stock CAF audio HAL interface; verify all routes |
| Jack / headset buttons | Unported | MBHC in `msm8916-wcd-analog.c` | Needs codec card first |

## Camera

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| Sensors OV12A10 + OV13880 rear, S5K5E8 front | Unported | Donor `techpack/camera-legacy`; stock log probes | Port sensor power/ID paths + CAF camera ABI |
| CCI / CSIPHY / CSID | Unported | CAMSS has no MSM8953 match | MSM8953 resources or CAF port |
| ISP / VFE / CPP | Unported | Donor `CAM/isp`, `CAM/pproc/cpp` | CPP interface required by ROM |
| Actuator / EEPROM / flash | Unported | Donor board `camera.dtsi` | Port with installed-module calibration |
| Camera firmware | Unported consumer | Stock loads `cpp_firmware_v1_5_0.fw` | Follows CPP port |

## Connectivity

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| WCNSS Wi-Fi/BT (WCN3680, wcn36xx) | Partial | `B:675-694`; `drivers/net/wireless/ath/wcn36xx/`; `BT_QCOMSMD=m` (`K:1687`) | `wcnss.mdt` fails `-2` (`L:526-528`); not ath10k |
| IPA (v2.6L) | Unported | Donor `drivers/platform/msm/ipa/ipa_v2/`; upstream IPA starts at v3.1 | Port v2.6L/BAM |
| GNSS / GPS | Unported | Stock QTI GNSS service; MPSS disabled (`S:1226-1274`) | Needs modem + location QMI |
| NFC | N/A | No board node; [GSMArena review](https://www.gsmarena.com/xiaomi_mi_a1-review-1668.php) lists no NFC | None |

## Input and sensors

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| Touchscreen (FocalTech, edt-ft5x06) | Probes | `B:189-209`; `L:810` | Prove multitouch events in Android |
| Fingerprint (Goodix GF3208 or FPC1020) | Unported | Donor `techpack/xiaomi-msm8953/fingerprint` | Identify installed variant first |
| BMI120 / AK09918 / LTR579 | Off | GPIO-I2C topology `R:3983-4014`; bmi160 and ak8975 drivers support the first two; no LTR579 driver | Add nodes, enable drivers, write LTR579 support |
| Haptics (PMI8950 LRA) | Unported | Donor `techpack/xiaomi-msm8953/vibrator` | No upstream SPMI haptics driver |
| Keys (power, vol-up GPIO85, vol-down resin, hall GPIO44) | Probes | `B:25-43,211-215`; `L:205-206,577` | Prove key events and wakeup |

## Power and charging

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| Fuel gauge (PMI8950 FG) | Unported | Donor `qpnp-fg.c`; health HAL: `No battery devices found` (`L:4667-4673`) | Port gauge + battery profile |
| Charger (PMI8950 SMBCHG) | Unported | Donor `qpnp-smbcharger.c` | Port charger, extcon, OTG VBUS |
| USB Type-C / OTG / roles | Partial | `B:391-398` forces peripheral; overlay in `scripts/initramfs-diag/init.c` | Prove adb with UDC `7000000.usb`; PD capability unproven |
| Battery health / thermal throttling | Blocked | Depends on gauge, charger, TSENS, cpufreq | After those land |

## Storage, security, misc

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| eMMC (HS400, RPMB) | Working | `L:765-770` | Keep |
| microSD | Unstable | runs100/101 stuck-busy `-110` (`porting/FAILING-COMPONENTS.md`) | Debug SD init separately |
| QSEE / keymaster / TrustZone | Partial (transactions succeed) | `drivers/misc/qseecom.c`; `L:494-510,1938-2136` | Prove keystore keys, gatekeeper, FBE unlock |
| Ashmem | Fix unbooted | Rust ashmem selected in `scripts/tissot-ack.config`; build preflight in `scripts/build-ack-tissot.sh` | SystemServer died on missing `/dev/ashmem` in retained logcat |
| Notification LED (AW2013, white) | Built | `B:171-193`; `drivers/leds/leds-aw2013.c` | Prove LED and Lights HAL |
| IR blaster (Peel SPI) | Unported | Donor `techpack/xiaomi-msm8953/ir/peelir.c`; Xiaomi FAQ confirms IR | Pick driver matching Consumer IR HAL |

## Modem

| Component | Status | Where the work is | Next proof / blocker |
|---|---|---|---|
| Modem shared memory | Built (SMEM/SMP2P), MPSS off | `drivers/soc/qcom/smem.c`; `QCOM_RMTFS_MEM` off; donor memshare | rmtfs + memshare before MPSS |
| IPA + RMNET | Off | `K:2526,2584` | Needs IPA v2.6L |
| QMI / QRTR channels | Partial | `net/qrtr/`; `vendor.qrtr-ns` exits 1 | Needs remote processors running |
| Xiaomi modem quirks | Unknown | No Xiaomi-specific quirk found | Bring MPSS up before classifying failures |
