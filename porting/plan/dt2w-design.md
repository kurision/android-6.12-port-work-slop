# Double tap to wake (DT2W) for tissot on 6.12: design

**Date:** 2026-10-21 · **Status:** implemented and verified on hardware
(run334a, kernel `#38`) ·
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

The implementation supplies that sysctl directory and file, a `0`/`1`
integer, and reports `KEY_WAKEUP`. A read-only `adb shell 'ps -AZ'` check
on 2026-10-21 showed the running
`android.hardware.power-service.lineage-libperfmgr` as UID root in
`hal_power_default`; mode 0644 therefore permits its DAC write. Verified on
run334a: the node is labelled `u:object_r:proc_touchpanel:s0`, and the
toggle's writes (`0`, then `1`) reached the handler with no `libperfmgr`
failure. No ROM change is needed.

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
may support firmware detection of a double tap in a low-power mode. This
is not yet verified on this phone's installed firmware.
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

A downstream property, documented in the local binding. It requires
`reset-gpios` and must not be combined with `wakeup-source`. Probe also
requires generic FocalTech protocol, FB_NOTIFY, PROC_SYSCTL and PM_SLEEP.

### Driver state (`struct edt_ft5x06_ts_data`)

* `bool gesture_wakeup` - the DT property is present.
* `bool gesture_active` - the controller is in gesture mode now.
* `struct notifier_block fb_notif` and a `struct work_struct` for the
  transitions.
* Per-device `dt2w_enable` and sysctl table/header. The fixed ROM path
  assumes one gesture-capable touchscreen per phone.
* `state_lock` protects `display_off`, the screen-off-latched
  `gesture_requested`, and `pm_blocked`. Hardware state is changed only
  by the single worker or by PM/cleanup after draining that worker.

### The switch: the ROM's path

`register_sysctl("dev/xiaomi_msm8953_touchscreen", table)` with one entry,
`enable_dt2w`, mode `0644`, `proc_dointvec_minmax` clamped to 0..1,
registered in probe only when `gesture_wakeup` is set, unregistered on
teardown. A wrapper parses through a temporary integer and publishes with
WRITE_ONCE; the notifier samples with READ_ONCE. A change takes effect at
the next screen-off, not directly from the sysctl handler. ABI documentation:
`Documentation/ABI/testing/procfs-xiaomi-msm8953-touchscreen`.

### The trigger: screen off and on

This kernel's `fb_blank()` still sends `FB_EVENT_BLANK` after a
successful blank (`drivers/video/fbdev/core/fbmem.c:359-360`), Android's
`FBIOBLANK` reaches it (`fb_chrdev.c:140-146`), and the port's own
`drivers/video/fbdev/msm/mdss_dsi_status.c:187` already consumes it.
Register an fb client (`fb_register_client()`, `CONFIG_FB_NOTIFY=y`):

* Filter to the primary framebuffer (`info->node == 0`).
* Both powerdown and unblank record the latest desired display state and
  queue the same work item, unless system PM has blocked it.
* Sample the switch only on an on-to-off transition, not duplicate blanks.
* Never gate unblank on `gesture_active`: entry may still be queued.
  A notification during work requeues that work to reconcile the new state.

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

* Suspend gates enqueueing under `state_lock`, drains the worker without
  holding its locks, then reconciles intent before the I2C adapter suspends.
  Preserve power if gesture mode is active; otherwise use ordinary power-off.
* Resume preserves active gesture mode, or restores ordinary controller
  power, before opening the gate and requeueing reconciliation. Background
  resumes with the display still off therefore keep gesture mode active.

Do **not** call `device_init_wakeup(dev, true)` unconditionally: with
`device_may_wakeup()` true, the existing suspend path keeps the
controller fully scanning. Wakeup capability is established in probe but
initially disabled. Enable the wake source in "enter"
(`device_wakeup_enable()` plus `enable_irq_wake()`), check both return
values, and drop it in "leave". For gesture-capable panels, the gesture
state rather than externally writable `power/wakeup` selects the PM path.

### Locking and ordering

* Disable/drain the IRQ before taking `tsdata->mutex` for transitions.
  The ISR does not acquire that mutex. Existing factory-mode IRQ draining
  therefore cannot deadlock against a mutex-taking ISR.
* One work item serializes enter/leave; PM blocks enqueueing and drains it.
* Emit key-up events and release every touch slot, followed by input sync,
  before entering gesture mode. Merely clearing key_state is not a release.
* On failed entry, reset and restore configured register parameters before
  falling back to ordinary suspend. Leave also resets and restores them.
* Devres teardown unregisters the sysctl/notifier, drains work, disables the
  IRQ, and unwinds wake state before devres releases the IRQ and supplies.

## What was verified (and what was not)

1. **Tissot's controller honours `0xD0`.** Verified on run334a: entry
   read `0xD0 = 1` back from the firmware, and a real double tap produced
   gesture ID `0x24` and woke the display in two consecutive cycles.
2. **`FB_EVENT_BLANK` fires with the Evo X display HAL.** Verified on the
   previous kernel with kprobes: `composer@2.1-se` calls `fb_blank()` ->
   `mdss_fb_blank()` -> `fb_notifier_call_chain()` on both screen off and
   on.
3. **Normal touches after "leave".** The user used the screen normally
   after the wake cycles, but no log evidence was recorded; the fallback
   remains the LineageOS `0x8C = 0x01` write if input is ever dead after
   the screen comes on.
4. **Power:** suspend current with DT2W on and off was not measured.
5. **Deep-suspend wake:** not proven. The captured wake cycles were
   display off/on close together; suspend residency was not traced.

## Test plan

1. Build with `bash porting/tools/build-kernel.sh <run> ../ack-kgsl-artifacts/boot-run258.img`
   (the build refuses a kernel over the bootloader's size limit; this
   change is small).
2. Boot; `cat /proc/sys/dev/xiaomi_msm8953_touchscreen/enable_dt2w` and
   `ls -Z` it (expect `proc_touchpanel`). The libperfmgr
   `enable_dt2w` failure line must be gone from logcat.
3. Toggle Settings > Display > Double tap to wake; the value must follow.
4. Screen off, confirm system suspend with kernel PM trace/log evidence
   (wakeup_count and dumpsys power alone do not prove residency), then
   double tap: the screen must wake. A single
   tap or a swipe must not.
5. DT2W off: screen off, tap: must not wake.
6. Screen on: touch and the three capacitive keys must work normally.
7. Repeat rapid off/on transitions, including on while entry is pending,
   background resumes with the screen off, and repeated suspend cycles.
8. Exercise I2C entry errors, IRQ-wake enable failure, and driver unbind/bind
   when safe; verify cleanup and normal input recovery.

Before building, run `python3 porting/tests/test_dt2w_contracts.py`, scoped
checkpatch and the kernel API scanner. The Python checks guard source-level
ordering/ABI only; they do not execute the driver or prove concurrency.

### Implementation checks (2026-10-21)

* Six source-contract tests passed in `porting/tests/test_dt2w_contracts.py`.
* Strict checkpatch on the driver diff: no errors, warnings or checks.
* Kernel API pattern scanner: no advisory findings in the driver.
* `dt-doc-validate` on the edited binding passed. This is schema validation,
  not `dt_binding_check` example compilation or board `dtbs_check`.
* Scoped `git diff --check` passed.
* Read-only `/proc/403/status` confirmed the power HAL's effective UID 0.
* `W=1` object build of `edt-ft5x06.o` is warning-free. Sparse is not
  installed in this environment, so `C=1` was not run.

### Hardware verification (run334a, 2026-10-21)

Flashed `boot-run334a.img` (kernel `#38`, sha256
`b910920e2f386223f826df8e3805451a6ae7f500d74910dfa1bd413edd0144ea`) to
`boot_b`. Full evidence in
`porting/findings/2026-10-21-dt2w-hardware.md`.

* Trigger path proven on the previous kernel with kprobes: the composer
  calls `fb_blank()` -> `mdss_fb_blank()` -> `fb_notifier_call_chain()`.
* Node: `-rw-r--r-- 1 root root u:object_r:proc_touchpanel:s0 enable_dt2w`,
  default `0`, live DT node has `edt,gesture-wakeup`.
* Screen off: `primary display off`, then `gesture mode enabled, D0=1`.
* Double tap: `double tap gesture`, then `primary display on`; two
  consecutive cycles.
* ROM toggle: `enable_dt2w=0` then `enable_dt2w=1` from the HAL, no
  `libperfmgr` failure, so DAC and SELinux both admit the write.
* Not proven: deep-suspend wake, suspend current, and touch recovery after
  leave with log evidence. See the findings file.

## Not in scope

* The CPU-DDR bandwidth devfreq node (`cpu-cpu-ddr-bw`). Note for that
  work: Evo X labels `/devices/platform/soc/soc:qcom,cpu-cpu-ddr-bw/devfreq`,
  but this kernel's SoC node is `soc@0`, so the device would appear under
  `/devices/platform/soc@0/` and miss that label.
* Other gestures (the masks enable them; only `0x24` reports a key).
  Ignoring their IDs does not prevent their IRQs from waking the system.

Protocol cross-check: the LineageOS ft5435 source linked above. PM semantics:
[upstream suspend/interrupt documentation](https://docs.kernel.org/power/suspend-and-interrupts.html)
and the target tree's `drivers/base/power/wakeup.c` / `kernel/irq/manage.c`.
