# Porting guide verification — 2026-10-05

Verdict: **the captured evidence is useful, but the guide is not reliable as an implementation plan yet.** Several proposed driver projects are unnecessary, the PMIC draft contains incorrect interrupt values, and the reserved-memory advice misreads the board DTS.

Scope: README, all five existing findings, all six phase-plan documents, the PMIC draft, standalone build harness, logging documentation and collectors. Checked against local DT/log/config captures and accessible primary upstream sources. No phone was flashed or runtime settings changed. Original guide files remain unchanged.

## Reproduced locally

```sh
sh build-test/build-dts.sh build-test/dts-upstream msm8953-xiaomi-tissot.dts /tmp/porting-verify-upstream.dts
# fails: pmi8950.dtsi missing from this standalone input directory
sh build-test/build-dts.sh build-test/dts-patched msm8953-xiaomi-tissot.dts /tmp/porting-verify-patched.dts
# succeeds: 76,593 bytes of DTS text; five warnings
```

The warnings are four duplicate QUP unit addresses plus one DSI address/size-cell warning. README/findings incorrectly count three duplicate pairs. The harness uses `dtc -O dts`, so this proves preprocessing and DTS compilation, **not** a binary DTB build, schema validation, kernel build, or successful boot. The patched copy matches the draft.

## High-priority corrections

### 1. The missing-PMIC claim confuses an incomplete harness with upstream

Affected: README status/reproduction section, findings/04, phase 1, prior-art conclusions.

Only three upstream DTS files were vendored; `pmi8950.dtsi` was omitted. Linux upstream contains that file, including `pmi8950_wled` and LAB/IBB. The failure reproduced above establishes a missing local include, not that the complete upstream tree cannot build. Use the target tree's existing file before introducing a replacement. [Upstream PMI8950 DTSI](https://raw.githubusercontent.com/torvalds/linux/master/arch/arm64/boot/dts/qcom/pmi8950.dtsi).

The exact android-common `upstream-master` file could not be retrieved during this review. Therefore the claim about that branch remains unverified; pin a commit and build its complete tree before calling it an upstream blocker.

### 2. The PMIC draft is not ready to drop in

Affected: `drafts/pmi8950.dtsi:29`, `:46`, `:63`; phase 1.

Haptics interrupt cells use `0xc000` instead of peripheral ID `0xc0`; WLED uses `0xd800` instead of `0xd8`. Both disagree with `artifacts/tissot-live.dts:2663` and `:2679`. Trigger types also changed: live haptics uses both edges, WLED rising edges, and LAB/IBB OCP level-low; the draft uses rising/level-high in those places. LAB/IBB's OCP level-low wiring also appears in the [upstream binding example](https://www.kernel.org/doc/Documentation/devicetree/bindings/regulator/qcom-labibb-regulator.yaml).

`dtc` accepts these cells syntactically; it cannot establish their hardware correctness. Reuse the upstream PMIC definition and review any necessary board overrides against bindings and hardware.

### 3. The reserved-memory explanation is wrong

Affected: findings/04 reserved-memory caveat; phase 1 step 3; phase 4 step 2.

`upstream-refs/msm8953-xiaomi-tissot.dts:13` deletes the inherited `adsp_fw_mem`, `qseecom_mem`, and `wcnss_fw_mem`, then **redefines all three** at lines 46–59. The generated patched DTS retains reservations at 0x84a00000, 0x8d600000 and 0x8e800000. The deletes relocate inherited nodes; they do not delegate reservation to the Android bootloader. Do not remove them based solely on bootloader choice. Inspect the final FDT and reservation map instead.

### 4. Phase 2 proposes the wrong clock path and CPU policy

Affected: phase 2, roadmap, findings/04.

The reference DT supplies CPU clocks from `qcom,apcs-cc-msm8953` at 0xb011050 (`artifacts/tissot-live.dts:3311`), not GCC CPUSS gates. Absence of a `CPUSS` substring in GCC does not justify inventing CPU clocks there. The reference config enables `CONFIG_QCOM_CLK_APCS_MSM8953` and `CONFIG_QCOM_CPR4PD`; compare those implementations with the pinned target and carry the required APCS/PLL/CCI and power-domain support together.

The captured `device-facts.tar` member `cpufreq.txt` shows **one policy affecting CPUs 0–7**, with eight frequencies from 652800 to 2016000 kHz. Both CPU groups use Cortex-A53 and the same OPP-table phandle. The proposed big/little split with independent policies is unsupported by this baseline. The listed CPR voltage table does match the bootlog, but is device-specific evidence, not permission to skip voltage coordination or hardware-bin filtering. Treat valid voltage/frequency sequencing as a prerequisite for enabling high OPPs.

### 5. Thermal support already has a compatible driver

Affected: findings/02, findings/04, prior art, phase 5a and phase ordering.

The DT includes `qcom,tsens-v2`, which [Linux 6.12 tsens.c](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/thermal/qcom/tsens.c) explicitly matches. A separate `tsens-8953.c` filename is not required for binding. [Generic TSENS v2](https://raw.githubusercontent.com/torvalds/linux/master/drivers/thermal/qcom/tsens-v2.c) supports 16 sensors, uses 12-bit temperature fields and deci-Celsius, and its generic operations have no software calibration callback. The guide's “10-bit, 5 °C/LSB” model and proposed guessed calibration are incorrect for this path.

The local TSENS interrupts are level-high, not rising-edge. Start by checking the existing driver's probe, temperatures and cooling behavior. Validate thermal protection before sustained performance testing; idle temperatures alone do not prove calibration or effective throttling.

### 6. Backlight and notification LED drivers exist

Affected: findings/04–05, roadmap, phase 3, PMIC draft comments.

Upstream [drivers/video/backlight/qcom-wled.c](https://raw.githubusercontent.com/torvalds/linux/master/drivers/video/backlight/qcom-wled.c) explicitly matches `qcom,pmi8950-wled`. [drivers/leds/leds-aw2013.c](https://raw.githubusercontent.com/torvalds/linux/master/drivers/leds/leds-aw2013.c) implements AW2013. The reference config enables `CONFIG_BACKLIGHT_QCOM_WLED=y` and `CONFIG_LEDS_AW2013=m`, and the device capture lists a backlight device. Searching only `drivers/leds` missed the backlight driver. Reuse these drivers; a fixed regulator is not a demonstrated substitute for this SPMI WLED controller.

### 7. WLAN configuration and firmware instructions need replacement

Affected: findings/03, phase 4.

`wcn36xx` is its own driver, not ath10k. The captured config uses `CONFIG_WCN36XX`, `CONFIG_QCOM_WCNSS_PIL`, and `CONFIG_QCOM_WCNSS_CTRL`, with the required SMEM/RPMSG infrastructure. `ATH10K_PCI` is not an SMD transport, and `QCOM_Q6V5_WCNSS` is not the reference symbol. [Upstream WCN36XX Kconfig](https://raw.githubusercontent.com/torvalds/linux/master/drivers/net/wireless/ath/wcn36xx/Kconfig).

Firmware paths such as `qcom/wlan/wlanmdt.mdt` and `wlan_caldata` are asserted without driver/loader evidence. Capture actual firmware requests and the loader's mappings; extract the complete subsystem image, including referenced split segments if present, plus the board's NV data. The mounted modem partition must be inspected alongside persist. The supplied directory listing does not establish that `wcnss.mdt` resides in persist. Do not promote the captured locally administered MAC address to a verified factory identifier.

### 8. The audio codec drivers already exist in 6.12

Affected: findings/04 naming note and audio row; phase 5b.

[Linux 6.12 sound/soc/codecs/Makefile](https://github.com/torvalds/linux/blob/v6.12/sound/soc/codecs/Makefile) includes `msm8916-wcd-analog.o`, `msm8916-wcd-digital.o`, and their config symbols. The path is `sound/soc/codecs` in 6.12 too; the claimed move from `drivers/sound` is false. Reuse the codecs and investigate the remaining machine/topology support against the chosen target.

### 9. “No reference charger/fuel-gauge driver” is contradicted by the capture

Affected: findings/01, findings/02, phase 5d.

`device-facts.tar` → `kconfig.txt` contains `CONFIG_CHARGER_QCOM_SMBCHG=y` and `CONFIG_BATTERY_PMI8994_FG=y`. This establishes compiled support, not successful binding or charging. Missing probe messages cannot prove absent drivers. Check `/sys/class/power_supply`, driver links and runtime readings before classifying the failure. Likewise, lack of a success message is insufficient to declare a sensor or Bluetooth device unbound.

## Other corrections and evidence limits

| Location | Finding / correction |
|---|---|
| findings/01 storage; README | The capture is eMMC (`mmcblk0`, boot0/boot1 and RPMB), not UFS. |
| findings/01 keys; findings/04 | The board DT maps GPIO 44 to hall and GPIO 85 to volume-up; power comes from the PMIC power key. |
| findings/01 and phase 5c | AK8975 is a magnetometer, not an accelerometer. The sensor plan omits BMI120 while listing touch as both missing and already present. Distinguish DTS labels from Linux adapter numbers. |
| findings/01 IMU claim | The full journal contains `0-0068/iio:device3` and iio-sensor-proxy errors. This contradicts “does not bind”; the observed problem includes userspace buffer/trigger access. |
| findings/03 Bluetooth | [btqcomsmd.c](https://raw.githubusercontent.com/torvalds/linux/master/drivers/bluetooth/btqcomsmd.c) already supplies an SMD HCI driver and the reference config enables it. Absence of `hci0` in dmesg does not establish nonfunctionality; capture `btmgmt info`, sysfs and pairing results. |
| phase 1 warnings | Do not fake unit addresses such as `i2c@1` for nodes with real MMIO `reg` values. Shared QUP I2C/SPI addresses need correct enablement and binding-aware validation. DSI address/size cells are needed once `panel@0` is added. `dtc -Werror` is not GCC-style warning promotion; use named `-E` checks and target `dtbs_check`. |
| phase 3 verification | Reference connector is `card0-DSI-1`, not `card0-HDMI-A-1`. Discover the connector dynamically. |
| phase 2 verification | `cpuinfo_max_freq` describes hardware capability, not the newly written policy cap. Read back `scaling_max_freq` and observe actual transitions under a suitable governor. Restore the cap afterwards. |
| findings/03 disconnects | AP deauth reason 2 is an observation, not proof that the driver is blameless. “Cosmetic” needs evidence of no functional impact. |
| roadmap Android claims | Binder, DMA-BUF heaps and fscrypt also require kernel support/configuration; they are not all userspace work. Successful postmarketOS graphics does not verify Android HAL integration or an Android boot. |
| logging/README runtime commands | Quote `sysctl -w kernel.printk='7 4 1 7'`; `printk_devkmsg` accepts string modes such as `on`, not `1`. |
| logging/README pstore | `record-size` is the kernel crash-log chunk, not pmsg; `console-size` is the console buffer. Ftrace requires runtime enablement (`/sys/kernel/debug/pstore/record_ftrace`) and records calls rather than function-graph returns. See [ramoops documentation](https://www.kernel.org/doc/Documentation/admin-guide/ramoops.rst). |
| logging/README decoder | Compression configuration alone does not prove mounted pstore files need manual decompression. [pstore inode.c](https://raw.githubusercontent.com/torvalds/linux/master/fs/pstore/inode.c) formats ftrace records for filesystem reads. No real crash record was captured to validate the decoder's claims. |
| logging/README UART | The recommended 3.3 V electrical interface is not substantiated by these captures. Establish test-point voltage/pinout before attaching a transmitter. |
| collectors | `artifacts/collect/collect-device-facts.sh` reads `/proc/asounds/pcm` instead of `/proc/asound/pcm`, explaining the empty PCM section. The logging collector does not collect `/var/lib/systemd/pstore`, so archived records can be missed. |
| README layout | Actual boot-log directory is `logging/logs`, not `porting/logs`. |

The live model/panel wiring, remoteproc firmware boot messages, eight policy frequencies and CPR voltages, thermal trip values, and local 4.19.325 version are supported by captures. Those captures describe one patched postmarketOS kernel, not proof that each subsystem works on android-mainline. Runtime temperature snapshots vary; avoid treating one idle reading as a fixed expected value.

## Required before using the phase plan

1. Pin exact android-common and prior-art commits; record provenance/checksums for downloaded references.
2. Build the complete target tree with its existing PMI8950 include, then run binding validation. Keep DTS compilation, DTB compilation and hardware boot as separate statuses.
3. Replace the clock/thermal/WLED/audio/WLAN tasks above with verified deltas against that target. Review thermal and voltage sequencing before high-frequency tests.
4. Collect driver symlinks, power-supply state, IIO devices, HCI state and firmware request paths to resolve the remaining runtime questions.

Direct access to several android-common and prior-art branch URLs failed during this review. Branch availability, exact current version, generated panel-driver compatibility and those branches' complete build status were not independently revalidated. Linux upstream sources linked above disprove the general driver-absence claims; they do not replace commit-specific validation of the intended Android target.
