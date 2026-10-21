> **2026-10-22:** superseded for sequencing by
> [2026-10-22-video-and-audio-port.md](2026-10-22-video-and-audio-port.md).
> Route B is confirmed by a donor-kernel measurement (the ROM uses
> `OMX.qcom.video.decoder.avc` on the 4.19 kernel). Correction: upstream
> Venus is a *stateful* V4L2 m2m driver, not a stateless one.

# Plan: hardware video codec (Venus) for tissot

Goal: give the ROM a working hardware video **decoder and encoder**, which
is the missing piece behind (a) the YouTube app's 360p cap and its
corrupted video layer, and (b) the absence of hardware video encode.

Donor: `kernel/oc-test` (CAF 4.19) — `drivers/media/platform/msm/vidc_3x`,
33 files, 34 179 lines, `CONFIG_MSM_VIDC_3X_V4L2=y` in the donor's
`msm8953-perf_defconfig`.

## 1. What the ROM actually asks for (measured on the phone)

The ROM's media stack is the CAF one:

```
/vendor/lib64/libOmxVdec.so   opens /dev/video32   (or /dev/video/q6_dec)
/vendor/lib64/libOmxVenc.so   opens /dev/video33   (or /dev/video/q6_enc)
    ... and drives V4L2_CID_MPEG_VIDC_* controls
```

i.e. the ROM speaks the **CAF `msm_v4l2` (vidc) V4L2 ABI**, not the
standard V4L2 stateless API. `dumpsys media.player` on the port lists only
the `c2.android.*` software codecs — there is **no `c2.android.v4l2.*`
plugin** in the ROM, so an upstream-style Venus device would be invisible
to every app that uses MediaCodec.

Consequence: to get hardware video into the ROM's apps (YouTube, the
camera, any recorder), the port needs the **CAF vidc_3x driver**.

## 2. The good news: the hardware plumbing is already in the port

Audited today (`drivers/clk/qcom/gcc-msm8953.c`, `arch/arm64/boot/dts/qcom/msm8953.dtsi`):

| need | port status |
|---|---|
| Venus clocks `GCC_VENUS0_AHB_CLK`, `GCC_VENUS0_AXI_CLK`, `GCC_VENUS0_CORE0_VCODEC0_CLK`, `GCC_VENUS0_VCODEC0_CLK`, `GCC_VENUS_TBU_CLK` | **present** (`gcc-msm8953.c:3749-3820`, IDs in `gcc-msm8953.h:172-176`) |
| settable Venus core clock `vcodec0_clk_src` (clk_rcg2 + freq table) | **present** (`gcc-msm8953.c:1591-1626`) |
| power domains `VENUS_GDSC`, `VENUS_CORE0_GDSC` (genpd) | **present** (`gcc-msm8953.c:3863-3880`, `4198-4199`) |
| Venus memory region (firmware + secure) `venus_mem` @ 0x91400000, 7 MiB | **present** (`msm8953.dtsi:315-318`) |
| SMMU context bank for Venus (`iommu-ctx@16000`, "VENUS_NS") | **present** (`msm8953.dtsi`, inside `apps_iommu`) |
| interconnect driver for msm8953 | **present** (`drivers/interconnect/qcom/msm8953.c`) |
| upstream Venus driver | **present** in the tree, but `CONFIG_VIDEO_QCOM_VENUS` is not set and there is no `qcom,msm8953-venus` data table |

So the *hardware* side of the port is ready; what is missing is the
**driver and its device tree**, plus the firmware.

## 3. Two routes

### Route A — upstream Venus driver (cheap, but the ROM cannot use it)

Work: add a `qcom,msm8953-venus` resource table to
`drivers/media/platform/qcom/venus/core.c` (upstream has msm8916/msm8939/
msm8996/msm8998/sdm660/sdm845 but **not** msm8953 — the postmarketOS 6.17
reference DT in `porting/artifacts/tissot-live.dts:2284` carries a
pmos-local `qcom,msm8953-venus` node, so upstream does not have it), the
DT node, the ICC paths (`video-mem`, `cpu-cfg`), the firmware, and
`CONFIG_VIDEO_QCOM_VENUS=y`.

Cost: small (a few hundred lines). Value: proves the clocks/power/IOMMU/
firmware plumbing; gives a *standard* V4L2 stateless codec that only
non-ROM apps can use. **It does not fix YouTube**, because the ROM has no
V4L2 C2 plugin.

### Route B — CAF vidc_3x forward-port (the real goal)

Work: forward-port 34 179 lines of CAF 4.19 V4L2 code to 6.12, plus the
CAF-style DT (the donor's `msm8953-vidc.dtsi`: the `qcom,msm-vidc` node
with `qcom,platform-version`, `qcom,reg-presets`, `qcom,dcvs-tbl`,
`qcom,clock-freq-tbl`, the four `qcom,msm-vidc,context-bank` children and
the `qcom,msm-vidc,bus` children), the firmware loader, and the port's
IOMMU/genpd/ICC adaptation.

Cost: large (weeks), and it is the same class of work as the MDSS port
that already succeeded in this tree.

**Recommendation: Route B, with Route A as its first milestone.** The
plumbing (clocks, GDSCs, memory, SMMU bank, ICC) is identical for both, so
Route A's bring-up is a cheap way to shake out the hardware layer (clock
gating, power sequencing, firmware load, SMMU) before the 34 k-line
driver port starts. Then Route B reuses the proven plumbing and only has
to add the CAF ABI.

## 4. Sequencing

### Step 1 — Route A: upstream Venus for msm8953 — **DONE (commit c5e5fa5e0)**

The plumbing is proven on the device:

* `CONFIG_VIDEO_QCOM_VENUS=y`, the `qcom,msm8953-venus` node in
  `msm8953-xiaomi-tissot-venus.dtsi`, and `msm8953_res` in
  `drivers/media/platform/qcom/venus/core.c`;
* the ROM's firmware (`venus.mdt` + `venus.b00..b04`, a split ELF on the
  firmware_mnt partition) is pulled by
  `porting/tools/pull-venus-firmware.sh` and staged into the ramdisk
  (`--firmware-dir` now takes more than one tree);
* on the phone: `/dev/video0` = `qcom-venus-decoder`, `/dev/video1` =
  `qcom-venus-encoder`, the firmware loaded, the HFI handshake
  completed (`/sys/kernel/debug/venus/fw_level` = 0x18, read from the
  firmware's response), and no errors in `dmesg`.

So the clocks, the two power domains, the SMMU context bank, the
firmware load and the HFI version (3.x, as the CAF donor's DT says) all
work on this port. The HFI version was the one genuinely uncertain
item, and the firmware's own "Venus332" string agrees with the donor.

What this does **not** do: the upstream driver speaks the standard V4L2
stateless API and the ROM has no plugin for it, so the ROM's apps still
use the software decoder. The `msm8953-venus` node is also not what the
stock 4.19 kernel used (see `porting/artifacts/tissot-live.dts:2284`,
which carries a postmarketOS-local binding), so the DT shape here is
this port's, not the ROM's.

### What step 1 changed, and what it did not

1. `drivers/media/platform/qcom/venus/core.c`: `msm8953_res` - the
   register presets of the Venus 1.8 register map (the same three the
   msm8916/msm8939 entries use) with the **HFI 3.x** protocol the CAF
   donor's DT asks for (`qcom,hfi-version = "3xx"`) and the device's
   firmware agrees with (it identifies itself as "Venus332"), the GCC
   `vcodec0_clk_src` rate list, and the donor's encoder/decoder
   bandwidth tables.
2. DT (`msm8953-xiaomi-tissot-venus.dtsi`): the node at 0x1d00000 with
   the core/iface/bus clocks, the SMMU stream 0x16, the Venus memory
   region and the VENUS_GDSC domain, the decoder and encoder children
   on VENUS_CORE0_GDSC with the vcodec0_core clock, and the
   `operating-points-v2` table the driver sets the core rate through.
3. No "interconnects" property: this tree has no ICC providers for the
   Venus paths, and `of_icc_get()` returns NULL for a missing property,
   which the driver reads as "no bandwidth constraints". The port's
   `drivers/interconnect/qcom/msm8953.c` does carry `mas_venus` and
   `slv_venus_cfg`, so the paths can be added later if the bandwidth
   governor turns out to matter.
4. Firmware: it **is** on the device, but not in /vendor - the ROM
   keeps it on the firmware_mnt partition as `venus.mdt` plus
   `venus.b00..b04` (a split ELF, which is why the MDT loader's ELF
   path is the one that reads it). The driver probes long before
   /vendor is mounted, so the files are staged into the ramdisk.
5. Config: `CONFIG_VIDEO_QCOM_VENUS=y` (+ `CONFIG_QCOM_MDT_LOADER`).

**Verification done**: the device shows `/dev/video0` and `/dev/video1`
(the decoder and the encoder), the firmware loaded, the HFI handshake
completed (`/sys/kernel/debug/venus/fw_level` = 0x18) and `dmesg` has no
Venus errors. Not done yet: an actual frame through the device - there
is no V4L2 client on the ROM (no `v4l2-ctl`, and the ROM's media stack
has no C2 V4L2 plugin), so the decode path itself is untested.

### Step 2 — Route B: the CAF vidc_3x port

1. Import `drivers/media/platform/msm/vidc_3x/` from the donor, build it
   out-of-tree of the display work, and get it to compile on 6.12.
2. Adapt to the port's kernel model, in the order the MDSS port had to:
   * V4L2/media-controller API drift (4.19 → 6.12),
   * `dma_buf`/IOMMU: the CAF "context bank" children become the port's
     `apps_iommu` stream 0x16 (non-secure only; the secure banks need the
     port's missing `MSM_TZ_SMMU`),
   * genpd instead of the CAF `gdsc` regulator,
   * the interconnect/clocks in the port's model,
   * the firmware loader: CAF's `subsystem_get_with_fwname("venus")` needs
     either the CAF PIL ported or a replacement in the port's
     remoteproc/mdt-loader model.
3. DT: the donor's `msm8953-vidc.dtsi` re-expressed in the port's model
   (the `qcom,msm-vidc,context-bank` children become one `apps_iommu`
   stream; the `qcom,msm-vidc,bus` children become the port's bus
   scaling driver, if it still has one).
4. **ABI check against the ROM**: `/dev/video32` (dec) and `/dev/video33`
   (enc) must appear with the names `libOmxVdec.so`/`libOmxVenc.so`
   open, and the `V4L2_CID_MPEG_VIDC_*` controls must be present.

**Verification for step 2**: `dumpsys media.player` must list
`OMX.qcom.video.decoder.avc` / `OMX.qcom.video.encoder.avc` (the ROM's
`/vendor/etc/media_codecs.xml` already declares them) with
`hw-accelerated: 1`; the YouTube app must then report a quality above
360p, and the video layer must stop being the CPU-decoded YV12 path that
corrupts (see `2026-10-21-youtube-video-garbage-and-360p-cap.md`).

## 5. Risks / open questions

* **HFI version of the msm8953 Venus**: the donor's DT says
  `qcom,hfi-version = "3xx"`, but the msm8953 Venus is otherwise treated
  as a 1.x/2.x class device upstream. Must be settled from the firmware
  version string before writing the resource table.
* **Firmware file**: not in the ROM under any `venus*` name; the
  `cpp_firmware_v1_*.fw` set is the candidate. Without it there is no
  hardware video at all.
* **ROM ABI drift**: the ROM's `libOmxVdec.so`/`libOmxVenc.so` are from
  the CAF 2019/2020 era; the donor's vidc_3x is the same generation, so the
  ioctl/control surface should match — but the *device names* and the
  `msm_v4l2` capability negotiation must be verified against the ROM's
  expectations, not assumed.
* **Secure paths**: the CAF DT has three secure context banks (bitstream,
  pixel, non-pixel). The port has no `MSM_TZ_SMMU` and no secure-display
  path, so the first bring-up should be the **non-secure** path only;
  Widevine L1 (and therefore HD in the YouTube app) also needs a
  TEE-side change, not just this driver.
* **Camera coupling**: the encoder is only useful once the camera stack
  exists; the decoder is the one that matters today.

## 6. Relation to the YouTube bug

Two independent problems, one shared cause:

* the **360p cap** is a DRM/security-level problem
  (`mediadrm.errored getPropertyString error_code=6` =
  `ERROR_INSUFFICIENT_SECURITY`; the ROM ships the software Widevine CDM
  and the device is not L1-certified) — a ROM/attestation problem, not a
  kernel one, though HD streams also need the hardware decoder to be
  useful;
* the **corrupted video layer** is the CPU-decoded YV12 buffer on the MDP
  VIG/scaler path (verified: the MDP's addresses, plane offsets, format
  and rects are all correct, and the app's own re-composition is clean) —
  the hardware decoder removes this path entirely, because the VDEC writes
  the buffer through the SMMU with no CPU cache involved.
