# 2026-10-22: donor kernel baseline for video decode and audio playback

**Evidence:** `porting/artifacts/snapshot60/stock-donor-baseline-20261022-001122/`.
`stock-boot-live.bin` (sha256 `62159562…`, kernel
`4.19.325-cip136-st20-perf-mglru-next-gdf4a1f863991`; `df4a1f863991` is on
`../oc-test` branch `oc-test-2ghz`) was RAM-booted with `fastboot boot`;
nothing was flashed. Same Evolution X (Android 17) system and vendor as the
port. This boot has no root, so dmesg, `/proc/asound` and ASoC debugfs were
not readable; everything below is from logcat and `dumpsys`.

## Video: the ROM does use the vendor OMX decoder

* `dumpsys media.player` lists `OMX.qcom.video.decoder.avc` for
  `video/avc`, attributes `0xa` (vendor, hardware-accelerated). The
  serialized codec list is 19568 bytes; on the port (run342) it is 13556
  and contains no `qcom` entry.
* The codec list generator logs `MediaCodecList: Allowing only
  non-surface-encoder OMX codecs` with `Codec2 services: "software"
  "__ApexCodecs__"`: it does consult OMX on Android 17.
* `/dev/video32` and `/dev/video33` exist (CAF vidc).
* YouTube playback: `OMXStore: makeComponentInstance(OMX.qcom.video.decoder.avc)`,
  `OMX-VDEC-1080P: component_init: OMX.qcom.video.decoder.avc : fd=7`,
  `YT.codecreuse: Codec created: OMX.qcom.video.decoder.avc`.

**Correction.** An earlier inference in this session that the Android 17
codec list ignores OMX, and that `external/v4l2_codec2` on upstream Venus
was the route, was wrong. The route is the plan's Route B: the CAF
`vidc_3x` forward-port (`porting/plan/venus-vidc-port.md`). The line in
`2026-10-21-youtube-video-garbage-and-360p-cap.md` that the stock kernel
decodes in hardware is now measured, not assumed.

## Audio: the HAL and mixer paths are not the problem

Playing the same YouTube video on the donor, the audio HAL starts
`deep-buffer-playback` on the speaker once, with `app_type 69936`,
`acdb_dev_id 1058`, `snd_device_be_idx 52` and the mixer path
`deep-buffer-playback speaker` — identical to the port's run342 log. No
`out_write` or `pcm_prepare` errors and no restart loop.
`dumpsys media.audio_flinger`: `AudioOut_1D` (DEEP_BUFFER, speaker)
`Frames written` 1372800, then 1946880 on the next read.

So the ROM's HAL configuration works unchanged on the donor kernel; the
port's failures (`out_write: error -14`, fixed in b250002a2 but not yet
tested; `no backend DAIs enabled for MSM8x16 Media9`; low-latency
`pcm_prepare returned -1`; `ASM_STREAM_CMD_CLOSE` rejected) are
kernel-side. A kernel-side donor comparison (dmesg, ASoC DAPM state) needs
root on the donor boot, which this image does not have.
