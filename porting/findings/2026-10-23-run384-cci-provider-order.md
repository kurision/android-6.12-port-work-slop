# Run384: CCI provider publication follows child creation

The user booted kernel `6.12.93-4k-g8e6263ae9919 #29`. Android reached
`sys.boot_completed=1`, all three sensor slots bound, and qcamerasvr ran,
but Android still reported zero cameras. Evidence is preserved under
`porting/artifacts/snapshot60/camera-capture-20261023T082726Z/`.

`logdump.log:3889` records `legacy_msm_sensor_cci_i2c_util ... rc = -19`,
followed by `cci_init failed` and failed sensor-init requests. This is
different from run383's missing-slot `-EINVAL`. `cci-bindings.txt` shows
CCI and all three slot devices bound later; it also records CCI interrupts.
Those later observations do not establish which pointer a sensor cached
earlier, or whether sensor communication succeeded.

## Source-confirmed ordering defect

In `msm_cci_probe()`, the inherited donor sequence was:

1. Populate CCI's child platform devices.
2. Set CCI's disabled state and publish `g_cci_subdev`.
3. Create the two write workqueues.

Child creation can synchronously call an already registered sensor driver's
probe. `legacy_msm_sensor_init_default_params()` caches the result of
`legacy_msm_cci_get_subdev()` without a readiness check. A child probing
inside population can therefore retain NULL even after CCI returns.
`legacy_msm_sensor_cci_i2c_util()` later passes that cached pointer to
`v4l2_subdev_call()`, which returns `-ENODEV` for a NULL subdevice.

The same ordering exists in the local donor
`../oc-test/techpack/camera-legacy/sensor/cci/msm_cci.c`; the import commit
`e7baf73f97a5` retained it. Upstream references:

- [V4L2 subdevice calls and NULL return semantics](https://docs.kernel.org/driver-api/media/v4l2-subdev.html#calling-subdev-operations).
- [AOSP V4L2 subdevice call macro](https://android.googlesource.com/kernel/common/+/refs/heads/android-mainline/include/media/v4l2-subdev.h).
- Target `drivers/of/platform.c` calls platform device creation from
  `of_platform_populate()`; `drivers/base/dd.c` supplies probe/defer handling.

The built initcall table places CCI driver registration before sensor driver
registration. This does not prove CCI's device probe completed first:
deferred probing can change when device probes execute. The exact timing
and cached pointer on this phone were not captured and remain unverified.
The source defect is reproduced in the host test; it is a supported
explanation for the phone's failure, not a proven hardware diagnosis.

## Narrow repair and proof

Initialize the disabled state and create workqueues, publish the subdevice,
then populate children. The patch only reorders existing operations and
retains the population-error diagnostic. It does not change DT, IRQ setup,
register writes, power sequences, clock rates or initcall levels.

The focused host test executes the actual probe-tail setup code with a
synchronous child callback. Its old-order negative control caches NULL;
the corrected order sees the published provider and both workqueues.
Population failure still emits the existing error diagnostic. Workqueue
allocation-failure handling and provider removal are unchanged and are not
proved safe by this test.

All 19 camera host tests pass. Strict checkpatch reports no errors, warnings
or checks, and the added-line API-pattern scan reports no findings.
No kernel build, Sparse, image packaging or device boot of this change was
performed. The proposed repair is not boot-tested. CCI communication,
sensor identification and capture remain unverified.

The earlier run371 evidence ruling out a NULL-workqueue boot panic applies
to that boot's observed ordering. This new finding does not reclassify that
death evidence or assert that run384 panicked.
