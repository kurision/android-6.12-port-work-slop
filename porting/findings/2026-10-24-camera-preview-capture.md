# Kernel #43: working preview, orientation, JPEG corruption and video encoding

Kernel #43 is `6.12.93-4k-g6b7fe2b3628d-dirty`, built 2026-10-24
00:48:06 +0545. The user reports working front/rear preview, rear preview
upside down with reversed apparent motion, normal front preview, corrupt
saved photos and playable videos. These are separate observations; a
shared cause has not been established.

The [capture directory](../artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/)
contains identity, initial/live/post-use logs, camera dumps, codec metrics,
IRQ state and raw logdump. Its `saved-media/` directory contains the two
test JPEGs and videos, remote/local names, byte counts, hashes, ffprobe
metadata and decoder logs. Test media were copied read-only; the phone's
files and archived originals were not modified.

## CPP milestone

The primary logdump prefix now records userspace-triggered CPP hardware
initialization at approximately 28.24, 28.38 and 28.87 seconds, reporting
hardware version `0x40030003`, the same version seen on working stock.
See lines 4115-4135 of
[logdump-prefix.txt](../artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/logdump-prefix.txt).
This is progress beyond #42, where CPP registered but a source and library
audit found lost `entity.revision` semantics in its device-selection ABI.
The failing daemon open itself was not traced.

The user now sees preview, but that does not establish every capture,
firmware, DMA or postprocessing path as correct.

## Orientation: wrong inherited sensor base

The donor entry point is
`../oc-test/arch/arm64/boot/dts/vendor/qcom/tissot-titanium.dts`. It includes
`msm8953-camera-sensor-qrd.dtsi` before the tissot board overrides in
`mi8953/tissot/camera.dtsi`. The board overrides do not replace the three
mount-angle properties.

| Slot | Effective QRD donor | Port before correction |
| --- | --- | --- |
| 0, rear | 90 degrees | 270 degrees |
| 1, secondary rear | 90 degrees | 90 degrees |
| 2, front | 270 degrees | 90 degrees |

The port restored inherited slots using the MTP base in `8e6263ae9919`.
MTP differs from QRD for slots 0 and 2. That earlier donor-parity check
used the wrong base for this board and did not establish effective tissot
parity. This corrects that finding rather than treating the old check as
proof of the orientation values.

The working 4.19 camera dump reports orientations `[90, 270, 90]` for its
three camera IDs, while #43 reports `[270, 270]` for its two IDs. Evidence:
[stock camera-before.txt](../artifacts/snapshot60/stock419-camera-20261023T143434Z/camera-before.txt)
and [#43 camera.txt](../artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/camera.txt).
The rear has a 180-degree metadata discrepancy. Front already reports
270 degrees despite the incorrect DT default; the sensor probe can
replace the default with supplied sensor-init parameters. Correct final
metadata does not prove a correct DT default.

With user approval, the camera DTSI now uses QRD angles `[90, 90, 270]`.
The resolved-board test verifies the donor entry point includes QRD and
compares each compiled slot angle against that file. It does not change
sensor register tables, gyro configuration, HAL binaries or application
rotation logic. This correction has not been boot-tested; the next test
must check rear orientation and retain front as a working control.

[Android's camera-preview documentation](https://developer.android.com/media/camera/camera2/camera-preview)
describes the sensor/device orientation relationship. The hardware values
here come from the effective donor and captured stock metadata, rather
than choosing a rotation to hide the symptom.

## Saved JPEGs: missing hardware and a malformed fallback stream

The still path attempts `/dev/jpeg0` and `/dev/jpeg1`, fails both opens,
then reports that the JPEG hardware library could not initialize. It
uses the software/hybrid encoder and reports success to the HAL. See
lines 37846 onward of
[live logcat](../artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/logcat-live.txt).
Later gallery/Skia messages report libjpeg warning 117, premature end of
the entropy data segment, for these captures.

The JPEG camera nodes are absent from this port's DT stage. This establishes
why those hardware-device opens fail; it does not establish that enabling
JPEG hardware alone fixes every photo problem. That block's power, clocks,
IOMMU, ioctl and buffer lifetime paths still need review before activation.

Both copied JPEGs have SOI and final EOI markers; their files are not simply
missing the final marker. The decoded frame dimensions are 1944x2592 and
3000x4000. The files contain 161 and 251 restart markers, respectively,
but no DRI (`0xffdd`) segment declaring their restart interval. See
`saved-media/jpeg-markers.json` and the archived decoder output.

A host diagnostic reads the originals with libjpeg and writes no image.
Normal decoding sees declared restart interval zero. Supplying one MCU
row as the decoder interval gives:

| Sample | MCU columns | Original warnings | Interval override warnings |
| --- | --- | --- | --- |
| 5 MP | 122 | 162 | 0 |
| 12 MP | 188 | 252 | 3 |

The diagnostic source and output are archived as
`saved-media/jpeg-restart-diagnostic.c` and
`saved-media/jpeg-restart-diagnostic.log`. Decoded-pixel hashes change.
The remaining three rear-sample warnings prevent claiming complete repair
or complete isolation of that sample. No repaired media were installed or
saved over the originals.

The missing interval is a reproducible bitstream defect, distinct from
the mount-angle discrepancy. The exact vendor encoder/header-generation
code responsible remains unverified. The relevant primary references are
libjpeg-turbo's
[marker writer](https://raw.githubusercontent.com/libjpeg-turbo/libjpeg-turbo/main/src/jcmarker.c)
and [entropy decoder](https://raw.githubusercontent.com/libjpeg-turbo/libjpeg-turbo/main/src/jdhuff.c):
the encoder emits DRI for a nonzero interval and the decoder uses the
interval to process restart boundaries.

## Videos: software AVC confirmed; selection cause pending

The user's recorded videos used `c2.android.avc.encoder` at 1920x1080.
Codec metrics associate it with `org.lineageos.aperture`, `encoder=1`,
MIME `video/avc`; the completed second session explicitly reports
`hardware=0`. See records 152 and 220 in
[codecs-191127.txt](../artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/codecs-191127.txt).
AAC also uses a software component, which is a separate audio choice.

Both MP4 files demux and decode on the host. One decoder run reports a
duplicate/non-monotonic timestamp; this is not a clean timing verdict.
Playback success does not establish hardware encoding.

[Encoder configuration](../artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/encoder-config.txt)
advertises `OMX.qcom.video.encoder.avc` and other hardware encoders.
Therefore do not conclude they are absent merely because Aperture selected
software. Selection policy, queried capabilities and encoder initialization
need comparison with working stock. Earlier VIDC IOVA and compat-plane
fixes (`b64b87a7e7e4`, `793615c17e5f`) are already in history and must not be
replaced with an assumption that the codec driver was never brought up.
No new hardware-encoder failure was isolated in this capture.

## Scope and next checks

The approved DT orientation correction and its regression check are committed
as `b74883f50`; they are newer than #43 and not boot-tested. CPP and ABI
changes are listed in the [handoff](../HANDOFF-camera-2026-10-24.md).
No JPEG node, codec policy, vendor binary or application behavior was changed.
No kernel build or phone boot was performed by the agent.

Next: validate the orientation correction on the user's next authorized
build; review the donor JPEG hardware path and the malformed software
fallback separately; identify why Aperture selects software AVC before
changing codec configuration. No further boot is needed just to preserve
or inspect the evidence already archived.
