# Mi A1 port dependency research — 2026-10-05

> **Historical record - 2026-10-05.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

The next useful porting step is to compare the working MSM8953 CPU/voltage stack and generated panel driver with a pinned Android target. WLAN already has a working firmware-loading reference; its board supplies must be carried over too.

## Evidence boundaries

- User reports postmarketOS running Linux 7.0 on **slot B**, reachable as `user@172.16.42.1`. This is the current device context, not independently verified here.
- SSH failed before authentication with `Operation not permitted` under this session's network sandbox. No new device data was collected or runtime settings changed. Credentials are deliberately excluded from this note.
- Existing `artifacts/device-facts.tar`, `artifacts/dmesg-live.txt`, and `logging/logs/20261005-095945/meta.txt` report **6.17.7-msm8953**. All runtime conclusions below refer to that older capture, not the current 7.0 boot.
- Source browsing established repository/branch leads and retrieved upstream WLAN code. Several exact Android and WIP driver-file URLs could not be fetched. A failed fetch is not evidence that a file or driver is absent.

## Target and prior-art comparison points

The Android repository's `android-mainline` page inspected during research pointed at commit `a2a0ccf4c10574fde950e554abffd9bdc9aec676`, authored/committed on 2026-10-02, with merge subject `Merge tag 'v7.2' into android-mainline`. This supplies a reproducible candidate target; individual driver contents at this commit were not audited. Keep the Android-integrated branch distinct from `upstream-master` when recording comparisons. [Android common repository](https://android.googlesource.com/kernel/common/), [candidate commit](https://android.googlesource.com/kernel/common/+/a2a0ccf4c10574fde950e554abffd9bdc9aec676).

The MSM8953 branch listing also exposes `7.1.3/main` and `barni2000/7.1.3/develop` (listed as updated July 19, 2026), plus `barni2000/7.0.9/develop` (June 16, 2026). These are newer comparison candidates than the guide's captured 6.12 board DTS. Their driver implementations and commit hashes still need retrieving before selecting patches. Branch names alone do not establish device support or build success. [Branch listing](https://github.com/msm8953-mainline/linux/branches), [7.1.3/main](https://github.com/msm8953-mainline/linux/tree/7.1.3/main).

## CPU scaling: preserve the coupled stack

Local evidence: `artifacts/tissot-live.dts:58`, `:309`, `:479`, `:1114`, `:2497`, `:3311`, `:3326`; `./kconfig.txt`, `./cpufreq.txt`, and `./dmesg.txt` inside `artifacts/device-facts.tar`.

| Component | Captured implementation | Porting implication |
|---|---|---|
| CPU clocks | `qcom,apcs-cc-msm8953`, `CONFIG_QCOM_CLK_APCS_MSM8953=y` | Inspect this provider and its bindings rather than invent GCC CPUSS gates. |
| CPU groups | First four CPUs use clock index 0; remaining four use index 3 | There are two clock outputs, but the capture exposes one policy covering all eight CPUs. |
| Voltage domain | `qcom,msm8953-cpr4pd`, `CONFIG_QCOM_CPR4PD=y` | Clock, OPP and voltage-domain changes must be reviewed together. |
| CPU frequency driver | `CONFIG_ARM_QCOM_CPUFREQ_NVMEM=y`, `CONFIG_CPUFREQ_DT=y` | Check target compatible matching, speed-bin selection and required-OPP handling. |
| CPU OPP selection | Shared `operating-points-v2-kryo-cpu` table with `opp-supported-hw` | The compatible name does not change the CPU identity: all eight are Cortex-A53. |
| Fuse cells | QFPROM `cpu_speed_bin@125`: byte 0x125, bits 0..2; `fusing_rev@23e`: byte 0x23e, bits 5..7 | Preserve cell interpretation and fuse-dependent voltage computation. |
| APC supply | CPR `apc-supply` resolves to PMIC SID 1 `s5`, under `qcom,pm8950-regulators` | This is a direct SPMI regulator dependency, separate from the RPM regulator block. |
| Bandwidth | CPU OPP peak/average bandwidth; APCS provider also exposes an interconnect and CCI OPPs | Include CCI/interconnect support in the source comparison. |

APCS has register windows at `0xb011050`, `0xb016000`, `0xb111050`, `0xb116000`, `0xb1d0000`, and `0xb1d1050`, named for CPU RCG/CBR, CPU PLLs and CCI PLL/RCG. Assigned rates decode to 748.8 MHz, 748.8 MHz and 299.52 MHz. CPR additionally references APM, APCS memory-ACC and TCSR memory-ACC windows. This is more than a CPU OPP table replacement.

The older boot logs report `speed_bin=2 fusing_revision=3`. Its active policy lists 652.8, 844.8, 1036.8, 1228.8, 1420.8, 1612.8, 1804.8 and 2016 MHz. Logged CPR voltages are respectively 650, 675, 700, 735, 770, 805, 870 and 955 mV. These are observed results for this captured chip and kernel, **not** a universal voltage table to hardcode.

The raw DT also contains 614.4 and 2208 MHz entries with different hardware masks. Their presence does not authorize enabling them on this device. The log's initial 748.8 MHz is not in the selected policy; cpufreq explicitly transitions it to 844.8 MHz. Treat early probe/frequency messages in the context of the final registered policy.

The vendored upstream SoC DTS lacks these CPU clock/OPP connections. Its APCS mailbox occupies `0xb011000 + 0x1000`, while the working capture uses `+ 0x50` with a separate clock provider at `0xb011050`. A port must review register ownership as well as driver selection. This is a local reference delta; the exact Android target may already differ.

## Display: identify the generated driver and retain power wiring

The captured panel node (`artifacts/tissot-live.dts:1983`) uses `mdss,otm1911-fhd` followed by `xiaomi,tissot-panel`, TLMM GPIO 61 active-low reset, WLED backlight, and LAB/IBB `vsp`/`vsn` supplies. Both `CONFIG_DRM_PANEL_MDSS_OTM1911_FHD=m` and `CONFIG_DRM_PANEL_XIAOMI_OTM1911=m` are enabled, so configuration alone cannot identify the selected driver.

The saved module listing (`logging/logs/20261005-095945/sysfs/modules.txt:95`) contains `panel_mdss_otm1911_fhd`, and DRM helper dependencies include it. This supports researching the generated MDSS driver first. The capture lacks a panel device-to-driver symlink, so binding should still be checked on the current system.

The [panel-generation repository](https://github.com/msm8953-mainline/linux-panel-drivers) contains a [Tissot configuration entry](https://github.com/msm8953-mainline/linux-panel-drivers/tree/master/config). Its README documents regenerating drivers from DTBs; the generator submodule shown is `7be56b6`. The Tissot script contents could not be retrieved during this session. Before adapting it, inspect the actual generated driver for compatible strings, DSI mode/flags, command sequence, delays and supply names. A panel DT node alone does not prove the target has a matching driver.

## WLAN: board wiring and actual firmware paths

The vendored SoC DTS already describes Pronto v3 remoteproc, its reserved memory, SMP2P/SMD transport, WCNSS controller, Wi-Fi and Bluetooth children. It leaves WCNSS disabled and Iris board-specific. The vendored Tissot board does not supply the following working overrides.

Resolved from `artifacts/tissot-live.dts:3237` and RPM regulator phandles:

| Node/property | Captured provider |
|---|---|
| WCNSS `vddpx-supply` | PM8953 RPM L5, 1.8 V |
| Iris compatible | `qcom,wcn3680` |
| Iris `vddxo-supply` | PM8953 RPM L7, range 1.8–1.9 V |
| Iris `vddrfa-supply` | PM8953 RPM L19, range 1.2–1.35 V |
| Iris `vddpa-supply` | PM8953 RPM L9, range 3.0–3.3 V |
| Iris `vdddig-supply` | PM8953 RPM L5, 1.8 V |
| Iris reference clock | RPM RF_CLK2 |

Carry over supplies and Iris identity along with status, subject to target bindings. The captured boot also reports a dummy `vddmx` regulator; do not interpret every warning as fatal, or replicate dummy supplies without checking the target driver's power-domain handling.

Upstream remoteproc defaults to `wcnss.mdt`, and its MDT loader handles the associated split-image segments. WCN36xx defaults its NV request to `wlan/prima/WCNSS_qcom_wlan_nv.bin`, with a `firmware-name` override read from its parent node. These are separate firmware roles. [WCNSS remoteproc source](https://raw.githubusercontent.com/torvalds/linux/master/drivers/remoteproc/qcom_wcnss.c), [WCN36xx header](https://raw.githubusercontent.com/torvalds/linux/master/drivers/net/wireless/ath/wcn36xx/wcn36xx.h), [WCN36xx probe](https://raw.githubusercontent.com/torvalds/linux/master/drivers/net/wireless/ath/wcn36xx/main.c).

The [msm-firmware-loader 1.5.0 source](https://gitlab.com/postmarketOS/msm-firmware-loader/-/raw/1.5.0/msm-firmware-loader.sh) mounts firmware partitions read-only, gathers files from partition `image/` directories, links persist's NV file into `wlan/prima/`, and sets the firmware-class search path. Its base directory is `/lib/firmware/msm-firmware-loader`; the local capture uses `/run/msm-firmware-loader`, so this source is a mechanism reference, not proof of the exact installed version. Slot-dependent modem selection must be checked against the current loader and active slot B.

The older capture successfully boots `wcnss.mdt`, reports WCNSS version 1.5/1.2, then reports WLAN firmware/API information. Firmware extraction is therefore not an established blocker for reproducing that setup. Inventory actual files and symlink targets before packaging them for a different userspace.

WCN36xx also accepts a valid `local-mac-address` from its Wi-Fi node. The capture's locally administered address matches its DT and boot log. Do not assume the MAC is exclusively supplied by NV data or copy a captured device address into a reusable board DTS. [WCN36xx probe](https://raw.githubusercontent.com/torvalds/linux/master/drivers/net/wireless/ath/wcn36xx/main.c).

## Next research checks

1. Obtain fresh `uname -a`, `/proc/config.gz`, `/sys/firmware/fdt`, module list and driver links from the user's Linux 7.0 slot-B boot. Record the installed kernel package version and APKBUILD/source commit, plus firmware-loader version. Keep this as a separate capture from 6.17.7.
2. Retrieve exact source commits for the installed 7.0 kernel, a newer WIP comparison branch and the Android candidate. Compare APCS, CPR4PD, cpufreq-nvmem, SPMI S5, CCI/interconnect and their bindings as one dependency set. Failed web fetches currently prevent a reliable commit-level patch list.
3. Resolve the live panel driver symlink and obtain its generated source. Compare it with the Android target and retain the captured LAB/IBB/WLED power topology.
4. Record `/sys/module/firmware_class/parameters/path`, loader script/service, `wcnss.mdt` and split-image symlink targets, NV location and firmware-partition mounts on slot B. Check WLAN/HCI state separately from module presence.
5. Only after identifying the real target deltas, build the complete target DTB and run relevant binding checks. The current standalone DTS harness does not establish kernel or hardware readiness; see [verification findings](06-verification.md).

No flashing, boot-slot changes, voltage/frequency writes, or kernel implementation changes were performed during this research.
