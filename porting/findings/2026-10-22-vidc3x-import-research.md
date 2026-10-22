# 2026-10-22 — CAF `vidc_3x` import research (donor inventory, UAPI collision check, 6.12 API survey, risk list)

Research only. **No kernel source was edited and nothing was built.**

* Donor (CAF 4.19): `/home/kurision/development/kernel/oc-test`, HEAD `687ee893ae5d` ("psi: Fix trigger being fired unexpectedly at initial").
* Target (ACK 6.12): `/home/kurision/development/kernel/ack-kgsl`, HEAD `eebbbf38e` ("porting: plan the vidc_3x video port and the audio playback fixes").
* Board: Xiaomi Mi A1 / tissot, SoC msm8953 / sdm660 (Venus 1.8, "Venus332" firmware).

Method: every numeric value below was produced by running `gcc -E -dM` over the
donor's and the target's `include/uapi/linux/videodev2.h` +
`include/uapi/linux/v4l2-controls.h` and resolving the macro expressions
(`/tmp/opencode/resolve.py`); enum values were obtained by compiling a
generated user-space program that prints each enumerator
(`/tmp/opencode/dumpall2.py`). No value in this report is guessed.

---

## 1. DONOR FILE INVENTORY

### 1.1 `drivers/media/platform/msm/vidc_3x/` (top level: 31 files, 34 212 lines)

Line counts from `wc -l` in the donor tree. (`governors/` adds 5 files / 1 240
lines and `vmem/` adds 6 files / 847 lines; whole directory = 42 files /
36 299 lines.)

| File | Lines | Role |
|---|---:|---|
| `hfi_packetization.c` | 2568 | Builds the HFI command packets (session create/ETB/FTB/flush/property) sent to the Venus firmware. |
| `hfi_packetization.h` | 103 | Packet-builder prototypes + `hfi_get_pkt_ops_handle()`. |
| `hfi_response_handler.c` | 2106 | Parses HFI messages/session-property responses coming back from the firmware. |
| `Kconfig` | 14 | `menuconfig MSM_VIDC_3X_V4L2` (depends on `ARCH_QCOM && VIDEO_V4L2`, selects `VIDEOBUF2_CORE`). Sources `governors/Kconfig`. |
| `Makefile` | 19 | Builds the 14 objects of the driver, plus `governors/` and (optional) `vmem/`. |
| `msm_smem.c` | 652 | Shared-memory manager: ION alloc, dmabuf attach/map, IOMMU iova mapping, cache ops. |
| `msm_v4l2_vidc.c` | 836 | V4L2 file operations, ioctl tables, `video_device` registration, platform probe of the vidc/context-bank/bus child devices. |
| `msm_vdec.c` | 2813 | Decoder instance: control tables, buffer layout negotiation, `vb2_ops` for the capture queue. |
| `msm_vdec.h` | 38 | Decoder-side prototypes (`msm_vdec_get_vb2q_ops()` etc.). |
| `msm_venc.c` | 4700 | Encoder instance: control tables, bitrate/QP handling, `vb2_ops` for the output queue. |
| `msm_venc.h` | 38 | Encoder-side prototypes (`msm_venc_get_vb2q_ops()` etc.). |
| `msm_vidc.c` | 1498 | Core V4L2 glue: `querycap/enum_fmt/s_fmt/g_fmt`, `vb2` queue setup, poll, event queue, ctrl init entry points. |
| `msm_vidc_common.c` | 5453 | Shared instance logic: control cluster init, buffer registration, `V4L2` buffer flag handling, session state machine. |
| `msm_vidc_common.h` | 109 | Common helpers + `IS_PRIV_CTRL()` macro. |
| `msm_vidc_dcvs.c` | 704 | DCVS (dynamic clock/voltage scaling) — computes the target clock for a session. |
| `msm_vidc_dcvs.h` | 42 | DCVS prototypes. |
| `msm_vidc_debug.c` | 543 | debugfs: `core_info`, `trigger_ssr`, per-instance dumps. |
| `msm_vidc_debug.h` | 178 | `dprintk` levels, debugfs prototypes. |
| `msm_vidc_internal.h` | 422 | Internal structs: `msm_vidc_inst`, `msm_vidc_core`, `buffer_info`, `msm_vidc_list`. |
| `msm_vidc_resources.h` | 223 | `struct msm_vidc_platform_resources` + `is_iommu_present()`. |
| `msm_vidc_res_parse.c` | 1743 | DT parsing: reg-presets, qdss-presets, clock tables, DCVS tables, bus tables, context banks. |
| `msm_vidc_res_parse.h` | 35 | DT-parsing prototypes. |
| `venus_boot.c` | 471 | Non-secure PIL path: GDSC enable, clocks, wrapper/VBIF programming, ARM9 reset, subsys notifier. |
| `venus_boot.h` | 23 | `venus_boot_init()` / `venus_boot_deinit()`. |
| `venus_hfi.c` | 4671 | The HFI client itself: command queues, session management, power on/off, SCM calls, PM QoS. |
| `venus_hfi.h` | 270 | Venus HFI device structures and prototypes. |
| `vidc_hfi.c` | 73 | HFI dispatcher: `vidc_hfi_initialize()` / `vidc_hfi_deinitialize()`. |
| `vidc_hfi.h` | 935 | HFI abstraction: `struct hfi_device`, `hfi_ops`, HAL↔HFI mapping. |
| `vidc_hfi_api.h` | 1551 | The HFI wire protocol: `struct hfi_cmd_*`, `hfi_msg_*`, HAL enums. |
| `vidc_hfi_helper.h` | 1185 | Inline helpers shared by the HFI files. |
| `vidc_hfi_io.h` | 196 | Venus register offsets (wrapper, VBIF, HFI). |

### 1.2 `drivers/media/platform/msm/vidc_3x/governors/`

| File | Lines | Role |
|---|---:|---|
| `fixedpoint.h` | 74 | Fixed-point arithmetic helpers (`fp_t`, `fp_frac()`, `fp_round()`). |
| `Kconfig` | 7 | `menuconfig MSM_VIDC_3X_GOVERNORS` (depends on `MSM_VIDC_3X_V4L2 && PM_DEVFREQ`). |
| `Makefile` | 6 | Builds `msm_vidc_dyn_gov.o` and `msm_vidc_table_gov.o`; adds `-I$(srctree)/drivers/devfreq/`. |
| `msm_vidc_dyn_gov.c` | 1036 | devfreq "dynamic" governor: LUT-based compression ratio → target clock. |
| `msm_vidc_table_gov.c` | 118 | devfreq "table" governor: reads `qcom,load-busfreq-tbl` from the DT. |

### 1.3 `drivers/media/platform/msm/vidc_3x/vmem/`

| File | Lines | Role |
|---|---:|---|
| `Kconfig` | 4 | `menuconfig MSM_VIDC_VMEM` (depends on `ARCH_MSM && MSM_VIDC_V4L2`). |
| `Makefile` | 3 | Builds `vmem.o` + `vmem_debugfs.o`. |
| `vmem.c` | 699 | Shared "vmem" heap (iommu-mapped, bus-voted) used for internal buffers. |
| `vmem.h` | 36 | vmem prototypes. |
| `vmem_debugfs.c` | 83 | debugfs for vmem. |
| `vmem_debugfs.h` | 23 | debugfs prototypes. |

### 1.4 Donor DTS

Full path: `/home/kurision/development/kernel/oc-test/arch/arm64/boot/dts/vendor/qcom/msm8953-vidc.dtsi`
(209 lines; the sibling `sdm660-vidc.dtsi` also exists in the same directory.)

```dts
/* Copyright (c) 2015-2019, The Linux Foundation. All rights reserved.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 and
 * only version 2 as published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */
 
&soc {
	qcom,vidc@1d00000 {
		compatible = "qcom,msm-vidc";
		reg = <0x01d00000 0xff000>,
			<0x000a4124 0x4>,
			<0x000a0164 0x4>;
		reg-names = "vidc", "efuse", "efuse2";
		qcom,platform-version = <0x00180000 0x13>;
		qcom,capability-version = <0x00002000 0x0d>;
		interrupts = <GIC_SPI 44 IRQ_TYPE_LEVEL_HIGH>;
		/* Regulators */
		venus-supply = <&gdsc_venus>;
		venus-core0-supply = <&gdsc_venus_core0>;
		/* Clocks */
		clocks = <&clock_gcc clk_gcc_venus0_vcodec0_clk>,
			<&clock_gcc clk_gcc_venus0_core0_vcodec0_clk>,
			<&clock_gcc clk_gcc_venus0_ahb_clk>,
			<&clock_gcc clk_gcc_venus0_axi_clk>;
		clock-names = "core_clk", "core0_clk", "iface_clk", "bus_clk";
		qcom,clock-configs = <0x1 0x0 0x0 0x0 0x0>;
		qcom,hfi = "venus";
		qcom,hfi-version = "3xx";
		qcom,reg-presets = <0xe0020 0x05555556>,
			<0xe0024 0x05555556>,
			<0x80124 0x00000003>;
		qcom,qdss-presets = <0x825000 0x1000>,
			<0x826000 0x1000>,
			<0x821000 0x1000>,
			<0x802000 0x1000>,
			<0x9180000 0x1000>,
			<0x9181000 0x1000>;
		qcom,max-hw-load = <1044480>; /* 4096 x 2176 @ 30 fps */
		qcom,slave-side-cp;
		qcom,sw-power-collapse;
		qcom,firmware-name = "venus";
		qcom,pm-qos-latency-us = <213>;
		qcom,dcvs-tbl =
			/* Dec UHD@30 H.264, HEVC, VP8, VP9 - NOM to NOM+*/
			<816000 816000 979200 0x3f00000c>,

			/* Enc 3840x1920@30 H.264/HEVC Turbo to Nom+ */
			<855000 821100 979200 0x4000004>,

			/* Enc True4K@24 H.264/HEVC Nom to Nom+ */
			<816000 720000 835584 0x4000004>;
		qcom,dcvs-limit =
			<28800 24>, /* Encoder 3840x1920 */
			<32400 24>; /* Decoder UHD */
		qcom,allowed-clock-rates = <465000000 400000000
			360000000 310000000 228570000 114290000>;
		qcom,clock-freq-tbl {
			qcom,profile-enc {
				qcom,codec-mask = <0x55555555>;
				qcom,cycles-per-mb = <863>;
				qcom,low-power-mode-factor = <35616>;
			};
			qcom,profile-dec {
				qcom,codec-mask = <0xf3ffffff>;
				qcom,cycles-per-mb = <355>;
			};
			qcom,profile-hevcdec {
				qcom,codec-mask = <0x0c000000>;
				qcom,cycles-per-mb = <400>;
			};
		};
	};

	/* MMUs */
	non_secure_cb {
		compatible = "qcom,msm-vidc,context-bank";
		label = "venus_ns";
		iommus = <&apps_iommu 0x800 0x01>,
			<&apps_iommu 0x807 0x00>,
			<&apps_iommu 0x808 0x07>,
			<&apps_iommu 0x810 0x01>,
			<&apps_iommu 0x828 0x01>,
			<&apps_iommu 0x82c 0x01>,
			<&apps_iommu 0x821 0x10>;
		qcom,iommu-dma-addr-pool =<0x79000000 0x50000000
                                0xa1000000 0xc9000000>;
		qcom,iommu-faults = "non-fatal";
		buffer-types = <0xfff>;
		virtual-addr-pool = <0x79000000 0x50000000
			0xa1000000 0xc9000000>;
	};

	secure_bitstream_cb {
		compatible = "qcom,msm-vidc,context-bank";
		label = "venus_sec_bitstream";
			 iommus = <&apps_iommu 0x900 0x0>,
				<&apps_iommu 0x902 0x8>,
				<&apps_iommu 0x909 0x2>,
				<&apps_iommu 0x90e 0x0>,
				<&apps_iommu 0x926 0x0>,
				<&apps_iommu 0x929 0x2>;
		qcom,iommu-dma-addr-pool = <0x51000000 0x28000000>;
		qcom,iommu-faults = "non-fatal";
		buffer-types = <0x241>;
		virtual-addr-pool = <0x51000000 0x28000000>;
		qcom,secure-context-bank;
		qcom,iommu-vmid = <0x9>; /*VMID_CP_BITSTREAM*/
	};

	secure_pixel_cb {
		compatible = "qcom,msm-vidc,context-bank";
		label = "venus_sec_pixel";
		iommus = <&apps_iommu 0x904 0x8>,
			<&apps_iommu 0x910 0x0>,
			<&apps_iommu 0x92c 0x0>;
		qcom,iommu-dma-addr-pool = <0x29000000 0x28000000>;
		qcom,iommu-faults = "non-fatal";
		buffer-types = <0x106>;
		virtual-addr-pool = <0x29000000 0x28000000>;
		qcom,secure-context-bank;
		qcom,iommu-vmid = <0xA>; /*VMID_CP_PIXEL*/
	};

	secure_non_pixel_cb {
		compatible = "qcom,msm-vidc,context-bank";
		label = "venus_sec_non_pixel";
		iommus = <&apps_iommu 0x908 0x0>,
			<&apps_iommu 0x905 0xa>,
			<&apps_iommu 0x925 0x8>,
			<&apps_iommu 0x928 0x0>;
		qcom,iommu-dma-addr-pool = <0x1000000 0x28000000>;
		qcom,iommu-faults = "non-fatal";
		buffer-types = <0x480>;
		virtual-addr-pool = <0x1000000 0x28000000>;
		qcom,secure-context-bank;
		qcom,iommu-vmid = <0xB>; /*VMID_CP_NON_PIXEL*/
	};

	/* Buses */
	venus_bus_ddr {
		compatible = "qcom,msm-vidc,bus";
		label = "venus-ddr";
		qcom,bus-master = <MSM_BUS_MASTER_VIDEO_P0>;
		qcom,bus-slave = <MSM_BUS_SLAVE_EBI_CH0>;
		qcom,mode = "venus-ddr";
		qcom,bus-range-kbps = <1000 2365000>;
	};

	arm9_bus_ddr {
		compatible = "qcom,msm-vidc,bus";
		label = "venus-arm9-ddr";
		qcom,bus-master = <MSM_BUS_MASTER_VIDEO_P0>;
		qcom,bus-slave = <MSM_BUS_SLAVE_EBI_CH0>;
		qcom,mode = "performance";
		qcom,bus-range-kbps = <1 1>;
	};
};
```

Note the DT shape the donor driver expects:
* one `qcom,msm-vidc` node with **four** context-bank children
  (`compatible = "qcom,msm-vidc,context-bank"`) and **two** bus children
  (`compatible = "qcom,msm-vidc,bus"`), all probed through
  `of_platform_populate()` (donor `msm_v4l2_vidc.c:642`);
* **four** separate `iommus` context banks (non-secure + 3 secure), each its own
  child platform device with its own `iommu_domain`;
* the GDSC is described with `venus-supply` / `venus-core0-supply` **regulator**
  phandles, not `power-domains`.

---

## 2. UAPI HEADERS

### 2.1 Paths and sizes

| Header | Donor path | Lines |
|---|---|---:|
| `msm_vidc.h` | `/home/kurision/development/kernel/oc-test/include/uapi/media/msm_vidc.h` | 448 |
| `msm_media_info.h` | `/home/kurision/development/kernel/oc-test/include/uapi/media/msm_media_info.h` | 1411 |
| `msm_vidc_private.h` | `/home/kurision/development/kernel/oc-test/include/uapi/media/msm_vidc_private.h` | 123 |
| `msm_vidc_utils.h` | `/home/kurision/development/kernel/oc-test/include/uapi/media/msm_vidc_utils.h` | 375 |

**None of these four exist in the target tree.** The ACK tree has **no
`include/uapi/media/` directory at all** (`ls include/uapi/` → `asm-generic drm
Kbuild linux misc mtd rdma regulator scsi sound video xen`). `include/uapi/media`
must be created and the four headers installed, and the ROM's OMX/Codec2 plugins
expect them.

### 2.2 `msm_vidc.h` — name=value table

`D` = `#define`, `E` = enum member. Values are the compiled numeric values.

```
D 6     __MSM_VIDC_H__                                        = (guard)
D 10    MSM_VIDC_HAL_INTERLACE_COLOR_FORMAT_NV12             = 0x2
D 11    MSM_VIDC_HAL_INTERLACE_COLOR_FORMAT_NV12_UBWC        = 0x8002
D 12    MSM_VIDC_4x_1                                        = 0x1
D 13    MSM_VIDC_EXTRADATA_FRAME_QP_ADV                      = 0x1
D 27    V4L2_CID_MPEG_VIDC_VIDEO_IDR_PERIOD                  = 0x00992005   (V4L2_CID_MPEG_MSM_VIDC_BASE+5)
D 29    V4L2_CID_MPEG_VIDC_VIDEO_STREAM_OUTPUT_MODE          = 0x00992016   (V4L2_CID_MPEG_MSM_VIDC_BASE+22)
E 30    V4L2_CID_MPEG_VIDC_VIDEO_STREAM_OUTPUT_PRIMARY       = 0
E 30    V4L2_CID_MPEG_VIDC_VIDEO_STREAM_OUTPUT_SECONDARY     = 1
E 265   MSM_VIDC_EXTRADATA_NONE                              = 0x00000000
E 265   MSM_VIDC_EXTRADATA_MB_QUANTIZATION                   = 0x00000001
E 265   MSM_VIDC_EXTRADATA_INTERLACE_VIDEO                   = 0x00000002
E 265   MSM_VIDC_EXTRADATA_VC1_FRAMEDISP                     = 0x00000003
E 265   MSM_VIDC_EXTRADATA_VC1_SEQDISP                       = 0x00000004
E 265   MSM_VIDC_EXTRADATA_TIMESTAMP                         = 0x00000005
E 265   MSM_VIDC_EXTRADATA_S3D_FRAME_PACKING                 = 0x00000006
E 265   MSM_VIDC_EXTRADATA_FRAME_RATE                        = 0x00000007
E 265   MSM_VIDC_EXTRADATA_PANSCAN_WINDOW                    = 0x00000008
E 265   MSM_VIDC_EXTRADATA_RECOVERY_POINT_SEI                = 0x00000009
E 265   MSM_VIDC_EXTRADATA_MPEG2_SEQDISP                     = 0x0000000D
E 265   MSM_VIDC_EXTRADATA_STREAM_USERDATA                   = 0x0000000E
E 265   MSM_VIDC_EXTRADATA_FRAME_QP                          = 0x0000000F
E 265   MSM_VIDC_EXTRADATA_FRAME_BITS_INFO                   = 0x00000010
E 265   MSM_VIDC_EXTRADATA_VQZIP_SEI                         = 0x00000011
E 265   MSM_VIDC_EXTRADATA_ROI_QP                            = 0x00000013
E 265   MSM_VIDC_EXTRADATA_VPX_COLORSPACE_INFO               = 0x00000014
E 265   MSM_VIDC_EXTRADATA_MASTERING_DISPLAY_COLOUR_SEI      = 0x00000015
E 265   MSM_VIDC_EXTRADATA_CONTENT_LIGHT_LEVEL_SEI           = 0x00000016
E 265   MSM_VIDC_EXTRADATA_PQ_INFO                           = 0x00000017
E 265   MSM_VIDC_EXTRADATA_COLOUR_REMAPPING_INFO_SEI         = 0x00000018
E 265   MSM_VIDC_EXTRADATA_UBWC_CR_STAT_INFO                 = 0x00000019
E 265   MSM_VIDC_EXTRADATA_INPUT_CROP                        = 0x0700000E
E 265   MSM_VIDC_EXTRADATA_OUTPUT_CROP                       = 0x0700000F
E 265   MSM_VIDC_EXTRADATA_DIGITAL_ZOOM                      = 0x07000010
E 265   MSM_VIDC_EXTRADATA_MULTISLICE_INFO                   = 0x7F100000
E 265   MSM_VIDC_EXTRADATA_NUM_CONCEALED_MB                  = 0x7F100001
E 265   MSM_VIDC_EXTRADATA_INDEX                             = 0x7F100002
E 265   MSM_VIDC_EXTRADATA_ASPECT_RATIO                      = 0x7F100003
E 265   MSM_VIDC_EXTRADATA_METADATA_LTR                      = 0x7F100004
E 265   MSM_VIDC_EXTRADATA_METADATA_FILLER                   = 0x7FE00002
E 265   MSM_VIDC_EXTRADATA_METADATA_MBI                      = 0x7F100005
E 265   MSM_VIDC_EXTRADATA_VUI_DISPLAY_INFO                  = 0x7F100006
E 265   MSM_VIDC_EXTRADATA_YUVSTATS_INFO                     = 0x7F100007
E 309   MSM_VIDC_INTERLACE_FRAME_PROGRESSIVE                 = 0x01
E 309   MSM_VIDC_INTERLACE_INTERLEAVE_FRAME_TOPFIELDFIRST    = 0x02
E 309   MSM_VIDC_INTERLACE_INTERLEAVE_FRAME_BOTTOMFIELDFIRST = 0x04
E 309   MSM_VIDC_INTERLACE_FRAME_TOPFIELDFIRST               = 0x08
E 309   MSM_VIDC_INTERLACE_FRAME_BOTTOMFIELDFIRST            = 0x10
E 309   MSM_VIDC_INTERLACE_FRAME_MBAFF                       = 0x20
E 327   MSM_VIDC_FRAME_RECONSTRUCTION_INCORRECT              = 0x0
E 327   MSM_VIDC_FRAME_RECONSTRUCTION_CORRECT                = 0x01
E 327   MSM_VIDC_FRAME_RECONSTRUCTION_APPROXIMATELY_CORRECT  = 0x02
E 332   MSM_VIDC_USERDATA_TYPE_FRAME                         = 0x1
E 332   MSM_VIDC_USERDATA_TYPE_TOP_FIELD                     = 0x2
E 332   MSM_VIDC_USERDATA_TYPE_BOTTOM_FIELD                  = 0x3
E 339   MSM_VIDC_RESERVED_1                                  = 0
E 339   MSM_VIDC_BT709_5                                     = 1
E 339   MSM_VIDC_UNSPECIFIED                                 = 2
E 339   MSM_VIDC_RESERVED_2                                  = 3
E 339   MSM_VIDC_BT470_6_M                                   = 4
E 339   MSM_VIDC_BT601_6_625                                 = 5
E 339   MSM_VIDC_BT470_6_BG                                  = 5   (= MSM_VIDC_BT601_6_625)
E 339   MSM_VIDC_BT601_6_525                                 = 6
E 339   MSM_VIDC_SMPTE_240M                                  = 7
E 339   MSM_VIDC_GENERIC_FILM                                = 8
E 339   MSM_VIDC_BT2020                                      = 9
E 353   MSM_VIDC_CS_UNKNOWN                                  = 0
E 353   MSM_VIDC_CS_BT_601                                   = 1
E 353   MSM_VIDC_CS_BT_709                                   = 2
E 353   MSM_VIDC_CS_SMPTE_170                                = 3
E 353   MSM_VIDC_CS_SMPTE_240                                = 4
E 353   MSM_VIDC_CS_BT_2020                                  = 5
E 353   MSM_VIDC_CS_RESERVED                                 = 6
E 353   MSM_VIDC_CS_RGB                                      = 7
E 364   MSM_VIDC_MATRIX_RGB                                  = 0
E 364   MSM_VIDC_MATRIX_BT_709_5                             = 1
E 364   MSM_VIDC_MATRIX_UNSPECIFIED                          = 2
E 364   MSM_VIDC_MATRIX_RESERVED                             = 3
E 364   MSM_VIDC_MATRIX_FCC_47                               = 4
E 364   MSM_VIDC_MATRIX_601_6_625                            = 5
E 364   MSM_VIDC_MATRIX_BT470_BG                             = 5   (= MSM_VIDC_MATRIX_601_6_625)
E 364   MSM_VIDC_MATRIX_601_6_525                            = 6
E 364   MSM_VIDC_MATRIX_SMPTE_170M                           = 6   (= MSM_VIDC_MATRIX_601_6_525)
E 364   MSM_VIDC_MATRIX_SMPTE_240M                           = 7
E 364   MSM_VIDC_MATRIX_Y_CG_CO                              = 8
E 364   MSM_VIDC_MATRIX_BT_2020                              = 9
E 364   MSM_VIDC_MATRIX_BT_2020_CONST                        = 10
E 380   MSM_VIDC_TRANSFER_RESERVED_1                         = 0
E 380   MSM_VIDC_TRANSFER_BT709_5                            = 1
E 380   MSM_VIDC_TRANSFER_UNSPECIFIED                        = 2
E 380   MSM_VIDC_TRANSFER_RESERVED_2                         = 3
E 380   MSM_VIDC_TRANSFER_BT_470_6_M                         = 4
E 380   MSM_VIDC_TRANSFER_BT_470_6_BG                        = 5
E 380   MSM_VIDC_TRANSFER_601_6_625                          = 6
E 380   MSM_VIDC_TRANSFER_601_6_525                          = 6   (= MSM_VIDC_TRANSFER_601_6_625)
E 380   MSM_VIDC_TRANSFER_SMPTE_240M                         = 7
E 380   MSM_VIDC_TRANSFER_LINEAR                             = 8
E 380   MSM_VIDC_TRANSFER_LOG_100_1                          = 9
E 380   MSM_VIDC_TRANSFER_LOG_100_SQRT10_1                   = 10
E 380   MSM_VIDC_TRANSFER_IEC_61966                          = 11
E 380   MSM_VIDC_TRANSFER_BT_1361                            = 12
E 380   MSM_VIDC_TRANSFER_SRGB                               = 13
E 380   MSM_VIDC_TRANSFER_BT_2020_10                         = 14
E 380   MSM_VIDC_TRANSFER_BT_2020_12                         = 15
E 380   MSM_VIDC_TRANSFER_SMPTE_ST2084                       = 16
E 380   MSM_VIDC_TRANSFER_SMPTE_ST428_1                      = 17
E 380   MSM_VIDC_TRANSFER_HLG                                = 18
E 406   MSM_VIDC_BIT_DEPTH_8                                 = 0
E 406   MSM_VIDC_BIT_DEPTH_10                                = 1
E 406   MSM_VIDC_BIT_DEPTH_UNSUPPORTED                       = 0xFFFFFFFF
E 412   MSM_VIDC_COMPONENT                                   = 0
E 412   MSM_VIDC_PAL                                         = 1
E 412   MSM_VIDC_NTSC                                        = 2
E 412   MSM_VIDC_SECAM                                       = 3
E 412   MSM_VIDC_MAC                                         = 4
E 412   MSM_VIDC_UNSPECIFIED_FORMAT                          = 5
E 412   MSM_VIDC_RESERVED_1_FORMAT                           = 6
E 412   MSM_VIDC_RESERVED_2_FORMAT                           = 7
E 423   MSM_VIDC_COLOR_DESC_NOT_PRESENT                      = 0
E 423   MSM_VIDC_COLOR_DESC_PRESENT                          = 1
D 330   MSM_VIDC_FRAMEPACK_CHECKERBOARD                      = 0x00
D 331   MSM_VIDC_FRAMEPACK_COLUMN_INTERLEAVE                 = 0x01
D 332   MSM_VIDC_FRAMEPACK_ROW_INTERLEAVE                    = 0x02
D 333   MSM_VIDC_FRAMEPACK_SIDE_BY_SIDE                      = 0x03
D 334   MSM_VIDC_FRAMEPACK_TOP_BOTTOM                        = 0x04
D 335   MSM_VIDC_FRAMEPACK_TEMPORAL_INTERLEAVE               = 0x05
D 442   MSM_VIDC_PIC_STRUCT_MAYBE_INTERLACED                 = 0x0
D 443   MSM_VIDC_PIC_STRUCT_PROGRESSIVE                      = 0x1
D 444   MSM_VIDC_PIC_STRUCT_UNKNOWN                          = 0xFFFFFFFF
D 446   MSM_VIDC_ALL_LAYER_ID                                = 0xFF
```

`msm_vidc.h` also carries the shared structs (`struct msm_vidc_extradata_header`,
`msm_vidc_interlace_payload`, `msm_vidc_framerate_payload`, `msm_vidc_ts_payload`,
`msm_vidc_concealmb_payload`, …) — these are the ABI the ROM's OMX plugins
exchange with the driver and must be byte-identical.

### 2.3 `msm_media_info.h` — name=value table

```
D 3     __MSM_MEDIA_INFO_H__                    = (guard)
D 8     NV12_STRIDE_ALIGNMENT                  = 128
D 9     NV12_SCANLINE_ALIGNMENT                = 32
D 11    UBWC_EXTRA_SIZE                        = 16384
D 14    INTERLACE_WIDTH_MAX                    = 1920
D 15    INTERLACE_HEIGHT_MAX                   = 1920
D 16    INTERLACE_MB_PER_FRAME_MAX             = ((1920*1088)/256)   -> 8160
D 19    MSM_MEDIA_ALIGN(sz, align)             = (((align) & ((align)-1)) ? (((sz)+((align)-1))/((align)))*((align)) : (((sz)+((align)-1)) & (~((align)-1))))
D 25    MSM_MEDIA_ROUNDUP(sz, r)               = (((sz)+((r)-1))/((r)))
E 26    COLOR_FMT_NV12                         = 0
E 26    COLOR_FMT_NV12_128                     = 1
E 26    COLOR_FMT_NV21                         = 2
E 26    COLOR_FMT_NV12_UBWC                    = 3
E 26    COLOR_FMT_NV12_BPP10_UBWC              = 4
E 26    COLOR_FMT_RGBA8888                     = 5
E 26    COLOR_FMT_RGBA8888_UBWC                = 6
E 26    COLOR_FMT_RGBA1010102_UBWC             = 7
E 26    COLOR_FMT_RGB565_UBWC                  = 8
E 26    COLOR_FMT_P010_UBWC                    = 9
E 26    COLOR_FMT_P010                         = 10
E 26    COLOR_FMT_NV12_512                     = 11
```

The remaining 1400 lines of `msm_media_info.h` are `struct`s (NV12/UBWC
layout descriptors, `msm_vidc_buffer_usage`, …) — pure ABI, no numbers.

### 2.4 `msm_vidc_private.h` — name=value table

```
D 3     __MSM_VIDC_PRIVATE_H__                                = (guard)
D 8     VIDIOC_VIDEO_CMD   = _IOWR('V', BASE_VIDIOC_PRIVATE_VIDEO, struct msm_vidc_arg)
D 12    MSM_VIDC_CMD_START                                       = 0x10000000
D 13    MSM_CVP_START                                            = (MSM_VIDC_CMD_START + 0x1000)  = 0x10001000
D 25    MSM_CVP_GET_SESSION_INFO                                 = (MSM_CVP_START + 1) = 0x10001001
D 32    MSM_CVP_REQUEST_POWER                                    = (MSM_CVP_START + 2) = 0x10001002
D 39    MSM_CVP_REGISTER_BUFFER                                  = (MSM_CVP_START + 3) = 0x10001003
D 46    MSM_CVP_UNREGISTER_BUFFER                                = (MSM_CVP_START + 4) = 0x10001004
D 49    MSM_CVP_FLAG_UNSECURE                                    = 0x00000000
D 50    MSM_CVP_FLAG_SECURE                                      = 0x00000001
D 53    MSM_CVP_BUFTYPE_INPUT                                    = 0x00000001
D 54    MSM_CVP_BUFTYPE_OUTPUT                                   = 0x00000002
D 55    MSM_CVP_BUFTYPE_INTERNAL_1                               = 0x00000003
D 56    MSM_CVP_BUFTYPE_INTERNAL_2                               = 0x00000004
```

`BASE_VIDIOC_PRIVATE_VIDEO` is itself a CAF addition to the donor's
`include/uapi/linux/videodev2.h` and does **not** exist in the 6.12 tree.

### 2.5 `msm_vidc_utils.h` — name=value table

```
D 3     __MSM_VIDC_UTILS_H__                                             = (guard)
D 7     MSM_VIDC_EXTRADATA_NONE                                           = 0x00000000
D 18    MSM_VIDC_INTERLACE_FRAME_PROGRESSIVE                              = 0x01
D 19    MSM_VIDC_INTERLACE_INTERLEAVE_FRAME_TOPFIELDFIRST                 = 0x02
D 20    MSM_VIDC_INTERLACE_INTERLEAVE_FRAME_BOTTOMFIELDFIRST              = 0x04
D 21    MSM_VIDC_INTERLACE_FRAME_TOPFIELDFIRST                            = 0x08
D 22    MSM_VIDC_INTERLACE_FRAME_BOTTOMFIELDFIRST                         = 0x10
D 23    MSM_VIDC_INTERLACE_FRAME_MBAFF                                    = 0x20
D 25    MSM_VIDC_HAL_INTERLACE_COLOR_FORMAT_NV12                          = 0x2
D 26    MSM_VIDC_HAL_INTERLACE_COLOR_FORMAT_NV12_UBWC                     = 0x8002
D 27    MSM_VIDC_EXTRADATA_INTERLACE_VIDEO                                = 0x00000002
D 33    MSM_VIDC_EXTRADATA_FRAME_RATE                                     = 0x00000007
D 38    MSM_VIDC_EXTRADATA_TIMESTAMP                                      = 0x00000005
D 44    MSM_VIDC_EXTRADATA_NUM_CONCEALED_MB                               = 0x7F100001
D 50    MSM_VIDC_FRAME_RECONSTRUCTION_INCORRECT                           = 0x0
D 51    MSM_VIDC_FRAME_RECONSTRUCTION_CORRECT                             = 0x01
D 52    MSM_VIDC_FRAME_RECONSTRUCTION_APPROXIMATELY_CORRECT               = 0x02
D 53    MSM_VIDC_EXTRADATA_RECOVERY_POINT_SEI                             = 0x00000009
D 58    MSM_VIDC_EXTRADATA_ASPECT_RATIO                                   = 0x7F100003
D 74    MSM_VIDC_EXTRADATA_OUTPUT_CROP                                    = 0x0700000F
D 91    MSM_VIDC_EXTRADATA_INDEX                                          = 0x7F100002
D 99    MSM_VIDC_EXTRADATA_PANSCAN_WINDOW                                 = 0x00000008
D 112   MSM_VIDC_USERDATA_TYPE_FRAME                                      = 0x1
D 113   MSM_VIDC_USERDATA_TYPE_TOP_FIELD                                  = 0x2
D 114   MSM_VIDC_USERDATA_TYPE_BOTTOM_FIELD                               = 0x3
D 115   MSM_VIDC_EXTRADATA_STREAM_USERDATA                                = 0x0000000E
D 121   MSM_VIDC_EXTRADATA_FRAME_QP                                       = 0x0000000F
D 130   MSM_VIDC_EXTRADATA_FRAME_BITS_INFO                                = 0x00000010
D 136   MSM_VIDC_EXTRADATA_S3D_FRAME_PACKING                              = 0x00000006
D 166   MSM_VIDC_EXTRADATA_ROI_QP                                         = 0x00000013
D 173   MSM_VIDC_EXTRADATA_MASTERING_DISPLAY_COLOUR_SEI                   = 0x00000015
D 183   MSM_VIDC_EXTRADATA_CONTENT_LIGHT_LEVEL_SEI                        = 0x00000016
D 189   MSM_VIDC_EXTRADATA_HDR10PLUS_METADATA                             = 0x0000001A
D 195   MSM_VIDC_EXTRADATA_CVP_METADATA                                   = 0x0000001B
D 201   MSM_VIDC_COMPONENT                                                = 0
D 202   MSM_VIDC_PAL                                                      = 1
D 203   MSM_VIDC_NTSC                                                     = 2
D 204   MSM_VIDC_SECAM                                                    = 3
D 205   MSM_VIDC_MAC                                                      = 4
D 206   MSM_VIDC_UNSPECIFIED_FORMAT                                       = 5
D 207   MSM_VIDC_RESERVED_1_FORMAT                                        = 6
D 208   MSM_VIDC_RESERVED_2_FORMAT                                        = 7
D 212   MSM_VIDC_RESERVED_1                                               = 0
D 213   MSM_VIDC_BT709_5                                                  = 1
D 214   MSM_VIDC_UNSPECIFIED                                              = 2
D 215   MSM_VIDC_RESERVED_2                                               = 3
D 216   MSM_VIDC_BT470_6_M                                                = 4
D 217   MSM_VIDC_BT601_6_625                                              = 5
D 218   MSM_VIDC_BT470_6_BG                                               = 5   (= MSM_VIDC_BT601_6_625)
D 219   MSM_VIDC_BT601_6_525                                              = 6
D 220   MSM_VIDC_SMPTE_240M                                               = 7
D 221   MSM_VIDC_GENERIC_FILM                                             = 8
D 222   MSM_VIDC_BT2020                                                   = 9
D 225   MSM_VIDC_MATRIX_RGB                                               = 0
D 226   MSM_VIDC_MATRIX_BT_709_5                                          = 1
D 227   MSM_VIDC_MATRIX_UNSPECIFIED                                       = 2
D 228   MSM_VIDC_MATRIX_RESERVED                                          = 3
D 229   MSM_VIDC_MATRIX_FCC_47                                            = 4
D 230   MSM_VIDC_MATRIX_601_6_625                                         = 5
D 231   MSM_VIDC_MATRIX_BT470_BG                                          = 5   (= MSM_VIDC_MATRIX_601_6_625)
D 232   MSM_VIDC_MATRIX_601_6_525                                         = 6
D 233   MSM_VIDC_MATRIX_SMPTE_170M                                        = 6   (= MSM_VIDC_MATRIX_601_6_525)
D 234   MSM_VIDC_MATRIX_SMPTE_240M                                        = 7
D 235   MSM_VIDC_MATRIX_Y_CG_CO                                           = 8
D 236   MSM_VIDC_MATRIX_BT_2020                                           = 9
D 237   MSM_VIDC_MATRIX_BT_2020_CONST                                     = 10
D 240   MSM_VIDC_TRANSFER_RESERVED_1                                      = 0
D 241   MSM_VIDC_TRANSFER_BT709_5                                         = 1
D 242   MSM_VIDC_TRANSFER_UNSPECIFIED                                     = 2
D 243   MSM_VIDC_TRANSFER_RESERVED_2                                      = 3
D 244   MSM_VIDC_TRANSFER_BT_470_6_M                                      = 4
D 245   MSM_VIDC_TRANSFER_BT_470_6_BG                                     = 5
D 246   MSM_VIDC_TRANSFER_601_6_625                                       = 6
D 247   MSM_VIDC_TRANSFER_601_6_525                                       = 6   (= MSM_VIDC_TRANSFER_601_6_625)
D 248   MSM_VIDC_TRANSFER_SMPTE_240M                                      = 7
D 249   MSM_VIDC_TRANSFER_LINEAR                                          = 8
D 250   MSM_VIDC_TRANSFER_LOG_100_1                                       = 9
D 251   MSM_VIDC_TRANSFER_LOG_100_SQRT10_1                                = 10
D 252   MSM_VIDC_TRANSFER_IEC_61966                                       = 11
D 253   MSM_VIDC_TRANSFER_BT_1361                                         = 12
D 254   MSM_VIDC_TRANSFER_SRGB                                            = 13
D 255   MSM_VIDC_TRANSFER_BT_2020_10                                      = 14
D 256   MSM_VIDC_TRANSFER_BT_2020_12                                      = 15
D 257   MSM_VIDC_TRANSFER_SMPTE_ST2084                                    = 16
D 258   MSM_VIDC_TRANSFER_SMPTE_ST428_1                                   = 17
D 259   MSM_VIDC_TRANSFER_HLG                                             = 18
D 261   MSM_VIDC_EXTRADATA_VUI_DISPLAY_INFO                               = 0x7F100006
D 279   MSM_VIDC_EXTRADATA_HDR_HIST                                       = 0x7F100008
D 284   MSM_VIDC_EXTRADATA_MPEG2_SEQDISP                                  = 0x0000000D
D 296   MSM_VIDC_CS_UNKNOWN                                               = 0
D 297   MSM_VIDC_CS_BT_601                                                = 1
D 298   MSM_VIDC_CS_BT_709                                                = 2
D 299   MSM_VIDC_CS_SMPTE_170                                             = 3
D 300   MSM_VIDC_CS_SMPTE_240                                             = 4
D 301   MSM_VIDC_CS_BT_2020                                               = 5
D 302   MSM_VIDC_CS_RESERVED                                              = 6
D 303   MSM_VIDC_CS_RGB                                                   = 7
D 304   MSM_VIDC_EXTRADATA_VPX_COLORSPACE_INFO                            = 0x00000014
D 312   MSM_VIDC_EXTRADATA_METADATA_LTRINFO                               = 0x7F100004
D 314   LTRINFO                                                          = MSM_VIDC_EXTRADATA_METADATA_LTRINFO (0x7F100004)
D 320   MSM_VIDC_BIT_DEPTH_8                                              = 0
D 321   MSM_VIDC_BIT_DEPTH_10                                             = 1
D 322   MSM_VIDC_BIT_DEPTH_UNSUPPORTED                                    = 0xFFFFFFFF
D 325   MSM_VIDC_PIC_STRUCT_MAYBE_INTERLACED                              = 0x0
D 326   MSM_VIDC_PIC_STRUCT_PROGRESSIVE                                   = 0x1
D 329   MSM_VIDC_ALL_LAYER_ID                                             = 0xFF
E 344   MSM_VIDC_RGB_PRIMARY_00 = 0 ; MSM_VIDC_RGB_PRIMARY_01 = 1 ; MSM_VIDC_RGB_PRIMARY_10 = 2
        MSM_VIDC_RGB_PRIMARY_11 = 3 ; MSM_VIDC_RGB_PRIMARY_20 = 4 ; MSM_VIDC_RGB_PRIMARY_21 = 5
        MSM_VIDC_WHITEPOINT_X = 6 ; MSM_VIDC_WHITEPOINT_Y = 7 ; MSM_VIDC_MAX_DISP_LUM = 8
        MSM_VIDC_MIN_DISP_LUM = 9 ; MSM_VIDC_RGB_MAX_CLL = 10 ; MSM_VIDC_RGB_MAX_FLL = 11
E 359   MSM_VIDC_BUFFER_FD = 0 ; MSM_VIDC_DATA_OFFSET = 1 ; MSM_VIDC_COMP_RATIO = 2
        MSM_VIDC_INPUT_TAG_1 = 3 ; MSM_VIDC_INPUT_TAG_2 = 4
E 367   MSM_VIDC_HEIGHT = 0 ; MSM_VIDC_WIDTH = 1 ; MSM_VIDC_BIT_DEPTH = 2
        MSM_VIDC_PIC_STRUCT = 3 ; MSM_VIDC_COLOR_SPACE = 4 ; MSM_VIDC_FW_MIN_COUNT = 5
```

Note `msm_vidc_utils.h` and `msm_vidc.h` **define the same symbols with the same
values** (`MSM_VIDC_EXTRADATA_*`, `MSM_VIDC_INTERLACE_*`, …) with two different
include guards. Only one of them may be included in a translation unit.

### 2.6 CAF additions in the donor's `include/uapi/linux/videodev2.h`

The bulk of them arrive with the snapshot commit
`6e7d1f9d7242 "vidc_3x: Add snapshot of video driver"` (verified with
`git show 6e7d1f9d7242 -- include/uapi/linux/videodev2.h`), plus a few from the
earlier `e8507af28b12 "msm: vidc: Add snapshot of MSM video driver"` and
`269ba02f63b3 "ANDROID: GKI: Add support for missing V4L2 symbols"`.

**Buffer flags / flags (donor `videodev2.h:1088-1113`)**

```
V4L2_BUF_FLAG_CODECCONFIG            = 0x00020000   (CAF only)
V4L2_BUF_FLAG_DATA_CORRUPT           = 0x00400000   (CAF only)
V4L2_BUF_FLAG_END_OF_SUBFRAME        = 0x00000080   (CAF only)
V4L2_BUF_FLAG_EOS                    = 0x02000000   (CAF only)
V4L2_BUF_FLAG_PERF_MODE              = 0x20000000   (CAF only)
V4L2_BUF_FLAG_READONLY               = 0x04000000   (CAF only)
V4L2_BUF_FLAG_CVPMETADATA_SKIP       = 0x40000000   (CAF only)
V4L2_BUF_INPUT_UNSUPPORTED           = 0x01000000   (CAF only)
```

**QCOM/MSM buffer flags (donor `videodev2.h:1099-1113`)**

```
V4L2_QCOM_BUF_DROP_FRAME                 = 0x00800000
V4L2_QCOM_BUF_END_OF_SUBFRAME            = 0x00000080
V4L2_QCOM_BUF_FLAG_CODECCONFIG           = 0x00020000
V4L2_QCOM_BUF_FLAG_DECODEONLY            = 0x00200000
V4L2_QCOM_BUF_FLAG_EOS                   = 0x02000000
V4L2_QCOM_BUF_FLAG_EOSEQ                 = 0x00040000
V4L2_QCOM_BUF_FLAG_IDRFRAME              = 0x80000000
V4L2_QCOM_BUF_FLAG_PERF_MODE             = 0x20000000
V4L2_QCOM_BUF_FLAG_READONLY              = 0x04000000
V4L2_QCOM_BUF_INPUT_UNSUPPORTED          = 0x01000000
V4L2_QCOM_BUF_TIMESTAMP_INVALID          = 0x00080000

V4L2_MSM_BUF_FLAG_MBAFF                  = 0x00000200
V4L2_MSM_BUF_FLAG_YUV_601_709_CLAMP      = 0x10000000
V4L2_MSM_BUF_FLAG_DEFER                  = 0x40000000
V4L2_MSM_VIDC_BUF_START_CODE_NOT_FOUND   = 0x08000000
```

**Events (donor `videodev2.h:2322-2351`)**

```
V4L2_EVENT_BITDEPTH_FLAG    = 0x00000001
V4L2_EVENT_PICSTRUCT_FLAG   = 0x00000002
V4L2_EVENT_COLOUR_SPACE_FLAG= 0x00000004

V4L2_EVENT_MSM_VIDC_START                                          = 0x08001000
V4L2_EVENT_MSM_VIDC_FLUSH_DONE                                     = 0x08001001
V4L2_EVENT_MSM_VIDC_PORT_SETTINGS_CHANGED_SUFFICIENT               = 0x08001002
V4L2_EVENT_MSM_VIDC_PORT_SETTINGS_CHANGED_INSUFFICIENT             = 0x08001003
V4L2_EVENT_MSM_VIDC_PORT_SETTINGS_BITDEPTH_CHANGED_INSUFFICIENT    = 0x08001004
V4L2_EVENT_MSM_VIDC_SYS_ERROR                                      = 0x08001005
V4L2_EVENT_MSM_VIDC_RELEASE_BUFFER_REFERENCE                       = 0x08001006
V4L2_EVENT_MSM_VIDC_RELEASE_UNQUEUED_BUFFER                        = 0x08001007
V4L2_EVENT_MSM_VIDC_HW_OVERLOAD                                    = 0x08001008
V4L2_EVENT_MSM_VIDC_MAX_CLIENTS                                    = 0x08001009
V4L2_EVENT_MSM_VIDC_HW_UNSUPPORTED                                 = 0x0800100a
V4L2_EVENT_MSM_VIDC_REGISTER_BUFFER_DONE                           = 0x0800100b
V4L2_EVENT_MSM_VIDC_UNREGISTER_BUFFER_DONE                         = 0x0800100c
```

**Encoder/decoder command aliases (donor `videodev2.h:2016-2042`)**

```
V4L2_DEC_QCOM_CMD_RECONFIG_HINT = 6
V4L2_QCOM_CMD_FLUSH             = V4L2_CMD_FLUSH             (4)
V4L2_QCOM_CMD_SESSION_CONTINUE  = V4L2_CMD_SESSION_CONTINUE  (5)
V4L2_QCOM_CMD_FLUSH_OUTPUT      = V4L2_CMD_FLUSH_OUTPUT      (1)
V4L2_QCOM_CMD_FLUSH_CAPTURE     = V4L2_CMD_FLUSH_CAPTURE     (2)
```

**CAF-only pixel formats** (all of these are **absent** from the 6.12 tree, see §3.4):
`V4L2_PIX_FMT_DIVX` (0x58564944), `V4L2_PIX_FMT_DIVX_311` (0x33564944),
`V4L2_PIX_FMT_HEVC_HYBRID` (0x48435648), `V4L2_PIX_FMT_NV12_512` (0x32313551),
`V4L2_PIX_FMT_NV12_UBWC` (0x38323151), `V4L2_PIX_FMT_NV12_TP10_UBWC` (0x41323151),
`V4L2_PIX_FMT_NV12_P010_UBWC` (0x42323151), `V4L2_PIX_FMT_RGBA8888_UBWC` (0x42475251),
`V4L2_PIX_FMT_SDE_Y_CBCR_H2V2_P010_VENUS` (0x30315051), `V4L2_PIX_FMT_CVP` (0x30505643),
`V4L2_PIX_FMT_TME` (0x30454d54) and the ~40 `V4L2_PIX_FMT_SDE_*` display formats.

### 2.7 CAF additions in the donor's `include/uapi/linux/v4l2-controls.h`

Base: `V4L2_CID_MPEG_MSM_VIDC_BASE (V4L2_CTRL_CLASS_MPEG | 0x2000)`
= `0x00990000 | 0x2000` = **`0x00992000`**.

The donor also defines `V4L2_CID_MPEG_VIDEO_MULTI_SLICE_DELIVERY_MODE` (base+18),
`V4L2_CID_VIDC_QBUF_MODE` (base+45), `V4L2_CID_MPEG_VIDEO_MIN_QP_PACKED`
(base+60) and `V4L2_CID_MPEG_VIDEO_MAX_QP_PACKED` (base+61) — note the first two
use the `V4L2_CID_MPEG_*` (not `V4L2_CID_MPEG_VIDC_*`) prefix, which is a CAF
naming inconsistency, not a value collision.

```
V4L2_CID_MPEG_VIDC_VIDEO_PICTYPE_DEC_MODE                          = 0x00992000
V4L2_CID_MPEG_VIDC_VIDEO_KEEP_ASPECT_RATIO                         = 0x00992001
V4L2_CID_MPEG_VIDC_VIDEO_STREAM_FORMAT                             = 0x00992002
V4L2_CID_MPEG_VIDC_VIDEO_DECODE_ORDER                              = 0x00992003
V4L2_CID_MPEG_VIDC_VIDEO_NUM_P_FRAMES                              = 0x00992006
V4L2_CID_MPEG_VIDC_VIDEO_NUM_B_FRAMES                              = 0x00992007
V4L2_CID_MPEG_VIDC_VIDEO_REQUEST_IFRAME                            = 0x00992008
V4L2_CID_MPEG_VIDC_VIDEO_RATE_CONTROL                              = 0x00992009
V4L2_CID_MPEG_VIDC_VIDEO_ROTATION                                  = 0x0099200a
V4L2_CID_MPEG_VIDC_VIDEO_H264_CABAC_MODEL                          = 0x0099200b
V4L2_CID_MPEG_VIDC_VIDEO_INTRA_REFRESH_MODE_CYCLIC                 = 0x0099200c
V4L2_CID_MPEG_VIDC_VIDEO_INTRA_REFRESH_RANDOM                      = 0x0099200d
V4L2_CID_MPEG_VIDC_VIDEO_AU_DELIMITER                              = 0x0099200e
V4L2_CID_MPEG_VIDC_VIDEO_SYNC_FRAME_DECODE                         = 0x0099200f
V4L2_CID_MPEG_VIDC_VIDEO_SECURE                                    = 0x00992010
V4L2_CID_MPEG_VIDC_VIDEO_EXTRADATA                                 = 0x00992011
V4L2_CID_MPEG_VIDEO_MULTI_SLICE_DELIVERY_MODE                      = 0x00992012
V4L2_CID_MPEG_VIDC_VIDEO_VUI_TIMING_INFO                           = 0x00992013
V4L2_CID_MPEG_VIDC_VIDEO_VP8_PROFILE_LEVEL                         = 0x00992014
V4L2_CID_MPEG_VIDC_VIDEO_PRESERVE_TEXT_QUALITY                     = 0x00992015
V4L2_CID_MPEG_VIDC_VIDEO_STREAM_OUTPUT_MODE                        = 0x00992016   (msm_vidc.h)
V4L2_CID_MPEG_VIDC_VIDEO_MPEG2_LEVEL                               = 0x00992017
V4L2_CID_MPEG_VIDC_VIDEO_MPEG2_PROFILE                             = 0x00992018
V4L2_CID_MPEG_VIDC_VIDEO_CONCEAL_COLOR                             = 0x00992019
V4L2_CID_MPEG_VIDC_VIDEO_LTRMODE                                   = 0x0099201a
V4L2_CID_MPEG_VIDC_VIDEO_LTRCOUNT                                  = 0x0099201b
V4L2_CID_MPEG_VIDC_VIDEO_USELTRFRAME                               = 0x0099201c
V4L2_CID_MPEG_VIDC_VIDEO_MARKLTRFRAME                              = 0x0099201d
V4L2_CID_MPEG_VIDC_VIDEO_HIER_P_NUM_LAYERS                         = 0x0099201e
V4L2_CID_MPEG_VIDC_VIDEO_ALLOC_MODE_OUTPUT                         = 0x0099201f
V4L2_CID_MPEG_VIDC_VIDEO_IFRAME_X_RANGE                            = 0x00992020
V4L2_CID_MPEG_VIDC_VIDEO_PFRAME_X_RANGE                            = 0x00992021
V4L2_CID_MPEG_VIDC_VIDEO_BFRAME_X_RANGE                            = 0x00992022
V4L2_CID_MPEG_VIDC_VIDEO_IFRAME_Y_RANGE                            = 0x00992023
V4L2_CID_MPEG_VIDC_VIDEO_PFRAME_Y_RANGE                            = 0x00992024
V4L2_CID_MPEG_VIDC_VIDEO_BFRAME_Y_RANGE                            = 0x00992025
V4L2_CID_MPEG_VIDC_VIDEO_VPX_ERROR_RESILIENCE                      = 0x00992026
V4L2_CID_MPEG_VIDC_VIDEO_BUFFER_SIZE_LIMIT                         = 0x00992027
V4L2_CID_MPEG_VIDC_VIDEO_HEVC_PROFILE                              = 0x00992028
V4L2_CID_MPEG_VIDC_VIDEO_HEVC_TIER_LEVEL                           = 0x00992029
V4L2_CID_MPEG_VIDC_VIDEO_HIER_B_NUM_LAYERS                         = 0x0099202a
V4L2_CID_MPEG_VIDC_VIDEO_HYBRID_HIERP_MODE                         = 0x0099202b
V4L2_CID_MPEG_VIDC_VIDEO_DPB_COLOR_FORMAT                          = 0x0099202c
V4L2_CID_VIDC_QBUF_MODE                                            = 0x0099202d
V4L2_CID_MPEG_VIDC_VIDEO_MAX_HIERP_LAYERS                          = 0x0099202e
V4L2_CID_MPEG_VIDC_VIDEO_BASELAYER_ID                              = 0x0099202f
V4L2_CID_MPEG_VIDC_VENC_PARAM_SAR_WIDTH                            = 0x00992030
V4L2_CID_MPEG_VIDC_VENC_PARAM_SAR_HEIGHT                           = 0x00992031
V4L2_CID_MPEG_VIDC_VIDEO_VQZIP_SEI                                 = 0x00992032
V4L2_CID_MPEG_VIDC_VENC_PARAM_LAYER_BITRATE                        = 0x00992033
V4L2_CID_MPEG_VIDC_VIDEO_PRIORITY                                  = 0x00992034
V4L2_CID_MPEG_VIDC_VIDEO_OPERATING_RATE                            = 0x00992035
V4L2_CID_MPEG_VIDC_VIDEO_VENC_BITRATE_TYPE                         = 0x00992036
V4L2_CID_MPEG_VIDC_VIDEO_VPE_CSC                                   = 0x00992037
V4L2_CID_MPEG_VIDC_VIDEO_LOWLATENCY_MODE                           = 0x00992038
V4L2_CID_MPEG_VIDC_VIDEO_BLUR_DIMENSIONS                           = 0x00992039
V4L2_CID_MPEG_VIDC_VIDEO_BLUR_WIDTH                                = 0x0099203a
V4L2_CID_MPEG_VIDC_VIDEO_BLUR_HEIGHT                               = 0x0099203b
V4L2_CID_MPEG_VIDC_VIDEO_COLOR_SPACE                               = 0x0099203c
V4L2_CID_MPEG_VIDC_VIDEO_FULL_RANGE                                = 0x0099203d
V4L2_CID_MPEG_VIDC_VIDEO_TRANSFER_CHARS                            = 0x0099203e
V4L2_CID_MPEG_VIDC_VIDEO_MATRIX_COEFFS                             = 0x0099203f
V4L2_CID_MPEG_VIDC_VIDEO_IFRAME_SIZE_TYPE                          = 0x00992040
V4L2_CID_MPEG_VIDC_VIDEO_LAYER_ID                                  = 0x00992041
V4L2_CID_MPEG_VIDC_VIDEO_VP9_PROFILE                               = 0x00992042
V4L2_CID_MPEG_VIDC_VIDEO_VP9_LEVEL                                 = 0x00992043
V4L2_CID_MPEG_VIDC_VIDEO_COLOR_SPACE_CAPS                          = 0x00992044
V4L2_CID_MPEG_VIDC_VIDEO_ROTATION_CAPS                             = 0x00992045
V4L2_CID_MPEG_VIDC_VIDEO_MB_ERROR_MAP_REPORTING                    = 0x00992046
V4L2_CID_MPEG_VIDC_VIDEO_CONTINUE_DATA_TRANSFER                    = 0x00992047
V4L2_CID_MPEG_VIDC_VIDEO_ALLOC_MODE_INPUT                          = 0x00992048
V4L2_CID_MPEG_VIDC_VIDEO_FRAME_ASSEMBLY                            = 0x00992049
V4L2_CID_MPEG_VIDC_VIDEO_H263_PROFILE                              = 0x0099204a
V4L2_CID_MPEG_VIDC_VIDEO_OUTPUT_ORDER                              = 0x0099204b
V4L2_CID_MPEG_VIDC_VIDEO_H264_TRANSFORM_8x8                        = 0x0099204c
V4L2_CID_MPEG_VIDC_VIDEO_QP_MASK                                   = 0x0099204d
   (offsets 0x4e .. 0x5f are unused)
V4L2_CID_MPEG_VIDEO_MIN_QP_PACKED                                  = 0x00992060
V4L2_CID_MPEG_VIDEO_MAX_QP_PACKED                                  = 0x00992061
V4L2_CID_MPEG_VIDC_VIDEO_ADAPTIVE_B                                = 0x00992062
V4L2_CID_MPEG_VIDC_VIDEO_I_FRAME_QP                                = 0x00992063
V4L2_CID_MPEG_VIDC_VIDEO_P_FRAME_QP                                = 0x00992064
V4L2_CID_MPEG_VIDC_VIDEO_B_FRAME_QP                                = 0x00992065
V4L2_CID_MPEG_VIDC_VIDEO_I_FRAME_QP_MIN                            = 0x00992066
V4L2_CID_MPEG_VIDC_VIDEO_P_FRAME_QP_MIN                            = 0x00992067
V4L2_CID_MPEG_VIDC_VIDEO_B_FRAME_QP_MIN                            = 0x00992068
V4L2_CID_MPEG_VIDC_VIDEO_I_FRAME_QP_MAX                            = 0x00992069
V4L2_CID_MPEG_VIDC_VIDEO_P_FRAME_QP_MAX                            = 0x0099206a
V4L2_CID_MPEG_VIDC_VIDEO_B_FRAME_QP_MAX                            = 0x0099206b
V4L2_CID_MPEG_VIDC_VIDEO_DYN_QP                                    = 0x0099206c
V4L2_CID_MPEG_VIDC_VIDEO_CONCEAL_COLOR_8BIT                        = 0x0099206d
V4L2_CID_MPEG_VIDC_VIDEO_CONCEAL_COLOR_10BIT                       = 0x0099206e
V4L2_CID_MPEG_VIDC_VIDEO_TME_PROFILE                               = 0x0099206f
V4L2_CID_MPEG_VIDC_VIDEO_TME_LEVEL                                 = 0x00992070
V4L2_CID_MPEG_VIDC_VIDEO_TME_PAYLOAD_VERSION                       = 0x00992071
V4L2_CID_MPEG_VIDC_VIDEO_VPE_CSC_CUSTOM_MATRIX                     = 0x00992072
V4L2_CID_MPEG_VIDC_VIDEO_FLIP                                      = 0x00992073
V4L2_CID_MPEG_VIDC_VENC_HDR_INFO                                   = 0x00992074
V4L2_CID_MPEG_VIDC_IMG_GRID_SIZE                                   = 0x00992075
V4L2_CID_MPEG_VIDC_COMPRESSION_QUALITY                             = 0x00992076
V4L2_CID_MPEG_VIDC_VIDEO_FRAME_RATE                                = 0x00992077
V4L2_CID_MPEG_VIDC_VIDEO_HEVC_MAX_HIER_CODING_LAYER                = 0x00992078
V4L2_CID_MPEG_VIDC_VENC_CVP_DISABLE                                = 0x00992079
V4L2_CID_MPEG_VIDC_VENC_NATIVE_RECORDER                            = 0x0099207a
V4L2_CID_MPEG_VIDC_VENC_RC_TIMESTAMP_DISABLE                       = 0x0099207b
V4L2_CID_MPEG_VIDC_SUPERFRAME                                      = 0x0099207c
V4L2_CID_MPEG_VIDC_CAPTURE_FRAME_RATE                              = 0x0099207d
V4L2_CID_MPEG_VIDC_CVP_FRAME_RATE                                  = 0x0099207e
V4L2_CID_MPEG_VIDC_VIDEO_ROI_TYPE                                  = 0x0099207f
V4L2_CID_MPEG_VIDC_SET_PERF_LEVEL                                  = 0x00992080
   (offsets 0x81 .. 0x82 are unused)
V4L2_CID_MPEG_VIDC_VENC_BITRATE_SAVINGS                            = 0x00992083
   (offset 0x84 is unused)
V4L2_CID_MPEG_VIDC_VIDEO_LOWLATENCY_HINT                           = 0x00992085
V4L2_CID_MPEG_VIDC_VIDEO_AIR_MBS                                   = 0x00992086
V4L2_CID_MPEG_VIDC_VIDEO_AIR_REF                                   = 0x00992087
V4L2_CID_MPEG_VIDC_VIDEO_CIR_MBS                                   = 0x00992088
V4L2_CID_MPEG_VIDC_VIDEO_H264_VUI_TIMING_INFO                      = 0x00992089
V4L2_CID_MPEG_VIDEO_MULTI_SLICE_GOB                                = 0x0099208a
V4L2_CID_MPEG_VIDC_VIDEO_H264_VUI_BITSTREAM_RESTRICT               = 0x0099208b
V4L2_CID_MPEG_VIDC_VIDEO_DEINTERLACE                               = 0x0099208c
V4L2_CID_MPEG_VIDC_VIDEO_MPEG4_TIME_RESOLUTION                     = 0x0099208d
V4L2_CID_MPEG_VIDC_VIDEO_REQUEST_SEQ_HEADER                        = 0x0099208e
V4L2_CID_MPEG_VIDC_VIDEO_RATE_CONTROL_TIMESTAMP_MODE               = 0x0099208f
V4L2_CID_MPEG_VIDC_VIDEO_ENABLE_INITIAL_QP                         = 0x00992090
V4L2_CID_MPEG_VIDC_VIDEO_INITIAL_I_FRAME_QP                        = 0x00992091
V4L2_CID_MPEG_VIDC_VIDEO_INITIAL_P_FRAME_QP                        = 0x00992092
V4L2_CID_MPEG_VIDC_VIDEO_INITIAL_B_FRAME_QP                        = 0x00992093
V4L2_CID_MPEG_VIDC_VIDEO_H264_NAL_SVC                              = 0x00992094
V4L2_CID_MPEG_VIDC_VIDEO_PERF_MODE                                 = 0x00992095
V4L2_CID_MPEG_VIDC_VIDEO_MBI_STATISTICS_MODE                       = 0x00992096
V4L2_CID_MPEG_VIDC_VIDEO_CONFIG_QP                                 = 0x00992097
V4L2_CID_MPEG_VIDC_VIDEO_H264_PIC_ORDER_CNT                        = 0x00992098
V4L2_CID_MPEG_VIDC_VIDEO_SCS_THRESHOLD                             = 0x00992099
V4L2_CID_MPEG_VIDC_VIDEO_MVC_BUFFER_LAYOUT                         = 0x0099209a
V4L2_CID_MPEG_VIDC_VIDEO_SECURE_SCALING_THRESHOLD                  = 0x0099209b
V4L2_CID_MPEG_VIDC_VIDEO_NON_SECURE_OUTPUT2                        = 0x0099209c
V4L2_CID_MPEG_VIDC_VIDEO_VP8_MIN_QP                                = 0x0099209d
V4L2_CID_MPEG_VIDC_VIDEO_VP8_MAX_QP                                = 0x0099209e
V4L2_CID_MPEG_VIDC_VIDEO_H263_LEVEL                                = 0x0099209f
V4L2_CID_MPEG_VIDC_VIDEO_POST_LOOP_DEBLOCKER_MODE                  = 0x009920a0
V4L2_CID_MPEG_VIDC_VIDEO_DIVX_FORMAT                               = 0x009920a1
   (offset 0xa2 is unused)
V4L2_CID_MPEG_VIDC_IMG_GRID_DIMENSION                              = 0x009920a3
V4L2_CID_MPEG_VIDC_VIDEO_FRAME_QP                                  = 0x009920a4
V4L2_CID_MPEG_VIDC_VIDEO_INTRA_REFRESH_MODE                        = 0x009920a5
V4L2_CID_MPEG_VIDC_VIDEO_IR_MBS                                    = 0x009920a6
V4L2_CID_MPEG_VIDC_ENABLE_ONLY_BASE_LAYER_IR                       = 0x009920a7
```

The 138 `V4L2_CID_MPEG_VIDC_*` IDs occupy **0x00992000 … 0x009920a7** (138
distinct values, no duplicates).

Enum-valued companion symbols (donor `v4l2-controls.h:793-1170`), all of them
menu/boolean *values* rather than control IDs:
`V4L2_MPEG_VIDC_VIDEO_PICTYPE_DECODE_{I=1,P=2,B=4}`, `..._DECODE_{OFF=0,ON=1}`,
`V4L2_MPEG_VIDC_VIDEO_NAL_FORMAT_{STARTCODES=0,ONE_NAL_PER_BUFFER=1,
ONE_BYTE_LENGTH=2,TWO_BYTE_LENGTH=3,FOUR_BYTE_LENGTH=4}`,
`V4L2_CID_MPEG_VIDC_VIDEO_RATE_CONTROL_{OFF=0,VBR_VFR=1,VBR_CFR=2,CBR_VFR=3,
CBR_CFR=4,MBR_CFR=5,MBR_VFR=6,CQ=7}`,
`V4L2_CID_MPEG_VIDC_VIDEO_ROTATION_{NONE=0,90=1,180=2,270=3}`,
`V4L2_CID_MPEG_VIDC_VIDEO_H264_CABAC_MODEL_{0,1,2}`,
`V4L2_MPEG_VIDC_VIDEO_AU_DELIMITER_{DISABLED=0,ENABLED=1}`,
`V4L2_MPEG_VIDC_VIDEO_SYNC_FRAME_DECODE_{DISABLE=0,ENABLE=1}`,
`V4L2_MPEG_VIDC_VIDEO_VUI_TIMING_INFO_{DISABLED=0,ENABLED=1}`,
`V4L2_MPEG_VIDC_VIDEO_VP8_{UNUSED=0,VERSION_0=1..VERSION_3=4}`,
`V4L2_MPEG_VIDC_VIDEO_PRESERVE_TEXT_QUALITY_{DISABLED=0,ENABLED=1}`,
`V4L2_MPEG_VIDC_VIDEO_MPEG2_LEVEL_{0..3}`,
`V4L2_MPEG_VIDC_VIDEO_MPEG2_PROFILE_{SIMPLE=0,MAIN=1,HIGH=2,SNR_SCALABLE=3,
SPATIAL_SCALABLE=4,422=5}`,
`V4L2_MPEG_VIDC_VIDEO_MVC_{SEQUENTIAL=0,TOP_BOTTOM=1}`,
`V4L2_MPEG_VIDC_VIDEO_LTR_MODE_{DISABLE=0,MANUAL=1,PERIODIC=2}`,
`V4L2_MPEG_VIDC_VIDEO_{STATIC=0,RING=1,DYNAMIC=2}`,
`V4L2_MPEG_VIDC_VIDEO_VPX_ERROR_RESILIENCE_{DISABLED=0,ENABLED=1}`,
`V4L2_MPEG_VIDC_VIDEO_HEVC_PROFILE_{MAIN=0,MAIN10=1,MAIN_STILL_PIC=2}`,
`V4L2_MPEG_VIDC_VIDEO_HEVC_LEVEL_*` (0..26, `..._UNKNOWN=26`),
`V4L2_MPEG_VIDC_VIDEO_DPB_COLOR_FMT_{NONE=0,UBWC=1,TP10_UBWC=2}`,
`V4L2_MPEG_VIDC_VIDEO_VQZIP_SEI_{DISABLE=0,ENABLE=1}`,
`V4L2_MPEG_VIDC_VIDEO_PRIORITY_REALTIME_{ENABLE=0,DISABLE=1}`,
`V4L2_MPEG_VIDC_VIDEO_VENC_BITRATE_{DISABLE=0,ENABLE=1}`,
`V4L2_MPEG_VIDC_VIDEO_VPE_CSC_{DISABLE=0,ENABLE=1}`,
`V4L2_MPEG_VIDC_VIDEO_LOWLATENCY_{DISABLE=0,ENABLE=1}`,
`V4L2_MPEG_VIDC_VIDEO_FULL_RANGE_{DISABLE=0,ENABLE=1}`,
`V4L2_MPEG_VIDC_VIDEO_VP9_PROFILE_{UNUSED=0,P0=1,…}`,
`V4L2_MPEG_VIDC_EXTRADATA_*` (0..34, see the donor header).

---

## 3. COLLISION CHECK

### 3.1 Summary

| Namespace | Donor | 6.12 | Result |
|---|---|---|---|
| `V4L2_QCOM_BUF_*` | 11 symbols | **0 symbols** | No name collision. **Two numeric collisions** (see §3.2). |
| `V4L2_EVENT_MSM_VIDC_*` | 13 symbols | **0 symbols** | No name or numeric collision. |
| `V4L2_CID_MPEG_VIDC_*` | 138 symbols | **0 symbols** | No collision with any 6.12 `V4L2_CID_*`. |
| QCOM/CAF `V4L2_PIX_FMT_*` | 23 used by vidc_3x | 15 of 23 present | 15 values match exactly, **8 are missing** from 6.12. |

### 3.2 Numeric collisions in the buffer-flag namespace — THE IMPORTANT PART

6.12's vb2 masks out a set of flags that the 4.19 vb2 does not. Quoting
`/home/kurision/development/kernel/ack-kgsl/drivers/media/common/videobuf2/videobuf2-v4l2.c:50-62`:

```c
/* Flags that are set by us */
#define V4L2_BUFFER_MASK_FLAGS	(V4L2_BUF_FLAG_MAPPED | V4L2_BUF_FLAG_QUEUED | \
				 V4L2_BUF_FLAG_DONE | V4L2_BUF_FLAG_ERROR | \
				 V4L2_BUF_FLAG_PREPARED | \
				 V4L2_BUF_FLAG_IN_REQUEST | \
				 V4L2_BUF_FLAG_REQUEST_FD | \
				 V4L2_BUF_FLAG_TIMESTAMP_MASK)
/* Output buffer flags that should be passed on to the driver */
#define V4L2_BUFFER_OUT_FLAGS	(V4L2_BUF_FLAG_PFRAME | \
				 V4L2_BUF_FLAG_BFRAME | \
				 V4L2_BUF_FLAG_KEYFRAME | \
				 V4L2_BUF_FLAG_TIMECODE | \
				 V4L2_BUF_FLAG_M2M_HOLD_CAPTURE_BUF)
```

and the donor's 4.19 equivalent
(`/home/kurision/development/kernel/oc-test/drivers/media/common/videobuf2/videobuf2-v4l2.c:44-47`):

```c
/* Flags that are set by the vb2 core */
#define V4L2_BUFFER_MASK_FLAGS	(V4L2_BUF_FLAG_MAPPED | V4L2_BUF_FLAG_QUEUED | \
				 V4L2_BUF_FLAG_DONE | V4L2_BUF_FLAG_ERROR | \
				 V4L2_BUF_FLAG_PREPARED | \
				 V4L2_BUF_FLAG_TIMESTAMP_MASK)
```

**Two CAF buffer flags land exactly on 6.12 flags that vb2 now owns:**

| CAF flag (donor) | value | 6.12 name at the same value | 6.12 treatment | consequence |
|---|---|---|---|---|
| `V4L2_QCOM_BUF_DROP_FRAME` | `0x00800000` | `V4L2_BUF_FLAG_REQUEST_FD` (`include/uapi/linux/videodev2.h:1229`) | in `V4L2_BUFFER_MASK_FLAGS` | **silently dropped** on both QBUF and DQBUF |
| `V4L2_QCOM_BUF_END_OF_SUBFRAME` (= `V4L2_BUF_FLAG_END_OF_SUBFRAME`) | `0x00000080` | `V4L2_BUF_FLAG_IN_REQUEST` (`include/uapi/linux/videodev2.h:1207`) | in `V4L2_BUFFER_MASK_FLAGS` | **silently dropped** on both QBUF and DQBUF |
| `V4L2_MSM_BUF_FLAG_MBAFF` | `0x00000200` | `V4L2_BUF_FLAG_M2M_HOLD_CAPTURE_BUF` (`videodev2.h:1211`) | in `V4L2_BUFFER_OUT_FLAGS` | cleared on capture queues (`:341-346`) |

Evidence in 6.12 `videobuf2-v4l2.c`:

```c
319:	/* Zero flags that we handle */
320:	vbuf->flags = b->flags & ~V4L2_BUFFER_MASK_FLAGS;
321:	if (!vb->vb2_queue->copy_timestamp || V4L2_TYPE_IS_CAPTURE(b->type)) {
...
327:		vbuf->flags &= ~V4L2_BUF_FLAG_TSTAMP_SRC_MASK;
...
341:	} else {
342:		/* Zero any output buffer flags as this is a capture buffer */
343:		vbuf->flags &= ~V4L2_BUFFER_OUT_FLAGS;
344:		/* Zero last flag, this is a signal from driver to userspace */
345:		vbuf->flags &= ~V4L2_BUF_FLAG_LAST;
346:	}
```

```c
545:	/*
546:	 * Clear any buffer state related flags.
547:	 */
548:	b->flags &= ~V4L2_BUFFER_MASK_FLAGS;
```

and in the qbuf path, `V4L2_BUF_FLAG_REQUEST_FD` is *actively interpreted*:

```c
396:	if (!is_prepare && (b->flags & V4L2_BUF_FLAG_REQUEST_FD) &&
397:	    vb->state != VB2_BUF_STATE_DEQUEUED) {
398:		dprintk(q, 1, "%s: buffer is not in dequeued state\n", opname);
399:		return -EINVAL;
400:	}
...
416:	if (!(b->flags & V4L2_BUF_FLAG_REQUEST_FD)) {
417:		if (q->requires_requests) { ... return -EBADR; }
...
426:	} else if (!q->supports_requests) {
427:		dprintk(q, 1, "%s: queue does not support requests\n", opname);
428:		return -EBADR;
```

**Consequence:** if a userspace app sets `V4L2_QCOM_BUF_DROP_FRAME` on a buffer
and calls `VIDIOC_QBUF`, the 6.12 vb2 core sees `V4L2_BUF_FLAG_REQUEST_FD` and
either returns `-EINVAL` ("buffer is not in dequeued state") or `-EBADR`
("queue does not support requests"), because the vidc_3x queue does not set
`VB2_SUPPORTS_REQUESTS`. On the DQBUF side the driver-set
`V4L2_QCOM_BUF_DROP_FRAME` (donor `msm_vidc_common.c:2290`) is stripped from
`b->flags` before it reaches userspace, so the app never learns that the frame
was dropped. In the 4.19 donor both directions work.

Two more partial-overlap cases:

| CAF flag | value | 6.12 mask | consequence |
|---|---|---|---|
| `V4L2_QCOM_BUF_FLAG_EOSEQ` | `0x00040000` | inside `V4L2_BUF_FLAG_TSTAMP_SRC_MASK` (`0x00070000`, `videodev2.h:1223`) | cleared on capture/non-COPY-timestamp queues (`videobuf2-v4l2.c:321-327`). **Same in 4.19** (donor `videobuf2-v4l2.c:418-426`), so not a regression. |
| `V4L2_QCOM_BUF_TIMESTAMP_INVALID` | `0x00080000` | no 6.12 mask covers it | safe |

Everything else in the CAF flag set is numerically free in 6.12's buffer-flag
namespace:
`V4L2_QCOM_BUF_FLAG_CODECCONFIG` (0x00020000), `V4L2_QCOM_BUF_FLAG_DECODEONLY`
(0x00200000), `V4L2_QCOM_BUF_FLAG_EOS` (0x02000000), `V4L2_QCOM_BUF_FLAG_READONLY`
(0x04000000), `V4L2_QCOM_BUF_FLAG_PERF_MODE` (0x20000000),
`V4L2_QCOM_BUF_FLAG_IDRFRAME` (0x80000000),
`V4L2_MSM_BUF_FLAG_YUV_601_709_CLAMP` (0x10000000),
`V4L2_MSM_BUF_FLAG_DEFER` (0x40000000),
`V4L2_MSM_VIDC_BUF_START_CODE_NOT_FOUND` (0x08000000).

### 3.3 `V4L2_CID_MPEG_VIDC_*` vs the 6.12 MPEG / VIDEO / CODEC control IDs

**Zero collisions.** The donor's IDs live in `0x00992000 … 0x009920a7`. In the
6.12 tree:

```
V4L2_CTRL_CLASS_CODEC        = 0x00990000   (include/uapi/linux/v4l2-controls.h:20)
V4L2_CID_CODEC_BASE          = 0x00990900   (v4l2-controls.h:229)
V4L2_CID_CODEC_CLASS         = 0x00990001   (v4l2-controls.h:230)
V4L2_CID_CODEC_CX2341X_BASE  = 0x00991000   (v4l2-controls.h:911)
V4L2_CID_CODEC_MFC51_BASE    = 0x00991100   (v4l2-controls.h:952)
V4L2_CID_CODEC_STATELESS_BASE= 0x00a40900   (v4l2-controls.h:1318)
```

All 477 `V4L2_CID_*` defines in the 6.12 tree were resolved numerically; the
**only** ones anywhere near the donor's range are the CX2341X family at
0x00991000+ and the MFC51 family at 0x00991100+, both below 0x00992000.
An exhaustive scan for "any 6.12 `V4L2_CID_*` whose value equals a donor
`V4L2_CID_MPEG_VIDC_*`" returned **0 hits**, and the reverse scan ("any 6.12
`V4L2_CID_*` inside 0x00992000..0x009920a7") also returned **0 hits**.

**However — a compile break, not a numeric one.** The donor's base is

```c
/* donor include/uapi/linux/v4l2-controls.h:787 */
#define V4L2_CID_MPEG_MSM_VIDC_BASE		(V4L2_CTRL_CLASS_MPEG | 0x2000)
```

and `V4L2_CTRL_CLASS_MPEG` is **not defined for kernel code** in 6.12. It only
exists in the userspace-compatibility block:

```c
/* target include/uapi/linux/v4l2-controls.h:3502-3510 */
/* MPEG-compression definitions kept for backwards compatibility */
#ifndef __KERNEL__
#define V4L2_CTRL_CLASS_MPEG            V4L2_CTRL_CLASS_CODEC
#define V4L2_CID_MPEG_CLASS             V4L2_CID_CODEC_CLASS
#define V4L2_CID_MPEG_BASE              V4L2_CID_CODEC_BASE
#define V4L2_CID_MPEG_CX2341X_BASE      V4L2_CID_CODEC_CX2341X_BASE
#define V4L2_CID_MPEG_MFC51_BASE        V4L2_CID_CODEC_MFC51_BASE
#endif
```

(the donor, by contrast, defines `V4L2_CTRL_CLASS_MPEG 0x00990000`
unconditionally at `include/uapi/linux/v4l2-controls.h:55`).
So the ported base **must** be written as

```c
#define V4L2_CID_MPEG_MSM_VIDC_BASE  (V4L2_CTRL_CLASS_CODEC | 0x2000)   /* 0x00992000 */
```

which is numerically identical (`0x00990000 | 0x2000`), so the ABI is preserved.
The same applies to `IS_PRIV_CTRL()` (donor `msm_vidc_common.h:74`), which
compares against `V4L2_CTRL_CLASS_MPEG`:

```c
#define IS_PRIV_CTRL(idx) (\
		(V4L2_CTRL_ID2WHICH(idx) == V4L2_CTRL_CLASS_MPEG) && \
		V4L2_CTRL_DRIVER_PRIV(idx))
```

`V4L2_CTRL_ID2WHICH(id) = ((id) & 0x0fff0000UL)` and
`V4L2_CTRL_DRIVER_PRIV(id) = (((id) & 0xffff) >= 0x1000)`
(target `include/uapi/linux/videodev2.h:1904-1905`).
For every donor VIDC CID (`0x00992000 + n`, `n` ≤ 0xa7) the low 16 bits are
`0x2000 + n` ≥ `0x1000`, so `IS_PRIV_CTRL` is TRUE and all of them are created
through `v4l2_ctrl_new_custom()` with the driver's own `.qmenu` — which is the
path that still works in 6.12 (`drivers/media/v4l2-core/v4l2-ctrls-core.c:2120-2160`).
Note that 6.12's `v4l2_ctrl_new_custom()` now emits
`WARN_ON(step)` for menus and `WARN_ON(cfg->menu_skip_mask)` for non-menus
(`v4l2-ctrls-core.c:2145-2148`), so the control tables must keep `step == 0`
for MENU controls and `menu_skip_mask == 0` for non-MENU controls.

### 3.4 Fourccs

The 23 `V4L2_PIX_FMT_*` that vidc_3x actually references
(`grep -rE "V4L2_PIX_FMT_" drivers/media/platform/msm/vidc_3x/`) compared with
the 6.12 `include/uapi/linux/videodev2.h`:

| fourcc | donor value | 6.12 | match |
|---|---|---|---|
| `V4L2_PIX_FMT_DIVX` | 0x58564944 (`DIVX`) | **absent** | — |
| `V4L2_PIX_FMT_DIVX_311` | 0x33564944 (`DIV3`) | **absent** | — |
| `V4L2_PIX_FMT_H263` | 0x33363248 | 0x33363248 | yes |
| `V4L2_PIX_FMT_H264` | 0x34363248 | 0x34363248 | yes |
| `V4L2_PIX_FMT_H264_MVC` | 0x3436324d | 0x3436324d | yes |
| `V4L2_PIX_FMT_H264_NO_SC` | 0x31435641 | 0x31435641 | yes |
| `V4L2_PIX_FMT_HEVC` | 0x43564548 | 0x43564548 | yes |
| `V4L2_PIX_FMT_HEVC_HYBRID` | 0x48435648 (`HVCH`) | **absent** | — |
| `V4L2_PIX_FMT_MPEG1` | 0x3147504d | 0x3147504d | yes |
| `V4L2_PIX_FMT_MPEG2` | 0x3247504d | 0x3247504d | yes |
| `V4L2_PIX_FMT_MPEG4` | 0x3447504d | 0x3447504d | yes |
| `V4L2_PIX_FMT_NV12` | 0x3231564e | 0x3231564e | yes |
| `V4L2_PIX_FMT_NV12_512` | 0x32313551 (`Q512`) | **absent** | — |
| `V4L2_PIX_FMT_NV12_TP10_UBWC` | 0x41323151 (`Q12A`) | **absent** | — |
| `V4L2_PIX_FMT_NV12_UBWC` | 0x38323151 (`Q128`) | **absent** | — |
| `V4L2_PIX_FMT_NV21` | 0x3132564e | 0x3132564e | yes |
| `V4L2_PIX_FMT_RGB32` | 0x34424752 (`RGB4`) | 0x34424752 | yes |
| `V4L2_PIX_FMT_RGBA8888_UBWC` | 0x42475251 (`QRGB`) | **absent** | — |
| `V4L2_PIX_FMT_SDE_Y_CBCR_H2V2_P010_VENUS` | 0x30315051 (`QP10`) | **absent** | — |
| `V4L2_PIX_FMT_VC1_ANNEX_G` | 0x47314356 | 0x47314356 | yes |
| `V4L2_PIX_FMT_VC1_ANNEX_L` | 0x4c314356 | 0x4c314356 | yes |
| `V4L2_PIX_FMT_VP8` | 0x30385056 | 0x30385056 | yes |
| `V4L2_PIX_FMT_VP9` | 0x30395056 | 0x30395056 | yes |

**15 of 23 already exist in 6.12 and every single one of those 15 has the
identical value. 8 are missing and must be added to the 6.12 header**
(`grep -rn "NV12_512\|NV12_UBWC\|TP10_UBWC\|RGBA8888_UBWC\|DIVX\|HEVC_HYBRID\|SDE_Y_CBCR" include/uapi/linux/videodev2.h` returns nothing in the target tree).

Two of the eight are used by the encoder/decoder pixel-format negotiation and
by the MDP hand-off, so the port **cannot** work without them:
`V4L2_PIX_FMT_NV12_UBWC` (decoder output) and
`V4L2_PIX_FMT_SDE_Y_CBCR_H2V2_P010_VENUS` (10-bit encoder output to the MDP).

A separate CAF-only set (`V4L2_PIX_FMT_SDE_*`, ~40 formats) *does* collide
numerically with upstream 6.12 names, but those names are not used by vidc_3x
except `V4L2_PIX_FMT_SDE_Y_CBCR_H2V2_P010_VENUS`, which is unique
(0x30315051). Examples of the CAF-vs-upstream fourcc collisions (not used by
vidc_3x, listed for completeness):
`V4L2_PIX_FMT_SDE_Y_CBCR_H2V2_P010` == `V4L2_PIX_FMT_P010` (0x30313050);
`V4L2_PIX_FMT_SDE_RGBA_8888` == `V4L2_PIX_FMT_RGBA32` (0x34324241);
`V4L2_PIX_FMT_SDE_RGBX_8888` == `V4L2_PIX_FMT_RGBX32` (0x34324258);
`V4L2_PIX_FMT_SDE_SBGGRPLAIN16`-style pairs similarly.

### 3.5 Events

`V4L2_EVENT_MSM_VIDC_START` = `V4L2_EVENT_PRIVATE_START + 0x1000` =
`0x08000000 + 0x1000` = **0x08001000**, and the range
`0x08001000..0x0800100c` is free in the 6.12 tree: the only private-event
users in the target are `atomisp` (`V4L2_EVENT_PRIVATE_START + 1..6`,
`drivers/staging/media/atomisp/include/linux/atomisp.h:888-892`),
`imx-media` (`+0`), `omap3isp` (`| 0x100`) and `g_uvc` (`+0..5`).
None of them reaches 0x08001000.

Note a **donor-internal** collision that must not be copied: the donor's
`V4L2_EVENT_MSM_CVP_START` is *also* `V4L2_EVENT_PRIVATE_START + 0x1000`
(donor `videodev2.h:2356`), i.e. `V4L2_EVENT_MSM_VIDC_START ==
V4L2_EVENT_MSM_CVP_START`. Only the VIDC half is needed by this port.

---

## 4. 6.12 API SURVEY FOR THE PORT

### 4.1 Firmware load: `subsystem_get_with_fwname` / `subsys_notif` / `venus_boot.c` PIL

**Donor.**
* `venus_hfi.c:4324` — `subsystem_get_with_fwname("venus", device->res->fw_name)`
  to pull `venus.mdt` into memory and `subsystem_put()` it back.
* `venus_boot.c:449` — `subsys_notif_register_notifier("venus", &venus_notifier)`
  and `venus_boot.c:468` `subsys_notif_unregister_notifier()`; the notifier
  callback `venus_notifier_cb()` (`venus_boot.c:356-415`) does
  `devm_regulator_get()` + `regulator_enable()` + clock enable and then calls
  `pil_venus_auth_and_reset()` / `pil_venus_shutdown()`.
* `venus_boot.c:440` — `ioremap_nocache(res->register_base, res->register_size)`.

**Target equivalents (all already present in the port).**

`drivers/media/platform/qcom/venus/firmware.c:82-146` — the upstream Venus
firmware loader, which is what the port's Venus node
(`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-venus.dtsi`) uses:

```c
110:	ret = request_firmware(&mdt, fwname, dev);
111:	if (ret < 0)
112:		return ret;
113:
114:	fw_size = qcom_mdt_get_size(mdt);
...
135:	if (core->use_tz)
136:		ret = qcom_mdt_load(dev, mdt, fwname, VENUS_PAS_ID,
137:				    mem_va, *mem_phys, *mem_size, NULL);
138:	else
139:		ret = qcom_mdt_load_no_init(dev, mdt, fwname, VENUS_PAS_ID,
140:					    mem_va, *mem_phys, *mem_size, NULL);
```

with the secure-world calls in the same file:

```c
220:	    (core->use_tz && !qcom_scm_is_available()))
238:		ret = qcom_scm_pas_auth_and_reset(VENUS_PAS_ID);
256:		ret = qcom_scm_mem_protect_video_var(res->cp_start,
261:			qcom_scm_pas_shutdown(VENUS_PAS_ID);
```

`qcom_mdt_loader.h` / `qcom_scm.h` are at
`include/linux/soc/qcom/mdt_loader.h` and
`include/linux/firmware/qcom/qcom_scm.h`; the helpers the donor needs are all
present there:

```
include/linux/firmware/qcom/qcom_scm.h:62  bool qcom_scm_is_available(void);
include/linux/firmware/qcom/qcom_scm.h:67  int qcom_scm_set_remote_state(u32 state, u32 id);
include/linux/firmware/qcom/qcom_scm.h:79  int qcom_scm_pas_auth_and_reset(u32 peripheral);
include/linux/firmware/qcom/qcom_scm.h:80  int qcom_scm_pas_shutdown(u32 peripheral);
include/linux/firmware/qcom/qcom_scm.h:91  int qcom_scm_mem_protect_video_var(u32 cp_start, u32 cp_size, ...)
```

**Conclusion:** the donor's `subsystem_get_with_fwname()` +
`subsys_notif_register_notifier()` + `venus_boot.c` PIL path has **no direct
6.12 equivalent**. It must be replaced by the upstream-Venus model that the
port already runs:
* firmware → `qcom_mdt_load()` / `qcom_mdt_load_no_init()` on a
  `memory-region` reserved area (`firmware.c:97-108,128-140`);
* power → genpd + `pm_runtime` (§4.2);
* secure memory protection → `qcom_scm_mem_protect_video_var()`
  (`firmware.c:256`), which replaces the donor's
  `scm_call2(SCM_SIP_FNID(SCM_SVC_MP, TZBSP_MEM_PROTECT_VIDEO_VAR))`
  (`venus_hfi.c:3945`);
* `subsys_notif` has **no implementation** in the target tree: the only
  `subsystem_notif.h` is the CAF copy under
  `sound/soc/msm/caf-include/soc/qcom/subsystem_notif.h`, and there is **no
  `.c` file defining `subsys_notif_register_notifier()`** anywhere in the
  target (verified with `grep -rn "subsys_notif_register_notifier" --include=*.c`).
  `CONFIG_MSM_SUBSYSTEM_RESTART` is not set in `out/.config`.

### 4.2 `regulator_get` on the GDSC → genpd / `dev_pm_domain_attach_by_name`

**Donor** (`venus_boot.c`):
```c
376:		venus_data->gdsc = devm_regulator_get(
377:				&data->pdev->dev, venus_data->reg_name);
...
389:	ret = regulator_enable(venus_data->gdsc);
...
241:		rc = regulator_enable(venus_data->gdsc);   /* non-IOMMU path */
```
with the DT phandles `venus-supply = <&gdsc_venus>;` /
`venus-core0-supply = <&gdsc_venus_core0>;`.

**Target.** The port's GDSCs are **genpd providers**, not regulators. The GCC
driver registers them here:

```c
/* drivers/clk/qcom/gdsc.c:497 */
	ret = pm_genpd_init(&sc->pd, NULL, !on);
...
/* drivers/clk/qcom/gdsc.c:576-583 */
		if (scs[i]->parent)
			ret = pm_genpd_add_subdomain(scs[i]->parent, &scs[i]->pd);
		else if (!IS_ERR_OR_NULL(dev->pm_domain))
			ret = pm_genpd_add_subdomain(pd_to_genpd(dev->pm_domain), &scs[i]->pd);
...
	return of_genpd_add_provider_onecell(dev->of_node, data);
```

and the msm8953 GDSCs are declared in
`drivers/clk/qcom/gcc-msm8953.c:3863` (`venus_gdsc`) and `:3873`
(`venus_core0_gdsc`).

The port's Venus node already uses the genpd form:

```dts
/* arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-venus.dtsi:39,45 */
		power-domains = <&gcc VENUS_GDSC>;
...
			power-domains = <&gcc VENUS_CORE0_GDSC>;
```

and the upstream Venus driver attaches them with the genpd list helper:

```c
/* drivers/media/platform/qcom/venus/pm_helpers.c:864-880 */
static int vcodec_domains_get(struct venus_core *core)
{
	struct device **opp_virt_dev;
	struct device *dev = core->dev;
	const struct venus_resources *res = core->res;
	struct dev_pm_domain_attach_data vcodec_data = {
		.pd_names = res->vcodec_pmdomains,
		.num_pd_names = res->vcodec_pmdomains_num,
		.pd_flags = PD_FLAG_NO_DEV_LINK,
	};

	if (!res->vcodec_pmdomains_num)
		goto skip_pmdomains;

	ret = devm_pm_domain_attach_list(dev, &vcodec_data, &core->pmdomains);
	if (ret < 0)
		return ret;
```

plus `devm_pm_opp_attach_genpd()` at `pm_helpers.c:888` and
`dev_pm_genpd_set_hwmode()` at `pm_helpers.c:416`.

**Conclusion:** the donor's `devm_regulator_get(dev, "venus-supply")` +
`regulator_enable()/disable()` must become
`devm_pm_domain_attach_list()` (or `dev_pm_domain_attach_by_name()`) +
`pm_runtime_get_sync()/put_sync()`. There is **no regulator device** behind
the port's GDSCs, so the donor code as written cannot work: `devm_regulator_get()`
would return `-EPROBE_DEFER`/`-ENODEV`.

### 4.3 `scm_call` → the port's `soc/qcom/scm.h` shim

The target has a purpose-built compat shim at `include/soc/qcom/scm.h`
(196 lines). It provides the exact legacy surface the donor uses:

* `include/soc/qcom/scm.h:39-54` — `SCM_SVC_BOOT`, `SCM_SVC_MP`, … (same values
  as the donor).
* `include/soc/qcom/scm.h:56` — `SCM_SIP_FNID(s, c)` = `(((s)&0xFF)<<8)|((c)&0xFF)|0x02000000`,
  identical to the donor.
* `include/soc/qcom/scm.h:84` — `SCM_ARGS(...)`, identical encoding.
* `include/soc/qcom/scm.h:125-129` — `struct scm_desc { u32 arginfo; u64 args[MAX_SCM_ARGS]; u64 ret[MAX_SCM_RETS]; }`,
  identical layout to the donor's `struct scm_desc`.
* `include/soc/qcom/scm.h:167-171` — `static inline int scm_call2(u32 smc_id, struct scm_desc *desc)`,
  same signature as the donor's.

The donor's two `scm_call2()` sites therefore port unchanged:

```c
/* donor venus_hfi.c:1024-1032 */
	struct scm_desc desc = {0};
	desc.args[0] = cmd.state = state;
	desc.args[1] = cmd.spare = 0;
	desc.arginfo = SCM_ARGS(2);
	rc = scm_call2(SCM_SIP_FNID(SCM_SVC_BOOT, TZBSP_VIDEO_SET_STATE), &desc);
	tzbsp_rsp = desc.ret[0];
```
```c
/* donor venus_hfi.c:3944-3947 */
	desc.arginfo = SCM_ARGS(4);
	rc = scm_call2(SCM_SIP_FNID(SCM_SVC_MP, TZBSP_MEM_PROTECT_VIDEO_VAR), &desc);
```

The shim's transport is `__scm_smc_call_legacy()` (`include/soc/qcom/scm.h:116`,
implemented in the port's qseecom/secure-world path), and the modern
`qcom_scm_*` helpers listed in §4.1 are the better route for the two calls
above (`qcom_scm_pas_auth_and_reset`, `qcom_scm_mem_protect_video_var`).

### 4.4 `pm_qos_add_request` → `cpu_latency_qos_add_request`

The 6.12 tree **removed** the per-class `pm_qos_add_request()` API. The target's
`include/linux/pm_qos.h` only offers the CPU-latency class:

```c
include/linux/pm_qos.h:150:void cpu_latency_qos_add_request(struct pm_qos_request *req, s32 value);
include/linux/pm_qos.h:151:void cpu_latency_qos_update_request(struct pm_qos_request *req, s32 new_value);
include/linux/pm_qos.h:152:void cpu_latency_qos_remove_request(struct pm_qos_request *req);
```

(the donor's `include/linux/pm_qos.h:144-150` still has
`pm_qos_add_request(struct pm_qos_request *, int pm_qos_class, s32 value)`).

The donor's four call sites are all `PM_QOS_CPU_DMA_LATENCY`, i.e. exactly the
class the CPU-latency API serves:

```
donor venus_hfi.c:2157:		pm_qos_add_request(&dev->qos, PM_QOS_CPU_DMA_LATENCY, ...)
donor venus_hfi.c:2185:		pm_qos_remove_request(&device->qos);
donor venus_hfi.c:4212:		pm_qos_remove_request(&device->qos);
donor venus_hfi.c:4281:		pm_qos_add_request(&device->qos, PM_QOS_CPU_DMA_LATENCY, ...)
```

So the mechanical translation is
`pm_qos_add_request(&q, PM_QOS_CPU_DMA_LATENCY, v)` →
`cpu_latency_qos_add_request(&q, v)`,
`pm_qos_remove_request(&q)` → `cpu_latency_qos_remove_request(&q)`.
The `PM_QOS_CPU_DMA_LATENCY` class value in the donor is 6; the CPU-latency
QoS in 6.12 is a different (dedicated) node, so the *numeric* latency value
(213 µs from the DT `qcom,pm-qos-latency-us`) is what must be preserved, not
the class id.

### 4.5 `msm_bus_scale_*` → the port's `include/linux/msm-bus.h` shim

The port already has the shim: `include/linux/msm-bus.h` (76 lines), with the
full donor prototype set:

```c
include/linux/msm-bus.h:52: struct msm_bus_scale_pdata *msm_bus_pdata_from_node(
include/linux/msm-bus.h:53:		struct platform_device *pdev, struct device_node *node);
include/linux/msm-bus.h:56: uint32_t msm_bus_scale_register_client(
include/linux/msm-bus.h:57:		struct msm_bus_scale_pdata *pdata);
include/linux/msm-bus.h:58: int msm_bus_scale_client_update_request(uint32_t cl, unsigned int index);
include/linux/msm-bus.h:59: int msm_bus_scale_client_update_context(uint32_t cl, bool active_only,
include/linux/msm-bus.h:62: void msm_bus_scale_unregister_client(uint32_t cl);
```

Implementation: `drivers/gpu/msm/msm-bus-compat.c`. The important behavioural
note for the port:

```c
/* drivers/gpu/msm/msm-bus-compat.c:177-204 */
int msm_bus_scale_client_update_request(uint32_t cl, unsigned int index)
{
	...
	if (!cl || cl > MAX_CLIENTS)
		return -EINVAL;
	pdata = clients[cl - 1];
	if (!pdata)
		return -EINVAL;
	if (index >= pdata->num_usecases)
		return -EINVAL;
	if (!bus_path)
		return 0;                       /* no ICC path -> success, no-op */
	return icc_set_bw(bus_path, ...);
}
```

So the donor's `vmem/vmem.c:175,206,223` calls
(`msm_bus_scale_client_update_request(v->bus.priv, 1/0)`) will succeed as a
no-op even though the port has no Venus ICC path — i.e. **the bus vote will be
silently dropped**, which is a performance (not functional) difference.

### 4.6 ION

The port has ION: `drivers/staging/android/ion/` (20 files incl. `msm/msm_ion_of.c`).
Config (`out/.config`):

```
6251:CONFIG_ION=y
6252:CONFIG_ION_LEGACY=y
6253:CONFIG_ION_SYSTEM_HEAP=y
6254:# CONFIG_ION_CARVEOUT_HEAP is not set
6255:# CONFIG_ION_CHUNK_HEAP is not set
6256:CONFIG_ION_CMA_HEAP=y
```

The kernel-side allocation API the donor uses is available with the **same
signature**:

```c
/* drivers/staging/android/ion/ion_kernel.h (target) */
struct dma_buf *ion_alloc(size_t len, unsigned int heap_id_mask,
			  unsigned int flags);
```

reached from `include/linux/ion_kernel.h`, which forwards to
`../../drivers/staging/android/ion/ion_kernel.h`.

But the donor's `msm_smem.c:20` includes **`<linux/msm_ion.h>`**, which does not
exist in the target. In the donor this is a *build-time symlink*:
`include/uapi/linux/msm_ion.h -> ../../../drivers/staging/android/uapi/msm_ion.h`
(the donor's `gen_headers_arm64.bp:382` lists `"linux/msm_ion.h"` among the
headers the Qualcomm build symlinks into `include/linux/`). The target already
has `include/uapi/linux/msm_ion.h` as a **regular file** whose only difference
from the donor's is the SPDX line (`WITH Linux-syscall-note` added), so the
port only needs either the same symlink or
`#include <uapi/linux/msm_ion.h>`.

The actual `ion_alloc()` declaration comes from the donor's `msm_smem.c:21`
`#include <linux/ion_kernel.h>`, which exists in the target with the identical
`ion_alloc()` signature.

The heap ids and secure flags the donor uses are present in the target's
`include/uapi/linux/msm_ion.h`:
`ION_CP_MM_HEAP_ID=8`, `ION_SECURE_HEAP_ID=9`, `ION_ADSP_HEAP_ID=22`,
`ION_SYSTEM_HEAP_ID=25`, `ION_FLAG_SECURE`, `ION_FLAG_CP_TOUCH/BITSTREAM/PIXEL`,
`ION_FLAG_CACHED` (`include/uapi/linux/ion.h:47`).

### 4.7 dma-buf API in 6.12 (`drivers/dma-buf/dma-buf.c`)

**Signatures that changed:**

| API | 4.19 (donor) | 6.12 (target) |
|---|---|---|
| `dma_buf_vmap` | `void *dma_buf_vmap(struct dma_buf *)` | `int dma_buf_vmap(struct dma_buf *, struct iosys_map *)` (`dma-buf.c:2281`) |
| `dma_buf_vunmap` | `void dma_buf_vunmap(struct dma_buf *, void *)` | `void dma_buf_vunmap(struct dma_buf *, struct iosys_map *)` (`dma-buf.c:2350`) |
| `dma_buf_begin_cpu_access` | `void` return | `int` return (`dma-buf.c:2115`) |
| `dma_buf_map_attachment` | no dma_resv lock requirement | **dma_resv lock must be held** |

**Locking rules the caller must follow in 6.12** (quoted):

```c
/* include/linux/dma-buf.h:597-598 */
/* @importer_ops: importer operations for this attachment, if provided
 * dma_buf_map/unmap_attachment() must be called with the dma_resv lock held. */
```

```c
/* drivers/dma-buf/dma-buf.c:1927-1946 */
void dma_buf_unmap_attachment(struct dma_buf_attachment *attach,
				struct sg_table *sg_table,
				enum dma_data_direction direction)
{
	might_sleep();

	if (WARN_ON(!attach || !attach->dmabuf || !sg_table))
		return;

	dma_resv_assert_held(attach->dmabuf->resv);
	...
}
```

```c
/* drivers/dma-buf/dma-buf.c:2291 (dma_buf_vmap) */
	dma_resv_assert_held(dmabuf->resv);
...
/* drivers/dma-buf/dma-buf.c:2355 (dma_buf_vunmap) */
	dma_resv_assert_held(dmabuf->resv);
```

There are `_unlocked` wrappers that take the lock themselves:
`dma_buf_map_attachment_unlocked()` (`dma-buf.c:1898`),
`dma_buf_unmap_attachment_unlocked()` (`dma-buf.c:1959`),
`dma_buf_vmap_unlocked()` (`dma-buf.c:2328`),
`dma_buf_vunmap_unlocked()` (`dma-buf.c:2374`).

`dma_buf_begin_cpu_access()` / `dma_buf_end_cpu_access()` do **not** need the
resv lock, but they now *wait on fences*:

```c
/* drivers/dma-buf/dma-buf.c:2079-2094 */
static int __dma_buf_begin_cpu_access(struct dma_buf *dmabuf,
				      enum dma_data_direction direction)
{
	...
	ret = dma_resv_wait_timeout(resv, dma_resv_usage_rw(write),
				    true, MAX_SCHEDULE_TIMEOUT);
```

**The donor's `msm_smem.c` violates all of the above:**

```c
/* donor msm_smem.c:68-98 */
		attach = dma_buf_attach(dbuf, cb->dev);
		...
		attach->dma_map_attrs = DMA_ATTR_DELAYED_UNMAP;   /* :79  -- macro GONE in 6.12 */
		attach->dma_map_attrs |= DMA_ATTR_SKIP_CPU_SYNC;  /* :86  -- still exists */
		...
		table = dma_buf_map_attachment(attach, DMA_BIDIRECTIONAL);  /* :93 -- needs dma_resv lock */
```

```c
/* donor msm_smem.c:478-496 */
		dma_buf_begin_cpu_access(dbuf, DMA_BIDIRECTIONAL);
		mem->kvaddr = dma_buf_vmap(dbuf);               /* :479 -- signature changed */
...
		dma_buf_end_cpu_access(dbuf, DMA_BIDIRECTIONAL);
```

```c
/* donor msm_smem.c:517 */
		dma_buf_vunmap(mem->dma_buf, mem->kvaddr);       /* :517 -- signature changed */
```

Also `DMA_ATTR_DELAYED_UNMAP` and `DMA_ATTR_IOMMU_USE_UPSTREAM_HINT` **do not
exist** in the target's `include/linux/dma-mapping.h` (only
`DMA_ATTR_SKIP_CPU_SYNC` at `:37` is present); they were removed upstream in
6.6.

### 4.8 The 6.12 videobuf2 API surface used by CAF

All of the following exist unchanged in the target:

| Symbol | Target location |
|---|---|
| `struct vb2_ops` | `include/media/videobuf2-core.h:434` |
| `vb2_ops.wait_prepare` / `.wait_finish` | `include/media/videobuf2-core.h:439-440` (helper `vb2_ops_wait_prepare()` in `include/media/videobuf2-v4l2.h:380`) |
| `vb2_queue.buf_struct_size` | `include/media/videobuf2-core.h:637` |
| `vb2_queue.mem_ops` / `.drv_priv` / `.allow_zero_bytesused` / `.timestamp_flags` | `videobuf2-core.h:632,635,619,638` |
| `vb2_queue_init()` | `drivers/media/common/videobuf2/videobuf2-v4l2.c:956` |
| `vb2_queue_release()` | `include/media/videobuf2-v4l2.h:259` (impl `videobuf2-v4l2.c:962`) |
| `VB2_MMAP` / `VB2_USERPTR` | `videobuf2-core.h:205-206` |
| `vb2_ops.queue_setup/.start_streaming/.buf_queue/.stop_streaming` | all present |

**One API break:** `struct vb2_mem_ops.get_userptr` changed signature.

* 4.19 (donor `include/media/videobuf2-core.h:124-127`):
  ```c
  	void		*(*get_userptr)(struct device *dev, unsigned long vaddr,
  					unsigned long size,
  					enum dma_data_direction dma_dir);
  ```
* 6.12 (target `include/media/videobuf2-core.h:127-130`):
  ```c
  	void		*(*get_userptr)(struct vb2_buffer *vb,
  					struct device *dev,
  					unsigned long vaddr,
  					unsigned long size);
  ```

The donor's implementation (donor `msm_vidc.c:1113-1128`) matches the 4.19
signature and therefore **will not compile** against 6.12:

```c
static void *vidc_get_userptr(struct device *dev, unsigned long vaddr,
			unsigned long size, enum dma_data_direction dma_dir)
{
	return (void *)0xdeadbeef;
}
static void vidc_put_userptr(void *buf_priv) { }
static const struct vb2_mem_ops msm_vidc_vb2_mem_ops = {
	.get_userptr = vidc_get_userptr,
	.put_userptr = vidc_put_userptr,
};
```

### 4.9 Does 6.12's vb2 mask or reject unknown buffer flags?

**It masks them (silently), and for `0x00800000` it actively misinterprets them.**

The mask is `V4L2_BUFFER_MASK_FLAGS` (quoted in §3.2). It is applied in two
places:

* user → kernel (`__fill_vb2_buffer`): `vbuf->flags = b->flags & ~V4L2_BUFFER_MASK_FLAGS;`
  (`drivers/media/common/videobuf2/videobuf2-v4l2.c:320`);
* kernel → user (`__fill_v4l2_buffer`): `b->flags &= ~V4L2_BUFFER_MASK_FLAGS;`
  (`videobuf2-v4l2.c:548`).

**There is no rejection of unknown flags** — no `WARN_ON(b->flags & ~known)`.
So unknown CAF bits survive, *except* the ones that collide with a 6.12-owned
bit.

**Which CAF buffer flags would be dropped:**

| CAF flag | value | dropped? | where |
|---|---|---|---|
| `V4L2_QCOM_BUF_DROP_FRAME` | 0x00800000 | **yes** | `V4L2_BUF_FLAG_REQUEST_FD` ∈ `V4L2_BUFFER_MASK_FLAGS` → cleared at `videobuf2-v4l2.c:320` and `:548`; and on QBUF it is *interpreted* as a media request (`:396-399`, `:416-428`) → `-EINVAL`/`-EBADR` |
| `V4L2_QCOM_BUF_END_OF_SUBFRAME` / `V4L2_BUF_FLAG_END_OF_SUBFRAME` | 0x00000080 | **yes** | `V4L2_BUF_FLAG_IN_REQUEST` ∈ `V4L2_BUFFER_MASK_FLAGS` → cleared at `:320` and `:548` |
| `V4L2_MSM_BUF_FLAG_MBAFF` | 0x00000200 | **yes** (capture queues) | `V4L2_BUF_FLAG_M2M_HOLD_CAPTURE_BUF` ∈ `V4L2_BUFFER_OUT_FLAGS` → cleared at `videobuf2-v4l2.c:343` |
| `V4L2_QCOM_BUF_FLAG_EOSEQ` | 0x00040000 | **yes** (capture / non-COPY timestamps) | inside `V4L2_BUF_FLAG_TSTAMP_SRC_MASK` → cleared at `videobuf2-v4l2.c:327`. *Identical in the 4.19 donor (`videobuf2-v4l2.c:425`) — not a regression.* |
| `V4L2_QCOM_BUF_FLAG_DECODEONLY` | 0x00200000 | no | free in 6.12 |
| `V4L2_QCOM_BUF_FLAG_CODECCONFIG` | 0x00020000 | no | free in 6.12 |
| `V4L2_QCOM_BUF_FLAG_EOS` | 0x02000000 | no | free in 6.12 |
| `V4L2_QCOM_BUF_FLAG_READONLY` | 0x04000000 | no | free in 6.12 |
| `V4L2_QCOM_BUF_FLAG_PERF_MODE` | 0x20000000 | no | free in 6.12 |
| `V4L2_QCOM_BUF_FLAG_IDRFRAME` | 0x80000000 | no | free in 6.12 |
| `V4L2_QCOM_BUF_TIMESTAMP_INVALID` | 0x00080000 | no | free in 6.12 |
| `V4L2_QCOM_BUF_INPUT_UNSUPPORTED` | 0x01000000 | no | free in 6.12 |
| `V4L2_MSM_BUF_FLAG_YUV_601_709_CLAMP` | 0x10000000 | no | free in 6.12 |
| `V4L2_MSM_BUF_FLAG_DEFER` | 0x40000000 | no | free in 6.12 |
| `V4L2_MSM_VIDC_BUF_START_CODE_NOT_FOUND` | 0x08000000 | no | free in 6.12 |

Note that 6.12's `__fill_vb2_buffer` also has two extra behaviours the donor
does not have:
```c
339:		if (!(q->subsystem_flags & VB2_V4L2_FL_SUPPORTS_M2M_HOLD_CAPTURE_BUF))
340:			vbuf->flags &= ~V4L2_BUF_FLAG_M2M_HOLD_CAPTURE_BUF;
```
and the `copy_timestamp`/`TSTAMP_SRC_MASK` rule at `:321-327` now keys on
`V4L2_TYPE_IS_CAPTURE(b->type)` instead of `!V4L2_TYPE_IS_OUTPUT(b->type)`.

### 4.10 The 32-bit compat ioctl path

**Target file:** `drivers/media/v4l2-core/v4l2-compat-ioctl32.c` (1210 lines).
Structure (all in the target tree):

* `:860-871` — the 32-bit ioctl numbers:
  ```c
  #define VIDIOC_S_EXT_CTRLS32    _IOWR('V', 72, struct v4l2_ext_controls32)
  #define VIDIOC_TRY_EXT_CTRLS32  _IOWR('V', 73, struct v4l2_ext_controls32)
  #define	VIDIOC_DQEVENT32	_IOR ('V', 89, struct v4l2_event32)
  #define VIDIOC_CREATE_BUFS32	_IOWR('V', 92, struct v4l2_create_buffers32)
  #define VIDIOC_PREPARE_BUF32	_IOWR('V', 93, struct v4l2_buffer32)
  #ifdef CONFIG_COMPAT_32BIT_TIME
  #define VIDIOC_QUERYBUF32_TIME32	_IOWR('V',  9, struct v4l2_buffer32_time32)
  #define VIDIOC_QBUF32_TIME32		_IOWR('V', 15, struct v4l2_buffer32_time32)
  #define VIDIOC_DQBUF32_TIME32		_IOWR('V', 17, struct v4l2_buffer32_time32)
  #define	VIDIOC_DQEVENT32_TIME32		_IOR ('V', 89, struct v4l2_event32_time32)
  #define VIDIOC_PREPARE_BUF32_TIME32	_IOWR('V', 93, struct v4l2_buffer32_time32)
  #endif
  ```
* `:874-931` — `v4l2_compat_translate_cmd()`: maps the 32-bit command to the
  native one (`VIDIOC_G_FMT32`→`VIDIOC_G_FMT`, `VIDIOC_S_FMT32`→`VIDIOC_S_FMT`,
  `VIDIOC_TRY_FMT32`, `VIDIOC_G_FBUF32`, `VIDIOC_S_FBUF32`,
  `VIDIOC_QUERYBUF32[_TIME32]`, `VIDIOC_QBUF32[_TIME32]`,
  `VIDIOC_DQBUF32[_TIME32]`, `VIDIOC_PREPARE_BUF32[_TIME32]`,
  `VIDIOC_CREATE_BUFS32`, `VIDIOC_G/S/TRY_EXT_CTRLS32`,
  `VIDIOC_ENUMSTD32`, `VIDIOC_ENUMINPUT32`, `VIDIOC_G_EDID32`,
  `VIDIOC_S_EDID32`, `VIDIOC_DQEVENT32` (only `#ifdef CONFIG_X86_64`),
  `VIDIOC_DQEVENT32_TIME32`).
* `:933-975` — `v4l2_compat_get_user()`: the per-command *copy-in* helpers
  (`get_v4l2_format32`, `get_v4l2_framebuffer32`, `get_v4l2_buffer32`,
  `get_v4l2_buffer32_time32`, `get_v4l2_ext_controls32`, `get_v4l2_create32`,
  `get_v4l2_standard32`, `get_v4l2_input32`, `get_v4l2_edid32`).
* `:977-1030` — `v4l2_compat_put_user()`: the matching *copy-out* helpers.
* `:1029-1100` — `v4l2_compat_get_array_args()`: the *array* copy-in for
  multi-plane buffers and extended controls.
* `:1101-1178` — `v4l2_compat_put_array_args()`: the matching copy-out.
* `:1188-1209` — `v4l2_compat_ioctl32()` itself:
  ```c
  1199:	if (_IOC_TYPE(cmd) == 'V' && _IOC_NR(cmd) < BASE_VIDIOC_PRIVATE)
  1200:		ret = file->f_op->unlocked_ioctl(file, cmd,
  1201:					(unsigned long)compat_ptr(arg));
  1202:	else if (vdev->fops->compat_ioctl32)
  1203:		ret = vdev->fops->compat_ioctl32(file, cmd, arg);
  ```

**Important structural difference from the 4.19 donor:** 6.12 has **no
`do_video_ioctl()`** any more. The 32→64 conversion is driven from the *core*
ioctl layer instead, `drivers/media/v4l2-core/v4l2-ioctl.c`:

```c
/* v4l2-ioctl.c:3239-3259 */
static unsigned int video_translate_cmd(unsigned int cmd)
{
	...
	if (in_compat_syscall())
		return v4l2_compat_translate_cmd(cmd);

	return cmd;
}

/* v4l2-ioctl.c:3289-3294 */
	if (cmd == real_cmd) {
		if (copy_from_user(parg, (void __user *)arg, n))
			err = -EFAULT;
	} else if (in_compat_syscall()) {
		memset(parg, 0, n);
		err = v4l2_compat_get_user(arg, parg, cmd);
```

with the array helpers called from `v4l2-ioctl.c:3452`
(`v4l2_compat_get_array_args()`) and `v4l2-ioctl.c:3499`
(`v4l2_compat_put_array_args()`). The four public entry points are declared in
`include/media/v4l2-ioctl.h:693-699`.

**Donor CAF changes to that file** (all three named commits exist in the donor
repo; verified with `git show`):

1. **`e3552920188036f3fe1d6b9a430fad7aec3b43b1`** — "media: v4l2-core: 32 bit
   to 64 bit v4l2-compat changes" (Shivendra Kakrania, 2018-03-06,
   `drivers/media/v4l2-core/v4l2-compat-ioctl32.c | 10 ++++++++--`):
   adds `reserved` and `length` to the plane copy in/out:

   ```diff
   	if (copy_in_user(p64, p32, 2 * sizeof(__u32)) ||
   	    copy_in_user(&p64->data_offset, &p32->data_offset,
   			 sizeof(p64->data_offset)))
   +		return -EFAULT;
   +	}
   +
   +	if (copy_in_user(p64, p32, 2 * sizeof(__u32)) ||
   +	    copy_in_user(&p64->data_offset, &p32->data_offset,
   +			 sizeof(p64->data_offset)) ||
   +	    copy_in_user(p64->reserved, p32->reserved,
   +			 sizeof(p64->reserved)) ||
   +	    copy_in_user(&p64->length, &p32->length,
   +			 sizeof(p64->length)))
   		return -EFAULT;
   ```

   **In 6.12 this is already handled** — the target's
   `get_v4l2_plane32()` (`v4l2-compat-ioctl32.c:334-366`) copies the whole
   struct by value:
   ```c
   357:	memset(p64, 0, sizeof(*p64));
   358:	*p64 = (struct v4l2_plane) {
   359:		.bytesused	= plane32.bytesused,
   360:		.length		= plane32.length,
   361:		.m		= m,
   362:		.data_offset	= plane32.data_offset,
   363:	};
   ```
   and `put_v4l2_plane32()` (`:368-398`) does the reverse. **No porting
   needed.**

2. **`2ea36671164e37cd9e853d6321550baa00339254`** — "media: v4l2-core: compat:
   ignore native command codes" (Arnd Bergmann, 2019-12-16; upstream
   `4a873f3fa5d6ca52e446d306dd7194dd86a09422`). It changes `do_video_ioctl()`
   to compute a separate `ncmd` and use it only for the *native* handler,
   keeping the original `cmd` for deciding the conversion:
   ```diff
   -	case VIDIOC_G_FMT32: cmd = VIDIOC_G_FMT; break;
   +	case VIDIOC_G_FMT32: ncmd = VIDIOC_G_FMT; break;
   ...
   +	default: ncmd = cmd; break;
   ...
   -		err = native_ioctl(file, cmd, (unsigned long)p32);
   +		err = native_ioctl(file, ncmd, (unsigned long)p32);
   ```
   and switches the "which conversion" cases from the native names to the
   `*32` names (`VIDIOC_OVERLAY` → `VIDIOC_OVERLAY32`, …).
   **6.12 already has the equivalent**, expressed differently: the target
   splits the work into `v4l2_compat_translate_cmd()` (compat file `:874`),
   `v4l2_compat_get_user()` (`:933`) and `v4l2_compat_put_user()` (`:977`),
   and the core's `video_translate_cmd()` (`v4l2-ioctl.c:3239`) keys the
   conversion decision on the **32-bit** command number. **No porting
   needed.**

3. **`17f07c01bc8464ac9b05db1bd55100ef4c17c85b`** — "media: v4l2: Allow ioctl
   type of 'U' for video devices like usb camera" (Zhou Guo, 2021-11-15):
   ```diff
   -	if (_IOC_TYPE(cmd) == 'V' && _IOC_NR(cmd) < BASE_VIDIOC_PRIVATE)
   +	if (((_IOC_TYPE(cmd) == 'V') || (_IOC_TYPE(cmd) == 'U')) &&
   +		_IOC_NR(cmd) < BASE_VIDIOC_PRIVATE)
   		ret = do_video_ioctl(file, cmd, arg);
   ```
   **Not present in 6.12** (target `:1199` still tests only `'V'`), but it is
   only needed for the UVC *gadget*, which this port does not use. **No
   porting needed for vidc_3x.**

**Net conclusion for the compat path:** the target's 6.12 compat layer is
strictly newer than the donor's; the three CAF/upstream patches to it are
already subsumed. vidc_3x defines no private ioctl of its own (the donor's
`VIDIOC_VIDEO_CMD` lives in `msm_vidc_private.h` and is a **CVP** ioctl,
not used by vidc_3x), so **no change to `v4l2-compat-ioctl32.c` is required**.

The one thing that *does* need attention: the CAF control IDs
`0x00992000+` are above `BASE_VIDIOC_PRIVATE`? No — they are *control* IDs,
not ioctl numbers, and `VIDIOC_G_EXT_CTRLS32` copies `struct v4l2_ext_controls32`
which contains the CID array verbatim, so the 32-bit path carries the CAF CIDs
unchanged. Good.

### 4.11 Per-context-bank iommus

**Donor model.** The vidc node has four `qcom,msm-vidc,context-bank` children,
each with its own `iommus` list. The driver creates a platform device for each
of them with `of_platform_populate()` (donor `msm_v4l2_vidc.c:642`) and the
matching probe (`msm_v4l2_vidc.c:677-680`, `:699-702`) fills the
`context_bank_info` list. Each context bank then gets its **own IOMMU domain**:

```c
/* donor msm_vidc_res_parse.c:1378-1411 */
static int msm_vidc_setup_context_bank(struct context_bank_info *cb,
		struct device *dev)
{
	...
	cb->dev = dev;
	bus = cb->dev->bus;
	...
	cb->domain = iommu_get_domain_for_dev(cb->dev);
	...
	if (!dev->dma_parms)
		dev->dma_parms =
			devm_kzalloc(dev, sizeof(*dev->dma_parms), GFP_KERNEL);
	dma_set_max_seg_size(dev, DMA_BIT_MASK(32));
	dma_set_seg_boundary(dev, (unsigned long)DMA_BIT_MASK(64));
```

and the driver then attaches each dmabuf to the *bank's* device
(`msm_smem.c:68  attach = dma_buf_attach(dbuf, cb->dev);`), which is what
makes each bank have its own SMMU context (and its own VMID for the secure
banks).

**Target model (the port's mdss).** The port already implements exactly this
pattern for the display:

```c
/* drivers/video/fbdev/msm/mdss_smmu.c:687-710 */
/*
 * mdss_smmu_device_create()
 * @dev: mdss_mdp device
 *
 * For smmu_v2, each context bank is a separate child device of mdss_mdp.
 * Platform devices are created for those smmu related child devices of
 * mdss_mdp here. This would facilitate probes to happen for these devices in
 * which the smmu mapping and initialization is handled.
 */
void mdss_smmu_device_create(struct device *dev)
{
	struct device_node *parent, *child;
	struct msm_smmu_private *prv = mdss_smmu_get_private();

	parent = dev->of_node;
	for_each_child_of_node(parent, child) {
		char name[MDSS_SMMU_COMPAT_STR_LEN] = {};

		strscpy(name, child->name, sizeof(name));
		if (is_mdss_smmu_compatible_device(name))
			of_platform_device_create(child, NULL, dev);
	}
	prv->pdev = parent;
}
```

i.e. the same "one child platform device per SMMU context bank, each with its
own `iommus`" mechanism, and each child then gets its own
`iommu_get_domain_for_dev()` (`mdss_smmu.c:849`) and its own fault handler
(`mdss_smmu.c:868`).

**Target model (upstream Venus).** The upstream 6.12 Venus driver does *not*
use per-context-bank child devices; it uses a **single** `iommus` on the Venus
node (`iommus = <&apps_iommu 0x16>;` in
`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-venus.dtsi:37`) and one
`iommu_domain` for both the decoder and the encoder children.

**Conclusion:** if the port wants the donor's four-bank model (non-secure +
3 secure, each with its own VMID), the mdss pattern above is the in-tree
blueprint to copy; the upstream-Venus single-bank model is a different
hardware contract (no secure buffers) and does not give the donor's
`qcom,secure-context-bank` / `qcom,iommu-vmid` behaviour.
The port's DTS already has a "VENUS_NS" SMMU context bank (`iommu-ctx@16000`
per the comment in `msm8953-xiaomi-tissot-venus.dtsi:9`), and the donor's
`msm8953-vidc.dtsi` wants `0x800`+ (`apps_iommu 0x800 0x01`) for the
non-secure bank and `0x900`+ / `0x904`+ / `0x908`+ for the three secure banks.
**Those context-bank numbers must be reconciled with what the msm8953 SMMU
actually implements** — this is a hardware/DT question that this research does
not answer.

---

## 5. IMPORT RISK LIST — 20 most likely failures

Ordered roughly by "will definitely break the build" first.

| # | Donor file:line | What breaks | Why / what to do |
|---:|---|---|---|
| 1 | `msm_smem.c:479` and `:517` | `dma_buf_vmap(dbuf)` / `dma_buf_vunmap(buf, ptr)` | 6.12 changed the API to `int dma_buf_vmap(struct dma_buf *, struct iosys_map *)` (`drivers/dma-buf/dma-buf.c:2281`) and `void dma_buf_vunmap(struct dma_buf *, struct iosys_map *)` (`:2350`). Must switch to `struct iosys_map`. |
| 2 | `msm_smem.c:79` | `attach->dma_map_attrs = DMA_ATTR_DELAYED_UNMAP;` | `DMA_ATTR_DELAYED_UNMAP` was removed upstream; the target's `include/linux/dma-mapping.h` only has `DMA_ATTR_SKIP_CPU_SYNC` (`:37`). Also `DMA_ATTR_IOMMU_USE_UPSTREAM_HINT` (donor `msm_smem.c:90`, commented out) is gone. |
| 3 | `msm_smem.c:93`, `:128`, `:156` | `dma_buf_map_attachment()` / `dma_buf_unmap_attachment()` without the resv lock | 6.12 requires the dma_resv lock: `include/linux/dma-buf.h:597-598` and `dma_resv_assert_held()` in `dma-buf.c:1936`. Use `dma_buf_map_attachment_unlocked()` / `dma_buf_unmap_attachment_unlocked()` (`dma-buf.c:1898`, `:1959`) or take the lock explicitly. |
| 4 | `msm_smem.c:478`, `:496`, `:519` | `dma_buf_begin_cpu_access()` / `dma_buf_end_cpu_access()` return type | 6.12 returns `int` (`dma-buf.c:2115`, `:2175`) and now blocks on fences (`:2088`). The donor ignores the return; the port should check it. |
| 5 | `msm_vidc.c:1113-1128` | `struct vb2_mem_ops.get_userptr` prototype | 4.19: `(dev, vaddr, size, dma_dir)`; 6.12: `(vb, dev, vaddr, size)` (`include/media/videobuf2-core.h:127`). The donor's `vidc_get_userptr()` will not compile. |
| 6 | `msm_vidc_common.h:74` (`IS_PRIV_CTRL`) and `v4l2-controls.h:787` (`V4L2_CID_MPEG_MSM_VIDC_BASE`) | `V4L2_CTRL_CLASS_MPEG` is undefined in 6.12 kernel code | target `include/uapi/linux/v4l2-controls.h:3504-3510` defines it only `#ifndef __KERNEL__`. Must use `V4L2_CTRL_CLASS_CODEC` (same value 0x00990000). |
| 7 | `venus_hfi.c:2157`, `:2185`, `:4212`, `:4281` | `pm_qos_add_request()` / `pm_qos_remove_request()` | Removed in 6.12; use `cpu_latency_qos_add_request()` / `..._remove_request()` (`include/linux/pm_qos.h:150-152`). |
| 8 | `venus_boot.c:440` | `ioremap_nocache()` | Not present anywhere in the target tree (removed upstream in 6.5). Use `devm_ioremap()` (`include/linux/io.h:68`). |
| 9 | `venus_boot.c:33-34`, `:449`, `:468` | `<soc/qcom/subsystem_notif.h>` / `<soc/qcom/subsystem_restart.h>`, `subsys_notif_register_notifier()` | Not in `include/soc/qcom/`; the only copy is the audio driver's `sound/soc/msm/caf-include/soc/qcom/subsystem_notif.h` and there is **no implementation** of the API in the target. Replace with the upstream-Venus power model (§4.1/§4.2). |
| 10 | `venus_hfi.c:4324` | `subsystem_get_with_fwname()` / `subsystem_put()` | No such API in 6.12. Use `request_firmware()` + `qcom_mdt_load()` like `drivers/media/platform/qcom/venus/firmware.c:110-140`. |
| 11 | `venus_boot.c:376`, `:241`, `:389` | `devm_regulator_get()` / `regulator_enable()` on the GDSC | The port's GDSCs are **genpd** providers (`drivers/clk/qcom/gdsc.c:583`), not regulators; the port's Venus DT uses `power-domains = <&gcc VENUS_GDSC>`. Convert to `devm_pm_domain_attach_list()` / `pm_runtime` (§4.2). |
| 12 | `msm_smem.c:19`, `:20` | `#include <linux/msm_dma_iommu_mapping.h>` and `#include <linux/msm_ion.h>` | Neither exists in the target. `include/linux/msm_dma_iommu_mapping.h` is the CAF lazy-mapping header (`msm_dma_map_sg_attrs()` / `msm_dma_map_sg_lazy()`) and has no 6.12 equivalent — drop it (the donor does not call anything from it). `<linux/msm_ion.h>` is, in the donor, a build-time symlink to `include/uapi/linux/msm_ion.h` (see the donor's `gen_headers_arm64.bp:382`); the target has `include/uapi/linux/msm_ion.h` as a real file with the same content, so either add the symlink or include `<uapi/linux/msm_ion.h>`. **Note `msm_smem.c:21` already includes `<linux/ion_kernel.h>`, which does exist in the target and provides `ion_alloc()` — that part is fine.** |
| 13 | `hfi_response_handler.c:21` | `#include <soc/qcom/socinfo.h>` | Not in the target's `include/soc/qcom/` (only the audio copy under `sound/soc/msm/caf-include/`). The symbol is unused in vidc_3x — just drop the include. `SMEM_IMAGE_VERSION_TABLE` (donor `include/soc/qcom/socinfo.h:235`) is also needed at `hfi_response_handler.c:1975` — must be defined locally. |
| 14 | `msm_vidc_common.c:2290`, `:1988-2005`, `:2273-2296` | `V4L2_QCOM_BUF_DROP_FRAME` (0x00800000) and `V4L2_QCOM_BUF_END_OF_SUBFRAME` (0x80) | These now mean `V4L2_BUF_FLAG_REQUEST_FD` and `V4L2_BUF_FLAG_IN_REQUEST` in 6.12 and are stripped by vb2 (`videobuf2-v4l2.c:320`, `:548`); on QBUF, 0x00800000 makes the core return `-EINVAL`/`-EBADR` (`:396-399`, `:416-428`). The two flags must be **renumbered** to free bits, which is a UAPI break for the ROM's plugins — needs a decision, not a mechanical port. |
| 15 | `msm_vidc_res_parse.c:215-902` (whole DT parser) | Missing UAPI/DT support | `qcom,reg-presets`, `qcom,qdss-presets`, `qcom,clock-freq-tbl`, `qcom,dcvs-tbl`, `qcom,dcvs-limit`, `qcom,allowed-clock-rates`, `qcom,platform-version`, `qcom,capability-version`, `qcom,bus-master/slave/range-kbps`, `qcom,iommu-dma-addr-pool`, `buffer-types`, `virtual-addr-pool`, `qcom,iommu-vmid`, `qcom,secure-context-bank` — none of these properties exist in the port's DT and none are documented in 6.12 bindings. The parser is a rewrite, not a port. |
| 16 | `msm_vidc.c:83`, `:106`, `:121`, `:136`, `:173`, `:1090` | `msm_vidc_querycap`, `msm_vidc_enum_fmt`, `msm_vidc_s_fmt`, `msm_vidc_g_fmt`, `msm_vidc_s_ext_ctrl`, `msm_vidc_enum_framesizes` — the `EXPORT_SYMBOL()`ed control surface (`msm_vidc.c:104`, `:119`, `:134`, `:149`, `:186`, `:1113`) | These are exported to the CAF media stack; the 6.12 core has no users for them, and `msm_vidc_common.c:117-260` builds the control tables with `v4l2_ctrl_new_custom()`/`v4l2_ctrl_new_std()`/`v4l2_ctrl_new_std_menu()`. In 6.12 `v4l2_ctrl_new_std_menu()` **fails** for a non-standard CID (`v4l2-ctrls-core.c:2203-2213`: `qmenu` is NULL → `-EINVAL`); the donor's `IS_PRIV_CTRL` path (`v4l2_ctrl_new_custom()`, `v4l2-ctrls-core.c:2120`) is the one that still works. Keep that path and check the `WARN_ON(step)`/`WARN_ON(cfg->menu_skip_mask)` in `v4l2-ctrls-core.c:2142-2144`. |
| 17 | `msm_vidc_res_parse.c:1398-1409` | `iommu_get_domain_for_dev()` + `dev->dma_parms` + `dma_set_max_seg_size()` | 6.12 still has all three, but `dma_set_seg_boundary()` semantics changed (`DMA_BIT_MASK(64)` no longer forces a 64-bit segment boundary on arm64 with 4K/64K pages) and `dev->dma_parms` is now a `struct dma_parms` with different fields. Must be re-validated against the target's `include/linux/dma-mapping.h`. |
| 18 | `msm_smem.c:591-603` | `dma_buf_begin_cpu_access_partial()` / `dma_buf_end_cpu_access_partial()` | Present in 6.12 (`include/linux/dma-buf.h:777`, `:782`; `dma-buf.c:2139`, `:2191`) — **this one is fine**, but the *exporter* must implement `begin_cpu_access_partial`; the port's ION exporter may not. |
| 19 | `msm_vidc.c:1145`, `:1155`, `msm_vdec.c:1913`, `msm_venc.c:1987` | `q->io_modes = VB2_MMAP \| VB2_USERPTR;`, `q->mem_ops`, `q->drv_priv`, `q->allow_zero_bytesused` | All still present in 6.12 (`include/media/videobuf2-core.h:619,632,635,205-206`), but 6.12's vb2 additionally honours `q->requires_requests` / `q->uses_requests` / `q->supports_requests` (`videobuf2-v4l2.c:416-430`) — the donor's queue must not set `V4L2_BUF_FLAG_REQUEST_FD`, i.e. risk #14 again. |
| 20 | `governors/msm_vidc_dyn_gov.c` (1036 lines), `governors/msm_vidc_table_gov.c` | devfreq governor API | The donor's governors are built against CAF's `struct msm_vidc_bus_table_gov` and the CAF devfreq hooks; 6.12's `drivers/devfreq/` has a different `devfreq_governor` shape and the port has no Venus devfreq node. The `governors/` directory should be **dropped** in the first port slice (the clock rate can be set from the OPP table instead, as the port's Venus already does with `dev_pm_opp_set_rate()`). |

Additional lower-severity items that still need work (not in the top 20 but
verified):

* `msm_vidc.c:1159` and `msm_v4l2_vidc.c:50` use `struct video_device` /
  `video_devdata()`. **This one is fine**: this ACK snapshot still uses the
  pre-5.7 names (`include/media/v4l2-dev.h:266`, `:509`), so no rename is needed.
* The donor needs `include/trace/events/msm_vidc.h` (406 lines) and
  `include/trace/events/msm_vidc_events.h` (414 lines); **neither exists in the
  target** (`include/trace/events/` has no `msm_vidc*`). The driver calls 15
  distinct trace points:
  `trace_msm_smem_buffer_{dma,iommu}_op_{start,end}`,
  `trace_msm_v4l2_vidc_{open,close,fw_load,buffer_event}_{start,end}`,
  `trace_msm_vidc_common_state_change`, `trace_msm_vidc_perf_bus_vote`,
  `trace_venus_hfi_var_done`.
* `vmem/` is a separate optional Kconfig (`MSM_VIDC_VMEM`) and depends on
  `ARCH_MSM`; the port can drop it.
* `include/uapi/media/` does not exist in the target at all — the four UAPI
  headers plus `BASE_VIDIOC_PRIVATE_VIDEO` have to be added, and the header
  install/export machinery (`build.config.constants`, `abi.bzl`) has to be
  checked, otherwise the ROM's OMX plugin will not find `msm_vidc.h`.
* The donor's `msm_vidc_res_parse.c` also needs `qcom,proxy-reg-names`
  (`venus_boot.c:371`) which the port's DT does not have.

---

## 6. WHAT IS *NOT* A PROBLEM (verified, so it is not wasted work)

* `struct video_device` / `video_devdata()` — still the names used by this ACK
  snapshot (`include/media/v4l2-dev.h:266`, `:509`). No rename needed.
* `v4l2_ctrl_new_custom()`, `v4l2_ctrl_new_std()`, `v4l2_ctrl_cluster()`,
  `v4l2_ctrl_handler_init/free()`, `v4l2_ctrl_new_std_menu()` — all present
  (`include/media/v4l2-ctrls.h:671`, `:695`, `:852`, `:599`, `:721`;
  implementations `drivers/media/v4l2-core/v4l2-ctrls-core.c:2120`, `:2165`,
  `:2188`).
* `v4l2_fh_init/add/release`, `v4l2_event_queue/pending/subscribe/unsubscribe`,
  `video_register_device/unregister_device`, `v4l2_device_register/unregister`
  — all present (`include/media/v4l2-fh.h:73,122`,
  `include/media/v4l2-event.h:95,133,142,159`,
  `include/media/v4l2-dev.h:360`, `include/media/v4l2-device.h:94,146`).
* `vb2_ops` (`.queue_setup/.start_streaming/.buf_queue/.stop_streaming`),
  `vb2_ops.wait_prepare/wait_finish`, `vb2_queue.buf_struct_size`,
  `vb2_queue_init/release` — all present.
* `scm_call2()`, `struct scm_desc`, `SCM_SIP_FNID()`, `SCM_ARGS()` — provided
  by the port's `include/soc/qcom/scm.h` shim with the donor's exact semantics.
* `qcom_scm_pas_auth_and_reset()`, `qcom_scm_pas_shutdown()`,
  `qcom_scm_mem_protect_video_var()`, `qcom_scm_set_remote_state()`,
  `qcom_scm_is_available()` — present in
  `include/linux/firmware/qcom/qcom_scm.h:62,67,79,80,91`.
* `qcom_smem_get()`, `QCOM_SMEM_HOST_ANY` — present in
  `include/linux/soc/qcom/smem.h`.
* `msm_bus_scale_*`, `msm_bus_pdata_from_node()` — present in
  `include/linux/msm-bus.h` (implementation `drivers/gpu/msm/msm-bus-compat.c`).
* `ion_alloc()` with the identical signature — present in
  `drivers/staging/android/ion/ion_kernel.h` (reached via
  `include/linux/ion_kernel.h`); `CONFIG_ION=y`, `CONFIG_ION_SYSTEM_HEAP=y`,
  `CONFIG_ION_CMA_HEAP=y` in `out/.config`.
* `readl_poll_timeout()`, `readl_relaxed()`, `writel_relaxed()`,
  `of_property_read_u32_array()`, `of_platform_populate()` — all present.
* The 15 standard fourccs vidc_3x uses are present in 6.12 with identical
  values.
* The 138 `V4L2_CID_MPEG_VIDC_*` IDs collide with nothing in 6.12.
* The 13 `V4L2_EVENT_MSM_VIDC_*` events collide with nothing in 6.12.

---

## 7. OPEN QUESTIONS THIS RESEARCH DID NOT ANSWER

* Which SMMU context-bank numbers the msm8953 `apps_iommu` actually implements
  for Venus (the donor wants `0x800`/`0x900`/`0x904`/`0x908`; the port's Venus
  DT uses `0x16`). This determines whether the donor's four-bank model can be
  reproduced at all on this SoC.
* Whether the ROM's OMX/Codec2 plugins on this device use the CAF control IDs
  (0x00992000+) or the upstream stateless ones. That decides whether the CAF
  UAPI is worth carrying at all versus using the port's existing
  `drivers/media/platform/qcom/venus` stateless driver.
* The exact numeric replacement bits for `V4L2_QCOM_BUF_DROP_FRAME` (0x00800000)
  and `V4L2_QCOM_BUF_END_OF_SUBFRAME` (0x80) — the free bits in the 6.12
  buffer-flag namespace are limited and any change is a UAPI break for the
  ROM's plugins.
