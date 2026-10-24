# Run385: CSI receivers absent after sensor identification

Kernel `6.12.93-4k-ga791620db3c5 #30` reaches Android boot completion.
Android enumerates two cameras. Subdevice names identify `ov12a10` and
`s5k5e8_ofilm`, and CCI reads hardware version `0x10020005`.
This establishes discovery, not working preview or capture.

Evidence: `porting/artifacts/snapshot60/camera-capture-20261023T083757Z/`.
`camera.txt` records two devices and the subdevice names. `logcat.txt:4018`
records `csid_open: failed`; subsequent lines report missing ISPIF/ISP and
CPP devices. `csi-discovery.txt` shows registered CSID/CSIPHY drivers, no
corresponding platform devices or DT nodes, and only the sensor/control
subdevices. The missing hardware descriptions are the immediate CSI
discovery blocker; the userspace open errno was not captured.

## History and scope

`2d48ee98d4e9` imported the CCI and board camera descriptions without the
donor's three CSIPHY and three CSID nodes. `7fde5eeb61ab` intentionally
excluded VFE/ISPIF and CPP while reaching the sensor-identification milestone.
`9e6bab38f80c` corrects earlier size measurements: the build wrapper must
retain Rust/ashmem when resolving the configuration. Run385's wrapper reports
`image_size=53870592`, limit `54001664`, headroom `131072` bytes. This is the
old image's measurement, not proof that a future full-pipeline build fits.

The next source stage restores the six CSI receivers only. It does not
enable ISP/CPP, add GDSC regulator adapters or change the kernel configuration.
The earlier claim that CSID/CSIPHY initcalls were safe concerned driver
registration; absent DT nodes meant their hardware probes had not run.

## Probe IRQ safety

Both CSI probes requested an enabled IRQ and then disabled it. Their handlers
access MMIO; CSID also selects its register description after the request.
A pending IRQ could run before runtime clocks or register state are ready.
This source-confirmed window has not been reproduced as a CSI device crash.

Register with `IRQF_NO_AUTOEN` and remove the initial disable, following the
CCI correction. Runtime enables and disables are unchanged, preserving the
initial disable depth. Existing trigger flags are unchanged. A host test
executes each actual registration statement with a modeled pending interrupt
and verifies no extra probe-time disable remains.

## S3 voltage translation

The donor CSID nodes request exactly 1,225,000 microvolts from PM8953 S3.
This port's board and upstream tissot constrain S3 to 1,224,000 microvolts.
`rpm_pm8953_regulators` uses `pm8998_hfsmps` for S3: its linear range starts
at 320,000 microvolts with 8,000-microvolt steps. 1,224,000 is representable;
1,225,000 is not. Copying the donor's exact request would fail the provider
constraint/selector checks when the CSID configures its supply.

The restored CSID descriptions request the existing 1,224,000 value. The
shared S3 regulator constraints and provider driver are unchanged. Hardware
CSI operation at this existing rail value remains unverified on this build.

## Donor and upstream references

- `../oc-test/arch/arm64/boot/dts/vendor/qcom/msm8953-camera.dtsi` supplies
  all six nodes, with board overrides checked in `mi8953/tissot/camera.dtsi`.
- `../oc-test/techpack/camera-legacy/sensor/{csid,csiphy}/` contains the
  inherited probe behavior.
- [AOSP camera DT](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-baiji-4.9-pie-wear-dr/arch/arm64/boot/dts/qcom/msm8953-camera.dtsi).
- [Upstream tissot S3 constraint](https://android.googlesource.com/kernel/common/+/refs/heads/upstream-master/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts).
- [Upstream IRQ APIs](https://docs.kernel.org/core-api/genericirq.html).
- Target `drivers/clk/qcom/gcc-msm8953.c`,
  `include/dt-bindings/clock/qcom,gcc-msm8953.h`, and
  `drivers/regulator/qcom_smd-regulator.c` verify the translations.

## Verification and limits

All 22 camera host tests pass. They cover the IRQ window, all receiver
resources and sensor-route indexes, clock name/rate counts and GCC symbols,
and the S3 provider range. Strict checkpatch and added-line API scanning pass
for the IRQ patch. DT strict checkpatch passes. Effective donor properties
match after GCC symbol translation, `ok` to `okay`, and the explicit voltage
translation. Records are under `porting/artifacts/snapshot60/`:

- `run385-csi-donor-parity.json`.
- `run385-csi-{baseline,updated}-dtc.log`: direct board preprocessing and dtc
  compilation succeed, with no new warnings.
- `run385-csi-{baseline,updated}-schema.log` and
  `run385-csi-schema-delta.json`: schema validation is not clean. The delta
  has 15 raw-property type diagnostics for `cell-index`, `qcom,clock-rates`
  and `qcom,csi-vdd-voltage`, which lack legacy CSI binding definitions.
  A zero validator exit code does not mean these reports are clean.

No kernel build, Sparse, make-based dtbs_check, image packaging or device
boot of these changes was performed. The source is not boot-tested. Receiver
probing, CSI initialization, streaming and capture require later evidence;
ISPIF/VFE/CPP remain separate work. Hardware console output stays forbidden.
