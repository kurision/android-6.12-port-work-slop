# Plan: port the downstream MDSS (fbdev) display driver to 6.12 (tissot)

Written 2026-10-11 after snapshot60 run33. Status: **superseded - the driver is
ported and it works.** See "Status update" below before working from this doc.
The decision recorded here is option 2: port the 4.19 donor display driver, so the
vendor composer (sdm) runs unchanged. This doc covers how display works today on both
kernels, why the port is needed, what has to be ported, every known or likely bug,
and a phased, boot-verified plan.

Conventions follow `AGENTS.md`. **verified** means seen in a named log or command
this session. **unverified** means inferred, and must be proven on a boot before it
is relied on.

---

## Status update (2026-10-19, after run261)

**The port is done; do not re-plan it.** The downstream MDSS fbdev driver was
imported into the tree (`6b76153f7`, run198) and now probes, registers
`fb0` at 1080x1920, finds the real `otm1911` panel with the donor's timing,
and the vendor composer opens the framebuffer and commits frames
(`mdss_fb_open: mdssfb_80000 by android.hardwar`, DSI clocked at 802.6 MHz,
1200 kickoffs). The boot animation renders.

**The lag is not the display.** The frames stall because the **GPU stops
retiring work** in the ported kgsl: the composer's kgsl timeline fence never
signals, the MDSS drops the frame
(`__mdss_fb_wait_for_fence_sub: mdp-fence: sync_fence_wait failed! ret =
ffffff92`), SurfaceFlinger reports `Faking VSYNC due to driver stall`, and
the Android display HAL (which lives inside system_server on this ROM) turns
that into a 5.7-core retry loop. The kgsl's own watchdog fires first:
`possible gpu syncpoint deadlock for context 4`, with
`queue=3123328, submit=3121536, start=3121536, retire=3121536` and 8-10 ms
host-side submit times.

Full evidence and the next step:
[`findings/gpu-retirement-stall-run261-2026-10-19.md`](findings/gpu-retirement-stall-run261-2026-10-19.md).
The remaining milestone is the GPU retirement stall, not this driver.

## 0. Where the project stands (verified)

| Item | State | Evidence |
|---|---|---|
| kgsl driver (Stage 2/3) | probes, `/dev/kgsl-3d0` major 503 on 6.12 | run31/run33 `adb shell ls -l /dev/kgsl-3d0` |
| GPU microcode + EGL (Stage 4, EGL half) | **working**: vendor 2020 Adreno blob initialises, PFP/ME versions read back from the GPU | `run33-logcat.log`: `AdrenoGLES-0: PFP: 0x005ff113, ME: 0x005ff066`, `SurfaceFlinger: renderer : Adreno (TM) 506`, `version : OpenGL ES 3.2 V@0502.0` |
| Android userspace | reaches zygote, adb up on 6.12 | run31-run33 adb sessions |
| **Blocker** | the vendor composer `android.hardware.graphics.composer@2.1-service` crashes, so surfaceflinger aborts with `failed to get hwcomposer service` and `sys.boot_completed` never arrives | `run33-logcat.log` (8 composer tombstones), section 2.3 |

Fixes that got here (all in `snapshot60`, the run numbers are the boots):
- run26/27: `interrupt-names = "kgsl_3d0_irq"` in the tissot `&gpu` override, plus
  the msm-bus vector table; probe completes.
- run27/29: `console=ttynull` (no panel or serial console). Userspace went from
  about 2 s per init line to normal speed. The kgsl probe moved from about 14.8 s back to about 4.5 s.
- run30: guard inputs (`ack-protected-fstab.qcom`, `ack-vendor-file-contexts`)
  staged from the snapshot32 donor. `mount_all` went from 100 s to 590 ms and `/data` mounts.
- run31: `force_debuggable` + the real 3.3 MB `userdebug_plat_sepolicy.cil`.
  The snapshot59 base had neither, so the stock policy loaded and qseecomd looped on exit 255.
- run32: `firmware_class.path=/vendor/firmware` (the 6.12 kernel has no user-helper
  fallback, see `CONFIG_FW_LOADER_USER_HELPER_FALLBACK is not set`).
- run33: diag-only policy rule `(allow kernel vendor_file (file (open read getattr)))`.
  The 6.12 firmware loader reads with kernel creds (`drivers/base/firmware_loader/main.c:976-981`)
  and this ROM labels `/vendor/firmware/*` as `vendor_file`. See section 9 for the production fix.
- The diag init watchdog reboot is now **off by default** (`BOOT_DEADLINE_SECONDS=0`,
  `scripts/initramfs-diag/init.c`). Runs end with `adb reboot`.

---

## 1. Summary of the problem

- The stock 4.19 kernel **does not use DRM for display**. It uses Qualcomm's
  downstream **MDSS fbdev** driver (`drivers/video/fbdev/msm`, `CONFIG_FB_MSM_MDSS=y`).
- The vendor composer (`hwcomposer.qcom.so` + `libsdmcore.so`, "sdm") has two
  backends, fbdev (`HWInfo`/`HWDevice`) and DRM (`HWInfoDRM`/`HWDeviceDRM`). It
  picks one by checking whether **`/sys/devices/virtual/graphics/fb0/mdp/caps`**
  exists.
- On 6.12 that file doesn't exist. Mainline `drm/msm` (MDP5) provides `/dev/dri/card0`
  instead, so sdm takes its DRM backend. That backend expects Qualcomm's SDE DRM
  driver (custom properties and blobs), which mainline MDP5 doesn't have. It
  dereferences NULL in `sdm::HWInfoDRM::GetHWResourceInfo`.
- Option 2 restores the stock contract: port MDSS fbdev to 6.12, drop the mainline
  display path, and sdm runs its fbdev backend exactly as on 4.19.

---

## 2. How display works today

### 2.1 Stock 4.19 (the working reference), verified on the phone 2026-10-11 under `su`

Kernel side:
- `CONFIG_FB=y`, `CONFIG_FB_MSM=y`, `CONFIG_FB_MSM_MDSS=y`,
  `CONFIG_FB_MSM_MDSS_WRITEBACK=y`, `CONFIG_FB_MSM_MDSS_DSI_CTRL_STATUS=y`,
  `CONFIG_FB_MSM_MDSS_XLOG_DEBUG=y`, `CONFIG_MSM_MDSS_PLL=y`
  (`kernel_xiaomi_msm8953/arch/arm64/configs/vendor/msm8953-perf_defconfig`).
  No DRM display driver is built.
- `/dev/dri` **does not exist**.
- `/proc/fb`: `0 mdssfb_80000` (primary DSI panel), `1 mdssfb_a0000`
  (`msm_fb_type` = `writeback panel`, used for virtual displays such as screen recording and casting).
- `/dev/graphics/fb0` is `crw-rw---- root graphics 29,0`.
  `/dev/mdss_rotator` is `crw-rw-r-- system system 242,0`.
  `/dev/ion` is `10,63`. `/dev/kgsl-3d0` is `234,0`.
- `fb0/msm_fb_type` = `mipi dsi video panel`.
- `fb0/msm_fb_panel_info`: `panel_name=otm1911 fhd video mode dsi panel primary_panel=1
  min_fps=60 max_fps=60 dyn_fps_en=0 pu_en=0 dual_dsi=0 is_hdr_enabled=0 …`.
- `fb0/mdp/caps` (this is what sdm parses):
  ```
  mdp_version=5  hw_rev=269484032
  pipe_count:5   (vig x1 [ndx 1], rgb x2 [ndx 8,16], dma x1 [ndx 64], cursor x1 [ndx 1024])
  rot_input_fmts / rot_output_fmts / wb_output_fmts bitmaps
  blending_stages=4  max_cursor_size=128  max_downscale_ratio=4  max_upscale_ratio=20
  max_bandwidth_low=3400000 max_bandwidth_high=3400000 max_pipe_width=2048
  max_mixer_width=2048 max_pipe_bw=2300000 max_mdp_clk=400000000
  clk_fudge_factor=105,100
  features= ubwc decimation non_scalar_rgb rotator_downscale dynamic_bw_limit
  ```
- `fb0/` sysfs attributes: `ad ad_bl_event ad_event bits_per_pixel bl_event blank
  console cursor dev dyn_pu dynamic_bitclk dynamic_fps hist_event idle_notify
  idle_power_collapse idle_state idle_time lineptr_event lineptr_value mdp mdss_fb
  measured_fps mode modes msm_cmd_autorefresh_en msm_disable_panel
  msm_fb_dfps_mode msm_fb_panel_info msm_fb_panel_status msm_fb_persist_mode
  msm_fb_split msm_fb_src_split_info msm_fb_thermal_level msm_fb_type msm_misr_en
  name pan power rotate show_blank_event …` (list truncated at 40).

Userspace side (stock services, all `running`): `vendor.hwcomposer-2-1`,
`vendor.gralloc-2-0`, `surfaceflinger`, `display-color-hal-1-0`,
`vendor.livedisplay-sdm`.

Paths `libsdmcore.so`/`libsdmutils.so` touch. These are the **ABI the port must
provide**, taken from `strings` of the stock vendor blobs:
```
/dev/graphics/fb (+ /dev/fb)               framebuffer nodes, MSMFB_* ioctls
/sys/devices/virtual/graphics/fb0/mdp/caps   backend selector + hw caps
/sys/devices/virtual/graphics/fb0/mdp/bw_mode_bitmap
/sys/devices/virtual/graphics/fb0/msm_fb_type
/sys/devices/virtual/graphics/fb0/connected
/sys/devices/virtual/graphics/fb0/msm_cmd_autorefresh_en
/sys/devices/virtual/graphics/fb  (fbN enumeration)
/dev/mdss_rotator + /sys/devices/virtual/rotator/mdss_rotator/caps
/sys/class/leds/lcd-backlight/{brightness,max_brightness}
/sys/class/backlight/panel0-backlight/{brightness,max_brightness}
/sys/devices/virtual/hdcp/msm_hdcp/min_level_change
/dev/video, /sys/class/video4linux/video   (WFD/v4l2 writeback; optional)
```

Boot flow on stock:
1. LK (`MSM8953_TISSOT2.0_20200810200428`) initialises the panel and leaves it
   lit with the splash in the `cont-splash@90001000` reserved region. It passes
   `mdss_mdp.panel=1:dsi:0:qcom,mdss_dsi_otm1911_fhd_video:1:none:cfg:single_dsi`
   on the cmdline (verified in every run's `Kernel command line:`).
2. `mdss_mdp` and `mdss_dsi` probe and take over the running display (cont-splash
   handoff, with SMMU early-map of the splash buffer, `qcom,iommu-earlymap`).
3. `mdss_fb` registers fb0/fb1. ueventd creates `/dev/graphics/fbN`.
4. The composer opens fb0 and finds `mdp/caps`, so it uses the fbdev backend.
   Commits go through `MSMFB_ATOMIC_COMMIT` with ION dma-buf fds and sync fences.
   Rotation and downscale go through `/dev/mdss_rotator`.
5. surfaceflinger renders client layers on the GPU (kgsl + the Adreno blob) into
   gralloc buffers (ION). The composer hands them to MDSS.

### 2.2 Port 6.12 today, verified

- Mainline **drm/msm MDP5**: `mdp: display-controller@1a01000`
  (`qcom,msm8953-mdp5`), `mdss_dsi0: dsi@1a94000`,
  `mdss_dsi0_phy: phy@1a94400` (`qcom,dsi-phy-14nm-8953`), panel driver
  `drivers/gpu/drm/panel/panel-otm1911.c` (`CONFIG_DRM_PANEL_OTM1911=y`,
  imported in `23f85fef1`), backlight `&pmi8950_wled`
  (`CONFIG_BACKLIGHT_QCOM_WLED=y`), `CONFIG_DRM_FBDEV_EMULATION=y`.
- Kernel log: `msm_mdp 1a01000.display-controller: bound 1a94000.dsi`,
  `[drm] Initialized msm 1.12.0`, `MDP5 version v1.16`, panel status `0x9c`. The
  panel lights and the kernel console works.
- `/dev/dri/card0` and `renderD128` exist. `/sys/class/graphics` has **only
  `fbcon`**: no fb0, so no `mdp/caps`, so sdm goes to its DRM backend.
- Since Stage 1 the GPU is owned by kgsl (`compatible = "qcom,kgsl-3d0"`),
  and drm/msm runs display-only (`priv->gpu == NULL`, `no GPU device was found`).

### 2.3 The crash, verified (run31-run33, `run33-logcat.log`)

```
F DEBUG : >>> /vendor/bin/hw/android.hardware.graphics.composer@2.1-service <<<
F DEBUG : signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0 — null pointer dereference
F DEBUG :  #00 libsdmcore.so (sdm::HWInfoDRM::GetHWResourceInfo(sdm::HWResourceInfo*)+208)
F DEBUG :  #01 libsdmcore.so (sdm::CoreImpl::Init()+376)
F DEBUG :  #02 libsdmcore.so (sdm::CoreInterface::CreateCore(...))
F DEBUG :  #03 hwcomposer.qcom.so (sdm::HWCSession::Init()+452)
F SurfaceFlinger: failed to get hwcomposer service
```
Knock-on crashes in the same runs:
- `vendor.lineage.livedisplay-service.sdm` aborts (`PictureAdjustment backend not ready` / `Failed to initialize SDM backend`).
- `dpmd` aborts (`ProcessState already initialized with a different mmap size`). It is
  unrelated to display and looks like a ROM/binder issue; it is section 7, item U5.

History: the same conclusion is in `f630f7c07` (snapshot47: "the vendor sdm HWC
needs downstream MDSS fbdev"). `9bbfe6f5c` (snapshot58) stubbed the composer and
livedisplay rc files out with `-DANDROID_HEADLESS`. That clears the crash loop,
but surfaceflinger still cannot start without a composer.

### 2.4 Why not the alternatives (brief)

- **drm_hwcomposer on mainline MDP5**: possible, but it has to understand the vendor
  gralloc (`gralloc.msm8953.so`, allocator@2.0, mapper 2.x, no gralloc4 metadata).
  It also loses sdm features (rotator, livedisplay, color HAL). It would be the
  long-term "mainline" path, and is not the parity path.
- **Teaching sdm's DRM backend to accept MDP5**: impossible without the vendor
  source. The backend expects SDE DRM objects and properties.
- **Headless**: no `boot_completed`.

---

## 3. Source to port

Donor: `../kernel_xiaomi_msm8953` (4.19.325). The MDSS driver there **already
runs on 4.19**: it is CAF's msm-4.9 MDSS forward-ported, so the delta to 6.12 is
4.19 → 6.12, not 3.18 → 6.12.

### 3.1 Files tissot needs (from `drivers/video/fbdev/msm/Makefile`), about **90.4k lines** (`wc -l`)

| Group | Objects | Keep? |
|---|---|---|
| MDP core | `mdss_mdp.c mdss_mdp_ctl.c mdss_mdp_pipe.c mdss_mdp_util.c mdss_mdp_overlay.c mdss_mdp_layer.c mdss_mdp_intf_video.c mdss_mdp_intf_cmd.c mdss_mdp_splash_logo.c mdss_mdp_cdm.c mdss_io_util.c mdss_smmu.c mdss_sync.c dsi_status_6g.c` | yes |
| Post-processing | `mdss_mdp_pp.c mdss_mdp_pp_v1_7.c mdss_mdp_pp_v3.c mdss_mdp_pp_common.c mdss_mdp_pp_cache_config.c mdss_mdp_pp_debug.c mdss_mdp_pp_stub.c` | yes (color HAL and livedisplay use PP) |
| Rotator | `mdss_rotator.c` (+ `mdss_rotator_internal.h`) | yes (`/dev/mdss_rotator`, sdm uses it) |
| Writeback / WFD | `mdss_mdp_intf_writeback.c mdss_mdp_wfd.c mdss_wb.c` | phase 4 (fb1 virtual display) |
| DSI | `mdss_dsi.c mdss_dsi_host.c mdss_dsi_cmd.c mdss_dsi_status.c mdss_dsi_panel.c msm_mdss_io_8974.c mdss_dsi_phy.c mdss_dsi_phy_v3.c mdss_dsi_phy_12nm.c mdss_dsi_clk.c` | yes (the PHY variant for 8953 must be confirmed, see section 4.6) |
| FB core | `mdss_fb.c mdss_util.c mdss_panel.c mdss_compat_utils.c` | yes (`compat` is only for 32-bit userspace; keep it, because sdm may have 32-bit clients) |
| Xiaomi/Lineage | `mdss_livedisplay.c` | phase 4 (livedisplay HAL) |
| Debug | `mdss_debug.c mdss_debug_xlog.c mdss_mdp_debug.c` | minimal, XLOG off at first |
| **Exclude** | HDMI (`mdss_hdmi_*`, `mdss_cec_core`, `mdss_hdcp_*`), DP (`mdss_dp*`), MHL (`mhl3/`, `mhl_sii8334`), DBA (`msm_dba/`, `mdss_dba_utils`), `mdss_debug_frc` | no |

Note that `mdss_hdmi_util.o mdss_hdmi_edid.o mdss_cec_core.o mdss_dba_utils.o`
are built unconditionally whenever `!MDP3`. The Makefile has to be trimmed, or
those files shimmed.

### 3.2 DSI PLL / clocks driver
- `drivers/clk/msm/mdss/` (`mdss-pll.c` holds the `qcom,mdss_dsi_pll_8953` compatible;
  the directory has 12nm, 28lpm and 8996 variants), **about 10k lines** in total. Only
  the 8953 path is needed.

### 3.3 Headers
- **UAPI, copy verbatim** (this is the sdm ABI; the same rule as kgsl's `msm_kgsl.h`):
  `include/uapi/linux/msm_mdp.h` (1,474 lines), `include/uapi/linux/msm_mdp_ext.h`
  (853), `include/uapi/linux/mdss_rotator.h` (149). None of them exists in the 6.12 tree.
- Kernel-internal: `include/linux/mdss_io_util.h` (118), `linux/mdss_smmu_ext.h`,
  `linux/msm_mdp.h` (the kernel-side wrapper, if present), `video/msm_hdmi_modes.h`
  (still needed by the panel code even with HDMI excluded).

### 3.4 Device tree (donor sources)
- `arch/arm64/boot/dts/vendor/qcom/msm8953-mdss.dtsi` (`qcom,mdss_mdp` @ `0x01a00000`
  `+0x90000` and vbif, `interrupts = <GIC_SPI 72>`, `vdd-supply = <&gdsc_mdss>`,
  `qcom,msm-bus,name = "mdss_mdp"`, three `qcom,mdss-fb` nodes, `qcom,mdss-dsi`
  with two `qcom,mdss-dsi-ctrl`, `qcom,mdss_wb`, `qcom,mdss_rotator`,
  `smmu_mdp_unsec` (`iommus = <&apps_iommu 0xC00 0>`, `qcom,iommu-earlymap`),
  `smmu_mdp_sec` (`0xC01`, `qcom,iommu-vmid = <0x11>`)).
- `msm8953-mdss-pll.dtsi` (2× `qcom,mdss_dsi_pll_8953`).
- Panel: `mi8953/tissot/panel/dsi-panel-otm1911-fhd-video.dtsi`, node
  `dsi_otm1911_fhd_vid: qcom,mdss_dsi_otm1911_fhd_video`: WLED backlight
  (`bl_ctrl_wled`, levels 1..4095), on/off command tables.
- Tissot display glue: `mi8953/tissot/*` (grep `dsi_otm1911_fhd_vid`).

---

## 4. Porting work items (4.19 → 6.12)

API counts are `grep -c` over the donor MDSS sources and are rough: the counts for
`ion_`/`sync_pt` include unrelated identifiers. Each item lists the 6.12
replacement and how risky it is.

### 4.1 Build glue
- `drivers/video/fbdev/msm/{Kconfig,Makefile}`, sourced from
  `drivers/video/fbdev/Kconfig`. `CONFIG_FB=y`, `CONFIG_FB_MSM=y`,
  `CONFIG_FB_MSM_MDSS=y`, `CONFIG_FB_MSM_MDSS_WRITEBACK` (phase 4),
  `CONFIG_MSM_MDSS_PLL=y`. **Built-in**, the same as kgsl (single `fastboot boot` image).
- **Keep the composite object name `mdss-mdp.o`.** `KBUILD_MODNAME` then becomes
  `mdss_mdp`, which makes the LK-supplied `mdss_mdp.panel=` cmdline parameter bind
  (the `module_param` in the mdss code). Renaming the object silently breaks panel selection.
- In `scripts/tissot-ack.config`, display ownership has to move: set
  `CONFIG_DRM_MSM=n` (kgsl already owns the GPU), and also
  `DRM_PANEL_OTM1911=n` and `DRM_FBDEV_EMULATION=n`. If drm/msm stays in, both
  drivers claim `0x1a00000` and the DSI controller (section 7, B1).
- Add `-Wno-implicit-fallthrough` and similar flags, as in the kgsl Makefile.

### 4.2 Removed kernel APIs (compile-breakers)

| Donor usage | Count | 6.12 replacement | Notes |
|---|---|---|---|
| `set_fs/get_ds/KERNEL_DS` | 37 | gone since 5.10 | kernel-internal callers of ioctl handlers (splash, compat utils, PP). Refactor them to call the inner function with kernel pointers, or use `copy_from_kernel_nofault`. **The largest mechanical item.** |
| `access_ok(VERIFY_*, …)` | 12 | 2-arg `access_ok()` | mechanical |
| `pm_qos_*` (CPU DMA latency) | 23 | `cpu_latency_qos_*` | **The same bug is already live in kgsl**: run33 hits `WARNING kernel/power/qos.c:302 cpu_latency_qos_update_request` ×6 (update before add). Fix both the same way. |
| `clk_set_flags` (`linux/clk/qcom.h`) | 14 | no 6.12 equivalent | shim to a no-op (memory retention flags); kgsl already has this shim in `adreno.h` |
| `msm_bus_scale_*` (`linux/msm-bus.h`, `msm-bus-board.h`) | 39 | reuse **kgsl's `msm-bus-compat.c`** (vendor DT vectors → icc) | move it to a shared place (`drivers/soc/qcom/msm-bus-compat.c` + `include/linux/msm-bus.h`), so kgsl and mdss link one copy |
| `wakeup_source_init` | 1 | `wakeup_source_register` | mechanical |
| `of_get_named_gpio` | 17 | still present in 6.12 (deprecated, verify); prefer `gpiod` | keep at first |
| `linux/bootmem.h` | 2 | `linux/memblock.h` | mechanical |
| `linux/version.h` | 2 | drop | |
| `soc/qcom/event_timer.h` | 3 | none | used for idle/vsync wake timers. Shim with hrtimer, or compile out. |
| `soc/qcom/rpm-smd.h` | 1 | none | rpm vote. Mainline rpmpd/icc covers it. Stub. |
| `linux/msm-sps.h`, `usb/msm_hsusb.h`, `usb/usbpd.h`, `extcon` (relative include) | 1-2 each | n/a | DP/HDMI only. Drop with the excluded objects. |
| `linux/hdcp_qseecom.h`, `msm_ext_display.h` | 4-5 | n/a | HDMI/DP only. Drop, or stub `hdcp_*`. sdm still reads `msm_hdcp/min_level_change`; a missing node should be non-fatal (verify). |
| `media/msm_media_info.h` | 1 | copy (header only, UBWC/venus stride macros) | header-only, safe to vendor |
| `xiaomi-msm8953/mach.h` | 5 | **Xiaomi board-ID helper** | which board/panel variant is running (tissot/mido/vince share code). Write a tiny shim (`of_machine_is_compatible("xiaomi,tissot")`), or hard-code tissot. |
| `linux/display_state.h` | 1 | Lineage helper (`is_display_on()`) | vendor it, or stub it |
| `asm/dma-iommu.h`, `linux/msm_dma_iommu_mapping.h` (`msm_dma_map_sg`) | 1 / 3 | gone | see section 4.4 (SMMU) |
| `stdarg.h` | 1 | `linux/stdarg.h` | mechanical |

### 4.3 fbdev core differences (4.19 → 6.12)
- fbdev still exists in 6.12, but `FBINFO_DEFAULT`/`FBINFO_FLAG_DEFAULT` are gone, and
  `fb_ops` changed (`fb_mmap` defaults, `FB_DEFAULT_IOMEM_OPS`/`__FB_DEFAULT_*`
  helpers, `fb_deferred_io` changes). Rework `mdss_fb.c`'s `fb_ops`.
- `framebuffer_alloc/register_framebuffer` are unchanged. `fb_info->fbops` is const in 6.12.
- **fbcon**: with `CONFIG_FRAMEBUFFER_CONSOLE=y`, fbcon binds to fb0. That matches
  stock, but `mdss_fb` must survive fbcon's early `fb_blank`/`fb_set_par`
  calls before the composer starts. On stock 4.19 it does.
- `sysfs` attributes: `device_attribute` groups, `DEVICE_ATTR` signatures are unchanged, and
  `sysfs_notify` for `vsync_event`/`show_blank_event` still works.
- `ueventd` must create `/dev/graphics/fbN`. The ROM's `ueventd.rc` already maps
  `/dev/graphics/*` (verify the ROM file), because stock runs the same ROM.

### 4.4 SMMU / IOMMU (`mdss_smmu.c`, 163 call sites): **high risk**
- The donor uses downstream ARM-SMMU domain attributes (`DOMAIN_ATTR_ATOMIC`,
  `S1_BYPASS`, `SECURE_VMID`, `EARLY_MAP`, `PAGE_TABLE_FORCE_COHERENT`),
  `arm_iommu_create_mapping`/`asm/dma-iommu.h`, and `msm_dma_map_sg` (lazy
  mapping cache). **All of these were deleted upstream.** kgsl hit the same wall
  (Stage 2 log: "6.12 deleted the entire vendor iommu domain-attr API").
- msm8953's display SMMU is the **apps SMMU, `qcom,msm-iommu-v1` (`qcom_iommu`)
  in 6.12**, not arm-smmu. Context banks are selected by `iommus = <&apps_iommu N>`
  with **context index semantics**, not the downstream SID `0xC00`. Map donor
  `0xC00` (non-secure context bank) to the index the mainline `mdp` node already
  uses: **`<&apps_iommu 0x15>`** (verified, `msm8953.dtsi` `mdp` node).
- Plan:
  1. Use the standard DMA API on the `mdss_mdp` device. `iommus=` gives it a DMA
     domain automatically, and `dma_map_sgtable`/`dma_buf_map_attachment` replace
     `msm_dma_map_sg`.
  2. Drop the secure context bank (`smmu_mdp_sec`, VMID `0x11`): no content protection.
     Every `mdss_smmu_is_secure` path returns false.
  3. **Cont-splash early-map** (`qcom,iommu-earlymap`): LK scans out of
     `0x90001000`. The moment the domain attaches, scanout faults unless that range is
     identity-mapped first. Options: attach with an identity mapping of
     `cont-splash@90001000` (`iommu_map(dom, 0x90001000, 0x90001000, size, …)`), or
     disable cont-splash and let the kernel re-init the panel (simpler and visibly
     blank; see section 7, B4).
  4. ION dma-buf import: the 6.12 dma-buf locking rules apply
     (`dma_buf_map_attachment_unlocked`, `dma_resv` held). The kgsl port's
     `kgsl_sharedmem` dma-buf path is a working example in-tree.

### 4.5 Power: the GDSC (`vdd-supply = <&gdsc_mdss>`): **high risk, same class as kgsl**
- Downstream GDSCs are **regulators**. Mainline GDSCs are **genpd power domains**
  (`power-domains = <&gcc MDSS_GDSC>`), switched on only through runtime PM.
- kgsl shows the failure mode: `supply vdd not found, using dummy regulator` and
  in run33 `regulator 'vdd' disable timed out`. kgsl only works because something
  else (drm/msm today, or bootloader state) keeps the domains up (unverified).
- For MDSS: switch the `vdd` regulator calls to `pm_runtime_get_sync/put` on a
  device with `power-domains`, or write a small genpd-backed "regulator" shim. **The
  same fix should then go into kgsl** (GPU GDSC `GPU_GX_GDSC`/`OXILI_*`).
- With drm/msm removed, nothing else holds `MDSS_GDSC`. If MDSS probes without
  owning it properly, the first register access hangs the SoC: the classic
  unclocked or unpowered register read. It shows up as a silent reset with no
  log, see section 7, B2.

### 4.6 Clocks and the DSI PLL
- MDSS clocks come from **mainline `gcc-msm8953`** (MDSS AHB/AXI/MDP/VSYNC/BYTE/
  PCLK/ESC RCGs and branches). The donor DT uses downstream `clock_gcc` IDs.
  Translate every `clocks = <&clock_gcc clk_…>` to `<&gcc GCC_MDSS_…>`. The
  clock-name strings the driver looks up must match (kgsl had the same
  `core` vs `core_clk` trap in run25/26).
- **The DSI PLL provider disappears with drm/msm.** Today `mdss_dsi0_phy`
  (`qcom,dsi-phy-14nm-8953`, part of drm/msm) registers the byte/pixel PLL
  clocks that `gcc` uses as parents for `BYTE0`/`PCLK0` (`msm8953.dtsi:810-811`,
  `assigned-clock-parents`). Choose between:
  - porting `drivers/clk/msm/mdss/mdss-pll.c` + the 8953 PLL code
    (`qcom,mdss_dsi_pll_8953`; it is already on the common clock framework in 4.19,
    so the port is moderate), **or**
  - extracting only the mainline 14nm DSI PHY/PLL as a standalone clock provider
    (`drivers/gpu/drm/msm/dsi/phy/dsi_phy_14nm.c` without the DRM bits). It is
    smaller and known-good on this exact SoC, but couples to drm/msm sources.
  Which PHY file does the donor DSI path use for 8953 (`mdss_dsi_phy.c` "14nm",
  versus `_v3`/`_12nm`)? Confirm from the donor's `qcom,mdss-dsi-ctrl` /
  `qcom,platform-*` DT before choosing (unverified).

### 4.7 Interrupts
- The `mdss_mdp` top-level IRQ (`GIC_SPI 72`) feeds an MDSS **irq domain** that DSI
  (and HDMI) hang off. The `irq_domain_add_linear` and `irq_find_mapping` APIs still
  exist. Check `irq_domain_ops.map` and `handle_level_irq` usage against 6.12.

### 4.8 Sync / fences
- `mdss_sync.c` already wraps `dma_fence` in 4.19 (24 `dma_fence` refs). The
  `sync_fence`/`sync_pt`/`sw_sync` hits are mostly internal names. Port to
  `sync_file_create`/`sync_file_get_fence`. Retire/release fence semantics must
  match what sdm expects (acquire fences in, release/retire fences out per commit).
- Timeline/fence context allocation: `dma_fence_context_alloc` is unchanged.
- The kgsl port still has `kgsl_sync.c` in SCOPED state (TRACKER churn
  inventory: 3 legacy sites). Do both together, because gralloc buffers carry kgsl
  fences into MDSS commits.

### 4.9 ION
- ION is in-tree (`a33336265`, `CONFIG_ION=y`, `/dev/ion` on 6.12). MDSS mostly
  consumes dma-buf fds (`dma_buf_get`/`attach`/`map`). Check for any
  `ion_client`/`ion_handle` legacy calls (none found by grep) and for ION heap IDs
  in MDSS (secure display heap; drop it).

### 4.10 SCM
- 7 SCM call sites: restoring the MDSS secure config after power collapse
  (`restore_sec_cfg`) and secure-display transitions. Mainline has
  `qcom_scm_restore_sec_cfg()` (qcom_iommu uses it). Drop secure display.

### 4.11 Panel and backlight
- The downstream panel driver is **DT-driven** (`mdss_dsi_panel.c` parses
  `qcom,mdss-dsi-on-command` etc.), so the mainline C driver `panel-otm1911.c` is
  not used. **Panel selection comes from LK**: the cmdline names
  `qcom,mdss_dsi_otm1911_fhd_video`, so the DT node must keep exactly that name.
- Backlight is `bl_ctrl_wled`. On 4.19 the downstream WLED driver exposes
  `/sys/class/leds/lcd-backlight` (LED class), and MDSS calls
  `led_trigger_event(bl_led_trigger, level)`. On 6.12, `qcom-wled` is a **backlight
  class** device (`/sys/class/backlight/…`). sdm reads both
  `leds/lcd-backlight` and `backlight/panel0-backlight` (strings). Options: name the
  mainline WLED backlight `panel0-backlight`, and change `mdss_dsi_panel`'s
  `bl_ctrl_wled` path to call `backlight_device_set_brightness()`. Or add an
  `lcd-backlight` LED trigger shim. The scale differs (4095 vs the WLED max) and must be mapped.
- The ESD check (`CONFIG_FB_MSM_MDSS_DSI_CTRL_STATUS`, `dsi_status_6g.c`) reads the
  panel status (`0x9c` expected; the mainline driver logs `panel status 0x9c`).
  Start with it **off**: a false ESD trigger blanks and re-inits the panel in a
  loop.

### 4.12 Device tree translation (`msm8953-xiaomi-tissot.dts`)
- Disable the mainline `mdss`/`mdp`/`mdss_dsi0`/`mdss_dsi0_phy` nodes, and the panel
  node under the DSI (`compatible = "orisetech,otm1911"`, tissot dts:413-414).
- Add the downstream-format nodes from section 3.4, with phandles translated:
  - clocks → mainline `gcc` IDs (section 4.6); DSI PLL → whichever provider section 4.6 picks
  - `vdd-supply = <&gdsc_mdss>` → `power-domains = <&gcc MDSS_GDSC>` (section 4.5)
  - PMIC regulators: downstream `pm8953_lN` / `pmi8950_*` labels → mainline labels
    (`vdda`/`vddio`/`lab`/`ibb` supplies for the DSI and panel)
  - GPIOs (reset, TE, mode): TLMM numbers are unchanged; labels differ
  - `qcom,msm-bus,*` vectors → kept verbatim for the shared `msm-bus-compat`;
    interconnect path to **`mas_mdp`** (exists in `drivers/interconnect/qcom/msm8953.c:1021`)
  - `iommus` → mainline `apps_iommu` context index (section 4.4)
  - `cont-splash@90001000` is already a reserved-memory node on 6.12 (verified in
    every boot's reserved-mem dump); point `qcom,cont-splash-memory` at it
- **Do not touch the GPU node.** Its kgsl override is boot-proven.

---

## 5. Userspace / ROM side (no ROM changes expected; verify each)

| Item | Expectation |
|---|---|
| `hwcomposer.qcom.so` backend | fbdev, because `fb0/mdp/caps` exists (strings show the exact path) |
| `ueventd` | creates `/dev/graphics/fb0`, `/dev/mdss_rotator` with the stock modes (the same ROM as stock) |
| SELinux labels | the stock ROM already labels `graphics_device`, `/dev/mdss_rotator`, the fb sysfs nodes. Verify there are no new `avc: denied` lines for `composer`/`surfaceflinger` on `fb0`. The diag base's patched policy is a fallback for diag-only rules, exactly like run33's firmware rule. |
| livedisplay HAL | needs MDSS PP + `mdss_livedisplay` sysfs (phase 4). Crashing until then is fine. |
| `display-color-hal-1-0` | uses MDSS PP ioctls (`MSMFB_*PP*`); phase 4 |

---

## 6. Phased plan (one change per boot; record each verdict in the tracker)

Use the existing toolchain: `scripts/build-ack-tissot.sh` (with `ACK_TREE=$PWD`),
`package-diag-boot.py --base-image base-guard-debug-fw.img
--append-cmdline "firmware_class.path=/vendor/firmware"`, `clear-logdump.sh`,
`usb-boot-capture.py`, `pull-run-evidence.sh`. adb now comes up on 6.12, so
`adb logcat -b all -d` is the main userspace channel. The kernel log comes from the
logdump (both ramoops slots + the SD log). **The cmdline is at 507/511 bytes**:
drop the dead `pstore_blk.*` tokens (about 110 B; `pstore_blk` never registers,
because it resolves its partition at 3.8 s and the eMMC only appears at 5 s) before adding anything.

**Phase 0: prep (no boot)**
- New worktree/branch `mdss-port` from `kgsl-port`, once the kgsl WIP is committed.
- Move `msm-bus-compat` to a shared location. Commit.

**Phase 1: vendor + compile-clean (no boot)**
- Copy the subset from section 3.1, the uapi headers verbatim, and the shims from section 4.2.
- Build with `CONFIG_FB_MSM_MDSS=y` while drm/msm is **still on**, and the
  downstream DT nodes are **absent or disabled**, so nothing binds. Exit: links;
  `nm vmlinux | grep mdss_fb_init`; the audit shows the drivers built but unbound.

**Phase 2: own the hardware (boot)**
- DT swap (section 4.12), `CONFIG_DRM_MSM=n`, cont-splash **disabled** at first (the
  kernel re-inits the panel; a blank flash is expected), ESD off, writeback off.
- Exit: `fb0` exists; `fb0/mdp/caps` matches the stock dump in section 2.1
  (diff it line by line); `msm_fb_type = mipi dsi video panel`; the panel is lit with
  fbcon text (temporarily use `--keep-stock-console` for this one boot); no SMMU
  faults; no oops.

**Phase 3: composer (boot)**
- Exit: `vendor.hwcomposer-2-1` stays running, surfaceflinger stays running
  (GPU via kgsl, already proven), the boot animation shows, `sys.boot_completed=1`.
- Watch for: commit ioctl failures (`MSMFB_ATOMIC_COMMIT` errno in logcat `SDM`),
  fence timeouts, SMMU faults on ION buffers, underruns (`mdp … underrun`).

**Phase 4: feature parity (boots, one feature each)**
- cont-splash handoff (early-map), rotator, writeback fb1 (screen record), DFPS
  (off on this panel: `dyn_fps_en=0`), MDSS PP + livedisplay + color HAL,
  backlight scale and brightness slider, ESD check, suspend/resume
  (`FBIOBLANK`, idle power collapse, `restore_sec_cfg`).

**Phase 5: cleanup / production**
- Remove the diag-only policy rules (`tee block_device`, `hal_keymaster device`,
  `kernel vendor_file`) and replace them with production fixes (section 9).
- Close the kgsl follow-ups in section 8.
- Update `porting/FAILING-COMPONENTS.md` rows (GPU 3D, display).

---

## 7. Bug / risk register (expected, with symptom → check → mitigation)

| # | Risk | Symptom | Check | Mitigation |
|---|---|---|---|---|
| B1 | drm/msm and mdss both claim MDSS/DSI | `-EBUSY` on ioremap, or two drivers fighting, display dies | kernel log `request_mem_region` | `CONFIG_DRM_MSM=n` and the mainline nodes disabled |
| B2 | GDSC off at the first register access | **silent reset**, empty logdump (dies before the snapshotter at about 6 s) | the same signature as the early kgsl runs | the genpd/runtime-PM shim (section 4.5); if it still dies, defer the probe past the snapshotter (the deferral trick from the kgsl plan) |
| B3 | missing or wrong clock names/IDs | `Couldn't get clock`, probe `-ENOENT`, or a hang on unclocked registers | grep the probe errors | name map table, the same way as kgsl `_get_clocks` |
| B4 | cont-splash SMMU fault on attach | blank screen or a fault storm at about 5 s, `qcom-iommu … fault` | kernel log | phase 2 without cont-splash; phase 4 with an identity early-map |
| B5 | no DSI PLL provider | `BYTE0`/`PCLK0` parents missing, `clk_set_rate` fails, the panel never lights | `clk_summary` (debugfs) | the PLL port or extraction (section 4.6) |
| B6 | LK panel string mismatch | the panel isn't found and fb0 falls back to a dummy | `mdss_mdp.panel` parse message | keep the node name `qcom,mdss_dsi_otm1911_fhd_video` and the object name `mdss-mdp.o` |
| B7 | `set_fs` refactor mistakes | `-EFAULT` from internal ioctl paths (splash, PP init) | logcat SDM errors, kernel `copy_from_user` failures | unit-test each refactored path on boot |
| B8 | fence semantics differ | composer hangs, `fence timeout`, a frozen boot animation | logcat `SDM`, `sync` warnings | match 4.19 retire/release behaviour; test with `dumpsys SurfaceFlinger` |
| B9 | ION/dma-buf locking | lockdep splats, `dma_resv` WARNs | kernel WARNs | `_unlocked` variants |
| B10 | backlight path | display on but black (backlight 0), or a slider that does nothing | `/sys/class/backlight/*/brightness` | the WLED bridge (section 4.11) |
| B11 | ESD false positive | the panel blinks and re-inits every few seconds | `dsi_status` log | keep ESD off until phase 4 |
| B12 | PP/AD init needs calibration data | color HAL errors, wrong colors | logcat `display-color` | phase 4; non-fatal for boot |
| B13 | 32-bit compat ioctl path | 32-bit apps (camera previews, video) fail to map | `mdss_compat_utils` errors | keep `mdss_compat_utils.c`, test a 32-bit client |
| B14 | underruns at boot (bandwidth) | flicker, `underrun` IRQ storms | kernel log | the shared msm-bus-compat must actually vote (today it no-ops without a `gpu_icc_path`; MDSS needs the `mdp0-mem` icc path or a fixed high vote) |
| B15 | fbcon on fb0 before the composer | garbage or conflicting writes during handoff | visual | the stock behaviour is the same; if it causes trouble, use `fbcon=map:` or disable FRAMEBUFFER_CONSOLE |
| B16 | `xiaomi-msm8953/mach.h` board helpers wrong | wrong panel variant or GPIO set | probe logs | hard-code tissot in the shim |
| B17 | timing: console slowness returns | a 2 s/line userspace crawl | timestamps | keep `console=ttynull` except on visual-check boots (run25-27 lesson) |
| U5 | `dpmd` crash loop (`ProcessState already initialized with a different mmap size`) | 12-21 tombstones per run | logcat | not display; investigate separately (binder/ROM) |

---

## 8. kgsl follow-ups seen in run33 (fix alongside, they are not blockers)

From `run33-sd.log` (3,071,879 B, 0 oopses):
1. `WARNING adreno_a5xx.c:294 a5xx_init` "The highest-bank-bit property is invalid":
   add `qcom,highest-bank-bit` to the tissot GPU node (donor `msm8953-gpu.dtsi` value).
2. `WARNING kernel/power/qos.c:302 cpu_latency_qos_update_request` ×6: kgsl
   updates a pm_qos request that was never added. Fix the pm_qos-class removal shim
   (TRACKER: "pm_qos-class removal").
3. `kgsl kgsl-3d0: GPU BW scaling failure: -22` (`kgsl_pwrctrl.c:241`): the
   msm-bus-compat vote has no icc path. Add `mas_gpu` to the msm8953 icc provider
   and `interconnects`/`gpu_icc_path` (handoff stage 3 item 3).
4. `regulator 'vdd' disable timed out` (`adreno.c:4083`) and `supply vdd not
   found, using dummy regulator`: the GDSC/genpd problem (section 4.5).
5. `dt: Couldn't get clock: gpu_ahb_clk`: the `dt:` child node asks for a clock the
   tissot node doesn't provide. Map it or drop it.
6. `WARNING adreno_ringbuffer.c:396` "GPU preemption is disabled": harmless,
   because a5xx preemption init fails. Clear `ADRENO_PREEMPTION` for a506, or ignore it.
7. `AdrenoUtils: Failed to open /sys/class/kgsl/kgsl-3d0/gpu_model`: a sysfs SELinux
   label (`sysfs` vs `sysfs_kgsl`). The blob falls back to the GSL path, so it is cosmetic.
   It's fixed by the ROM's genfs contexts matching the new sysfs path
   (`/sys/devices/platform/soc@0/1c00000.gpu/kgsl/kgsl-3d0/…`). On 4.19 the path is
   `soc/1c00000.qcom,kgsl-3d0`. The genfscon entries key on that path, which is why
   the label is lost.
8. `kgsl_sync.c` legacy sync sites (TRACKER churn inventory) must be done before
   MDSS phase 3 (section 4.8).

## 9. Diag-only policy rules to retire (production fixes)

| Rule (in `userdebug_plat_sepolicy.cil` of the diag base) | Why it exists | Production fix |
|---|---|---|
| `(allow tee block_device (blk_file (open read write)))` | SSD partition `mmcblk0p4` keeps the default label (`502b359b6`, `bc871cd44`) | correct `by-name` symlink labelling. The genfs/ueventd path differs on 6.12 (`soc@0/7824900.mmc` vs `soc/7824900.sdhci`) |
| `(allow hal_keymaster device (chr_file (open read write ioctl)))` | `/dev/qseecom` keeps the default label | ueventd/file_contexts match for the 6.12 device path |
| `(allow kernel vendor_file (file (open read getattr)))` | 6.12 firmware loader uses kernel creds | either label `/vendor/firmware(/.*)?` `vendor_firmware_file` (ROM/vendor), or keep firmware reads in the caller's context (a kernel patch, reverting to the 4.19 behaviour for this device) |

Common root cause of the first two (and of the kgsl sysfs label in section 8.7): **6.12's
device paths (`soc@0/…`, mainline node names) don't match the 4.19 paths that the
ROM's `file_contexts`/`genfs_contexts` were written for.** One systematic fix (a
diag overlay of contexts for the 6.12 paths, like the existing `ack-vendor-file-contexts`
guard) would close all three.

---

## 10. Open questions (resolve before or while porting)

1. Which donor DSI PHY file drives 8953 (`mdss_dsi_phy.c` vs `_v3` vs `_12nm`)?
   Read the donor `qcom,mdss-dsi-ctrl` compat/phy properties.
2. ~~Which mainline `apps_iommu` context index does the MDP use?~~ **Resolved:**
   `iommus = <&apps_iommu 0x15>` (msm8953.dtsi `mdp` node). The donor's `0xC00` SID
   becomes `0x15` on 6.12.
3. ~~Does the mainline icc provider expose an MDP master?~~ **Resolved: yes**,
   `mas_mdp` (`drivers/interconnect/qcom/msm8953.c:1017-1022`). The mainline `mdp` node
   doesn't use `interconnects` today; MDSS can vote through it.
4. Does sdm treat a missing `msm_hdcp/min_level_change` as non-fatal? (It should;
   verify on the first phase 3 boot.)
5. Is there a 32-bit client of the MDSS ioctls on this ROM? (If not, `compat` can wait.)
6. ~~Exact GDSC for MDSS on mainline?~~ **Resolved:** `MDSS_GDSC` (= 2,
   `include/dt-bindings/clock/qcom,gcc-msm8953.h:229`). The mainline `mdss` and `mdp`
   nodes already carry `power-domains = <&gcc MDSS_GDSC>`. The GPU equivalents are
   `OXILI_CX_GDSC` (3) and `OXILI_GX_GDSC` (4), relevant to kgsl's `vdd` problem.
7. Keep fbcon on fb0 (stock parity), or turn it off to avoid handoff noise?

## 11. Evidence index

- `porting/artifacts/snapshot60/run31-logcat-all*.log`, `run32-logcat.log`,
  `run33-logcat.log`, `run33-logcat-final.log`: userspace on 6.12
- `porting/artifacts/snapshot60/run33-sd.log` / `run33-logdump.bin`: full
  6.12 kernel log during GPU use
- `porting/artifacts/snapshot60/run31-live-state.txt`: kgsl sysfs + DRM nodes on 6.12
- Stock 4.19 display state: the commands and outputs in section 2.1 (captured under `su`
  2026-10-11; rerun with `adb shell su -c 'cat /sys/devices/virtual/graphics/fb0/mdp/caps'`)
- Images: `snapshot60/boot-run33.img` (current best: kgsl + EGL working),
  base `snapshot60/base-guard-debug-fw.img` (gitignored, so the only copy; rebuild with
  `scripts/stage-guard-inputs.py --base-image snapshot59/base.img --donor <snapshot32 from git 371c57d2c> --with-debuggable --cil snapshot60/userdebug-run33.cil`)
