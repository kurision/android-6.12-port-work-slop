# run334a: double tap to wake works on the tissot panel

DT2W is implemented in `edt-ft5x06` and verified on the phone. The user
reported "it's not working" before this run; the cause was not the design
or the controller. The phone was running a kernel built before the change.

## Why the first report said "not working"

The running kernel was `#37`, built 15:49, from the tree at `166d3b532`
with dirty initramfs changes. The DT2W driver and DTS edits were made at
16:13-16:16, after that build:

```
16:13 arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts
16:16 drivers/input/touchscreen/edt-ft5x06.c
15:49 out/arch/arm64/boot/Image
15:04 out/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb
```

The running image therefore had none of it: `strings` found zero
occurrences of `xiaomi_msm8953_touchscreen` in `Image`, the DTB had no
`edt,gesture-wakeup`, the live node
`/sys/firmware/devicetree/base/soc@0/i2c@78b7000/touchscreen@38` had no
such property, the sysctl did not exist, and `libperfmgr` logged
`Failed to write ... fd: -1` (ENOENT). The "implemented" note in the
design was true of the source tree, not of the booted kernel. Check
`uname -a` against the source mtimes before diagnosing device behaviour.

## Trigger path, verified on the old kernel without a reboot

Tracefs was used on the running kernel (`#37`) to watch the real display
HAL. `composer@2.1-se` calls the fbdev blank path on both screen off and
on:

```
echo 'p:fbblank fb_blank' >> /sys/kernel/tracing/kprobe_events
echo 'p:fbnotify fb_notifier_call_chain' >> ...
echo 'p:mdsblank mdss_fb_blank' >> ...
input keyevent 26

composer@2.1-se-694  7337.107508: fbblank: (fb_blank+0x0/0xb4)
composer@2.1-se-694  7337.107518: mdsblank: (mdss_fb_blank+0x0/0x1f4)
composer@2.1-se-694  7337.352622: fbnotify: (fb_notifier_call_chain+0x0/0x30)
composer@2.1-se-694  7339.756708: fbblank: (fb_blank+0x0/0xb4)
composer@2.1-se-694  7339.756720: mdsblank: (mdss_fb_blank+0x0/0x1f4)
composer@2.1-se-694  7339.941262: fbnotify: (fb_notifier_call_chain+0x0/0x30)
```

`fb_notifier_call_chain` runs only when `mdss_fb_blank` returns 0, so
`FB_EVENT_BLANK` is delivered on this ROM. The notifier is the right
trigger. The probe is `info->node == 0`; the composer blanks fb0.

The ROM's own policy already covers the ABI: the pulled
`/vendor/etc/selinux/precompiled_sepolicy` contains the type
`proc_touchpanel` and the genfscon path
`/sys/dev/xiaomi_msm8953_touchscreen`, and the power HAL runs as UID 0 in
`hal_power_default`.

## Fixes made before the boot cycle

* `edt_ft5x06_gesture_leave()` no longer returns early when
  `disable_irq_wake()` fails. An early return left the controller in
  gesture mode with normal input dead after the screen came on. It now
  warns and finishes the reset and wake-source teardown.
* `edt_ft5x06_ts_resume()` reaches `unblock:` on every path, including
  `EDT_PMODE_NOT_SUPPORTED` and regulator failures. Previously those
  returned before clearing `pm_blocked`, so no later screen transition
  could ever enter gesture mode again.
* Gesture entry writes the six masks before `0xD0 = 1`, matching the
  donor's `fts_gesture_suspend()` and `fts_gesture_recovery()` order.
* Diagnostic logs at `dev_info`/`pr_info` were demoted to `dev_dbg` after
  this run; enable them with dynamic debug when debugging.

## Hardware result

Image: `porting/artifacts/snapshot60/boot-run334a.img`
(sha256 `b910920e2f386223f826df8e3805451a6ae7f500d74910dfa1bd413edd0144ea`,
kernel `#38`, `6.12.93-4k-g09e3154bf20c-dirty`), built from
`../ack-kgsl-artifacts/boot-run258.img`, flashed to `boot_b`.

The sysctl exists with the ROM's label and DAC:

```
-rw-r--r-- 1 root root u:object_r:proc_touchpanel:s0 0 enable_dt2w
```

The devicetree property is present in the live node, and the full chain
is in dmesg:

```
[603.995150] edt_ft5x06 1-0038: primary display off
[604.009851] edt_ft5x06 1-0038: gesture mode enabled, D0=1
[604.997873] edt_ft5x06 1-0038: double tap gesture
[605.332680] edt_ft5x06 1-0038: primary display on
[608.038963] edt_ft5x06 1-0038: primary display off
[608.053071] edt_ft5x06 1-0038: gesture mode enabled, D0=1
[608.637891] edt_ft5x06 1-0038: double tap gesture
[608.980993] edt_ft5x06 1-0038: primary display on
```

`D0=1` is the firmware's own readback after entry, and `0x24` is the
double-tap gesture ID. Two consecutive off/on cycles woke the display.

The ROM toggle was then exercised by the user, and the HAL's writes appear
in the same log with no `libperfmgr` failure:

```
[683.596442] xiaomi_msm8953_touchscreen: enable_dt2w=0
[685.649775] xiaomi_msm8953_touchscreen: enable_dt2w=1
```

So DAC (UID 0 against root-owned 0644) and the `proc_touchpanel` SELinux
label both admit the ROM's write, and no ROM change is needed.

## Not verified

* Wake from deep system suspend. The captured cycles were display
  off/on close together; `suspend_stats` or a PM trace during a wake from
  suspend was not collected. The screen-off path is proven, the suspend
  residency path is not.
* Normal touch and the capacitive keys after "leave" were used by the
  user but no log evidence was recorded. If a future report shows dead
  input after the screen comes on, the LineageOS `0x8C = 0x01` write is
  the fallback.
* Gesture IDs other than `0x24` are ignored but their interrupts still
  arm the wake source and can wake the system.
* Suspend current with DT2W on and off was not measured.

Recovery image for the previous boot (kernel `#37`, the one that booted
before this flash): `../ack-kgsl-artifacts/boot-live-run333-good.img`.
