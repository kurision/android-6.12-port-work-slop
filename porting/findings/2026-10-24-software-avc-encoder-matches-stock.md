# Aperture's software AVC encoder selection is stock behaviour, not a port defect

**Date:** 2026-10-24 · **Branch:** `ack-camera` · **Evidence:**
`porting/artifacts/snapshot60/stock419-camera-20261023T143434Z/logcat-live.txt`
and `porting/artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/`

## The question

Kernel #43's two video sessions encoded with `c2.android.avc.encoder`
(metrics in `codecs-191127.txt`, `hardware=0`), while
`/vendor/etc/media_codecs.xml` declares `OMX.qcom.video.encoder.avc`
(`encoder-config.txt:148`). The camera handoff's third work item asked
whether VIDC or codec policy has to change before hardware encode is used.

## The control: the same ROM on the donor kernel

The stock419 capture ran this same Evolution X image on the donor 4.19
kernel and exercised its working camera. During that camera session the
encoder chosen was **also the software one**:

| Boot | Kernel | Encoder allocated | Evidence |
| --- | --- | --- | --- |
| Donor 4.19, camera session | `4.325-cip136-st20-perf` | `c2.android.avc.encoder` | `stock419-.../logcat-live.txt:44907` (20:20:46, three allocations, same triple-allocate pattern as the port) |
| Port #43, video sessions | `6.12.93-4k-g6b7fe2b36` | `c2.android.avc.encoder` | `camera-cpp-capture-.../logcat-live.txt:44438` (00:52:32), `:54811`, `:56244` |

The OMX hardware path itself is functional on the port:
`OMX.qcom.video.decoder.hevc` ran a 1080p decode session on #43
(`codecs-191127.txt`, record 28), and `IOmx service obtained` appears
throughout the session. Nothing failed; the hardware encoder was never
queried for allocation on either kernel.

## Conclusion

Software AVC selection for camera recording is this ROM's/app's codec
policy, identical on the donor kernel with a fully working camera. There
is no port regression to fix, and changing VIDC or codec policy to force
`OMX.qcom.video.encoder.avc` would deviate from stock behaviour.
**No kernel change.** Close the handoff's "video encoder selection" item
as matches-stock.

## Why the hardware encoder is unreachable (2026-10-24, live checks)

The framework's registered encoder list contains only `c2.android.*`
software encoders; `OMX.qcom.video.encoder.avc` is not in the
MediaCodecList at all, while the OMX.qcom decoders register and run.
The `MediaCodecListGenerator` produced a list of exactly **19568 bytes on
both kernels** (donor `logcat-live.txt:3788`, port `:9954`) - the OMX
encoders are dropped by the ROM's list build on stock as well. The kernel
side is complete either way: on the running port, `/dev/video32` is
`msm_vdec_8974` and `/dev/video33` is `msm_venc_8974`, both answering
`VIDIOC_QUERYCAP` with M2M MPLANE capabilities (on-device probe,
`venc-probe`, 2026-10-24 ~01:40 NPT).

Enabling hardware encoding for the user's thermal goal is therefore a
ROM-side codec-policy change (registering or un-filtering the OMX.qcom
encoder, or a Codec2 wrapper for it) - outside this kernel tree. The
kernel's encoder path can be proven independently of the framework with
a raw V4L2 M2M encode test against `/dev/video33` if that evidence is
wanted.

Remaining, unverified: the duplicate-timestamp warning on one #43 MP4 has
no stock counterpart in the capture (no stock recording was pulled), so it
stays open as a minor observation, not a defect claim.
