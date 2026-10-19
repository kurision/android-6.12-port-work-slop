# Handoff: MSM8953 CPU bring-up — run261 boots with a working CPUFreq policy

## Resume here — the splash/reset is fixed; the phone now dies of something else

**The boot is fixed.** run261 booted the port kernel, handed the clock over
the donor's way, created one shared cpufreq policy over CPUs 0-7 with the
seven stock OPPs and reached `sys.boot_completed=1`. The phone then died
about 326 s of kernel uptime later with **no kernel-side fault record**. The
evidence and the analysis are in
`findings/cpu-dvfs-first-boot-run261-2026-10-19.md`; the pre-run analysis and
the hardening are in
`findings/cpu-boot-failure-analysis-run258-run260-2026-10-19.md`.

1. **Last completed test: run261.** Image SHA256
   `6b008c81b57f4099d24ae521dec84eab10d43d21000fb730062294df3c76a054`,
   kernel payload `59eb2793a5f7993002f544864f18e46250f51395f1eec8b69b802374bfe33d15`,
   banner `#1 ... Mon Oct 19 21:50:01 +0545 2026`. The only source difference
   against run260 is `drivers/clk/qcom/apcc-msm8953.c`; the DTB, config,
   ramdisk, init and command line are identical. Fastboot Sending/Booting
   both OKAY. 41 port ADB samples, boot_completed 1, bootanim stopped.
2. **The APCC handoff worked and is now evidenced:**
   `boot state: pll 00000000 00000000 00000000 0000000f mux 00000401 00000000
   00000403` followed by `shared CPU/CCI domain, speed bin 2, CPU 799999804
   CCI 399999902 Hz, corner 2` - the donor's post-boot state. cpufreq then
   reported `Running at unlisted initial frequency: 799999 KHz, changing to:
   1036800 KHz` and one policy0 covers CPUs 0-7 with all seven stock OPPs.
3. **There is a kernel log for a boot that reached userspace** for the first
   time: 1,965,307 readable bytes plus two CRC32-verified snapshot slots and
   two verified periodic printk tails. run260's logdump was 64 MiB of zeros.
4. **The death is a separate, unverified problem.** Last kernel message at
   272.35 s (ordinary Android service startup), last ADB at host 348.3 s,
   device gone at 353.3 s, back on rooted stock at 453.3 s after the user's
   force reboot. No panic, oops, lockup, watchdog bite or ACKRESET1 record.
   Leading hypothesis: the CPUs sat at 2016 MHz for 91 % of the run and this
   port has **no thermal control loop** - `CONFIG_QCOM_TSENS` is not set, the
   CPU nodes do not reference the thermal zones and the shared OPP table has
   no cooling-device, so nothing can throttle them.
5. **The UI lag is not a clock problem, and not the display either.** The
   MDSS fbdev port is **done** (fb0 at 1080x1920, the real otm1911 panel,
   the vendor composer opening the framebuffer, 1200 frame kickoffs) - the
   plan document's "nothing ported yet" is out of date. The frames stall
   because the **GPU stops retiring work**: the kgsl watchdog prints
   `possible gpu syncpoint deadlock for context 4` with
   `queue=3123328, submit=3121536, start=3121536, retire=3121536` and 8-10 ms
   host-side submit times, the composer's kgsl timeline fence never signals
   (`mdss-fence: sync_fence_wait failed! ret = ffffff92`), SurfaceFlinger
   fakes vsync, and the display HAL inside system_server retries at 566 %
   CPU. Full evidence: `findings/gpu-retirement-stall-run261-2026-10-19.md`.
6. **Proposed next step, not authorized/executed:** the **GPU retirement
   stall** in the ported kgsl - why `submit`/`start`/`retire` freeze while
   the queue runs ahead, and why the host-side submit takes 8-10 ms. The
   port's dispatcher work is the only caller of
   `kgsl_process_event_groups()`, so the first evidence to collect is the
   kgsl debugfs state (dispatcher, fault count, per-context
   queue/submit/start/retire, pending event groups) plus the first submit
   freeze correlated with the kgsl fault/snapshot prints. Separately, and
   independently of the GPU, the port has no thermal feedback at all
   (`CONFIG_QCOM_TSENS` unset, the CPU nodes do not name their thermal zone,
   the shared OPP table has no cooling-device), which is why a 5.7-core
   spin at the top OPP kills the phone in about five minutes.
7. **Phone:** rooted stock `4.19.325-cip136-st20-perf-mglru-next-g5835eacd666d`,
   boot ID `7185f97b-862e-4d98-87ee-0d0850c36413`, root confirmed. The host
   did not request a recovery reboot; the user force rebooted. No flashing
   and no governor/frequency writes were performed.
8. **Committed checkpoints:** binding `2d56bc749`, mailbox `22529fab4`, APCC
   `931064e41`, diagnostic declarations/tests `9c1bc7000`, provenance
   `28d9cf677`, run260 handoff `e1e4c2d42`, analysis `3b3f9f660`, APCC
   hardening `647bd6404`, then the run261 evidence commit. No
   attribution/sign-off tags or push. Pre-existing PMIC/S5/AVS/CPR-table,
   init and unrelated documentation changes deliberately remain uncommitted;
   do not discard them.
9. **Exact artifact:** snapshot60 `boot-run261.img` (gitignored, keep the
   file), output `../ack-out-run261`, staged source `../ack-staged-run239`,
   source manifest `run261-source-verification.json` (69625 files, only
   `drivers/clk/qcom/apcc-msm8953.c` changed against run260), config diff
   empty, DTB byte-identical to run260, schema messages identical (332).
10. **Do not reuse run259/run260/run261 capture helpers directly:** their
    artifact namespaces are occupied and their guards intentionally refuse
    overwrites. `run261-host-experiment.py` reuses the SHA-pinned reviewed
    `run259-host-experiment.py` in the run261 namespace. For a package-only
    control use a real package-verification gate, not a fabricated build
    status. Preserve/hash current evidence before any approved preclear; start
    bounded capture before fastboot and poll identity through return to
    stock. Read the boot reference.
11. **Build hygiene, updated rule:** do not do clean builds unless required,
    and use the default `out` directory instead of a per-run output
    directory. The run261 build used the historical per-run layout
    (`../ack-out-run261`) because it continues that chain; the next build
    should follow the new rule.

The diagnostic restoration fixes W=1 declarations, not the boot failure. Do not
revert the CPU repair wholesale or resume speculative PLL/voltage edits. First
obtain fresh failure evidence or run the agreed single-variable control. Early
APCC failure can precede the ~5 s durable snapshot channel, so even restored
logging may be silent; silence alone cannot show Linux never executed.

Key files to read next: `run260-summary.json`, `run260-live/usb-capture.out`,
`run260-live/adb-timeline.jsonl`, `run260-live/pull-evidence.out`,
`run260-preclear.status`, `run260-build-verification.json`,
`run260-dt-comparison.json` under `artifacts/snapshot60/`, followed by the detailed
sections below. No further build, package or device operation is in progress.

## Run260: build/package passed; splash/reset with no fresh kernel evidence

Fresh cumulative Image.gz build and W=1 pstore/reboot/APCC/mailbox/SPM object
checks succeeded. The four missing pstore prototypes and unused file-pointer
errors from the initial run259 build are gone. Final vmlinux contains the five
diagnostic helpers; this does not prove their runtime execution.

Image SHA256 `5b521015c64e7ab8b36cbde2e73bbcca75b51a8a85b4fa72af94337045a5ff9d`,
kernel payload SHA256
`55f5ab11109abaa06dec2355d58a35b1cd96d1cffecea8bee46fcc5987ef958d`.
Banner: `#1 ... Mon Oct 19 20:54:21 +0545 2026`. Config has no diff from run258;
ramdisk/init/cmdline hashes match the real run258 base. All 69625 recorded source
hashes matched the checkout after the build. The build uses pending prerequisite
edits as documented in the commit map, not just the committed CPU changes.

APCC binding example compiled/validated through dt_binding_check. Inherited
global schema-processing and full-board validation findings remain; comparing
run258/run260 DTBs against the same processed schemas finds no new messages and
removes the two missing-MX-property findings. Build logs also retain unchanged
sorttable unused-global and reboot kernel-doc parameter warnings. Sparse absent.

The authorized RAM boot/capture completed after these checks:

- Exact image Sending and Booting both returned OKAY. User reports "Static
  splash, then reset". No port ADB identity was observed in 45 samples; stock
  returned at host +176.01 s, stock uptime 23.88 s. Stock policy/frequency values
  in that final sample belong to 4.19, not the port.
- Previous 64 MiB logdump and five early-logcat files were archived and verified
  before preclear; readback was proven zero. Post-attempt raw logdump is **still
  entirely zero**, 67108864 bytes, SHA256
  `3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351`.
  Device/local SHA match. No readable prefix, valid console/tail slots or reset
  record. Unlike run259, this is a verified zero result, not stale run258 bytes.
- The ACM gadget never appeared (expected for this init); its reader was stopped
  after stock returned. An empty USB stream is not a kernel-execution verdict.
  No recovery reboot was sent by the host; stock is rooted with fresh boot ID
  `770479a1-5951-4bf3-92e7-d382aaa24d83`.

**No fresh run260 kernel banner or failure cause is established.** Bootloader
acceptance is proven; Linux execution/stage of failure is not. Restoring the
diagnostic interfaces did not make this image reach an observable port boot.
This does not identify a CPU clock, rail, CPR, genpd or other step as the cause.
The pre-snapshot blackout still applies.

See `run260-summary.json`, `run260-build-verification.json`,
`run260-dt-comparison.json`, `run260-preclear.status`,
`run260-panel-observation.txt` and `run260-live/` under snapshot60. Existing raw
records and base images are preserved. No second boot was attempted.

Proposed next isolation, **not packaged or booted yet**: reuse the exact run260
kernel/DTB/ramdisk/init and append only
`initcall_blacklist=apcc_msm8953_driver_init`. The function is present in the
matching vmlinux, CONFIG_KALLSYMS is enabled, and the target init/main.c handles
exact function-name blacklisting, cross-checked with ACK and upstream docs.
The header command line would be 502 bytes, below the 512-byte limit, without
dropping any inherited parameter. This skips APCC registration/MX acquisition/
handoff as one path; CPUFreq is expected to remain absent and firmware CPU4 may
remain on XO. It is an isolation control, not a performance fix. A successful
control would narrow the failure to that path, not identify the individual step.
Obtain approval before consuming another boot cycle.

## Diagnostic restoration after the user-built run259 (run260 build started)

User agreed to restore/reconcile the diagnostics. Preserved staged changes in
`artifacts/snapshot60/run259-user-capture/` before restoring the implementations
and the QSEE/GPU/reboot call sites from the checkout. APCC source hash remains
identical to the recorded run259 source; this batch does not change CPU behavior.

- Four diagnostic helpers now have shared **non-static** declarations in
  `include/linux/pstore_ram.h`, included by their consumers. Removed the local
  static prototypes from ram.c; all five diagnostic exports, including reset
  note, remain. The file-lifetime pointer is kept and marked `__maybe_unused`
  instead of commenting out its declaration/assignment.
- Checkout and staged kernel sources are reconciled. Witness-open, stage-queue,
  snapshot-commit and both reset-decoder suites pass. Their host mocks needed
  the pre-existing cadence-wakeup helpers and the current enum's invalid upper
  bound (5 is now a valid panic-snapshot marker); no kernel behavior was changed
  to satisfy these tests. Strict checkpatch passes. Results:
  `findings/run260-diagnostic-restoration-checks.log`.
- Authorized fresh build/package is running via
  `artifacts/snapshot60/run260-build-host.sh`, output `../ack-out-run260`, config
  and real ramdisk base from run258, unchanged init-run257. No run260 boot yet
  at the time of this entry. Inspect `run260-build.status` and `run260-build.log`
  rather than inferring success. New build requires diagnostic symbols in the
  final vmlinux as well as embedded Rust/ashmem/CPUFreq guards.
- One-shot capture helper `artifacts/snapshot60/run260-host-experiment.py` reuses
  the SHA-pinned reviewed run259 capture script in a fresh namespace. It requires
  `status=0`, rooted stock, pyserial, and no old observer; preserves all existing
  evidence before preclear, RAM-boots (never flashes), observes through kernel
  uptime 480 s, recovers stock and pulls raw logs. Run it only once after review.
  Pyserial was restored at `/tmp/opencode/run258-diagvenv`, still ephemeral.

No change here closes the pre-snapshot early-panic blackout. An empty/stale
capture is not a claim that the bootloader never entered Linux. No boot-failure
cause has been established. Do not reuse run259 or alter its preserved evidence.

## User-built run259: splash/reset reported; recovered evidence is entirely stale

The next build/package/boot was authorized. The agent's initial fresh run259
build stopped at W=1 pstore errors (four missing helper prototypes and an unused
witness-file variable); **no image or boot was produced by that invocation**.
The user subsequently changed sources/staging, built and booted run259 themselves,
and reported static splash followed by reset, without an Android/port ADB window.
The exact fastboot Sending/Booting transcript has not been supplied, so kernel
execution in that attempt is not independently established.

- User image `artifacts/snapshot60/boot-run259.img` SHA256
  `6fa41d995d9d2f6ebded85c933611d4b01d0be478a866ed677416771f5fb1a71`
  matches `package-run259.json`, including its embedded kernel payload hash.
  The kernel banner is `#2 ... Mon Oct 19 17:45:43 +0545 2026`; output Image.gz
  matches the archived kernel. Rust, ashmem, APCC, CPUFREQ_DT, APCS mailbox and
  RPM/genpd are enabled. Ramdisk/init/command line match run258. New APCC handoff
  messages exist in the binary; the old pstore CPU4-switch string does not.
- Read-only recovery found the phone already on rooted stock, boot ID
  `a0764a72-cac2-43f8-b0fa-e78fd5fa7fe4`. No reboot, flash, log clearing or retry
  was performed by the agent after the user's report.
- The recovered **entire 67108864-byte logdump is identical to run258**:
  SHA256 `a4c095fb0d333237f0109996c4b1187dde8de5d1f653afb9a40049cdd4594742`.
  Device hashes before/after retrieval match it. `run259-logdump.log:4` still has
  run258's `#1 ... 15:19:00` banner; ACKRESET1 is the old host-requested run258
  recovery. **All recovered slots/logs are stale; none diagnoses run259.**
- Checkout and staged `fs/pstore/ram.c` differ. The stage comments out complete
  witness/stage/QSEE/reset-note functions and exports, not just print messages;
  helper symbols are absent from the user vmlinux. The checkout instead adds
  static prototypes to exported helpers and comments the witness-file declaration
  while leaving its assignment. The latter checkout state is not a reproducible
  representation of the shipped image. Neither source was overwritten. Both
  source copies, their diff, hashes, raw provenance and collector output are saved
  under `artifacts/snapshot60/run259-user-capture/`.

Removing those diagnostic implementations removes particular evidence channels;
it does **not establish the cause of the splash/reset**, nor prove Linux never
executed. The approved CPU repair also removed the functional early CPU4 clock
workaround and transferred it to APCC's later voltage-first handoff. That is a
separate behavior change requiring runtime evidence, not merely log reduction.

Before another scarce boot: reconcile the checkout/staged sources with the user,
restore required diagnostic interfaces using proper non-static shared prototypes
rather than deleting exports, and arrange fresh early evidence (the reference's
pre-snapshot blackout still applies). Do not rerun run259's helper: its namespace
now belongs to the user-built image/recovery and its build status records an older
failed invocation. Select a fresh run only after agreeing the diagnostic change.
No failure cause or runtime fix is confirmed for run259.

## After run258: approved ownership, MX and boot-handoff repair implemented

User approved this concrete source-repair batch after run258. **No kernel/object
build, staged-tree sync, packaging or phone operation followed that approval.**
Run258 remains the last device result, not a test of these new sources.

### Implemented changes

- `drivers/mailbox/qcom-apcs-ipc-mailbox.c`: MSM8953-specific match data reserves
  only the four-byte IPC doorbell at global-block offset 8. Its regmap is based
  at that address with register offset zero. CPU4's `0xb011050..0xb01105f` stays
  exclusively reservable by APCC; the DT global-block resource is not truncated
  or mutated. Other six match-data variants retain their full maps and offsets.
  All eight board mailbox consumers were checked: they use mailbox channels,
  not this regmap as an independent CPU clock provider.
- `apcc-msm8953.c`: preserves the coordinated private-PLL/shared-CPU/CCI
  transaction and AVS work. Adds the donor PLL's active-only MX SVS floor via
  existing `rpmpd` (`MSM8953_VDDMX_AO`, S7 level resource), not a guessed physical
  S7 voltage or another regulator driver. The driver refuses handoff/DVFS
  without successful MX activation/voting. This omission was found in source;
  it is **not an established cause of run258's lag**.
- Successful CPU regulator acquisition/enable, MX attachment/runtime reference/
  performance vote, and source-clock pins are intentionally retained for system
  lifetime. This built-in non-unbindable driver reuses them on probe retry.
  A separate genpd virtual device protects MX from the platform bus's ordinary
  failed-probe detach. Failed runtime resume detaches the not-yet-active virtual
  device so a cached runtime-PM error cannot poison the retry; no successful
  active/voted pin is detached. CPU corner and permanent rollback-fault state
  also survive replacement of probe-local state. Cleanup cannot drop their votes
  after a late CCF/provider-registration failure.
- APCC now performs a real voltage-first boot handoff before publishing clocks:
  validates firmware state, holds the old/parking/target corner, enables the APC
  supply, and uses the same transaction to select the lowest stock OPP
  (652.8 MHz on both clusters, CCI /2.5). It handles the observed GPLL0/XO split
  rather than rejecting it. Unknown sources, fractional/partial PLL states and
  above-stock CPU rates still fail closed. Every affected register has checked
  readback/rollback. Only CPU4's donor-documented branch-enable register is
  written; its enable bit is snapshotted/restored too. CPU0/CCI branch behavior
  is not invented. Failed restore retains conservative power and latches a
  fault across probe retries.
- `fs/pstore/ram.c`: removes the ad-hoc CPU4 GPLL0 switch/branch writer. The
  early CPU-register diagnostic remains read-only; ramoops persistence/reset
  capture is unchanged. This means a provider failure before handoff can leave
  CPU4 on firmware's XO: do not conceal such a failure with a diagnostic writer.
- CPU DTS/binding add the MX domain and name; Kconfig depends on the RPM/genpd
  providers and `apcc.config` explicitly requests QCOM_RPMPD. **The repaired
  binding now requires this MX dependency**; old DTBs without it are not a
  safe programming contract. Use the newly compiled board DTB with these sources.
  One shared eight-core OPP table and seven 652.8–2016 MHz OPPs are unchanged.
  No OC/UV, idle-state or TSENS change; no invented CPU-model branding.

### Fresh checks (source/host only)

`findings/cpu-bringup-after-run258-checks.log` records commands, statuses and
source SHA256 hashes:

- Seven host suites pass with GCC and Clang: APCC, new APCS-mailbox probe/send,
  SPM/AVS, S5 regulator, APM, memory-ACC and CPR table dimensions.
- APCC executes 49 stock-rate pairs and every one-shot MMIO failure at 245
  transition positions (78 + 78 + 89), plus 104 split-boot handoff positions:
  **349 injected positions**, along with timeout, persistent/silent-write-loss,
  missing MX, rail-enable failure, publication-failure retry and retained-fault
  tests. The original stronger voltage/ABORT tests remain.
- Mailbox test executes the real probe/send functions for all seven data
  variants and all 32 channels, checks exact physical IPC address/reservation,
  minimum/missing/short resources and mapping/regmap/controller/send errors.
- Strict checkpatch is clean for source/DTS/config and separately for binding;
  whitespace and added-line API scan are clean. Whole-file scan flags the
  mailbox's pre-existing `.remove_new` (valid on target 6.12), not a new defect.
- Standalone board DTS preprocessing/DT compilation and focused **new APCC
  schema validation** pass. `fdtget` verifies the compiled eight CPU clock IDs,
  common OPP phandle, seven OPPs, opp-shared and MX-AO specifier. Binding document
  validation passes. Existing board dtc warnings are retained in
  `findings/cpu-bringup-after-run258-dt.log`; this is not a clean full-board
  dtbs_check verdict or the full make dt_binding_check target.

Host mocks do **not** run the real CCF, genpd, runtime-PM, regulator or resource
core. Kernel compilation, Kconfig resync, Sparse (not installed), full binding/
board validation, runtime registration, actual frequencies/voltages/CPR control,
suspend and UI improvement remain **unverified**. Do not call CPU bring-up
complete on hardware or call the lag fixed. No new artifact/run number was used.

### Reviewed references and next authorized verification

- Donor `../oc-test/drivers/clk/msm/clock-cpu-8953.c:82-149,822-829,1042-1099`
  and `msm8953-regulator.dtsi:95-122` establish the PLL MX SVS/active-only vote,
  register offsets and CPU4 branch handoff. Online
  [LineageOS MSM8953 source](https://github.com/LineageOS/android_kernel_xiaomi_msm8953/blob/lineage-20/drivers/clk/msm/clock-cpu-8953.c)
  independently retains the MX dependency and early handoff. Its above-stock
  frequencies were not imported.
- [ACK rpmpd](https://github.com/aosp-mirror/kernel_common/blob/android16-6.12/drivers/pmdomain/qcom/rpmpd.c)
  confirms S7, active-only level and max aggregation. Target source was used
  for details; the online branch differs in pre-sync clamping.
- [ACK genpd](https://github.com/aosp-mirror/kernel_common/blob/android16-6.12/drivers/pmdomain/core.c)
  and [current upstream genpd](https://github.com/torvalds/linux/blob/master/drivers/pmdomain/core.c)
  confirm the independent virtual attachment/performance APIs. Target
  `drivers/base/power/common.c:143-166` explains why the normal attach wrapper
  rejects an already bus-attached device; this is why the genpd-specific API
  is deliberate here. Acquisitions, runtime-PM errors and detach paths were read.
- Read the complete donor transaction/power path and target cpufreq-dt/CCF/OPP
  wiring rather than treating host compilation as framework validation.

Next build, **only when separately authorized**: sync all changed kernel files,
including mailbox, pstore, Kconfig and CPU DTS/binding, not APCC alone. Preserve
the run258 config and a real verified base ramdisk; inspect config differences
and required symbols after resolution. Build W=1 objects/image, run Sparse if
available, and validate the new DT. A later separately authorized RAM boot must
prove mailbox clients still work, APCC binds and one CPUFreq policy covers 0–7,
all seven OPPs/readbacks and CCI ratio are correct, and voltage transitions have
no errors. Compare CPU load, ANRs and physical panel behavior against run258;
do not infer a performance fix just from a policy directory. No sustained
high-OPP stress with TSENS still off. Idle/suspend/thermal integration is a
separate unresolved gate, not implied by this DVFS repair.

## Run258: built and RAM-booted; APCC blocked by CPU4/mailbox resource overlap

User authorized build, package, boot and capture on 2026-10-19. No kernel-source
repair or second boot was performed during this test. Phone returned to rooted
stock `4.19.325-cip136-st20-perf-mglru-next-g5835eacd666d` after observation.

- Image: `artifacts/snapshot60/boot-run258.img`, SHA256
  `527a8bcbd8ee59d14b4a079ea44a192dd20b6a54e5ad97b53f8b15dd161e94fa`.
  Real run257 base SHA and package payload hashes were verified. Ramdisk, init
  and command line are unchanged; the new DTB contains the intended OPP sharing.
- Pinned installed Clang/libclang 23.1.3, Rust 1.99.0 and bindgen 0.73.2.
  BUIL_TISSOT.md's Clang 22 listing is stale; run257 already used Clang 23.1.3.
  Preserved run257's embedded configuration, with **no resolved config diff**.
  Rust, ashmem and CPUFREQ_DT remain built in. Fresh output: `../ack-out-run258`.
- Compared 69622 tracked source/binding files against `../ack-staged-run239`;
  synchronized APCC, its binding, diagnostic-init source and the checkout's
  pstore heartbeat change (10 -> 100). The packaged init remains `init-run257`;
  syncing its source does not mean a new init was built. Full source hashes and
  commands are in `run258-source-verification.json` and `run258-build-host.sh`.
- W=1 APCC/SPM objects and Image.gz build succeeded. Only reported C warnings
  were unused globals in host `scripts/sorttable.c`. Board DT compilation and
  CHECK_DTBS ran; validation is **not clean**, but old/new DTBs produce identical
  messages against the same processed schemas (`run258-dt-comparison.json`).
  APCC YAML `dt-doc-validate` and APCC/SPM host tests passed. Sparse unavailable.
- Archived and SHA-verified the previous 64 MiB logdump and five early-logcat
  files before removing those diagnostic logcat files and proving logdump zero.
  Fastboot Sending/Booting both returned OKAY. No partition was flashed.
- Fresh log banner is `#1 ... Mon Oct 19 15:19:00 +0545 2026`
  (`run258-logdump.log:4`), matching the new kernel. Live boot ID
  `9451acf1-ede3-441a-b705-d9f357a851c2`; 69 port ADB samples, first observed
  host +120 s/kernel uptime 95.93 s, last +481.87 s/uptime 458.80 s.
  `/dev/ashmem` exists; boot_completed reaches 1. User physically observed
  boot animation, then homescreen, severe lag and unresponsive touch.

### Reproduced blocker; correction to the resource review below

`run258-logdump.log:560-563` reports `-EBUSY` requesting
`0x0b011050..0x0b01105f`; cpufreq-dt remains deferred at `:594` and live policy
directories are absent. **Run257 already has the same failure at :560-563.**
This is CPU4's RCG, not CPU0's `0xb111050` window. The previous APM-disjointness
argument did not cover it and was insufficient grounds to dismiss all overlap.

`msm8953.dtsi:1788-1790` declares APCS mailbox `0xb011000..0xb011fff`;
`qcom-apcs-ipc-mailbox.c:90` reserves the full resource. APCC's exclusive CPU4
mapping (`apcc-msm8953.c:760`) requests an overlapping 16 bytes. ACK 6.12's
[mailbox source](https://raw.githubusercontent.com/aosp-mirror/kernel_common/android16-6.12/drivers/mailbox/qcom-apcs-ipc-mailbox.c)
and [upstream devres](https://github.com/torvalds/linux/blob/master/lib/devres.c)
cross-check the reservation behavior. APM's narrow reservation is disjoint,
but does not eliminate this separate mailbox conflict. Runtime resource-owner
dump was not captured; fix design must account for both consumers before edits.
The coordinated transaction/rollback implementation never reached registration
in this run and remains hardware-unverified.

### Lag evidence: CPU pressure and ANRs, not observed RAM exhaustion

Under `artifacts/snapshot60/run258-live/`:

- Two same-boot samples at uptime 258.08/264.71 s show 97.67% aggregate active CPU
  ticks over the interval (`lag-cpu-delta.json`). Load average rises 22.30 ->
  23.24. MemAvailable is 2341088/2386516 KiB, approximately 2.2–2.3 GiB.
- `lag-cpuinfo.txt:3-4` attributes 368% to SystemUI and 277% to system_server
  (100% represents one core). This is about 6.5 cores combined, not 645% of the
  entire eight-core machine. It does not prove the reason for their work.
- `logcat-final.log:5301-5333` records SystemUI service ANR after 60509 ms,
  zero memory-pressure totals, CPU some avg10=49.61, I/O some avg10=15.28, and
  heavy kernel CPU time. A second SystemUI ANR is at `:20664` (wait 60205 ms).
  These are ANRs, not proof of a native SystemUI crash. Captured native crash
  is instead the fingerprint HAL (`lag-crash.txt`).
- CPUFreq policies are absent throughout. Actual sustained CPU/GPU/CCI rates,
  reason for high kernel CPU time and the causal contribution of missing DVFS
  to lag remain **unverified**. Do not call this simply low frequency or RAM.

Capture limits: no ACM gadget appeared; USB log is empty and its reader was
terminated after bounded observation, not interpreted as a reset. Raw logdump
is 67108864 bytes with a 3413357-byte readable prefix, plus two CRC-valid console
and periodic-tail slots around 507 s. SD capture unavailable; kmsg overrun
markers mean some records were lost. Freshness also relies on verified preclear,
new banner and live boot identity, not CRC alone. Host-requested stock recovery
is recorded by ACKRESET1 at 507.58 s, PID1/init, command=shell; this is not an
unsolicited device reset. Final rooted stock identity is saved in the live dir.

Next: review the CPU4/mailbox resource ownership and propose the smallest safe
repair; obtain confirmation before kernel edits or another build/boot. Preserve
all run258 evidence. No DVFS/voltage/AVS runtime-success verdict is justified.

## Latest: coordinated repair implemented, not kernel-built or boot-tested

This section supersedes the proposed repairs in the historical audit below.
The user authorized the coordinated repair and review/reversion of their
concurrent edits where wrong. No kernel build or phone operation was performed.

- `drivers/clk/qcom/apcc-msm8953.c` now owns one complete CPU/CCI hardware
  transaction. The PLL/RCGs are private, not independently adjustable CCF
  parents. CPU0/CPU4 clock IDs alias one CCF clock/cache; CCI is read-only.
  Both IDs and all DT resources remain present. `recalc_rate` reads hardware.
- CPU PRE notifiers execute the transaction and can veto it through CCF.
  The provider `.set_rate` is intentionally side-effect-free: CCF drops its
  return value. POST releases the old voltage requirement, ABORT restores the
  snapshot. The notifier makes no top-level clock API calls. The target DT
  gives CPR4 no optional controller clocks; its NULL clock handles are no-ops.
- The old/target/parking corner maximum is retained while both CPUs and CCI
  change. All three park on rate-protected GPLL0 before PLL writes; CCI is
  placed at divide-by-2.5 before CPUs return to divide-by-1 on the APCS PLL.
  Register readback, PLL lock and all three resulting rates are checked.
- The PLL path uses donor integer-L changes and cold-init values, not an
  inferred alpha UPDATE/ACK protocol or a blind HUAYRA ops substitution.
  Probe reads its state without programming the APCS PLL/RCGs. Unsupported
  fractional, partial, split-cluster or above-stock boot states fail closed.
  The protocol is donor-derived but **not hardware-validated on the port**.
- Restore verifies saved PLL metadata/L and mux readback before lowering the
  rail. A failed restore holds the conservative voltage, logs the error and
  blocks subsequent hardware transactions. A failed final voltage decrease
  leaves the higher safe corner rather than undoing a completed frequency change.
- Boot corner is derived from actual CPU/CCI rates, then the CPR regulator is
  explicitly enabled before publishing clocks. Enabled input-source handles
  and exclusive-rate references are intentionally pinned for system lifetime,
  as these may already feed live boot CPUs. A deferred/failed probe reuses the
  pins, never runs a managed disable on a live source, and does not accumulate
  another enable/protection reference. This is a built-in, non-unbindable driver.
  Domain outputs themselves have no gate operations (including late-unused
  cleanup), so critical-clock registration/unwind cannot accidentally gate CPUs.
- `msm8953-spm.c` pauses autonomous AVS around reset/VCTL/data/status and
  restores it on success and error, under the existing raw lock. It preserves
  SAW4 AVS_LIMIT instead of applying the older SAW1.1 AVS-limit scheme.
- DTS now has `opp-shared`; stock OPPs remain 652.8–2016 MHz, TSENS unchanged.
  Binding text describes the coupled IDs and read-only CCI output; no new
  required properties or clock IDs were introduced.

### Concurrent user changes reviewed

- Kept the `current` -> `observed` local-variable rename: `current` expands
  as a kernel macro. Host tests now define that macro too, to catch recurrence.
- Kept the boot-state `dev_info()` print for diagnosing rejected handoff states.
- Reverted the switch to shared RCG mapping and its claimed APM conflict.
  Local `msm8953-apm.c:181-187` reserves only `0xb1112a8..0xb1112b3`, not the
  full DT window; the RCG at `0xb111050..0xb11105f` is disjoint. Restored
  exclusive managed resource mapping, and added EFUSE/PLL/RCG size validation.
  ACK `lib/devres.c::__devm_ioremap_resource()` confirms reservation is over
  the supplied start/size. Run256 had already reached wrapper registration
  after mapping this RCG, not an `-EBUSY` resource failure.

### Fresh checks and remaining gates

`python3 porting/build-test/test-msm8953-apcc.py` now executes the actual
transaction and notifier functions, rather than isolated vote helpers:

- All 49 pairs of the seven stock frequencies; both clusters and CCI; readback
  and request bounds; parking-source voltage requirement above the target.
- Cold/warm handoff and external veto/ABORT; voltage rejection with no clock writes.
- Every one-shot MMIO fault across warm downscale/upscale and cold initialization
  (73 + 73 + 84 = 230 injection positions).
- Persistent rollback failure; PLL timeout; silent RCG/L/output-enable write
  loss; silent rollback-L loss; failed POST voltage decrease; input-pin retry.

SAW host tests cover AVS pause/restore ordering, timeout and restore failure.
The transition audit entry point now runs the same stronger regression suite.
The original failing-audit log is retained as historical evidence. Fresh
results and source hashes are in
`porting/findings/cpu-bringup-batch-after-run256.log`.

Strict checkpatch on driver/DTS changes and separately on binding text is
clean; whitespace and the focused kernel API scan are clean. Host compilation
does not include all kernel headers/probe code and is not a CCF integration
test. **A real kernel/object build, Sparse, DT compilation/schema checks and
hardware validation are still outstanding. Do not call this boot-verified.**
No commit, staged-tree synchronization, packaging or boot cycle was performed.
Any next authorized build must use all changed source/DTS files, not a stale
staged tree, and retain a real known-good base ramdisk.

## Consolidated CPU-chain audit after run256 (2026-10-19)

**Do not treat a recalc-only fix as a boot-ready CPU DVFS implementation.**
The following are source-level defects or explicit review gaps, not claims
that each has manifested on hardware. Only the registration failure below
is the observed run256 blocker. No kernel source was changed during this
audit; existing uncommitted changes were preserved.

Run256 image/kernel SHA256 match `package-run256.json`; the embedded #10
build timestamp matches `run256-logdump.log:4`. At `:564-568`, CCF rejects
`apcc_cpu0` for its missing recalc operation. cpufreq remains deferred at
`:599`. S5 and CPR initialization messages are not proof of working DVFS.

### Priority batch: APCC/CCF and voltage ownership

All APCC references below are to `drivers/clk/qcom/apcc-msm8953.c` as audited.

1. **Registration:** `apcc_vdd_ops:292-295` lacks `.recalc_rate`. Add a
   transparent parent-rate callback, but only alongside the parent repair.
2. **Wrong parent at registration:** `apcc_register_mux:465-491` reuses
   `init` without clearing `parent_data` before setting `parent_hws`.
   `drivers/clk/clk.c:4315-4325` prioritizes `parent_data`, so the wrapper
   selects its first old parent (PLL), not its RCG. Use separate zeroed init
   structures or clear the obsolete parent representation.
3. **Rate-request parent escapes the wrapper:** `apcc_clk_determine_rate:226`
   forwards the original request into the RCG. Its determine callback writes
   the selected PLL/GPLL into `best_parent_hw`; this must not become the
   wrapper's direct parent. Use a separate forwarded parent request and keep
   the wrapper's own parent identity/bounds; compare CCF's leaf-mux tests at
   `drivers/clk/clk_test.c:2139-2152`.
4. **CPR rail is never enabled by APCC:** probe only obtains the regulator
   (`:520-524`), with no enable or matching cleanup anywhere in this provider.
   `cpr3-regulator.c:4203-4206,4225-4228` explicitly requires enable plus a
   valid corner; otherwise set-voltage merely stores the corner. DT does not
   make `apc_corner` boot-on/always-on. Establish a safe boot corner, enable
   the CPR supply with managed cleanup, and retain all running-domain votes.
5. **Unsafe downscale order:** `:254-267` replaces both old votes before
   lowering either clock. Donor `drivers/clk/msm/clock.c:686-717` holds old
   and new requirements across the rate operation, releasing the old vote
   only after success. Keep max(old,new) until both CPUs and CCI are safe.
6. **Rollback is not restoration:** `:258-270` unvotes to zero rather than
   restoring the old vote; it can retain a new lower sibling vote with both
   clocks still fast. `:282-289` can return after one cluster changes and its
   sibling fails. Snapshot/restore the complete coupled transition; if a
   hardware rollback itself fails, retain conservative voltage and report
   the actual state instead of advertising atomic success.
7. **CCF error contract:** ACK `drivers/clk/clk.c:2497-2516` does not propagate
   provider set-rate/set-parent callback returns to `clk_set_rate()` callers.
   APCC's voltage rejection inside `.set_rate` is therefore not an effective
   cpufreq veto. The transition design must use a failure-capable preflight
   and validated completion/error reporting; do not assume callback `-EIO`
   reaches OPP. Simply adding `CLK_SET_RATE_PARENT` would move parent changes
   before the wrapper's voltage vote, so it is not a standalone fix.
8. **RCG parent retuning:** RCG init has no `CLK_SET_RATE_PARENT`, although
   the generic RCG determine/set helpers search rounded parent rates. CCF
   only retunes a parent through `clk_calc_new_rates()` when that flag is
   set (`clk.c:2405-2407`). Fix as part of the voltage-first transition design,
   not by blindly adding the flag to the current wrapper scheme.
9. **CCI and notifier state:** all three muxes share the PLL, but the notifier
   (`:304-328`) only handles PRE, parks using cached `md->src`/`md->div` (not
   initialized from hardware at registration), swallows parking errors, and
   has no ABORT restoration. CCI has no DT consumer of `APCC_CCI_CLK`, so it
   gets neither a vote nor an explicit initial rate. A PLL retune can affect
   CCI regardless of CPU-only mirroring. Preserve donor CCI division/rate
   tracking and manage all three domains together; snapshot actual mux state
   and restore on abort rather than relying on zero-initialized caches.
10. **Missing clock lifetime ownership:** provider never prepares/enables or
    marks CPU/CCI clocks critical. cpufreq-dt obtains its clock but does not
    enable it (`cpufreq-dt.c:104-121`); OPP sets rate without doing so either.
    CCF can disable an unreferenced enabled PLL at late init
    (`clk.c:1470-1505`). Donor explicitly keeps CPU/CCI clocks prepared/enabled
    (`clock-cpu-8953.c:950-965`). Recreate ownership without gating live CPUs
    on probe failure/removal; this risk has not been reproduced on the phone.

### DT, PLL and SAW requirements in the same review

11. **Policy sharing:** `msm8953-cpu.dtsi:701-703` lacks `opp-shared`.
    Referencing the same OPP node alone does not create one cpufreq policy.
    `drivers/opp/of.c:1352-1356` returns a single-CPU mask without the flag;
    cpufreq-dt consumes it. Correct the table's declared coupled policy and
    test all eight CPUs' sharing mask. No voltage units or CPU-supply change.
12. **PLL handoff and protocol remain unresolved:** see the preceding-session
    section below. Unconditional L=34 programming and generic alpha UPDATE
    sequencing are not proven equivalent to the donor's integer-only path.
    Do not substitute HUAYRA/hwfsm ops on name or register layout alone.
13. **SAW drops donor AVS pause/restore:** `msm8953-spm.c:145-173` requests VCTL
    with AVS still enabled. Donor `msm-spm.c:542-619` saves AVS enable state,
    pauses it before reset/VCTL, and restores it on success and failure.
    CPR enables the AVS limit regulator during init and does not disable it
    around every voltage request. The CPU raw lock only serializes software,
    not the AVS hardware. Restore the donor pause/restore semantics while
    retaining SAW4 AVS_LIMIT (not the SAW1.1 bit-27 scheme). Actual contention
    or a resulting voltage failure on this phone remains unverified.

### Checked scope and limitations

- Read APCC, SAW4, APM, memory-ACC and S5/AVS operations; traced CPR enable,
  voltage changes and DT/cpufreq wiring. Diffed CPR3 core/util and CPR4 APSS
  against the local donor: most changes are mechanical or CPR3-only paths.
  The 32 shared CPR numeric properties match the donor source after the
  earlier table fixes. No additional active-path APM/memory-ACC defect was
  established in this audit, which is not a proof they are bug-free.
- Inherited fault-path follow-up: `cpr3-util.c:175-178` does not test
  `devm_ioremap()` for NULL before reporting fuse mapping success. Run256
  reads fuse values, so this is not the observed boot blocker.
- Duplicate regmap debugfs names are visible (`run256-logdump.log:563`), but
  do not confuse that observability warning with the CCF ops rejection.
- Ran the skill API scan on all eight reviewed C files. Its findings are
  allocation-style heuristics explicitly for v7.0+, not defects in 6.12.
  Generated the kernel documentation index; reviewed local clock/OPP docs.
- Host tests pass for APCC plan/vote helpers, S5 arithmetic, APM, memory-ACC,
  and CPR dimensions. SAW host test initially failed to compile because its
  mock lacked READ_ONCE/EPROBE_DEFER; the mock now includes them and checks
  readiness as well. None of these tests proves CCF or device behavior.
- New `python3 porting/build-test/audit-msm8953-apcc-transitions.py` extracts
  the actual set-rate callback and adds host clock faults. It intentionally
  exits nonzero on the current implementation: three failures (downscale
  order, old-vote retention after clock failure, sibling rollback). Keep
  this audit until a replacement transition path passes it or replaces it
  with equivalent stronger tests. Original helper tests still pass, showing
  why they were insufficient.
- No kernel build, DT compile/schema validation, Sparse, KUnit/CCF runtime
  test, phone access or boot. Donor source is not a known-good port image;
  the findings above do not claim any unobserved hardware regression.

### Cross-check sources and proposed next batch

- [ACK clock core](https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/drivers/clk/clk.c)
  (parent precedence, rate propagation and callback error handling).
- [ACK OPP sharing](https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/drivers/opp/of.c)
  and [upstream OPP binding](https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/opp/opp-v2-base.yaml).
- [Current upstream clock core](https://github.com/torvalds/linux/blob/master/drivers/clk/clk.c)
  agrees on parent-data precedence; target behavior was checked in ACK itself.
- [AOSP CPR enable contract](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-wahoo-4.4-oreo-dr1/drivers/regulator/cpr3-regulator.c)
  and [AOSP SAW AVS handling](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-wahoo-4.4-oreo-dr1/drivers/soc/qcom/msm-spm.c).

Propose one reviewed repair series, not thirteen boot experiments: fix APCC
registration/request topology, implement coherent shared CPU/CCI voltage and
clock transactions with failure-safe preflight/rollback and boot ownership,
settle integer-PLL handoff, declare OPP sharing, and restore SAW AVS request
protection. Primary files: `apcc-msm8953.c`, `msm8953-cpu.dtsi`,
`msm8953-spm.c`, and focused host/CCF tests. Obtain confirmation for the
concrete design before rewriting the source. Build/boot remain separately
authorized operations. Keep stock 652.8–2016 MHz and TSENS off.

## Run255 and APCC follow-up (supersedes the run254 next action)

- `run255-logdump.log:486-491` reaches target-quotient calculation, aging init
  and the default HW closed-loop mode message. APCC reaches its speed-bin
  message (`:560`) but fails PLL setup with `-EINVAL` (`:563`). cpufreq
  remains deferred (`:597`). This is not proof of runtime closed-loop control.
- Both APCC MMIO configs omitted `reg_bits` and `val_bits`; ACK 6.12 rejects
  the zero register width before MMIO access. Both now specify 32-bit register
  and value widths, with stride 4. This correction is not built or booted.
- The PLL notifier now uses `devm_clk_notifier_register()`. It is acquired
  after its managed clock handle and the clocks, so reverse-order devres
  cleanup unregisters the callback before releasing those objects or APCC
  state, including on a later probe failure. This is a lifetime fix, not a
  claimed cause of run255's failure.
- `test-msm8953-apcc.py` covers the config fields and managed-notifier call
  at source level, in addition to the existing host plan/vote arithmetic.

### PLL semantics: do not switch ops based on the register layout alone

The donor's `clock-cpu-8953.c:1053-1068` selects
`clk_ops_variable_rate_pll_hwfsm`. Its `clock-pll.c:771-817` rounds to whole
19.2-MHz multiples and changes only L, with donor enable/disable callbacks.
Those callbacks (`:547-594`) are not equivalent to ACK's similarly named
`clk_alpha_pll_hwfsm_ops`: the donor disable normally only delays, while ACK
clears the hardware FSM enable bit. Names and offsets do not prove equivalence.

The current port still uses `clk_alpha_pll_ops`, which can program alpha/VCO
and use the UPDATE/ACK latch protocol. The HUAYRA alternative has different
signed-alpha arithmetic and live-update restrictions; switching to it is not
justified by the donor's integer-only path. PLL operations are unchanged.

Another handoff difference remains: the donor reads the existing L value
before choosing initialization, while `apcc_register_pll()` unconditionally
calls `clk_alpha_pll_configure()` with L=34 before its notifier is registered.
Safety of this on a bootloader-running CPU PLL is **unverified**. Resolve
handoff and rate-change sequencing before calling the next image boot-ready;
do not use a boot to choose between unreviewed PLL-operation variants.

Online cross-checks:
[ACK managed notifier](https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/drivers/clk/clk.c),
[AOSP vendor integer PLL path](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-wahoo-4.4-oreo-dr1/drivers/clk/msm/clock-pll.c).

## Latest state (run254; supersedes the original blocker below)

- Run252 reached the S5 child probe (`run252-logdump.log:409`) after the
  PM8953 two-USID match fix, but its type read returned `00/00`.
- The regulator's 8-bit base regmap truncated absolute addresses such as
  `0x2004`. Switching to the 16-bit extended API let run253 register S5 at
  870000 uV, AUTO, 1200 uV/us (`run253-logdump.log:409-410`). Run254 repeats
  that result (`run254-logdump.log:409-410`).
- Run253 rejected the misc-fuse table's 240-byte length (`:494`). Restoring
  four omitted donor zeros made it 256 bytes; run254 progressed to floor
  limiting instead.
- Run254 rejects `qcom,cpr-floor-to-ceiling-max-range`: 968 bytes versus
  accepted lengths 28, 128 or 1024 (`run254-logdump.log:492-495`). Seven
  speed-bin-7 revision rows lacked two `50000` cells each. Those 14 donor
  cells are now restored locally: 256 cells / 1024 bytes, runtime unverified.
- All 32 shared CPR numeric source properties now match the donor's
  `arch/arm64/boot/dts/vendor/qcom/msm8953-regulator.dtsi`. This is not a
  comparison against the donor's compiled/live DT or its board OC overrides.
- `python3 porting/build-test/test-msm8953-cpr-tables.py` checks the source
  table dimensions. Negative checks confirmed it rejects truncation of both
  previously failing properties. The existing SPM arithmetic test also passes.
- Run254 image/kernel hashes match `package-run254.json`. Its embedded banner
  matches the log, but is unchanged from run253 (#9, 09:31:38); the kernel
  payload hashes differ, consistent with a DT-only change.
- Next authorized build/boot: verify CPR4 binds, then APCC and cpufreq. No
  kernel build, DT schema validation or boot was performed for this correction.
  APCC/cpufreq remain deferred in run254 (`:1076-1079`).

Source cross-check: the AOSP vendor
[CPR parser](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-wahoo-4.4-oreo-dr1/drivers/regulator/cpr3-util.c)
uses the same corner/speed-bin/fuse-combo property length checks as this port.

## Original handoff and investigation history

Audience: the next model picking up this port. Everything below is observed, with
the evidence path named. Nothing here is inferred unless marked `[INFERENCE]`.

Repo: `/home/kurision/development/kernel/ack-kgsl` (Linux 6.12.93-4k + CAF/vendor
kgsl, board `msm8953-xiaomi-tissot`). Donor tree for hardware truth:
`/home/kurision/development/kernel/oc-test` (working CAF kernel, boots this phone).

## Bottom line

The S5/APC regulator **never probes because its parent SPMI PMIC never binds** in
run251. USID 1 is confirmed against the live stock device tree. Source review
found that `qcom,pm8953` was missing from the PMIC match table, causing fallback
to `qcom,spmi-pmic` with one USID and a revision read on USID 1. The donor skips
revision reads on odd USIDs. A two-USID match entry is now added locally; it has
not been built or booted. Whether the rail driver works afterward is **unverified**.

## Observed failure and source-level explanation

1. `pmic@1` (USID 1, PM8953) is created by the SPMI core as spmi device `0-01`, but
   it **never binds** the `pmic-spmi` driver. Live sysfs on the port kernel:
   `readlink -f /sys/devices/platform/soc@0/200f000.spmi/spmi-0/0-01/driver` returns
   the path itself (unbound), while `0-00`, `0-02`, `0-03` all resolve to
   `/sys/bus/platform/drivers/spmi_pmi_arb` / `pmic-spmi`.
2. The reason, from the kernel log of run251
   (`porting/artifacts/snapshot60/run251-logdump.log:240`):
   ```
   3,231,1608417,-,caller=T1;pmic-spmi 0-01: error -ENODEV: failed to read PMIC revision
   ```
    This reports a revision-load failure, not an S5 register-read failure.
3. Source tracing: `pmic_spmi_load_revid()` first reads `PMIC_TYPE` at `0x104`.
   The missing specific match selected `N_USIDS(1)`, so USID 1 incorrectly took
   this path instead of copying revision information from USID 0.
   `pmic_arb_offset_v2()` forms PPID `0x101` for that read; S5 at `0x2000`
   uses the distinct PPID `0x120`. `pmic_arb_ppid_to_apid_v2()` returns
   `-ENODEV` when the requested mapping is absent. This source path explains
   the logged errno, but no runtime trace identifies the exact failed read.
   **The log does not establish that all USID 1 APIDs are absent.** Earlier
   references to `:1078` and `:1148` were incorrect for this working tree.
4. `pmic-spmi`'s probe ends with `devm_of_platform_populate()`
   (`drivers/mfd/qcom-spmi-pmic.c:315`). No bind ⇒ **no platform devices for any
   PMIC child**. Live proof: `ls .../spmi-0/0-01/` contains only
   `of_node power subsystem uevent waiting_for_supplier` — no `spm-regulator@2000`,
   while `0-00` lists `adc@3100 gpio@c000 pon@800 rtc@6000 temp-alarm@2400`.
5. No rail platform device ⇒ `qcom-msm8953-spm-regulator.c` probe never runs ⇒ no
   `pm8953_s5`, no `pm8953_s5_avs_limit`, no `apc_corner` ⇒ CPR4, the APCC clock
   controller and `cpufreq-dt` defer forever. Live sysfs on run250/run251:
   `/sys/class/regulator/` has 26 entries, none of them `pm8953_s5`;
   `/sys/devices/system/cpu/cpu0/cpufreq` does not exist.
6. The deferred chain, from the same log (`:1063` and the two lines after it):
   ```
   platform b018000.cpr4-ctrl: deferred probe pending: ... /pmic@1/spm-regulator@2000/avs-limit-regulator
   platform b116000.clock-controller: deferred probe pending: ... /cpr4-ctrl@b018000/thread/regulator
   platform cpufreq-dt: deferred probe pending: (reason unknown)
   ```
   `apc_mem_acc_corner` (regulator.2, `19461d4.regulator`) **does** bind — the rest
    of the bring-up stack is not thereby proven functional.

### What the run248 capture misled us into

run248's logdump had **no** "unsupported SMPS type" message, which read as "the USID
1 fix worked". It did not: the rail driver was never called. Absence of the old
error was absence of any probe. The error is now visible only because the SPMI PMIC
driver reports its own probe failure.

## Changes in the working tree (uncommitted, checkpatch clean)

| File | Change |
|---|---|
| `drivers/mfd/qcom-spmi-pmic.c` | Follow-up: added `qcom,pm8953` with `N_USIDS(2)` so USID 1 copies base revision data instead of reading its own revision peripheral; runtime unverified |
| `drivers/mfd/qcom-spmi-pmic.c` | `pmic_spmi_probe()` now uses `dev_err_probe()` for both revid-failure paths — previously a failed PMIC probe returned the error silently, which is what hid this for many runs |
| `drivers/regulator/qcom-msm8953-spm-regulator.c` | `devm_msm8953_spm_get()` failure now reported via `dev_err_probe()` instead of a bare `return PTR_ERR()` |
| `scripts/initramfs-diag/init.c` | diagnostic-init rc: added `ack-kmsg-dump` service (see "log access" below) |

`porting/HANDOFF.md`, `porting/README.md`, `porting/REFERENCE-boot-testing.md` and
`porting/FAILING-COMPONENTS.md` were already modified before this session; leave
them alone.

## Todos

### Follow-up source cross-check (2026-10-19)

- Donor `../oc-test/drivers/mfd/qcom-spmi-pmic.c:138-142` skips revision
  reads on odd USIDs and populates their children.
- [ACK android16-6.12 PMIC driver](https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/drivers/mfd/qcom-spmi-pmic.c)
  and [current upstream PMIC driver](https://github.com/torvalds/linux/blob/master/drivers/mfd/qcom-spmi-pmic.c)
  use per-compatible USID counts and copy base revision data for secondary
  USIDs. Both checked sources also lack the PM8953-specific entry; the local
  change is not a claimed upstream fix.
- Local binding already accepts `qcom,pm8953`; both nodes in `pm8953.dtsi`
  use that compatible plus the generic fallback. No DT or ABI change is needed.
- The existing base lookup holds a device reference, copies revision data under
  `pmic_spmi_revid_lock`, releases the reference, and defers if base driver data
  is absent. This change reuses that path without changing locking or cleanup.
- Host assertions checked compatible selection and PPID arithmetic. Build,
  Sparse and runtime verification remain outstanding; no device operation was
  performed for this follow-up.

### Next actions

1. **Validate the PM8953 two-USID match fix** when a build and boot are authorized.
   First check that `0-01` binds and its S5 child is created. Do not change the
   arbiter based solely on the failed revision read. If S5 itself then fails
   APID resolution, investigate its actual PPID `0x120`, cheapest checks first:
   - compare `drivers/spmi/spmi-pmic-arb.c` + its DT against the donor's
     `oc-test/drivers/spmi/spmi-pmic-arb.c` and the donor's `spmi@200f000` node
     (`qcom,bus-ee`, `qcom,num-ee`, APID scan limits);
   - check the arbiter's APID scan bounds: `bus->apid_data` is sized
     `pmic_arb->max_periphs` and `pmic_arb_find_apid()` only scans what the hardware
      table reports — check the requested peripheral's mapping, not an entire
      USID inferred from a revision-read failure;
   - print the APID scan result once (dev_info in `init_apid`) to see which PPIDs
     the hardware actually reports.
2. **Once the PMIC binds**: verify `pm8953_s5` and `pm8953_s5_avs_limit` appear in
   `/sys/class/regulator/`, then CPR4, then the APCC clock controller, then
   `scaling_available_frequencies` must contain `2016000000` and `related_cpus` all
   eight CPUs (stock fused top; no OC, settled with the user).
3. **GPU/DevCheck inventory** (plan step 5, still open). kgsl attributes exist on
   the port kernel: `/sys/class/kgsl/kgsl-3d0/{gpu_clock_stats,gpu_busy_percentage,
   default_pwrlevel,clock_mhz,max_clock_mhz,freq_table_mhz,...}` — but reading them
   needs root, so this must wait for root or for a shell-readable copy.
4. **Live kernel log without root** (in progress, see below).
5. Deferred by plan: retire the pstore diagnostic clock writer once cpufreq works.

## Log access: state of play

Goal: read dmesg from the *running* port kernel instead of logdump round-trips.

- `adb root` does not stick (port kernel adbd stays `uid=2000(shell)`).
- `logcat -b kernel` does not exist on this ROM: `logcat -g` lists only
  `main/system/crash`, so the `ack-kernel-log` service added in run250 sat in
  `init.svc.ack-kernel-log=restarting`.
- The rc service without `seclabel` (run251, `ack-kmsg-dump`) is refused by SELinux:
  `run251-logdump.log:3199` — *"File /system/bin/sh … no domain transition from
  u:r:init:s0"*. So the shell domain cannot be borrowed, and `u:r:shell:s0` cannot
  read `/dev/kmsg`.
- Magisk was tried and **failed**: `magiskboot`-patched image
  (`magiskinit` as `/init`, port init moved to `.backup/init`) boots the kernel fine
  (kernel log reaches 13.5 s, no panic — `run249-ramoops-slot0-*.log`) but userspace
  never starts and the board falls back to stock. Not worth more boot cycles.
- Working channel, unchanged: DIAG init captures kmsg into the `logdump` partition
  continuously; read it after rebooting to stock with
  `porting/logging/pull-run-evidence.sh`. That is what produced every finding above.
- Cheapest remaining idea `[INFERENCE]`: have the DIAG init itself (it already runs as
  PID 1 in `u:r:init_su` and already reads `/dev/kmsg`) tee the same stream into
  `/data/local/tmp/ack-kmsg.log` once `/data` is mounted. One userspace rebuild, no
  kernel rebuild.

## Boot/evidence loop (works, use it verbatim)

All commands from `porting/artifacts/snapshot60/`. Never flash: `fastboot boot`.

```sh
# 1. stock up, clear the 64 MiB logdump (needs su: stock only)
bash ../../logging/clear-logdump.sh <run>

# 2. package (kernel dir + new init)
python3 -B ../../logging/package-diag-boot.py --base-image boot-run237.img \
  --kernel-dir kdir-run<run> --init init-run<run> --keep-stock-console \
  --append-cmdline ' earlycon console=ttyMSM0,115200' \
  --out boot-run<run>.img --report package-run<run>.json

# 3. RAM boot
adb reboot bootloader && sleep 15 && fastboot boot boot-run<run>.img
# adb is back ~35-90 s later on the port kernel (6.12.93-4k); ~140 s means it reset

# 4. back to stock, then pull
bash ../../logging/pull-run-evidence.sh <run> boot-run<run>.img
```

Evidence files land beside them as `run<N>-logdump.log` (full DIAG-format kmsg, the
one to grep) and `run<N>-ramoops-slot*.log` (CRC-verified console snapshots).
**Match the banner** (`Linux version 6.12.93-4k … #<n> SMP PREEMPT <build time>`)
against the kernel you booted before believing any line of it — this has already
produced one false "reset" conclusion.

## Kernel build (incremental, ~55 s for a driver-only change)

```sh
cd /home/kurision/development/kernel/ack-kgsl
# sync every touched .c/.h/.dtsi into the staged tree first (a stale staged tree
# has already made two boots report an already-fixed error)
S=/home/kurision/development/kernel/ack-staged-run239
for p in drivers/mfd/qcom-spmi-pmic.c drivers/regulator/qcom-msm8953-spm-regulator.c; do
    cmp -s "$p" "$S/$p" || cp "$p" "$S/$p"; done
cat scripts/tissot-ack.config porting/build-test/apcc.config > /tmp/tissot-apcc.config

TC=/home/kurision/.rustup/toolchains/stable-x86_64-unknown-linux-gnu
export RUSTC="$TC/bin/rustc" HOSTRUSTC="$TC/bin/rustc"
export BINDGEN=/home/kurision/.cache/run164-bindgen0732/bin/bindgen
export RUST_LIB_SRC="$TC/lib/rustlib/src/rust/library" LIBCLANG_PATH=/usr/lib
export RUSTFLAGS_AUTOFDO_CLANG='-Zdebuginfo-for-profiling -Cllvm-args=-enable-fs-discriminator=true -Cllvm-args=-improved-fs-discriminator=true'
ACK_TREE=$S FRAGMENT=/tmp/tissot-apcc.config \
OUT_DIR=/home/kurision/development/kernel/ack-out-run244 JOBS=12 \
./scripts/build-ack-tissot.sh
```

Diagnostic init (userspace only, seconds):

```sh
aarch64-linux-gnu-gcc -Os -static -DANDROID_CAPTURE -DANDROID_EARLY_LOGCAT \
  -DBOOT_DEADLINE_SECONDS=0 scripts/initramfs-diag/init.c \
  -o porting/artifacts/snapshot60/init-run<run>
```

Before every commit: `git diff | perl scripts/checkpatch.pl --strict --no-signoff -`
must print `0 errors`. Never add `Signed-off-by:`.

## Files that matter

| Path | Why |
|---|---|
| `drivers/mfd/qcom-spmi-pmic.c` | the silent probe that hid the fault; `:315` populate |
| `drivers/spmi/spmi-pmic-arb.c` | `pmic_arb_offset_v2()` forms peripheral-specific PPIDs; `pmic_arb_ppid_to_apid_v2()` reports missing mappings |
| `drivers/regulator/qcom-msm8953-spm-regulator.c` | S5/APC rail; `:627` `qpnp_smps_check_type()` |
| `arch/arm64/boot/dts/qcom/msm8953-cpu.dtsi` | `:78` S5 rail node under `pmic@1`, SAW4, APCC clock controller, OPP |
| `drivers/clk/qcom/apcc-msm8953.c` | `:231` `apcc_clk_set_rate()`; needed once the rail binds |
| `porting/build-test/apcc.config` | bring-up fragment (`CONFIG_CPUFREQ_DT=y` included) |
| `porting/REFERENCE-boot-testing.md` | tooling and pitfalls; read before any boot cycle |
| `porting/logging/{clear-logdump.sh,pull-run-evidence.sh,package-diag-boot.py}` | the loop above |

## Ground rules from the user and the repo

- Store pulled logs and evidence **in the repo** (as `run<N>-*` files), not in `/tmp`.
- Boot cycles are the scarce resource: one change per boot, read the banner, never
  trust a capture that was not matched to the image that produced it.
- `AGENTS.md`: for this kernel, check Android common kernel sources before upstream
  Linux, and cross-check edits online when acting as a free model.
- The device is shared. After collecting evidence, reboot to stock and confirm
  `uname -r` = `4.19.325-cip136-st20-perf-mglru-next-g5835eacd666d`.
- Scope stays stock fused range only, 652.8–2016 MHz, no OC. TSENS stays off; do not
  add thermal sensors in this work.
