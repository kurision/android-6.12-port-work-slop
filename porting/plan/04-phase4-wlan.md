# Phase 4 — WLAN

> **Historical record - undated.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

**Goal:** `wlan0` associates, using firmware pulled off the device's `persist`
partition.

## State

Upstream `msm8953.dtsi:2011-2075` already contains the complete pronto/WCNSS
remoteproc and the `qcom,wcnss` / `qcom,wcnss-wlan` / `qcom,wcnss-bt` subtree —
with the same interrupt numbers, SMEM state indices and SMD channel as the
device's own DT (`findings/03`). Only two things are missing: `status`, and
firmware.

## Step 1 — get the firmware off the device

```sh
# on the device
doas ls -la /run/msm-firmware-loader/mnt/persist/
doas find /run/msm-firmware-loader/mnt/ -name 'wcnss*' -o -name '*caldata*' -o -name '*regulatory*'
```

Copy out everything under `persist/` that looks like `wcnss.mdt`,
`wlan_caldata`, `WCNSS_*`, `regulatory.db*` and place them in the kernel
firmware tree at the paths upstream expects (mirror another msm board, e.g.
`arch/arm64/boot/dts/qcom/msm8996.dtsi` plus its `firmware-name` values):
typically `wcnss.mdt` for the remoteproc and `qcom/wlan/wlanmdt.mdt` +
`qcom/wlan/wlan_caldata` for the wifi node.

If `persist` turns out to be empty, fall back to an Android `vendor`/`system`
image and extract the WLAN subsystem from it.

## Step 2 — DT

* Enable `wcnss` (`status = "okay"`); keep the board file's pinctrl
  (`wcnss_pin_a`) — confirm it is defined in the dtsi, otherwise copy the
  GPIO list from the live DT.
* If the board file deletes `&adsp_fw_mem` / `&wcnss_fw_mem` (see phase 1 step 3),
  restore them for a self-booted DTB.
* MAC/BT-BD: CAF keeps them in the DT (`local-mac-address = 02:00:28:19:f2:32`,
  `local-bd-address = 33:f2:19:28:00:02`). Upstream's wcn36xx path expects the
  MAC from `wlan_caldata`; verify which one your kernel honours and keep the
  factory MAC — this is a user-visible identifier.

## Step 3 — build-time config

Needs `CONFIG_ATH10K`, `CONFIG_ATH10K_PCI` (the SMD transport), and the QMI/
remoteproc bits (`CONFIG_QCOM_SMEM`, `CONFIG_QCOM_Q6V5_MSS`, `CONFIG_QCOM_Q6V5_WCNSS`).

## Verification

```sh
dmesg | grep -iE 'wcnss|wcn36xx|remoteproc.*a204000'
ip link; iw dev wlan0 scan | head
```

Accept when the firmware banner matches `findings/03`
(`WCN v2.0 RadioPhy vIris_TSMC_4.0`, API `1.5.1.2`) and `wlan0` associates.
The `SMD_EVENT (312) not supported` message after deauths is a known cosmetic
upstream gap — not a regression.