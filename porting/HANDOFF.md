# Handoff — tissot 6.12 port, update 2026-10-17

## Current source-only update — reset/TE pinctrl

Approved donor pinctrl fidelity change is applied to
`msm8953-xiaomi-tissot-mdss.dtsi`: reset GPIO61 has its own GPIO states,
active 8 mA/no pull/output-high and suspend 2 mA/pull-down. TE GPIO24
has separate active/suspend `mdp_vsync` states, both 2 mA/pull-down.
DSI0 selects both reset and TE groups for each state.

Android common 6.12's MSM8953 mux table and pinconf driver support these
settings directly; both inspected drivers are byte-identical to the local
versions. No pinctrl/GPIO driver API workaround was added.
Before/after host DT preprocessing/compilation passed. Resolved-phandle
comparison verified only the approved pinctrl changes, with all supply
topology unchanged and the same DTC warning categories.
Evidence: `artifacts/snapshot60/panel-pinctrl-source-check.json`.

No kernel/boot-image build, boot or device pin write was performed.
The supply-topology and panel-policy corrections below remain unbooted too.
Reset waveforms, panel completion, rendering and the reset cause are
unverified on hardware. Board-guard, audio and fingerprint work remain queued.

Follow-on board-guard audit found no further functional Tissot branch to
enable in the imported stack: remaining Tissot gates wrap an unconsumed
panel pointer; family gates wrap includes, while other runtime branches
belong to other boards. No config symbols were enabled.
Audio/fingerprint comparison found no corresponding donor machine/routing
or fingerprint drivers in this port. Mainline QDSP6/MAX98927 exist, but no
board sound-card links; the codec already uses reset GPIO descriptors.
Those functions require separately scoped integration, not mechanical
application of the remaining donor patches. They remain unimplemented.

## Current source-only update — panel supply topology

Removed the port-only DSI0 `vdd-supply = <&pm8953_l17>` binding from
`msm8953-xiaomi-tissot-mdss.dtsi`. Donor Tissot includes SKU3's explicit
deletion of this property. Read-only inspection of the running stock DT
confirmed it is absent; stock regulator_summary shows DSI0 consuming the
dummy supply, L6, LAB and IBB, with L17 held only by its deviceless consumer.
Run194's failed `vdd` enable was therefore on an operation absent from stock.
This does not establish why that RPM transaction timed out or run210 reset.

Normal `regulator_get()` dummy fallback remains supported in 6.12; no
transport or regulator-core workaround was added. Android common's RPM
transport is byte-identical to this port. Resource type/IDs and basic V0
request/KVP layouts agree with donor; no wire-protocol cause was established.
The upstream shared-completion/late-ACK limitation is not diagnosed here.

Before/after host DT preprocessing and compilation passed. Resolving
renumbered phandles showed only the DSI0 VDD-to-L17 connection removed;
L6/LAB/IBB and every other semantic DT property are unchanged.
Evidence: `artifacts/snapshot60/panel-supply-source-check.json` and
`panel-supply-stock-{summary,properties}.txt`. No new kernel/boot image was
built and no device boot or regulator write was performed.
Always-on constraints, voltage settings, RPM errors and pinctrl remain
unchanged; the prior panel-policy fix is also still unbooted.

## Current source-only update — panel policy, 2026-10-17

**Approved panel-policy correction is in source only: NOT BUILT OR BOOTED.**
No new device observation or reset-cause conclusion follows from this patch.
Run210 below remains the latest device baseline; existing images do not
contain the panel-policy change.

- `drivers/video/fbdev/msm/mdss_dsi.c`: move Tissot suspend reset/power
  assignment out of the command-line-only, compile-gated finder into
  `mdss_dsi_config_panel()`, after successful node selection and before
  panel initialization. Both command-line and DT preferred-panel selection
  now use the actual selected node via `of_node_name_eq()`, not its
  human-readable panel-name property.
- Retain the runtime Tissot condition and both flags' mappings:
  TD4310=1, OTM1911=2, FT8716=3. Unknown selected Tissot nodes reset both
  flags to zero; no selection and non-Tissot selection do not reassign them.
- Reset waveform/timings, regulator flags/voltages, clocks and pinmux are
  unchanged. No kernel build, packaging, boot or device operation
  was performed for this source-only update.
- Added `logging/test_mdss_panel_policy.py`, a focused host regression
  extracting the actual C selection/configuration functions and OF name
  comparison. Covers command-line and DT fallback, mappings/defaults,
  stale flags, unresolved names/controller fallback, no-panel cases, policy
  visibility before init and runtime-machine isolation with the old config
  gate disabled/enabled. **Host regression passed**, and failed against
  the original functions. Validation command from repo root:
  `python3 porting/logging/test_mdss_panel_policy.py`.

The inherited globals still represent shared panel policy; this patch does
not redesign ownership. Hardware sequencing, panel completion, rendering
and run210's reset cause remain UNVERIFIED. The host check cannot establish
electrical behavior. See `REFERENCE-rktdnt-tissot-history.md`, section 1.
No build/boot is authorized; request separate approval before either.

## Latest device handoff — run210, 2026-10-17

**Built and RAM-booted the two approved KGSL 6.12 compatibility fixes.
The phone reset and returned to rooted stock; rendering and reset cause
remain UNVERIFIED.** No partition was flashed. No further build/boot is
authorized by this result.

Final serial `2819f2320604`, stock kernel
`4.19.325-cip136-st20-perf-mglru-next-g5835eacd666d`, boot_id
`a21fd043-16cd-43ed-a8b3-ec5768722bc7`. Observers/capture have stopped.
Device logdump holds run210, archived and device-hash-verified as
`artifacts/snapshot60/run210-logdump.bin`, SHA256
`4fe66152b7b7c123e7c7670639dd6b78ddbcdfca0818831dc415f33ca8bdeb60`.
Verify that archive/hash before any later clear.

### Build and tested changes

Source, host regressions and run210 result metadata: commit `5f5f8ccce`.

- `kgsl.c`: use 6.12 reservation-locking DMA-BUF map/unmap wrappers;
  unmap successful mappings on failed imports and publish metadata only
  after SG validation. Caller retains its DMA-BUF reference on failure.
- `secure_buffer_compat.c`: use a fresh local `u64` source VMID bitmask
  per SG extent, validate inputs, and preserve donor `-EADDRNOTAVAIL`
  quarantine semantics after failed SCM assignment. Caller VMIDs are
  not overwritten. Secure-context enablement remains unchanged.
- Both behavioral host checks failed before and passed after, including
  ASan/UBSan. Secure adapter strict checkpatch passed; two focused reviews
  found no issues. Device execution of DMA-BUF imports or secure-memory
  transfers is not established by this boot's evidence.
- `/tmp/ack-run164-source` had disappeared. Restored 87,556 source files
  at the same path, preserving mtimes; checksum-compared all restored
  files against the repo. Kept `out/` and its merged config; no clean.
  Rust availability and pinned clang/Rust/bindgen verified.
- `boot-run210.img` SHA256:
  `c59807e72412aa2ef939df881952dbf584af7d12524f1ecfd42a31c9f0ee1025`.
  Real run209 base. Embedded config, DTB, compressed ramdisk, init and
  command line match run209; exactly one inherited `panic=60`.
  DTC emitted reg/address-cell and prerequisite warnings, but DTB bytes
  are unchanged. Same eight BTF duplicate-ID warning categories and
  inherited duplicate-genfscon package warning.
  See `run210-build.log`, `package-run210.json`,
  `run210-source-verification.json`, `run210-build-verification.json`.

### Device result and capture limits

- Prior run209 device/local logdump SHA matched before clear; zero
  readback verified. Early logcat archived and hash-verified before
  removing only its diagnostic output. Both fastboot operations returned
  OKAY; USB captured fresh `6.12.93-4k #7` execution.
- Zap authentication, secure-mode-switch call, post-start and GPU-start
  all returned zero. Stages 16-22 prove hwcomposer thread PID680 completed
  first open/process setup; final open returned zero at 42.088811858 s.
  Initial idle work and ACTIVE/NAP transitions also returned zero.
- Stages 11-15, 29-30 and reserved31 are zero. Recording is asynchronous
  best-effort: this does not prove no submit/snapshot/slumber path ran.
- USB text ends at 41.742269 s; logdump text prefix at 41.504700 s.
  Both entire 1 MiB snapshot payloads, including dmesg areas, were
  inspected: CRC-valid samples at 39.611/41.696 s, no valid panic/oops.
  Latest periodic header is 41.788425087 s, its text ends 41.674714 s.
  No panel cold/completion diagnostic or DSI status triple was captured;
  panel completion cannot be inferred.
- No ACKRESET1 record. Four-second ADB observation saw no 6.12 window.
  New stock boot observed at host elapsed 167.960 s; stock dmesg/logcat
  saved immediately. PMIC reports Hard Reset/cold boot and PS_HOLD,
  without naming the reset caller. Elapsed time does not prove panic.
- `run210-postboot/ack-early-logcat.log` is 85,476 B, device-hash-verified,
  no NULs; ends before graphics initialization.
- User's run210 panel observation: **"backlit blink reset"**. This confirms
  backlight/blink before reset, not a rendered frame or the reset cause.

Next diagnostic boundary remains post-open ioctl/mmap/userspace
initialization and independent panel completion. Do not infer a rendering
fix or reset cause from the blink or missing
records. Ask before new instrumentation or another build/boot.
Summary: `artifacts/snapshot60/run210-summary.json`.


## Previous handoff — run209, 2026-10-17 (historical)

### Next session: start here

Phone returned to rooted stock 4.19 after the approved run209 RAM boot.
Serial `2819f2320604`, boot_id `88133e7c-f87f-46ed-a1d2-68741776e2d0`.
Capture and observation have stopped. Device logdump holds run209; its
64 MiB archive is `porting/artifacts/snapshot60/run209-logdump.bin`, SHA256
`7d35b50cee75ded5fb926c6eaf1b7e069c6853c5b40b2769c2109cd7f816d648`.
Verify that hash before any later clear.

The first-open/idle diagnostics and asynchronous stage writer are now
**BUILT AND BOOTED in run209**. Older unbuilt notes below are historical.
Source commit `e83d1d5fe`; build/package verification commit `a41604a6f`.
`boot-run209.img` SHA256:
`64c4e1a82d47f06cdca6a35c43a1708d1d6ecf23d021b64573f77f29876dae1e`.
Incremental build in `out/`, pinned tools and `CC=clang`; embedded config,
compressed ramdisk, init, DTB and command line match run208. Exactly one
`panic=60` is inherited. Same eight BTF duplicate-ID warning categories;
the packager's duplicate genfscon warning concerns inherited base records.
The four diagnostic sources in `/tmp/ack-run164-source` were synced and
verified against the repo. Re-check before any later build.

**Run209 recorded more progress, but the reset cause remains UNVERIFIED.**
`run209-zap-stages.txt:6-37` decodes all 32 slots. Authentication completed
at 47.043165658 s; the secure-mode-switch call returned zero at
47.043598471 s, as in run208. This is a function result, not a direct
readback of the protected register. GPU startup and post-start returned
zero. New stages 16-22 all carry ret=0 and PID 678 (hwcomposer): first
start, ACTIVE change, active-count put, device open, process setup and
the final `kgsl_open` success-return marker at 47.044159148 s.
Stages 23-28 record successful first idle work, ACTIVE (AWARE=32 to
ACTIVE=2) and NAP (ACTIVE=2 to NAP=4) transitions. Process setup/final
open sample state NAP=4. The asynchronous writer persisted these records
after the GPU caller queued them; that does not establish later progress
or rule out storage effects elsewhere.

Slots 11-15 (first submission/snapshot/fallback), 29-30 (SLUMBER) and
reserved 31 are all zero. With asynchronous best-effort recording, absence
does not prove a path never ran. UCHE faults, GPU hangs and rendering after
startup remain unverified. The locked-register CPU snapshot fallback
hazard remains; no persisted marker identifies it as this reset's cause.

Capture limits and reset evidence:
- `run209-usb.log:3559-3562`: panel cold bring-up and the same three DSI
  status errors at 41.748388-41.748477 s. No `dsi_on: done` was captured.
  USB continues beyond those errors through 46.447013 s (line 3580), then
  the ACM reader disconnects. Thus the panel errors are not themselves
  the last captured kernel activity. Panel completion remains unverified.
- Both entire 1 MiB snapshot payloads were inspected, including dmesg
  areas. Both headers/payload CRCs validate (39.674/41.723 s), with no
  valid panic/oops record. Latest periodic tail header is 46.822961335 s,
  but its text ends at 41.719660 s; the USB stream contains later text.
  Stage records at 47.044 s are later still. Why captures stop is unverified.
- No ACKRESET1 record. QSEE ring last returns at 38.404299 s; this alone
  does not identify what subsequently reset the board. Stock dmesg and
  logcat were saved immediately on ADB return, about 168 s after the
  bootloader reboot request. PMIC reports Hard Reset/cold boot and
  PS_HOLD, without identifying the reset caller. `panic=60` and elapsed
  time do not prove a panic occurred.
- User panel observation: **backlit, then completely black**. No 6.12 ADB
  window was observed at four-second cadence. New early logcat is archived
  and hash-verified in `run209-postboot/`; its tail is incomplete/NUL-filled.
  Prior early logcat was preserved in `run209-preboot/` before clearing.

Do next: inspect the paths after successful first open (ioctl/mmap and
userspace initialization), while checking panel completion independently.
Do not diagnose a cause from a missing stage or this single run. Any new
instrumentation needs the user's exact-edit confirmation; **ask before
another build or boot**. Keep builds incremental in `out/`, preserve real
base images, and find observers by PID. Keep committing without co-authors.

## Previous handoff — run207-run208, 2026-10-17 (historical)

### Next session: start here

Last confirmed device state: rooted stock 4.19, serial `2819f2320604`,
boot_id `92f04e57-964d-46fa-b847-c60860996ba4`. No capture/observer remains.
Device logdump holds run208, archived in `porting/artifacts/snapshot60/`.
Before clearing it, verify the device SHA equals `run208-logdump.bin`:
`3b7ceabe525a6a3f4e09e165bee8bee46a272613ee81ce802617f4a40316b9ab`.

Commits:
- `c9a84d881`: checkpoint of the previously uncommitted run201-206 work,
  run208 startup diagnostics, supplied handoff and package reports.
- `a6684a45d`: **new first-open/idle diagnostics, NOT BUILT OR BOOTED**.
  This is newer than every existing image and the staged build source.
- The asynchronous stage guard described below is also **NOT BUILT OR
  BOOTED**. Include it when comparing the repo against the staged tree.
- Keep committing completed changes, as requested by the user. No
  Assisted-by or co-author trailers.

What run208 actually recorded: zap authentication, secure-mode switch,
post-start and GPU startup all returned zero. Stage 10 persisted at
47.556380762 s. No first-submission or GPU-snapshot/fallback marker
persisted. **The subsequent reset cause is UNVERIFIED.** The next diagnostic
target is first-open completion, process/page-table setup and initial idle
or power transitions. Missing records do not prove those paths never ran.

Do next, in order:
1. Read `REFERENCE-boot-testing.md` before any boot. **Ask before building
   or booting**; neither is authorized merely by this handoff. Run209 image
   and package report did not exist at handoff; re-check before using 209.
2. Before the next authorized build, sync these four files from the repo
   into `/tmp/ack-run164-source`, then compare all tested/modified sources:
   `drivers/gpu/msm/adreno-zap-compat.h`, `drivers/gpu/msm/kgsl.c`,
   `drivers/gpu/msm/kgsl_pwrctrl.c`, `fs/pstore/ram.c`.
   The staged tree currently carries run208, not `a6684a45d`.
3. Build **incrementally in `out/`**, preserving its merged config. Use the
   pinned Rust/bindgen environment in `BUIL_TISSOT.md`, with `CC=clang`
   and `/usr/bin` first in PATH. Spelling it `CC=/usr/bin/clang` triggered
   unrelated recompilation during run208; that invocation was stopped and
   the build completed with the original `CC=clang`. No clean was run.
4. Package from the real `boot-run208.img`, retaining its ramdisk, init,
   DTB and **`panic=60`**. The user specifically requested 60 seconds before
   reboot on panic. Do not append a second panic token. Verify embedded
   config, payload hashes and header fields before asking to boot.
5. For an approved boot: archive early logcat, verify prior logdump SHA,
   clear and prove zero, start one reader and four-second ADB observation.
   After any reset, save stock PMIC reasons immediately, then pull evidence.
   Find observers by PID; `pgrep -f` also matches the calling shell.
6. Decode **32** stage slots at `0x3f01000` for the next image, plus both
   snapshot payloads even if a header is torn. Existing images through
   run208 only write slots 0-15. New bank ends at `0x3f05000`, before the
   QSEE ring at `0x3f10000`; witness/reset offsets are unchanged.

### New diagnostic map — committed, unbuilt

The 40-byte little-endian record is unchanged: `<QIiQQQ` = magic, stage,
signed ret, uptime_ns, mem_phys, size. Magic is `0x454741545350415a`.
Slot stride is 512 bytes. Slots 0-15 retain their run208 meanings. New
slots 16-30 record the first visit per stage; slot 31 is reserved.

| Slots | Event |
|---|---|
| 16 / 17 / 18 | First-open: GPU start returned / ACTIVE change returned / active-count put returned |
| 19 | `kgsl_open_device` returned to `kgsl_open` |
| 20 / 21 / 22 | Process setup entered / returned / final `kgsl_open` return |
| 23 / 24 | Idle work entered / returned |
| 25 / 26 | ACTIVE transition entered / returned |
| 27 / 28 | NAP transition entered / returned |
| 29 / 30 | SLUMBER transition entered / returned |

For slots 16-22, `mem_phys` carries PID and `size` carries current KGSL
state. For slots 23-30 they carry current/requested state, respectively.
These are software values, not register reads. State bits:
INIT=1, ACTIVE=2, NAP=4, SUSPEND=16, AWARE=32, SLUMBER=128, RESET=256.
Match PID/timestamps: first records from different stages need not belong
to the same open or idle attempt. The original ignored ACTIVE-change
result and other error handling are preserved; the result is now recorded.

Cross-checks: [AOSP kgsl.c](https://android.googlesource.com/kernel/msm/+/0ba0fc238751acb47afdb023edb5152111fc2ca0/drivers/gpu/msm/kgsl.c)
has the same first-open start/ACTIVE/active-count-put ordering;
[Linux block documentation](https://origin.kernel.org/doc/html/v6.12/block/writeback_cache_control.html)
describes FUA completion durability.

Host harnesses exercised the actual open, first-open, idle, state-change,
record-helper and stage-backend functions: success, error cleanup, ignored
ACTIVE error, EBUSY requeue, model/zap gating, repeat open, one-shot races,
metadata, errno, FUA/SYNC flags, slot 31 acceptance/32 rejection and QSEE
separation passed. Strict checkpatch: zero errors, warnings or checks.
Kernel compilation and device behavior of these additions are unverified.
Those checks covered the synchronous version in `a6684a45d`; see the
additional queue checks below for the current source.

### Storage-stall guard — asynchronous stage recording, unbuilt

`fs/pstore/ram.c` now copies all GPU stage records into a preallocated
32-entry FIFO under a short spinlock. An ordered workqueue performs the
existing FUA writes after releasing that lock. GPU callers neither take
the witness mutex nor allocate or wait for storage. The stage helper in
`adreno-zap-compat.h` also no longer prints synchronously. The record
format, slot offsets and event timestamps are unchanged; worker console
lines report `DIAG stage slot=... write_ret=...` after each write returns.

This guards the stage caller against waiting on its own diagnostic I/O;
it does not repair stalled storage or establish run208's reset cause.
Queue success means accepted into RAM, **not persisted**. A reset can lose
any recent stages, including authentication. Full queues return `-ENOSPC`,
and unavailable workers return `-ENODEV`; the diagnostic caller skips the
record. The first-visit guard is still consumed by a rejected attempt.
Missing records therefore cannot establish that a path was not reached.
There is no synchronous fallback, retry or panic-time queue flush.
Runs through run208 used the earlier synchronous writer: their recorded
evidence and interpretation are unchanged.

Removal disconnects producers before draining accepted work; an in-flight
storage operation can still delay removal. Witness, QSEE and snapshot
writers remain synchronous and share storage resources. This change
does not bound their waits or eliminate system-wide storage effects.

`python3 porting/logging/test_ramoops_stage_queue.py` compiles the actual
queue/worker/lifecycle functions with pthread workqueue and storage stubs.
It passed blocked-storage/non-waiting producer, full/unavailable queue,
slot/length bounds, owned copies, FIFO/wrap, write-error continuation,
allocation failure, and concurrent teardown checks. This is host proof,
not kernel compilation or device validation. Upstream cross-check:
[Linux 6.12 workqueue documentation](https://www.kernel.org/doc/html/v6.12/core-api/workqueue.html)
specifies `alloc_ordered_workqueue()` for ordered execution.

### Run207 — unchanged run206 image retried

`boot-run206.img` SHA `c595cfdf543335b63ad0c7449832f6fe0653a4c66dad7a55da260ec606990fe4`.
Phone reset and returned to stock. All seven zap stages returned zero;
`run207-ramoops-slot1-seq20-ns41661687379-snapshot-console.log:3491`
reports authentication success, and line 3497 reports
`DIAG secvid: zap_loaded=1 ret=0 trust_cntl=00000000` at 41.410971 s.
The trust value is a placeholder, not a hardware read. Console text survives
through 41.639321 s; no recorded UCHE/GPU hang/SEA in that captured window.
Both snapshot payloads were inspected. Run206's absent zap records did not
repeat, but neither run's reset cause is established.

### Run208 — startup completes, later reset unverified

Image SHA `e0d594c7db1c39e925c96fcd09e8eb60a98dcf4d95d0ce795fa9642a0ec0b494`.
Built incrementally in `out/`, packaged on the real run206 base. Config,
DTB, ramdisk and init were byte/hash checked against run206; only the
diagnostic kernel and appended `panic=60` changed. Build and package
reports are in `snapshot60/`. The BTF duplicate-ID warnings also occurred
in run206. Run208 itself includes stages 7-15, not the new 16-30 additions.

Primary result: `run208-zap-stages.txt:12-16` decodes stages 6-10 from the
separate logdump bank: authentication at 47.547933522 s, secure-mode switch
at 47.551572324 s, post-start return at 47.554986856 s, startup completion
at 47.556380762 s, every ret=0. Slots 11-15 are entirely zero. This does
not establish that the first-submit or snapshot paths were never reached.

Capture limit: snapshot headers are CRC-valid at 41.635/43.872 s; latest
periodic tail header is 47.371510970 s, but its **text ends at 42.259087 s**.
The later durable stage records therefore carry the GPU progress that
the console captures lack. Both raw snapshot payloads were inspected;
no retained reset/panic record explains the death. QSEE ring ends with a
returned keymaster call at 38.893939 s; witness canary=35, quiet=0.

**Where the run208 console stops: panel DSI errors.** The last text in both
run208 payloads is the panel cold bring-up followed by three error-IRQ lines
on CPU0 (`run208-printk-tail-slot0-seq21-ns47371510970-periodic-printk.log`,
end of file):
`[42.259026][T671] DIAG dsi_on: ctrl=0 cold bring-up`,
`[42.259039][C0] mdss_dsi_fifo_status: status=44441000`,
`[42.259069][C0] mdss_dsi_ack_err_status: status=10000000`,
`[42.259087][C0] mdss_dsi_timeout_status: status=1`.
`dsi_on: done` never appears. Runs 201/202/205/207 have none of these lines
and log `dsi_on: done ... rc=0` around 41.4 s. The same triple is in
`run194-logdump.log` and `run196a-logdump.log`, and both still reached
`dsi_on: done`, so on its own it is an intermittent panel bring-up error,
not a reset cause.
- The kernel kept running after console text stopped: snapshot headers
  at 43.872/47.372 s, stage records at 47.53-47.56 s. More than 5 s without
  any new console line during init is abnormal. Console capture is
  unreliable after 42.259 s in run208; the stage records are the only
  evidence past it. Why the console stopped is **not established**.
- GPU start came ~6 s late (stage 0 at 47.527 s vs 41.4-41.6 s in run205/207).
  T671 (hwcomposer, the kgsl opener) was inside `dsi_on`, so one
  **unverified** explanation is a ~5 s panel-on timeout before the GPU
  open. Matches the run208 panel observation (backlight only, then black).
- When decoding the next run, grep for `mdss_dsi_.*_status` and check that
  `dsi_on: done` is present before treating a GPU-side record as the last
  activity.
- The new `a6684a45d` stage writes are synchronous FUA I/O issued under
  the KGSL device mutex (`kgsl_open`, `kgsl_pwrctrl_change_state`). If the
  logdump I/O stalls, they stall the GPU path too. The later asynchronous
  guard above addresses this stage-writer risk in source only; neither
  version of the new first-open/idle diagnostics has been built or booted.

User observation: run208 showed backlight only, then became completely
black. The user also reported a panel blink before resetting during the
preceding investigation. Run206 observation was fastboot splash off,
backlight on, fully black, then dim backlight.

Stock returned roughly 168 s after the run208 reboot request versus 104 s
for run207. This is consistent with a 60-second panic delay, **not proof
that a panic occurred or identification of its cause**. Stock PMIC reasons
were saved immediately in `run208-stock-pon.txt`: Hard Reset/cold boot and
PS_HOLD, as in run207; they do not identify the reset caller.

Residual hazard unchanged: CPU snapshot fallback reads locked 0xf400 after
zap authentication. Run208 has no persisted snapshot-entry/fallback marker;
do not present that hazard as this run's diagnosed cause. UCHE/rendering
outcome remains unverified because no first-submission record survived.

## Previous handoff — run202-run206, 2026-10-17 (historical)

### Next session: start here

State at hand-off: phone on stock 4.19 with root (serial 2819f2320604,
boot_id `bd02ae0a`), no capture/observer running, run205 + run206 evidence
pulled into `snapshot60/`. Device logdump still holds run206 (archived as
`run206-logdump.bin`). Everything from runs 201-206 is **uncommitted** in the
working tree; `/tmp/ack-run164-source` matches it (cmp-verified for
`adreno.c`; re-check all modified files before building).

What is established (details below):
- The A506 zap shader **loads and authenticates** (run205: all 7 ZAPSTAGE
  records, every ret=0, `auth_and_reset=0`).
- run204/run205's reset was **our DIAG CPU read of `RBBM_SECVID_TRUST_CNTL`
  (0xf400) after the zap load** -> SEA -> PANIC_ON_OOPS -> reset. run206
  removes that read when `zap_loaded`.
- run206 failed **differently** and the cause is **unverified**: no persistent
  record after 39.55 s, no ZAPSTAGE at all, reset ~35 s later than run205.

Do next, in order:
1. Ask the user what the panel showed during run206 (not yet answered).
2. With the user's OK, **re-boot `boot-run206.img` unchanged** (sha256
   `c595cfdf...0fe4`) to tell an intermittent hang from a systematic one.
   Procedure as BUIL_TISSOT.md: verify device logdump sha == archived
   `run206-logdump.bin` before `clear-logdump.sh`; observer + fastboot
   capture as in `run206-host-timeline.log`; file it as run207 (copy/symlink
   not needed, pull script takes the image path: `pull-run-evidence.sh 207
   boot-run206.img`).
3. **Immediately after any reset**, once stock is up, save the stock PMIC
   reason: `adb shell "su -c 'dmesg | grep -i -E \"power-on reason|power-off
   reason\"'" > runNNN-stock-pon.txt` (run206's is saved; run205's was lost).
4. Decode: ZAPSTAGE slots at `0x3f01000` (16 x 512 B); snapshot slots at
   `0x3c00000`/`0x3d00000`-area via the pull report. **If a slot is reported
   torn (magic 0), still read its payload** (`logdump.bin[slot_off+4096 :
   +1 MiB]`) — run205's crash was only visible there. Grep for `DIAG zap`,
   `DIAG secvid` (now prints the CP_SET_SECURE_MODE switch `ret`), `SEA`,
   `Internal error`, `UCHE`, `GPU hang`.
5. If run207 gets past the GPU start: report the `DIAG secvid ... ret=`
   value, UCHE/GPU-hang counts and ask for the panel. The open question is
   whether leaving secure mode via the zap shader removes the UCHE fault.
6. Known residual hazard: `a5xx_legacy_snapshot_registers` (used when the
   crash dumper does not complete, incl. the silent SMMU-stalled return in
   `_a5xx_do_crashdump`) reads 0xF400 over AHB and would SEA after a zap
   load. Guard it if a hang snapshot ever takes that path.

Rules: don't boot without asking; `pgrep -f`/`pkill -f` on the observer
command line also matches your own shell (kill by PID after `ps -o
pid,ppid,cmd`); builds incremental in `out/`, no clean build.

**run202 — full stock GPU regime, fault unchanged.** `qcom_iommu.c` GPU bank
back to ARM_64_LPAE_S1 ias=39 (reverts run199's misread) and
`KGSL_MMU_64BIT` re-enabled in `adreno.c` (stock is arm64). Readback:
`KGSL_MMU_64BIT enabled`, `init_domain ... ias=39 aarch64=1`, `addr_mode=1`.
The UCHE fault is identical: first trap `addr=000000050001f000` (offset 0 of
a 4 KiB memtype-9 `gl` buffer), `cp_status=80423c68`, IB2 again at `...0140`
(userspace HLSQ state upload: `HLSQ_CONTROL_0_REG`, `HLSQ_UPDATE_CNTL`
`0x020fffff`), 22 hangs in ~100 s, panel lit black, screencap identical.
Leaf PTE `006000003c00fe43` correct. **The fault is independent of the whole
MMU/VA family** (format, ias, 32/64-bit, PTE bits, impl-defs). Also seen: kgsl
sysfs nodes are labelled generic `sysfs` (port path `/devices/platform/soc@0/
1c00000.gpu/...` misses vendor genfscon) - `gpu_model` unreadable; GL driver
falls back. Not the fault; fix later.

**Lead: the zap shader was never loaded.** `adreno-zap-compat.h` returned
`-ENXIO` and the a5xx path was gated on `mmu.secured` (false only because the
port has no gfx3d_secure bank). Stock loads `a506_zap` via PIL (PAS id 13,
`/vendor/firmware/a506_zap.*`, `gpu_region` 8 MiB in 0x80000000-0x90000000);
mainline msm8953.dtsi has a `zap-shader` child (`zap@81800000`, 8 KiB; the
only PT_LOAD segment is 0x1444 B) and `a5xx_hw_init` uses it to leave secure
mode. Without it the GPU likely stays secure - **unverified**.

- **run203** (zap load via mainline sequence, non-fatal fallback): no output
  at all (0 B USB, logdump untouched) - most likely the known intermittent
  RAM-boot hang.
- **run204** = retry of `boot-run203.img` (filed as 204: pull script needs a
  numeric run): port reached userspace (USB to 40.80 s), last snapshot
  39.55 s, **board reset between 40.8 and 41.6 s = first GPU start** (run202:
  41.3 s), no ACKRESET record -> TZ/watchdog-level reset in the zap path.
- **run205** (`boot-run205.img`, sha256 `ea7907ca...2f33`): same load split
  into steps with a FUA stage record before/after each SCM call
  (`ramoops_stage_write`, logdump `0x3f01000 + stage*512`, magic
  `"ZAPSTAGE"`, struct in `adreno-zap-compat.h`). Stages: 0 enter, 1 fw
  loaded, 2/3 pas_init (init_image + mem_setup), 4 segments copied, 5/6
  auth_and_reset. The highest stage present names the fatal step.
  Decode: read 512-byte slots at `0x3f01000` of `run205-logdump.bin`.

**run205 result — the zap load WORKS; the reset was our own DIAG read.**
Booted 15:05 (logdump zero-verified pre-boot), reset at 41.6 s, back on stock
(boot_id `c8a450af`). All 7 ZAPSTAGE records present, every `ret=0`
(41.598-41.622 s, `mem_phys=0x81800000 size=8192`): init_image, mem_setup,
segment copy and `auth_and_reset` all succeed. The console up to the reset
survives in the *torn* snapshot slot 1 (seq 20, header magic 0, payload
intact; extract `logdump.bin[63967232+4096 : +1 MiB]`): `zap ... 
auth_and_reset=0`, `ME_INIT submit ... zap_loaded=1`, then
`SEA: ESR=96000210 far_pa=0x1c3d000` in `readl_relaxed <- adreno_regread <-
adreno_set_unsecured_mode <- a5xx_rb_start`, x21=`0xf400` =
`A5XX_RBBM_SECVID_TRUST_CNTL`. That is the run203 DIAG readback, executed
after `adreno_switch_to_unsecure_mode`; `PANIC_ON_OOPS=y` + `panic=1` turned
the Oops into the board reset (run204 is the same image, same 41 s reset).
After authentication TZ blocks CPU access to that register (drm/msm
a5xx_hw_init comment: "access to the RBBM_SECVID_TRUST_CNTL register will be
blocked and a permissions violation will soon follow"; runs <=202 wrote it
fine pre-zap). Stock (`oc-test` adreno.c 2027) and drm/msm never touch it from
the CPU when the zap is loaded. Not yet known: whether CP_SET_SECURE_MODE 0
itself completed (its ret was never printed) and whether leaving secure mode
changes the UCHE fault.

- **run206** (`boot-run206.img`, sha256 `c595cfdf...0fe4`, built on
  `boot-run205.img`; ramdisk/init/cmdline/embedded config identical, only
  `adreno.o` rebuilt; NOT booted): readback skipped when `zap_loaded`; the
  `DIAG secvid` line still prints `ret` (switch result). Residual risk: on a
  hang, `a5xx_legacy_snapshot_registers` (used only when the crash dumper does
  not complete) reads 0xF400 over AHB and would SEA the same way; runs
  200-202 never hit "Crash dump timed out", but the SMMU-stalled early return
  in `_a5xx_do_crashdump` also falls back silently.

**run206 result — different failure, cause UNVERIFIED.** Booted 15:11:42
(logdump zero-verified; pre-clear sha matched archived run205 copy), back on
stock (boot_id `bd02ae0a`). USB normal to 41.10 s (`gpu`, `surfaceflinger`
started, nothing abnormal). But **nothing persistent after 39.55 s**: no
snapshot seq 20 (due ~41.6 s; slots hold seq 18/19 only), **no ZAPSTAGE
record at all** (stage 0 was at 41.609 s in run205), QSEE ring identical to
run205 and ending at 37.8 s. Phone off adb for 132 s vs 96 s in run205, and
the USB reader disconnected at host 93.7 s vs 59.0 s -> the port stayed
powered ~35 s longer before resetting. Pattern = whole-system stop (or
logdump I/O stall) between 39.55 s and the GPU start, then a delayed
reset, not an Oops. Stock PON after the reset (`run206-stock-pon.txt`):
"Hard Reset ... 'cold' boot", power-off "PS_HOLD" - no run205 baseline, so
not distinguishing. The run206 change only affects code after stage 6, and
stage 0 never appeared, so nothing ties this to the change - but that is
inference from absence. Next: repeat `boot-run206.img` once to tell
intermittent from systematic; capture stock PON after every reset.

Tooling notes: a torn snapshot slot (header magic 0) still carries a readable
console payload - run205's crash was only visible there. `pgrep -f` on the
observer command line also matches the calling shell; filter by PPID.

Builds are incremental in `out/` (user request; `out-run201/` is the older
tree). Staged source `/tmp/ack-run164-source` must `cmp` the repo.

## Previous handoff — run201, 2026-10-17 (corrects run198/run199)

**run201 result: no change.** Panel lit black (user observation), 149
`GPU hang detected`, first UCHE trap `0x139000`, screencap byte-identical to
run200 (`d1d094a5...`). Image `boot-run201.img` sha256 `90a80267...9a26`,
built on `boot-run200.img`; ramdisk/init/cmdline unchanged, kernel + DT only.
Observer stopped early at ~160 s uptime after the panel verdict
(boot_completed=1); logdump CRC-valid through ~201 s.

What run201 tested and what it showed (`run201-logdump.log`):

- **CAF's SMMU impl-defs and ACTLR.** 4.19 CAF arm-smmu writes
  `attach-impl-defs` (`msm-arm-smmu-impl-defs-8953.dtsi`) and the GPU bank
  ACTLR on every SMMU power-up; mainline qcom_iommu writes neither. kgsl now
  writes them (`_apply_impl_defs`, `kgsl_iommu.c`). Readback before the write:
  9 of 10 impl-defs **already** at the CAF value (firmware sets them); `0x6000`
  is the micro-MMU halt/status register, mismatch meaningless. ACTLR was
  `0x3` and is now `0x70000000` as on CAF — **no effect** on faults. Closed.
- **Real leaf PTE** for the trapped buffer (walker fixed; run200's walker
  indexed by page and kept bit 55, so its output was garbage):
  `va=139000 lvl=3 desc=006000002a37de43` = page, AttrIndx 0 (NC), AP=1,
  SH=OS, AF, nG, XN — the same bits CAF `prot_to_pte`/`init_pte` produce.
  The SMMU leg (TTBR0 identity, table, leaf attributes, impl-defs) is clean.

**CORRECTION — stock is NOT 32-bit.** Item 2 of the run199 handoff below says
"stock CAF 4.19 is 32-bit so the A506 never enters" 64-bit mode. Wrong: the
stock kernel is `aarch64`, `CONFIG_64BIT=y`, and surfaceflinger is a 64-bit
ELF (checked live on the device, 2026-10-17). So on stock
`adreno_support_64bit()` is true (A506 has `ADRENO_64BIT`,
`oc-test/drivers/gpu/msm/adreno-gpulist.h`), KGSL sets `KGSL_MMU_64BIT`,
programs every `*_ADDR_MODE_CNTL=1`, reports bitness 48, and places 64-bit
processes' VA at `0x500000000+`. Item 3 is also wrong: CAF picks
`ARM_64_LPAE_S1` whenever the SMMU supports AArch64 (`oc-test` arm-smmu.c
2547-2568, and stock dmesg prints `AARCH64 is supported for
...gfx3d_user`); `qcom,use-3-lvl-tables` only caps ias at 39. Commit
`0fc24c807` (ARM_32_LPAE_S1, ias=32) therefore moved *away* from stock.

**The port has never run stock's complete GPU regime**: ARM_64_LPAE_S1 ias=39
**together with** `KGSL_MMU_64BIT` and 64-bit address mode. run187/198 had the
format without 64-bit; run185 had 64-bit (CP-init failed 28x with real
translation faults on globals around `0xfc0a8000-0xfc0c61e0`, inside
`capturescript_regs`), and is the starting point. Next: understand run185's
global TFs, then run the full stock regime.

## Previous handoff — run199, 2026-10-17

Three defects found today (display bring-up, GPU address mode, page-table
format); the visible-display goal is still open and the reason is now known
precisely. All three fixes are committed in `4d4fcc1`.

**1. The display bring-up was broken and is fixed.** run194's logdump named it:
`mdss_dsi_panel_power_on: failed to enable vregs for PANEL_PM` ->
`mdss_dsi_on:Panel power on failed. rc=-110` -> `mdss_mdp_video_display: intf #2
link ready error (-110)` -> `mdss_fb_open: can't turn on fb0! rc=-110`. The
panel `vdd` rail is an RPM-served pm8953 LDO whose enable request is not
acked, so the RPM write returns `-ETIMEDOUT`. CAF treats that as fatal and
aborts `mdss_dsi_on()` before the PHY, clock source or DSI controller are
touched. The bootloader has already supplied the rails, so the abort is wrong;
run196 makes it non-fatal. run196 then reads
`DIAG dsi_on: done ctrl=0 rc=0 state=0x4 pwr=1 clk_rate=802589760` with **0**
`turn on fb0` and **0** `link ready error` in the whole log. The video bring-up
path is byte-identical to CAF 4.19 and the byte clock is exactly
`1148*1942*60*24/4 = 802,589,760`. run197 additionally fixed the tissot
`acc_vreg` refcount that produced `unbalanced disables for l6`.

**2. The GPU was entering a 64-bit hardware address mode stock never uses.**
`adreno_support_64bit()` is gated on `BITS_PER_LONG == 64`; stock CAF 4.19 is
32-bit so the A506 never enters it, this arm64 port did, while
`KGSL_MMU_64BIT` was deliberately withheld so the MMU built 32-bit
descriptors. All three uses are now gated on
`MMU_FEATURE(&device->mmu, KGSL_MMU_64BIT)`; `addr_mode` reads back 0 and
`KGSL_PROP_DEVICE_BITNESS` no longer advertises 48 over a 32-bit pool.
**This was ruled out as the fault cause**: run198 still traps at exactly
`0x139000` with `cp_status=80423c68`.

**3. The GPU page-table format also differed from stock, and was also ruled
out.** Stock CAF sets `qcom,use-3-lvl-tables` on this very SMMU
(`msm-arm-smmu-8953.dtsi:29`), which selects `ARM_32_LPAE_S1` — 32-bit
stage-1 descriptors. The port derived `use_aarch64_pt` from compatible strings
alone and got `ARM_64_LPAE_S1` with `.ias=39`. run199 forces the stock format
(`ias=32 aarch64=0 tcr=80802020 tcr2=00038002`) and the trap is unchanged:
same `0x139000`, same `cp_status=80423c68`, `screencap` byte-identical to
run196-198 (`d1d094a5...`), panel still backlit with no render.

So every axis on which the port could have disagreed with stock about
addresses is now closed and verified: hardware address mode, page-table
format, MMU mapping, software walk, and SMMU context-bank state.

**Why the screen is still black — measured, not inferred.** On a live port boot
`screencap` was decoded by hand: 1080x1920, 42,625 sampled pixels, **one
colour, `#000000`**, six captures byte-identical. `screenrecord` (a different
path, through a VirtualDisplay) agrees: 6 byte-identical frames, 1x1 RGB
`(0,0,4)`. So the panel is being driven with a black frame. Only 3-4 layers
exist and the launcher is killed in a loop:
`ActivityManager: Process com.google.android.apps.nexuslauncher (pid N) has
died: fg BFGS`. The first fault is on `surfaceflinger[716]`, the first GL
context ever to submit, 12 ms after `ME_INIT` — a startup fault, not a
workload fault. This **corrects** the earlier claim that `screencap` returns
a constant image regardless of display state; it is constant while the content
is.

**Tooling added.** `porting/logging/observe-boot.py` (bounded observer; its
logcat runs as its own process because a streaming `adb logcat` blocks until
the adb timeout) and `porting/logging/port-boot-retry.py` (retries a RAM boot
and confirms `uname -r` before reporting success — `fastboot boot` returning
OKAY does not mean the kernel ran). Never run two capture readers against the
same serial port; doing so cost three boots today.

**Known damage.** `/home/kurision/development/kernel/ack-android16-6.12` was
deleted during this session. `ack-kgsl` is a git worktree of it, so **git is
dead for this tree** and the four commits made earlier today
(`aafc0aca7`, `87b2a5d70`, `e303e8859`, `bd6f4c91f`) are lost with the object
store. Working files are intact. `drivers/video/fbdev/msm/mdss_dsi.c` was
restored from `~/.cache/run126-rust.oFKCctgK/source-ee66fc52d/` after an
editor error duplicated it.

**Repository note.** `.git` was a worktree pointer into the deleted
`ack-android16-6.12`. It has been replaced by a fresh `git init` with
`origin = git@github.com:kurision/android-6.12-port-work-slop.git` and one
import commit `4d4fcc1`. `git ls-remote` currently fails with
`Permission denied (publickey)` — the local `id_ed25519`
(`kumalanil34@gmail.com`) is not authorised on that remote, so the tree is
committed locally but not pushed.

Evidence: `artifacts/snapshot60/run196-live/display-analysis.md`,
`artifacts/snapshot60/run198-live/gpu-analysis.md` (all three GPU runs and the
method notes),
`artifacts/snapshot60/FAILING-COMPONENTS.md` (top table).

Next: the UCHE out-of-bounds trap itself. It is a startup fault on the first
GL submission, at a structurally invariant SVM address, with the hardware in
stock's address regime, stock's page-table format, and the buffer proven to
map and translate. What is left is the GPU's own address generation or the
command stream, not the port's MMU/SMMU programming.

## Previous handoff — run188, 2026-10-17

Build/package/boot/capture instructions are in [BUIL_TISSOT.md](../BUIL_TISSOT.md).
Keep run evidence in this handoff, the trackers and `artifacts/snapshot60/`.
Run filenames in this section are relative to `artifacts/snapshot60/`.
Earlier "Latest", "read first" and "current best" headings below are historical.

Run188 exists to close one specific question from run187: is the faulting IOVA
actually translated to the right physical page? The answer is **yes in software,
and the fault still happens**.

- **One source change vs run187:** `adreno_fault_dump_target()` now calls
  `iommu_iova_to_phys()` and prints `DIAG <name>-walk`. Nothing else in the kernel
  changed; `package-run188.json` shows ramdisk, init, cmdline, cpio record count,
  `debuggable`, firmware and policy all byte-identical to run187, and
  `run188-embedded.config` matches `run187-resolved.config` exactly.
- **Artifact:** `boot-run188.img`, sha256
  `f690ade9d7b8e7923d72c8b5e31b7bc7f0632847069297ba76e2aa07ac0e6fd8`, kernel
  payload `05cf0e90f8613a570eab5693541aac599fe29caac34520ed253cd5e36efa35af`,
  base the real `boot-run187.img` (`7cc2d6e38559…`). Build log
  `run188-build.log`, package report `package-run188.json`, seed/resolved configs
  `run188-seed.config` / `run188-resolved.config`, preflight
  `run188-preflight.log`.
- **Boot:** fastboot `Sending`/`Booting` both OKAY (`run188-usb-capture.out:4-5`),
  diag gadget enumerated, port boot ID `5b8f79d3-66d3-4f2b-9413-3d0d9fb37c97`.
  First port ADB sample at device uptime 46.66 s (`run188-live/poll.jsonl:18`);
  `sys.boot_completed=1` and `dev.bootcomplete=1` first sampled at uptime
  **101.93 s** (`run188-live/poll.jsonl:30`), bootanim `stopped`, still set at
  **412.29 s** with SurfaceFlinger **711** and system_server **1122** unchanged
  (`run188-live/final-state.log`). `/dev/ashmem` present throughout.
- **The walk result — the point of the run:** all **13** `*-walk` lines are
  `walked=1 backing=1 match=1 mapped_flag=1`. Example,
  `run188-logdump.log:3690`:
  `uche-trap-walk target=139000 offset=0 walked=1 resolved=0x00000000330ad000
  backing=1 expected=0x00000000330ad000 match=1 mapped_flag=1`. The entry's
  `pt_ttbr0` equals `gpu_current_ttbr0` (:3687) and the SMMU reports
  `sctlr=00001167 translating=1 ttbr0=0x1aa43000 fsr=00000400 far=0` (:3696) —
  FORMAT=2 with no active fault bits, so the UCHE trap is internal to the GPU, not
  a translation fault. **This retires the "not mapped / wrong physical page"
  hypotheses.** It does **not** prove hardware-visible translation: a software
  walk still cannot inspect the leaf PTE the MMU actually fetched, nor its
  attributes, nor the ordering of map/unmap against the fetch.
- **Faults persist, unchanged:** same targets as run187 — uche-trap `0x139000`
  (4×) and `0x1b14000` (4×), mem-write `0x133000` (4×) and `0x1b0e000` (1×), all
  at `offset=0` of a `0x1000`-byte entry, i.e. not a tail overrun. 436
  `GPU hang detected`, 543 UCHE records, 2 `gpu fault threshold exceeded`
  (surfaceflinger 711 at `run188-logdump.log:4503`, nexuslauncher 1607 at :11417).
  First hang at `run188-logdump.log:3678`, t=41.986325 s. Zero oops/BUG/call
  trace/blocked task/soft lockup. Hang counts are **not** a controlled comparison
  with run187 (498 over 480 s there, 436 over 412 s here).
- **CPU:** healthy scheduling — 8/8 online, **steal 0**, 4016 jiffies in a 5 s
  window against ~4000 expected, 62.2 % busy, 3.7 % iowait (`run188-cpu-note.json`).
  But **frequency is unmanaged and unreadable**: no
  `/sys/devices/system/cpu/cpuN/cpufreq`, `CONFIG_CPUFREQ_DT` not set, cpu nodes
  carry no `clocks`, no `littledcvs` node. Stock scales these cores
  (1,401,600–2,784,000 kHz, schedutil, `run188-stock-cpufreq.log`), though stock's
  2,784,000 kHz ceiling is itself a vendor OPP-table artifact above this A53's real
  maximum, so neither number is a trustworthy measurement. Whether the port runs
  the little cluster at its intended OPP is **unverified**.
- **Capture and recovery:** USB 443,083 B, ending at host_elapsed 63.7 s during
  the adbd UDC handoff — the known tooling cutoff, not a boot defect. Logdump was
  cleared this run, but only after the partition was verified byte-identical to the
  preserved `run187-logdump.bin` (`run188-preboot/manifest.json`), readback proven
  all-zero. Recovered 18,300,386 B of text, sha256
  `63a3243576a1440a46b9e18f050ee25954321d7d8b927615ef73027ff5c7dfa7`, four
  CRC-verified slots carrying this boot's marks (`boot_id=0x5f11be76`). The reset
  record is orderly and host-requested — `action=1 pid=1 comm=init command=shell`
  at 427.131141 s (`run188-recovery.log:36`). Final device: rooted stock
  **4.19.325-cip136**, boot ID `0297c073-acfe-41bd-a953-6f7329401708`. Nothing
  flashed.
- **Not verified for this run:** no physical panel observation was collected, so
  **visible output is unverified for run188** — do not read run187's dimly backlit
  panel forward. `run188-live/logcat-stream.log` is 32.7 MB and only its tail dump
  was read.

Next work: what the MMU actually fetched — leaf PTE attributes (AF, device/denormal,
SH vs nGnRE/nGnRnE, nGXN/XN) and map/unmap ordering versus the fetch — or why the
UCHE declares out-of-bounds on a legal, correctly mapped address at offset 0.
Summary/provenance: `run188-summary.json`, `run188-live/`,
`run188-preboot/`, `run188-recovery.log`, `run188-ramoops.json`,
`run188-cpu-note.json`, `run188-stock-cpufreq.log`.

### The first UCHE fault and its mapping block, verbatim

`run188-logdump.log:3669-3696`. This is the whole diagnostic cluster for the first
fault of the run; nothing between these lines is omitted except unrelated
`init`/`libprocessgroup` service chatter.

```
3669  UCHE: Out of bounds access addr=0000000000139000
3672  DIAG uche-oob: cp_status=80423c68 hw_fault=00000000 ib2=0000000000260140/0
      addr_mode=1 mode=20000000 gmem=00100000-00121000
3675  DIAG cp-stall: rptr=fd wptr=fd ahb=0903a284 protect=00000000 int0=00000000
      status3=00000000 switch_cntl=00000000
3678  MISC: GPU hang detected
3681  surfaceflinger[711]: gpu fault ctx 2 ctx_type GL ts 12672 status 800001C1
      rb 0100/0209 ib1 0000000000289000/00e6 ib2 0000000000260140/0000
3684  surfaceflinger[711]: gpu fault rb 1 rb sw r/w 0100/0209
3687  DIAG uche-trap-pt target=139000 pt=000000002cd8f45d
      pt_ttbr0=000000001aa43000 gpu_current_ttbr0=000000001aa43000 match=1
      default_pt=000000002cd8f45d
3690  DIAG uche-trap-walk target=139000 offset=0 walked=1
      resolved=0x00000000330ad000 backing=1 expected=0x00000000330ad000
      match=1 mapped_flag=1
3693  DIAG uche-trap-cpu-sample-skipped target=139000 entry_gpu=139000 size=1000
      flags=c0900 priv=808 secure=0 sgt=0000000000000000 aligned=1 offset=0
      in_range=1 memtype=9
3696  DIAG fault-smmu: sctlr=00001167 translating=1 ttbr0=000000001aa43000
      fsr=00000400 far=0000000000000000 fsynr=00000000
```

Reading notes, so the next run does not re-derive them:

- The leading `2,3516,41986602,-,caller=T129;` style prefix in the log is
  **record-sequence metadata, not a line number**. Cite line numbers only.
- `uche-trap-walk` here is the "software translation agrees" outcome: `walked=1`,
  `resolved` non-zero and equal to `expected`, `match=1`. Across the entire run all
  13 walk lines are identical in those four fields — there is **no**
  `resolved=0`, no `match=0`, no `walked=0` and no `backing=0` case to chase.
- `cp-stall` shows `rptr == wptr` (`fd/fd`), i.e. the ring is empty when dumped,
  and `ahb=0903a284` is a register residue from the driver's own read. Run154
  already established these AHB registers are not decisive; do not re-read them
  as the fault.
- `gmem=00100000-00121000` is a 0x21000-byte GMEM aperture window with
  `addr_mode=1`.
- `fault-smmu`: `translating=1`, `far=0`, `fsynr=0`, `fsr=0x400`. Bit 9 of FSR is
  FORMAT, so this is FORMAT=2 with no active fault bits. The MMU did not fault;
  the trap is internal to the UCHE.
- The trapping entry is `size=0x1000`, `in_range=1`, `offset=0`, `memtype=9`,
  `MAPPED` (`priv=808`) — the trap is on the **first** word of a legally mapped
  object, not a tail overrun. `0x1b41040` (`:10655`) is a distinct OOB address
  with no matching walk line in this capture.

### Build cost note (from run188)

`out-run$N` per run makes every build a clean build; run188 cost roughly 40
minutes for one changed `.c` file. Reuse a single persistent `O=` directory for
incremental runs. kbuild bakes the absolute `O=` path into `.cmd` files, so
*copying* an old out dir to a new name still triggers a near-full rebuild — the
directory has to be the same path across runs.

## Previous handoff — run187, 2026-10-17

Run filenames in this section are relative to `artifacts/snapshot60/`.

- **Android boot completion is reproduced:** run187 first sampled
  `sys.boot_completed=1` and `dev.bootcomplete=1` at **103.73 s**;
  still set at **479.70 s**, with SurfaceFlinger **706** and system_server
  **1126** unchanged. Port boot ID `46f81447-d2f8-4915-9062-a281bf2b4e79`.
  Evidence: `run187-live/poll.jsonl:27`, `final-state.log:1-10`.
- **Visible output remains open:** user observed "for first 10 sec fastboot
  splash then dimly backlit screen till now". No visible boot animation or UI
  confirmed. Record: `run187-live/panel-observation.json`; do not substitute
  screencap or HWUI timing warnings for a physical-panel observation.
- **The GPU still faults:** first UCHE OOB at **42.150316 s**, target
  `0x139000` (`run187-logdump.log:3673`); **607** UCHE records and **316**
  GPU fault-context records over the captured boot. **0** CP-init failures,
  GPU page-fault records or invalid-page-free warnings observed in this
  capture. Counts cover this run only and are not a controlled rate comparison.
- **No spontaneous reset during the observation.** The host stopped collectors
  and requested `adb reboot` for persistent recovery. Decoded reset record at
  logdump offset `0x3f30000`: `comm=init command=shell`, 492.603 s.
  Final device: rooted stock **4.19**, boot ID
  `93165dd4-225f-479e-aae2-9dcd1ad66165`. Nothing flashed or cleared.

### Exact artifact and build provenance

- Image `boot-run187.img`, SHA-256
  `7cc2d6e385590f97f12baeac4db74d50e185795b5ddadb65374d325188bf4188`;
  kernel payload
  `81181d73fb3160eb5545a7a48edfd77968f46a5b906d9a79ef678bece862795d`.
- Real `boot-run186.img` base; ramdisk hash, init hash, command line and DTB
  verified unchanged. Source `/tmp/ack-run164-source`, output `out-run187`;
  reviewed GPU/IOMMU/DT files matched this worktree. Current branch:
  `mdss-bisect`; the two tested driver changes remain uncommitted.
- Embedded configuration seeded from run185, not run186: Rust/ashmem enabled.
  Pinned Rust **1.99.0**, bindgen **0.73.2**, libclang/clang **22.1.8**.
  The known `RUSTFLAGS_AUTOFDO_CLANG` spelling override was required.
  See `run187-build-environment-final.json`, `run187-source.patch`,
  `run187-embedded.config`, `package-run187.json` and build logs.

### Run186 reset: reproduced ashmem failure, not an attributed SMMU reset

Run186 omitted `CONFIG_RUST_IS_AVAILABLE`, `CONFIG_RUST` and `CONFIG_ASHMEM`
from its embedded config; run183/run185 retained them. system_server repeatedly
threw `Failed to create ashmem: No such file or directory`
(`run186-live/logcat-all.log:551,824,2076,9439,16705`). Decoding
`run186-logdump.bin` at `0x3f30000` gives `command=zygote-fatal` at
79.857 s and the retained init line "critical process 'zygote' exited 4 times
before boot completed". This matches [AOSP's critical-service policy](https://android.googlesource.com/platform/system/core/+/android16-release/init/).
Run187 restores the driver (`run187-logdump.log:280`) and
`/dev/ashmem` is present throughout the port ADB samples.

The PATH issue is established: `/usr/bin/rustc` is **1.98.1 / LLVM 22.1.8**;
the rustup compiler is **1.99.0 / LLVM 23.1.1**. bindgen is absent from PATH,
but the cached 0.73.2 binary exists. Do not repeat an unpinned build.

### Corrections to the earlier diagnosis

- **Table depth:** with 4 KiB pages, IAS=32 and IAS=39 both use **three**
  levels; IAS=40 uses **four**. The "2-level versus 3-level" descriptions below
  and in commit `bc619e32e` are incorrect. CAF caps
  `qcom,use-3-lvl-tables` at **39** bits, not 40
  ([CAF source](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-crosshatch-4.9-pie-qpr2/drivers/iommu/arm-smmu.c)).
- **Current GPU translation:** run187 uses ARM_64_LPAE_S1, IAS=39/OAS=40,
  a successful SCM page-table-format request and the corresponding TCR/TLB code.
  Readback: `tcr=00802019 tcr2=00038012`
  (`run187-logdump.log:442,454`). MDSS remains IAS=32/AArch32 (:469).
  KGSL_MMU_64BIT is deliberately still withheld to isolate this experiment;
  adreno.c's accompanying "aperture is 32-bit" diagnostic is now stale.
- **SCTLR:** the requested mask is **0x10e7**, not 0x1325. CFIE is bit 6,
  CFRE bit 5, CFCFG bit 7; `0x1167` retains CFIE/CFRE and reflects KGSL
  selecting HUPCF instead of CFCFG. The previous lost-bit/firmware-ownership
  deduction is withdrawn. SCTLR=0 after secure restore does not establish
  ownership of other bank configuration, including its translation format.
- **FSR:** bit 9 belongs to FORMAT, not IGN. `0x200` is FORMAT=1;
  run187's `0x400` is FORMAT=2, with no active fault bits in these samples
  (`run187-logdump.log:3700`). Run185's `0x80000202` includes TF/MULTI.
- **Mapping proof is incomplete:** MAPPED plus matching TTBR0 does not inspect
  the actual leaf PTE or prove hardware-visible translation/attributes.
  The public `iommu_iova_to_phys()` API already reaches this driver's walk;
  the earlier abandoned-probe comment claiming an extra IOMMU export was
  necessary is incorrect. A software walk still is not a hardware walk.
- **Run184 page wait:** `folio_wait_bit_common` alone does not identify the
  waited bit, page owner or a GPU-backed buffer. The claimed causal chain
  "one GPU fault locks that buffer and permanently wedges system_server" is
  **unverified**. Boot-time available-memory output does not rule out later
  memory pressure; service liveness does not prove audio playback.

Register definitions cross-checked against the [upstream ARM SMMU header](https://raw.githubusercontent.com/torvalds/linux/master/drivers/iommu/arm/arm-smmu/arm-smmu.h).

### Capture quality and next work

The 64 MiB run187 logdump SHA was verified against the device:
`481163b16c211f473643418be2b885b2bb647dc6459d8c7ce4d78a598d93550f`.
Its readable prefix is **21,200,714 B**, one fresh #18 banner, strictly
increasing record sequences through **489.766674 s**. All **3335** USB records
match persistent capture. USB: **439,386 B**, ends at 40.970600 s during
handoff; later faults come from persistent evidence. Retained run186 partition
was hash-verified before boot; logdump was left uncleared.

The explicit run187 boot saw a roughly **24 s** ADB-to-fastboot transition,
then both Sending/Booting OKAY and a fresh kernel banner. This does not prove
the original script caused earlier intermittent splash hangs. Its unconditional
ADB reboot cannot start from fastboot, and an unbounded reader can hide progress;
capture outcome and image loading must be recorded separately.

Next work is the persisting UCHE fault: inspect actual PTE/backing-page and
attribute agreement using existing APIs before another hypothesis-driven change.
Do not label the 39-bit experiment a rendering fix or blindly replay run185.
Summary/provenance: `run187-summary.json`, `run187-live/`,
`run187-host-commands.log`, `run187-recovery.log`, `run187-ramoops.json`.

## Historical handoff entries

The entries below retain the evidence and hypotheses available at the time.
The current handoff above supersedes their status and identifies retracted claims.

## Latest: run171 — boot_completed PROVEN on target; SMMU bypass proven at draw time

- **Goal half 1 met:** `sys.boot_completed=1` and `dev.bootcomplete=1` on the
  port kernel, first observed at uptime **114.29 s**
  (`run171-live/boot-state.log`, `final-state.log`; `BOOT_COMPLETED` x4 in
  `run171-live/logcat-final.log`). Kernel banner
  `6.12.93-4k #5 SMP PREEMPT Sat Oct 17 00:26:19`, boot_id `32a47d19-…`.
- **Goal half 2 still UNMET:** no rendered boot animation. The framebuffer is
  **solid WHITE** (`run171-live/screencap.png`, `screencap-final.png`), which is
  a change from the solid black of run163-166. `init.svc.bootanim` was
  `running` then `stopped`, and `BootAnimation` appears x7 in logcat, but no
  animation frame was ever composited.
- **SMMU bypass proven at fault time.** New `DIAG fault-smmu` probe, 4 samples
  at t=42.49-42.69 s: `sctlr=0x00000000 translating=0 ttbr0=0 far=0 fsynr=0`,
  `fsr=0x200` (bit 9 = `ARM_SMMU_CB_FSR_IGN`, latched/ignored, not an active
  fault). **The "secure-managed SMMU translates at draw time" hypothesis is
  eliminated.** The probe reads gfx3d_user via a SoC-node scan (the board DT
  deletes the gpu `iommus` phandle) from the dispatcher workqueue, never
  hardirq — it booted clean, confirming the run118/119 safety reasoning.
- **Address-translation mismatch also eliminated.** First UCHE trap
  `0x3aa53000`; independent checks agree: `gpu=0x3aa53000`, SG 1/1
  contiguous, `dma=0x3aa53000`, `actual(PFN)=0x3aa53000`, `gpu-match=1`.
  50 GPU faults, `cp_status_1=0x80423c68`, `hw_fault=0`.
- Boot method matters: the **automated** `usb-boot-capture.py` attempt stalled
  at splash with a **0-byte** capture; the user's **manual** `fastboot boot` of
  the *same image* booted fully. This matches the tracker precedent at
  `TRACKER-kgsl-port.md:2962-2971` ("the splash hang and the boot are the same
  event seen at different times"). `porting/logging/fastboot-boot-capture.py`
  was added for fastboot-only retries but was not the path that worked.
- Evidence: `run171-live/` (logcat 3.0 MB, two screencaps, GPU snapshot
  945,280 B, boot state), `run171-logdump.log`, `run171-live/results.json`.
  Device returned to stock 4.19. Nothing flashed or cleared.
- **Remaining GPU hypotheses, in order:** (1) VSC producer never writes size
  words — upstream CP/VSC config mismatch, buffer reads 0; (2)
  cacheability/shareability mismatch on the WRITECOMBINE coherent mapping;
  (3) A5xx microcode/VSC setup divergence from stock. The `0xf9ec4100` trap in
  the launcher path is a second, distinct trap address worth separating.

## Latest: run172 — self-inflicted policy regression removed; NOT a regression

- `boot-run172.img` sha256 `b6d941ed6f2bd6978a79423804e770495ddcada74eb69727d802872b80608934`,
  **kernel payload identical to run171** (`5b6c9013d389`); only the ramdisk
  policy differs. Based on real `boot-run166.img` (which never carried the
  wide GPU label) plus `porting/policy/harness-run172-evidence.cil`.
- Verified inside the image: exactly **1** GPU genfscon, scoped to
  `/devices/platform/soc@0/1c00000.gpu/kgsl/kgsl-3d0/snapshot`, plus 1 MDSS
  LED label. run167's whole-subtree `1c00000.gpu -> sysfs_gpu` relabel — the
  cause of run171's 371 `hal_power_default` search denials — **is gone**.
- Automated boot worked this time: 442,995 B USB capture. **0 GPU faults
  observed, but that is a capture-cutoff artifact, not an improvement**: the
  log ends at `t=40.96 s`, just before run171's first UCHE fault at `t=42.4 s`.
- Port kernel did **not** set `boot_completed` within the ~179 s observation
  window before USB dropped. SystemServer PID changed 1109 -> 1821 mid-boot,
  i.e. the known watchdog-restart pattern (run150 section below) that
  completes at ~590 s. So run172 is **not** proven worse than run171 — the
  window was too short.
- **Attribution guard:** once the RAM image is lost the phone returns to stock
  4.19, which reaches `sys.boot_completed=1` in ~46 s. A poll showing `bc=1`
  near 46 s is the STOCK kernel (boot_id `f5d05438-…`), **not** the port
  kernel. Always confirm `uname -r` before crediting a completion. The real
  port-kernel completion observed is run171 `32a47d19-…` @ 114.29 s.
- Device is on stock 4.19. Nothing flashed or cleared.

## Correction: screencap is NOT a rendering signal on this device

- `adb exec-out screencap -p` returns a **solid, byte-identical image
  (sha256 `1fa22509…`, 12,504 B) regardless of display state**. On stock 4.19
  it was captured twice: once with `Display State=OFF, mWakefulness=Dozing`,
  and once after `KEYCODE_WAKEUP` + `dismiss-keyguard` with `Display State=ON`.
  Same hash both times.
- **The "framebuffer went BLACK -> WHITE" claim in the run171 section above is
  therefore withdrawn.** It was an artifact of display power state, not
  evidence that the backlight policy fix changed rendering. The policy fix
  itself is still proven — every `brightness`/`max_brightness`/
  `lcd-backlight` denial disappeared from run171's logcat — but its *visual*
  effect is unverified.
- **Do not use screencap to judge rendering here.** Verifying a visible boot
  animation requires looking at the physical panel (user observation or a
  photo), as in the user's `PXL_20261016_171508720.TS.mp4`, which showed
  EXTREME BOOT splash at 30 s, blank blue at 80 s, dark at 130 s.
- Stock control is otherwise healthy: stock 4.19 GPU reports
  `gpubusy = 395754/1005275` (39% busy) at 320 MHz with
  `sys.boot_completed=1`, i.e. the same userspace drives the stock GPU fine.
  Whatever breaks rendering is in the port kernel path, not the vendor blobs.

## Exhaustive elimination — do not re-test these

Each item was checked directly against source or a snapshot register dump.
All are **eliminated**, except where a row says otherwise:

| Hypothesis | Check | Result |
|---|---|---|
| ~~Secure SMMU translates at draw time~~ | `DIAG fault-smmu` x4, t=42.5-42.7 s | **REVERSED — see the MAJOR section below. The port has no SMMU; stock does. A difference, not a cleared hypothesis.** |
| Trap buffer address mismatch | `gpu`/`dma`/`page_to_phys` | all `0x3aa53000`, `gpu-match=1` |
| Trap buffer non-contiguous | `sg=1/1`, `contiguous=1`, `covered=1000` | contiguous |
| Missing A506 register init | `a5xx_init` vs CAF donor | **byte-identical** |
| Wrong A506 thresholds | vs upstream `a5xx_gpu.c:762-773` | `CP_MEQ_THRESHOLDS=0x20`, `CP_MERCIU_SIZE=0x400`, `CP_ROQ_1=0x20100D0A`, `CP_ROQ_2=0x40000030` all match |
| Wrong `PC_DBG_ECO_CNTL` | `adreno_is_a504_to_a506` branch | `(0x100<<11 \| 0x100<<22)`, matches upstream A506 |
| Wrong UCHE trap base | vs upstream `a5xx_gpu.c:1774` | both `0x0001ffffffff0000` |
| `CP_PROTECT` intercepting | snapshot `0x880-0x88f` | every entry has bit31 clear = disabled |
| VSC geometry programmed by kernel | source grep | `VSC_BIN_SIZE` comes from the **userspace** blob |
| `errno 71` = driver bug | `kgsl.c:1891-1894` | `-EPROTO` is an explicit "context needs recovery" success marker |
| MMU logic lost in port | `kgsl_mmu.c` vs donor | differs **only** by diagnostic `dev_info` lines |
| Userspace blobs at fault | stock 4.19 control | stock GPU 39% busy @320 MHz, `sys.boot_completed=1` — same blobs work on stock |
| DMA mask regression | `kgsl.c:5234` | `U64_MAX` == `DMA_BIT_MASK(64)`, cosmetic |

**What survives:** a driver-written register is later changed, or the hang is a
hardware-state effect no register diff can show. The signature is now decoded:
`RBBM_STATUS=0x800001c1` = `GPU_BUSY_IGN_AHB` + `CP_BUSY` +
`GPMU_MASTER_BUSY` + `HI_BUSY`, with **`CP_ME_BUSY` clear** — the CP stopped
fetching mid-ring (`rptr 0xc0` behind `wptr 0x107`) with the micro-engine idle
and no CP error (`CP_INTERRUPT_STATUS=0`, `CP_HW_FAULT=0`). That is a CP stall
awaiting a condition that never arrives, not a faulting unit.


## Graphics stack facts (and one dead end)

- The active GLES driver **is** the Qualcomm Adreno blob. `dumpsys
  SurfaceFlinger` on stock 4.19 reports
  `GLES: Qualcomm, Adreno (TM) 506, OpenGL ES 3.2 V@0502.0 (GIT@03dd3ba, ... Date:10/28/20)`.
- **Dead end, do not chase:** `/system/lib64` contains `libGLESv2_angle.so` and
  friends, which looks like GL is routed through ANGLE-over-Vulkan. It is not.
  There is no `libGLESv2_adreno.so` in `/vendor/lib64` (only `libEGL_adreno.so`,
  `libadreno_utils.so`, `libq3dtools_adreno.so`, `hw/vulkan.adreno.so`); the
  active GLES library lives elsewhere in the ROM. `ro.hardware.vulkan=adreno`
  exists but `ro.hwui.use_vulkan` is empty, and the reported GLES renderer is
  the native Adreno one.

## Run173 — the CP is NOT stalled; it drains the ring (model corrected)

- Read-only probe in the UCHE OOB handler; no register is written. Image
  `7750aa932ce0837efbc582a6371aefdad186d6a00949fd54787b744dbc69cf74`,
  kernel payload `84ee336aee140e22fbcb33c80a7c69275f10e109abcac03a892e92274b4d2d93`.
- USB capture again ended at ~t=41 s, before the 42.4 s fault, so the data came
  from the persistent logdump.
- **At the first UCHE OOB (t=42.613 s): `rptr=0xb1 wptr=0xb1` — they are equal.**
  Also `cp_ahb_fault=0x0903a284` (bit31 error=0, stale residue), `protect=0`,
  `int0=0`, `status3=0`, `switch_cntl=0`.
- **This corrects the earlier "CP stopped fetching mid-ring" reading.** That came
  from a snapshot sampled later at fault-check time (`rptr 0xc0` vs `wptr 0x107`),
  not from the interrupt itself. At the interrupt the CP has already drained the
  ring, so it is **not** stalled mid-fetch and **not** waiting on a memory
  barrier. Do not re-derive a CP-wait theory from this.
- SMMU bypass, `CP_STATUS_1=0x80423c68`, `CP_HW_FAULT=0` and the UCHE aperture
  registers all re-confirmed unchanged.
- Root-cause chain, now with step 4 corrected: VSC binning issues a UCHE access
  to the 4 KiB VSC size buffer -> UCHE rejects it -> VSC emits no visibility
  output -> **CP drains the ring with no error latched** -> hang detector fires
  ~60 ms later -> GPU wedged, SurfaceFlinger never renders.
- **Open question is step 2 alone:** why the UCHE rejects an access whose buffer
  is proven physically valid. Buffer identity (gpu/dma/page_to_phys), contiguity,
  cache mode, SMMU state and every aperture/threshold register are eliminated.

## MAJOR: stock CAF runs the GPU *with* a working SMMU — NOMMU is the bug

Stock 4.19 `dmesg` (`run173` control, `kgsl-3d`/`smmu-kgsl` lines):

    [ 1.418887] platform 1c40000.qcom,kgsl-iommu:gfx3d_user: Linked as a consumer
                to 1c40000.arm,smmu-kgsl
    [ 1.418926] iommu: Adding device 1c40000.qcom,kgsl-iommu:gfx3d_user to group 2
    [ 1.419972] arm-smmu 1c40000.arm,smmu-kgsl: AARCH64 is supported for
                1c40000.qcom,kgsl-iommu:gfx3d_user

So on stock the **`gfx3d_user` context bank is attached to a real SMMU with
AARCH64 page-table support**, and the GPU runs translated. (The
`Couldn't get clock: gpu_ahb_clk` lines are a red herring: CAF retries and both
`gfx3d_user` and `gfx3d_secure` end up attached, in groups 2 and 3.)

Our port runs `DIAG fault-smmu: sctlr=0x00000000 translating=0`. **This reverses
the conclusion recorded above.** NOMMU is not a proven-good state to have
eliminated — it is the one large behavioural difference from stock, and it is
the prime remaining suspect for the UCHE rejecting a physically valid buffer:
with an SMMU the GPU gets hardware-validated addresses plus page-table memory
attributes; with the bank off it decodes raw addresses and rejects these.

- The "secure-managed SMMU translates at draw time" row in the elimination table
  above is **wrong as stated**. The correct statement is: the port has no SMMU,
  stock does. That is a difference, not a cleared hypothesis.
- History (`250485599`, `fef07bec1`): giving the GPU an IOMMU was fatal in 5/5
  boots with no recoverable log, so it was reverted in favour of NOMMU, which
  reaches userspace. The revert's own comment admits it is **untested** whether
  the secure-managed SMMU passes GPU traffic with the bank's M bit clear.
  **Re-enabling the SMMU correctly — and surviving it — is the next task.** The
  5/5 fatal failure needs its own diagnosis first; do not simply re-apply
  `250485599`.
- `gpu_region@0` in stock is only the 8 KiB `removed-dma-pool` firmware region
  (`bengal.dtsi:355`), not a render-buffer pool. Not a missing allocation pool.

## Run174: SMMU ENABLED — the GPU now starts clean (biggest fix so far)

- `msm8953-xiaomi-tissot.dts`: the `kgsl_iommu` node's `clock-names` changed
  from `"gpu_ahb_clk", "gcc_bimc_gfx_clk"` (which deliberately never resolve, to
  force NOMMU) to `"iface_clk", "mem_iface_clk"`, which are this GPU device's
  real names. The `/delete-property/ iommus` on `&gpu` is **kept**.
- `panic=0` was **dropped from the cmdline** (`--drop-cmdline panic=0`) so a
  fault reboots into a recoverable state instead of hanging at the splash.
  This is what made the run174/175 evidence possible at all; the historic
  "fatal with no log" verdicts were measured under `panic=0`.
- Image `65f1b723e0d395d664feb60d153c68663dfa661057857d6dcb82d8259539b5eb`,
  kernel payload `6551ade25cb6df37d400e94f481599bca7a59b4602257452832900ed1e9706c8`.
- **Result — KGSL is now translated, matching stock:**

      DIAG kgsl_mmu: subtype='iommu' type=0 (IOMMU/translated)
      DIAG gpu_smmu: cb=gfx3d_user sctlr=00001167 translating=1
                     ttbr0=00000000182c1000 fsr=00000200 mmu_type=0

  and **every bring-up probe reads `rbbm=00000001` (idle, no hang bit)**:

      DIAG bringup[start-entry]:    rbbm=00000001 rb_base=00000000
      DIAG bringup[rb-programmed]:  rbbm=00000001 rb_base=FC00B000
      DIAG bringup[microcode-loaded]: rbbm=00000001
      DIAG bringup[me-unhalted]:     rbbm=C00003C1

  Under NOMMU every one of these latched `800001C1`. The clean first start the
  tracker chased since run155 is finally achieved. **It also did NOT die** —
  it reached `mdss_fb_open` and userspace init.
- **Remaining blocker, now precisely located:** SurfaceFlinger's first
  allocation fails and it crash-loops (`no suitable EGLConfig found, giving
  up` -> SIGABRT, 39 crashes). Kernel cause is exact:

      WARNING at drivers/iommu/io-pgtable-arm-common.c:324 arm_lpae_map_pages
      Call trace: arm_lpae_map_pages <- iommu_map_nosync <- iommu_map_sg
                 <- kgsl_iommu_map <- kgsl_mmu_map
                 <- kgsl_mem_entry_attach_process <- kgsl_ioctl_gpuobj_alloc

  Line 324 is `WARN_ON(iaext || paddr >> cfg->oas)` returning `-ERANGE`
  (`x0=0xffffffde`). `qcom_iommu_init_domain()` hardcodes `.ias = 32`, so
  `aperture_end` is `0xffffffff`, and KGSL — which places GPU IOVA near the top
  of the 32-bit range (`rb gpu=0xfc00b000`) — runs out. Userspace sees
  `IOCTL_KGSL_GPUOBJ_ALLOC failed: errno 19` -> `EGL_BAD_ALLOC`.
  **Raising the IOVA aperture is the fix.** It is also consistent with the GPU
  itself being programmed for 64-bit addressing (`a5xx_enable_64bit()` sets
  ADDR_MODE_CNTL=1 on CP/VPC/GRAS/UCHE/VSC).

## Run175: ARM_64_LPAE_S1 attempt — REVERTED, undiagnosed

- Changing `.ias` to 40 and `alloc_io_pgtable_ops(ARM_32_LPAE_S1 -> ARM_64_LPAE_S1)`
  did **not boot**. No evidence was recoverable: `run175-usb.log` was 0 bytes and
  `run175-logdump.log` still carries run174's `#6` banner and records, so the
  partition was never rewritten.
- `ARM_64_LPAE_S1` *is* registered (`drivers/iommu/io-pgtable.c:20`, same
  `CONFIG_IOMMU_IO_PGTABLE_LPAE` guard as the working `ARM_32_LPAE_S1`), so the
  failure is **not** a missing-ops table and remains unexplained.
- **The change has been reverted** (`drivers/iommu/arm/arm-smmu/qcom_iommu.c`
  now differs from its committed state by comment only). run174 is the last
  known-good image. Do not re-apply run175 blind; the next attempt needs its
  failure captured, which means a boot that gets far enough for the ramoops
  snapshotter or the USB diag gadget to run.

## Run177: the -ERANGE root cause is FIXED (ERANGE count 0)

- Image `d6464517bc085c75ff7bab0245c458437b44a32ec481fc3ad8eed190b862ce29`,
  kernel payload `617bb9349af926da15af193b2aac340ba2892f052178341df52a70de81dd6cfb`.
- **Root cause found.** `KGSL_MMU_64BIT` (set because the A506 has
  `ADRENO_64BIT`) makes `setup_64bit_pagetable()` hand every non-secure page
  table `KGSL_IOMMU_VA_BASE64..VA_END64` = **`0x500000000..0x600000000`**
  (20-24 GiB, `kgsl_iommu.h:32-33`). The GPU SMMU aperture is 32-bit
  (`qcom_iommu.c` `.ias=32`), so every such map failed `-ERANGE`. The run174
  register dump confirms it: `x0=0xffffffde` (-ERANGE) with
  `x1=0x500000000` — literally the 64-bit VA base.
- **Fix:** withhold `KGSL_MMU_64BIT` in `adreno.c`, so KGSL falls back to
  `setup_32bit_pagetable()` whose ranges are all below 4 GiB. The aperture is
  left at 32-bit: raising it was tried twice and **both attempts failed to boot
  with no recoverable evidence** (run175 switched the page-table FORMAT to
  `ARM_64_LPAE_S1`; run176 kept `ARM_32_LPAE_S1` and only raised `.ias`).
  Do not re-raise the aperture without a way to capture the failure.
- **Proof it worked:** `arm_lpae_map_pages`/`ERANGE` occurrences went from
  repeated (run174) to **0**; the gate logged
  `run177: KGSL_MMU_64BIT withheld`; and GPU IOVA moved from `0xfc00b000`
  (above nothing useful) to **`0xf800b000`**, inside the aperture.
- **SurfaceFlinger no longer crash-loops.** It held PID **708** from 56 s to
  97 s and SystemServer **1108** for the same window (run174: SF died within
  seconds of the first EGL failure). SF then died around 100 s.
- Remaining: 12 GPU faults / 20 UCHE OOB (down from 50 faults), first trap
  `0x139000` at t=41.86 s — the address moved with the VA range (run174 trapped
  `0x3aa53000`), so it tracks the allocation, not a fixed aperture.
  `cp-stall` again shows `rptr==wptr`: the CP drains its ring with no error
  latched. `boot_completed` still not reached.
- Device on stock 4.19. Nothing flashed or cleared.

## Run178: the trap target is a *legitimately mapped* GPUOBJ (run177 read wrong)

- Image `f7cadad3a2c7c2c52629ed10c4bbe6daf1bec5189e1e271313b4beb9e3388a73`.
  The run177 message `DIAG uche-trap ... secure, absent scatterlist, or invalid
  range` was ambiguous, so run178 split it into per-condition fields.
- It now reads, on every trap:

      DIAG uche-trap-unmapped target=139000 entry_gpu=139000 size=1000
        flags=c0900 priv=808 secure=0 sgt=(nil) aligned=1 offset=0
        in_range=1 memtype=9 cpu_map=0

- **Correction:** `sgt=(nil)` is **not** a defect. `priv=0x808` is
  `KGSL_MEMDESC_MAPPED | KGSL_MEMDESC_CAN_RECLAIM` — a mapped GPUOBJ. In
  IOMMU mode such a buffer keeps its pages in `memdesc->pages` and builds an
  sgt only transiently while mapping into the page table. So the trapping
  buffer is properly allocated, 4 KiB, memtype GL, correctly addressed, and
  mapped. run177's "unmapped" wording was wrong and is corrected in the source
  comment.
- Net: after the run174/run177 SMMU and -ERANGE fixes, the picture is a
  **valid, mapped, identity-consistent VSC size buffer that the UCHE still
  rejects** — the same class of fault as before, now with translation enabled.
  The remaining discriminator is whether the buffer's pages are actually in
  the GPU page table (`kgsl_memdesc_get_va_len`) at fault time, and whether
  process reclaim (`CAN_RECLAIM` is set) is dropping it.

## Run179: the trapped buffer is valid on EVERY axis — the fault is GPU-side

- Image `721258262ebef0ef17b8853c751f61d04fb9786b9c27e801602a27371263d5ef`.
  Added a direct backing check (this KGSL has no reverse gpuaddr->va helper,
  so `memdesc->pages` / `pagetable` are the ground truth):

      DIAG uche-trap-backing target=139000 gpu=139000 size=1000
        pagetable=0x826a7583 pages=0xa5263b59 page_count=1
        mapped_flag=1 first_page=0x37c1a000 offset=0

- Verified individually: IOVA `0x139000` is the allocation **base** (offset 0,
  not an overrun) and sits inside KGSL's `SVM_BASE32`
  (`uche_gmem_base + gmem_size` = `0x100000 + 0x22000` = `0x122000`);
  size is one page; a page table **is** attached; `pages` **is** present with
  `page_count=1`; `KGSL_MEMDESC_MAPPED` is set; the backing physical page is
  `0x37c1a000`; and the context bank is translating
  (`sctlr=0x00001167`, M bit set, valid `ttbr0`).
- **Conclusion.** The UCHE raises out-of-bounds on an access that is valid on
  every software-visible axis. Buffer identity, contiguity, backing page,
  page-table mapping, translation state, cache mode, and all A5xx
  threshold/aperture registers have each now been checked directly and all
  pass. Nothing this evidence can reach explains the rejection; what remains
  is GPU-side — the secure-managed context bank's translation regime, or the
  GMEM aperture interacting with KGSL's VA layout.
- Do not re-run the contiguity, identity, cache-mode, register-init or SMMU
  probes: each is settled above and in the run165-179 logs.

## Run180: page-table mismatch also eliminated — the fault is fully unexplained by software

- Image `e6ddd605b74cef668d56fa102600870730bbecfe389706796d577805b90bf71b`.
  Tested whether the buffer is mapped into the page table the GPU is
  *currently running*, not just some page table:

      DIAG uche-trap-pt target=139000 pt=0x97788aac pt_ttbr0=0x18680000
        gpu_current_ttbr0=0x18680000 match=1 default_pt=0x97788aac
      DIAG gpu_smmu: cb=gfx3d_user sctlr=0x1167 translating=1 ttbr0=0x18680000

  The buffer's page table **is** the default one, **is** the one the context
  bank is running (identical `ttbr0` on both sides), and translation is on.
- **Eliminated this session, each with direct evidence:**
  SMMU bypassed vs stock (fixed, run174) ·
  `KGSL_MMU_64BIT` 20 GiB VA in a 32-bit aperture (fixed, run177) ·
  buffer address identity and contiguity (run165-166) ·
  SMMU translating at draw time (run171-174) ·
  trap buffer unmapped / no pages (run179) ·
  mapping in a stale page table (run180).
- The UCHE raises out-of-bounds on an access that is correctly addressed,
   page-backed, mapped into the running page table, and translated. Every
   software-visible property now passes. Anything further is GPU-side: the
   secure-managed context bank's translation regime, the GMEM aperture against
   KGSL's VA layout, or an A5xx hardware behaviour not described in the
   register documentation available here. Further progress likely needs
   secure-firmware/TZ configuration knowledge or a hardware reference rather
   than another log probe.

## Anomaly worth checking: the SCTLR we program is not the SCTLR we get

- `qcom_iommu_init_domain()` writes
  `ARM_SMMU_SCTLR_CFIE|CFRE|AFE|TRE|M|S1_ASIDPNE|CFCFG` = **0x1325**
  (bits 0,2,5,8,9,12) and reads back **0x1167** (bits 0,1,2,5,6,8,12) in the
  very next statement.
- **Bit 9, `CFRE` (client-fault response enable), is set by us and clear in
  hardware.** Bits 1 and 6 come back set and were not written.
- No claim is made about the cause. It is consistent with the secure firmware
  (invoked earlier in the same function by `qcom_scm_restore_sec_cfg()`)
  owning part of the context bank, or with hardware-defined/reserved bits.
- It is worth one look, because with `CFRE` clear a *client* translation fault
  is not turned into a response upstream — which is the shape of symptom that
  a UCHE out-of-bounds on a valid mapping would take. **Unverified.**

## Run182: boot completion re-proven on the CURRENT best image

- Booted `boot-run180.img` (the current tree, i.e. **with** the SMMU and
  `KGSL_MMU_64BIT` fixes, not the older run171 image the goal was first
  measured on).
- **`sys.boot_completed=1` at uptime 105.75 s**, `dev.bootcomplete=1`, logcat
  carries `BOOT_COMPLETED` x3 plus the broadcast latency report and the full
  `boot_progress_*` chain; `init.svc.bootanim` ran then stopped.
- **SurfaceFlinger PID 710 and SystemServer PID 1109 held from 72.91 s through
  105.75 s with no restart.**
- So the two fixes did **not** regress boot completion; it improved slightly
  (105.75 s here vs 114.29 s on run171, which predates them).
- Evidence: `run182-live/` (logcat 2.96 MB, poll log), `run182-usb.log`
  (433,804 B). Device returned to stock 4.19; nothing flashed or cleared.
- **Visible boot animation remains UNMET.** The bootanimation *service* runs
  and exits cleanly, but no animation frame has ever been confirmed on the
  panel: `screencap` is unusable on this device, and the GPU still raises
  UCHE out-of-bounds on a valid, mapped, translated VSC buffer (run180).

## Run183: the SCTLR anomaly is BENIGN — secure firmware does not own the bank

- Image `19cd2d60b014b58f33861e746063c408011bc3e0649da254b22a9fdb9b2a4ef7`.
  Read the context bank **immediately after** `qcom_scm_restore_sec_cfg()`,
  before touching it:

      DIAG cb-owner: asid=0 sctlr_after_secure_cfg=00000000 secure_ctx=0
      DIAG init_domain: master=...:gfx3d_user cb=0 sctlr=000010e7

  (for contrast the apps IOMMU at `1e20000` reads `asid=21 sctlr=30000080`, so
  the secure world does program *some* banks — just not the GPU's.)
- **The secure firmware leaves the GPU bank at SCTLR=0.** It therefore does not
  own, and is not silently overwriting, the GPU context bank. That hypothesis
  is eliminated.
- The SCTLR difference is then ordinary hardware behaviour on our own write:
  we write `0x1325` (bits 0,2,5,8,9,12) and read `0x10e7`
  (bits 0,1,2,5,6,7,12). Precisely **`CFIE` (bit 8) and `CFRE` (bit 9) do not
  stick**; `CFCFG` (bit 12) does. Translation (`M`), `AFE` and `TRE` all take,
  which is what matters. For contrast the MDSS bank (`asid=21`) reads back
  `0x000000e7` — same core bits, no `CFCFG`.
- So the earlier `CFRE` worry is resolved: **not the cause, and not a lead.**
  Nothing needs changing here.

## Frames ARE composed — just at ~0.3 fps (important for the visual check)

- run182's logcat contains HWUI late-frame warnings:
  `Davey! duration=2473ms / 3136ms / 3297ms / 3766ms`.
  So SurfaceFlinger **is** producing frames; each takes **2.5-3.8 s**.
- That reframes the outstanding visual question. It is not "nothing is ever
  rendered" — it is "rendering is glacial". A boot animation would therefore
  likely appear as a **static or barely-changing image**, not a smooth
  animation, and could easily be missed or written off as a blank screen.
- **Action for whoever is at the device:** watch the panel from ~20 s to
  ~120 s after the RAM boot and describe what is actually displayed. If a
  boot-animation logo is visible even for a few seconds, the remaining work
  is frame pacing / the VSC stall, not a total absence of rendering. If the
  panel is blank the whole time, composition is failing outright.
  This is the one measurement that cannot be taken from software here:
  `screencap` provably returns a constant image regardless of display state
  (identical SHA-256 with `Display State=ON` and `OFF`).
- Evidence: `run182-live/logcat.log` (HWUI Davey! lines).

## Status summary for whoever picks this up

| Deliverable | State |
|---|---|
| `sys.boot_completed=1` on the port kernel | **met** — run182 @ 105.75 s on the current best image, SF + SystemServer stable throughout |
| Visible boot animation | **NOT met** — user confirmed the panel is black |

- **Best image: `boot-run183.img`** (and `boot-run180.img`, same tree state).
  Kernel `6.12.93-4k`, GPU SMMU translating, GPU starts clean
  (`rbbm=0x00000001` at every bring-up probe), SurfaceFlinger stable.
- **run184 is the definitive causal capture** (29.4 MB of kernel log from a
  single 5.5 h boot, `boot_id ca9dda3f-…`). One GPU fault at **t=42.6 s**
  wedges `system_server` in **`folio_wait_bit_common`** (a page lock on a
  GPU-backed buffer); Android records it as
 `Blocked in handler on ActivityManager (ActivityManager) for 56s`
  / `Watchdog-Type: pre_watchdog`. The UI never recovers, so the panel stays
  black for the remaining ~5 h even though the GPU faults stop at t=897 s.
  **0 watchdog kills** — Android could not even restart its way out.
- **The panel is not the problem.** Display `ON`, `mWakefulness=Awake` for the
  whole boot, backlight applied (0.10, raisable to 0.76 via
  `settings put system screen_brightness 255`), and still black. Memory is
  fine (3.53 GB of 3.93 GB, 0 OOM events). Audio is fine (`mediaserver`,
  `audioserver`). Hardware buttons cannot help: input is downstream of the
  system_server stall, so `KEYCODE_WAKEUP` changes nothing.
- **Remaining direction:** the UCHE/VSC fault and whatever makes system_server
  take a page lock on the GPU buffer. Everything software-visible about that
  buffer is verified correct — address, contiguity, backing page, page-table
  mapping, running-page-table identity, translation state, cache mode, A5xx
  register init. run185's one hard datum is that with a 3-level table the SMMU
  finally reports `FSR=0x80000202` (bit1 TF, a **real translation fault**),
  which the 2-level setup never did. That is the thread worth pulling on.

## Run184 + code audit: the real divergence from stock is page-table depth

- The 5.5 h run184 boot (29.4 MB log, 341,931 lines, `boot_id
  ca9dda3f-…`) gives the causal chain for the black screen:
  GPU faults run **t=42.6 s … 897.3 s** and then stop; the screen stays black for
  the remaining ~5 h. The `/data/anr` trace for that boot (`Subject: Blocked in
  handler on ActivityManager (ActivityManager) for 56s`,
  `Watchdog-Type: pre_watchdog`) shows the main thread in
  **`sysTid=1103 folio_wait_bit_common`** with `context hwbinder` and an
  outgoing binder transaction stuck 1946 ms. So one GPU fault wedges
  system_server on a page lock and the UI never recovers. 0 watchdog kills:
  Android could not even restart its way out.
- **Ruled out:** memory exhaustion (`Memory: 3530424K/3932160K available`, 0 OOM
  events — it is a page *lock*, not memory pressure); the display pipeline
  (panel registers, `Display State=ON`, `mWakefulness=Awake`, backlight applied);
  audio (`mediaserver` + `audioserver` running); hardware buttons (input is
  downstream of the system_server stall).
- **Ruled out:** process reclaim. `KGSL_MEMDESC_CAN_RECLAIM` is set on the
  trapping buffer (`priv=0x808` = `MAPPED|CAN_RECLAIM`), but A506's feature mask
  is `ADRENO_PREEMPTION | ADRENO_64BIT | ADRENO_CONTENT_PROTECTION |
  ADRENO_CPZ_RETENTION` with **no `ADRENO_USE_SHMEM`**, so
  `KGSL_FLAG_PROCESS_RECLAIM` is never set and `kgsl_reclaim_init()` returns
  immediately. The flag is inert. (The reclaim selection loop also never checks
  `MAPPED`, which is a latent bug if reclaim is ever enabled, but it is not
  running here.)
- **The real divergence, found by audit.** A506 has `ADRENO_64BIT` set, so
  withholding `KGSL_MMU_64BIT` (run177) is a *workaround for the broken 32-bit
  aperture*, not the correct state. CAF's `msm-arm-smmu-8953.dtsi` sets
  **`qcom,use-3-lvl-tables`**; **this tree has no handling for that property
  anywhere**. With 4 KiB pages, `.ias=32` builds a **2-level** table
  (`va_bits=20`, `levels=2`) where CAF and stock use **3-level**. The GPU
  therefore runs against a differently shaped translation regime than on stock.
- **Direction for the fix:** give the GPU domain the CAF-equivalent 40-bit,
  3-level regime and re-enable `KGSL_MMU_64BIT`, rather than leaving KGSL on
  32-bit ranges. This is what run175/run176 attempted and both **failed to boot
  with no recoverable evidence** (0-byte USB capture, logdump still holding the
  previous boot). That is now worth redoing with a way to capture the failure:
  the failures happen before the diag gadget starts, so they need an earlier
  channel (ramoops console snapshot, or `earlycon`) before another attempt.

## Latest: run167 — physical recovery required; visual-boot goal still open

- User goal: visible boot animation plus target boot-completion logs. Completion
  is repeatedly observed; rendered boot animation is **not** verified.
- Run167 fastboot RAM boot returned OKAY, then no Mi A1 in ADB, fastboot or
  `lsusb` through the bounded observation. USB capture **0 bytes**. Reader stopped.
  **Cause unverified**; do not blame the policy from this silent attempt.
  User asked to hold Power ~15 s to return to stock; physical reset is pending.
  Nothing flashed or cleared. Before another boot, recover this attempt's logdump
  using unused label **167**, image `boot-run167.img`, and compare against
  SHA-verified `run166-logdump.bin`. Do not overwrite or clear retained evidence.
- Run167 image SHA-256
  `7494ddcb320806929dc9d1ed784dda254bbd2cca9fada63f17e59e840fc97810`.
  Kernel/init/cmdline unchanged from run166; only appended
  `harness-gpu-evidence-read.cil` to permit read-only GPU snapshot/LED path
  inspection. Its runtime policy compilation/access remains unverified.
  Exact shipped fragment saved in `run167-test/shipped-policy.cil`. Current
  source fragment narrows the genfscon from the whole GPU subtree to only
  `kgsl/kgsl-3d0/snapshot`; this narrower version is **unpackaged and untested**.
  Source review found no concrete policy syntax/type/neverallow error, but the
  whole-subtree relabel is a possible confound, not a proven failure cause.
- Run165: UCHE OOB precedes hang, first trap `0x34b02000`, distinct from
  conditional target `0x31e63000`. CP_STATUS_1 `80423c68`, HW_FAULT zero.
  UCHE mode/address-mode match initialization. Captured framebuffer is black
  (`run165-test/screencap.stdout`); boot completion observed at 106.72 s.
- Run166: first trap `0x32d0b000` belongs to a live native 4 KiB GL allocation,
  `flags=c0900`, SG 1/1; CPU words zero. **Cache mode is WRITECOMBINE**, not
  WRITEBACK: mask `0x0c000000`. GPU==SG physical is not independent DMA-handle
  validation. Last IB2's 121 DWORDs captured at `run166-logdump.log:3848-3941`;
  it uses CP_SET_DRAW_STATE (17 groups), then a 90-index draw. Trap address is
  not a direct IB2 operand. Referenced state span `[f9480940,f9480f40)` needs
  decoding; full snapshot export is the intended next evidence channel.
- Rootless LED readlink/ls failed, so canonical MDSS LED pathname is unverified.
  Source/policy review found old backlight explanations wrong: MDSS does register
  `lcd-backlight`; `sysfs_leds_202604` is an attribute mapping to `sysfs_leds`,
  and genfscon prefixes cover descendants. Actual current denials concern the
  MDSS LED endpoint, not the raw WLED attributes labelled in prior experiments.
  Do not introduce versioned attributes as context types or blind allow rules.
- Results: `run165-test/results.json`, `run166-test/results.json`,
  `run167-test/results.json`. Fresh capture ends at byte **3167484** (run165)
  / **3015399** (run166); trailing bytes match the preceding partition backup.

## Latest: run164 — fault-target diagnostic (Linux session)

- Device returned to stock **4.19** after RAM-only testing; nothing flashed or
  cleared. No capture reader remains running. Screen appearance was not observed.
- Run163 reproduced the unchanged run161 image: boot completion first sampled
  at **100.37 s**, 43 fresh GPU fault records. Its recovery label **162** is the
  pretest partition backup, not a boot of a new image.
- Latest tested image: `porting/artifacts/snapshot60/boot-run164.img`, SHA-256
  `802d2be5a26163c62bddaed5a9908d530ab7ad37465faefcc54f2afe11a61c0d`.
  Based on real run161; ramdisk CPIO, command line and DTB verified unchanged.
  Source diagnostic: `adreno_dispatch.c`, bounded candidate MEM_WRITE scan and
  CPU/scatterlist sample without cache maintenance. Rust 1.99/bindgen 0.73.2;
  host build/config differences and profiling-flag override in `run164-test/`.
- Run164 boot ID `75b92c37-877f-4450-b78a-4f7819428e25`: completion sampled at
  **103.31 s**, still complete at 169.17 s; SF/SystemServer PIDs **706/1121**.
  `dumpsys window lastanr` reports no ANR since boot.
- **42 fresh GPU faults; nine target samples.** First four SF samples show
  target `0x386ff000`, size 4 KiB, `sg=1/1`, contiguous and GPU==physical.
  CPU words `1/0`, nearby MEM_WRITE payload `0`
  (`run164-logdump.log:3748-3751`, repeated at 3843, 3928, 4026).
  Non-contiguity is not observed in these samples. GPU visibility, whether the
  candidate write executed, and the root cause remain **unverified**.
- Results/provenance/patch: `run163-test/`, `run164-test/`; SHA-verified 64 MiB
  partitions `run162-logdump.bin`, `run163-logdump.bin`, `run164-logdump.bin`.
  Run164 capture bytes after offset **3557138** match the pretest partition;
  exclude that stale tail. All 3404 USB printk records match persistent capture.
- Next: investigate conditional execution and GPU visibility of the sampled
  `1/0` words, not another contiguity-only probe. Do not treat CPU reads as
  evidence of GPU-visible contents or a precise CP execution location.

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
