# Handoff — tissot 6.12 port, state at commit `017effda6`

Written for whoever picks this up next. Read this first, then
`porting/REFERENCE-boot-testing.md`, then `porting/FAILING-COMPONENTS.md`.

## The one-line state

Battery and charging **work and are verified**. `sys.boot_completed` is **still
never set**; the device always stalls after `boot_progress_enable_screen`. The
cause of that stall is **not yet identified** — there are at least two distinct
problems and I have been wrong twice about which one is the blocker.

## Read this before spending a boot cycle

Boot cycles are the scarce resource. Three things in this repo will waste one
if you do not know them:

1. **`/data/anr` is the richest evidence and the hardest to reach.** `shell` can
   `ls /data/anr/` on the port kernel but **cannot `cat` the files** (confirmed
   permission denied). You must pull them from a **stock** boot where `su`
   exists. The files are persistent, so any past boot's traces can be pulled
   later — but you must match a trace to a run by **SystemServer's pid**, not by
   filename or timestamp. The device clock resets every boot, so `ls -lt`
   ordering is meaningless across boots. I got this wrong and briefly claimed a
   trace described the current run when it was two runs old.

2. **Never leave a capture script running across a boot.** `pgrep -af
   usb-boot-capture` must be empty before you boot. A leftover one from a prior
   attempt silently confounded run146.

3. **A `genfscon` naming an undeclared type kills the boot.** secilc aborts,
   init dies, recovery. See "The backlight dead end" below. And this **cannot be
   checked offline** — the CIL in the ramdisk is a fragment, `vendor_sepolicy.cil`
   is read from `/vendor` at runtime.

## Where the phone is

**On stock 4.19** at commit time. Before any port boot it must be on stock
(`clear-logdump.sh` needs `su`). `adb reboot` off a `fastboot boot` image
returns it to stock.

Last confirmed-good image: **run150** (booted, 444 KB kernel log captured).
run151 never booted usefully — it bricked the boot into recovery.

## What is verified working

**Battery and charging — done, and this is the user's original ask.**

    USB powered: true   status: 2 (CHARGING)   level: 92
    voltage: 4145 mV    temp: 27.7 C    health: GOOD
    charge counter moved 1959547 -> 1957591 over 45s while voltage climbed

- Fuel gauge prints a line byte-identical to stock; both QPNP drivers bound.
- The charging-control HAL registers. `dumpsys battery` reports live values.

Mechanism, because it will come up again: `vendor_sepolicy.cil` labels sysfs
with **literal CAF 4.19 paths** (`soc`, `200f000.qcom,spmi`, `spmi0-02`,
`pmi8950@2`) that no mainline kernel can match (`soc@0`, `200f000.spmi`,
`spmi-0/0-02`, `pmic@2`). Injecting `genfscon` for the real paths is the fix.
Fragments are one file per run in `porting/policy/`.

## The boot stall — open, and I have been wrong twice

`sys.boot_completed` unset at 300+ s, `init.svc.bootanim` still `running`,
ActivityManager drops `system_server_pre_watchdog` and goes quiet.

**Hypothesis A — the charging-control HAL.** In one trace SystemServer's main
thread is:

    ServiceManager.waitForDeclaredService
      <- ChargingControlController.<init>
      <- HealthInterfaceService.onStart
      <- LineageSystemServer.startServices
      <- SystemServer.startOtherServices

`waitForDeclaredService` has **no timeout**, so `startOtherServices` never
returns. Measured stock-vs-port delta:

    stock: vendor.lineage.health.IChargingControl/default   present
    port:  absent   (every other lineage service IS present)

The HAL is **not** failing: pid 686 `vendor.lineage.health-service.default` is
alive, state `S`, idle, logs **nothing**, and has **no SELinux denial** naming
it. It simply never registers the interface.

**But hypothesis A is not present in every run.** The trace above has
SystemServer pid **1040**; run149/150 is pid 1104 and run150b is pid **1101**.
In run150b's own trace there are **zero** `ChargingControlController` frames and
main is idle in `Looper.loop()` — `startOtherServices` completed, yet boot is
still incomplete. So A explains at most some runs.

### Do this first

1. **VINTF version check** — `vendor/etc/vintf/manifest/vendor.lineage.health-service.default.xml`
   declares `vendor.lineage.health` **version 2**. If the binary registers v1,
   the servicemanager marks it declared-but-unavailable, which is exactly the
   state `waitForDeclaredService` cannot escape. Cheapest test, fits the
   evidence, and nothing else has been checked.
2. Watch `IChargingControl` over a **long** window. It was absent at 182 s but I
   only sampled once — I cannot rule out a slow registration.
3. Chase `android.hardware.health-service.qti` (pid 673), which does not answer
   binder: `Failed to get binder state info for pid: 673 status: -2`, and the
   watchdog dumps it. Not investigated.

## FastRPC — real progress, wrong ceiling

The adsprpcd chain is genuine and each fix was real, but it does not converge:

| run | errno | meaning | fixed by |
|---|---|---|---|
| 147 | 2 ENOENT | node was `/dev/fastrpc-adsprpc-smd` | run148, drop redundant `fastrpc-` prefix |
| 148 | 16 EBUSY | empty session table | run149, add `cb@0` DT child |
| 149 | ENOTTY | ioctl 12 unimplemented | **not sufficient — see below** |

The real problem is bigger and I only found out by having it investigated
properly: **CAF and mainline number their ioctls completely differently.** Only
nr 13 coincides, payload differs even there, and `_IOC` encodes size in bits
16-29 so the `cmd` integers barely overlap (CAF `INIT` `0xd0285206` vs mainline
nr-6 `MMAP` `0xc0205206`). A CAF-built `adsprpcd` hits `-ENOTTY` on its
INIT/MMAP/MUNMAP/INVOKE/GETINFO **regardless of what this driver implements**.
Making audio/camera/sensors work means a **CAF ABI translation layer**.

`porting/staged/fastrpc-ioctl12-control.patch` implements ioctl 12 with the
donor's ABI verified byte-identical (`sizeof` 12, cmd `0xc00c520c`). It is
**deliberately unapplied** so it cannot contaminate a boot. Read its README
before applying — it is not expected to fix adsprpcd.

Note `porting/patches/` is gitignored (`.gitignore:128` has a bare `patches`
entry for quilt). That directory is `porting/staged/`.

## The backlight dead end — do not re-attempt blind

Dpps cannot init; `mm-pp-dpps` is denied on `brightness`, and
`Dpps: main():33 Failed to initialize DPPS` follows. This is worth fixing
eventually but **both obvious moves have been tried**:

- Labelling the attributes `sysfs_leds` (run150): compiles, does nothing.
  `sysfs_leds` is a declared type that is **never an allow target**. The denial
  came back byte-identical, which reads like a bad path and is not.
- Labelling them `sysfs_leds_202604` (run151): **killed the boot into
  recovery**. `secilc: Type not a type or type alias`. That name *is* what
  `mm-pp-daemon` is allowed on, and it does appear in `vendor_sepolicy.cil` as
  an allow target — but it is not declarable in a `genfscon`. **Appearance in
  an `allow` is not the same as being declarable.** Confirmed in
  `porting/policy/README.md`.

The untried option is an **explicit `allow`** on `sysfs_leds` rather than a
label, checked by reading the policy files directly rather than inferring from
an `allow`.

Also relevant: `init.rc:1273` chowns `/sys/class/leds/lcd-backlight/brightness`,
a path that does not exist on this port (we create no leds-class device, only
`backlight/backlight`).

## Mistakes I made, so you do not repeat them

- Claimed **audio was fixed** from one run's `grep -c` returning 0. Later runs
  disproved it (381, 623 errors). A single grep count on one run is not a
  component status.
- Claimed **stock runs permissive**. It is Enforcing. My `selinux=0` and
  `--debuggable` detours were wasted cycles.
- Claimed duplicate `genfscon` breaks secilc. **It does not** — run142/run143
  carry duplicates and boot. My own new guard caught the error.
- Claimed the **GPU is the blocker**. `/dev/kgsl-3d0` exists and SurfaceFlinger
  is registered. The tracker's original claim is not supported.
- Used `service list | grep composer` as a test for a composer2 HAL. It
  registers with hwservicemanager, not the legacy service manager. The composer
  was running all along.
- **Cleared the logdump before a boot with no capture path**, destroying the
  evidence when that boot died. If a boot might go blind, leave the logdump.
- Left a **background capture script running** across a later boot.

## Still open, lower priority

- **Charging rate**: same cable, same moment — stock `Max charging current:
  500000`, port `100000` µA. Port DT sets `constant-charge-current-max` 1 A, so
  the observed value is neither the DT nor the stock figure. Which property the
  health HAL reads has not been checked.
- **WLAN firmware not staged.** Same mechanism as ADSP: `wcnss.mdt` + 4.2 MB of
  segments on `/firmware/image`, currently `error -2`.
- **SystemUI ANR**: blocked in `BpSurfaceComposer::getGpuContextPriority` — a
  binder call to SurfaceFlinger that never returns. Separate process, separate
  stack, so **not** evidence for the SystemServer cause. Unrelated-ness not
  established.
- **Fingerprint SIGSEGV does reproduce** (fault addr `0xc0`). Earlier "no SIGSEGV
  in run137" was a rolled-over log window, not an absence.

## Useful commands

    # build (env is easy to lose)
    R=/home/kurision/.cache/run126-rust.oFKCctgK
    TC=$R/rustup/toolchains/1.82.0-x86_64-unknown-linux-gnu
    PATH="$TC/bin:$PATH" RUSTC=$TC/bin/rustc HOSTRUSTC=$TC/bin/rustc \
    BINDGEN=$R/bindgen-0721/bin/bindgen ACK_TREE=/tmp/ack-run131-source \
    OUT_DIR=.../out-runNNN JOBS=12 scripts/build-ack-tissot.sh

    # one policy change per image; append ONLY the new statements
    python3 porting/logging/package-diag-boot.py \
      --base-image .../boot-runNNN.img --kernel-dir .../kdir-runNNN \
      --stage-kernel .../out-runNNN/arch/arm64/boot \
      --init .../init-run127 --keep-stock-console --debuggable \
      --policy-append porting/policy/<one-fragment>.cil \
      --out .../boot-runNNN.img --report .../package-runNNN.json

The packager refuses duplicate ramdisk record names (that is a real defect) and
**warns** on duplicate `genfscon` (harmless — verified). Always base an image
on a run that does not already contain the fragment you are adding, or you will
silently ship it twice.

## Inventory — what is actually on disk

All under `porting/artifacts/snapshot60/`. Images are gitignored, so none of this
survives a `rm`; recover from git history before deleting anything.

### Images, newest first

`kernel` is the kernel payload sha256 prefix — **the reliable way to tell two
builds apart**, since every build reports the same `uname -r`
(`6.12.93-4k-ga54b131a885c-dirty`).

| image | kernel | size | base | policy fragment | booted? |
|---|---|---|---|---|---|
| `boot-run151.img` | `336a7fc23a72` | 43712512 | run149 | `210af3c87eb0` | **no — secilc abort, recovery** |
| `boot-run150.img` | `336a7fc23a72` | 43712512 | run149 | `d55b06355e29` | **yes, current best** |
| `boot-run149.img` | `336a7fc23a72` | 43710464 | run148 | none | yes |
| `boot-run148.img` | `644881c2a781` | 43710464 | run147 | none | yes |
| `boot-run147.img` | `afdc4cc452fe` | 43708416 | run144 | none | yes (after an EDL reset) |
| `boot-run144.img` | `dabc20b927d8` | 43708416 | run143 | `f54704992603` | yes |
| `boot-run143.img` | `dabc20b927d8` | 43708416 | run142 | `8f4477fc3138` | yes |

`run145`, `run146` never booted usefully. `boot-run146.img` carries a rejected
kernel and a policy fragment later found useless — kept for the record, not for
use. A rejected `run144` image (duplicate firmware records) was deleted; its sha
was recorded at `/tmp/opencode/run144-rejected.sha256`
(`f6dff9c8136e778df...`) before removal.

`package-runNNN.json` beside each image is the provenance: base image, kernel
payload sha, cpio record count, and the policy fragment sha.

### Kernel logs (`*-usb.log`, from the USB diag gadget)

The most recent and most complete:

| file | bytes | note |
|---|---|---|
| `run150b-usb.log` | 444401 | **run150b**, the most recent port boot |
| `run150-usb.log` | 444986 | run150, same image |
| `run149-usb.log` | 444441 | run149 |
| `run148-usb.log` | 438053 | run148 |
| `run151-usb.log` | 148832 | **truncated** — dies at the secilc abort, which is the point of it |
| `run146-usb.log` | 131072 | truncated, run146 |
| `run144b-usb.log` | 439391 | run144 (the `b` is the successful retry) |
| `run143-usb.log` | 441851 | run143 |
| `run141-usb.log` | 440169 | run141 |

Many earlier runs have 0-byte logs — those are the splash/recovery failures.

### Userspace logs (`*-logcat-dump*.log`)

`run151-logcat-dump.log` (1.2 MB) is the smallest and covers run151.
`run150b-logcat-dump.log` (3.6 MB) is run150b. `run149-logcat-dump.log` and
`run149-logcat-dump2.log` are the same run at two points in time — the second is
useful because the ring buffer rolls over, so a count taken from the first may
simply have scrolled off (this is how I wrongly concluded audio was fixed).
`run143-logcat-dump.log` / `-dump2.log` and `run144b-logcat-dump.log` are the
largest.

`run141-host-logcat.log` (14.6 MB) is the **only** log containing the
charging-control HAL actually registering — `IChargingControl/default registered
(binder 288)`. It is the baseline that later runs do not reproduce, so keep it.

### ANR traces (`anr/`)

| file | bytes | what it is |
|---|---|---|
| `ss-anr-102533.txt` | 424132 | **the `waitForDeclaredService` stack.** Subject `Blocked in handler on main thread (main) for 45s`. SystemServer **pid 1040** — an *older* boot, not run150b |
| `r150b-anr.txt` | 651547 | run150b's trace (pid **1101**). Subject is `com.android.phone` ui thread; system_server included but **main is idle in `Looper.loop()`**, zero `ChargingControlController` frames |
| `r150b-anr_2026-10-09-10-33-00-305` | 452981 | run150b-area, pulled with the same prefix |
| `r150b-anr_2026-10-09-10-34-04-699` | 705002 | largest; pulled with the same prefix |
| `anr_2026-10-09-10-25-42-095` | 71536 | SystemUI ANR — blocked in `BpSurfaceComposer::getGpuContextPriority` |
| `anr_2026-10-09-10-25-42-072` | 71966 | the matching SystemUI ANR |

The four files prefixed `r150b-` were pulled with `su` from stock; the two
unprefixed SystemUI ones were pulled as plain `shell` and were readable. The
naming is historical, not a guarantee — check the pid inside before trusting
which run a trace belongs to.

`/data/anr` on the device still holds many more, including traces whose
SystemServer is pid 1104 (run149/150). Those have not been pulled and are worth
checking, since they would show whether the `waitForDeclaredService` block is
present in the 1104 runs or only in the older 1040 run.

### Policy fragments (`porting/policy/`)

One file per run. **Append only the fragment for the change you are testing**, to
a base that does not already contain it — that mistake happened twice and the
packager cannot catch a semantically-duplicated append (duplicates are merely
warned about, because secilc accepts them).

| file | statements | status |
|---|---|---|
| `harness-genfs-battery.cil` | 3 `genfscon` | **WORKS.** Labels the battery `power_supply` nodes so the charging-control HAL registers and `dumpsys battery` reports live values. The fix that got the original ask done. |
| `harness-genfs-backlight.cil` | 2 `genfscon` | Labels the backlight **directory** only. Compiles, is in every image from run142 on, and is **insufficient** — it does not fix the `mm-pp-dpps` denial. |
| `harness-genfs-extcon.cil` | 10 `genfscon` | **WORKS.** Labels the charger's extcon subtree `sysfs_graphics`. Verified: `grep -c ExtconUEventObserver` goes to 0 where run143 logged the failure plus the `PhoneWindowManager.init` frames. Did *not* clear the boot stall. |
| `harness-genfs-backlight-attrs.cil` | 4 `genfscon` | **USELESS as written** — labels the attributes `sysfs_leds`, which is declared but never an allow target. Ships in run150/151. The comment block at the top explains the trap in full. |
| `harness-sysfs-allow.cil` | 3 `allow` | Dead end, kept as record. The run140 experiment; it compiled (`secilc exit_code=0x0`) and did nothing. |

`porting/policy/README.md` explains the CAF-vs-mainline naming mismatch, and ends
with **why `genfscon` type validity cannot be checked offline** — read that
before writing another one.

Verified contents of the shipped images (counted from the CIL, not assumed):

| image | total `genfscon` | battery | backlight dir | extcon | backlight attrs | attrs labelled |
|---|---|---|---|---|---|---|
| run143 | 367 | 3 | 2 | 0 | 0 | — |
| run144 | 377 | 3 | 2 | 9 | 0 | — |
| run147 | 377 | 3 | 2 | 9 | 0 | — |
| run148 | 377 | 3 | 2 | 9 | 0 | — |
| run149 | 377 | 3 | 2 | 9 | 0 | — |
| **run150** | 381 | 3 | 2 | 9 | 4 | `sysfs_leds` (no effect) |
| run151 | 381 | 3 | 2 | 9 | 4 | `sysfs_leds_202604` (**boots into recovery**) |

So **run150 carries the full working set** — battery labels, extcon labels, and
four inert backlight statements. run149 is the same minus the inert four.

### Build trees

`out-run149` and later under the repo root; `/tmp/ack-run131-source` is the tree
the build script actually compiles (`ACK_TREE`). `/tmp` is tmpfs — do not stage
anything there you cannot lose. ~25 GB free on `/home`.

## Artifacts

`boot-run130.img` is the known-good base, sha256 `30bacf46ecf72dd6ca71de3f83601b7e1e71f8173b59c59326af2eb5f4d1b7f1`.
It and the run130 ramdisk must be preserved in every image — the diag ramdisk is
**not reconstructible**; it carries a patched SELinux policy and a
`force_debuggable` trigger that nothing in the tree regenerates. Rebuilding a
base from stock produces an image that packages cleanly, boots, and then stalls
in userspace several stages later than it should.