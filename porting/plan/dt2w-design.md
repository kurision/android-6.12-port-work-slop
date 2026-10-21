# Double tap to wake (DT2W) for tissot on 6.12: design

**Date:** 2026-10-21 · **Status:** design only, nothing implemented ·
**ROM:** Evolution X · **Donor:** `../oc-test` (4.19)

Read `AGENTS.md` and the kernel development skill (`drivers.md`,
`devicetree.md`) before editing. Boot cycles are the scarce resource:
follow `porting/REFERENCE-boot-testing.md`.

## The problem, as measured

On the running 6.12 port (run331, kernel `#35`) the Evo X power HAL logs,
about twice a second:

```
W libperfmgr: Failed to write to node: /proc/sys/dev/xiaomi_msm8953_touchscreen/enable_dt2w with value: 1, fd: -1
```

The node does not exist, so the Settings toggle cannot reach the kernel and
DT2W does nothing. (The same log line for
`/sys/class/devfreq/soc:qcom,cpu-cpu-ddr-bw/min_freq` is a separate issue,
the CPU-DDR bandwidth devfreq; not covered here.)

## The userspace ABI (fixed: it is the ROM's)

From the phone's own files:

| Fact | Source |
|---|---|
| Path: `/proc/sys/dev/xiaomi_msm8953_touchscreen/enable_dt2w` | `/vendor/etc/powerhint.json`, node `DoubleTapToWakeEnable`, values `"1"`, `"0"`, `ResetOnInit: true` |
| Written `1` on the `DOUBLE_TAP_TO_WAKE` power hint (the Settings toggle) | same file, `Actions` |
| Labelled `proc_touchpanel` | `/vendor/etc/selinux/vendor_sepolicy.cil:9`: `(genfscon proc "/sys/dev/xiaomi_msm8953_touchscreen" (u object_r proc_touchpanel ...))` |
| `hal_power_default` may open/read/write it | `vendor_sepolicy.cil:18173,18176` (also `hal_lineage_touch_default`, 18164/18167) |
| The wake key: `KEY_WAKEUP` (143) | `Generic.kl` maps 143 to `WAKEUP`; PhoneWindowManager wakes on it |

So the kernel must provide exactly that sysctl directory and file, a
`0`/`1` integer, and wake the phone with `KEY_WAKEUP`. No ROM change is
needed.

## What the donor did, and why it is not the model

* `oc-test/drivers/input/touchscreen/doubletap2wake.c`: a software input
  handler. It watches touch events while `is_display_on()` is false and
  injects `KEY_WAKEUP` on a double tap. Switch:
  `/sys/android_touch/doubletap2wake` (or `dt2w=` on the command line),
  **not** the path Evo X writes.
* The donor's touch driver,
  `oc-test/drivers/input/touchscreen/focaltech_touch/`, has the
  controller's gesture mode **compiled out** (`FTS_GESTURE_EN 0`,
  `focaltech_config.h:158`). On `FB_EVENT_BLANK` powerdown its
  `fts_ts_suspend()` disables the IRQ and sends the controller to sleep
  (`FTS_REG_POWER_MODE_SLEEP`), so the software handler never sees a touch
  with the screen off.
* Neither the donor tree nor the stock 4.19 kernel image
  (`../ack-kgsl-artifacts/stock-boot-live.bin`) contains the string
  `xiaomi_msm8953_touchscreen`.

**Conclusion (unverified on device):** DT2W very likely did not work on
the 4.19 kernel either. There is no proven path on this phone to copy.

## The hardware mechanism: the controller's gesture mode

The controller (FocalTech, driven here by upstream `edt-ft5x06` as
`edt,edt-ft5406` at I2C `0x38`, `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts:195`)
can detect a double tap itself in a low-power mode and interrupt only then.
The protocol, from LineageOS's `ft5435` driver for this panel family
(`HQ_D2_XiaoMi_FT5435_*` firmware;
[LineageOS android_kernel_xiaomi_msm8953 lineage-20, `drivers/input/touchscreen/ft5435/ft5435_ts.c`](https://github.com/LineageOS/android_kernel_xiaomi_msm8953/tree/lineage-20/drivers/input/touchscreen/ft5435)),
matching the donor's own register names (`FTS_REG_GESTURE_EN 0xD0`,
`FTS_REG_GESTURE_OUTPUT_ADDRESS 0xD3`, `GESTURE_DOUBLECLICK 0x24` in
`oc-test/.../focaltech_touch/focaltech_common.h:93-94`,
`focaltech_gesture.c:59`):

**Enter** (LineageOS `ft_tp_suspend()`):
1. Write `0xD0 = 0x01` (gesture enable).
2. Write `0xD1, 0xD2, 0xD5, 0xD6, 0xD7, 0xD8 = 0xFF` (gesture type masks).
3. `msleep(10)`, read `0xD0`; if not `1`, repeat steps 1-3, up to 10 times.
4. Leave the IRQ enabled and make it a wake source (`enable_irq_wake()`).

**Interrupt while in gesture mode** (LineageOS `ft_tp_interrupt()`):
1. Read `0xD3`.
2. If `0x24`: report `KEY_WAKEUP` 1, sync, `KEY_WAKEUP` 0, sync.
3. Otherwise ignore. Return without reading touch data.

**Leave** (LineageOS `ft5435_ts_resume()`):
1. Pulse the reset line: assert, `msleep(2)`, deassert.
2. Wait for the controller to boot (the port already uses 500 ms after
   reset; see commit `3533dddf6`).
3. `disable_irq_wake()`.

LineageOS also writes `0x8C = 0x01` on every resume. Its meaning is
undocumented; leave it out unless the controller does not return to
normal reporting after the reset.

## Design

All in `drivers/input/touchscreen/edt-ft5x06.c` (the port's copy, already
carrying tissot changes), enabled per board by a DT property so other
boards using this driver are unaffected.

### DT

```dts
touchscreen@38 {
	...
	edt,gesture-wakeup;	/* controller supports the 0xD0 double-tap gesture */
};
```

(A port-local property. If it is ever upstreamed it needs a binding
change; for now document it in the driver.)

### Driver state (`struct edt_ft5x06_ts_data`)

* `bool gesture_wakeup` - the DT property is present.
* `bool gesture_active` - the controller is in gesture mode now.
* `struct notifier_block fb_notif` and a `struct work_struct` for the
  transitions.
* A module-level `static int edt_dt2w_enable` (0/1) backing the sysctl.
  One touchscreen per phone; a single global is acceptable here, document
  it.

### The switch: the ROM's path

`register_sysctl("dev/xiaomi_msm8953_touchscreen", table)` with one entry,
`enable_dt2w`, mode `0644`, `proc_dointvec_minmax` clamped to 0..1,
registered in probe only when `gesture_wakeup` is set, unregistered on
remove. A change takes effect at the next screen-off (do not enter or
leave gesture mode from the sysctl handler).

### The trigger: screen off and on

This kernel's `fb_blank()` still sends `FB_EVENT_BLANK` after a
successful blank (`drivers/video/fbdev/core/fbmem.c:359-360`), Android's
`FBIOBLANK` reaches it (`fb_chrdev.c:140-146`), and the port's own
`drivers/video/fbdev/msm/mdss_dsi_status.c:187` already consumes it.
Register an fb client (`fb_register_client()`, `CONFIG_FB_NOTIFY=y`):

* `FB_BLANK_POWERDOWN` and `edt_dt2w_enable` and `gesture_wakeup`: queue
  the "enter" work.
* `FB_BLANK_UNBLANK` and `gesture_active`: queue the "leave" work.

Do the I2C in a work item, not in the notifier: `fb_blank()` runs with
`console_lock()` and the fb lock held, and "enter" can take up to
~100 ms with its retries.

### The IRQ handler

At the top of `edt_ft5x06_ts_isr()`: if `gesture_active`, read `0xD3`,
report `KEY_WAKEUP` on `0x24`, call `pm_wakeup_event(dev, 500)` so the
system does not re-suspend before the key reaches userspace, and return
`IRQ_HANDLED`. Declare `KEY_WAKEUP` with `input_set_capability()` in
probe when `gesture_wakeup` is set.

### System suspend and resume (`edt_ft5x06_ts_suspend/resume`)

Today, unless `device_may_wakeup()`, suspend hibernates the controller
and (in `EDT_PMODE_POWEROFF`) cuts its supplies; resume powers it back and
re-toggles reset. With gesture mode active that would kill the gesture:

* suspend: if `gesture_active`, return 0 before the hibernate / power-off
  path (the IRQ is already a wake source from "enter").
* resume: if `gesture_active`, return 0 (the fb unblank "leave" work does
  the reset).

Do **not** call `device_init_wakeup(dev, true)` unconditionally: with
`device_may_wakeup()` true, the existing suspend path keeps the
controller fully scanning and IRQ-wake for every suspend, so any touch in
a pocket would wake the phone even with DT2W off. Enable the wake source
in "enter" (`device_wakeup_enable()` plus `enable_irq_wake()`) and drop it
in "leave".

### Locking and ordering

* Serialise enter/leave/ISR with the driver's existing `tsdata->mutex`
  or a dedicated mutex; the ISR is threaded, so it may sleep.
* "leave" must not run concurrently with "enter": use one ordered
  workqueue or cancel the other work first.
* Release held keys (`key_state = 0`, as suspend already does) and all
  touch slots before entering gesture mode.

## What must be verified before trusting it

1. **That tissot's controller honours `0xD0`.** LineageOS's driver is for
   the FT5435 panels on this family; the port's `edt-ft5x06` reports the
   model it identified in its probe log. Read `0xD0` back after "enter"
   (step 3 does) and log the result. If it never reads `1`, the firmware
   lacks gesture support and this design does not apply.
2. That `FB_EVENT_BLANK` actually fires on screen off/on with the Evo X
   display HAL (log it in the notifier on the first build).
3. That the controller reports normal touches again after "leave" (if
   not, try the `0x8C = 0x01` write LineageOS does).
4. Power: measure suspend current with DT2W on and off.

## Test plan

1. Build with `bash porting/tools/build-kernel.sh <run> ../ack-kgsl-artifacts/boot-run258.img`
   (the build refuses a kernel over the bootloader's size limit; this
   change is small).
2. Boot; `cat /proc/sys/dev/xiaomi_msm8953_touchscreen/enable_dt2w` and
   `ls -Z` it (expect `proc_touchpanel`). The libperfmgr
   `enable_dt2w` failure line must be gone from logcat.
3. Toggle Settings > Display > Double tap to wake; the value must follow.
4. Screen off, wait for suspend (`dumpsys power`, or watch
   `/sys/power/wakeup_count`), double tap: the screen must wake. A single
   tap or a swipe must not.
5. DT2W off: screen off, tap: must not wake.
6. Screen on: touch and the three capacitive keys must work normally.

## Not in scope

* The CPU-DDR bandwidth devfreq node (`cpu-cpu-ddr-bw`). Note for that
  work: Evo X labels `/devices/platform/soc/soc:qcom,cpu-cpu-ddr-bw/devfreq`,
  but this kernel's SoC node is `soc@0`, so the device would appear under
  `/devices/platform/soc@0/` and miss that label.
* Other gestures (the masks enable them; only `0x24` is acted on).
