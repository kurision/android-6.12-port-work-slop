# snapshot43 findings through run 11 — console timing, interrupted-SMC ABI, and capture endpoints

> **Historical record - 2026-10-09.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

Date: 2026-10-09. Kernel tree `ack-android16-6.12`, out dir `out-snapshot43`
(donor reference: `../kernel_xiaomi_msm8953`). Artifacts in
`porting/artifacts/snapshot43/`. Nothing was flashed; every boot was
`fastboot boot` on slot `_a` (device 2819f2320604).

## 0. Executive summary

1. **Small-request interrupted returns preserve x1–x5.** The two run-3
   requests and two run-11 requests (4 and 24 bytes per run) preserve these
   registers on their first interrupted returns. ACK original-argument and
   donor returned-register feedback agree for the next resume's x0–x6 in
   those observations. Returned x4/x5 for the repeatedly interrupted
   1164-byte request remain unobserved; this is not firmware-wide equivalence.
2. **Console-associated slowdown is real, but printk intervals are not
   firmware-only timing.** Matched first-request `qsee_send_desc` markers are
   396.269012 s in run 2 and 77.403896 s in run 3, a 318.865116 s difference.
   This is neither boot completion nor an isolated causal measurement.
   Run-3 small-request timing pairs are given in §2, not extrapolated to
   the third request or to a universal per-print cost.
3. **Capture ends; subsequent kernel state is unobserved.** Neither
   recorder-first causality nor a kernel-wide halt is proved. The retained
   output contains no relevant late failure diagnostic; detector execution,
   qualifying conditions, output retention, and subsequent reset cause
   remain unobserved.
4. **Third-request coverage differs by run.** Run 1 captures repeated SMC
   interruptions for the 1164-byte request. Run 2 captures preparation
   through spilling at 423.164424 s. No-tty0 run 8 reaches its send path at
   94.610903 s and ends at `qsee_send` 94.611040 s, before a captured raw
   SMC entry/return. Run 11 has no captured 1164-byte request.
5. **Run 11 shows execution after the durable-prefix cutoff, not a proved
   spill/reclaim blocker.** Its saved witness is conditionally at 93.920 s,
   durable last record at 94.713096 s, and USB last record at 98.625345 s.
   The next five-second witness opportunity lies beyond that USB tail.
   Spillfix lazily allocates on first use; causality remains unproved (§8).

## 1. Interrupted-register evidence and its scope

`scm_capture_result_regs()` captures x0–x7 for the first three attempts per
traced invocation (`SCM_SMC_INT_CAPTURE_ATTEMPTS == 3`). The actual predicate
is `desc->owner == 48 && desc->svc == 0`, not an exclusive keymaster-name
test (`drivers/firmware/qcom/qcom_scm-smc.c:79–170,299`). ACK retains original
x1–x5, resubmits interrupted x0, and feeds returned x6 through the A6 quirk.

Run 3, keymaster pid 352, cmd 6 (whitelist, 7 args, request lengths 4 and 24):

```
attempt=1 x0=0x1 x1=0x8887 x2=0x10001 x3=0xf9370000 x4=0x4  x5=0xff011000 x6=0x1 x7=0x0   <- INTERRUPTED
attempt=2 x0=0x0 x1=0x0    x2=0xee01 x3=0x10001    x4=0x0  x5=0x0        x6=0x0 x7=0x0   <- SUCCESS
```

The first interrupted return preserves x1–x5 and returns x6=1 as session
state. Success changes x1–x5, including x4/x5 becoming zero; no further
interrupted resume follows that success. Both run-3 small requests and both
run-11 small requests complete in two attempts
(`run3-usb.log:3434–3437,3457–3460`;
`run11-usb.log:3382–3388,3404–3410`).

**Conclusion:** ACK original-argument and donor returned-register feedback
agree for the next resume's x0–x6 in these four small-request observations.
The donor's in-out r0–r6 operands feed returned registers
(`../kernel_xiaomi_msm8953/drivers/soc/qcom/scm.c:97–134`), while ACK retains
original x1–x5. Both repeat while the interrupted return is 1; this does not
make their full call environments identical. Returned x4/x5 for the
repeatedly interrupted 1164-byte request remain unobserved.

[Upstream commit 82bcd087029f](https://github.com/torvalds/linux/commit/82bcd087029f)
introduces x6 session-state feedback, resubmits interrupted x0, and retains
original x1–x5. [Linux v6.12 SCM](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/firmware/qcom/qcom_scm-smc.c)
retains that pattern. This affirmatively supports ACK's mechanism, but is
not an msm8953 firmware specification or proof of equivalent call environments.

## 2. Console-associated slowdown and timing boundaries

Run-3 elapsed intervals between printk timestamp sites:

| request length | interrupted-return log → successful-return log | resume-pre log → successful-return log |
|---|---:|---:|
| 4 bytes | 376 µs | 234 µs |
| 24 bytes | 2626 µs | 2541 µs |

Anchors: `run3-usb.log:3434–3437,3457–3460`. These are not isolated SMC
latencies: `__scm_smc_do_quirk()` prints before SMC and before result
processing completes. Instrumentation and possible scheduling are included.
Nothing here establishes that the 1164-byte request's firmware time is 234 µs.

Run 2 with `console=tty0 loglevel=8` (fbcon over the OTM1911 DSI panel):

| diagnostic-site pair | elapsed interval |
|---|---:|
| `smc ... call` → `qsee_send` | 18 µs |
| `spilled` → `scm_send_desc` | 2257071 µs |
| `scm_send_desc` → `lock_wait` → `lock_acquired` → `scm_pre` → `raw_enter` | 8–59 µs per adjacent pair |
| `scm_raw_enter` → `scm_regs` | 2547 µs |
| `scm_regs` → `scm_raw_first_ret` | 785789 µs |

These are intervals between diagnostic sites, not a measured universal
printk cost; other tasks' records also appear between some of them
(`run2-usb.log:1953–1969`). The console-associated slowdown is real, but
console-enabled printk intervals cannot be treated as firmware-only timing.
The snapshot42 5.1 s interval cannot be equated to six prints. The proposed
DSI-clock/framebuffer mechanism remains a hypothesis, not an established cause.

The matched first-request `qsee_send_desc` markers are run 2 at 396.269012 s
and run 3 at 77.403896 s: difference 318.865116 s. This compares progress to
a command marker, not boot completion or an isolated console causal effect.
“No console” in this report means no `tty0`; ramoops/ttynull consoles remain.

## 3. Interrupted-SMC resume path

`QCOM_SCM_INTERRUPTED == 1` (`drivers/firmware/qcom/qcom_scm.h:176`).
Run 1's second request interrupts/resumes; both small run-3 requests and
both small run-11 requests interrupt/resume. Both small run-2 requests
succeed on attempt 1 (`run2-usb.log:1967,1996`).

ACK and donor both repeat while the interrupted return is 1, but differ in
argument feedback (§1). Agreement of next-resume x0–x6 is measured only for
the four captured small-request interrupted returns in runs 3 and 11.
Returned x4/x5 for the repeatedly interrupted 1164-byte request remain
unobserved.

## 4. Capture endpoints and unobserved subsequent state

Capture ends at different retained records; subsequent kernel state is
unobserved unless another retained channel directly shows later execution.

| run / historical instrumentation | tty0 | USB last retained kernel record (s) | durable-prefix last record (s) | latest DBGC header sample (s) |
|---|---|---:|---:|---:|
| 1, register capture (`boot.img`) | yes | 433.958900 | 433.958900 | 432.704479 |
| 2, register capture (`…-regs.img`) | yes | 423.164424 | 423.956443 | 423.112721 |
| 3, register capture (`…-noconsole.img`) | no | 77.532417 | 73.080063 | 76.861275 |
| 4, watchdog (`…-stallwatch.img` v1) | no | 77.061180 | 74.518567 | 77.045882 |
| 5, watchdog + historical RAM witness, ioremap WARN | no | 141.335548 | 139.243165 | 139.991262 |
| 6, historical RAM witness, ioremap WARN | no | no records; 0 bytes | 61.973579 | 63.585307 |
| 7, historical RAM witness, ioremap WARN | no | no records; 0 bytes | 73.035487 | 75.638539 |
| 8, historical RAM witness, memremap arming | no | 94.611040 | 91.336268 | 94.101735 |
| 9, historical RAM witness, memremap arming | no | no records; 0 bytes | 70.184048 | 70.068478 |

Fresh read-only extraction follows `porting/logging/pull-run-evidence.sh`:
durable text is the first-NUL-terminated prefix below 60 MiB; DBGC headers
are `<QQQQ8I` at offsets 62914560 and 63967232. The device-mutating pull
script was not run. Header times above are rounded to six decimal places.
These are retained-record/sample timestamps, not measured recorder stop
instants. Headers precede payload writes (`fs/pstore/ram.c:716–740`): a new
header does not prove payload completion, and the payload's last printk is
not the copying thread's stop time. Simultaneous termination within 0.5 s
is not established.

Runs 6, 7 and 9 status files report a serial reader exception with zero
delivered bytes (“device disconnected or multiple access on port?”).
Disconnection, competing access, gadget and host causes remain unresolved.

Retained evidence:
- Last-record content is not uniform: run 8 USB ends at `qsee_send`, and its
  durable prefix ends at an init late-fs action, not `sys_ptrace`.
- No relevant late panic, oops, lockup, hung-task or watchdog failure
  diagnostic is present in retained output. Detector execution, qualifying
  conditions, output retention and subsequent reset cause remain unobserved.
  Panic-related cmdline flags request behavior; they do not prove a panic.
  Detector-specific prerequisites and primary sources are detailed in §8.
- The device then resets and comes back on the installed ROM (boot reason
  `bootloader`, which identifies the reset class, not the initiator).
- Run 1 captures repeated third-request SMC interruptions. Run 2 captures
  1164-byte preparation through spilling at 423.164424 s
  (`run2-usb.log:2029–2036`). Run 8 reaches the no-tty0 send path at
  94.610903 s and ends at `qsee_send` 94.611040 s
  (`run8-usb.log:3112–3114`), without captured raw entry/returns.

### Historical RAM witness chronology (runs 5–9)

Runs 5–7 show `ioremap_prot` WARNs at probe: arm64 refuses this RAM mapping.
Runs 8–9 show witness arming at 0x868f7000 with the later memremap build.
Neither retained run-8/9 prefix has a previous-record print. Arming is not
per-write confirmation. ROM overwrite, reset/bootloader clearing, and other
writes remain possible explanations for absent readback, not a proved
second defect. Current partition-witness source and run-11 evidence are
separate from this historical RAM-witness implementation (§8).

### Current partition witness: safety and proof limits

Current source uses `RAMOOPS_WITNESS_OFFSET = 0x3f00000ULL` (66060288) and
512-byte `ramoops_witness_read()`/`ramoops_witness_write()` helpers
(`fs/pstore/ram.c:794–889`), called from qseecom write/probe paths
(`drivers/misc/qseecom.c:493–503,9967–9977`). DBGC slot 1 payload spans
63971328–65019903 inclusive; the free tail starts at 65019904. The old
proposed offset is removed: it overlapped slot data and was four bytes off
sector alignment.

The helpers synchronously wait for storage; the witness uses plain
`REQ_OP_WRITE`, without its own flush/FUA. [Linux v6.12 write-cache control](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/block/writeback_cache_control.rst)
explains that ordinary completion may precede nonvolatile persistence:
`REQ_PREFLUSH` persists preceding completed writes before a new write, while
`REQ_FUA` waits for nonvolatile commitment of the flagged write. Submission
alone is not a reset-durability guarantee when volatile caching is enabled;
this review has no device evidence that such caching is enabled here.

A correctly attributed later record proves watchdog execution and that its
write progressed at that time. An old, missing or unchanged record cannot
distinguish storage failure, scheduling/canary failure, or kernel-wide halt.
The watchdog writes the previous sampled canary/quiet before updating them
(`qseecom.c:525–539`), allowing one polling interval plus I/O latency of lag.
It ignores witness-write errno and waits for that write before checking the
canary: a blocked write can prevent this watchdog's subsequent detection and
dump. Stack dumps are not guaranteed to survive a failed logdump path.

The USB child closes durable input/output after fork
(`scripts/initramfs-diag/init.c:1733–1738`). Its
`dump_log(..., 900, 0, NULL, NULL)` is independent of durable
`dump_log(..., 900, 1, &sd, &sampler)` after startup
(`init.c:1632–1660,1786–1791`). Startup still opens logdump before forking
USB (`init.c:1696–1738`). Making durable writes nonfatal does not inherently
keep that already-separate USB stream alive; errno diagnostics are an
investigation proposal, not a proved fix or authorization to edit the recorder.

## 5. Where each hypothesis stands

| hypothesis | status |
|---|---|
| whitelist falsely enabled (feature-version query returns the base version) | **refuted**: probe prints `ret=0 version=0x401000 enabled=1`; the firmware answers feature 15 with a real version |
| whitelist command/7-arg layout/empty sglist is what TZ chokes on | untested for the 1164-byte request; both small requests in runs 3 and 11 succeed with that layout, without proving all command payloads valid |
| resume needs the donor's x0–x6 feed-back | next-resume x0–x6 agree for the two small requests in each of runs 3 and 11; returned x4/x5 for the repeatedly interrupted 1164-byte request remain unobserved |
| console/printk explains the apparent freeze | console-associated slowdown affects timing, but no-tty0 captures also end; firmware-only latency, a universal per-print cost, and the proposed DSI-clock mechanism are not established |
| TZ stalls on the third command | open: run 1 captures repeated SMC interruptions; runs 2 and 8 capture preparation/send-path markers, not third-request raw returns; run 11 has no captured 1164-byte request |
| logdump/eMMC writes block and end capture | open; shared storage is a candidate, but neither recorder-first causality nor a kernel-wide halt is proved |
| missing warnings imply halt or recorder failure | unsupported: detector execution, qualifying conditions, output retention and subsequent reset cause are unobserved; cmdline panic flags do not prove a panic |

## 6. Next steps (investigation requirements, in order)

1. Decode the already-pulled partition witness and separate host elapsed,
   kernel-record, DBGC-header and payload clocks (§8); no new boot is needed
   for this saved-record check.
2. Classify probe-time `-ENODEV` as unavailable readback, not an empty/lost
   witness. Any separately authorized experiment needs readback after block
   readiness; the current probe does not retry.
3. Require an independent execution-progress observation before diagnosing
   eMMC blockage versus a kernel-wide stall. The capture-investigation item
   is this item, not the whitelist experiment: inspect channel endpoints and
   errors without assuming that changing durable writes preserves USB.
4. Obtain third-request raw SMC entry/returns and later progress, keyed to
   command markers rather than borrowed console-enabled wall time. Runs 2
   and 8 already capture preparation/send-path progress, not raw returns.

These requirements do not authorize driver/recorder changes, additional
instrumentation, timeout/config changes, device boots, flashing or partition
writes. A whitelist-off experiment is not executed or justified as a fix by
the retained evidence.

## 7. Historical capture procedure (not executed by this review)

```
# any of the images in porting/artifacts/
/tmp/snapshot43-venv/bin/python porting/logging/usb-boot-capture.py \
    --image porting/artifacts/boot-ack-snapshot43-noconsole.img \
    --log porting/artifacts/snapshot43/runN-usb.log --adb-serial 2819f2320604 \
    --status porting/artifacts/snapshot43/runN-usb-capture.status
# durable channel (pulled after the device returns to the ROM):
adb -s 2819f2320604 shell 'su -c "dd if=/dev/block/by-name/logdump bs=1M"'
```

Register-capture source: `drivers/firmware/qcom/qcom_scm-smc.c`
(`scm_capture_result_regs`, `snapshot43 scm_regs`); witness/watchdog:
`drivers/misc/qseecom.c` (`qseecom_stall_watchdog_*`, `snapshot43 stall
watchdog` / `stall witness`).

## 8. Run-11 addendum (run 10 not fully reviewed)

### Identity and endpoint accounting

`run11-capture.log` boots `boot-ack-snapshot43-spillfix.img`.
`run11-usb.log:2,164` identifies build #8 and build ID
`64c446eb679a208effab5d2376a9a58f98de52b3`. USB status reports 561520
bytes and host elapsed 121.0 s; host elapsed and kernel timestamps are
different clocks, not two measures of the same endpoint.

| run | USB last kernel record (s) | durable-prefix last record (s) | DBGC slot 0 header (s; seq) | DBGC slot 1 header (s; seq) | slot 0 payload last printk (s) | slot 1 payload last printk (s) |
|---|---:|---:|---|---|---:|---:|
| 11, spillfix / partition witness | 98.625345 | 94.713096 | 97.234002879; 45 | 95.187535015; 44 | 97.123422 | 95.181923 |

Read-only extraction uses the same prefix/header convention as §4.
Headers precede payload writes; none of these timestamps proves payload
completion or a recorder stop instant. USB ends after `installkey /data`
succeeds, not inside an observed third SMC. No `req_len=1164` is captured.

### Probe readback and saved witness

At 1.688388 s run 11 reports `stall witness read failed errno=-19`, then
watchdog arming at 1.691350 s. Current `ramoops_witness_open()` returns
`-ENODEV` when no logdump partition is discovered. The probe does not retry:
this is unavailable early block-device readback, not proof that an old
witness was empty or lost.

`run11-usb.log:161–198` warns that `class_for_each_device()` was called
before class `block` initialized, from `ramoops_snap`. The snapshotter
becomes ready at 4.678810 s. This recovered early warning is not the later
capture cutoff.

Direct decoding of `run11-logdump.bin` at 0x3f00000 as a 32-byte `<QQQII`
record gives magic `0x5354414c4c574751`, canary 85, jiffies 4294915776,
quiet 0, and `boot_id` 138394. Current `stall_witness_write()` samples
realtime seconds on each write: `boot_id` is not a stable boot identifier.
Run 10's saved record differs (canary 64, jiffies 4294910592, realtime
137788). Run-11 audit records show realtime 138394 around 93.6 s.
Together these support run-11 attribution **[INFERENCE]**; the record lacks
a stable run ID. This comparison is not a full run-10 review.

The inspected `out-snapshot43/.config` has `CONFIG_HZ=250`.
`include/linux/jiffies.h:320` and the [v6.12 jiffies baseline](https://github.com/torvalds/linux/blob/v6.12/include/linux/jiffies.h)
define deliberately nonzero `INITIAL_JIFFIES = u32(-300*HZ)`.
**Conditional on the run-11 binary using that config**,
`(4294915776 - 4294892296) / 250 = 93.920 s` elapsed ticks.
Image-matched config provenance is unverified; retain the raw jiffies
value rather than interpreting raw jiffies/HZ as uptime.

That conditional witness timestamp precedes the durable-prefix last record
by about 0.793 s. USB continues to 98.625345 s and canary tick 94 is visible
at 97.989529 s. Kernel execution is directly observed after the durable
prefix cutoff; the witness does not show progress after all captures end.
With a five-second sleep after each write, the next witness opportunity
after 93.920 s is no earlier than about 98.920 s, beyond the retained USB
tail (and later still if I/O takes time). The saved record is not evidence
of a frozen witness, a blocked bio, or a kernel hang.

### Small requests and spillfix limits

The 4- and 24-byte requests complete in two attempts
(`run11-usb.log:3382–3388,3404–3410`):

| request length | interrupted-return log → successful-return log | resume-pre log → successful-return log |
|---|---:|---:|
| 4 bytes | 360 µs | 262 µs |
| 24 bytes | 364 µs | 271 µs |

These are printk-site intervals, not isolated firmware latency. x1–x5 are
preserved on those interrupted returns, not on success. ACK/donor next
resume x0–x6 agree only in the observed small-request cases (§1); returned
x4/x5 for the repeatedly interrupted 1164-byte request remain unobserved.

Spillfix is **lazy persistent-page reuse**, not probe-time preallocation.
`qseecom_spill_alloc()` still calls `dma_alloc_coherent(..., GFP_KERNEL)`
on first use, holding `qseecom_spill_lock` until free after SCM returns
(`qseecom.c:9866–9894`). Run 11 logs first allocation at 97.697850 s
and reuses PA 0xff011000 for the second small send. The log's
“preallocated” label does not change when allocation actually happens.
The run-era comment at `qseecom.c:9840–9849` asserted a direct-reclaim/eMMC
cause that these logs do not prove. Before committing, that comment was
corrected to describe lazy reuse and its proof limits; allocator behavior
was not changed. Neither the logs nor image name proves a firmware fix.

The [primary TrustZone allocator patch](https://lkml.indiana.edu/hypermail/linux/kernel/2403.0/01880.html)
motivates pools by duplicated code, per-call DMA allocation performance,
shared-memory properties and future SHM Bridge support. It does not identify
this board's alleged direct-reclaim/eMMC failure or establish “the same reason.”

### Missing-warning interpretation

No relevant late failure diagnostic is present in retained output.
Detector execution, qualifying conditions, output retention and subsequent
reset cause remain unobserved. Panic-related cmdline flags prove requested
behavior, not that a panic occurred.

- [v6.12 lockup-watchdog documentation](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/admin-guide/lockup-watchdogs.rst)
  makes softlockup checking depend on hrtimer callbacks and the watchdog
  scheduling timestamp; nominal default threshold is 20 s. A sleeping,
  storage-blocked task is not automatically a CPU softlockup.
- The inspected config selects buddy hardlockup detection, not perf/NMI.
  [v6.12 buddy source](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/watchdog_buddy.c)
  checks another CPU from a running CPU's timer samples; without any
  monitoring CPU executing, that mechanism cannot report. This setting is
  conditional on the booted image matching the inspected config.
- [v6.12 RCU stall documentation](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/RCU/stallwarn.rst)
  says “No grace period, no CPU stall warnings.” Run 11 logs a 10-second
  RCU parameter; it measures from grace-period start, not the last printk.
  Slow consoles/debug printk are documented stall sources: observer-effect
  caution, not proof of a DSI mechanism.
- [v6.12 hung-task source](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/hung_task.c)
  checks qualifying uninterruptible tasks from a scheduled detector thread.
  `hung_task_panic=1` changes response, not timeout. The inspected config's
  default is 120 s; retained run-11 output ends at 98.625345 s. Config/runtime
  provenance for the booted image remains unverified, so the current-build
  timeout is conditional, not a measured runtime value.

### Review verification

Read-only arithmetic, prefix/header extraction and direct witness decoding
passed against saved runs 1–9 and 11, with run 10 used only for witness
comparison. Source and linked primary passages were inspected. No device
behavior after the capture cutoff is verified; no boot, flash, partition
write or driver/recorder change is part of this report correction.

Repository retention at commit: only snapshot43 run-10/run-11 capture
evidence is tracked. Runs 1–9 measurements above were verified before this
pruning; older artifacts remain ignored locally, not available from a fresh
checkout. A checkout-only reproduction can check runs 10/11, not rerun the
full historical extraction without those local artifacts.

Commit preparation added narrow safety fixes, not a new device experiment:
capture assembly is ARM64-only; partition diagnostics require built-in
ramoops with BLOCK enabled; witness allocation failure closes the temporary
file and leaves cached state unset for retry. The saved run-10/run-11 images
predate these changes and were not repacked or booted. The boot-only canary
still lacks suspend/resume rearming, so a quiet canary after suspend is not
a reliable stall finding.
