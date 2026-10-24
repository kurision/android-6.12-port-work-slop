# CSI failure-path hardening before the next boot

This audit follows kernel #30/run385 sensor discovery. No new phone boot was
used to find these defects. The evidence establishes source and host-test
failures, not a reproduced CSI crash on the phone.

## Clock array ownership

Both release helpers in `common/cam_soc_api.c` accept a pointer to the caller's
clock-array variable. Their `if (clk_ptr[i])` condition instead indexed beyond
that variable, while the release used `(*clk_ptr)[i]`. The former can read
outside the caller's stack and skip valid entries or release NULL entries.
Both conditions now index the actual clock array.

`porting/artifacts/snapshot60/run385-csi-clock-cleanup-audit.json` preserves
the original ASan stack-buffer-overflow and passing in-memory correction.
The host test executes both real helpers for zero through nine clocks, with
NULL holes and rate-table cleanup. It passes with ASan/UBSan as well.

## Subdevice shutdown-list ownership

`legacy_msm_sd_register()` adds a subdevice to `ordered_sd_list`, which camera
shutdown and freeze notifications traverse. `legacy_msm_sd_unregister()`
previously removed only the V4L2 registration. The ordered list could retain
a freed subdevice. Unregister now finds and unlinks the entry under the same
mutex used by the traversals, then releases that lock before calling V4L2.
Searching by identity also permits cleanup after failed or repeated
registration without following an uninitialized per-device list node.

The host test executes the actual registration, sorted insertion and
unregistration functions. It checks middle-entry removal, registration failure,
repeated unregister and an empty final list. Existing unregister callers in
sensor-init, buffer-manager, ISP and CPP paths were inspected.

## CSI probe publication and unwind

CSID and CSIPHY both ignored subdevice-registration failures and published
their nodes before finishing setup. Subsequent failure could free their
controller while leaving the node registered; failed registration could also
lead to dereferencing a NULL devnode. CSID selected its register description
after publication. Both probes also replaced clock errors, including
`-EPROBE_DEFER`, with `-EFAULT`.

Finish version, clocks, regulator descriptions, mapping, IRQ and initial
state setup before registering either subdevice. Check entity and registration
results. Explicitly release an acquired managed IRQ before freeing its callback
state on later failure. Release only successfully acquired clocks and mappings,
free the regulator descriptions and controller allocations, and clear device
driver data. Preserve clock, IRQ-lookup and registration deferred errors.
CSIPHY's second-allocation failure now frees its first allocation, and its
cell-index read is checked.

`porting/tests/test_camera_csi_probe.py` compiles the actual complete probe
bodies with mocked acquisitions. For native and CONFIG_COMPAT builds it covers
29 probe scenarios: success, allocation failures, malformed/missing DT values,
deferred clocks and IRQ lookup, regulator/count errors, mapping failures,
IRQ-request failure, unsupported versions, entity failure and registration
failure/defer. Each tested failure checks no published subdevice and no retained
tracked allocation, mapping, clock, IRQ or entity. Clock helpers are modeled
with their existing self-unwind contract. Hardware and kernel API ABI are not
emulated by these stubs.

`run385-csi-probe-negative-controls.json` under the artifact directory records
that both original probe bodies fail the registration-readiness assertion.
The corrected bodies pass, including ASan/UBSan execution.

## History and references

The corresponding donor files are under
`../oc-test/techpack/camera-legacy/{common, sensor/csid, sensor/csiphy}/`, plus
its `msm.c`. The pointer-level errors and early-publication patterns are
inherited; the prior port fixes did not repair these paths. History checked
includes import `e7baf73f97a5`, probe hardening `437649518a37`, CSI IRQ fix
`90952fd1d`, and the target files' histories.

- [V4L2 registration lifetime](https://docs.kernel.org/driver-api/media/v4l2-device.html).
- [Managed-resource ownership](https://docs.kernel.org/driver-api/driver-model/devres.html).
- Target `drivers/media/v4l2-core/v4l2-device.c`, `include/linux/list.h`,
  and camera `legacy_msm_camera_{get,put}_clk_info()` implementations.

The focused checks cover 24 camera tests, one CSI probe-matrix test and three
media ABI tests. The new probe and clock tests also pass ASan/UBSan. Strict
checkpatch and added-line API checks cover the production changes; evidence
is archived as `run385-csi-preboot-hardening-checks.log` and
`run385-csi-preboot-hardening-sanitizers.log` in snapshot60.

No kernel build, Sparse, image packaging, device boot, streaming or capture
was performed. Active-device unbind and open-file lifetime are outside this
probe-failure test and are not established safe. The existing legacy CSI
schema limitations from `2026-10-23-run385-csi-receivers.md` remain. The ISP,
ISPIF and CPP pipeline is still a separate, intentionally disabled stage.
