# Tissot camera handoff — 2026-10-24

## Resume here

User kernel **#43 has working front and rear preview**. The user reports rear
preview upside down with reversed apparent motion, normal front preview,
corrupt saved photos and playable videos. Software AVC encoding is confirmed
by codec metrics. Camera bring-up is not complete.

The latest source change corrects sensor mount angles to the effective QRD
donor values. It is committed but **not boot-tested**. Do not repeat the old
CCI/actuator/EEPROM blacklist experiments merely because the earlier session
began with silent boots: the current milestone is userspace camera streaming.
The old boot-death record is history, not a diagnosis of these capture defects.

## Rules that remain in force

- Before any file edit, explain the exact change/files/checks and obtain
  explicit confirmation. Read AGENTS.md and the kernel development skill.
- Do not start a kernel build unless the user asks. Use the existing `out/`
  through the documented wrapper; do not clean it. Boot cycles belong to the
  user. Keep one isolated change per future boot cycle.
- Use only `console=ttynull`. Never enable `earlycon`, `ttyMSM0` or `tty0`.
  [Console SError evidence](findings/2026-10-20-console-serror.md) supersedes
  older suggestions in [the boot reference](REFERENCE-boot-testing.md).
- Keep all run evidence under `artifacts/snapshot60/`. Do not delete or
  overwrite boot images, media, logdumps or captures. They are not backed up
  by these commits. Clear logdump only on explicit request, after archiving.
- Inspect history, effective donor and upstream/AOSP before conclusions.
  Say **unverified** where proof is missing. No attribution trailers.
- Package from a real known-good image, never a reconstructed capture.
  Preserve its policy, ramdisk and init behavior. See
  [driver forward-porting](REFERENCE-driver-forward-porting.md) and
  [build instructions](../BUILD_TISSOT.md) before implementation/build work.

## Source checkpoint

Branch: `ack-camera`. Earlier user commits end at `6b7fe2b3628d` (UBSAN off
for image size), following native VFE/ISPIF and CPP power-domain conversions.
The session's pending work is now separated into these commits:

| Commit | Change |
| --- | --- |
| `032529e8d` | Host VFE/ISPIF power, pixel-probe and SMMU regression tests |
| `38cb1990e` | Correct static SMMU register dump and failure tests |
| `0ba1142af` | Restore donor 32-bit timestamp/ioctl/event layouts |
| `37d207627` | CPP publication, allocation/cleanup and snapshot-ready gating |
| `ec8ac3f59` | CPP DT resources and APPS bank `0x12` / IRQ 109 |
| `906b00d7f` | CPP/VPE vendor `entity.revision` subdevice-number ABI |
| `b74883f50` | QRD sensor mount angles `[90,90,270]`; not boot-tested |

Kernel #43 identifies as `6.12.93-4k-g6b7fe2b3628d-dirty`, built
2026-10-24 00:48:06 +0545. The first six commits above organize changes
already present during the observed progression. The dirty build ID does not
prove an exact source snapshot; no packaged-image hash was associated with
these #40–43 captures. Individual commits were not boot-tested in isolation.
No new kernel build or phone boot was performed by the agent.

Current config enables VFE and CPP and retains KASAN and KALLSYMS_ALL;
UBSAN is off. Check the next image header size against the wrapper's
bootloader limit; do not infer that a future image fits from #43 booting.

## Evidence to keep

Paths below are relative to `porting/`. Each capture retains original logs;
the JPEG/MP4 originals were copied read-only and not repaired in place.

| Capture | What it establishes |
| --- | --- |
| [Stock 4.19](artifacts/snapshot60/stock419-camera-20261023T143434Z/) | Working stock camera, CPP version `0x40030003`, three cameras, stock zoom/orientations and library comparisons |
| [Kernel #40](artifacts/snapshot60/camera-capture-20261023T180742Z/) and [app log](artifacts/snapshot60/camera-app-20261023T180852Z/) | Old metadata ENOTTY/bad event fields; no CPP DT; static routing |
| [Compat audit](artifacts/snapshot60/camera-compat-audit-20261023T181111Z/) | Donor wire layouts, converters, sanitizer results and failing original-header controls |
| [Kernel #41](artifacts/snapshot60/camera-capture-20261023T182354Z/) | Earlier metadata failures absent in retained capture, but pproc links fail; CPP still absent |
| [CPP preflight](artifacts/snapshot60/camera-cpp-preflight-20261023T183544Z/) | DT baseline/candidate, schema limitations, source patch and fault tests |
| [Kernel #42](artifacts/snapshot60/camera-cpp-capture-20261023T184546Z/) | CPP bound at subdev16 but blank preview; library disassembly and revision ABI proof |
| [Kernel #43](artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/) | CPP hardware initialization, working preview report, JPEG/video evidence and unbooted orientation patch |

The #43 directory contains `identity.txt`, `logdump-prefix.txt`, original
64 MiB `logdump.bin`, later `logdump-after-191127.bin`, live/post-use logcat,
`camera-after-191127.txt`, `codecs-191127.txt`, `encoder-config.txt` and
`saved-media/`. The saved-media directory includes hashes/remote paths,
decoder output, marker analysis and the read-only libjpeg diagnostic.
Preserve these local artifacts separately when moving machines.

## What the fixes establish

The compat import used native `__kernel_old_timeval` in 32-bit structures.
`old_timeval32` restores buffer-info size 100 and GET_BUF32 `0xc06456e1`,
along with ISP event/CPP frame offsets. Native UAPI remains unchanged.

Captured static routing agrees across #40/#41: CPP SID `0x1c00` goes to
bank `0x12`, JPEG `0x1800` to `0x13`, and VFE `0x400`/`0x2800` to `0x14`.
The target qcom_iommu binding takes the bank ASID, not a donor SID.

The installed CPP library saves `entity.revision` and opens
`/dev/v4l-subdev<revision>`. The donor supplies `devnode->num`; the port
previously returned zero. The optional camera callback now restores that
behavior for CPP/VPE only. Native media devices keep revision zero. The
failing daemon open was not straced, so do not claim a directly observed
wrong open. #43 logs CPP hardware version `0x40030003` at about 28 seconds
and the user confirms previews after the combined changes.

CPP registers at late_initcall only after
`ramoops_wait_snapshot_ready(10000)` succeeds. This guards CPP registration
and hardware access, not the earlier camera/APPS context probes.
`RAMOOPS_PERIODIC_SNAPSHOTS` is currently **1**. Logdump flash is the usable
cross-boot channel; RAM pstore does not survive bootloader handoff. The live
`/sys/kernel/ramoops_raw` attribute exposes the current console ring.

See [CPP findings](findings/2026-10-24-camera-cpp-isolation.md) for donor,
upstream and evidence details. Known diagnostic limitation: the static dump
maps APPS GR0 while its SoC-gated caller can be the GPU IOMMU instance; its
runtime-PM reference does not prove ownership of APPS power. This remains a
source-review item, not an established camera failure cause.

## Next work, in order

1. **Orientation:** await the user's requested build/boot of `b74883f50`.
   Keep this as the single change against the preview milestone. Check rear
   orientation/motion, then front as control; capture HAL orientations.
   Donor `tissot-titanium.dts` includes the QRD sensor base, not MTP. The
   older restoration `8e6263ae9919` used the wrong base. Do not compensate
   with gyro/app changes before validating the corrected DT metadata.
2. **JPEG:** inspect the existing evidence before enabling hardware. Logcat
   fails opens of `/dev/jpeg0` and `/dev/jpeg1`, then uses a software/hybrid
   fallback which reports success. JPEG DT nodes are currently absent.
   Both saved files have SOI/EOI and restart markers but no DRI segment.
   The host diagnostic's one-MCU-row interval override reduces warnings
   from 162 to 0 for the 5 MP sample and 252 to 3 for 12 MP. This proves a
   malformed stream and a partial explanation, not a complete repair or
   the responsible encoder/header code. Audit donor JPEG resources,
   power/clocks, bank `0x13`/IRQ 110, ABI and buffer ownership before
   proposing activation. Do not edit the originals or vendor binaries.
3. **Video encoder selection:** metrics confirm `c2.android.avc.encoder`,
   1080p AVC; the second completed session explicitly has `hardware=0`.
   Configuration advertises `OMX.qcom.video.encoder.avc`, so missing XML is
   not established. Compare queried capabilities, Aperture selection and
   initialization with stock before changing VIDC or codec policy. VIDC
   IOVA (`b64b87a7e7e4`) and compat-plane (`793615c17e5f`) fixes already
   exist. Both MP4s decode; one has a duplicate timestamp warning.

Stock has three cameras and additional sensor/EEPROM/flash nodes; ACK #43
exposes two. Do not enable those alongside the next isolated fix. Zoom
capabilities were captured earlier; full zoom behavior is not qualified by
working preview. Generic vendor ERROR logs can also occur on working stock.

## Focused checks and remaining limits

Fresh commit-time host checks: **41 camera tests plus one routing test pass**.
CPP, time32 and media ABI tests also pass ASan/UBSan with leak checking when
run outside the sandbox; LeakSanitizer cannot run under sandbox ptrace.
The combined C/header/DTS diff passes strict checkpatch. Full per-commit
checks have zero errors but warn about long evidence/reference lines,
SPDX tags absent from the host tests, the new-file MAINTAINERS reminder,
and undocumented legacy CPP/camera-SMMU compatibles. These warnings remain;
do not describe the full series as warning-free.

```sh
python3 -m unittest discover -s porting/tests -p 'test_camera_*.py'
python3 porting/tests/test_qcom_iommu_routing.py
env CAMERA_TEST_SANITIZERS=address,undefined ASAN_OPTIONS=detect_leaks=1 \
  python3 -m unittest discover -s porting/tests -p 'test_camera_cpp_probe.py'
env CAMERA_TEST_SANITIZERS=address,undefined ASAN_OPTIONS=detect_leaks=1 \
  python3 -m unittest discover -s porting/tests -p 'test_camera_compat_time.py'
env CAMERA_ABI_CFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' \
  ASAN_OPTIONS=detect_leaks=1 python3 porting/tests/test_camera_media_abi.py
```

These are host harnesses, not a kernel build or device proof. The DT test
uses the existing dtc binary to compile a standalone board description.
Donor-dependent tests require the sibling `../oc-test` tree. DTC baseline
and CPP candidate both have 21 warning lines. Focused core/qcom-IOMMU schema
validation adds 15 untyped legacy CPP diagnostics plus 15 reference lines;
this was not a clean schema run or full dtbs_check. No new kernel compile,
Sparse run, hardware stability qualification or orientation boot test has
been performed for these commits.
