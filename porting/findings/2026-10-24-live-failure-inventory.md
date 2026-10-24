# Failure inventory and repair ledger — 2026-10-24

This records observed failures and the state of our repairs. It supplements
[the current work queue](../FAILING-COMPONENTS.md), preserving the existing
camera/audio work. Fix one component at a time; log volume is not a measurement
of battery energy. A warning/error label alone does not establish a broken
hardware component or a kernel regression.

## Device and evidence coverage

Evidence: [failure-audit-20261024](../artifacts/snapshot60/failure-audit-20261024/).
Short `file:line` references below are relative to that directory.
`capture.json` records each command, UTC start/end, exit status and output hash;
`SHA256SUMS` covers the saved evidence. Collection used wireless ADB and read-only
device commands. No reboot, service stop, settings change, build or installation
was performed.

- Live identity: `identity.txt:1` through `:5`: 2026-10-24 10:55 local,
  `6.12.93-4k-gd13339db2abb #44`, boot UUID
  `d03407f5-f1e7-42d5-a22b-5799c757e898`, uptime 33125.72 s, 4096-byte pages.
- `logcat.txt`: 52,789 parsed records across buffers, with an aggregate retained
  span 05:15:43–10:55:08. Different buffers have different retention windows;
  this is not 5.5 hours of continuous coverage for every component.
- `dmesg.txt`: 869 parsed records, timestamps 5987.910–6066.720 s. These kernel
  timestamps and wall-clock uptime are different clocks across suspend.
- `logdump-prefix.txt`: printable text from the first 8 MiB of the logdump
  partition, not a complete partition capture. The leading segment runs from
  4.666 to 183.692 s. At **line 9233** the sequence drops from 9505 to 8965 and
  older epoch values follow: classify that tail as stale, not current evidence.
  The retained prefix has no embedded boot UUID; keep its provenance distinct
  from live logs. Line 3 also reports an initial kmsg overrun.
- `earlier-observations.txt` preserves the earlier approximately 10:49 analysis
  output. It is explicitly a **truncated summary**, not a saved raw log. Its
  internal source-line numbers refer to the earlier stream. In particular,
  the modem event had rotated out of the later raw dmesg capture.
- `severity-index.tsv` retains **all 31,321 parsed warning/error/fatal records**
  from the three raw log sources, including stack lines and duplicate reports.
  Each has source, line, timestamp, native severity, logger, message and
  provenance: 27,320 live, 3,738 retained-prefix, 263 stale-tail records.
  These are records, not 31,321 separate failures. No low-volume logger or
  warning was silently discarded. `kernel-patterns.tsv` groups kernel messages
  for navigation; its numeric normalization is not a root-cause classifier.
- Logcat W/E/F (and A if present) and kernel priorities 0–4 are indexed using
  their native levels. Kernel records with facility bits use priority & 7.
  SELinux denials logged at Android INFO remain in the raw logs; kernel copies
  at WARNING are included in the severity index. Rate-limited/lost messages
  mean this cannot enumerate every event that occurred overnight.

## Our fixes and their actual status

| Item | Change / location | Checks completed | Status / remaining proof |
|---|---|---|---|
| USB suspend candidate | `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts`, `&usb3_dwc3`: add donor `snps,dis_u2_susphy_quirk` and `snps,dis_enblslpm_quirk` | Compared donor and supported binding/code; strict checkpatch and whitespace passed | Source edited only. Not built or boot-tested; PLL failure repair is unverified. |
| Restart guards | Removed the proposed dpmd/peripheral-manager stop guards from `scripts/initramfs-diag/init.c` after review | Restored file matched HEAD; host guard self-check passed | Containment withdrawn. This is not a repair of the crashing services. |
| dpmd mapping-size repair | `porting/tools/patch-dpmd-hidl.py`, with `porting/tests/test_patch_dpmd_hidl.py`; local output `dpmd.hidl-default` | Nine host tests plus real-binary checks passed. On run401, two candidate service starts remained stable for 120.647 s and 60.695 s, with candidate hashes, expected SELinux domain and no new mapping-size abort in either live crash capture | **Temporary file binding is active on run401.** Original ROM file retained. Reboot removes the binding. Persistent integration, end-to-end data services and battery benefit remain unverified. |
| JPEG reset compatibility | Existing parallel camera fix `4646f53406c3` | Existing camera host checks recorded in current tracker | Not built or device-tested. Not part of this dpmd repair; retain existing camera qualification requirements. |
| Other failures below | No new code changes | Observations and evidence only | Open; do not mark fixed merely because a service was disabled or a log became quiet. |

## Component failures and warnings to investigate

Counts below apply only to the named retained source/window. Severity is the
message's native level; priority orders follow-up work, not inferred causality.

| ID / component | Severity and evidence | Established behavior / recurrence | Status and next check |
|---|---|---|---|
| F01 — dpmd / HIDL | F: `logcat.txt:10450`, `:10466`; `tombstone-dpmd.txt:16`, `:33`, `:34` | 334 SIGABRT records, approximately every five seconds. Abort explicitly reports incompatible ProcessState mapping sizes; stack reaches `init_child`. Fresh run401 baseline repeats the abort. | Mapping-size abort stopped in two temporary candidate service-start trials below. Persistent integration and functional data-service qualification remain open. |
| F02 — USB PHY / DWC3 / GCC | E/W: `logdump-prefix.txt:8168`, `:8171`, `:8177`, `:8240`, `:7806`; live state `usb.txt:1` | Retained prefix shows QUSB2 PLL lock failure and resume `-16` at 149.098 s, nine clock-stuck messages and six HS-PHY-not-L2 messages. Live UDC is `not attached`, child runtime state `suspended`, parent active, gadget configured for adb. | Donor-quirk source candidate only. Compare exact known-good artifact and test resume on a user-built image. Overnight sleep alone is not established as the trigger. |
| F03 — FastRPC / adsprpcd | E: `logcat.txt:35443`, `:35444`, `:35445`, `:35439` | 2,147 listener-open errors and 2,148 25 ms retry notices in approximately 67 s. Reports ENOSPC during apps-device initialization. | Repeated failure, strong activity candidate; energy contribution unmeasured. Trace actual failing open/ioctl and allocation lifetime. **ENOSPC here is not proof that storage is full.** Prior GETINFO/GET_DSP_INFO repairs do not prove this different failure is fixed. |
| F04 — modem remoteproc / firmware IPA | Kernel E with fatal content: `earlier-observations.txt:158` through `:161` | Earlier stream observed firmware `ipa_util.c:1087` assertion at 5686.001 s and remoteproc recovery. Counter said `handling crash #10`; only one such event is preserved in this summary. | Modem subsystem crash, not evidence of an AP kernel panic. Obtain another full raw event and correlate IPA/firmware/host transactions before assigning a cause. |
| F05 — peripheral manager / proxy | E: `logcat.txt:35820`, `:35821`, `:35827`; missing interfaces in `peripheral-discovery.txt.stderr:1` | 28 missing SSR-root messages; 14 manager system-information failures and 14 proxy configuration failures. Expected `/sys/bus/msm_subsys/devices` and `/sys/bus/esoc/devices` are absent; remoteprocs are running. | Discovery ABI mismatch is observed. Audit the donor libmdmdetect/SSR lifecycle before proposing compatibility code. Do not fake nodes or stop services as the repair. |
| F06 — diagnostic transport | E/SELinux: `logcat.txt:35957`; `peripheral-discovery.txt.stderr:3`; `dpmd-analysis.txt:337` | `/dev/diag` absent; HIDL lookup is denied/unavailable. Earlier capture also shows socket-connect errors (`earlier-observations.txt:13`). | This changes dpmd startup behavior and leaves diagnostics unavailable. Matching the mmap sizes does not implement diag transport or remove its warnings. Compare donor behavior and actual required ABI. |
| F07 — framebuffer suspend | W: `logdump-prefix.txt:7639` | Ten WARNING headers at `fb_set_suspend`, `drivers/video/fbdev/core/fbmem.c:598`; stack lines are not extra incidents. | Open. Trace caller/console-lock contract against donor and current framebuffer code. No edit or verified explanation yet. |
| F08 — Wi-Fi resume / TX completion / logging features | W/E: `logdump-prefix.txt:7686`, `dmesg.txt:141`, `logcat.txt:35665`, `:35666` | One ieee80211_resume WARNING header in the prefix; six Bad TX completion warnings in live kernel capture. Wi-Fi logger-feature requests repeatedly return -3. Wireless ADB continues to work. | Separate resume, TX-completion and optional-feature issues. No blanket Wi-Fi outage established; wakeup counts alone do not measure drain. |
| F09 — audio ASoC register access / EOS | E: `logdump-prefix.txt:223`, `:913`, `:6262` | Repeated component read/write/update errors return -5; six CMD_EOS failures before the stale-tail boundary. | Preserve current audio blockers. Trace register-less component callbacks and EOS transactions separately; playback-open or registration alone does not qualify audio. |
| F10 — data services ANR / telephony / IMS / SIM | E/W: `logcat.txt:4032`, `:26732`, `:28749`, `:26943`, `:27035` | `.dataservices` ANR at 09:47:39; IMS unavailable, SIM_ERR/decoding errors, and unsupported newer radio API calls. | Distinguish modem-recovery fallout, missing IMS/data services and unsupported optional APIs. Do not infer failed SIM hardware or complete cellular failure from these messages. |
| F11 — missing UCE service / init requests | E/W: `dmesg.txt:13`; `logcat.txt:35661` | Repeated `com.qualcomm.qti.uceservice@2.3::IUceService` start requests cannot find a service definition. | Userspace service/manifest compatibility follow-up; no service disabled by this work. |
| F12 — SELinux / wake statistics / memtrack | E/W: `logcat.txt:52674`, `:52677`, `:5942`; `dmesg.txt:4`, `:173` | system_suspend cannot read camera wakeup attributes; memtrack and application DevCheck reads are denied; audit loss/rate limiting is present. | Record distinct subjects/targets. Denied diagnostics are not proof that the underlying device is broken. Correct labels/policy only after tracing ownership; do not disable enforcement. |
| F13 — sensors, thermal-engine, GNSS / time services | E/W: `earlier-observations.txt:117`, `:128`, plus complete earlier logger summaries | Earlier capture shows sensor QMI -16, modem thermal-client transport -2 and location/time errors around subsystem disruption. | Raw context for these events is incomplete. Correlate another captured recovery; no claim that every sensor or thermal function fails. |
| F14 — keystore / credential / root-module configuration | E/W: `logcat.txt:1261`; `earlier-observations.txt:14`, `:105`, `:106` | Five INCOMPATIBLE_BLOCK_MODE reports in retained system buffer; earlier credential decryption and incomplete keybox parse reports. | App/ROM/root-module investigation, separate from proven kernel failures. Stack-line counts are not operation counts. No identity/attestation configuration changes made. |
| F15 — crash-reporting fallout | E/W: `logcat.txt:2`, `:3`; full logger counts below | NativeTombstoneManager rejects root UID tombstones (1,925 records); NativeCrashListener cannot find ProcessRecords (1,924 records). DEBUG repeats stack metadata at F. | Correlated with native restart churn; do not count every reporter line as another crashing component. Reassess after fixing dpmd. |
| F16 — framework / applications / storage cleanup | W/E: all remaining logger rows and exact records in `severity-index.tsv` | AppOps unfinished operations, binder/RefBase/process cleanup, launcher/system warnings, storage lifetime/sysfs warnings and other lower-frequency records remain preserved. | Untriaged individually, not silently classified as harmless. Reproduce a concrete user-facing fault before changing framework or storage behavior. |
| F17 — boot policy / configuration | E/W: `logdump-prefix.txt:1006`, `:1019`, `:1451`, `:1508`, `:1636` | Retained boot reports vbmeta read, early gadget creation, linker configuration, property permission and init-trigger parsing failures. | Distinguish expected diagnostic-boot substitutions from functional defects by comparing a real known-good image. Early gadget warning alone does not explain the later PLL failure. |
| F18 — camera LED flash / torch | Run401 `camera-run401-20261024T064738Z/camera-service.txt:48`, `:509`, `:927`, `:1309`; `flash-nodes.txt` in the same directory | Both cameras report no flash unit / FLASH_INFO_AVAILABLE=false; no flash/torch LED class device is exposed. Board camera DTS explicitly omits the donor PMI8950 flash connection. | Confirmed porting gap, not evidence of a failed physical LED. Restore the actual PMIC flash/torch resources, driver support and camera link after review/approval; no flash source edit or LED activation performed. |
| F19 — fingerprint HAL | F: run401 `camera-run401-20261024T064738Z/crash.txt:154`, `:163`, `:169` | Native fingerprint-service SIGSEGV at address 0xc0 is present in the new boot's crash buffer. | Fresh failure evidence, exact cause unverified. No fingerprint changes in the dpmd trial. |
| F20 — Metrolist startup | E with fatal exception: run401 `camera-run401-20261024T064738Z/crash.txt:307` through `:330` | Application startup throws because credential-encrypted SharedPreferences are unavailable before user unlock. One retained event, not a kernel attribution. | Record for app/direct-boot investigation; no app settings or storage changed. |

## Overnight battery observations

`power.txt:185` through `:192` reports 483 minutes in deep noninteractive mode,
629 mAh and 35 percentage points consumed (78.1 mAh/h). These are Android's
accounting values, not a calibrated power measurement. `suspend.txt:122` through
`:145` shows 6067 successful and 915 failed attempts, including one failed
resume; `suspend.txt:97` lists 6383 `wcn36xx_rx` wakeups. The device did spend
substantial time suspended; this does not show that all peripherals resumed
correctly, or identify which component consumed the energy.

At capture, `battery.txt` reports 2%, USB present/charging, a 100000 µA input
limit and negative battery current. That observed combination warrants charging
qualification alongside USB recovery. It does not establish the charging limit's
cause. Active app use, wireless ADB and diagnostic snapshots contaminate an idle
baseline. A controlled before/after measurement is still needed for each repair.

## dpmd: exact repair candidate and why it is here

`dpmd-analysis.txt` preserves installed binary hashes and disassembly. Startup
calls Diag_LSM_Init (`:103`) before child initialization. The diagnostic library's
ENOENT branch (`:337` onward) reaches an Idiag HIDL lookup (`:402`) when
`/dev/diag` is missing. The installed HIDL default is 1 MiB minus two pages
(`:192` onward), but dpmd's explicit request is 8192 bytes (`:139`, `:142`).
The captured abort names the resulting incompatible mapping sizes.

Cross-check: [AOSP ProcessState.cpp](https://android.googlesource.com/platform/system/libhwbinder/+/062365942b0fd54cc5e6af46e12a5f90eeb5d4a1/ProcessState.cpp)
defines the same default and checks explicit requests against the existing
mapping. Local history `6ca61ad883549` already recorded this double-init
condition; `porting/TRACKER-kgsl-port.md:1309` is historical, not a repair.
The saved donor capture
`porting/artifacts/snapshot60/stock419-camera-20261023T143434Z/logcat.txt:84`
and `:86` shows dpmd denied access to an existing `/dev/diag` node. That differs
from ENOENT on this port; the diagnostic library branches differently. This
limited donor capture is not proof of complete stock data-service qualification.

The binary-only repair belongs in a porting tool, not the binder kernel driver
or a global HIDL assertion change. At **file offset 0x5468**, instruction bytes
`e0 03 13 32` request 0x2000; replacement `e0 1b 13 32` requests **0xfe000**
(1,040,384 bytes). Only byte **0x5469** changes. This matches the installed
default on the verified 4096-byte-page device, while retaining the HIDL check.

| Input/output | SHA256 |
|---|---|
| dpmd.original | `30a02d9a00f3496a1885409f6e6e5db7d4276fdb4ae56d1fec3d53e4ff9caeb8` |
| libhidlbase.so.original | `343d42aa7b046a2c060dd170e9ed68e668a04bf669babc4e672636d91a2dd535` |
| dpmd.hidl-default | `61db21d3ac67a266576e99a8b2fbef304d3ae2a84ebc19e14ffe44ae0bb72646` |

The patcher refuses unknown versions, other page sizes, unexpected instructions,
an unexpected result digest, and all existing output paths (including symlinks
and input files). Supply the actual device `getconf PAGESIZE` result; it does
not connect to the device itself. Example, from the repository root:

```sh
python3 -B -m unittest discover -s porting/tests -p test_patch_dpmd_hidl.py -v
python3 -B porting/tools/patch-dpmd-hidl.py \
  porting/artifacts/snapshot60/failure-audit-20261024/dpmd.original \
  porting/artifacts/snapshot60/failure-audit-20261024/libhidlbase.so.original \
  /tmp/dpmd.hidl-default --page-size 4096
```

Nine host tests passed, including wrong/truncated/already-patched input, wrong
library/page size, instruction/result validation, input preservation and output
overwrite/symlink refusal. `dpmd-patch-checks.txt` records a real-input CLI run,
disassembly, unchanged 29,272-byte size and overwrite rejection. Synthetic test
fixtures do not validate the proprietary binary by themselves; the separate
real-input check supplies that evidence. No source for this vendor executable
was available in the inspected trees. The original local binary/library copies
are retained read-only; they and the candidate are local evidence, not files to
publish. The runtime follow-up below records the approved deployment and rollback
observations; end-to-end data-service behavior remains unqualified.

### Proposed next step — temporary dpmd-only device trial

Read-only inspection found `/system/system_ext/etc/init/dpmd.rc:12` starts
the exact executable above with three sockets; its service stanza has no
`onrestart` actions. The executable is root:shell, mode 0755, label
`u:object_r:vendor_dpmd_exec:s0`. Android init and the root shell currently
share mount namespace `mnt:[4026533126]`. The root filesystem is read-only;
`/data` is writable and allows execution. These observations support a
temporary bind-mount trial; they do not prove SELinux will permit it.

After separate explicit approval, stage the candidate as
`/data/local/tmp/dpmd-hidl-20261024/dpmd`, preserving the observed owner, mode
and SELinux executable label. Verify its SHA256 and recheck the installed
binary/library hashes and page size. Stop only the init `dpmd` service, bind
the staged file over `/system/system_ext/bin/dpmd`, then start the service.
Capture logs and inspect parent/child PIDs and executable hashes for at least
two minutes. Success for this narrow test means the matching abort and restart
cycle cease with the candidate actually running; it is not full data-service,
radio, battery or deep-sleep qualification.

Rollback: stop dpmd, unmount the temporary file binding, verify the original
SHA256 is visible again, and start the original service. Abort/rollback on
label, mount, service-start or runtime validation failure. A reboot also drops
this nonpersistent binding, but no reboot is proposed. Data-policy services
may be interrupted briefly. The phone remains at 2% in the readiness check;
a power loss would invalidate the trial. At proposal time no stage file, label
change, bind mount or service restart had been performed.

Trial attempt after approval: the read-only preflight at **11:08:17 local**
still saw the original binary/library hashes and boot UUID, USB power present,
battery 3%, and dpmd restarting with no PID at that instant. A host positional
output check misread the missing PID line; this was a checker error, not loss
of USB power. Before the keyed retry could complete, wireless ADB disconnected.
`adb devices` became empty, reconnect to the advertised endpoint failed, and
host USB enumeration still showed no phone. The reason for transport loss is
**unverified**. No candidate was transferred, no device directory/file was
created, no mount was applied and no service state was changed; no rollback is
needed. Evidence/status: `dpmd-trial-20261024/preflight.txt` and
`dpmd-trial-20261024/attempt-status.json`. At that point the approved trial
awaited connection recovery; the offline candidate had not become a device fix.

Connection recovered at `192.168.1.75:43273`, but the phone is now on a
**different boot and kernel**: `4.19.325-cip136-st20-perf-mglru-next-gdf4a1f863991`
#5, UUID `6375887f-9d16-4790-8d56-9481f9a67588`, battery 41% and USB power
present. This is a donor control, not a test of the 6.12 repair. See
`dpmd-trial-20261024/preflight-reconnected.txt` and
`dpmd-trial-20261024/reconnected-identity.txt:2`.

The same dpmd parent/child PIDs **1247 / 1290**, with unchanged process start
ticks, were observed at uptime 138.98 s and again at 203.50 s. The current crash
buffer contains no dpmd or mapping-size abort. The dpmd, HIDL and diagnostic
library hashes exactly match those on the failing 6.12 boot
(`dpmd-trial-20261024/stock-dpmd-control.txt:5` through `:7`). `/dev/diag`
exists (`:19`), and the child maps `/dev/binderfs/hwbinder` at
`778063e000-7780640000`, **8192 bytes** (`:18`). This corroborates the startup
path distinction with unchanged userspace binaries. It does not qualify every
donor data-service feature, diagnose USB charging, or validate the patch.

No file was staged and no service/mount was changed on this donor boot. The
approved temporary dpmd trial remains pending the **6.12 target kernel**; do not
apply it to this working control just to complete a test. Existing approval is
retained for the planned target-kernel trial; no build/flash/reboot was performed.

### Run401 follow-up — temporary repair verified across two service starts

The user then reported booting `run401-camera.img`. Wired ADB enumerated as
`2819f2320604`; the live kernel reports **6.12.93-4k-gcd4d92e11900-dirty #46**,
boot UUID **bbed414c-1f67-4155-a622-4c138533987c**, 4096-byte pages and 44%
battery at preflight. The userspace hashes still match the verified inputs,
`/dev/diag` is absent, and the captured baseline contains 15 mapping-size
abort messages. The local run401 image matches package SHA256
`ee000d0db2c9591861cac41885dd1c554aeacb04d5d3c8b63d369b9029a35013`;
association with the live RAM boot is the user's report, not a hash of running
RAM. See `camera-run401-20261024T064738Z/local-image-identity.json`.

Trial evidence directory: `dpmd-run401-20261024T064641Z/`.

1. `preflight.txt`, `preflight.json`, `crash-before.txt`: target identity,
   matching binary/library hashes, service repeatedly restarting and failure
   reproduced before any device mutation.
2. `stage-candidate.txt`: candidate copied to the approved
   `/data/local/tmp/dpmd-hidl-20261024/dpmd`, root:shell, mode 0755 and
   `u:object_r:vendor_dpmd_exec:s0`. The staged hash matches the verified output.
3. Initial apply failed when Toybox's bind-remount command selected the backing
   `/data` block device and returned EBUSY. The cleanup handler unmounted the
   temporary binding and restarted the original. `rollback-verification.txt`
   independently verifies the original hash and no remaining file binding.
   This was a setup failure before patched-service execution, not a failed
   mapping-size repair. [Toybox mount source](https://github.com/landley/toybox/blob/master/toys/lsb/mount.c)
   shows its remount lookup and bind autodetection; the existing installed
   `/data/adb/ksu/bin/busybox mount` supplied the working bind-remount operation.
4. `retry-apply-candidate.txt`: temporary binding applied with read-only,
   executable, nodev flags and the original domain-transition permissions;
   the original `/data` mount flags and SELinux policy were not changed.
   `retry-sample-00.txt` through `retry-sample-12.txt`, `retry-samples.json`:
   **PIDs 11740 / 11744 stable for 120.647 s**, candidate executable hashes
   on both processes, expected `u:r:vendor_dpmd:s0` domain and a 0xfe000-byte
   HIDL mapping. `retry-crash-live.txt` contains no dpmd or mapping-size abort.
5. `controlled-restart.txt` and `restart-sample-00.txt` through
   `restart-sample-06.txt`: fresh parent/child **12392 / 12394**,
   stable for **60.695 s**, same hash/domain checks. `restart-crash-live.txt`
   likewise contains no dpmd or mapping-size abort. Results are summarized in
   `result-retry.json` and `result-controlled-restart.json`.

The temporary candidate remains active. **The on-disk original was not
rewritten; reboot removes the file binding.** `rollback-command.txt` contains
the stop/unmount/original-hash/start sequence. Original-hash recovery was
observed after the initial setup failure; no extra revert/reapply cycle was
needed after the two successful service starts. These are two initializations
on one kernel boot, not two boot tests or an overnight endurance test. The
specific abort/restart loop is resolved in these trials; diag transport,
radio/data functionality, persistent installation and energy improvement
remain separate open checks.

The camera report arrived while dpmd was still at read-only preflight. The
user clarified that the camera failed initially and then worked. Preserve it
as a **user-observed initial failure followed by recovery**, cause unverified.
`camera-run401-20261024T064738Z/` contains identity, logcat, kernel/crash logs,
camera-service metadata, LED-node inventory and an exhaustive severity index:
**6,853 W/E/F/A/kernel-warning-or-higher records**. Logcat conversion emitted
two warnings, retained in `logcat.txt.stderr`, so the capture is not guaranteed
complete. Startup timestamps span different wall-clock dates; trial durations
use monotonic host time and device uptime. No camera fatal appears in that
saved crash buffer; this does not disprove the user's transient failure.

For the separate flash question, both camera-service entries say no flash,
and `android.flash.info.available` is FALSE. The donor
`../oc-test/arch/arm64/boot/dts/vendor/qcom/pmi8950.dtsi:609` defines
`qcom,camera-flash` with real flash/torch/switch sources. The current
`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-camera.dtsi:972` explicitly
omits that connection because the PMIC LED resources are not described.
Commit `8e6263ae9919` documents omitting unsupported flash references when
restoring sensor slots. Android's
[FLASH_INFO_AVAILABLE contract](https://developer.android.com/reference/android/hardware/camera2/CameraCharacteristics#FLASH_INFO_AVAILABLE)
confirms how this capability is exposed. Repair requires the missing hardware
path, not forcing the metadata to TRUE. No PMIC current values were guessed,
no LED was switched on, and no camera/kernel source was changed in this trial.

For USB, cross-check [current upstream QUSB2 PHY code](https://github.com/torvalds/linux/blob/master/drivers/phy/qualcomm/phy-qcom-qusb2.c)
and [DWC3 quirk bindings](https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/usb/snps,dwc3-common.yaml).
These confirm code/property semantics, not that the candidate fixes this phone.

## Complete logger index

The following table accounts for every W/E/F/A logger present in the raw
logcat capture, including framework warnings and crash-report metadata.
Counts are **log records**, not distinct incidents or severity-ranked impact.
Each first-line reference points into `logcat.txt`; full messages and every
occurrence remain in `severity-index.tsv`. Kernel entries are exhaustively
indexed separately in `kernel-patterns.tsv`, with the stale tail marked.

| Logger | W records | E records | F/A records | First source line |
|---|---:|---:|---:|---:|
| `DEBUG` | 0 | 0 | 12376 | `logcat.txt:10412` |
| `adsprpcd` | 0 | 8589 | 0 | `logcat.txt:35439` |
| `NativeTombstoneManager` | 0 | 1925 | 0 | `logcat.txt:2` |
| `NativeCrashListener` | 1924 | 0 | 0 | `logcat.txt:3` |
| `libc` | 66 | 0 | 334 | `logcat.txt:10450` |
| `AppOps` | 292 | 0 | 0 | `logcat.txt:19` |
| `dashboard_refre` | 208 | 0 | 0 | `logcat.txt:35456` |
| `ActivityManager` | 94 | 33 | 0 | `logcat.txt:1274` |
| `libbinder.IPCThreadState` | 110 | 0 | 0 | `logcat.txt:35684` |
| `HidlServiceManagement` | 66 | 0 | 0 | `logcat.txt:35658` |
| `Diag_Lib` | 0 | 65 | 0 | `logcat.txt:35961` |
| `ProcessStats` | 55 | 0 | 0 | `logcat.txt:51` |
| `ImsStats` | 49 | 0 | 0 | `logcat.txt:26784` |
| `WifiHAL` | 0 | 46 | 0 | `logcat.txt:35665` |
| `RefBase` | 42 | 0 | 0 | `logcat.txt:35822` |
| `SIMRecords` | 3 | 37 | 0 | `logcat.txt:26732` |
| `wificond` | 35 | 0 | 0 | `logcat.txt:151` |
| `RILJ` | 0 | 34 | 0 | `logcat.txt:26841` |
| `ProcessCpuTracker` | 32 | 0 | 0 | `logcat.txt:594` |
| `FileUtils` | 31 | 0 | 0 | `logcat.txt:5141` |
| `ContentProviderHelper` | 29 | 0 | 0 | `logcat.txt:818` |
| `PerMgrProxy` | 0 | 28 | 0 | `logcat.txt:35825` |
| `libmdmdetect` | 0 | 28 | 0 | `logcat.txt:35820` |
| `ActivityTaskManager` | 27 | 0 | 0 | `logcat.txt:5426` |
| `SELinux` | 0 | 26 | 0 | `logcat.txt:35957` |
| `keystore2` | 0 | 25 | 0 | `logcat.txt:1257` |
| `JobServiceContext` | 22 | 0 | 0 | `logcat.txt:2814` |
| `android.system.suspend-service` | 0 | 20 | 0 | `logcat.txt:52674` |
| `ImsProvisioningController` | 15 | 0 | 0 | `logcat.txt:26901` |
| `libbinder.Binder` | 15 | 0 | 0 | `logcat.txt:35701` |
| `GsmCdmaPhone` | 0 | 14 | 0 | `logcat.txt:27280` |
| `NetworkPolicy` | 14 | 0 | 0 | `logcat.txt:52` |
| `PerMgrSrv` | 0 | 14 | 0 | `logcat.txt:35821` |
| `RemoteSmartspaceService` | 13 | 0 | 0 | `logcat.txt:3793` |
| `hw-ProcessState` | 0 | 0 | 13 | `logcat.txt:35965` |
| `tombstoned` | 0 | 13 | 0 | `logcat.txt:36029` |
| `Looper` | 12 | 0 | 0 | `logcat.txt:573` |
| `TransitionChain` | 0 | 11 | 0 | `logcat.txt:5433` |
| `SST-0` | 0 | 10 | 0 | `logcat.txt:27080` |
| `UriGrantsManagerService` | 10 | 0 | 0 | `logcat.txt:7904` |
| `CarrierActionAgent` | 0 | 9 | 0 | `logcat.txt:26612` |
| `PackageManager` | 9 | 0 | 0 | `logcat.txt:2853` |
| `Phone-1` | 0 | 8 | 0 | `logcat.txt:27406` |
| `UsimFH` | 0 | 8 | 0 | `logcat.txt:28615` |
| `ContextualAwarenessService` | 0 | 7 | 0 | `logcat.txt:3780` |
| `JobScheduler` | 7 | 0 | 0 | `logcat.txt:1276` |
| `AdbRootService` | 0 | 6 | 0 | `logcat.txt:5958` |
| `MagnificationConnectionManager` | 6 | 0 | 0 | `logcat.txt:2899` |
| `TelephonyAnalyticsSubId` | 0 | 5 | 0 | `logcat.txt:27620` |
| `UsageStatsService` | 5 | 0 | 0 | `logcat.txt:5578` |
| `DreamController` | 0 | 4 | 0 | `logcat.txt:3860` |
| `PowerManagerService` | 4 | 0 | 0 | `logcat.txt:3857` |
| `RemoteAugmentedAutofillService` | 0 | 4 | 0 | `logcat.txt:5726` |
| `EmergencyNumberTracker` | 0 | 3 | 0 | `logcat.txt:27775` |
| `ImsStateCallbackController` | 0 | 3 | 0 | `logcat.txt:27450` |
| `LocSvc_xtra2` | 0 | 3 | 0 | `logcat.txt:35870` |
| `LocTimerMsgTask` | 3 | 0 | 0 | `logcat.txt:35865` |
| `NotificationManager` | 3 | 0 | 0 | `logcat.txt:1407` |
| `RilRatcheter` | 0 | 3 | 0 | `logcat.txt:27087` |
| `SSCtr-0` | 0 | 3 | 0 | `logcat.txt:26885` |
| `SmsDispatchersController` | 0 | 3 | 0 | `logcat.txt:28602` |
| `Transition` | 3 | 0 | 0 | `logcat.txt:3973` |
| `WindowOrganizerController` | 0 | 3 | 0 | `logcat.txt:5618` |
| `ADSC` | 0 | 2 | 0 | `logcat.txt:26828` |
| `ActivityStartInterceptor` | 2 | 0 | 0 | `logcat.txt:7405` |
| `AnswerToReset` | 0 | 2 | 0 | `logcat.txt:28122` |
| `Nl80211Native` | 0 | 2 | 0 | `logcat.txt:52397` |
| `SMSVC` | 0 | 2 | 0 | `logcat.txt:26789` |
| `SSCtr-1` | 0 | 2 | 0 | `logcat.txt:27363` |
| `StorageManagerService` | 2 | 0 | 0 | `logcat.txt:2917` |
| `WindowManager` | 2 | 0 | 0 | `logcat.txt:8849` |
| `android.system.` | 2 | 0 | 0 | `logcat.txt:52676` |
| `vold` | 2 | 0 | 0 | `logcat.txt:2916` |
| `xtra-daemon` | 2 | 0 | 0 | `logcat.txt:35863` |
| `CarrierTestOverride` | 1 | 0 | 0 | `logcat.txt:28375` |
| `LinkBandwidthEstimator` | 0 | 1 | 0 | `logcat.txt:27649` |
| `NotificationService` | 1 | 0 | 0 | `logcat.txt:3904` |
| `RadioConfigResponse` | 0 | 1 | 0 | `logcat.txt:29211` |
| `ShellDesktopMode` | 1 | 0 | 0 | `logcat.txt:5389` |
| `TextToSpeechManagerPerUserService` | 1 | 0 | 0 | `logcat.txt:1457` |
| `UiccCardApplication [0]` | 0 | 1 | 0 | `logcat.txt:27499` |
| `UiccProfile [0]` | 0 | 1 | 0 | `logcat.txt:27506` |
| `UsbDeviceManager` | 1 | 0 | 0 | `logcat.txt:6271` |
| `VoiceMailConstants` | 1 | 0 | 0 | `logcat.txt:28377` |

Validation: every indexed row was checked against its exact source line,
per-logger totals sum to the raw severity counts, all report evidence line
references exist, and the local evidence manifest was verified. No Android
runtime test of either repair has occurred.
