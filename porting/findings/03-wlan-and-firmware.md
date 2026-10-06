# 03 — WLAN, firmware and partitions

## WiFi works today, on the mainline-style stack

From `artifacts/dmesg-live.txt`:

| Event | Value |
|---|---|
| remoteproc | `a204000.remoteproc`, boots `wcnss.mdt` (7,324 bytes) — lines 515-517 |
| CNSS version | `WCNSS Version 1.5 1.2` — line 544 |
| Firmware banner | `WCN v2.0 RadioPhy vIris_TSMC_4.0 with 48MHz XO` — line 564 |
| Firmware API | `1.5.1.2, 41 stations, 2 bssids` — line 565 |
| CRM | `CNSS-PR-4-0-3-169-212583-1` — line 564 |
| Driver | `wcn36xx` (ath10k-based), associates and stays associated — lines 602-664 |

So WLAN needs no Qualcomm downstream code; the blocker is firmware and DT
enablement only.

## DT nodes (live `artifacts/tissot-live.dts:3239-3294`)

```
remoteproc@a204000  (wcnss PIL; "iris" clock node = qcom,wcn3680)
└── smd-edge  irq 142, mboxes <apcs 17>, qcom,smd-edge = <6>, remote-pid 4, label "pronto"
    └── wcnss  compatible = "qcom,wcnss", qcom,smd-channels = "WCNSS_CTRL",
                 qcom,mmio = <&wcnss@6>            (reg 6, irq 144)
        ├── bluetooth  qcom,wcnss-bt, local-bd-address = 33:f2:19:28:00:02
        └── wifi       qcom,wcnss-wlan, local-mac-address = 02:00:28:19:f2:32,
                       irq tx 145 / rx 146, smem-states apps_smsm 10 / 9
                       ("tx-enable", "tx-rings-empty")
```

Also relevant: `smp2p-wcnss { qcom,smem = <451>, <431>; interrupts = <143 1> }`
(dts:1038-1044) — identical indices to android-mainline's dtsi.

## Firmware is NOT in /lib/firmware

```
/lib/firmware/qcom/: a530_pfp.fw  a530_pm4.fw  a530v3_gpmu.fw2  msm8953/
```

That is all. The WLAN blobs are pulled at runtime by the
`msm-firmware-loader` systemd service ("Load firmware that is located on
dedicated partitions of qcom devices", bootlog line 450), which mounts three
stock partitions read-only (from `/proc/mounts`):

| Partition | Mount point | Contents seen |
|---|---|---|
| `mmcblk0p13` | `/run/msm-firmware-loader/mnt/dsp` | ADSP/CDSP libraries (`libFastRPC_UTF_Forward_skel.so`, `AudioSphereModule.so.1`, …) |
| `mmcblk0p27` | `/run/msm-firmware-loader/mnt/persist` | root-only; expected to hold `wcnss.mdt` + `wlan_caldata` |
| `mmcblk0p2` | `/run/msm-firmware-loader/mnt/modem_b` | vfat, modem firmware |

Available partlabels: `DDR aboot abootbak apdp boot_a boot_b cmnlib cmnlib64
config devcfg devinfo dip dpo dsp fsc fsg keymaster keystore limits lksecapp logdump
mcfg mdtp misc modem_a modem_b modemst1 modemst2 mota msadp persist rpm sbl1 sec
splash ssd syscfg system_a system_b tz tzbak userdata vendor_a vendor_b`.

Note there is **no `wlan` partition** on this device — WiFi calibration lives in
`persist`.

## GPU firmware

`gpu@1c00000` declares `firmware-name = "qcom/msm8953/xiaomi/tissot/a506_zap.mdt"`,
and the DRM path loads `qcom/a530_pm4.fw` / `qcom/a530_pfp.fw` (bootlog 566-567)
from `/lib/firmware/qcom/`. Both are already present.

## Bluetooth

Modules `btqca`, `btqcomsmd`, `wcn36xx`, `wcnss_ctrl` are loaded (bootlog 553-564)
and the Bluetooth stack initialises Core/MGMT/RFCOMM, but **no HCI device ever
appears** — no `hci0` anywhere in the bootlog. BT is not functional on the
reference kernel either, so it provides no working baseline; it would need the
CNSS BT firmware plus a Bluetooth HCI driver over the wcnss SMD channel.

## Noise to ignore

* `wcn36xx: ERROR SMD_EVENT (312) not supported` after every deauth
  (lines 610, 621, 630, 639, 648, 657) — known upstream wcn36xx gap, cosmetic.
* AP deauth `Reason: 2=PREV_AUTH_NOT_VALID` every ~12 minutes — the access
  point, not the driver.
* `IPv6: ipv6_create_tempaddr: regeneration time exceeded` — privacy addresses.