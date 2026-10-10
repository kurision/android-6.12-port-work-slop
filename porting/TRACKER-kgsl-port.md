# Tracker: kgsl 4.19 -> 6.12 port (tissot)

Goal: restore `/dev/kgsl-3d0` with the stock ioctl ABI so the vendor EGL
(`libGLESv2_adreno.so`, 2020 QC blob), sdm HWC and gralloc work unchanged
— the "GPU 3D" row of `porting/FAILING-COMPONENTS.md` (backlog #1).

Worktree: `../ack-kgsl`, branch `kgsl-port` (from `driver-fix` a1e4992dc).
The main tree stays untouched until this port has a boot verdict.
Last update: 2026-10-10 — Stage 1 done (DT + exclusivity), dtb verified.

## Status key (same as FAILING-COMPONENTS.md)
FIXING · BLOCKED · SCOPED · PARKED · WATCH · CLOSED

## Source of truth (verified 2026-10-10; do not re-derive)
| Fact | Evidence |
|---|---|
| donor | `kernel_xiaomi_msm8953/drivers/gpu/msm` — 90 files / 74,471 lines |
| uapi to preserve verbatim | `.../include/uapi/linux/msm_kgsl.h` — 1,884 lines, 62 `IOCTL_KGSL_*` |
| ABI drift check | CAF `graphics-kernel` `GRAPHICS.LA.14.0.r7-01700-lanai.0` header diffed vs donor: additive only (new flags/props/structs/ioctls; no existing struct layout or ioctl-number change) |
| ION | built in since `a33336265`; `CONFIG_ION=y` (`arch/arm64/configs/tissot_gki.fragment:8`) |
| zap SCM | `include/linux/firmware/qcom/qcom_scm.h:75,79` (`pas_init_image`, `pas_auth_and_reset`) |
| zap fw | diag ramdisk stages `lib/firmware/qcom/a506_zap.mdt` (findings/13); kgsl requests the **flat** name `a506_zap.mdt` (donor `adreno_a5xx.c` zapfw) — staging layout decision needed |
| kgsl DT binding | donor `adreno.c:923` = `qcom,kgsl-3d0` |
| DRM binding displaced | `adreno_device.c:283-291` dt_match (incl. kgsl-3d0 back-compat) + component table `msm_drv.c:1022-1027` |
| DT pwrlevels | donor reads OPP-v2 first (`adreno.c:989-990`), legacy `qcom,gpu-pwrlevels` second (`adreno.c:1108`) — the existing `operating-points-v2 = <&gpu_opp_table>` (5 OPPs, `msm8953.dtsi`) is reusable |
| icc | `drivers/interconnect/qcom/msm8953.c:1304-1307` — bimc/pcnoc/snoc/snoc-mm, **no gpu master** |

## Adjacent references (checked; none is a donor)
- `msm8953-mainline/linux` `6.12/main`–`6.19/develop` and LineageOS
  `android_device_xiaomi_mi89xx-mainline` `lineage-23.0` (Android 16): the
  mainline path, no kgsl. Keep as patch source if display/GPU ever moves
  to mainline (dwc3-gadget reverts for 6.13–6.16, dm-table reverts 6.15,
  wcnss PIL reversions).
- CAF `graphics-kernel` LA.14.0 tag: sync already dma_fence (48 refs; only
  `msm_hw_fence_destroy` to stub), `adreno.c` on icc.
- `qualcomm-linux/kgsl` `gfx-kernel.le.0.0` (meta-qcom): has A506
  (`ADRENO_REV_A506 = 506`) but still the private qcom IOMMU context API —
  modern-anatomy reference only.

## Churn inventory (counted; supersedes BACKLOG #1's 4–8 week estimate)
| Item | Files | Work | Status |
|---|---|---|---|
| sync framework -> dma_fence | kgsl_sync.c | 3 legacy sites (`sync_fence_create` x2, `timeline_create` x1) -> `sync_file_create()`; `kgsl_timeline.c` already dma_fence-based | SCOPED |
| msm_bus -> icc | adreno.c, adreno_snapshot.c, kgsl.c, kgsl_gmu.c, kgsl_pwrctrl.c + 2 headers | `of_icc_get`/`icc_set_bw`; add `mas_gpu` to msm8953 icc or fixed-vote stub | SCOPED |
| iommu shims | kgsl_iommu.c | `iommu_fault_block` x2, `iommu_addr_in_svm_ranges` x2 | SCOPED |
| build glue | drivers/gpu/{Kconfig,Makefile}, fragment | `QCOM_KGSL` + `QCOM_KGSL_IOMMU` + `CORESIGHT_ADRENO`, `=y` | SCOPED |
| misc API delta | at compile | iterate, log per error | SCOPED |

## Stages
- [x] 0. Tracker + worktree `kgsl-port` created
- [x] 1. DT glue: kgsl exclusive, DTB compiles
- [ ] 2. Vendor driver + kernel links (CONFIG_QCOM_KGSL=y)
- [ ] 3. Boot #1 diag capture: kgsl probes, pwrlevels parse, `/dev/kgsl-3d0`,
      display + evidence channels intact
- [ ] 4. EGL/SF unlock (`EGL_BAD_ALLOC` gone)
- [ ] 5. Parity (render, suspend/resume, gpu cooling) + close FAILING-COMPONENTS rows

## Stage 1 log
- Exclusive binding: board override `&gpu { compatible = "qcom,kgsl-3d0",
  "qcom,adreno-506.0"; status = "okay"; }` in
  `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts` (drops the
  `qcom,adreno` fallback so DRM's dt_match stops claiming the node; SoC
  dtsi untouched, daisy/mido/vince boards unaffected).
- Removed `{ .compatible = "qcom,kgsl-3d0" }` from
  `drivers/gpu/drm/msm/adreno/adreno_device.c` (dt_match) **and**
  `drivers/gpu/drm/msm/msm_drv.c` (component table). The component one is
  the load-bearing edit: with the node present msm_drm waits forever for a
  GPU component that never binds, and display would die with the port.
- Verified: `make qcom/msm8953-xiaomi-tissot.dtb` builds; decompiled node
  shows the new compatible; zero `kgsl-3d0` matches left in drm/msm.
- Not yet verified (needs a boot): KMS binds with no GPU component
  (`priv->gpu == NULL`, `msm_drv.c:325-326`); flat-vs-`qcom/` firmware
  staging; the msm_bus/icc replacement.

## Stage 1 boot package (2026-10-10, awaiting device verdict)
- Worktree build `6.12.93-4k-gf3248eda0619` (`scripts/build-ack-tissot.sh`,
  ACK_TREE=worktree), full kernel + dtb, required-symbol assertion passed.
- Driver audit post-change: only new NOBIND node is
  `/soc@0/gpu@1c00000 qcom,kgsl-3d0 qcom,adreno-506.0` — kgsl is not
  vendored yet (Stage 2), so this image is the deliberate GPU-less test of
  the exclusivity change. (`/ion qcom,msm-ion` NOBIND is pre-existing: the
  ION backport registers as a misc device, same as snapshot58.)
- Image: `porting/artifacts/snapshot59/boot-run1.img`, 36,763,648 B,
  sha256 `e9254bddaa2cf6be712e50ee904bfd5036a04795f0181b29c3ea07eda2310ada`;
  same base image, ramdisk (`b6ac160d…`) and diag init (`b852daf2…`) as
  snapshot58 — only the kernel payload differs.
- Pass criteria on boot: mdp5/dsi/panel come up as before (DSI panel
  `0x9c`), no adreno/kgsl probe lines for the node, no new oops/WARN,
  evidence channels (logdump/USB) capture.
- Fail criteria: any display/DSI regression, or msm_drm master bind hang
  (no `msm` drm device, no panel). Revert `f3248eda0` partially: keep the
  driver-table edits if only the DT change is implicated, else whole commit.

## Boot economy (AGENTS.md)
One change per boot. `package-diag-boot.py` capture, verdict recorded here
with file+line evidence before any claim. Reverts are one-line documented.
