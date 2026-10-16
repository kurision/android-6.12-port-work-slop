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

## Artifacts

`boot-run130.img` is the known-good base, sha256 `30bacf46ecf72dd6ca71de3f83601b7e1e71f8173b59c59326af2eb5f4d1b7f1`.
It and the run130 ramdisk must be preserved in every image — the diag ramdisk is
**not reconstructible**; it carries a patched SELinux policy and a
`force_debuggable` trigger that nothing in the tree regenerates. Rebuilding a
base from stock produces an image that packages cleanly, boots, and then stalls
in userspace several stages later than it should.