# Plan: hardware video (CAF vidc_3x) and audio playback on tissot 6.12

**Written 2026-10-22** for an implementing session; a separate session reviews
each commit. Read `AGENTS.md`, `porting/REFERENCE-driver-forward-porting.md`
and `porting/REFERENCE-boot-testing.md` first, and use the kernel development
skill as `AGENTS.md` requires. Supersedes the route choice in
`venus-vidc-port.md` (its Route B stands; its "stateless" description of
upstream Venus is wrong: upstream Venus is a stateful V4L2 m2m driver).

## 0. Ground truth

The donor kernel (`../oc-test`, `oc-test-2ghz`; the phone's original boot
partition is `../ack-kgsl-artifacts/stock-boot-live.bin`, kernel
`4.19.325-cip136-…-gdf4a1f863991`) runs the **same** Evolution X Android 17
system and vendor with working hardware video and audio. Measured
2026-10-22 by RAM-booting `stock-boot-live.bin` (the captures are kept
locally, not in the repository):

* video: `/dev/video32` + `/dev/video33`; `dumpsys media.player` lists
  `OMX.qcom.video.decoder.avc` (attributes `0xa`); YouTube logs
  `OMX-VDEC-1080P: component_init: OMX.qcom.video.decoder.avc : fd=7` and
  `Codec created: OMX.qcom.video.decoder.avc`.
* audio: the HAL starts `deep-buffer-playback` → speaker with
  `app_type 69936`, `acdb_dev_id 1058`, `snd_device_be_idx 52`, path
  `deep-buffer-playback speaker`; AudioFlinger's DEEP_BUFFER thread writes
  frames (1372800 → 1946880). No errors, no restart loop.

The HAL configuration and mixer paths are therefore correct; every remaining
fault is in the port kernel. **Nothing in the ROM is to be changed.**

Working rule for both parts: when the port and the donor differ, the donor's
behaviour is the specification. Diff against `../oc-test`, not against
theory. A boot cycle is the scarce resource: one change per boot, logdump
pulled, evidence directory named in the commit body. No `Co-Authored-By` /
`Assisted-by` lines. No build or flash unless the user asks.

---

## Part A — Audio playback (do first; smaller, already half done)

### State at hand-off

| commit | fix | tested |
|---|---|---|
| `d67199a80` | `msm_audio_ion`: pass `struct iosys_map` to `dma_buf_vunmap`, use the `_unlocked` vmap/vunmap (kernel BUG at `dma-buf.c:2359` on PCM close froze the phone on every app launch) | run342 (#54): 179 failed stream cycles, no BUG |
| `b250002a2` | `msm-pcm-q6-v2`: `copy_{from,to}_iter() != xfer` (every playback write returned `-EFAULT`, HAL `out_write: error -14`) | **not built** |

Open failures seen on run342 (`snapshot60/run342-bootloop-20261022-000001/`):

1. `MSM8x16 Media9: ASoC: no backend DAIs enabled for MSM8x16 Media9`
2. low-latency playback: HAL `pcm_open_prepare_helper: pcm_prepare returned -1`
3. `q6asm_callback: cmd = 0x10bcd returned error = 0x1` — `0x10bcd` is
   `ASM_STREAM_CMD_CLOSE` (`caf-include/dsp/apr_audio-v2.h:8353`): the DSP
   refuses to close streams that never opened. A consequence, not a cause.
4. `msm_pcm_chmap_ctl_put: substream ref_count:0 invalid` on every retry.

### A1. Test the two fixes (one boot)

Build with `porting/tools/build-kernel.sh <run> ../ack-kgsl-artifacts/boot-run258.img`
(user builds/flashes). Stream `adb shell su -c 'dmesg -w'` and logcat to the
host before playback (a hard hang leaves nothing on the phone). Play the same
YouTube video as the baseline (`am start -a android.intent.action.VIEW -d
https://www.youtube.com/watch?v=aqz-KE-bpKQ com.google.android.youtube`).

Pass: no `out_write: error -14`; `dumpsys media.audio_flinger` DEEP_BUFFER
thread `Frames written` increasing; audible on the speaker; no `kernel BUG`,
`Oops`, hung-task or soft-lockup lines.

### A2. Sweep the whole audio tree for the same conversion classes

Both bugs found so far were 4.19→6.12 API conversions that compile and are
silently wrong. Before chasing individual symptoms, sweep `sound/soc/msm/`
(and `drivers/` files the audio stack pulled in) for every instance of:

* `copy_{from,to}_iter`, `copy_{from,to}_user`, `copy_page_*` return-value
  semantics;
* dma-buf: `dma_buf_vmap/vunmap` argument type and reservation locking,
  `dma_buf_begin/end_cpu_access`, `dma_buf_map_attachment` locking
  (`_unlocked` variants), attachment/detach pairing;
* ION: allocation flags, heap IDs, `ion_alloc` callers vs. the port's
  `drivers/staging/android/ion`;
* ALSA/ASoC signature changes that take `void *` or `unsigned long`
  arguments (where a wrong type compiles): `.copy` (iov_iter), `.pointer`,
  `.ack`, `snd_soc_component_*` vs. old codec APIs, `rtd->dais` indexing;
* `struct timer_list` / `setup_timer`, `do_gettimeofday`, `ktime` conversions.

Record each site in a findings file with the upstream conversion commit
(as `b250002a2` cites the iov_iter series). Use Coccinelle in report mode
where a rule exists; add a rule only for a repeated, understood pattern.

### A3. Media9 "no backend DAIs"

* Identify which HAL usecase opens the PCM device whose FE is `MSM8x16
  Media9`: map `/proc/asound/pcm` (device index → FE name) on the port to
  the ROM's `/vendor/etc/audio_platform_info_intcodec.xml` `pcm_ids` and
  `/vendor/etc/mixer_paths_mtp.xml`.
* Check that the mixer control that path sets (`<BE> Audio Mixer
  MultiMedia9`) exists on the port's card and maps to a BE the machine
  driver links. Compare the port's FE/BE dai-link tables and
  `msm-pcm-routing-v2.c` routing table with the donor's
  (`../oc-test/techpack/audio/asoc/msm8952.c`, `msm8952-dai-links.c`,
  `msm-pcm-routing-v2.c`). Recent commits `565871d5a`, `f79691702`,
  `6861c32da` touched exactly this matching; review them first.

### A4. Low-latency `pcm_prepare` -1

Trace `msm_pcm_playback_prepare()` → `q6asm_open_write*` → `q6asm_*` for the
MultiMedia5/ULL FE; add one `pr_err` per failure return if the existing log
does not name it. Compare against the donor's same function. Expect a
perf-mode/ULL path difference (`LOW_LATENCY_PCM_MODE`, `apr_start_rx_rt`).

### A5. Optional: a rooted donor baseline (needs user approval; one boot)

The stock image has no root, so kernel-side donor state (dmesg, ASoC DAPM in
`/sys/kernel/debug/asoc/msm8953-snd-card-mtp/`) was not captured. If A3/A4
stall, package the **stock kernel** with the existing debuggable base
ramdisk (`base-guard-debug.img`; per `AGENTS.md` extract real base images,
never reconstruct) for `adb root`, RAM-boot it, and capture DAPM widget
state + dmesg during playback. Diff against the port's DAPM state.

### Audio done when

Speaker playback, wired-headset playback, and microphone capture (a voice
recorder) all work, with clean dmesg across 10 app launches. Voice calls are
out of scope (modem is offline).

---

## Part B — Hardware video: forward-port CAF vidc_3x

### What the ROM requires (the ABI contract)

* `libOmxVdec` / `libOmxVenc` open `/dev/video32` / `/dev/video33` (also try
  `/dev/video/q6_dec`), drive V4L2 with **CAF private** controls, events,
  buffer flags and pixel formats, and allocate through `/dev/ion`.
* The vendor OMX service is **32-bit** (it maps `/vendor/lib`), so every
  ioctl goes through the 6.12 **compat** path. The donor carries CAF changes
  to `drivers/media/v4l2-core/v4l2-compat-ioctl32.c`
  (`e35529201880` "32 bit to 64 bit v4l2-compat changes",
  `17f07c01bc84`, `2ea36671164e`). These are part of the ABI; review them
  and port their effect, or 32-bit clients will fail where 64-bit ones pass.
* UAPI headers that must be value-identical to the donor:
  `include/uapi/media/msm_vidc.h` (402 lines), `msm_media_info.h` (1339),
  `msm_vidc_private.h` (107), `msm_vidc_utils.h` (335), plus the CAF
  additions inside `include/uapi/linux/videodev2.h` (≥54 QCOM definitions:
  `V4L2_QCOM_BUF_*`, `V4L2_EVENT_MSM_VIDC_*`, UBWC/TP10 pixel formats) and
  `include/uapi/linux/v4l2-controls.h` (197 `V4L2_CID_MPEG_VIDC_*`).
  **Collision check required:** 6.12 upstream has added buffer flags,
  fourccs and MPEG-class control IDs since 4.19. Every CAF value must stay
  numerically identical (the blobs are compiled) and must not alias an
  upstream value the 6.12 core interprets. Write a script that preprocesses
  both trees' headers and diffs the numeric values; commit its output.
  Also check that 6.12 `videobuf2-v4l2.c` does not mask off or reject the
  CAF buffer flags (`__fill_vb2_buffer`, `V4L2_BUFFER_MASK_FLAGS`).
* Device nodes: the donor registers `BASE_DEVICE_NUMBER 32`
  (`msm_v4l2_vidc.c:36`). `vendor-ueventd.rc` already gives
  `/dev/video*` `system:camera 0660`; SELinux label `video_device`.

### What the port already has (proved by upstream Venus, run342)

Clocks (`gcc-msm8953.c` Venus clocks, `vcodec0_clk_src`), power domains
(`VENUS_GDSC`, `VENUS_CORE0_GDSC` as genpd), `venus_mem` reserved memory,
firmware (`venus.mdt` + `.b00-.b04` via `porting/tools/pull-venus-firmware.sh`,
loaded with `qcom_mdt_loader` + `qcom_scm_pas`, HFI 3.x `fw_level` 0x18),
the Venus SMMU stream on `apps_iommu`, the `msm-bus` shim
(`include/linux/msm-bus.h`, ICC-backed, votes without a path succeed), and
the port's ION (`/dev/ion`, `drivers/staging/android/ion`).

### Donor dependencies that need a 6.12 replacement

Donor: `drivers/media/platform/msm/vidc_3x/` (33 files, 34179 lines) +
`governors/` + `arch/arm64/boot/dts/vendor/qcom/msm8953-vidc.dtsi` (209 lines).

| donor API | uses | 6.12 replacement / decision |
|---|---|---|
| `subsystem_get_with_fwname("venus")`, `subsys_notif_*`, `venus_boot.c` PIL | 1 + 4 + file | `qcom_mdt_load` + `qcom_scm_pas_auth_and_reset` exactly as `drivers/media/platform/qcom/venus/firmware.c` (proven on this phone); SSR notifications become a no-op with a documented limitation |
| `scm_call` | 3 | `qcom_scm_*` equivalents, or the port's legacy `<soc/qcom/scm.h>` shim (qseecom port) — verify which command IDs |
| `regulator_get` on `venus-supply`/`venus-core0-supply` (GDSC regulators) | 2 | genpd `power-domains` + `dev_pm_domain_attach_by_name` / runtime PM, as upstream Venus does. Preserve the donor's on/off **ordering** relative to clocks |
| `clk_set_flags` (CAF retention flags) | — | no 6.12 equivalent; document what each flag did and whether the GDSC/clock driver already provides it |
| `msm_bus_scale_*` | 1 | existing `msm-bus` shim |
| `socinfo_*` (`CONFIG_QCOM_SOCINFO` is off) | — | DT property or a fixed msm8953 value; do not enable socinfo just for this |
| `pm_qos_add_request` | 2 | `cpu_latency_qos_add_request` |
| ION / `msm_ion.h`, `dma_buf_get`, `dma_buf_map_attachment`, `dma_buf_vmap` | 1/4/1/1 | port ION + `_unlocked` dma-buf API; cache maintenance on the non-coherent SMMU must match the donor (`msm_smem.c` cache ops) |
| `vb2_*` | 85 | 6.12 videobuf2: check `vb2_ops`, `buf_struct_size`, `wait_prepare/finish`, `vb2_queue_init` fields, plane/`m.fd` handling |
| `asm/dma-iommu.h`, per-context-bank devices | 4 | per-CB child platform devices with their own `iommus`; `of_dma_configure` on the children (the MDSS port solved the same model in `drivers/video/fbdev/msm/mdss_smmu.c`) |

### DT

New `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-vidc.dtsi` from the
donor's `msm8953-vidc.dtsi`: `qcom,msm-vidc`, `reg 0x01d00000`, SPI 44,
clock names `core_clk core0_clk iface_clk bus_clk` mapped to the port's GCC,
`power-domains` instead of `*-supply`, `memory-region = <&venus_mem>`,
`qcom,hfi-version = "3xx"`, `qcom,firmware-name = "venus"`, the bus and
governor children. **Context banks:** start with `venus_ns` only; translate
the donor's `iommus = <&apps_iommu 0x800 …>` to the port's SMMU stream
(upstream Venus uses `<&apps_iommu 0x16>`). The three secure context banks
need TZ secure SMMU (`CONFIG_MSM_TZ_SMMU`, absent): leave them disabled;
secure (Widevine L1) playback is out of scope and its codecs will fail only
at instantiation.

Upstream Venus and vidc_3x must never both bind: the same commit that enables
`CONFIG_MSM_VIDC_3X_V4L2` disables `CONFIG_VIDEO_QCOM_VENUS` and the
`qcom,msm8953-venus` node.

### Sequence (each step one commit; build only when the user asks)

* **B0** Import donor sources verbatim (driver, governors, uapi headers),
  not yet in Kconfig. A reviewable baseline diff.
* **B1** UAPI: add the CAF headers and videodev2/v4l2-controls additions;
  commit the value-diff script and its output (must be empty vs donor).
* **B2** Kconfig/Makefile; compile fixes per the table above, one API class
  per commit, each citing the upstream conversion commit.
* **B3** compat-ioctl32 review and port.
* **B4** DT + config switch-over (vidc on, upstream Venus off).
* **B5** Boot test (one boot). Pass:
  `ls -l /dev/video32 /dev/video33`; dmesg free of vidc errors, SMMU faults
  and HFI timeouts; `dumpsys media.player` lists `OMX.qcom.*` with
  attributes `0xa`; YouTube logs `component_init … OMX.qcom.video.decoder.avc`
  and plays 1080p smoothly; `screenrecord` produces a playable file
  (encoder). Compare with the donor measurements in section 0.

### Review targets (the reviewer will check these first)

dma-buf locking and argument types; `copy_*` return semantics; page
references vs DMA pins in `msm_smem.c`; cache maintenance on a non-coherent
SMMU; vb2 buffer-flag filtering; 32-bit compat ioctl paths; firmware
load/unload and power-domain ordering; error paths that drop a lock or a
reference (the class that froze the phone on `msm_audio_ion_free`).

## Hand-off rules

* Commit small, with the evidence path, the donor reference and the upstream
  commit in each message; mark "not built"/"not boot-tested" honestly.
* Do not reconstruct base images; build with `porting/tools/build-kernel.sh`
  against `../ack-kgsl-artifacts/boot-run258.img` (`BUILD_TISSOT.md`,
  `AGENTS.md`).
* When a symptom appears, check `git log --all -i --grep` first: this
  repository's commit bodies carry the evidence for many already-solved
  problems.
