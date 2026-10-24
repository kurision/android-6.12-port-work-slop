# run368camera: CCI probe failure and missing wireless firmware

## Evidence and limits

The device runs `6.12.93-4k-g0423a9133d37 #18`, slot B. Host evidence is
preserved under
`porting/artifacts/snapshot60/run368camera-investigation/` (gitignored).
No boot, flash, firmware restart, service restart or SELinux change was
performed. Two explicit CCI bind attempts reproduced the already-unbound
device's failure; these are the only device writes in this investigation.

- `cci-bind-attempt.txt:21`: `msm_cci_probe: no irq resource?` at 339.665 s.
- `cci-bind-repeat.txt:2`: the same failure at 705.726 s.
- `cam-core.txt:7-10`: CCI exists, but no `qcom,msm-cam` device exists.
- `probes.txt:36-55`: camera drivers are registered, not evidence of binding.
- `remoteproc.txt:67-71`: `/dev/smd2` and `/dev/smd3` exist; MSS and ADSP
  run, WCNSS is offline. `cci-bind-repeat.txt:3-6` independently confirms
  that the offline remoteproc requests `wcnss.mdt`.
- `wireless-state.txt:2-14`: no WLAN interface.
- `logcat.txt:14030-14037`: Bluetooth reports initialization failure and
  kills its daemon to recover from stuck firmware download. This is an
  observation, not proof that no other Bluetooth defect remains.
- `logdump-strings.txt:75-82`: the primary recorder overran the boot log
  between 0.888 s and 31.708 s. Do not claim an observed early WCNSS load
  errno from this capture.

## Wireless: packaging regressed in the new worktree

Main's `package-run364.json` lists 17 WCNSS/NV/Venus firmware files;
`package-run368camera.json` lists none. Main's run364 embedded config has
`CONFIG_EXTRA_FIRMWARE="wlan/prima/WCNSS_qcom_wlan_nv.bin"`; run368camera
has an empty string. The staging directories are gitignored, so merging
main did not copy them. The script warned and still reported success.

History already documents why both stages are required:

- `7c15158655be`: embed the NV calibration because requests after
  switch_root cannot use the old ramdisk; the vendor symlink into persist
  was denied to kernel firmware-loader credentials on run304.
- `211b2000879b` and `a474b142696f`: QTI Bluetooth uses the WCNSS SMD packet
  transport, with the controller observed ON on run334.

The staging trees have been copied from main without overwriting differing
files. All 17 staged files were then compared byte-for-byte against the
ramdisk extracted from main's actual `boot-run364.img`, whose SHA256 is
`5f0767c42e9efb9ea07dae7e7abf85cf356fb2e40851c7b80ba7541607f97bfe`.
See `firmware-known-good.sha256` in the evidence directory. This is a
comparison with a real artifact, not a reconstructed base image.

`build-kernel.sh` now rejects missing or empty WCNSS/NV/Venus inputs before
changing the output config or starting a build. It no longer silently
disables embedded NV or omits the firmware directories. Runtime recovery
is **unverified** until a new correctly packaged image is booted.

## Camera: IRQ lookup, absent core and registration prerequisites

1. `legacy_msm_camera_get_irq()` used
   `platform_get_resource_byname(..., IORESOURCE_IRQ, ...)`. Since v5.18,
   OF platform devices have no statically populated IRQ resources. Main
   already fixed the identical donor assumption for VIDC in `bd462f2f1cb3`.
   CCI reaches exactly this failing lookup on the phone, twice.

   The shared helper now uses `platform_get_irq_byname()`, keeping the
   donor's resource-shaped handle as a device-managed allocation. All nine
   callers now check ERR_PTR and retain the original errno, including
   `-EPROBE_DEFER`. Register/enable/disable/free continue to use the same
   mapped interrupt; callers must not free the handle themselves.

2. The donor's `qcom,msm-cam@1b00000` node was omitted. Without it,
   `msm_probe()` never initializes the shared V4L2 device and sensor-init
   registration cannot succeed. Restore the node and its bus vote table
   from `../oc-test/arch/arm64/boot/dts/vendor/qcom/msm8953-camera.dtsi:15-22`.

3. The same donor DTS at lines 503-557 supplies CCI timing properties that
   were omitted from the imported empty mode nodes. Restore all four
   tables and the donor's enabled/disabled states; no timing is guessed.

4. Adding the core would expose further source-level registration defects:
   the config media device was registered before initialization; the sensor
   media device was initialized before setting its parent (6.12 uses that
   parent to derive bus_info); and all four non-subdev video registrations
   omitted `video_device.device_caps`, which 6.12 explicitly rejects in
   `drivers/media/v4l2-core/v4l2-dev.c`. Fix the ordering and initialization
   cleanup and set stream capabilities to match the existing QUERYCAP
   handlers. The config node is classified as video capture without
   advertising streaming. These are source-contract fixes, not observed
   successful probes on the device.

References cross-checked online:

- Upstream platform IRQ API:
  https://docs.kernel.org/driver-api/infrastructure.html
- OF removal discussion (the lore site served an anti-bot page here):
  https://lore.kernel.org/all/YcS6rl+dFqhH7giF@ripper/T/
- AOSP 6.12 `of_device_alloc()` populates only address resources:
  https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/drivers/of/platform.c
- Media initialization/registration/cleanup contract:
  https://docs.kernel.org/driver-api/media/mc-core.html
- Firmware request contract:
  https://docs.kernel.org/driver-api/firmware/request_firmware.html

## Verification

- `TMPDIR=/tmp/opencode python3 porting/tests/test_camera_bringup.py -v`:
  three tests pass, including compiled host fault injection of the actual
  IRQ helper, all nine error-checking callers, missing/empty/valid firmware
  preflight, and source checks of media/DT prerequisites. These do not
  emulate the device or prove runtime behavior.
- `bash -n porting/tools/build-kernel.sh` and `git diff --check`: pass.
- Strict checkpatch of the tracked changes: zero errors/warnings/checks.
- Bundled API scan on the patch: no advisory findings. The full imported
  driver scan still reports existing vendor patterns; it is not clean.
- Board DTS preprocessing and dtc compilation succeed without a kernel
  build. `dt-validate` was run against the existing processed schema, for
  both run368's DTB and the changed board. Validation is **not clean**:
  in addition to existing board diagnostics, the restored CAF timing and
  bus-vote properties have no schema type definitions. Logs are preserved
  as `dt-validate-{run368,fixed}.log`; binding coverage remains a follow-up,
  not a successful schema-validation claim.
- No kernel build, Sparse run, or boot test of these changes. The next
  authorized build must recheck the image budget with NV embedding restored
  and verify the 17 firmware paths in the actual package. The old 128 KiB
  margin is not evidence that the changed image fits.

These fixes are not present in `boot-run368camera.img`. Do not reflash that
image expecting them. Sensor identification and wireless recovery remain
unverified until the replacement image is built and tested.
