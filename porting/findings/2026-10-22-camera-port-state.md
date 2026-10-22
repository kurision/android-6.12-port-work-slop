# 2026-10-22: the state of the CAF camera-legacy forward port

**Worktree:** `../ack-camera`, branch `ack-camera`, based on `main`
(`e1ebf25d2`). The plan is `porting/plan/2026-10-22-camera-port.md`.

## Done

**C0 — the plan** (`04cfd9095`): `porting/plan/2026-10-22-camera-port.md`.

**C1 — the import** (`e7baf73f9`): the donor's
`techpack/camera-legacy` (166 files, 96 536 lines) as
`drivers/media/platform/msm/camera/`, the thirteen UAPI headers under
`include/uapi/media/`, the kernel-internal copies under
`include/media/`, `include/soc/qcom/camera2-legacy.h` and the tracepoint
header. The sources carry the first round of the 4.19 → 6.12
conversions:

| donor | 6.12 |
|---|---|
| `struct timeval` in the event structures | `struct __kernel_v4l2_timeval` (the type the v4l2 core uses; the layout is the donor's kernel-side one) |
| `struct compat_timeval` in the compat structures | `struct __kernel_old_timeval` (the same 8 bytes) |
| `V4L2_PIX_FMT_SGRBG14` | `MSM_V4L2_PIX_FMT_SGRBG14` (upstream 6.12 defines the same name with another value) |
| `CSID_MAX` | `MSM_CSID_MAX` (the kernel's `include/linux/clocksource_ids.h` has an enumerator of that name; user space keeps the old name) |
| `kzfree()` | `kfree()` |
| `strlcpy()` | `strscpy()` |
| `VFL_TYPE_GRABBER` | `VFL_TYPE_VIDEO` |
| the platform `.remove` callbacks | they return nothing (6.11) |
| `vb2_ops.get_userptr` | the 6.12 signature (the buffer, no direction) |
| `pm_qos_*` | `cpu_latency_qos_*` |
| `asm/dma-iommu.h`, `iommu_map_sg()` | `linux/iommu.h`, the 6.12 `iommu_map_sg()` with the protection and the allocation flags |
| `set_fs()` / `get_fs()` | gone: the helpers they guarded already use `copy_to_user()` and `copy_from_user()` |
| `do_gettimeofday()` | `ktime_get_real_ts64()` |
| `gpio_free_array()` | a loop of `gpio_free()` |
| `class_create(THIS_MODULE, name)` | `class_create(name)` (6.4) |
| the per-board quirks of the other Xiaomi phones (ROSY, YSL, VINCE) | dropped; this tree is one phone |
| the flag that chose between the donor's two camera stacks | always set; this tree has only the legacy one |

**C2 — the build glue** (`0ec6a8377`): the Kconfig of the stack, the
Makefiles with the tree's include paths, the UAPI headers installed.

**The crop ioctls** (`74d7ad01f`): upstream turned `VIDIOC_CROPCAP`,
`VIDIOC_G_CROP` and `VIDIOC_S_CROP` into the selection interface and
dropped the driver's own handlers in 6.3. The CAF camera implements
them, so the three handlers come back to `struct v4l2_ioctl_ops`, the
core takes the driver's handler when it has one (as 4.19 did) and
falls back to the selection interface otherwise.

## The tree does not build yet

The last compile of `drivers/media/platform/msm/camera/` (the build log
is `/tmp/opencode/cam10.log` of the session, not in the repository)
ends with 80 distinct diagnostics in these classes:

1. **the legacy `of_gpio` API** (`of_gpio_count()`, `of_get_gpio()` in
   `sensor/cci/msm_cci.c` and `sensor/eeprom/msm_eeprom.c`): upstream
   removed it in 6.2; the replacement is the fwnode GPIO descriptor
   API (`fwnode_gpiod_get()`, `devm_gpiod_get()`).
2. **the I2C probe signature**: 6.3 wants
   `int (*probe_new)(struct i2c_client *, const struct i2c_device_id *)`;
   the sensor, the EEPROM, the actuator and the flash drivers carry the
   old one.
3. **the dma-buf mapping** in `msm_buf_mgr/msm_generic_buf_mgr.c`:
   `dma_buf_vmap()` takes a `struct iosys_map` and wants the
   reservation lock (or `dma_buf_vmap_unlocked()`), and
   `dma_buf_vunmap()` has to be given the map it was given. The
   buffer manager has to keep the map in its queue entry
   (`struct msm_buf_mngr_user_buf_cont_info`).
4. **the variable length arrays** (three places): the kernel does not
   allow them.
5. **the timestamps of the CPP and the VPE**: the `struct timespec64`
   the conversion needs has to be declared in the functions that use
   it.
6. **the unterminated conditionals** (two places): the donor's
   `#if IS_ENABLED(CONFIG_...)` blocks whose `#endif` was in a file
   that changed.
7. **the remaining pointer and format diagnostics**: the CFI and the
   bounds checker classes the video port met in `044d3f406` and
   `b8123d808` (the handler types and the one-element arrays).

The classes above are the next commits (C3 to C9 of the plan). The
device tree (C10) and the configuration switch-over (C11) come after
them, and the boot test (B5 of the video plan's numbering) after that.

## Notes for the next session

* The port's configuration file (`porting/tools/kernel.config`) is
  **not** changed: the driver does not compile, and a configuration
  that cannot be built must not be in the port's configuration. The
  compile checks were done with `scripts/config --enable` on
  `out/.config` only.
* The build helper of this worktree is `/tmp/opencode/mkc.sh` (the
  same as the main tree's, with the worktree's path).
* The `struct compat_timeval` of the camera's compat structures was 8
  bytes in the donor (`__kernel_old_time_t` plus an `s32`); the
  replacement keeps that. The event structures were 16 bytes in the
  donor's 64-bit kernel (`struct timeval` with a 64-bit `tv_sec`);
  `struct __kernel_v4l2_timeval` is 16 bytes on both 32 and 64 bit,
  which is what the 32-bit daemon sees now and what the donor's kernel
  produced. **The 32-bit daemon's own view of these structures is
  unverified**: it used its own `struct timeval` (8 bytes) where the
  donor's kernel wrote 16. The boot test has to show that the camera's
  events are still usable.
* The camera's crop API is back, but whether the ROM's daemon uses it
  is unverified.
