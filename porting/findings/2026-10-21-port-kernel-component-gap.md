# 2026-10-21: what the port kernel is still missing (component gap)

Method: the running kernel's own config (`/proc/config.gz` on the phone,
6.12.93-4k-g166d3b5328c6) compared against the CAF donor
(`kernel/oc-test`, `arch/arm64/configs/vendor/msm8953-perf_defconfig`) and
against the donor's driver tree. "Missing" means the donor has it and the
running port kernel does not, i.e. the ROM has to run without it.

The port is not a "same kernel, fewer features" situation for display and
GPU: those are CAF ports that work. Everything below is a *different*
class of gap — a subsystem the ROM's user space expects to talk to and
cannot.

## Summary

| # | Area | Donor / stock | Port kernel | What the user loses | Route |
|---|---|---|---|---|---|
| 1 | **Video codec (Venus) — decode + encode** | `drivers/media/platform/msm/vidc_3x` (33 files, 34 179 lines), `CONFIG_MSM_VIDC_3X_V4L2=y` | **absent** (no `drivers/media/platform/msm` at all) | no hardware video decode/encode: the ROM's `OMX.qcom.*` codecs cannot load, every video app falls back to the CPU decoder. Directly causes the YouTube 360p cap and the corrupted video layer (see `2026-10-21-youtube-video-garbage-and-360p-cap.md`) | port the CAF vidc_3x driver (ROM ABI) — see `porting/plan/venus-vidc-port.md` |
| 2 | **Camera** (CAMSS/VFE/ISP + sensors) | `CONFIG_MSM_CAMERA`, `CONFIG_MSMB_CAMERA`, `CONFIG_MSM_CAMERA_SENSOR`, `CONFIG_VIDEO_QCOM_CAMSS=y` | `CONFIG_VIDEO_QCOM_CAMSS` **not set**, `MSM_CAMERA`/`MSMB_CAMERA` absent, no sensor drivers, no DT nodes | no camera at all; the ROM's vendor camera HAL has nothing to bind to | CAMSS exists upstream (`drivers/media/platform/qcom/camss`) but has no msm8953 data tables; the vendor HAL also needs the CAF `msm_camera` stack + sensor modules |
| 3 | **Modem data path** (IPA v2 + RMNET) | `CONFIG_IPA=y`, `CONFIG_RMNET=y`, `CONFIG_RMNET_IPA`, `CONFIG_RNDIS_IPA` | `CONFIG_RMNET` **not set**, IPA absent | no mobile data (the modem itself and QRTR signalling are up, the *packet path* is not) | upstream `drivers/net/ipa` is v3.1+/msm8998; msm8953 needs an IPA-v2 backport |
| 4 | **Modem IPL / PIL** | `CONFIG_MSM_PIL`, `CONFIG_MSM_PIL_MSS_QDSP6V5` | absent | no modem boot images; the ROM runs the prebuilt firmware today | needed anyway for the **Venus firmware** (the donor loads it through `pil-venus`) |
| 5 | **Inline crypto (ICE / QCEDEV)** | `CONFIG_CRYPTO_DEV_QCOM_ICE`, `CONFIG_CRYPTO_DEV_QCEDEV`, `CONFIG_QTI_CRYPTO_TZ` | absent | file-based encryption falls back to software; no secure camera; also blocks the CAF secure context banks | port or accept the software path |
| 6 | **Secure SMMU (TZ)** | `CONFIG_MSM_TZ_SMMU` | absent | no protected display / secure camera; the CAF "secure context bank" model (which the Venus DT needs) has no equivalent | the port replaced the CAF `apps_iommu` context-bank model with per-device SMMU nodes (as done for `smmu_mdp_unsec`) |
| 7 | **Sensors hub (SSC) / accel / gyro** | `CONFIG_SENSORS_SSC`, `CONFIG_QTI_VIRTUAL_SENSOR` | absent, no `drivers/sensors/` | no rotation, no step counter, no ambient sensors | upstream SSC driver + the ROM's SSC firmware |
| 8 | **Fingerprint (Goodix GF3208)** | `CONFIG_FINGERPRINT_GOODIX_GF3208` | absent, no driver | no unlock by fingerprint | small driver port, no upstream equivalent (matches `BACKLOG-driver-rewrites.md` §7) |
| 9 | **MDSS writeback / virtual display** | `CONFIG_FB_MSM_MDSS_WRITEBACK=y` (donor), fb1 "writeback panel" for virtual displays | **not set** (the code `mdss_wb.c` is in the tree but unbuilt) | no fb1 virtual display → no screen recording / casting path that needs WFD | one config line + the DT for fb1; the plan calls it phase 4 |
| 10 | **DSI command status** | `CONFIG_FB_MSM_MDSS_DSI_CTRL_STATUS=y` | **not set** | no panel command-status readback (diagnostics only) | config only |
| 11 | **MDSS xlog register dump** | `CONFIG_FB_MSM_MDSS_XLOG_DEBUG=y` + the DT's `qcom,regs-dump-mdp` ranges | config **not set** and the DT ranges were **deliberately dropped** | cannot read SSPP/DSPP/DSI registers from userspace | deliberate: the plan says "XLOG off at first" because MDP register access hangs the bus on this port when the MDSS domain is down (`17fa25c0c`, `925a863db`). The port's own `DIAG123` print covers the SSPP/CTL words it needs; extend that instead of re-registering the donor's dump list |
| 12 | **WLAN** | `CONFIG_WCNSS_CORE`, `CONFIG_WCNSS_CORE_PRONTO` | replaced by upstream `CONFIG_WCN36XX=y` | none — Wi-Fi works | done, different implementation (fixed 2026-10-21) |
| 13 | **Bluetooth power / BTFM** | `CONFIG_MSM_BT_POWER`, `CONFIG_BTFM_SLIM_WCN3990` | `drivers/bluetooth/btqcomsmd.c` (upstream) | none | done, different implementation (fixed 2026-10-21) |
| 14 | **Touch** | `CONFIG_TOUCHSCREEN_*` (vendor) | upstream Focaltech `edt_ft5x06` + the port's own DT node | none — touch works | done, different implementation |
| 15 | **KGSL / GPU** | CAF `kgsl` | port's CAF KGSL port | none — 3D/EGL work | done |
| 16 | **Display** | CAF MDSS fbdev | port's CAF MDSS fbdev port | none — panel, HWC, rotator work | done |
| 17 | **Audio** | CAF audio stack | port's CAF audio port (in flight) | audio track creation still fails (-19) in the current runs | in progress |
| 18 | **VPN / netfilter extras** | `NETFILTER_XT_MATCH_*`, `IP6_NF_*`, `TCP_CONG_BBR` | not set | no VPN, no conntrack helpers, no BBR | config only, if wanted |
| 19 | **Filesystems** | `EXT4_ENCRYPTION`, `F2FS_FS_ENCRYPTION`, `FS_ENCRYPTION_INLINE_CRYPT` | plain `EXT4_FS`/`F2FS_FS` | no FBE without an inline-crypto engine (see #5) | follows from #5 |
| 20 | **`MACH_XIAOMI_*`** | donor's Xiaomi machine files | not applicable | none | the port uses its own DT, not the donor's machine files |

## What the port *does* have that the donor does not

Worth recording, because the gap list above is one-sided:

* upstream `WCN36XX` instead of the CAF WCNSS stack
* upstream Focaltech touch instead of the vendor Synaptics stack
* upstream `CONFIG_DRM_MSM=y` (the GKI DRM display path) next to the CAF
  MDSS fbdev path — the panel is on MDSS, DRM is there for the virtual
  display/DRM use cases
* the whole Android 6.12 GKI/ACK base (binderfs, ashmem shim, vendor hooks,
  fs-verity, dm-verity, EROFS, F2FS, overlayfs)

## The video codec gap is the one that matters

It is the only gap in this list that a *user* hits immediately and that
the kernel can fix. Everything else is either invisible (a different
implementation of the same job) or blocked behind a vendor HAL that is
itself missing (camera).

The ROM's media stack is the CAF one: `/vendor/lib64/libOmxVdec.so` and
`libOmxVenc.so` open `/dev/video32` and `/dev/video33` and drive
`V4L2_CID_MPEG_VIDC_*` controls, i.e. they speak the **CAF `msm_v4l2`
ABI**. The upstream Venus driver in this tree
(`drivers/media/platform/qcom/venus`, compatibles `qcom,msm8916-venus`,
`qcom,msm8996-venus`, `qcom,msm8998-venus`) speaks the *standard* V4L2
stateless API, and the ROM has **no `c2.android.v4l2.decoder` /
`c2.android.v4l2.encoder` plugin** (`dumpsys media.player` lists only the
`c2.android.*` software codecs), so an upstream Venus driver would be
invisible to the ROM's apps.

=> To get hardware video into the ROM's apps, the port needs the CAF
`vidc_3x` driver, not the upstream Venus driver. Scope and sequencing:
`porting/plan/venus-vidc-port.md`.
