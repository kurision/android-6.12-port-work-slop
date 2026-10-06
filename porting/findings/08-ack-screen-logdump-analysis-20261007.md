# Xiaomi Mi A1 (tissot) ACK Android 16 (Kernel 6.12)
## Screen Logdump Analysis: `ack-screen-logdump-20261007.bin`

**Date:** 2026-10-07  
**Artifact Analyzed:** [`porting/artifacts/ack-screen-logdump-20261007.bin`](file:///home/kurision/development/kernel/ack-android16-6.12/porting/artifacts/ack-screen-logdump-20261007.bin) (64 MiB raw partition dump)  
**Companion File:** [`porting/artifacts/ack-screen-logdump-20261007.log`](file:///home/kurision/development/kernel/ack-android16-6.12/porting/artifacts/ack-screen-logdump-20261007.log) (48,484 bytes)

---

## 1. Executive Summary & Critical File Integrity Finding

### 1.1 The Dual-Boot Partition Residue (The Core Discovery)
Inspection and binary diff analysis of `ack-screen-logdump-20261007.bin` revealed that **the 64 MiB raw dump is NOT a single contiguous boot log**. Instead, it contains two distinct regions:

1. **Active Boot #5 Data (Bytes 0 to 48,484):**
   - Matches [`ack-screen-logdump-20261007.log`](file:///home/kurision/development/kernel/ack-android16-6.12/porting/artifacts/ack-screen-logdump-20261007.log) byte-for-byte.
   - Represents the actual run of local build `#5 SMP PREEMPT Tue Oct 6 23:40:38 +0545 2026` (`kurision@omarchy`).
   - Sequence records run from **seq 0 (0.000s) to seq 602 (42.595s)**.
   - Ends abruptly at sequence 602 immediately following SELinux policy load.

2. **Stale Historical Residue (Bytes 48,485 to 67,108,864):**
   - **Bytes 48,485 to 162,104:** Stale log data from the previous **Fedora Build #14** boot ([`ack-android-snapshot18h-build14-logdump-20261006-211656.log`](file:///home/kurision/development/kernel/ack-android16-6.12/porting/artifacts/ack-android-snapshot18h-build14-logdump-20261006-211656.log)), running through 319.852s.
   - **Bytes 162,105 to 167,854:** Stale log data from an earlier **Build #18c** run ([`ack-android-snapshot18c-display-wled-logdump.log`](file:///home/kurision/development/kernel/ack-android16-6.12/porting/artifacts/ack-android-snapshot18c-display-wled-logdump.log)).
   - **Bytes 167,855 to 67,108,864:** Null padding.

> [!CAUTION]
> **Do not interpret records past byte 48,484 (seq 602) as current boot evidence!**  
> This directly validates Rule 11 of [`snapshot18h-analysis.log`](file:///home/kurision/development/kernel/ack-android16-6.12/porting/artifacts/snapshot18h-analysis.log): *"Do not interpret stale tails in older durable dumps as current-boot evidence."*  
> The 46 repeated exits of `vendor.qseecomd` (status 255) and audit denials seen in the tail of `.bin` belong strictly to Build #14, **not** the current run.

---

## 2. Active Boot Identification & Environment

- **Kernel Banner:**
  `Linux version 6.12.93-4k-g05a6f7b2c2c5-dirty (kurision@omarchy) (Android (13989888, +pgo, +bolt, +lto, +mlgo, based on r563880c) clang version 21.0.0, LLD 21.0.0) #5 SMP PREEMPT Tue Oct 6 23:40:38 +0545 2026`
- **Git Commit:** `05a6f7b2c2c5-dirty` (`docs(port): preserve build14 USB captures and display verdict` with working-tree tree changes).
- **Machine Model:** `Xiaomi Mi A1` (MSM8953 / `tissot`).
- **Command Line Highlights:**
  - Carries `androidboot.boot_devices=soc@0/7824900.mmc` and `androidboot.bootdevice=../..`.
  - Added `console=tty0 loglevel=8`.
  - Result: Legacy framebuffer console enabled early at seq 92 (1.206s):
    `6,92,1206,-,caller=T0;printk: legacy console [tty0] enabled`

---

## 3. Subsystem Health & Progression

### 3.1 Display & DRM Subsystem (Successful Readback)
- **Panel Detection:**
  `panel-otm1911 1a94000.dsi.0: panel status 0x9c (downstream expects 0x9c)`
  Confirmed functional DSI readback from the OTM1911 glass.
- **Console Framebuffer:**
  `Console: switching to colour frame buffer device 135x120`
  `msm_mdp 1a01000.display-controller: [drm] fb0: msmdrmfb frame buffer device`
  `panel-otm1911 1a94000.dsi.0: 1080x1920@60 24bpp dsi 4dl - ready`
- **Known Non-Fatal Warnings:**
  - Clock RCG2 warning at `drivers/clk/qcom/clk-rcg2.c:133 update_config+0xd4/0xe8`: `pclk0_clk_src: rcg didn't update its configuration` during DSI link frequency change.
  - MDP5 error interrupt: `[drm:mdp5_irq_error_handler] *ERROR* errors: 04000000`.
  - IRQ balance warning: `Unbalanced enable for IRQ 38` at `kernel/irq/manage.c:796 enable_irq+0xa4/0x108` from workqueue `wled_ovp_work`.
  - Touch probe deferred/failed: `edt_ft5x06 1-0038: probe with driver edt_ft5x06 failed with error -110`.

### 3.2 Storage & Partitions
- **eMMC (`mmc0`):** `HS400 MMC card at address 0001, HCG8a4 58.2 GiB` -> `mmcblk0` (partitions p1 to p52).
- **SD Card (`mmc1`):** `ultra high speed SDR104 SDHC card, SD32G 29.1 GiB` -> `mmcblk1` (p1, p2).
- **First-Stage Mount:**
  - `system_a` on `/dev/mmcblk0p25` mounted read-only at t = 35.150s (`EXT4-fs (mmcblk0p25): mounted filesystem ... ro without journal`).
  - Init switched root to `/system` at 35.598s.

### 3.3 Guard Milestone: Bootdevice & Contexts Overlay Success!
The enhanced `install_android_guard` in [`scripts/initramfs-diag/init.c`](file:///home/kurision/development/kernel/ack-android16-6.12/scripts/initramfs-diag/init.c) ran before SELinux policy was loaded and executed completely without errors:
- **Record seq 580 (36.049s):**
  `DIAG: bootdevice guard installed read-only f2fs-only fstab and vendor contexts before policy load`
- **Record seq 581 (36.060s):**
  `DIAG: bootdevice canonical alias and legacy wait path ready`
- **Verification:** Both `/ack-protected-fstab.qcom` (bound to `/vendor/etc/fstab.qcom`) and `/ack-vendor-file-contexts` (bound to `/vendor/etc/selinux/vendor_file_contexts`) were staged and verified read-only before PID 1 loaded policy.

---

## 4. Root Cause Analysis: Why Did the Capture Cut Off at 42.595s?

### 4.1 Chronology of the Cutoff
1. **t = 40.192s (seq 587):** Second-stage init begins SELinux initialization:
   `init: Opening SELinux policy` -> `init: Loading SELinux policy`.
2. **t = 41.473s - 42.417s (seq 589 - 601):** Kernel validates capabilities and activates policy.
3. **t = 42.595s (seq 602):** The final recorded entry in the active log:
   `5,602,42595680,-,caller=T81;audit: type=1400 audit(96380.115:2): avc: denied { read } for pid=168 comm="init" path="/kmsg" dev="devtmpfs" ino=10 scontext=u:r:kernel:s0 tcontext=u:object_r:device:s0 tclass=chr_file permissive=1`

### 4.2 The Capture Termination Mechanism in `init.c`
In [`scripts/initramfs-diag/init.c`](file:///home/kurision/development/kernel/ack-android16-6.12/scripts/initramfs-diag/init.c), the logging loop is implemented in `dump_log()`:

```c
static int dump_log(int in, int out, unsigned seconds, int durable)
{
    time_t deadline = monotonic_seconds() + seconds;
    char buf[8192];

    do {
        ssize_t got = read(in, buf, sizeof buf);
        if (got > 0) {
            if (write_all(out, buf, (size_t)got) ||
                (durable && fsync(out)))
                return -1;
        } else if (got < 0 && errno == EPIPE) {
            say(out, "\nDIAG: kmsg overrun; some records lost\n");
        } else if (got < 0 && errno != EAGAIN && errno != EINTR) {
            return -1;   /* <--- ROOT CAUSE OF CUTOFF */
        } else {
            usleep(200000);
        }
    } while (monotonic_seconds() <= deadline);
    return 0;
}
```

- When SELinux enforcement loaded, PID 168 (running in the `u:r:kernel:s0` security context) had its `/dev/kmsg` descriptor subjected to runtime `security_file_permission()`.
- Reading `/dev/kmsg` (`tcontext=u:object_r:device:s0 tclass=chr_file`) was audited and returned **`errno = EACCES` (Permission Denied)**.
- In `dump_log()`, `errno != EAGAIN && errno != EINTR` evaluated to `TRUE` for `EACCES`.
- `dump_log()` immediately returned `-1`, closing `out` (the `logdump` partition descriptor) and terminating PID 168!
- As a consequence, **the durable logger stopped recording at t = 42.595s**, while Android init and the rest of the OS continued booting in the background.

---

## 5. Comparison: Build #14 vs. Current Build #5

| Parameter | Build #14 (Snapshot 18h) | Current Build #5 (`ack-screen-logdump-20261007`) |
| :--- | :--- | :--- |
| **Compiler** | Fedora Clang 22.1.8 | Android Clang 21.0.0 (r563880c) |
| **Builder** | `sneha@katwal` | `kurision@omarchy` |
| **Console Cmdline** | `console=ttynull` | `console=tty0 loglevel=8` |
| **tty0 Framebuffer** | Late (only via fbcon driver attach) | Early (legacy console enabled at t=1.206s) |
| **Guard Installed** | `fstab` only | `fstab` **AND** `vendor_file_contexts` |
| **Active Capture End**| 319.852s (seq 1569) | 42.595s (seq 602) due to `EACCES` on `read(/dev/kmsg)` |
| **Late Boot Records in `.bin`** | Real Build #14 logs (46x `qseecomd` 255) | Stale Build #14 residue (unwritten space in 64MB partition) |

---

## 6. Actionable Remediation Plan

To capture the entire Android boot and evaluate whether `ack-vendor-file-contexts` resolved the SSD and `qseecomd` blockers:

1. **Fix `dump_log()` in [`scripts/initramfs-diag/init.c`](file:///home/kurision/development/kernel/ack-android16-6.12/scripts/initramfs-diag/init.c):**
   - Treat `EACCES` as non-fatal or retryable rather than aborting:
     ```c
     } else if (got < 0 && errno != EAGAIN && errno != EINTR && errno != EACCES) {
         return -1;
     }
     ```
2. **SELinux Policy for Kernel Logger:**
   - In [`porting/artifacts/fedora-build/userdebug_plat_sepolicy.cil`](file:///home/kurision/development/kernel/ack-android16-6.12/porting/artifacts/fedora-build/userdebug_plat_sepolicy.cil), ensure the debug rules are present in the boot ramdisk's `/userdebug_plat_sepolicy.cil`:
     ```cil
     (allow kernel device (chr_file (read write)))
     (allow kernel device (blk_file (write)))
     (allow kernel init (dir (search)))
     (allow kernel init (lnk_file (read)))
     ```
   - This prevents `EACCES` when PID 168 reads `/dev/kmsg` and writes to `/dev/block/bootdevice/by-name/logdump`.
3. **Wipe `logdump` partition header or zero buffer before capture:**
   - Writing an explicit zero-fill or sequence delimiter prevents stale previous-boot data from remaining in unwritten sectors of the 64 MiB partition.
