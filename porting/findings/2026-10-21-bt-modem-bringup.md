# Bluetooth and modem bring-up: implementation and run334 boot result

Status: **code implemented, built and booted as run334 (#41). Bluetooth is
verified working on hardware. The modem is still offline: the initramfs child
failed to set `firmware_class.path` with `errno=13` and exited before the MSS
`start`, so the start code was never reached. The reset cause is unverified
and the start never ran.** The previous session established
the two root causes at runtime; this change adds the missing kernel interfaces
and the MSS start. The run334 result is below; the remaining work is the
firmware-path permission and then the MSS start.

## Bluetooth

### What was proven at runtime

The ROM's QTI Bluetooth HAL (`android.hardware.bluetooth@1.0-service-qti`)
does not use the mainline HCI transport. Its `mct_transport` opens the two
WCNSS SMD packet channels directly as character devices:

```
mct_transport: InitTransport: Cannot open /dev/smd3: No such file or directory
Retry after 2 seconds
data_handler: InitTimeOut: SoC Initialization stuck detected
Killing daemon to recover as firmware download is stuck
```

The framework then aborts at `hci_backend_hidl.cc:102`. The QTI HAL logcat
from that run is the source of the four lines above; the same run's kernel
log carries the secondary SELinux denial at
`../artifacts/snapshot60/logs-2026-10-21/run333d-155756/live-kmsg.txt:468`:

```
avc: denied { create } for comm="android.hardwar"
 scontext=u:r:hal_bluetooth_qti:s0 tcontext=u:r:hal_bluetooth_qti:s0
 tclass=qipcrtr_socket permissive=0
```

The stock donor kernel maps the two channels in
`../../kernel_xiaomi_msm8953/arch/arm64/boot/dts/vendor/qcom/msm8953.dtsi:1464-1482`:

| channel | device | property |
|---|---|---|
| `APPS_RIVA_BT_ACL` | `/dev/smd2` | `qcom,smdpkt-fragmented-read` |
| `APPS_RIVA_BT_CMD` | `/dev/smd3` | `qcom,smdpkt-fragmented-read` |

The donor driver is `../../kernel_xiaomi_msm8953/drivers/char/msm_smd_pkt.c` and its
header is `../../kernel_xiaomi_msm8953/include/linux/msm_smd_pkt.h`.

### Why the mainline path was not used

The mainline `btqcomsmd` driver creates `hci0` through the WCNSS control
interface. Loading `bluetooth.ko`, `btqca.ko` and `btqcomsmd.ko` by hand did
create `hci0` under `a204000.remoteproc:smd-edge:wcnss:bluetooth`, but the
QTI HAL still failed on `/dev/smd3`; the HAL ignores `hci0`. `btqcomsmd` and
`smd_pkt` also both claim the same WCNSS channels, so the port keeps
`btqcomsmd` out of the way instead of letting the two race.

### What was added

- `drivers/char/msm_smd_pkt.c`: the donor driver, adapted to the 6.12 rpmsg
  and driver-core APIs:
  - `struct rpmsg_driver.signals` and `rpmsg_get_sigs()`/`rpmsg_set_sigs()`
    do not exist upstream. Mainline has only `flowcontrol`; the TIOCM signal
    state is now a local `sigs` field, the observed `TIOCM_OUT1|TIOCM_OUT2`
    reset notification is kept, and `flowcontrol` wakes readers.
  - `class_create()` takes one argument since 6.4.
  - `dev_set_name()` is called with a literal `"%s"` format.
  - `.poll` returns `__poll_t` and uses `EPOLL*`.
  - CAF `ipc_logging` is replaced by `pr_debug`/`pr_err_ratelimited`.
  - The rpmsg driver registration result is checked, and the device/cdev/IDA
    error paths no longer free the same ID twice or release an uninitialised
    device.
  - The driver remains `bool`/built-in; there is no module-unload path.
- `include/linux/msm_smd_pkt.h`: the donor ioctl header. The driver keeps its
  own `SMD_PKT_IOCTL_QUEUE_RX_INTENT` (`_IOW(magic, 0, unsigned int)`) because
  that is the number the stock driver accepts.
- `drivers/char/Kconfig`, `drivers/char/Makefile`: `CONFIG_MSM_SMD_PKT`,
  `depends on RPMSG_QCOM_SMD`.
- `porting/tools/build-kernel.sh`: forces `CONFIG_MSM_SMD_PKT=y` and forces
  `CONFIG_BT_QCOMSMD` off. The latter is what prevents `btqcomsmd` from
  claiming the same channels if it is ever loaded.
- `arch/arm64/boot/dts/qcom/msm8953.dtsi`: a `qcom,smdpkt` node with only the
  two WCNSS Bluetooth children. The modem/ADSP packet children in the donor
  DTS are deliberately not added; those channels are not needed for the
  Bluetooth HAL, and the modem data path is a separate change that has to be
  verified on its own.
- `porting/policy/port-genfs-kgsl.cil`: the observed
  `(allow hal_bluetooth_qti self (qipcrtr_socket (create)))`. Only `create`
  is granted because it is the only permission in the captured AVC; the next
  boot's log has to show whether the HAL goes on to `connect`/`send`/`recv`
  against the `qrtr` peer.

The stock `/vendor/etc/ueventd.rc` already gives `/dev/smd2` and `/dev/smd3`
to `bluetooth:bluetooth`, and `vendor_file_contexts` already labels
`/dev/smd.*` as `smd_device`; no ueventd change is expected.

### What run334 showed

- `CONFIG_MSM_SMD_PKT=y` and `# CONFIG_BT_QCOMSMD is not set` in the
  resolved config.
- `/dev/smd2` and `/dev/smd3` exist, owned by `bluetooth` (major 235,
  minors 0/1), under `/sys/class/smdpkt/`; `smd3` reports
  `name=APPS_RIVA_BT_CMD` and `open_timeout=120`.
- The QTI HAL (`android.hardware.bluetooth@1.0-service-qti`, PID 673) and
  `com.android.bluetooth` are running; `dumpsys bluetooth_manager` reports
  `State: ON`, and the user confirmed the controller works (enable/scan).
- No `qipcrtr_socket` denial appears in the captured dmesg/pstore. The
  `mct_transport`/`InitTransport` lines are not in the current logcat
  buffer, so the HAL's own open log was not captured; the running HAL and
  the `ON` state are the evidence.

## Modem

### What was proven at runtime

`/sys/class/remoteproc/remoteproc0` (the `4080000.remoteproc` MSS) is
`offline`. `drivers/remoteproc/qcom_q6v5_mss.c:2015` sets
`rproc->auto_boot = false`, and nothing in the initramfs or the ROM writes
`start` to its `state`. The MSS therefore never loads `mba.mbn`/`modem.mdt`,
the modem never exposes its QRTR node, and `qcrild`/`qcrild2` have no modem to
talk to. The QRTR traffic on node 1 is the ADSP (`remoteproc1`); the MSS has
no rpmsg channels while it is offline.

The firmware is present in `/vendor/firmware_mnt/image`, but
`firmware_class.path` does not include that directory by default. Starting
the MSS from the su shell failed first with `-13` reading `mba.mbn` and then
with `-2`; the same shell can `dd` the file, so the `-13` is the caller/LSM
context, not file access. The initramfs `harvest_modem_child()` already
changes `firmware_class.path` to `/vendor/firmware_mnt/image` and rebinds
ADSP/WCNSS from a root child that can load from that partition.

### What was added

`scripts/initramfs-diag/init.c`: `start_remoteproc("mba", log)`, called after
the existing ADSP/WCNSS rebinds in `harvest_modem_child()`. It walks
`/sys/class/remoteproc`, matches the `firmware` attribute containing `mba`,
logs the state before and after, and writes `start` to `state`. The sysfs
`state` interface is the documented remoteproc user interface
(`Documentation/ABI/testing/sysfs-class-remoteproc`); `auto_boot` remains
false so the start is explicit and observable.

### What run334 showed

- **Not met.** `remoteproc0` is still `offline` with
  `firmware=mba.mbn`; `gsm.sim.state` is empty; no MSS rpmsg/QRTR node
  appeared; `qcrild`/`qcrild2` are running but have no modem; there are no
  `rmnet_data*` interfaces.
- The initramfs child **did run**. The raw logdump
  (`run334-logdump.log`) has `DIAG: fwlate: waiting for modem mount` at
  31.4 s (line 1159), the `modem_b` mount at 40.8 s (line 1848), and then
  `DIAG: fwlate: custom path set=0 errno=13` at 41.4 s (line 2171). The
  child exited on the failed `firmware_class.path` write, before the
  ADSP/WCNSS rebinds and `start_remoteproc("mba")`; the `DIAG: fwlate mba`
  line is absent because the start was never reached.
- The phone reset during the first boots; the MSS start never ran, so the
  reset is **not** explained by it. The recovered pstore is the current
  boot (seq 573/572, ~335 s), no dmesg dump record was recovered, and
  `pull-run-evidence.sh` reports the slot pair's freshness as unverified.
  The reset cause is **unverified**.

The next step is the `firmware_class.path` write failure: the initramfs
child must hold the credentials/permission the sysfs write needs, or the
path must be set before it becomes unavailable. Only after `custom path
set=1` can the ADSP/WCNSS rebind and the MSS `start` be tested.

## Run334 build and boot

- `bash porting/tools/build-kernel.sh run334-bt-modem` built
  `#41 6.12.93-4k-g9ca2c978871f-dirty` with `CONFIG_MSM_SMD_PKT=y` and
  `# CONFIG_BT_QCOMSMD is not set`; the image is
  `porting/artifacts/snapshot60/boot-run334-bt-modem.img`
  (sha256 `58ed5acee8cccb6d5e34639f6bf5d10b7f86c395a2ebddf69a8d2b392ce1e7d3`).
- It was flashed to `boot_b`; the previous #40 image is preserved as
  `boot-run335.img`.
- The logdump was cleared and verified zero before the flash. The pstore
  pull recovered the current boot's console (slots seq 573/572, ~335 s)
  and the raw logdump; it recovered no dmesg dump record and no crash
  record, and reports the slot pair's freshness as unverified. The raw
  logdump carries the initramfs MSS evidence: `run334-logdump.log:1159`
  (`waiting for modem mount`), `:1848` (`modem_b` mounted at
  `/vendor/firmware_mnt`), `:2171` (`custom path set=0 errno=13`).
- The evidence files are under `porting/artifacts/snapshot60/` (git-ignored):
  `run334-ramoops.json`, `run334-logdump.log`,
  `run334-ramoops-slot*-snapshot-console.log`,
  `run334-printk-tail-slot*-periodic-printk.log`.

## Limits and follow-ups

- The `qipcrtr_socket` allow is the observed `create` only. The
  `/data/vendor/ssmdump` directory denial mentioned in the runtime notes is
  **not** fixed: no AVC with the type/permissions was captured, so a rule
  would be a guess.
- The signal/TIOCM behaviour is a local emulation. The donor's remote signal
  bits are not available upstream; the reset notification and the local
  set/get path are preserved, but a client that depends on remote DCD/CTS
  bits will not see them.
- The driver is built-in (`bool`) and has no unload path. The platform device
  is a static DT node; the child devices are never removed in normal use.
- Only the two WCNSS Bluetooth children are described. The modem/ADSP
  `smdpkt` devices (`smdcntl*`, `smd22`, `apr_apps2`, ...) are not created.
  If the ROM's data path turns out to need them, add them as a separate,
  verified change; the current modem plan uses QRTR/rmnet.
- There is no YAML binding for `qcom,smdpkt` in this tree. The donor's text
  binding under `arch/arm64/boot/dts/vendor/bindings/arm/msm/smdpkt.txt` is
  the reference; `make CHECK_DTBS=y` will report the compatible as
  undocumented until a schema is added.
- The implementation is compiled (run334 #41) and the Bluetooth path is
  boot-verified. The MSS start is not verified because it was never
  reached: the initramfs child's `firmware_class.path` write failed with
  `errno=13` (`run334-logdump.log:2171`) and the child exited before the
  ADSP/WCNSS rebinds. The phone reset during the first boots; the cause is
  unverified and is not explained by the start, which never ran. The next
  work is the firmware-path credential/permission problem, then the start.

## References

- Donor driver and DTS: `../../kernel_xiaomi_msm8953/drivers/char/msm_smd_pkt.c`,
  `.../include/linux/msm_smd_pkt.h`,
  `.../arch/arm64/boot/dts/vendor/qcom/msm8953.dtsi`.
- Mainline rpmsg API: `include/linux/rpmsg.h` (`flowcontrol`, no signal API);
  the CAF signal series was never merged. The rpmsg documentation is
  `https://www.kernel.org/doc/html/latest/staging/rpmsg.html`.
- Remoteproc sysfs ABI:
  `Documentation/ABI/testing/sysfs-class-remoteproc`.
- MSS firmware names: `drivers/remoteproc/qcom_q6v5_mss.c`
  (`hexagon_mba_image = "mba.mbn"`, `hexagon_mdt_image = "modem.mdt"`,
  `auto_boot = false`).
- QTI HAL failure: the QTI Bluetooth HAL logcat from the diagnostic run;
  qipcrtr AVC at
  `../artifacts/snapshot60/logs-2026-10-21/run333d-155756/live-kmsg.txt:468`.
- Boot/log procedure: `porting/REFERENCE-boot-testing.md`.
