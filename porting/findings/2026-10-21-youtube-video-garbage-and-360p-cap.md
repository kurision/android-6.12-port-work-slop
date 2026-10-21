# 2026-10-21: YouTube app video corrupts on the panel; 360p cap

Device: tissot (msm8953), port kernel `6.12.93-4k-g166d3b5328c6-dirty`.
Donor: `kernel/oc-test` (CAF 4.19) — the MDSS tree in `ack-kgsl` is a
forward-port of it, so every file below was diffed against the donor.

## Symptom 1 (kernel side): the YouTube app's video is garbage on the panel

User report: "it tries to play but glitches appear every frame". The user
filmed the panel with a second phone
(`~/Downloads/PXL_20261021_135636318.TS.mp4`, frame 312, rotated with
`transpose=2`).

Zoom of the video area (`crop=580:640:205:755`): the **top ~20 % of the
video image is a vertical smear with horizontal tear lines**, the rest of
the frame is clean. The app's *UI text* below the player is clean.

`adb exec-out screencap` of the same moment is **clean** — SurfaceFlinger
re-composes the layers itself, so the decoded pixels are correct and the
corruption is introduced by the **MDP scanout of that layer**, not by the
decoder.

## What the two players do differently (measured, not inferred)

`/sys/kernel/debug/mdp/dump` and the DIAG123 SSPP register dump in
`drivers/video/fbdev/msm/mdss_mdp.c`:

| player | VIG (video) pipe source | composition |
|---|---|---|
| YouTube app | `src w=640 h=360 format=19 (Y_CR_CB_GH2V2)`, `dst_rect x=0 y=70 w=1080 h=608` | **SDM video overlay + scaler, CPU-decoded planar YV12** |
| Chrome (web) | `src w=1088 h=1920 format=45 (RGBA_8888_UBWC)` | GPU-composited RGBA, no YUV/scaler path |

So the app is the only content that puts a **CPU-written YUV buffer** on the
MDP VIG pipe with the scaler enabled. Chrome's video never touches that
path — which is why the browser is clean and the app is not.

## The MDP programming is correct (ruled out stride/offset/format)

MDSS xlog (`/sys/kernel/debug/mdp/xlog/dump`,
`mdss_mdp_src_addr_setup:2292` → `pipe->num, multirect, mixer, play_cnt,
addr[0..3]`) during app playback:

```
mdss_mdp_src_addr_setup:2292 =>[40760]:0 0 0 170 fff00000 fff38400 fff46500 0
```

For 640x360 planar YV12 that is exactly right:

* Y  @ 0xfff00000, size 640*360 = 0x38400
* Cr @ 0xfff38400 = Y + 0x38400
* Cb @ 0xfff46500 = Cr + 320*180 (0xe100)

and `src_rect 640x360 → dst_rect 1080x608` is the exact 16:9 fit.
So the port programs the right addresses, the right plane layout and the
right format. The corruption is in the **data the MDP reads**, not in how
it reads it.

## Why this path is broken only on the port

The port kernel has **no video decoder driver at all**:

* no `/dev/video*`, no CAF `videodec`/`vidc` in the tree
  (`drivers/media/platform/` has only `qcom/` = camss + venus);
* `dumpsys media.player` lists only `c2.android.avc.decoder` and
  `c2.android.hevc.decoder`, both `hw-accelerated: 0`.

The ROM's `OMX.qcom.*` / `c2.qti.*` codecs in `/vendor/etc/media_codecs.xml`
therefore cannot load, and both players fall back to the **software**
decoder (`media.swcodec`). On the stock 4.19 kernel the same video is
produced by the **hardware VDEC**, which writes the frame through the SMMU
with no CPU cache involved. The software decoder writes it through the
CPU's cache, and nothing in the display path cleans it for the device —
the MDP's SMMU is not coherent with the CPU.

Leading hypothesis (not yet proven): the MDP reads stale cache lines for
the CPU-written YV12 buffer, which is why the corruption is banded garbage
rather than a uniform shift, and why it only affects the one path that
puts a CPU-written YUV buffer on the VIG/scaler pipe.

Remaining alternative: the SDM scaler step registers for a 1.69x upscale
of a YUV source (the registers themselves could not be read — see
"instrumentation gap" below).

## The port's MDSS code is the donor's code

`diff` against `kernel/oc-test/drivers/video/fbdev/msm/`:

```
mdss_mdp_pipe.c   0 changed lines
mdss_mdp_layer.c  0 changed lines
mdss_mdp_ctl.c    0 changed lines
mdss_mdp_overlay.c 24   (diag only)
mdss_mdp.c        558  (genpd conversion + diag)
mdss_fb.c         115  (6.12 API + diag)
mdss_smmu.c        86  (msm_dma_iommu_mapping → generic dma API + diag)
```

The SMMU mapping path in the port uses `dma_map_sgtable()` where the donor
used `dma_map_sg_attrs()`/`msm_dma_map_sg_attrs()`; the ION layer
(`drivers/staging/android/ion`) is a faithful 6.12-ification with the same
`ion_sgl_sync_range()` → `dma_sync_sg_for_device()` cache handling, and the
ROM's gralloc still allocates from `/dev/ion` (there is no `/dev/dma_heap`
on this device).

## Symptom 2 (ROM side, not kernel): the 360p cap

The app's player menu shows **"Quality: Auto (360p)"**, and the measured
decode is 640x360.

`dumpsys media.metrics` shows the Widevine CDM failing the security-level
query:

```
mediadrm.errored (api=getPropertyString, error_code=6, scheme=Widevine Content Protection)
```

`error_code=6` is `MediaDrm.ERROR_INSUFFICIENT_SECURITY`: the ROM ships
`/vendor/lib64/mediadrm/libwvdrmengine.so` (software CDM) and the device
is not L1-certified, so HD is not served to the app. Note that Chrome is
not actually running 1080p either: the mediaserver decoded **640x360**
(5576 frames) and 640x272 for the web player — the "1080p" in Chrome's menu
is a label, the stream served is 360p.

Lifting the 360p cap therefore needs a **TEE-based Widevine L1 CDM plus
device certification** (ROM side), and for good quality a **hardware video
decoder in the kernel** (VDEC port). The kernel can only fix symptom 1.

## Instrumentation gap

The port's DT dropped the donor's `qcom,regs-dump-mdp` /
`qcom,regs-dump-names-mdp` properties, so
`/sys/kernel/debug/mdp/off` + `mdp/reg` refuse any offset
("invalid range requested") and the SSPP registers cannot be read from
userspace. The donor's ranges include `VIG0_SSPP` (0x5000-0x5150), which
is exactly what is needed to read `SSPP_SRC_YSTRIDE0/1`, `SSPP_OUT_SIZE`
and `SSPP_OUT_XY` during app playback.

## Next step (needs a build, not done yet)

1. Restore `qcom,regs-dump-mdp` + `qcom,regs-dump-names-mdp` in
   `msm8953-xiaomi-tissot-mdss.dtsi` (pure DT, donor values).
2. Extend the DIAG123 print in `mdss_mdp.c` with the VIG pipe's
   `YSTRIDE0/1`, `OUT_SIZE`, `OUT_XY` and the scaler step registers.
3. Rebuild, flash, reproduce in the app, and read the scaler programming.
4. If the programming is right (expected), A/B a cache clean for the
   display buffer: `dma_sync_sgtable_for_device()` on the fb sg table
   (`mfd->fb_table` in `mdss_fb.c`) before the kickoff, which is the
   difference between a CPU-written buffer and a VDEC-written one.
