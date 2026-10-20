# Live component audit — run237 port boot (2026-10-18)

## Identity and method

Read-only ADB collection from the phone currently booted on **run237**, plus
static inspection of this tree and of the CAF donor tree at `../oc-test`.

| item | value |
|---|---|
| kernel | `6.12.93-4k #22 SMP PREEMPT Sun Oct 18 16:37:36 +0545` |
| boot ID | `1cf363c6-34da-40d4-8127-a111946aa704` |
| uptime at collection | 255 s / 1024 s idle |
| `sys.boot_completed` | `1` (`init.svc.bootanim=stopped`) |
| privileges | shell UID 2000, **no root** (`su` absent) |
| build artifact | `artifacts/snapshot60/package-run237.json`, kernel payload `47b44e5b…` |

The kernel build string `#22 / Oct 18 16:37:36 +0545` is identical to the boot
audited in `2026-10-18-live-component-audit.md` (run234), but the boot ID differs,
so this is a separate boot of the same kernel image, not that earlier sample.

Evidence directory: `../artifacts/snapshot60/live-audit-run237-20261018T170301Z/`
— `shell-sections.txt`, `logcat-all.txt` (34,951 lines), `grep-*.txt`,
`devnodes.txt`, `proc-hal.txt`, `svc-props.txt`, `input-summary.txt`,
`touch-events.txt`, `rfkill.txt`.

Limits: no root, so kernel `dmesg`, remoteproc names/states, `/sys/class/kgsl/*`,
IIO device names and `/vendor/usr/keylayout` reads are denied. Permission denied
is **not** recorded as a component failure. No functional radio, camera, audio
playback, haptic, GPS-fix or suspend/resume test was performed; those rows are
marked from service state and error evidence only.

## Broken components

| # | Component | Runtime evidence | Static cause in this tree | Confidence |
|---|---|---|---|---|
| 1 | **Wi-Fi** | No `wlan0`; `Wifi HAL start failed` ×4; `CMD_STA_START_FAILURE` → `CMD_RECOVERY_RESTART_WIFI` → disable loop, 3 ClientModeManagers stopped (`dumpsys wifi`); `/sys/class/rfkill/` empty; `init.svc.wcnss-service=stopped` | **No WLAN driver is built at all.** `drivers/net/wireless/` has no `cnss2`; `configs/tissot-ack-resolved.config` sets `CONFIG_WLAN=y`, `CONFIG_NET_VENDOR_ATHEROS=y` and `CONFIG_QCOM_WCNSS_CTRL=y` but no Qualcomm WLAN driver (no ath10k/ath11k/ath12k, no `CONFIG_QCOM_CNSS2`). Firmware load is therefore impossible | high |
| 2 | **Bluetooth** | Vendor HAL `android.hardware.bluetooth@1.0-service-qti` dies repeatedly (new PID each cycle, last pid 5853); framework aborts with `system/gd/hal/hci_backend_hidl.cc:102 serviceDied: The Bluetooth HAL died.`; 8 crashes in ~100 s; no `/dev/bt*`, no `/dev/hci*`, empty rfkill | No Qualcomm BT controller/power driver in the port. `CONFIG_BT_QCOMSMD=m` exists but nothing binds the WCN3680; no DT for BT power/rfkill. The HAL's death itself is silent (no tombstone in logcat) — its own error path is unread | failure high, cause medium |
| 3 | **Cellular radio / mobile data** | `gsm.network.type=Unknown,Unknown`; `mVoiceRegState=1(OUT_OF_SERVICE)`, `mDataRegState=1(OUT_OF_SERVICE)`; no operator/SIM/baseband values; `RadioConfigResponse: SET_PREFERRED_DATA_MODEM error 1` | Modem DT historically disabled (see `FAILING-COMPONENTS.md`); no rmnet/QMI plumbing for the interface set below | high |
| 4 | **Network interfaces (whole netdev set)** | Only `lo` and `dummy0` exist (`ip -o link show`). No `wlan0`, no `rmnet_data*`/`ccmni*`, no `usb0` rndis | Consequence of rows 1 and 3 | high |
| 5 | **Hardware navigation keys (capacitive Home / Back / Recents)** | `getevent -pl`: the only devices are `pm8941_pwrkey` (KEY_POWER), `pm8941_resin` (KEY_VOLUMEDOWN), `gpio-keys` (KEY_VOLUMEUP, SW_LID), `generic ft5x06 (3b)` (touch only, **no key codes**) | **Root cause found.** Stock uses the vendor FocalTech driver: `../oc-test/arch/arm64/boot/dts/vendor/qcom/mi8953/tissot/touchscreen.dtsi` has `focaltech,have-key; focaltech,key-number = <3>; focaltech,keys = <172 139 158>; focaltech,key-x-coords = <500 200 800>; focaltech,key-y-coords = <2040 2040 2040>` — `172 = KEY_HOMEPAGE`, `139 = KEY_MENU`, `158 = KEY_BACK`. The port DT (`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts:193`) binds `edt,edt-ft5406` to mainline `drivers/input/touchscreen/edt-ft5x06.c`, which implements **no key support at all**. Upstream `msm8953-mainline` v7.1.3 has the same gap (verified on GitHub), so this is inherited, not introduced | high |
| 6 | ~~**HOME key as a GPIO key**~~ **withdrawn** | — | **Wrong in the first version of this audit.** The GPIO-88 home key cited earlier belongs to `msm8953-cdp.dtsi`, the CDP reference board. Mi A1 builds from `tissot-titanium.dts` → `msm8953-qrd.dtsi`, whose `gpio_keys` has **only** volume-up, exactly like the port. There is no missing GPIO home key; row 5 is the whole story | n/a |
| 7 | **Audio** | `AudioSystem: Function: listAudioPorts Line: 1914 Failed` hundreds of times per minute; `audioserver`: `initStreamVolume failed with 1 will retry` every 2 s; `/dev/snd` contains only `timer`; `/proc/asound/cards` denied (no root) | No Qualcomm ASoC machine driver or WCD codec support: `CONFIG_SND_SOC_MSM` never appears in `configs/tissot-ack-resolved.config`; `# CONFIG_SND_SOC_QCOM is not set`; `CONFIG_SND_SOC_MSM8916_WCD_ANALOG/_DIGITAL is not set`. `sound/soc/qcom/` has no msm-asoc-machine. The `max98927` speaker codec *is* in the port DT (`msm8953-xiaomi-tissot.dts:159`), so the DSP/PAL leg (row 8) is also implicated | high |
| 8 | **FastRPC / ADSP (DSP userspace ABI)** | 850 repeats of `remote_handle_open failed for adsp_default_listener (errno Inappropriate ioctl for device)` → `apps_dev_init failed for domain 0` → `adsp daemon will restart after 25ms`, an endless retry loop; `adsprpcd` process alive but useless | **Measured and fixed on `fix/components`, not yet booted.** Reading `/vendor/lib64/libadsprpc.so` off the device shows 19 CAF commands issued against 10 implemented here; three collide exactly (INVOKE/MUNMAP/INIT_ATTRS vs ALLOC_DMA_BUFF/INVOKE/MEM_MAP) and were being run through the wrong handler rather than refused. Detail and evidence: [fastrpc finding](fastrpc-abi-measured.md) | high |
| 9 | **Camera** | `dumpsys media.camera`: `Number of camera devices: 0`; `init.svc.qcamerasvr=restarting`; no `/dev/video*`, `/dev/media*`, `/dev/v4l-subdev*`; 18 `mm-qcamerad` → `property_socket` SELinux denials | No camera DT at all in the port: no `csi`, `csid` or `msm_camera` nodes in `msm8953-xiaomi-tissot.dts`/`-common.dtsi`; no `CONFIG_QCOM_CAMERA*` in the resolved config. Donor has `mi8953/tissot/camera.dtsi` and `msm8953-camera.dtsi` | high |
| 10 | **Fingerprint** | `/vendor/bin/hw/android.hardware.biometrics.fingerprint-service.xiaomi` dies: `Fatal signal 11 (SIGSEGV) … fault addr 0xc0` in `Session::Session(fingerprint_device*, …)`; `FingerprintProvider/default: HAL died`, `DeadObjectException`; `HAL deaths since last reboot: 1`. The HAL's own library is `gf_fingerprint.goodix.default.so`, so the sensor is Goodix | No fingerprint DT in the port. Donor: `../oc-test/…/mi8953/tissot/fingerprint.dtsi`. The crash is a null `fingerprint_device`, consistent with the absent node. **Cannot proceed further without root**: the HAL library and every other `/vendor/bin/hw` and `/vendor/lib64/hw` binary is unreadable to shell, so the node the HAL expects cannot be recovered the way the FastRPC ABI was | high (broken), low (fix shape) |
| 11 | **Thermal HAL** | Sharper than "not ready": **the vendor thermal HAL never runs at all.** `service list` has `thermalservice` and the lineage health services but no `android.hardware.thermal.*`; `ps` shows only the `thermal-engine` daemon; there is no `init.svc.*` property for a thermal HAL, and logcat holds no tombstone or denial for one | Only 3 thermal zones exist (`thermal_zone0..2` = PMIC/battery/bms); no SoC TSENS. Whether the service is gated by init or dies on a missing node cannot be told from outside: `/vendor/etc/init/*.rc` and the HAL binary are both unreadable to shell | high (never starts), low (why) |
| 12 | **Power HAL control paths** | 1,151 SELinux denials `u:r:hal_power_default:s0 -> u:object_r:sysfs:s0` in this single log window (plus 200 from `system_suspend`) | Unlabelled sysfs paths for GPU pwrlevel / CPU freq / DDR bandwidth. Also see row 13 | high |

## Broken or unusable, cause not yet established

| # | Component | Evidence | What is missing to decide it |
|---|---|---|---|
| 13 | CPU frequency + idle | `/sys/devices/system/cpu/cpu0/cpufreq/` absent, `scaling_cur_freq` absent, `cpuidle/current_driver = none`, no per-CPU cpuidle dirs. All 8 CPUs online (`cpu0..cpu7 = 1`) | Reproduces run188/234 finding; needs root or the CPU OC port (`porting/plan/CPU-oc-test-to-612.md`) before it can be judged |
| 14 | GNSS / GPS | `android.hardware.gnss@2.0-service-qti` (pid 675) runs; location providers register; `hal_gnss_qti` denied `read` on `vendor_pd_locater_dbg_prop` (2 denials) | Port DT has **no** `msm_gnss` node (donor has none either — it comes from the CAF msm dtsi). No fix attempt was possible: no `/dev/gnss*` node and no way to request a fix without root |
| 15 | Haptics | `VibratorManagerService` present, intensities table loaded | No `/dev/qti-haptics`, no haptics DT in the port; donor has `mi8953/common/haptic.dtsi`. Physical vibration untested |
| 16 | IR blaster | `init.svc.irsc_util=stopped`, no IR device nodes | No IR DT; donor CAF likewise relies on a userspace/gpio path not present here |
| 17 | LED | `led-controller@45` present on `i2c_2` with a white `led@0` (`msm8953-xiaomi-tissot.dts:171`) | Node present; actual on/off output unverified |
| 18 | Sensors | `sensorservice` reports **42 h/w sensors running** (BMI120 accel/gyro, AK09918 mag, LTR579 ALS/proximity, QTI virtual sensors); 2 IIO devices exist but `name` is denied without root | Prior audit confirmed accelerometer/light values advancing; the DSP sensor leg (row 8) is still broken, so gyro/mag/prox/fusion unverified |

## Confirmed working on this boot

- **Display / panel**: 1080x1920 @60.000004 Hz, mode 1, `FLAG_SECURE` built-in screen (`shell-sections.txt` DisplayManagerService dump).
- **GPU**: `/dev/kgsl-3d0` present (`crw-rw-rw-`, `system:system`, 503,0); Adreno 506 GLES 3.2 baseline from run234 retained. `max_pwrlevel`/`default_pwrlevel`/`gpuclk` reads denied without root.
- **Touch input**: `generic ft5x06 (3b)` present with correct ranges (`ABS_X 0..1079`, `ABS_Y 0..1919`, 5 MT slots). Key reporting is row 5.
- **ADB over USB**: works; that is the only live channel (see row 4 — the device has no other network path).
- **Battery / gauge / charging**: supplies enumerated, charging status reported (unchanged from earlier audit).
- **Storage / ashmem**: `/data` mounted, `/dev/ashmem` present, long-lived system_server (no run186-style restart).
- **Audio HAL process present** but unusable (row 7).

## Suggested order of attack (not actioned here)

1. Row 5 — hardware navigation keys. **Implemented on branch `fix/components`** (three commits: `62427a7b7` binding, `c71cc10ce` driver, `1a8832870` DTS). checkpatch --strict clean, `make W=1` clean, `dt_binding_check` clean, `CHECK_DTBS=y` adds no new schema warning. Not yet booted: needs a packaged image and a `getevent` check of which physical key maps to which code, since the donor pairs home/menu/back at x=500/200/800.
2. Row 1 — Wi-Fi. Nothing to tune; it needs a WLAN driver port (cnss2 + prima/CAF WLAN) — a project, not a config flip.
3. Row 7+8 — audio: FastRPC ioctl 12 first, then the ASoC machine driver. Audio cannot be judged until the DSP leg talks.
4. Row 9/10/11 — camera, fingerprint, thermal are pure "not ported yet" work with donor references in hand.
5. Row 12/13 — SELinux labels and CPUFreq need a root-capable kernel build before they can be measured honestly.

Nothing in the collection pass was changed, flashed or rebooted; the device was
only read from.

The navigation-key fix above was built and validated but **not booted**; the
device still runs run237.