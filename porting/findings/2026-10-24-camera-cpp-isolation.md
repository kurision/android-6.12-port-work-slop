# Tissot camera: CPP routing, ABI recovery and working preview

Status, 2026-10-24: the user's kernel #43 reaches CPP hardware initialization
and working front/rear preview after the combined CPP and vendor-ABI changes.
Kernel #42's blank preview is the earlier checkpoint documented below.
Rear orientation, corrupt JPEGs and software AVC selection remain separate
open issues; see [preview/capture evidence](2026-10-24-camera-preview-capture.md)
and the [session handoff](../HANDOFF-camera-2026-10-24.md).

The changes are now committed as `032529e8d`, `38cb1990e`, `0ba1142af`,
`37d207627`, `ec8ac3f59` and `906b00d7f`. The later orientation correction,
`b74883f50`, was not part of #43 and is not boot-tested. The agent ran no
kernel build or phone boot, and individual commits were not boot-tested
in isolation.

## What was observed

The working 4.19 baseline registers a `cpp` subdevice and reports hardware
version `0x40030003` in
[stock dmesg](../artifacts/snapshot60/stock419-camera-20261023T143434Z/dmesg.txt)
at line 918. Its postprocessing chain includes `c2d -> cpp` in
[stock logcat](../artifacts/snapshot60/stock419-camera-20261023T143434Z/logcat-after.txt)
at lines 15504, 15519 and 20615. The user exercised preview, camera
switching and zoom on this baseline.

The three checked HAL/MCT/ISP libraries have identical hashes on stock and
the earlier ACK capture; see
[baseline comparison](../artifacts/snapshot60/stock419-camera-20261023T143434Z/baseline-comparison.json).
This comparison does not establish that every camera userspace component
or runtime setting is identical.

ACK kernel #41 identifies itself as
`6.12.93-4k-g6b7fe2b3628d-dirty`, built 2026-10-24 00:06:29 +0545:
[identity](../artifacts/snapshot60/camera-capture-20261023T182354Z/identity.txt).
The dirty suffix matters: the commit ID alone does not identify the exact
running source. No packaged image hash was associated with this capture.

Both VFEs, their common parent, ISPIF and the VFE camera-SMMU context bind.
The `msm_cpp` driver directory exists but has no bound device, and no `cpp`
subdevice appears in
[bindings](../artifacts/snapshot60/camera-capture-20261023T182354Z/bindings.txt).
`CONFIG_MSM_CAMERA_CPP=y` was enabled by commit `28b40fcdad98`, but the
camera DTSI intentionally has no `qcom,cpp` node. Compiling the driver did
not enable its hardware probe.

During the #41 app test, the HAL logs `c2d -> c2d`, then fails the
`pproc -> imglib` link. The first retained sequence is at lines 44169-44195
of [live logcat](../artifacts/snapshot60/camera-capture-20261023T182354Z/logcat-live.txt).
Both camera IDs subsequently receive `ERROR_CAMERA_DEVICE`; Aperture
reconnects and the user sees no preview. This establishes the failing
stage, not that missing CPP is the complete cause.

The missing CPP node and the different postprocessing chain make CPP the
next isolated bring-up target. Other causes of link rejection remain
unverified.

## SMMU routing recovered across two boots

The initial dump helper from `62620e86c063` read offset zero and interpreted
bits 31:24 as the mapping count. Upstream and donor define ID0 at offset
`0x20`, with NUMSMRG in bits 7:0. The correction also checks runtime
resume before MMIO, filters SMR_VALID, and prints ID0/count even when there
are no valid routes. Extracted-function tests cover these paths.

The primary logdump prefix preserved the following routes on both #40 and
#41. The decoded S2CR type is 0 (translation).

| Client from donor DT | SMR | SID | S2CR | Context bank |
| --- | --- | --- | --- | --- |
| CPP | 34 | `0x1c00` | `0x30000012` | `0x12` / 18 |
| JPEG encoder | 35 | `0x1800` | `0x30000013` | `0x13` / 19 |
| VFE | 36 | `0x0400` | `0x30000014` | `0x14` / 20 |
| VFE | 37 | `0x2800` | `0x30000014` | `0x14` / 20 |

Evidence:

- [#40 primary prefix](../artifacts/snapshot60/camera-capture-20261023T180742Z/logdump-prefix.txt),
  lines 139-148, at about 4.845 seconds.
- [#41 primary prefix](../artifacts/snapshot60/camera-capture-20261023T182354Z/logdump-prefix.txt),
  lines 144-153, at about 5.876 seconds. Line 39 reports
  `ID0=0x7c017e7a NUMSMRG=122`.
- Each capture directory contains the original 64 MiB `logdump.bin` and
  decoded snapshot reports. Periodic snapshots are live samples, not
  crash records; the primary prefix is the routing evidence here.

The printed device prefix is `soc@0:iommu@1c48000` (GPU). The helper maps
the hardcoded APPS global-register address `0x01e00000`; the prefix names
the device executing the helper, not the register block being read.
The helper is SoC-gated, not APPS-instance-gated. Do not interpret these
entries as GPU stream routes, or claim that its runtime-PM reference
belongs to the APPS instance. This diagnostic ownership issue remains a
separate source-review item; it is not an observed preview failure cause.

The donor's stream IDs come from
`../oc-test/arch/arm64/boot/dts/vendor/qcom/msm8953-camera.dtsi`.
Its `msm-arm-smmu-8953.dtsi` supplies an ordered context-interrupt list;
zero-based bank 18 uses `GIC_SPI 109`, followed by bank 19 / IRQ 110 and
bank 20 / IRQ 111. The existing port VFE context already uses bank `0x14`
and IRQ 111.

The target qcom_iommu `get_asid()` derives ASID from the child `reg` offset
divided by `0x1000`; `of_xlate()` takes one ASID argument. Therefore a CPP
camera context must refer to `<&apps_iommu 0x12>`, backed by an APPS child
at offset `0x12000`. The existing parent starts its context range at
`0x01e20000`, giving physical bank address `0x01e32000`. Passing donor SID
`0x1c00` directly to this driver would use the wrong binding.

The routing registers establish the bank selection. They do not prove
CPP page-table programming, DMA mapping, fault handling or successful
image processing on ACK.

## Compat correction and its observed limits

Before the timestamp correction, #40 repeatedly logged metadata buffer
retrieval failure with `ENOTTY`, starting at line 14537 of
[app logcat](../artifacts/snapshot60/camera-app-20261023T180852Z/logcat.txt).
It also logged malformed event fields and capture-request timeouts.

The import substituted native-width `__kernel_old_timeval` for the donor's
8-byte `compat_timeval`. The resulting buffer struct was 112 bytes rather
than 100, changing GET_BUF32 from `0xc06456e1` to `0xc07056e1`. The same
substitution shifted ISP/ISP32 events and CPP frame fields. The committed
three-header correction uses `old_timeval32`, preserving the donor ABI.

[Host evidence](../artifacts/snapshot60/camera-compat-audit-20261023T181111Z/)
includes donor layout comparisons, actual ioctl-dispatch and event-dequeue
tests, ASan/UBSan results, and negative controls: the original headers fail
buffer dispatch and both ISP event conversions at runtime assertions.
The nearby internal legacy headers otherwise match the donor apart from
the timestamp type replacements and explicit time32 includes.

Those specific metadata ENOTTY, invalid-statistics-mask, uncleared-mask and
capture-timeout messages are absent from the retained #41 live capture.
That observation supports the correction, but does not establish complete
camera recovery: stream-link failures remain, and CPP is still absent.

## Kernel #42: CPP binds, but its discovery ABI is incomplete

The user's next build is
`6.12.93-4k-g6b7fe2b3628d-dirty #42`, built 2026-10-24 00:26:34 +0545.
[Its capture](../artifacts/snapshot60/camera-cpp-capture-20261023T184546Z/)
contains identity, driver bindings, logdump, live logcat/dmesg and post-open
camera/IRQ state. CPP and its camera-SMMU context bind, and CPP publishes
`v4l-subdev16`. The three checked library facts are distinct: CPP is bound,
its library is loaded by the daemon, and media enumeration exposes group 9.
None by itself establishes successful CPP userspace initialization.

Stream-on succeeds; metadata SOFs advance normally and camera service
counts output frames. The user still sees no preview. C2D repeatedly logs
`pp_buf_mgr_get_buf: invalid steam info params` (the spelling in the
installed library), starting at line 27631 of
[live logcat](../artifacts/snapshot60/camera-cpp-capture-20261023T184546Z/logcat-live.txt).
The same capture has no earlier metadata ENOTTY or malformed-mask messages,
and no `ERROR_CAMERA_DEVICE`. The working stock capture has no matching
postprocessing buffer failure. Output-frame counts do not prove correct
pixel contents.

### Missing donor revision semantics

The donor CPP probe sets:

```
cpp_dev->msm_sd.sd.entity.revision = cpp_dev->msm_sd.sd.devnode->num;
```

This is at line 4341 of
`../oc-test/techpack/camera-legacy/pproc/cpp/msm_cpp.c`. The donor VPE does
the same at line 1600 of `pproc/vpe/msm_vpe.c`; the nearby donor source
search found no other camera entity-revision assignments.

The installed CPP library was archived with SHA256
`293cd7334b3f332c033a6b043ea2b553ff90147e31e281dfb04c522e6bfd8770`.
Its Thumb disassembly shows:

- `cpp_hardware_create` at `0x1a60a` saves the entity's revision field
  after matching type `0x20000` and CPP group 9.
- `cpp_hardware_open_subdev` at `0x1a8b2` loads that saved value,
  formats `/dev/v4l-subdev%d` at `0x1a8be`, and opens it at `0x1a8c8`.
- The format string is at virtual address `0x42196`.

[Live media enumeration](../artifacts/snapshot60/camera-cpp-capture-20261023T184546Z/media-enum-current.txt)
identifies CPP as entity 19, name `v4l-subdev16`, type `0x20000`, group 9,
device `81:19`. Its subdevice number is 16, not its device minor 19.
The diagnostic did not print revision itself; revision zero is established
by the target media ioctl's unconditional source assignment, not by a
directly captured revision value or a traced daemon `open()`.

With that source value, the installed library's selection logic produces
`/dev/v4l-subdev0` rather than `/dev/v4l-subdev16`. See the archived
[path audit](../artifacts/snapshot60/camera-cpp-capture-20261023T184546Z/revision-path-audit.json)
and `libmmcamera2_cpp_module.so.disasm.txt` in the same directory. This is
a confirmed lost vendor ABI behavior. The later #43 capture and user report
establish CPP initialization and working preview after the combined changes;
they do not provide the missing daemon-open trace or an isolated A/B test.

The committed fix extends the existing optional `legacy_entity_info`
callback with a nullable revision output. The media core initializes it
to zero; only the Qualcomm camera callback supplies `sd->devnode->num`
for CPP/VPE when a devnode exists. Other camera groups and media devices
without the callback retain revision zero. This preserves the upstream
default: [MEDIA_IOC_ENUM_ENTITIES documentation](https://docs.kernel.org/userspace-api/media/mediactl/media-ioc-enum-entities.html)
defines revision as obsolete/zero, whereas the donor overloads it.
Graph IDs, topology ioctls and the userspace structure layout are unchanged.

The real-media-ioctl host test now covers native/compat CPP/VPE selection,
dynamic node-number changes, a minor different from the node number,
missing devnodes, ID-only lookups and revision-zero defaults. ARM32 and
ARM64 compile-time checks retain a 256-byte entity descriptor with revision
at offset 40. ASan/UBSan with leak checking pass. The
[forced-zero negative control](../artifacts/snapshot60/camera-cpp-capture-20261023T184546Z/revision-zero-negative-control.log)
fails the CPP path-selection assertion as expected. All 41 camera host
tests plus the routing test pass. No kernel build or device boot of this
revision correction was run by the agent.

## CPP hardware addition used by kernels #42 and #43

The user approved the following DT/driver/test changes, then built and
booted kernels #42 and #43. CPP was the only new camera hardware device
enabled by this stage. The list records that implementation and its checks.

1. In `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi`, add only
   the donor CPP device and its required SMMU path: APPS context bank
   `0x12` / IRQ 109, camera context label `cpp`, and CPP at `0x1b04000`
   with its donor VBIF/HW windows, IRQ 49, GCC clocks, microcontroller
   reset and firmware-payload properties. Use `CPP_GDSC` through the GCC
   power-domain provider. The obsolete GDSCR mapping must not bypass genpd
   ownership. JPEG/FD/sensor additions are separate hardware changes.
2. Keep the donor's six advertised CPP rates, 100-465 MHz, which exist in
   the target GCC table. The donor's initial 180 MHz request passes through
   `clk_round_rate()` before `clk_set_rate()` in the camera clock helper;
   the actual selected ACK rate has not been measured on this device.
3. Delay CPP driver registration to `late_initcall` and use the existing
   `ramoops_wait_snapshot_ready(10000)` gate, following EEPROM. Skip
   registration on readiness failure. This keeps the first CPP MMIO test
   behind a usable flash evidence channel; initcall level alone does not
   establish snapshot readiness. Preserve `console=ttynull` only.
4. `cpp_open_node()` now releases successfully initialized hardware when
   `cpp_init_mem()` fails, before clearing its opener/subscription state.
   The host test covers hardware-init failure, memory-init failure,
   successful first/second open and the opener limit. This source defect
   was not observed as the current app failure.
5. Check resolved DT resources/providers, bank/IRQ pairing, clock/reset
   names, payload values, registration gating and probe failure paths.
   Existing CPP host hardening covers 62 scenarios in native/compat modes;
   it does not replace a kernel compile or hardware test. Report legacy
   schema diagnostics honestly rather than claiming a clean dtbs_check.
6. User-authorized build and user-executed RAM-only boot. Capture CPP bind,
   HW version, IOMMU context, firmware selection, camera chain and first
   request/preview outcome. A clean probe is not proof of streaming.

### Validation of the prepared change

[CPP preflight evidence](../artifacts/snapshot60/camera-cpp-preflight-20261023T183544Z/)
contains baseline/candidate preprocessed DTS and DTBs, DTC output and schema
diagnostics. Tests compare CPP clock rates, bus vectors and firmware-payload
values against the donor and resolve GCC clock/reset/domain phandles, the
CPP camera ASID and bank IRQ. All 41 camera host tests and the routing test
pass. The four CPP tests also pass ASan/UBSan with leak checking, including
62 probe scenarios in each native/compat mode, snapshot gating and the
open-failure case. Strict checkpatch on the combined C/header/DTS diff and
`git diff --check` pass. Full per-commit checkpatch has zero errors and the
remaining metadata/test-license/legacy-binding warnings recorded in the
[handoff](../HANDOFF-camera-2026-10-24.md).

DTC reports 21 warning lines for both baseline and candidate. Focused
validation using `qcom,iommu.yaml` plus the core schemas emits 30 additional
lines: 15 untyped legacy CPP property diagnostics with their schema-source
lines. It emits no additional simple-bus or `iommu-ctx@12000` diagnostics.
This is not a clean schema run or a full `dtbs_check`; the custom legacy
CPP binding is not covered by this focused schema set.

CPP's gate covers its own driver registration and hardware access. Adding
the APPS context and camera-SMMU child also exercises their existing probe
paths; those paths do not gain a snapshot gate in this patch. A successful
registration gate must not be described as guarding every IOMMU probe.

The agent did not run a kernel compile, Sparse check or phone boot. The
user's #42 boot establishes CPP registration; #43 additionally records CPP
hardware version `0x40030003` and user-confirmed preview on both cameras.
These are combined-series observations, not standalone commit validation or
qualification of every firmware/DMA path. Latest evidence is in
[the #43 capture](../artifacts/snapshot60/camera-cpp-capture-20261023T190618Z/).

## Source cross-checks

- Donor:
  `../oc-test/techpack/camera-legacy/pproc/cpp/msm_cpp.c`,
  `msm_cpp_soc.c`, and the two DTSI files named above.
- Target:
  [qcom_iommu](../../drivers/iommu/arm/arm-smmu/qcom_iommu.c),
  [GCC](../../drivers/clk/qcom/gcc-msm8953.c),
  [CPP](../../drivers/media/platform/msm/camera/pproc/cpp/msm_cpp.c),
  [clock helper](../../drivers/media/platform/msm/camera/common/cam_soc_api.c).
- [Linux v6.12 SMMU register definitions](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/iommu/arm/arm-smmu/arm-smmu.h)
  establish ID0, NUMSMRG, SMR_VALID and S2CR bank/type fields.
- [Linux v6.12 qcom_iommu](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/iommu/arm/arm-smmu/qcom_iommu.c)
  establishes the one-ASID binding and context-bank numbering.
- [Linux v6.12 time32 definitions](https://raw.githubusercontent.com/torvalds/linux/v6.12/include/vdso/time32.h)
  and [native legacy timeval](https://raw.githubusercontent.com/torvalds/linux/v6.12/include/uapi/linux/time_types.h)
  establish the timestamp widths. Online AOSP mirrors were unavailable
  through the web tool during this audit; local donor and target sources
  supplied the vendor comparison.
