# Handoff — tissot 6.12 port, update 2026-10-16 (macOS session)

## Latest: run161 (2026-10-16 evening) — read this first

**Last used boot image**: `porting/artifacts/snapshot60/boot-run161.img`
(gitignored; provenance in `package-run161.json`, `kdir-run161/SHA256SUMS`).

- image sha256 `ad5ce74f0534d4c70b69d0e770b8d47b6792bec8c70c9e31e816074a7f40f4a7`
- kernel `6.12.93-4k-g8f6a13ced3c2-dirty #57`, Image.gz-dtb sha256
  `69b9955be90d4d67e06865b133e9ba3958df81c81412c5cbb4283b1f63db2a81`
- base `boot-run155.img` ramdisk/init/cmdline unchanged; `--debuggable
  --keep-stock-console`. Symbols: `run161/System.map` (vmlinux pull was
  incomplete).
- Repackage: `package-diag-boot.py --base-image boot-run155.img --kernel-dir
  kdir-run161 --init init-run127 --debuggable --keep-stock-console`.

**State**: Android boots (`sys.boot_completed=1` ~104-110 s, bootanim
stopped, no watchdog, no new ANRs), screen black.

Commits since run155 (unpushed unless pushed by user): `ac7728da2`,
`5ee66cef0` (probes), `4aafe26dc` (**fix**: soft reset on start without
GPU regulators — cured `CP initialization failed to idle`), `c72069425`
(donor A506 DT quirks; no effect), `12fd6a087`, `8f6a13ced` (fault IB dump
+ CP fetch position).

**Open GPU blocker**: every GL context faults (`800001C1`, CP-only busy).
run161: SurfaceFlinger stops at IB1 offset 0x1a0 after two IB2 calls,
around `CP_COND_EXEC`/`CP_MEM_WRITE 0x30f48000`/`CP_WAIT_MEM_WRITES`.
Hypothesis: CP waits on user-memory access that never completes under
NOMMU. Next: at fault, CPU-read the CP_MEM_WRITE target and log whether the
user buffer is physically contiguous. Preemption is disabled (NOMMU) but
not at the stop point. Details: `TRACKER-kgsl-port.md` "Run156-158"+.

**Black screen**: also backlight SELinux denials (`hal_light_default`
write `brightness`, `tcontext=sysfs`), see `FAILING-COMPONENTS.md`.

**Process**: logdump is not cleared between boots; stale tails from older
runs follow the fresh dump (run158/159 "392 s" lines were Run155). Pull
builds with `pull-built-kernel.sh -D <dir>` (positional dir is ignored).
Port boot has `ro.debuggable=0`: no adb root; read kernel log from stock
logdump.

## Read this update first (newer, supersedes the rest of this file)

**`sys.boot_completed` IS set on the user's manual run150 boot. The port boots
to a complete Android.** This contradicts every "boot never completes" statement
below, including the one-line state in the historical section. Do not act on
those until this is reconciled.

Verified 2026-10-16 on device `2819f2320604`, boot_id
`f6a1201b-1e6f-4622-bd3e-f9d079a34fab`:

- uptime **590.26 s**: `sys.boot_completed=1`, `mSystemReady=true`,
  `mSystemBooted=true`, `dumpsys window lastanr` -> no ANR since boot.
- Still `init.svc.bootanim=running` while booted. Cosmetic, not a stall.
- SystemServer is now PID **4977**, SurfaceFlinger still **712**. The PID 1108
  recorded below is dead — see the watchdog kill.

### What actually happens: SystemServer is watchdog-killed, then boot succeeds

From `run150-manual-live-20261016/port-logcat.log`:

- `watchdog: Blocked in handler on ui thread (android.ui) for 191s` at
  `:74356`, then `:78059` `*** WATCHDOG KILLING SYSTEM PROCESS`. The annotated
  subject is `HardwareRenderer.nSyncAndDrawFrame` <- `syncAndDrawFrame` <-
  `ViewRootImpl.performDraw` on `android.ui`.
- `:78082` `Sending signal. PID: 1108 SIG: 9`; `:78201` Zygote reports exit.
- `:80348` Zygote forks **4977** as the new SystemServer.
- The restarted server re-runs services: `:100211` `boot_progress_enable_screen:
  393914` (uptime ~394 s), then `:125670`+ boot completed at ~uptime **484 s**.

So the stall is not permanent: the GPU-blocked UI thread is killed by the
watchdog, the fresh SystemServer gets past the stage that blocked the first one,
and boot finishes. This is the same wait chain the ANR traces describe
(`adreno_drawctxt_wait`, `Fence waitForever ... timeline(kgsl-3d0_8-system_server)`),
seen as its consequence rather than as a permanent deadlock.

The still-unfixed part is the *first* SystemServer's 191 s block in
`nSyncAndDrawFrame` — a kgsl fence that never signals. Watchdog restart currently
masks it. That is the real remaining kernel-side target.

### Evidence saved this session (no reboot, nothing cleared)

- `run150-manual-snapshot-20261016/final-identity-20261016.log` — uptime, boot_id,
  PIDs, boot state at the end of the manual boot.
- `run150-manual-snapshot-20261016/boot-completed-confirm-20261016.log` — first
  `boot_completed=1`, battery state.
- `run150-manual-snapshot-20261016/logcat-post-boot-completed-20261016.log` —
  3.86 MB full `-b all` dump taken after completion.

### Still valid from the older update below

Nothing was flashed, changed or cleared in this session. The device is still on
the user's manual run150 RAM boot; the logdump on the device is untouched.
Handoff steps 2-4 (reboot to stock, persistent pull as label 153, read the
recovered logdump) are now **lower priority** — worth doing for the kernel-side
fence evidence, but no longer blocking, since userspace boot is proven.


**No kernel, init, policy, DT, firmware or boot-image changes were made in this
session. No fix was tested. Nothing was flashed.** The supplied run150 image
was RAM-booted as the run152 control; the user subsequently RAM-booted run150
manually. Do not conflate these attempts or assign their evidence by date alone.

### Device state at the time the older update was written

- Device `2819f2320604` is reachable through ADB on **6.12**, not stock.
- Query at the time: `6.12.93-4k-ga54b131a885c-dirty`, uptime **323.92 s**,
  `sys.boot_completed` empty, SurfaceFlinger PID **712**, SystemServer PID **1108**.
  That reading was taken **before** the watchdog kill and is superseded above.
- This is the **user's manual run150 boot**. Leave its logdump intact.
- The read-only manual-boot observer (PID **37291**, `--seconds 360`) has now
  finished; the harness reported completion after this handoff was written.
  Its cleanup stops its logcat child. It does NOT reboot. Recheck processes
  before rebooting; do not leave a reader across another boot.
- The run152 observer and USB reader were stopped. No automatic stock return
  occurred: ADB was unavailable when that orchestration tried to recover.

### Exact image and terminology

`porting/artifacts/snapshot60/boot-run150.img` is the image the user supplied.
Verified before testing and again afterward:

```
size:                  43712512
image sha256:          6a73c408a19dc57ebb6acb9c2865a9e8bfa8689fc6434c3c5eaae1b8bcf4fce1
kernel payload sha256: 336a7fc23a72437826ca39325cc0f8bf7f212ec36b7ed4ecc6afd50ff6839946
ramdisk sha256:        b14782e30652aa48333f30ea0a5469ae44b0e1a37283491bbd18d4ad1ff95eef
init sha256:           da0f2a6123838d10e36e412ba243a3eff92577b0acf58293b4fd83b3bddc08f4
cpio records:          683
```

`package-run150.json` and `init-run127` are also present. The image embeds the
full inherited debug ramdisk and battery/extcon policy. Do not reconstruct it.
Run150 and run151 were both packaged from **run149** (original table below).
Run130 is the earlier known-good ramdisk base, not run150's immediate parent.
"Known-good" here means reaching userspace/ADB, NOT completing Android boot.

### What happened in run152

- Used the exact run150 image above. `run152-capture-host.log:3-6` records
  `fastboot ... boot .../boot-run150.img`, sending and booting both OKAY.
- Before clearing, saved and SHA-verified the existing 64 MiB logdump in
  `run152-preparation/preexisting-logdump.bin`. Its hash/provenance is in
  `run152-preparation/manifest.json`.
- The five `ack-early-logcat.log[.1-.4]` files were individually copied,
  hash-verified, then removed on-device so the next early capture was fresh.
  Copies are in `run152-preparation/early-logcat-before-boot/`. No ANRs deleted.
- `run152-preclear.status` proves logdump zero-readback before RAM boot.
- Host observer ran nine minutes; at its end ADB was unavailable. USB reader
  was explicitly terminated, so there is no normal EOF/status completion.
- **Correction to earlier chat:** the USB capture is NOT empty. It contains
  **214206 bytes**, ending around kernel t=32.53 s. `run152-usb.log:1034`
  records secilc exit 0; `:1529-1535` starts service managers; `:1614` says
  fsck reported no error. It reached userspace. This is an incomplete capture,
  not proof of a kernel stall at its final line.
- Because the reader remained waiting and the user manually booted run150
  during this exchange, attribution of the partial USB bytes to the initial
  attempt versus the manual attempt is **not established**. Do not claim two
  reproduced outcomes from them.
- `run152-logdump.bin` and `run152-postboot/` do NOT exist. Persistent recovery
  never ran, and the manual boot may have overwritten the first attempt's slots.

### What is established in the manual boot

`run150-manual-snapshot-20261016/charging.log:1-5` shows both the Android health
HAL and `vendor.lineage.health.IChargingControl/default` registered. Lines
15-20 report charging status 2, level 96 and 4373 mV. Do not chase an absent
charging HAL as the blocker for THIS boot.

The snapshot's `logcat.log:6585` records `boot_progress_enable_screen` at
90037 ms; boot completion remained unset at 323.92 s. Rootless dmesg/pstore
and `debuggerd -b` were denied; corresponding failure logs are saved. No live
SF stack or late kernel cause was obtained by those commands.

Current logcat is dominated by repetitive FastRPC and audio errors. In a
44-second, 11457-record tail, ten FastRPC messages each appeared about 865
times (~76% combined), plus ~8% repeated audio-port errors. The tail showed
no new boot milestone/watchdog event. This is NOT proof FastRPC blocks boot.

### Historical ANR evidence recovered — stronger than the old hypothesis

Pulled **47 traces** from `/data/anr` using stock `su` before these boots:

- `anr/ANR-index.log`: per-file SystemServer PID and key frame counts.
- `anr/ANR-gpu-wait-excerpts.log`: selected PID 1104/1101 stacks with original
  file names and line numbers. Originals are beside these summaries.
- PID 1104 traces `anr_2026-10-09-10-26-36-263` (45 s watchdog subject) and
  `anr_2026-10-09-10-29-02-513` (191 s) repeat the graphics wait chain.
- SystemServer `android.display` waits in `BpSurfaceComposer::bootFinished`.
  SF's binder thread waits in `SurfaceFlinger::bootFinished` / `OnceFuture`.
  RenderEngine is in shader-cache priming -> `flushGL` -> libgsl timestamp
  wait; its kernel waiting channel is `adreno_drawctxt_wait`. The PID 1101
  trace also contains this pattern. Main being in Looper does not exonerate SF.
- This establishes a repeated WAIT CHAIN, not the kernel-side root cause.
  PID alone does not uniquely identify a run; historical run mapping still
  needs matching logs/build/process identities.

Upstream cross-check: current AOSP `SurfaceFlinger.cpp`, `bootFinished()`,
explicitly waits for `mRenderEnginePrimeCacheFuture`:
https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/services/surfaceflinger/SurfaceFlinger.cpp
The installed ROM reports Android **17 / API 37**. Earlier chat's assertion
that Android 13 sources matched this ROM was wrong. Main is corroboration,
not verified exact ROM source. The old section below's VINTF version
registration hypothesis is unsupported: examined servicemanager declaration
checks use package/interface/instance, not interface version. Do not patch the
manifest version on that hypothesis alone.

### Local evidence inventory added this session

All paths below are under `porting/artifacts/snapshot60/`:

- `stock-evidence-20261016-103115/`: stock logcat (4.48 MB), dmesg (1.17 MB),
  identity, properties, services and process lists; vendor health binaries,
  init RCs and VINTF manifests in its `vendor/` subtree. STOCK, not port logs.
- `retained-port-logs-20261016/`: 24 readable retained port log files plus
  `capture.tar`; includes the then-current early logcat and preserved run130,
  run133 and run134 directories. Not all files describe the same boot.
- `run152-preparation/`: preserved preboot partition and early logcat, manifest.
- `run152-session.log`, `run152-capture-host.log`, `run152-usb.log`,
  `run152-live/`, `run152-before-stock.log`, `run152-preclear.*`.
- `run150-manual-live-20261016/`: bounded observer samples, timeline, streaming
  `port-logcat.log` (12.2 MB at the last size check; capture subsequently finished).
- `run150-manual-snapshot-20261016/`: one-time logcat, identity, battery/service
  state, GPU access and recorded permission failures.

Added operational files: `porting/RUN152-test.md` (pre-test instructions, NOT a
result report) and `porting/logging/observe-gpu-boot.py` (read-only bounded
collector). Stock smoke test confirmed stock logs aren't labelled port; mocked
timeout/permission tests passed. No kernel tests or fixes claimed.

### Next steps — recover this boot before another test

1. Stop/wait for the manual observer and its logcat child; confirm no stale USB
   reader. Save final identity, uptime, process IDs, boot ID and boot-completion
   state. Do not clear any kernel evidence.
2. Ordinary `adb -s 2819f2320604 reboot` returns a RAM boot to stock. Confirm
   `uname -r` is 4.19 and `su -c id` succeeds before recovering the partition.
3. Use an UNUSED label such as **153** for the MANUAL boot's persistent recovery,
   documenting that the user booted run150 and did not preclear for this attempt.
   From `porting/artifacts/snapshot60/`:
   `bash ../../logging/pull-run-evidence.sh 153 boot-run150.img`.
   Hash-check the local 64 MiB against the device. Copy `/data/anr` and fresh
   early-logcat rotations into new manual-boot folders; never overwrite originals.
4. Read the recovered late kernel log for CP initialization/idle failures, SMMU
   faults and GPU completion/interrupt evidence, and correlate the new PID 1108
   ANRs. Lack of records or access is not evidence of absence.
5. Only then choose ONE targeted fix or diagnostic change. Keep real run150 as
   immutable base. Do not mix FastRPC ABI work, backlight policy and GPU changes.
   No new candidate image has been built or approved by evidence yet.

Read `REFERENCE-boot-testing.md` before the next cycle. This host is macOS,
pyserial 3.5 is available, and the USB reader enumerates macOS serial ports.
No SD card was detected; logdump is the primary durable kernel evidence path.
The worktree had extensive preexisting modifications/deletions; do not reset
them. These include deleted historical images, so preserve all remaining bases.

---

## Previous handoff — historical state at commit `017effda6`

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
