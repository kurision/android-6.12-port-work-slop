# Mi A1 (tissot) — booting an ACK 6.18 kernel: investigation report

> **Current state: porting/CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUIL_TISSOT.md](BUIL_TISSOT.md).

Investigation recorded on 2026-10-04; corrected after source and saved-image review on the same date. Device observations and boot timings below are historical session reports, not fresh device measurements. Source-verified behavior, saved-artifact checks, and unresolved hypotheses are distinguished explicitly. References and review limitations are in §11.

## 1. Hardware and device

- Xiaomi Mi A1, codename **tissot**, SoC **MSM8953 / SDM625** (14 nm, 8× A53, Adreno 506). 4 GB.
- ROM: **Evox 12.2 / Android 17** (`ro.build.display.id=CP2A.260605.016`). The kernel actually running is *this repo's* CAF 4.19 fork, not Evolution-X's tree.
- Boot image kernel actually running on slot `a`: `4.19.325-cip136-st20-perf-mglru-next-g7f57b3823629` (measured: `boot_a-live.img` header, payload extracted at offset 2048, `gunzip -c | strings`). The earlier report named `4.19.325-cip136-st20-perf-g9d3bf7da9553` as the stock kernel; that string is the stale backup image's (§7), and `…g9d3bf7da9553-dirty` is what `tissot_backup_20261003/img/boot_a.img` actually contains. `g9d3bf7da9553` appears only in the older `ack-boot-test/kernel` dump.
- A/B device: `boot_a`, `boot_b`, `system_a/b`, `vendor_a/b`. **No `dtb` partition** (`../tissot_backup_20261003/partitions.txt`).

## 2. What the ROM demands (measured)

- **Zero kernel modules.** `/vendor_dlkm` contains only `etc`; `/vendor/lib/modules`, `/vendor_dlkm/lib/modules`, `/system_dlkm/lib/modules` and `/lib/modules` do not exist. Every CAF driver is built into the kernel image.
- The session recorded prebuilt CAF binaries including `adsprpcd`, `mm-qcamera-daemon`, `hw/qcrild`, and `hw/audio.primary.msm8953.so`, with 483 `.so` under `/vendor/lib64`. Their precise kernel-interface dependencies were not verified by tracing the binaries in this review. In particular, the KGSL device-name definition alone does not establish an `adsprpcd` → KGSL dependency; this tree's `drivers/char/adsprpc_shared.h` instead defines the FastRPC devices `adsprpc-smd` and `adsprpc-smd-secure`.
- Consequence: a kernel swap cannot be done by "keeping vendor modules"; the CAF drivers must exist **built in**, with matching UAPI.

## 3. Source availability and search limitations

- Earlier search report: `https://android.googlesource.com/kernel/msm/+refs` had 591 branches with no branch-name hits for `msm8953|sdm625|sdm630|sdm632|sdm636|sdm660|tissot`. This search was not repeated in the review and does not establish which SoCs the source supports.
- Earlier CodeLinaro searches reported `msm`, `msm-5.4`, `msm-5.10`, and `msm-5.15`, with `kernel.lnx.5.15.r71-rel` reported as 5.15.206, and an HTTP 404 at `msm-6.x`. Repository availability, release versions, separate driver repositories, and CAF 5.x DTS coverage remain unverified here. A failed lookup of one repository name does not prove that no CAF 6.x tree exists or that no newer CAF tree supports MSM8953.
- Chosen base: **ACK `android17-6.18`**, checked local revision **`89b3cc162c81c59edf4a48f784725849effed283`**, reported kernel 6.18.32. It carries `msm8953.dtsi` and `msm8953-xiaomi-tissot.dts`. The recorded ROM version motivated the choice; that version match does not establish vendor-UAPI compatibility. See [ACK board source][ack-board].
- Community checkout: `github.com/msm8953-mainline/linux`, branch **`barni2000/6.18/develop`**, checked local head **`5b7b995f3738658038066f1b7bc19f0e2a61a1c2`** (full clone, not shallow; 1,399,005 commits). Measured at that head: 16 commits match `tissot` in the subject (`git log --grep=tissot`), 15 touch `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts`, and 17 touch that file or `msm8953-xiaomi-common.dtsi`; the earlier report's count of 14 is reproduced by none of these. `drivers/input/misc/qcom-spmi-haptics.c` is present. `msm8953-mainline/linux-panel-drivers` was identified as a possible panel-driver donor; absence of the driver from every kernel tree is not established, and that checkout was not examined.
- Not every upstream fix for this SoC that the fork carries is in ACK 6.18.32. ACK's `msm8953.dtsi:1437-1494` still has the nested `qcom,dwc3` + `snps,dwc3` USB layout (`usb3: usb@70f8800` at 1437, `usb3_dwc3: usb@7000000` at 1479, `usb-role-switch` at 1494), so `337fdd8c315c` (msm8953 flatten USB node) is **absent**. The fork's 6.18 line has the flattened `qcom,snps-dwc3` node at `msm8953.dtsi:2251-2252`. ACK's `qcom_scm.c:2399-2418` (irq requested at 2399 before `smp_store_release(&__scm, scm)` at 2418) and its `usb-role-switch` property fit `7ab36b51c6be` and `0b66b41b05fb`, both of which exist in the fork. But `../ack-android17-6.18` is a depth-1 clone, so none of the three hashes is verifiable there: `git cat-file -t` fails for all three in ACK and succeeds for all three in the fork.

## 4. Port state (built and measured)

- `scripts/tissot-ack.config` — device fragment merged over `gki_defconfig` via `scripts/kconfig/merge_config.sh -m`; `scripts/build-ack-tissot.sh` builds it and produces `Image.gz-dtb` by `cat Image.gz <dtb>` (the stock ROM's own layout — see §6).
- `scripts/ack-driver-audit.py` walks the built dtb with `fdtget`, searches compatible strings in C source, and attempts to resolve each source file to a CONFIG symbol through Makefiles. The regex does not restrict matches to actual driver match tables, and the symbol resolver does not prove that the object was linked. Its `enabled_symbols()` counts both `=y` and `=m` as enabled. These are static candidates, not evidence of built-in drivers, runtime binding, or successful probing. See [audit implementation](../scripts/ack-driver-audit.py).
- Historical audit output with the fragment: **100 device nodes, 97 static source matches, 65 matches classified as enabled**. The tool labelled the latter "compiled in", although modules count too. Reproduced by regenerating the config (`gki_defconfig` + `merge_config.sh -m` + `olddefconfig`) and re-running the audit against the built dtb. The bare-`gki_defconfig` baseline was re-measured at **6** enabled matches, not the 7 previously reported, and lacks the identified eMMC/SPMI/regulator configurations. Note that the ACK checkout's current `out/.config` is the bisect-B config (`CONFIG_REMOTEPROC`, `CONFIG_QCOM_RPMH` unset) and audits to 6, so the 65 figure holds only for the regenerated fragment config. Neither result establishes complete board support.
- The 3 reported unmatched nodes were `qcom,rpm-msg-ram` and two TCSR nodes with `syscon` fallback. The RPM node describes an SRAM region. Both are tool artefacts: in the checked ACK tree `drivers/of/syscon.c` does not exist, `drivers/mfd/syscon.c` does, and that file reaches syscon nodes through `of_device_is_compatible()` and `syscon_regmap_lookup_by_compatible()` — neither of which an `of_match` table scan can see. The pinned Android 5.15 donor also already has `drivers/mfd/syscon.c` (§11), so the move predates 5.15.
- The board leaves major functional blocks disabled, including display, GPU, WCNSS, and LPASS. The enabled board peripherals include gpio-keys, regulators, MAX98927, AW2013, touch, WLED, storage, serial, and USB. This describes DT configuration, not proof that every enabled block works or that all other gaps are confined to disabled nodes. See [ACK board source][ack-board].
- Note for Android specifically: upstream DRM/DPU is **not** what would drive this phone's screen. CAF drives the panel via `techpack/display` + vendor dtsi under `arch/arm64/boot/dts/vendor/qcom/mi8953/` (`common/panel/dsi-panel-ili7807-fhd-video.dtsi`, `common/panel/dsi-panel-ft8716-fhd-video.dtsi`, and tissot's own `tissot/panel/dsi-panel-otm1911-fhd-video.dtsi`), and Android's HWComposer is a prebuilt blob bound to KGSL. So the display/GPU work is a CAF port, not a mainline one.
- The reviewed ACK checkout has one uncommitted DTS change removing `ramoops@9ff00000` (see §6.2), but the saved images do not all contain that change. Appended DTBs in `boot-ack-6.18.img`, `boot-ack-6.18-console.img`, and `boot-ack-ffs.img` **retain** the node. `boot-ack-probe.img`, `boot-ack-v2.img`, `boot-ack-v3.img`, `boot-ack-v4.img`, `boot-ack-bisect.img`, and `boot-ack-bisect-b.img` omit it. Comparisons must use each image's embedded config and DTB, not the current checkout or `out/.config`.

## 5. Boot attempts: what was measured

Method: `fastboot boot <image>` (ephemeral — writes no partition, active slot unchanged), then measure the time until the phone returns to adb on the CAF slot.

| # | Image | Result |
|---|---|---|
| 1 | ACK + tissot config | splash, then stall; returns after ~215 s |
| 2 | + `CONFIG_USB_FUNCTIONFS=y` (legacy gadget; configfs FunctionFS was already enabled) | no adb or phone in `lsusb`; ~215 s. This does not locate the stall or prove that userspace was never reached. |
| 3 | `init=/nonexistent_init_zzz` probe | no panic/reboot in 10 s. **Inconclusive**: the kernel tries ramdisk `/init` first. A missing `rdinit=` path can also divert execution into root mounting before `init=` is tried; a revised probe must account for this. |
| 4 | + `clk_ignore_unused pd_ignore_undefined regulators_ignore_undefined` | unchanged, ~215 s. Only the clock parameter is recognised; the power-domain and regulator spellings are invalid. |
| 5 | + RPM clock/regulator/RPMPD/Q6V5/WCNSS/SPMI-PMIC **disabled** (bisect A) | unchanged, ~210 s. `CONFIG_QCOM_SCM=y` remains in the saved image. RPM/SCM involvement is **not excluded** by the unchanged return time. |
| 6 | + `CONFIG_REMOTEPROC`, `QCOM_RPMPD`, `QCOM_SCM`, `QCOM_RPMH` disabled (bisect B) | built (`../ack-boot-test/boot-ack-bisect-b.img`); result not recorded |

Saved-image check: the original `boot-ack-6.18.img` already embeds `CONFIG_USB_CONFIGFS_F_FS=y` and `CONFIG_USB_F_FS=y`. ACK's [USB gadget Kconfig][ack-usb] makes the former select the latter; `CONFIG_USB_FUNCTIONFS` instead selects the legacy `g_ffs` gadget in [legacy Kconfig][ack-usb-legacy]. Missing that legacy option did not mean FunctionFS support was absent. Recognised power parameters are `pd_ignore_unused` and `regulator_ignore_unused`, as defined in [power-domain core][ack-pd] and [regulator core][ack-regulator]. The saved `boot-ack-v4.img` also includes unrecognised `pd_ignore_forced`. These are corrections for future probes, not tests already performed. Init ordering and the missing-`rdinit` root-mount path are in [init/main.c][ack-init].

**Hypothesis, unverified:** the reported ~200 s return interval could include an unserviced hardware-watchdog reset. It measures time until CAF adb returns, not the reset instant. CAF's source defconfig enables `CONFIG_QCOM_WATCHDOG_V2=y` (`arch/arm64/configs/vendor/msm8953-perf_defconfig:574`), with a separate driver in `drivers/soc/qcom/watchdog_v2.c`. The reviewed ACK config has `CONFIG_QCOM_WDT` unset, and its MSM8953 DTS has no watchdog node. This does not establish the watchdog's boot-time hardware state, firmware ownership, or reset cause. The earlier attribution to ABL leaving it armed remains unverified. Identical return times can occur with different failure paths and do not prove where, or whether, the kernel stalls.

## 6. Log-channel observations and corrected interpretations

These cost most of the session and are the most reusable part:

1. **No pstore records were recovered after the reported CAF panic test.** The session used root and `echo 1 > /proc/sys/kernel/sysrq; echo c > /proc/sysrq-trigger`; after reboot, `/sys/fs/pstore/` was reportedly empty. **Superseded by §12:** that test's ramoops is at `0x91400000`, which is Venus memory on this SoC, so it could not have recorded anything regardless of whether DRAM survives. Firmware reinitialisation remains an untested hypothesis.
2. **`0x9ff00000` lies outside the reported CAF System RAM ranges.** Recorded `/proc/iomem`: `10000000-849fffff`, `86800000-86bfffff`, `8ef00000-9fefffff`, `a0000000-ffffffff`. [ACK's board DTS][ack-board] places ramoops at `0x9ff00000`. The session reported immediate device failure while mapping or reading that address, including a 512-byte read. These observations make it an unsuitable region for the tested reader, but the map alone does not prove absence of physical DRAM, and a CPU abort was not verified from a captured exception log.
3. **`0x91400000` (CAF's ramoops base) is already reserved for Venus** in ACK's dtb (`venus@91400000`, 7 MB) — do not point ramoops there.
4. **debugfs cannot be used unprivileged**: a debugfs mount is 0700, so even a `0444` file under it is unreachable; moving to sysfs fixes traversal, but **SELinux still denies it** — `adb shell` (uid 2000, `u:r:shell:s0`) gets `Permission denied` on `/sys/kernel/tissot/tissot_pstore`. Root is required.
5. **Flashing any custom boot image drops Magisk** (Magisk lives in the boot image). This is why an unprivileged design is preferable, and why root must be re-established after every kernel flash. Headless re-patch works: extract `assets/boot_patch.sh`, `assets/util_functions.sh`, `lib/arm64-v8a/lib{magiskboot,magiskinit,magisk,init-ld,busybox}.so` and `assets/stub.apk` from the APK, rename to `magiskboot`/`magiskinit`/`magisk`/`init-ld`, then `KEEPVERITY=1 KEEPFORCEENCRYPT=1 bash boot_patch.sh <boot.img>`. This produced a working patched image without touching the phone UI. After reboot, `su` is at `/debug_ramdisk/su` and may need `export PATH=/debug_ramdisk:$PATH`.
6. **`ro.debuggable=1` in the ramdisk's `prop.default` does not work**: `/system/build.prop` sets `ro.debuggable=0`, `ro.secure=1`, `ro.adb.secure=1`, and the property service keeps the later value.
7. **The reported pstore block test recovered no writes; configuration defects precede any ordering diagnosis.** The session reported unchanged `logdump` contents containing an existing ext filesystem. Saved `boot-ack-v3.img` embeds `CONFIG_PSTORE_BLK=y`, `CONFIG_PSTORE_BLK_KMSG_SIZE=131072`, and header cmdline `pstore_blk.blkdev=/dev/block/by-name/logdump pstore_blk.best_effort=1 pstore_blk.pmsg_size=32768`. Best-effort mode was enabled in this image; it was omitted from the earlier report. Both saved logdump dumps are 67,108,864 bytes (64 MiB).

   [Pstore Kconfig][ack-pstore-config] defines these sizes in KiB: the kmsg record is **128 MiB**, and the pmsg reservation is **32 MiB**. The kmsg record cannot fit the 64 MiB device even before subtracting the other reservations; [zone allocation][ack-pstore-zone] rejects a device with no room for one record. If 128 KiB was intended, the value is `128`, not `131072`.

   The built-in [pstore block backend][ack-pstore-blk] calls `early_lookup_bdev()` at a late initcall, before Android creates its by-name symlinks. [Early block lookup][ack-block-lookup] supports `PARTLABEL=logdump`, `PARTUUID=...`, or a kernel block-device name; `/dev/block/by-name/logdump` is not resolved as an Android symlink there. Registration could still fail if storage is not ready, but the saved path and sizes already prevent a valid test. Using a supported identifier and corrected sizes has **not** been tested here.

   Best-effort mode supplies ordinary read/write operations and **no `panic_write` callback**. The zone backend selects `panic_write` during panic and leaves data dirty when it is absent. Fixing registration alone therefore does not provide reliable panic persistence. A hardware reset without a kernel dump also does not guarantee a final kmsg write.

## 7. Environment facts worth keeping

- `fastboot fetch` is unsupported here (`Unable to get max-fetch-size`) — the live `boot_a` was pulled over rooted adb with `dd`. The existing backup `tissot_backup_20261003/img/boot_a.img` is **stale** (`…-g9d3bf7da9553-dirty`, Sep 30), not the kernel that was running.
- `fastboot flash vendor_b <vendor_a.img>` fails with `size too large`: the backup is 629,146,112 B but the partition is 629,145,600 B. Truncate first.
- **A/B retry exhaustion and fallback are bootloader responsibilities.** Android userspace marks a boot successful; the bootloader tracks retry counts and selects another eligible slot when retries are exhausted. The reported failure to recover on this phone does not establish that fallback requires `init`; its actual slot flags, retry counters, and bootloader behavior were not captured. See [AOSP bootloader requirements][aosp-ab].
- `fastboot set_active b` was run before checking that slot `b` held a ROM, which made the phone unbootable until `boot_b` was flashed with Evox `boot.img` + `system.img`. Slot `b` now boots the stock Evox ROM (with a stale `vendor_b`).
- This tree's `dtc` rejects DTS **labels** containing dashes (`ack-pstore-mem:` fails to parse); node names may contain them.
- `make O=out …` needs `ld.lld` on PATH in the same command, or Kconfig fails with `linker 'ld.lld' not found`. Single-dtb targets need the directory: `make … qcom/msm8953-xiaomi-tissot.dtb`.
- The checked ACK revision has no arm64 `Image.gz-dtb` target. Its [boot Makefile][ack-boot-makefile] provides `Image`, `Image.gz`, other compressed Image targets, and `image.fit`; this port's packaging script appends its DTB. CAF 4.19 does this via `CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE` (`arch/arm64/boot/Makefile`: `cat Image.gz $(DTB_OBJS) > Image.gz-dtb`), matching the stock layout reported in the original session. This observation does not establish the targets in every 6.x tree.

## 8. Last recorded device state (not rechecked during review)

- Slot `a`: original CAF 4.19 MGLRU kernel (`…-mglru-next-g7f57b3823629`) + working ROM, Magisk patched. Root available via `/debug_ramdisk/su`.
- Slot `b`: Evox stock `boot.img` + `system.img`, stale `vendor_b`; boots.
- ACK 6.18 is never flashed; it is only ever `fastboot boot`-ed.
- Backups: `ack-boot-test/boot_a-live.img` (original `boot_a`), `ack-boot-test/boot-ack-*.img`, and the untouched `tissot_backup_20261003/img/`.

## 9. Open questions for review

1. **Does ACK reach userspace, and where does boot fail?** The init probe was inconclusive; missing USB is also compatible with userspace or gadget-configuration failure. Bisect A did not exclude RPM/SCM, and bisect B has no recorded result. First-stage init, SCM firmware interaction, interconnect/`rpmsg`, and early kernel startup remain hypotheses without a captured log. Pstore registration defects explain missing logs but have not been shown to cause the boot failure.
2. Can a reliable observation channel be established without UART? Correct the pstore sizes and early device identifier before testing registration, and distinguish ordinary console persistence from panic-write support (§6.7). A minimal ramdisk with a positive userspace marker is another possible probe. Framebuffer-console and USB-network approaches remain untested ideas with display/gadget prerequisites.
3. **Does a validated ramoops buffer survive the actual reset path?** Check registration, a usable non-overlapping address, matching layouts, record creation, and possible userspace removal before attributing empty pstore to firmware DDR initialisation. Firmware identity and warm-reset behavior remain unverified. UART remains an option, but neither RAM persistence failure nor a particular firmware mechanism is established.
4. Is ACK the right base at all, versus CAF 5.15 (which has KGSL in a separate repo but is closer to the 4.19 driver's world) — given the ROM's blobs are CAF 4.19-era?

## 10. Where everything lives

| What | Path |
|---|---|
| This repo, branch `project-mainline` | `/home/kurision/development/kernel/kernel_xiaomi_msm8953` |
| Research doc (living) | `docs/project-mainline.md` |
| This report | `docs/ack-6.18-boot-investigation.md` |
| Handoff | `docs/handoff-ack-mainline.md` |
| ACK base tree (**current**) | `../ack-android16-6.12` (branch `android16-6.12`, head `3a7d1771d492`, 6.12.93; one local DTS change adding `ramoops@86800000`, see §12) |
| ACK base tree (previous) | `../ack-android17-6.18` (branch `android17-6.18`, head `89b3cc162`) |
| msm8953 fork, 6.12 line (current) | `../msm8953-linux-6.12` (branch `6.12/main`, head `d9eabbae3ede`) |
| msm8953 fork, 6.18 line | `../msm8953-linux-6.18` (branch `barni2000/6.18/develop`) |
| ROM images | `../evox_images/{boot.img,system.img}` |
| Boot images and dumps | `../ack-boot-test/` |

## 11. Review provenance and limitations

- **ACK baseline:** Google Android kernel common, branch `android17-6.18`, pinned checked revision `89b3cc162c81c59edf4a48f784725849effed283`. Pstore, USB Kconfig, and power-domain/regulator behavior were checked against files fetched from Gitiles at this commit using `?format=TEXT` and base64-decoded before reading. Linked board/init/build sources identify the same revision; the local board removal is an adaptation, not part of that baseline.
- **Ported-work donor:** Google Android kernel common, branch `android14-5.15`, pinned revision `76efa001ea197723c0423fdb9136e83b483f7aa1`. Decoded `fs/pstore/ram_core.c` confirms saving valid previous contents; decoded `drivers/mfd/syscon.c` confirms that location already exists in the donor. This is not a substitute for a matching 4.19 comparison.
- **4.19 baseline unavailable:** the requested `android13-4.19-*` branch family was absent from the reviewed kernel/common remote-ref listing. No alternative baseline was silently substituted. Conclusions requiring that comparison remain unverified; local CAF source describes this checkout only.
- **Saved artifacts:** image checks read Android boot-header cmdlines, decompress the kernel to recover the `IKCFG_ST`/`IKCFG_ED` embedded config, and inspect appended DTBs. They cover the nine named `../ack-boot-test/boot-ack-*.img` files in §4. Sizes were checked with `stat -c '%n %s bytes'` on `../ack-boot-test/logdump-ack.bin` and `../tissot_backup_20261003/img/logdump.img`. File content comparisons and device timings from the original session were not rerun.
- **Audit source:** `scripts/ack-driver-audit.py:of_matches()`, `symbol_table()`, and `enabled_symbols()` were inspected. Historical totals were retained as tool output, not rerun against the now-different config and presented as runtime coverage.
- This review ran no kernel build, flash, boot attempt, panic test, or live device query. It does not establish the kernel's failure location or reset cause.

## 12. Later session, 2026-10-04: root cause found, base retargeted to 6.12

Everything above records the 6.18 investigation. This section supersedes parts of
it. One earlier conclusion was wrong and is corrected here.

### The 6.18 stall: the kernel had no Qualcomm clock or pin control at all

Decoding the `IKCFG_ST`/`IKCFG_ED` embedded config out of the images that were
actually booted shows a defect no amount of reading the fragment would have found:

| Image | `COMMON_CLK_QCOM` | `MSM_GCC_8953` | `PINCTRL_MSM8953` |
|---|---|---|---|
| `boot-ack-6.18.img` | not set | absent | absent |
| `boot-ack-v4.img` | not set | absent | absent |
| `boot-ack-bisect-b.img` | not set | absent | absent |
| `boot_a-live.img` (CAF, works) | n/a | n/a | `=y` |

Both are `menuconfig` gates that wrap an entire Kconfig file: `COMMON_CLK_QCOM`
(`drivers/clk/qcom/Kconfig:10`, `if` at line 20 through `endif` at 1290) and
`PINCTRL_MSM` (`drivers/pinctrl/qcom/Kconfig.msm:2`). `scripts/tissot-ack.config`
requested `MSM_GCC_8953` and `PINCTRL_MSM8953` explicitly; `olddefconfig`
discarded both without emitting a warning. Every one of the six boot attempts
tested a kernel with no Global Clock Controller and no pin control. This is a far
better stall candidate than anything in §5 or §9, and it is invisible unless you
read the built kernel's own config rather than the fragment.

### Correction: the `androidboot.boot_devices` value

The name must match how the running kernel names the platform device. CAF's DTS
uses `soc/7824900.sdhci`. Upstream builds it in `of_device_make_bus_id()`
(`drivers/of/device.c:288`) as `%llx.%pOFn`, and `%pOFn` prints the node name
with the unit address stripped (`lib/vsprintf.c`, `device_node_string()`,
`case 'n'`), so `mmc@7824900` becomes **`7824900.mmc`**. Not `soc@0/mmc@7824900`.
With the CAF string, `info.is_boot_device` never matches in
`system/core/init/devices.cpp:226`, the `by-name` symlink is never created
(same file, lines 512-528), and `/dev/block/by-name/system` does not exist.
This is identical on 6.12, so retargeting the base does not avoid it.

### Correction: "DRAM does not survive the reset" was never established

§6.1 concluded from an empty `/sys/fs/pstore` that ABL re-initialises DDR. That
test used this repo's CAF DTS, whose ramoops sits at **`0x91400000`
(`arch/arm64/boot/dts/vendor/qcom/mi8953/tissot/android.dtsi:25`) — which is
Venus memory** on this SoC (`venus@91400000`, 7 MB). The pstore backend was
writing into the GPU buffer, so the test could not have produced a record
regardless of whether RAM survives. The conclusion does not follow.

### Log channels actually available

- **USB gadget serial cannot report a stall.** `USB_CONFIGFS_ACM`/`_SERIAL` are
  enabled, but Android's ueventd builds the gadget in configfs, and that is
  userspace. Measured during a stall: the phone does not appear in `lsusb` at
  all, no `/dev/ttyACM*` appears, and the host `cdc_acm` module is not loaded.
- **Modules are unreachable.** The ROM ships zero modules and has no
  `/lib/modules`; `insmod` needs adb, which needs init.
- **`drivers/usb/early/` is not applicable.** It is `ehci-dbgp.c` and
  `xhci-dbc.c`, host-side debug cables; this phone is a USB device.
- **Physical UART is the only live channel** and needs a 3.3V USB-TTL adapter.
  The port is GENI serial, so the console is `ttyMSM0`, not `ttyHSL0`; there is
  no `SERIAL_MSM_HSL` symbol in 6.12 at all.
- **pstore/blk to `logdump` was built and failed.** `boot-ack-612.img` carried
  `pstore_blk.blkdev=PARTLABEL=logdump` and `pstore_blk.best_effort=1` with
  `CONFIG_PSTORE_BLK=y`, `PSTORE_ZONE=y`, `PSTORE_CONSOLE=y`. After a 230 s stall
  the partition was **byte-identical** to the previous dump
  (`md5 70ad292958d1439be7d1bb7e7eed2952`), so nothing was written. Likely
  cause: `pstore_blk_init` is a `late_initcall` (`fs/pstore/blk.c:346`) and MMC
  card enumeration lands after it, so the device is not openable yet. This is
  inferred, not measured.

### Measured device behaviour of the 6.12 build

- `fastboot boot ../ack-boot-test/boot-ack-612.img` returns `OKAY`, the device
  leaves fastboot, and the panel lights dimly (display, GPU and panel are not
  enabled in this config).
- adb returns to the CAF slot after **230 s**; the earlier 6.18 attempts returned
  after ~215 s. Same failure class, no improvement.

- **Historical hypothesis: RAM was erased on reset. Not established.** The
  matching-address CAF reader returned empty pstore, but that did not establish
  that ACK had registered and populated ramoops in that particular run, nor
  exclude reader-side loss or removal. The successful 2026-10-05 capture (§13)
  now proves ramoops registration in `diag4`, not persistence across resets.

- **Historical inference: ACK never reached `late_initcall`. Superseded.** The
  invalid-init probe did not reset, but lack of reset did not prove that init
  was never reached. The 2026-10-05 `diag4` log (§13) directly records execution
  of `/init` and successful eMMC access.

- **The ~200 s reset story needs revising.** Two runs reset and returned to adb
  (180 s, 230 s); a third on the *same kernel image* hung ~13 minutes without
  resetting, differing only in the command line. The likeliest reading is that
  enabling `COMMON_CLK_QCOM` and `PINCTRL_MSM` let the kernel service a watchdog it
  previously could not, so it hangs instead of being reset — meaning the watchdog
  was never the cause of the stall and §5's hypothesis was backwards.

  Not confirmed. A faulty USB cable found during this session made at least one
  reset unobservable, so timing conclusions here are weak. The A/B retry-exhaustion
  alternative was checked and **disproven**: `slot-unbootable:a` and
  `slot-unbootable:b` are both `No`, and this ABL does not implement
  `getvar retry-count`.

### Base retargeted to `android16-6.12`

`android17-6.18` does ship point releases (`-2026-04`, `-2026-06`, `-2026-09`),
 so "no phone ships 6.18" is not accurate; 6.12 is simply the more settled line,
 carrying point releases through `2026-09` plus `android16-6.12-lts`. One concrete
  argument for it: `qcom_scm.c` in 6.12 already publishes `__scm` before
  requesting the waitqueue irq (`android16-6.12:2004-2006`), which is the fix the
  6.18 tree still lacks (6.18 requests the irq at `:2399` before publishing at
  `:2418`).

| Tree | Path | Head |
|---|---|---|
| ACK 6.12 | `../ack-android16-6.12` | `3a7d1771d492`, 6.12.93 |
| msm8953 fork, 6.12 line | `../msm8953-linux-6.12` | `d9eabbae3ede`, branch `6.12/main` |

The fork's 6.12 branch carries `qcom-spmi-haptics.c` but **zero** commits matching
`tissot` in the subject, unlike the 6.18 line.

## 13. 2026-10-05: successful ACK 6.12 log capture

**Known-good observation channel: diagnostic initramfs → eMMC `logdump`.**
This is a measured kernel/userspace boot, not an Android boot. Keep this image
and both dump artifacts as the reference; the diagnostic source may evolve.

### Reusable reference artifacts

Paths are relative to this repository:

| Artifact | Path | Bytes |
|---|---|---:|
| Successful temporary boot image | `../ack-boot-test/boot-ack-diag4.img` | 34,324,480 |
| Raw read of the complete logdump partition | `../ack-boot-test/ack-diag4-logdump.bin` | 67,108,864 |
| Clean capture, ending at its EOF marker | `../ack-boot-test/ack-diag4-logdump.log` | 24,713 |

SHA-256:

```text
ffee7154d9003b9825d7a8c4e3d0d1d5d4332f924d468067eedc76c591a34da2  boot-ack-diag4.img
658288b8b46fe4b507dc1ee03a13688b3050b9e988fa8304a67320b8b346af16  ack-diag4-logdump.bin
806af708b60bc050ea9354cd7172cda0b27187e6d62c784a37b4a5e02b0afde5  ack-diag4-logdump.log
```

Kernel: `6.12.93-4k-g3a7d1771d492-dirty`, local branch `android16-6.12`,
HEAD `3a7d1771d4925a56f7eeb8a5ba1faff0c544a9ef`. The tree has local
adaptations; the image and captured log, not HEAD alone, identify the tested
build. Diagnostic code is local, not a port from the pinned 5.15 donor.

### What made capture work

- A static `/init` mounts devtmpfs, proc and sysfs.
- It discovers the partition by exact `PARTNAME=logdump` in block-device
  uevents and opens its devtmpfs path. On this device the postmarketOS reader
  confirmed `DEVNAME=mmcblk0p48`, `PARTNAME=logdump`, size 64 MiB.
- It writes `/dev/kmsg` records from offset zero, captures for 45 seconds,
  appends an EOF marker and calls `fsync()`. It then loops indefinitely.
- `pstore_blk.*` activation parameters were omitted so the pstore block backend
  would not compete with this direct writer.
- The earlier `/dev/block/mmcblk0p48` lookup was wrong for this standalone
  devtmpfs initramfs. Failed lookup was not evidence of failed MMC probing.
- USB fallback was not exercised by this successful storage capture. Absence
  from host `lsusb` at 70 seconds does not negate the storage result.

API checks used the local `android16-6.12` revision above:
`block/partitions/core.c` emits `PARTNAME`; `Documentation/usb/gadget_configfs.rst`
identifies UDCs through `/sys/class/udc`; `Documentation/usb/gadget_serial.rst`
identifies gadget-side serial as `/dev/ttyGS0`, not host-side `/dev/ttyACM0`.

### Measured milestones and corrections

The clean log contains 304 kernel-record headers, begins with
`DIAG: init running; kernel log follows`, and ends with
`DIAG: EOF kmsg dump complete`.

| Kernel time | Captured event |
|---:|---|
| 0.396 s | ramoops registered at `0x86800000`, size `0x100000` |
| 4.684 s | SDHCI host at `7824900.mmc` registered |
| 4.844 s | eMMC detected in HS400 mode |
| 4.869 s | All 51 eMMC partitions enumerated |
| 4.877 s | SD card detected in SDR104 mode |
| 20.197 s | Touchscreen probe failed with `-110` |
| 20.292 s | `Run /init as init process` |

This supersedes earlier claims that eMMC never registered or that the kernel
never reached init. It does not establish Android compatibility: `diag4`
replaced Android's initramfs with the diagnostic program.

Warnings retained for investigation, not suppressed:

- Kernel-image misalignment warning: present in ACK, absent from the saved
  postmarketOS log. The tested ACK run still reached userspace; later harm is
  unverified. In this ACK revision, `arch/arm64/kernel/setup.c` emits it when
  `_text` is not aligned to `MIN_KIMG_ALIGN`.
- PSCI PC-mode failure `-1`: present in both ACK and the working postmarketOS
  boot, so this message alone does not explain Android boot failure.
- KVM unavailable: this boot cannot honor `kvm-arm.mode=protected`; no evidence
  here establishes that lack of KVM blocks ordinary Android startup.
- Touchscreen `-110`: a real probe timeout; startup continues afterward.

### Next experiment: Android first-stage capture

Prepared image: `../ack-boot-test/boot-ack-android-capture.img` (34,324,480
bytes), SHA-256
`e099b36ddfcb551a562062e4acac1c0de396f318b0fcae1abbd226c5a6274f8f`.

This preserves the tested kernel/DTB and all original Android ramdisk entries
except `/init`. That symlink is replaced with the static wrapper built from
`scripts/initramfs-diag/init.c` using `-DANDROID_CAPTURE`; the original
`/system/bin/init` ELF and fstab are preserved byte-for-byte.

The wrapper starts a recorder child in a private mount namespace, opens
`logdump`, flushes its readiness marker, and execs the original Android init
as PID 1. The child records for 180 monotonic seconds and flushes each record,
so a reboot can leave a useful prefix without an EOF marker. This mode never
configures USB. Mount isolation does not isolate global SELinux policy;
on-device capture through Android policy loading remains unverified.

Expected capture markers are `DIAG: Android capture ready`,
`DIAG: Android init exec succeeded`, and
`DIAG: EOF Android kmsg dump complete`; exec failure or recorder failure has
separate markers. A partial log without EOF must not be classified as empty.

Both init modes compiled warning-free. Host smokes exercised nonblocking
backpressure, durable record copying and error propagation. A native PID
namespace/chroot smoke exercised the recorder-failure fallback: the target
executable retained PID 1 and argv, the parent's `/dev` stayed unchanged, and
recorder descriptors did not leak across exec. Full recorder startup in the
phone's initial privileged namespace still requires the next device boot.

### Recovery and readback

1. Temporarily boot the preserved image; do not flash it:

   ```sh
   fastboot boot ../ack-boot-test/boot-ack-diag4.img
   ```

2. Allow 120 seconds from the accepted boot command. The image does not
   automatically reboot after capture; manually power-cycle into the working
   postmarketOS system.
3. SSH to `user@172.16.42.1`. Reconfirm partition identity before reading:

   ```sh
   cat /sys/class/block/mmcblk0p48/uevent
   ```

4. Read, without writing the partition:

   ```sh
   doas dd if=/dev/mmcblk0p48 of=/tmp/ack-logdump.bin bs=1M count=64
   doas chmod 644 /tmp/ack-logdump.bin
   ```

5. Pull the file over SSH/SCP and extract through the diagnostic EOF marker.
   Do not interpret bytes after the marker: older partition contents remain.

For this run, postmarketOS `7.0.9-msm8953` was the reader and its pstore
directory was empty. That is not proof of RAM persistence failure.
Reusing `logdump` overwrites the preceding capture on the device; preserve
local reference files before another experiment.

## 14. 2026-10-05: heartbeat and USB-serial isolation probe

Prepared `../ack-boot-test/boot-ack-heartbeat.img`, SHA-256
`a3fc547954ad29e62bd82c71ea07ccedc59ab395dde99c85e87c018425b34065`.
Its kernel and appended DTB are byte-identical to
`boot-ack-android-platform-capture.img`; only the ramdisk and boot-header
metadata/command line change. No kernel build or partition flashing.

- PID 1 is `scripts/initramfs-diag/heartbeat-init.sh`, interpreted by static
  upstream BusyBox 1.31.0 ARMv8l. ACK's built config has `CONFIG_COMPAT=y`.
  BusyBox source binary:
  `https://busybox.net/downloads/binaries/1.31.0-defconfig-multiarch-musl/busybox-armv8l`;
  SHA-256 `141adb1b625a6f44c4b114f76b4387b4ea4f7ab802b88eb40e0d2f6adcccb1c3`.
- Heartbeats start after the initial mounts, not at kernel time zero.
  After 40 seconds PID 1 tries both eMMC/SD p25 names with `ro,noload`,
  then loads `/mnt/system/vendor/etc/selinux/precompiled_sepolicy`.
- `load-policy.c` submits the complete policy in one write and distinguishes
  successful loading from errors. Ordinary chunked `cat` is not a valid
  substitute: ACK `security/selinux/selinuxfs.c:549-593` parses each write
  as a whole policy. This probe does not launch Android or enable enforcement.
  Enforcement is reported before and after the load.
- `init.c`, compiled with `HEARTBEAT_RECORDER`, records `/dev/kmsg` to the
  partition identified by `PARTNAME=logdump` for 300 seconds, with per-chunk
  `fsync`. A new run overwrites the preceding on-device capture.
- Independent `recorder --usb-setup` starts the existing CDC-ACM gadget even
  when storage is available. A reconnectable BusyBox shell uses `/dev/ttyGS0`;
  USB setup does not gate heartbeats, policy loading or storage recording.
  This is USB serial, not ADB, and exposes an unauthenticated root shell
  during the temporary diagnostic boot only.
- Command-line additions: `rcupdate.rcu_cpu_stall_timeout=10`,
  `softlockup_panic=1`, `hung_task_panic=1`, `printk.devkmsg=on`.
  The existing `panic=10` is retained. RCU timeout alone warns; it does not
  request an RCU-triggered panic. `cpuidle.off=1` and `maxcpus=1` remain
  separate follow-on bisects, not enabled in the baseline probe.

Measured pre-boot checks: both native helpers compile warning-free and are
statically linked; actual BusyBox shell syntax, timed heartbeat commands
and an isolated controlling-terminal interactive shell run in OrangeFox.
Loader usage/missing-file/nonregular-file errors return failure. No recovery
policy was loaded. The temporary boot was accepted and the ACK diagnostic
gadget enumerated as `18d1:9008`, product `ACK kernel log`, with host
`/dev/ttyACM0`. After the user granted temporary per-device access,
the actual USB serial shell returned uptime, enforcement state and the
process list. At 607.06 seconds it remained responsive; enforcement was 0
when sampled at 251.87 seconds. Manual policy loading returned successfully
at 69.081 seconds, and heartbeats continued through 421.606 seconds in the
retrieved live log. This does not exercise Android's enforcement transition.

Preserved evidence in `../ack-boot-test/`:
- `ack-heartbeat-usb-dmesg.log`: clean live boot log, 732 lines through
  421.606 seconds.
- `ack-heartbeat-logdump.log`: 41,486-byte durable capture through
  323.619 seconds, ending in `DIAG: EOF kmsg dump complete`.
- `ack-heartbeat-logdump-prefix.bin`: 192 KiB raw partition prefix,
  not a full partition dump.
- `ack-heartbeat-usb-state.log`: serial uptime, enforcement and process list.

The installed `/mnt/system/bin/secilc --help` also executes under ACK using
its bootstrap linker and libraries (it aborted on `MADV_WIPEONFORK` under
OrangeFox's 4.9 kernel). Compilation of a modified policy remains untested.
The captured AVCs deny the recorder's kmsg read and raw-partition write,
plus the probe's shell execution and serial ioctl; all report `permissive=1`.
Blindly enabling enforcement on this probe would therefore invalidate the
observer, not isolate an Android failure.

The host device is `root:uucp`, mode 0660. Temporary access was granted with
`sudo setfacl -m "u:$(id -un):rw" /dev/ttyACM0`; remove it afterward or
disconnect the device. No permanent udev/group configuration was changed.

Temporary boot:

```sh
fastboot boot ../ack-boot-test/boot-ack-heartbeat.img
```

Allow at least three minutes before manually resetting a hang. A heartbeat
counter is not an exact wall-clock measurement and stopping heartbeats does
not by itself identify which CPU or subsystem stopped. A successful load
with continuing heartbeats establishes this isolated path remains schedulable;
it does not prove Android's later enforcement/second-stage path is healthy.

### Working USB serial setup and host procedure

This was exercised on the ACK heartbeat probe, not just inferred from a
successful fastboot command. No USB driver, kernel or DTB change was needed.

1. The diagnostic ramdisk contains static BusyBox, the recorder and
   `heartbeat-init.sh` as `/init`. The script starts storage recording and
   `recorder --usb-setup` independently; USB is no longer only a fallback
   after storage failure.
2. The recorder mounts configfs at `/sys/kernel/config`. Its existing
   `setup_gadget()` creates `/sys/kernel/config/usb_gadget/g1`,
   `functions/acm.gs0` and `configs/c.1`, links the function into the
   configuration, sets vendor/product IDs `18d1:9008` and product
   `ACK kernel log`, then writes an actual `/sys/class/udc` controller name
   into `g1/UDC`. The native recorder was compiled statically with
   `-DHEARTBEAT_RECORDER`; the Android init was not running in this test.
3. Once `/dev/ttyGS0` exists, a background loop launches
   `/bin/busybox setsid -c /bin/busybox sh -i`, with stdin/stdout/stderr
   connected to that device, and restarts the shell after exit.
   Heartbeats and policy loading do not wait for this shell.
4. Temporarily boot `boot-ack-heartbeat.img` as shown above. On the host,
   `udevadm monitor --udev --subsystem-match=tty` observed the addition of
   `ttyACM0`; `lsusb -d 18d1:9008` identified `ACK kernel log`.
   The already-installed CDC-ACM driver bound without installing a package.
5. The host node was `root:uucp`, mode 0660. Ordinary access failed and
   `sudo -n` required authentication. The user ran this in their terminal:

   ```sh
   sudo setfacl -m "u:$(id -un):rw" /dev/ttyACM0
   ```

6. The actual host receiver used Python's standard library, not ADB:
   `os.open()` with `O_RDWR | O_NOCTTY | O_NONBLOCK`, termios raw input/output,
   115200 baud, 8 data bits, no parity, one stop bit, and `CRTSCTS` disabled.
   `selectors.DefaultSelector` waited for readable data; writes sent
   newline-terminated shell commands. A serial terminal with equivalent
   settings can also be used.
   After reopening the port during this session, the host also explicitly
   asserted DTR and RTS with
   `fcntl.ioctl(fd, termios.TIOCMBIS,
   struct.pack('I', termios.TIOCM_DTR | termios.TIOCM_RTS))`.
   Commands then returned again; the uptime query reported `1333.29`.
   If enumeration succeeds but the shell is silent, check those modem lines.
   Use only one host reader at a time. A later `fuser -v /dev/ttyACM0`
   showed both the Python receiver and `tio`; replies became partial because
   the readers consumed the same input stream. The Python descriptors were
   closed, leaving the user's `tio` session untouched.

Commands actually exercised through the USB serial shell:

```sh
printf '%s%s\n' USB_PROBE _OK
/bin/busybox cat /proc/uptime
/bin/busybox cat /sys/fs/selinux/enforce
/bin/busybox ps
/bin/busybox dmesg
```

The reply contained `USB_PROBE_OK`, uptime `251.87`, enforcement `0`, and
PID 1 `/bin/busybox sh /init`. A subsequent query returned uptime `607.06`.
The complete live boot log and completed durable partition capture were
retrieved over this connection; their paths and measured extents are listed
above. Terminal command echoes/prompts were excluded from the clean dmesg
file; the durable text was truncated at its explicit EOF marker.

For streaming rather than a finite snapshot:

```sh
/bin/busybox cat /dev/kmsg
```

Ctrl-C stops that stream. This gadget is serial, not Android ADB, and the
shell has no authentication: use it only for temporary diagnostics.
Original Android boot with enforcement enabled is not yet verified.

Remove the temporary host ACL when finished:

```sh
sudo setfacl -x "u:$(id -un)" /dev/ttyACM0
```

Disconnecting the USB device also removes this per-device-node permission.
No permanent group membership or udev rule was added.

After a reset, return directly to fastboot without booting installed Android
and temporarily boot `../ack-boot-test/recovery-ack-pstore-reader.img`.
Read `/sys/fs/pstore` and preserve a raw `logdump` copy before another probe.
The matching reader uses `0x86800000`, 1 MiB, record 4 KiB, console 512 KiB,
pmsg 32 KiB and ftrace 4 KiB. It registered successfully but a subsequent
ACK-to-reader cycle still yielded empty pstore; RAM retention/reader-format
compatibility is not established.

## 15. Original Android init survives SELinux enforcement

The approved temporary image is
`../ack-boot-test/boot-ack-android-policy-capture.img` (34,144,256 bytes),
SHA256 `738a620b4d70f52abd351d45aa3804a75ba90755c456ef4ae894a2a7eaa0a190`.
It was booted with `fastboot boot`, not flashed.

### Image and policy scope

The kernel plus appended DTB is byte-identical to the previous Android
platform-capture image; SHA256
`50bea980c7f0622f128b516b495d1581d600b7d6705bd9321f13d6f72250dbd9`.
The observed kernel identifies itself as
`6.12.93-4k-g3a7d1771d492-dirty`. The checked ACK checkout is
`android16-6.12` at `3a7d1771d4925a56f7eeb8a5ba1faff0c544a9ef`;
the image includes local adaptations, not a claim of an unmodified ACK tree.
No kernel build was performed for this probe.

The original ramdisk entries and metadata were preserved except for the
approved native `/init` replacement. The original `/system/bin/init` is
unchanged. Only `/force_debuggable` and `/userdebug_plat_sepolicy.cil` were
added. There is no added `adb_debug.prop`. The latter CIL is the installed
platform CIL with exactly these two appended rules:

```lisp
(allow kernel device (chr_file (read write)))
(allow kernel device (blk_file (write)))
```

They permit the kernel-domain observer to retain its generic character-device
and raw block-device accesses after policy loading. They do not make an
Android domain permissive. This is diagnostic-only policy, not a proposed
shipping policy or an installed-ROM modification.

The debug-policy selection mechanism was checked against AOSP
`system/core` main commit
[`a3b721a32242006b59cb12bd62c9133632af3a2d`](https://android.googlesource.com/platform/system/core/+/a3b721a32242006b59cb12bd62c9133632af3a2d/):
`init/first_stage_init.cpp` copies the selected ramdisk input to
`/debug_ramdisk`; `init/selinux.cpp` selects it for an unlocked device.
The original first-stage binary contains the relevant marker, policy-path
and environment strings. More importantly, the actual boot log confirms
selection of `/debug_ramdisk/userdebug_plat_sepolicy.cil`.

Before booting, the installed ROM's `secilc` successfully compiled the full
installed policy inputs plus the two rules on the running ACK heartbeat
probe: platform, system_ext and product CIL and `202604` mappings, vendor CIL
and `plat_pub_versioned.cil`, and `plat_sepolicy_genfs_202604.cil`.
The check used `-m -M true -G -N -c 30`; the installed precompiled binary's
policy version is 30. It returned zero despite the bootstrap linker's
missing-linker-configuration warning. This compile check did not load a new
policy into the heartbeat probe.

The native Android wrapper starts independent storage and USB readers,
then hands PID 1 to the original Android init. Storage recording lasts
300 seconds with per-chunk fsync. The new USB path is a native log stream,
not the heartbeat probe's interactive shell.

The image preserves `androidboot.force_normal_boot=1` and the corrected
`androidboot.boot_devices=soc@0/7824900.mmc`, and adds:

```text
rcupdate.rcu_cpu_stall_timeout=10 softlockup_panic=1 hung_task_panic=1 printk.devkmsg=on
```

### Actual boot results

The durable capture proves progress past the former observer cutoff:

| Boot time | Captured event |
|-----------|----------------|
| 19.811398 s | Independent Android USB capture ready |
| 21.203760 s | USB capture disconnected or failed; storage continues |
| 22.663978 s | Debug platform policy selected |
| 56.262518 s | Compiled SELinux policy loading |
| 56.639081 s | Audit record: `enforcing=1 old_enforcing=0` |
| 56.788207 s | Original Android second-stage init started |
| 69.710580 s | ueventd coldboot completed |
| 184.595002 s | Early vendor `mount_all` returned after 100,228 ms |
| 317.820317 s | Last kernel record, with Android init still managing services |

The text ends with `DIAG: EOF Android kmsg dump complete`. All 1,142 kernel
records, sequence 0 through 1,141, are present in order. This disproves a
global kernel stop at SELinux enforcement for this image; it does not prove
a completed Android boot.

The early USB path did not provide a complete stream. It enumerated as
`18d1:9008`; the recreated host node required the temporary ACL again.
The host retrieved only 8,192 bytes of early kernel records. In
`scripts/initramfs-diag/init.c`, `write_all()` returns failure when an
`EAGAIN` write does not become writable within its one-second poll.
Delayed host attachment is consistent with this failure, but the captured
failure message does not identify errno. The independent storage reader
continued through enforcement and completed its capture.

### Remaining boot blockers and evidence

The installed `/vendor/etc/init/hw/init.target.rc`, lines 34–36, waits for
`/dev/block/platform/soc/${ro.boot.bootdevice}`, creates
`/dev/block/bootdevice` pointing there, then runs the vendor fstab.
With `ro.boot.bootdevice=7824900.mmc`, the captured wait for
`/dev/block/platform/soc/7824900.mmc` times out. The fstab still uses
`/dev/block/bootdevice/by-name/*`; `userdata`, `persist`, `dsp` and `modem_a`
are subsequently skipped. `/data` is therefore not successfully mounted by
that action.

The same vendor init file starts `vendor.qseecomd` and waits for
`vendor.sys.listeners.registered=true` at lines 63–64. The log shows repeated
qseecomd exits with status 255 through the end of capture. Its failure cause
is not yet established; the log does not justify blaming every subsequent
service failure on the block-device alias.

Evidence under `../ack-boot-test/`:

- `ack-android-policy-capture-logdump.bin`: full 64 MiB raw partition,
  SHA256 `0a2f4ea4fa0a87cfe43f21e03026effac0b6adccaf8dbff3f172e9df7020a601`.
- `ack-android-policy-capture-logdump.log`: 119,637 bytes, trimmed at the
  explicit Android EOF marker; no stale tail included.
- `android-policy-capture/android-usb-live.log`: 8,192-byte partial stream.
- `android-policy-capture/fstab.qcom`, `init.target.rc`, `init.qcom.rc`,
  `system-ueventd.rc` and `vendor-ueventd.rc`: installed configuration copies.

After the probe, the matching recovery reader was temporarily booted directly
from fastboot. Root ADB identified `logdump` as `mmcblk0p48` for this run.
Its `dd` output included an 82-byte status footer after the 64 MiB payload;
that footer was separated before saving the raw partition. Recovery's
`/sys/fs/pstore` was empty again. Installed system_a was mounted `ro,noload`
only to retrieve configuration evidence; recovery itself had automatically
mounted userdata read-write, so this is not a claim of a wholly read-only
recovery session.

No block-device alias, vendor service or USB timeout fix has been applied.



[ack-board]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts
[ack-pstore-blk]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/fs/pstore/blk.c
[ack-pstore-config]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/fs/pstore/Kconfig
[ack-pstore-zone]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/fs/pstore/zone.c
[ack-block-lookup]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/block/early-lookup.c
[ack-usb]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/drivers/usb/gadget/Kconfig
[ack-usb-legacy]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/drivers/usb/gadget/legacy/Kconfig
[ack-pd]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/drivers/pmdomain/core.c
[ack-regulator]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/drivers/regulator/core.c
[ack-init]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/init/main.c
[ack-boot-makefile]: https://android.googlesource.com/kernel/common/+/89b3cc162c81c59edf4a48f784725849effed283/arch/arm64/boot/Makefile
[donor-ram]: https://android.googlesource.com/kernel/common/+/76efa001ea197723c0423fdb9136e83b483f7aa1/fs/pstore/ram_core.c
[aosp-ab]: https://source.android.com/docs/core/architecture/bootloader/updating
