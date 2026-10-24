# The driver-name clash behind -EBUSY, and where the probe deaths stand

Boot tested: `boot-run371-camera-cci-off.img` (run371). Capture:
`porting/artifacts/snapshot60/run371-camera-capture-Ci6Vf86v/` — the live
`/proc/cmdline` with the blacklist, the full boot `dmesg.txt` with
`initcall_debug`, the logdump partition, and pstore decode.

## What the isolation boot proved

run371 is run370's kernel with only the boot-header command line changed:
`initcall_blacklist=msm_cci_init_module initcall_debug log_buf_len=1M`
(verified byte-for-byte in `run371-camera-cci-off-verification.json`). It
booted. So the deaths of run369 and run370 followed the CCI registration
path; everything else in those images also boots. Two caveats stay
explicit: `initcall_debug`'s timing effects are not ruled out, and there
is no persistent record from the CCI-enabled boots, so the mechanism of
the death inside that path is still unverified.

## The name hidden behind the camera's silence

The dmesg of the good boot shows two platform drivers racing for one
name:

```
[    3.209852] calling  msm_drm_register+0x0/0x78 @ 1
[    4.363497] calling  msm_init+0x0/0x40 @ 1
[    4.364879] Error: Driver 'msm' is already registered, aborting...
[    4.365447] initcall msm_init+0x0/0x40 returned -16 after 939 usecs
```

`msm_drm_register` is `CONFIG_DRM_MSM=y`
(`drivers/gpu/drm/msm/msm_drv.c` `.name = "msm"`). The camera core
(`drivers/media/platform/msm/camera/msm.c`) also asked for `"msm"`, kept
that name from the donor's `camera_v2/msm.c:1471`, where it had no rival
— the donor does not build DRM_MSM. So `msm_probe()` never ran in *any*
flash of this port, run368 included; run368's "camera registered but no
`/dev/media*` no `v4l-subdev*`" is this same failure, seen from the
other side.

The `-5` returns two initcalls make a few hundred microseconds later
were misread for days as separate defects. They are the downstream of
the `-EBUSY`:

```
[    4.518820] WARNING: CPU: 4 PID: 1 at drivers/media/platform/msm/camera/msm.c:414
legacy_msm_sd_register+0x220/0x2c0
[    4.547613] initcall msm_sensor_init_module+0x0/0x178 returned -5 after 33328 usecs
[    4.582716] WARNING: ... legacy_msm_sd_register ...
[    4.612090] CAM-BUFMGR msm_buf_mngr_init:891 ... error = -5
[    4.612847] initcall msm_buf_mngr_init+0x0/0x200 returned -5 after 34652 usecs
```

`legacy_msm_sd_register()` (msm.c:414) returns `-EIO` when
`msm_v4l2_dev` does not exist — and `msm_v4l2_dev` is allocated only in
`msm_probe()`. Nothing else needs changing for sensor-init and
buf-mngr.

## The AHB vote client had no device

`legacy_cam_ahb_clk_init()` (cam_hw_ops.c, called from `msm_probe()`,
msm.c:1399) builds `struct msm_bus_scale_pdata` by hand and was the only
caller of `msm_bus_scale_register_client()` in the tree that never set
`pdata->dev`. The interconnect compat layer resolves a client's paths
through *that device*: `msm-bus-compat.c` sets `pdata->dev` in
`parse_table()` (the DT-parse path) and copies
`client->dev = pdata->dev` in `msm_bus_scale_register_client()`.

Harmless today: `icc_map` has no `MASTER_AMPSS_M0 → SLAVE_CAMERA_CFG`
pair, so `resolve_paths()` returns `-ENOENT` before `of_icc_get()` ever
sees a NULL device, and the compat layer's header documents what
happens then — "its votes are accepted and dropped, because bus voting
is tuning and not function". A mapping added later would hand
`of_icc_get()` NULL; the `.dev` is set now so that cannot happen.
Honest difference from the donor, which fed these votes to a real
msm-bus: the camera's votes are dropped. Follow-up, only if needed:
add the camera endpoints to `icc_map` once the msm8953 noc provider is
understood, or accept the dropped votes.

## Firmware, verified independently on device

run371's boot log carries the WCNSS remote booting with the restored
files (`remoteproc remoteproc2: Booting fw image wcnss.mdt, size 7324`,
`WCNSS Version 1.5 1.2`, the wifi smd edge probing clean at 12.78 s).
The camera boot resets therefore were not the firmware repair failing;
that part is done. The `wcnss-service` exiting 255 at 26 s is a
userspace/SELinux matter, out of the kernel's scope here (logged in the
same dmesg: audit denials for `wcnss_service` reading a property).

## Config parity note

The current flashable family keeps `CONFIG_MSM_CAMERA_VFE=n` and
`CONFIG_MSM_CAMERA_CPP=n` (the milestone allocation; the full camera
does not fit under the bootloader's limit with KASAN on). Camera
functions stay partial even after the core unblocks. That is a measured
budget decision from
`porting/findings/2026-10-22-camera-port-state.md`, not a bug.

## Changes made in this turn

- `drivers/media/platform/msm/camera/msm.c`: core platform driver
  renamed `"msm" → "msm_cam"` with a comment tying it to the DRM msm
  rival; the donor keeps `"msm"` and is not converging (tree-local
  adaptation, unfork ABI).
- `drivers/media/platform/msm/camera/common/cam_hw_ops.c`: the AHB
  client sets `.dev = &pdev->dev`.
- `porting/tests/test_camera_bringup.py`: two new tests cover both; 6/6
  pass. checkpatch --strict over the full pending diff: clean.

## Next

- **run372-camera**: this build, CCI still blacklisted through the
  command line as in run371, plus `initcall_debug log_buf_len=1M`.
  Success signature: `initcall msm_init+... returned 0`,
  `probe of 1b00000.qcom,msm-cam returned 0`, and *no* `-5` from
  sensor-init/buf-mngr. Live adb capture at the first connection, like
  run371's.
- **run373**: CCI enabled, after the CCI-probe review items stand
  (phandle-aware GPIO count in `msm_camera_gpio_count()`, the
  `qcom,camera@*/@1/@2` base properties inherited from the donor's
  `msm8953-camera-sensor-mtp.dtsi`), a node parity check against the
  donor, and — if a death repeats — a plan to read the PMIC reset
  reason on the following boot (QPnP PON registers survive it; the
  interface this tree exposes there is unverified, to be checked before
  relying on it).
