# Snapshot46–47: past QSEE into userspace; graphics now blocks boot (2026-10-09)

> **Historical record - 2026-10-09.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

Evidence lives under `porting/artifacts/snapshot46/` and `porting/artifacts/snapshot47/`
(`runN-usb.log`, `runN-sd.log`, `runN-logdump.bin`, `run4-logcat.txt`).

## 1. QSEE reset fixed: crypto-engine clocks (snapshot46, 97d12f932)

Snapshot45 reset inside TrustZone. Its last trace record was keymaster's
1164-byte `0x30000006` request (`args[2]=0x48c`), with no `SMC_RET` after it.
The donor 4.19 DT gives qseecom the four GCC crypto clocks and sets
`qcom,support-bus-scaling`. The ACK DT had `qcom,no-clock-support` instead,
so nothing voted for the clocks, and 6.12 turns unused clocks off at 4.65 s.

After the DT fix:

- probe logs `qseecom: HLOS CE clocks ready core=99999975 Hz`;
- seq 43, the `0x48c` request, returns in 7.5 ms, and its `extra[1]` (the
  clock refcount) is `0x1`;
- every later trace ends `LAST=SMC_RET` around 92–95 s. The reset no longer
  happens inside TrustZone.

## 2. Userspace restart loop (snapshot46 run1)

`sys.boot_completed` is never set. Counts from `run1-sd.log`:

| Service | Outcome |
|---|---|
| `vendor.hwcomposer-2-1` | SIGSEGV ×51; `onrestart` restarts surfaceflinger |
| zygote / audioserver / netd / audio HAL | SIGKILL ×59 each (zygote started 60 times) |
| `vendor.livedisplay-sdm` | SIGABRT ×46 |
| `vendor.tftp_server` / `vendor.per_mgr` / `vendor.per_proxy` | exit 255 / 255 / 1 |

- **Not a reboot cause:** init's "process with updatable components … exited
  4 times before boot completed" message appears more than 400 times from
  137 s on, and the phone keeps running.
- **Not an auto-reset:** that run ended because the phone was force-rebooted
  by hand.
- **No usable tombstones:** `/data/tombstones` files from that run exist with
  their full sizes but are all zero bytes.

## 3. Why there was no adb

There were two separate blockers:

1. **The diag serial owned the controller.** The diag ACM gadget held `g1`
   bound to the only UDC, so every Android write to `g1/UDC` failed with
   EBUSY.
2. **Legacy `g_ffs` took the FunctionFS device.** `CONFIG_USB_FUNCTIONFS=y`
   builds in `g_ffs`, which claims the single FunctionFS device (`g_ffs.c`
   `ffs_single_dev`). Android could not create `ffs.adb`, adbd's mount bound
   to `g_ffs`, and the log showed "g_ffs: couldn't find an available UDC".
   Removed in snapshot47.

Snapshot47 run1 also showed that configfs refuses a second configuration with
the same `bConfigurationValue` (`usb_add_config_only`). The diag's `c.1` made
Android's `mkdir configs/b.1` fail with EBUSY.

The first handoff unbound the gadget from the diag process itself. It never
fired, most likely because the `kernel` domain has no configfs rule after
policy load. That is unconfirmed, since audit messages were rate-limited.

The diag now uses `c.2`. Before policy load it appends an
`on property:sys.usb.configfs=1` action to
`/vendor/etc/init/hw/init.qcom.usb.rc`, so init itself writes `UDC=none`.
Run4 shows:

- the action is processed at 123.9 s;
- adb is up on `6.12.93-4k-g86cf5e36949c` at about 148 s, with
  `sys.usb.state=adb`.

## 4. QRTR (snapshot47)

`CONFIG_QRTR` and `CONFIG_QRTR_SMD` are now built in. Results:

| Service | Result |
|---|---|
| `tftp_server` | No longer crash-loops (it opens `AF_QIPCRTR` directly) |
| `vendor.qrtr-ns` | Exits 1 in a loop. Unconfirmed: probably the in-kernel QRTR name service already owns the control port |
| `pm-service` / `pm-proxy` | Still loop with `PerMgrSrv: Failed to get system information` and `PerMgrProxy: Failed to get device configuration`. Cause not identified |
| BT HAL | `qmi_cci_xprt_qrtr_supported: failed errno[13]`: the vendor policy denies `hal_bluetooth_qti` `qipcrtr_socket create` |

The modem (mpss) remoteproc is still disabled in the tissot DTS.

## 5. The boot blocker is now graphics, not only display

Headless runs (`-DANDROID_HEADLESS`) remove the vendor composer and
LiveDisplay rc files: init reports `service vendor.hwcomposer-2-1 not found`.
surfaceflinger still aborts, and run4 logcat gives the reason:

```
E Adreno-GSL: <ioctl_kgsl_driver_entry:878>: open(/dev/kgsl-3d0) failed: errno 2
W libEGL  : eglInitialize(...) failed (EGL_BAD_ALLOC)
F DEBUG   : Abort message: 'no suitable EGLConfig found, giving up ...'
```

The vendor Adreno EGL driver needs the downstream KGSL GPU driver, and the
vendor sdm HWC needs the downstream MDSS fbdev interface (`libsdmcore`:
`/dev/graphics/fb*`, `msm_fb_*` sysfs, `/dev/mdss_rotator`). Neither exists
in 6.12. The current VM builds also lack `DRM_MSM`, even though the fragment
requests it; snapshot42, the last build with it, lit the panel.

Open decision:

- **Mainline:** DRM_MSM display and GPU, with open userspace (Mesa freedreno,
  drm_hwcomposer, minigbm).
- **Downstream:** forward-port KGSL and MDSS so the stock vendor blobs work.

## 6. Other observations

- **Snapshot47 run2:** produced no evidence at all. Logdump is all zeros and
  the SD log is run1's stale copy. The user saw a blue screen, then a fast
  reset. Run3 booted the identical image normally, so the cause is unknown
  and has not recurred.
- **Boot deadline:** the diag reboots the phone if init has not logged
  `processing action (sys.boot_completed=1` by 360 s. It fired in runs 1, 3
  and 4. With adb available, a run can be cut short with `adb reboot` once
  logcat has been pulled.
- **No dmesg over adb:** the shell user cannot read `dmesg` on 6.12 (user
  build). The kernel log comes from logdump and the SD card.
