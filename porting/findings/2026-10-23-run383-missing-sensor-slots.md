# Run383: sensor slot definitions omitted during DT import

Run383 reached `sys.boot_completed=1`; qcamerasvr remained running, but
`dumpsys media.camera` reported zero cameras. The current logdump records
`failed: s_ctrl ... for camera_id 0` at line 3880 and camera_id 2 at lines
3896 and 3899, followed by sensor-init ioctl failures with `-EINVAL`.

Evidence lives under `porting/artifacts/snapshot60/`:

- `run383-live-20261023T081327Z/identity.txt` and `camera.txt`.
- `run383-live-20261023T081327Z/sensor-platform-dt.txt` and its stderr file.
- `run383-logdump.bin`, `run383-logdump.log`, and `run383-ramoops.json`.
- `run383-sensor-donor-parity.json`, `run383-sensor-dt-check.log`, and
  `run383-sensor-dt-baseline-check.log` cover the proposed source changes.

## Confirmed registration blocker

The live DT contains three `qcom,camera@N` children under CCI. All three
lack `compatible`, `reg`, and `cell-index`. The sensor platform driver
exists at `/sys/bus/platform/drivers/qcom,camera`, but there are no camera
slot platform devices. Linux 6.12 `drivers/of/platform.c` explicitly skips
nodes without `compatible` during strict platform population.

History: commit `2d48ee98d4e9` imported tissot's camera board overrides but
omitted their inherited definitions from the donor's
`arch/arm64/boot/dts/vendor/qcom/msm8953-camera-sensor-mtp.dtsi`.
Those base definitions also provide mandatory CSI indexes, supply arrays,
clock names/rates, pinctrl names, and reset indexes. Adding only compatible
would expose further parse failures rather than restore a usable slot.

The repair restores the effective donor base plus tissot overrides for all
three slots, translating clock symbols to this GCC and continuing to omit
unsupported LED-flash references. All 33/31/32 effective properties match
the respective donor slots after those explicit normalizations.

The six EEPROM clock source references also used CAMSS_GP0/GP1, unrelated
to the existing MCLK branches. GCC defines MCLK0/1/2 sources and parents
each MCLK branch to its corresponding source. Correct those six references
and use the same source/branch pairing for the three restored slots.
The old source mismatch is confirmed; its hardware effect is unverified.

## Probe failure safety

The parser previously published `g_sctrl[id]` before either probe acquired
its clocks. A clock failure freed the controller while leaving that slot
pointer and device driver data behind. This is a source-confirmed dangling
pointer path, not a reproduced run383 crash: the slots never existed there.

Publish only after clocks and device setup succeed. On failure, release the
parsed CCI client, GPIO tables, regulator descriptions, sensor information,
mutex and I2C client, and clear device data. The clock helper already unwinds
its own devm allocations; failed-clock cleanup must not release them again.
Use the parsed-state cleanup for default-parameter initialization failures
as well, including the previously leaked sensor_info allocation.

## References and checks

- Donor: `../oc-test/arch/arm64/boot/dts/vendor/qcom/` base sensor file and
  `mi8953/tissot/camera.dtsi`, plus `camera_v2/sensor/msm_sensor_driver.c`.
- [AOSP MSM8953 sensor definitions](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-baiji-4.9-pie-wear-dr/arch/arm64/boot/dts/qcom/msm8953-camera-sensor-mtp.dtsi).
- [Upstream DT APIs](https://docs.kernel.org/devicetree/kernel-api.html).
- Local `drivers/of/platform.c`, `drivers/clk/qcom/gcc-msm8953.c`, and
  `drivers/media/platform/msm/camera/common/cam_soc_api.c`.

18 camera host tests pass, including actual platform/I2C probe bodies with
mocked parsing and clocks: allocation, parse, deferred-clock and invalid-clock
failures, plus successful publication. DT resource tests cover all slots,
regulator-array lengths and all nine MCLK source/branch pairs. Direct clang
preprocessing and dtc compilation of the board succeed. The remaining dtc
warnings are present in the pre-change baseline; three missing-reg warnings
for the slots disappear. This is syntax checking, not schema validation.

No kernel build, Sparse, dtbs_check, or device boot of these changes has run.
No image was repackaged. Restoring compatible permits previously absent slot
probes and userspace sensor identification on the next authorized build;
successful identification and capture remain unverified.
