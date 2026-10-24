# Plan: hardware camera (CAF camera-legacy) on tissot 6.12

**Written 2026-10-22** for an implementing session; a separate session reviews
each commit. Read `AGENTS.md`, `porting/REFERENCE-driver-forward-porting.md`
and `porting/REFERENCE-boot-testing.md` first, and use the kernel development
skill as `AGENTS.md` requires. This is the camera companion of
`2026-10-22-video-and-audio-port.md`: the same donor, the same rules, a
bigger tree.

The work happens in its own worktree (`../ack-camera`, branch `ack-camera`,
based on `main`), so the video and audio work on `main` is not disturbed.

## 0. Ground truth

The donor kernel (`../oc-test`, `oc-test-2ghz`; the phone's original boot
partition is `../ack-kgsl-artifacts/stock-boot-live.bin`, kernel
`4.19.325-cip136-…-gdf4a1f863991`) runs the **same** Evolution X Android 17
system and vendor with a working camera. The stock baseline capture is in
`porting/artifacts/snapshot60/stock-donor-baseline-20261022-001122/` (kept out
of the repository):

* `/dev/video0` … `/dev/video3` and `/dev/video32` + `/dev/video33` (the
  video codec);
* 23 `v4l2-subdev` devices;
* `mm-qcamera-daemon` reading the sensor nodes under
  `1b0c000.qcom,cci:qcom,camera@0` and `camera@1`.

The ROM's camera services are deliberately stopped in this port
(`scripts/initramfs-diag/init.c:1245-1251`): `qcamerasvr` and
`vendor.per_mgr` were crash-looping because the kernel had no camera at all.
**Nothing in the ROM is to be changed.** When the port and the donor differ,
the donor's behaviour is the specification; diff against `../oc-test`, not
against theory.

Working rule: one change per boot, a named evidence directory per run, the
evidence path in every commit body, no `Co-Authored-By` / `Assisted-by`
lines, and no build or flash unless the user asks.

## 1. What has to be ported

The donor's `techpack/camera-legacy` (CAF, 4.19): **166 files, 96 536
lines**, built by `techpack/camera-legacy/Makefile` into
`common/`, `msm.o`, `camera/`, `msm_vb2/`, `sensor/`, `pproc/`, `isp/`,
`ispif/`, and separately `jpeg_10/` (`MSMB_JPEG`), `jpeg_dma/`
(`MSM_JPEGDMA`), `fd/` (`MSM_FD`).

| donor directory | files | lines | what |
|---|---|---|---|
| `isp/` | 32 | 30 317 | the VFE (the pixel processor) |
| `sensor/` | 62 | 27 574 | the sensor framework, the CCI, the CSIPHY, the CSID, the EEPROM, the actuator, the flash |
| `pproc/` | 5 | 7 054 | the CPP (the post processor) and the VPE |
| `common/` | 8 | 4 690 | the SMMU and SOC API |
| `ispif/` | 7 | 4 276 | the ISPIF (the interface between the CSID and the VFE) |
| `jpeg_10/` | 11 | 4 380 | the JPEG hardware encoder |
| `jpeg_dma/` | 5 | 3 746 | the JPEG DMA engine |
| `fd/` | 5 | 3 303 | the face detection |
| `camera/`, `msm_vb2/`, `msm_buf_mgr/` | 6 | 2 625 | the core, the buffer manager, the vb2 |

The user space interface is 13 headers under
`techpack/camera-legacy/include/uapi/media/` (`msm_camera-legacy.h`,
`msm_camsensor_sdk-legacy.h`, `msm_cam_sensor-legacy.h`, `msmb_camera-legacy.h`,
`msmb_isp-legacy.h`, `msmb_ispif-legacy.h`, `msmb_pproc-legacy.h`,
`msmb_generic_buf_mgr-legacy.h`, `msm_fd-legacy.h`, `msm_jpeg-legacy.h`,
`msm_jpeg_dma-legacy.h`), plus `include/soc/qcom/camera2-legacy.h` and
`include/trace/events/msm_cam_legacy.h`. The daemon is compiled against
them: **every value must stay numerically identical**, so they get the same
value-diff script discipline as the video port
(`porting/tools/vidc-uapi-diff.py`).

## 2. Two findings that shape the scope

**There are no sensor drivers to port.** The donor's tree has no
OV12A10, OV13880 or S5K5E8 driver: the only occurrences of those names are
the EEPROM entries of the device tree
(`../oc-test/arch/arm64/boot/dts/vendor/qcom/mi8953/tissot/camera.dtsi`).
The sensors are configured by the ROM's daemon through the CAF `sensor_init`
subdevice (`techpack/camera-legacy/sensor/msm_sensor_init.c`,
`VIDIOC_MSM_SENSOR_INIT_CFG`), which is why the sensors are not in the device
tree. The port needs that subdevice to behave exactly as the daemon expects,
not three sensor modules.

**The CCI has to come from the donor.** The upstream
`drivers/i2c/busses/i2c-qcom-cci.c` in this tree has no MSM8953 support; the
donor's own CCI (`techpack/camera-legacy/sensor/cci/msm_cci.c`, compatible
`qcom,cci`) ships with camera-legacy and is what the camera nodes in the
donor's device tree describe.

## 3. What the port already has

* the clocks: `GCC_CAMSS_MCLK0-3`, `GCC_CAMSS_CSI0/1_*`,
  `GCC_CAMSS_CSI0/1_CSIPHY_3P_CLK`, `GCC_CAMSS_CSI_VFE0/1_CLK`,
  `GCC_CAMSS_CPP_*`, `GCC_CAMSS_JPEG0_CLK`
  (`include/dt-bindings/clock/qcom,gcc-msm8953.h`);
* the power domains: `CPP_GDSC`, `JPEG_GDSC`, `VFE0_GDSC`, `VFE1_GDSC`
  (the same header; the GCC driver implements them as genpd);
* the sensor rails, in the board file: `pm8953_l2` (cam_vdig), `pm8953_l6`
  (cam_vio), `pm8953_l17` (cam_vaf), `pm8953_l22` (cam_vana) — see
  `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts:291,306,351,361`;
* ION: `CONFIG_ION=y`, `CONFIG_ION_LEGACY=y`
  (`drivers/staging/android/ion`) — the ROM allocates through `/dev/ion`;
* the SMMU: the `apps_iommu` stream the donor's camera nodes use;
* the interconnect framework and the `msm-bus` shim, which the camera's
  bus votes convert to the way the video port did (`fe931b92a`);
* the CAF subsystem compatibility shim
  (`include/soc/qcom/msm_subsystem_compat.h`), which the camera's PIL use
  needs like the video's did.

## 4. Donor dependencies and their 6.12 replacements

| donor | 6.12 replacement |
|---|---|
| `linux/msm_dma_iommu_mapping.h`, `iommu_map_sg()`, `iommu_unmap()` (`common/cam_smmu_api.c`) | the generic dma-buf and IOMMU API; the same conversion the video port's buffers needed (`2e19d190d`). **The hardest single piece.** |
| ION: `ion_alloc()`, the heap ids, the `ion_map_iommu()` calls (39 files) | the port's ION; check every call against `drivers/staging/android/ion`, do not assume the legacy API is the same |
| `msm_bus_scale_register()` / `msm_bus_scale_update_bw()` | the `msm-bus` shim, as the video port did (`fe931b92a`) |
| `regulator_get()` on `cam_vana`/`cam_vdig`/`cam_vio`/`cam_vaf`, the CAF power sequences | the port's pm8953 regulators and the upstream regulator API; the donor's power sequence order is the specification |
| `clk_set_flags()` (the CAF retention flags) | no 6.12 equivalent; document what each flag did |
| the CAF v4l2 subdev and vb2 API | the 6.12 v4l2 core: the vb2 queue, the subdev ops, the media controller API |
| the CAF `PIL` (the processor interface loader) | the `msm_subsystem_compat` shim, as the video's PIL did (`0cb8dabd8`) |
| `$(DISABLE_CFI_CLANG) $(DISABLE_LTO_CLANG)` on the whole tree | this kernel builds with CFI and LTO on: the handler-type mismatches and the one-element arrays, the classes the video port hit in `044d3f406` and `b8123d808` |
| the CAF tracepoints | the 6.12 tracepoint macros (`__string()`, `__assign_str()`) |

## 5. The device tree

Two donor files:

* `../oc-test/arch/arm64/boot/dts/vendor/qcom/msm8953-camera.dtsi` — the SoC
  part: the CCI (`qcom,cci`) and the sensor nodes;
* `../oc-test/arch/arm64/boot/dts/vendor/qcom/mi8953/tissot/camera.dtsi` —
  the board part: the six EEPROMs (the `arc`, `ofilm` and `qtech` module
  variants), the two actuators, the LED flash and the three `qcom,camera@N`
  nodes.

The port's version goes to `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi`,
translated to this kernel's names: the port's pm8953 regulators, the port's
TLMM gpio names, the port's SMMU stream, and the power domains instead of the
donor's regulators where the hardware has them.

## 6. Sequence (each step one commit; one boot per step)

* **C0** this plan and the inventory.
* **C1** the verbatim import: the sources and the UAPI headers, not built
  yet — a reviewable baseline diff. The value-diff script and its output.
* **C2** the build glue: the Kconfig (`MSMB_CAMERA`, `MSMB_CAMERA_LEGACY`,
  `MSMB_JPEG`, `MSM_JPEGDMA`, `MSM_FD`), the Makefiles, the include paths.
* **C3** the CFI and the one-element-array classes.
* **C4** the SMMU class (`cam_smmu_api.c`).
* **C5** the ION class.
* **C6** the bus-vote class.
* **C7** the v4l2 and the media-controller classes.
* **C8** the power, the regulators and the clocks.
* **C9** the remaining small classes (the tracepoints, the smem, the misc).
* **C10** the device tree.
* **C11** the configuration switch-over (`MSMB_CAMERA*` on).

The boots, one per milestone:

1. the daemon identifies a sensor over I²C (the CCI, the CSIPHY, the CSID
   and the sensor framework);
2. the preview (the ISPIF and the VFE);
3. the CPP, then the JPEG;
4. the actuator, the EEPROM and the flash (the rear module with its
   calibration);
5. the face detection.

## 7. Review targets

The reviewer will check these first: the DMA-BUF reservation locking and the
map/unmap pairing in `cam_smmu_api.c`; the page references versus the DMA
pins; the ION handle lifetime and the ION-to-SMMU mapping ownership; the
subdev file operations and the ioctl numbers the daemon uses (they are ABI);
the power sequence ordering; the error paths that drop a lock or a
reference — the class that froze the phone on `msm_audio_ion_free` in the
audio port.

## 8. Hand-off rules

Every commit: the donor path, the upstream conversion it follows, the
evidence path, and an honest "not built" / "not boot-tested". No
`Co-Authored-By`, no `Assisted-by`. The builds are the user's; the agent
does compile checks and asks before a full build or a flash. The boot
evidence is pulled with `porting/REFERENCE-boot-testing.md`'s tooling, and
the log is read before any conclusion: an unverified claim costs a boot
cycle, and the boot cycles are the scarce resource.
