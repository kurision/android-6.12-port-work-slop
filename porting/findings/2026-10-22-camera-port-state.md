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

## The build test of 2026-10-22

`bash porting/tools/build-kernel.sh run358` in this worktree: the
kernel, the device tree, the ramdisk's init and the image are built and
packaged, and the script verifies the embedded configuration. The
camera is **off** in the port's configuration, so this run proves that
the changes to the shared tree (the crop ioctls of the v4l2 core, the
CAF pixel formats of `videodev2.h`, the new user space headers) do not
break the port's build. The device tree check reports the usual
"failed to match any schema" for the port's own vendor nodes, which
are not new.

The same build with the camera enabled stops in
`drivers/media/platform/msm/camera/`: the camera's own objects do not
compile yet, and the classes that are left are below.

## The camera compiles

The camera's own objects compile without an error or a warning, and the
kernel builds with `CONFIG_MSMB_CAMERA_LEGACY=y` turned on
(`/tmp/opencode/build-cam2.log` of the session): the driver, the
governors, the JPEG encoder, the face detection and the sensor
framework are all in the image.

The last round of conversions:

* the legacy `of_gpio` helpers are gone in 6.12, so the camera reads
  the numbers of the gpios a node names through the descriptor API
  (`msm_camera_gpio_count()` and `msm_camera_gpio_number()` in
  `msm_sd.h`);
* the variable length arrays of the I2C and the SPI helpers are not
  allowed in the kernel, so the buffers are of a fixed size or
  allocated;
* this tree's I2C driver has the old probe signature, so the matched
  device id is asked for with `i2c_get_match_data()`;
* the RPM regulator of the sensor's miscellaneous rail is the standard
  regulator API, and the AHB vote takes the nominal vote when the
  operating point carries a voltage instead of a corner, because this
  tree has no regulator corners;
* `of_pwm_get()` is `devm_pwm_get()`, the SPI chip select is an array,
  and the per-board blocks of the flash that this phone does not take
  are gone.

## The tree does not build yet

The state before that last round, for the record:

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

The classes that are still open, with the files that carry them:

* **the legacy `of_gpio` API** (`of_gpio_count()`, `of_get_gpio()`):
  `sensor/cci/msm_cci.c` (the CCI's own gpio table) and
  `sensor/eeprom/msm_eeprom.c` (the EEPROM's). Upstream removed the
  helpers in 6.2; the donor's device tree gives the plain gpio numbers
  in a "gpios" property (`qcom,gpio-tbl-num`, `-flags` and `-label`
  next to it), so the conversion has to read that property and resolve
  the numbers. The port's device tree (C10) can use the descriptor
  form the kernel expects.
* **the I2C and the SPI probe signatures**: this tree's `struct
  i2c_driver` still has the 4.19 signature (the `probe_new` split of
  6.3 was undone upstream), so the donor's probes are right; the
  bodies that use the `id` argument (`sensor/eeprom/msm_eeprom.c`,
  `sensor/flash/adp1660.c`) have to get the device id another way.
* **`sensor/eeprom/msm_eeprom.c:1263`**: an array of 16 bytes is
  assigned to an `int`; the donor's code relied on the implicit
  truncation.
* **`sensor/flash/msm_flash.c`** and **`sensor/flash/msm_frontflash.c`**:
  the torch led index and the brightness variable of the other phones'
  blocks are gone with the blocks themselves, and the two functions
  that read the gpio table of the flash need the device of their own
  control structure.
* **`sensor/eeprom/msm_eeprom.c`**: the id table the probe takes the
  board information from is declared later in the file, and the
  assignment of the sixteen bytes of the module id to an `int` relies
  on the implicit truncation the compiler rejects now.
* **`sensor/flash/msm_led_i2c_trigger.c`**: the same device that the
  gpio helper needs.

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

## The device tree is the next task

The donor's two files are `../oc-test/arch/arm64/boot/dts/vendor/qcom/
msm8953-camera.dtsi` (the SoC part: the CAMSS node, the three
CSIPHYs, the three CSIDs, the ISPIF, the two VFEs, the JPEG encoder,
the CPP, the SMMU and the CCI) and `../oc-test/arch/arm64/boot/dts/
vendor/qcom/mi8953/tissot/camera.dtsi` (the board part: the six
EEPROMs of the module variants, the two actuators, the LED flash and
the three `qcom,camera@N` nodes).

What the translation needs, checked against this tree:

* **the clocks**: the port's GCC has every clock of the camera with
  its own names - `GCC_CAMSS_AHB_CLK`, `GCC_CAMSS_ISPIF_AHB_CLK`,
  `GCC_CAMSS_CSI0PHYTIMER_CLK`, `GCC_CAMSS_CSI0PHY_CLK`,
  `GCC_CAMSS_CSI0_CLK`, `GCC_CAMSS_CSI0PIX_CLK`,
  `GCC_CAMSS_CSI0RDI_CLK`, `GCC_CAMSS_CSI0_AHB_CLK`,
  `GCC_CAMSS_CSI_VFE0_CLK`, `GCC_CAMSS_VFE0_CLK`,
  `GCC_CAMSS_VFE0_AHB_CLK`, `GCC_CAMSS_VFE0_AXI_CLK`, `GCC_CPP_CLK`,
  `GCC_CAMSS_JPEG0_CLK`, `GCC_CAMSS_MCLK0_CLK` and the sources
  `CSI0PHYTIMER_CLK_SRC`, `CSI0_CLK_SRC`, `VFE0_CLK_SRC`,
  `CPP_CLK_SRC`, `CAMSS_TOP_AHB_CLK_SRC`
  (`include/dt-bindings/clock/qcom,gcc-msm8953.h`).
* **the rails**: the camera's four rails are the pm8953's `l2` (the
  digital), `l6` (the io), `l17` (the af) and `l22` (the analog), the
  ones the port's board file already has.  The camera asks for them by
  the name of the supply property of its own node ("cam_vana-supply"
  and the "qcom,cam-vreg-name" property that goes with it), which is
  how `regulator_get()` finds them: the name is the property's, not the
  regulator's, so the pm8953's rails keep their own names.
* **the power domains of the VFE**: the camera asks for the VFE's
  supply as a *regulator* ("vfe0-vdd-supply", "vfe1-vdd-supply" with
  the names "vfe0-vdd" and "vfe1-vdd"), but this tree has the two
  VFE GDSCs as power domains
  (`include/dt-bindings/clock/qcom,gcc-msm8953.h`: `VFE0_GDSC`,
  `VFE1_GDSC`).  The upstream `qcom-genpd-regulator` driver, which
  describes a power domain as a regulator, is **not** in this tree and
  has to be added.
* **the pinctrl**: the donor's camera nodes ask for the mclk pins and
  the sensors' reset and standby pins by name
  ("cam_sensor_mclk0_default" and the rest); this tree's pinctrl
  driver has the same pins under its own names, and the port's board
  file has to give them the camera's names.
* **the SMMU**: the port's `apps_iommu` already has the VFE's context
  bank (`iommu-ctx@14000`, the stream `0x14`); the camera's other two
  banks - the JPEG's (`0x1800`) and the CPP's (`0x1c00`) - have to be
  added, and the camera's SMMU node describes them the way the donor
  does ("qcom,msm-cam-smmu" with its "qcom,msm-cam-smmu-cb" children,
  the label of the bank and its dma address pool).  The donor's stream
  numbers are the context banks' offsets, so they carry over.

## The kernel has to fit under the bootloader's limit

The build script refuses an image whose `image_size` reaches past the
bootloader's own device tree (the LK puts the kernel at 0x10080000 and
its DTB at 0x13400000, and a kernel that reaches it overwrites its own
device tree and dies before it has a console: no log, no reset -
porting/findings/2026-10-21-kernel-overruns-the-dtb.md).

Without the camera the port's image had 655 360 bytes of headroom.  The
camera needs 917 504 bytes more, so it did not fit.  The ISP of the
generations this board does not have (the 4.4 and the 4.6) is left out
of the build - this board's VFE is the 4.0 (the camera nodes say
"qcom,vfe40"), and the 4.0 uses the 4.7's interrupt handling, so that
one stays.  The face detection stays: the ROM's daemon has a device for
it.

The result is 128 072 bytes of headroom, which is little.  Anything
else that grows the kernel has to pay for itself, and the face
detection is the first thing to look at if the image has to make room
again.
