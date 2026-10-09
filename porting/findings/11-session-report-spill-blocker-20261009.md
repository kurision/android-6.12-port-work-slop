# SESSION REPORT 2026-10-09 — spill reuse, capture endpoints, and remaining proof gaps

Evidence: saved snapshot43 artifacts in `porting/artifacts/snapshot43/`.
The corrected [findings through run 11](10-snapshot43-console-abi-capturedeath-20261009.md)
cover runs 1–9 and a separate run-11 addendum. This report additionally checks
run-10 command markers and its saved witness/endpoints; it is not a complete
run-10 audit. Historical captures used `fastboot boot`; this correction
accessed no hardware and changed no drivers, recorder, images or partitions.

## 1. Answer: the spill/direct-reclaim blocker is not proved

**Run 11 demonstrates lazy spill-page reuse and successful small commands.
It does not prove that the third command's allocation entered direct reclaim,
that eMMC was stalled, or that spillfix makes the boot complete.**

Matched elapsed intervals between `qsee_send` and `qsee_ret` printk sites:

| run / request | send timestamp (s) | return timestamp (s) | interval (ms) | raw loop attempts |
|---|---:|---:|---:|---:|
| 10 / 4 bytes | 76.341032 | 76.390429 | 49.397 | 9 |
| 10 / 24 bytes | 76.414394 | 76.537365 | 122.971 | 7 |
| 11 / 4 bytes | 97.694598 | 97.701458 | 6.860 | 2 |
| 11 / 24 bytes | 97.702785 | 97.706115 | 3.330 | 2 |

Anchors: `run10-usb.log:2553–2580,2594–2621`;
`run11-usb.log:3376–3389,3399–3411`. These intervals include spill preparation,
instrumentation, possible scheduling and SCM execution/resumes; they are
not isolated allocation or firmware latencies. The older 69/947 ms and
0.9/3.5 ms comparison did not use these matched sites.

Run 10's send→spill-log intervals are 7.063 ms and 91.479 ms. They do not
isolate `dma_alloc_coherent()` or show direct reclaim. Its two commands also
use more interrupted attempts than run 11, so the whole-call comparison
does not isolate an allocator causal effect.

Run 10 reaches `req_len=1164` at 77.354949 s and ends at `qsee_send`
77.358032 s (`run10-usb.log:2927–2929`). There is no retained spill log or
raw SMC entry/return for that request. The cutoff does not locate the thread
inside allocation or prove that it never subsequently returned.

Run 11 has no captured `req_len=1164`. Its USB last record is at 98.625345 s,
after `installkey /data` succeeds. “Not captured” does not mean “never issued”
or establish that HAL speed caused its absence. Neither this endpoint nor
the image name proves boot completion or a resolved firmware issue.

## 2. Witness and endpoint accounting

Run 11 boots `boot-ack-snapshot43-spillfix.img` (`run11-capture.log:3`).
`run11-usb.log:2,164` identifies build #8 and build ID
`64c446eb679a208effab5d2376a9a58f98de52b3`. Status reports 561520 bytes
and host elapsed 121.0 s. Host elapsed and kernel time are different clocks.

| run | USB last kernel record (s) | durable-prefix last record (s) | SD mirror last record (s) | slot 0 DBGC header (s; seq) | slot 1 DBGC header (s; seq) |
|---|---:|---:|---|---|---|
| 10, targeted comparison | 77.358032 | 74.574141 | not checked | 73.845639711; 35 | 75.893972054; 36 |
| 11 | 98.625345 | 94.713096 | 94.712899 | 97.234002879; 45 | 95.187535015; 44 |

Run-11 DBGC payload last-printk timestamps are 97.123422 s (slot 0) and
95.181923 s (slot 1). Extraction follows `pull-run-evidence.sh`'s convention:
first-NUL-terminated durable text below 60 MiB, `<QQQQ8I` headers at
62914560 and 63967232. The hardware pull script was not run.
Headers precede payload writes (`fs/pstore/ram.c:716–740`); a new header
does not prove payload completion. Last printk times are not measured
recorder/copying-thread stop instants. Simultaneous channel termination is
not established.

Direct `<QQQII` decoding at logdump offset `0x3f00000`:

| saved artifact | magic | canary | raw jiffies | quiet | per-write realtime (`boot_id`) |
|---|---|---:|---:|---:|---:|
| run 10 | `0x5354414c4c574751` | 64 | 4294910592 | 0 | 137788 |
| run 11 | `0x5354414c4c574751` | 85 | 4294915776 | 0 | 138394 |

`boot_id` is realtime seconds sampled on each write, not a stable boot ID
(`qseecom.c:493–503`). The changed record and run-11 audit realtime 138394
around 93.6 s support run-11 attribution **[INFERENCE]**; no stable run ID
is stored. A retained partition record is not a general ROM/reset-durability
guarantee.

Current `.config` has `CONFIG_HZ=250`; [the jiffies baseline](https://github.com/torvalds/linux/blob/v6.12/include/linux/jiffies.h)
is deliberately nonzero `u32(-300*HZ)` (`include/linux/jiffies.h:320`).
Conditional on each image matching that config, elapsed ticks are 73.184 s
for run 10 and 93.920 s for run 11, not canary/HZ or raw jiffies/HZ uptime.
Image-matched config provenance is unverified; raw values remain authoritative.

Run-11 witness time conditionally precedes the durable last record by
0.793 s. Canary tick 94 appears at 97.989529 s and USB continues to
98.625345 s: execution after the durable cutoff is directly observed in USB.
The next witness opportunity after a five-second sleep is no earlier than
98.920 s, beyond the USB tail. Thus canary 85 versus tick 94 does **not**
prove a blocked witness write or a frozen record. The watchdog stores its
previous sampled canary/quiet before updating them, allowing one polling
interval plus I/O latency of lag (`qseecom.c:525–539`).

A correctly attributed later witness proves execution/write progress at
that time; an old, missing or unchanged record cannot distinguish storage
failure, scheduling/canary failure, or a kernel-wide halt. It does not show
execution after every capture ends.

At 1.688388 s run 11 reports witness read errno=-19, then watchdog arming at
1.691350 s. Current `ramoops_witness_open()` returns `-ENODEV` if no logdump
partition is discovered; probe does not retry. This is unavailable early
readback, not an empty/lost record. The early `class_for_each_device()`
warning from `ramoops_snap` (`run11-usb.log:161–198`) recovers: snapshotter
ready at 4.678810 s. It does not explain the late cutoff.

## 3. Established observations, with scope

- **Interrupted ABI:** the two small requests in each of runs 3 and 11
  preserve x1–x5 on their first interrupted returns; next-resume x0–x6
  agree for ACK original-argument and donor returned-register feedback.
  Success changes x1–x5, including zeroing x4/x5. Returned x4/x5 for the
  repeatedly interrupted 1164-byte request remain unobserved.
  [Commit 82bcd087029f](https://github.com/torvalds/linux/commit/82bcd087029f)
  and [v6.12 SCM](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/firmware/qcom/qcom_scm-smc.c)
  support retaining x1–x5 and feeding returned x0/x6; they are not this
  firmware's specification. Both loops repeat while interrupted return is
  1, not in identical full call environments.
- **Resume intervals:** run 3 interrupted→success logs are 376/2626 µs
  for 4/24 bytes; resume-pre→success logs are 234/2541 µs. Run 11 pairs are
  360/364 µs and 262/271 µs. These are printk-site intervals, not a universal
  234 µs firmware latency or a timing of the third request.
- **Whitelist detection:** probe reports `ret=0 version=0x401000 enabled=1`
  (`run11-usb.log:252`). Feature detection is supported; validity of every
  whitelist command/payload is a separate question.
- **Console:** matched first-request markers are 396.269012 s in run 2
  and 77.403896 s in run 3 (318.865116 s difference). Console-associated
  slowdown is real; universal ~800 ms per-print cost, firmware-only timings,
  boot completion and a DSI-clock cause are not established. No-tty0 still
  leaves ramoops/ttynull consoles.
- **Third request:** run 1 captures repeated SMC interruptions; run 2
  reaches spilling at 423.164424 s; run 8 reaches the no-tty0 send path at
  94.610903 s and ends at `qsee_send` 94.611040 s. Run 10 ends at a send
  marker, and run 11 has no captured third request. Preparation is not raw
  SMC entry/return.
- **Historical RAM witness:** runs 5–7 show ioremap WARNs; runs 8–9 show
  arming at 0x868f7000, not per-write confirmation. Neither retained prefix
  shows previous-record readback. ROM overwrite/reset clearing/other writes
  remain hypotheses, not a proved second defect. Zero-byte USB statuses
  report reader errors; host, gadget, disconnect and competing access causes
  are unresolved.
- **Missing warnings:** no relevant late diagnostic is retained. Detector
  execution, qualifying conditions, output retention and subsequent reset
  cause are unobserved. Panic flags request behavior, not proof of a panic.
  [Softlockup checks](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/admin-guide/lockup-watchdogs.rst)
  require hrtimer/watchdog scheduling; storage sleep is not automatically a
  CPU softlockup. Current config selects [buddy hardlockup detection](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/watchdog_buddy.c),
  requiring an executing monitoring CPU, not perf/NMI.
  [RCU warnings](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/RCU/stallwarn.rst)
  require a grace period; run 11's 10 s parameter is not timed from last
  printk. [Hung-task checking](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/hung_task.c)
  requires a scheduled detector and qualifying task; panic flags do not
  shorten its timeout. Current config default is 120 s, conditionally on
  image/runtime provenance, versus USB retained through 98.625345 s.

## 4. Current implementation, not a list of proved fixes

1. `qseecom_spill_alloc()` lazily allocates one coherent page on first use
   with `GFP_KERNEL`, then reuses it. The mutex remains held until free after
   SCM returns; atomic/non-reclaim or oversized requests keep the allocator
   path (`qseecom.c:9866–9894`, `qcom_scm-smc.c:310–381`). First allocation
   is logged at 97.697850 s; the second small send reuses PA 0xff011000.
   This is not probe-time preallocation and does not remove first-use
   allocation from the SMC path. The run-era direct-reclaim/eMMC assertion
   at `qseecom.c:9840–9849` was corrected before commit; behavior is unchanged.
   The [primary upstream allocator patch](https://lkml.indiana.edu/hypermail/linux/kernel/2403.0/01880.html)
   cites duplication, per-call DMA performance, shared-memory properties and
   future SHM Bridge support, not this board's alleged failure.
2. `scm_capture_result_regs()` captures x0–x7 for the first three attempts
   per traced invocation, predicate `desc->owner == 48 && desc->svc == 0`,
   not exclusively keymaster by name (`qcom_scm-smc.c:79–170,299`).
3. The canary watchdog synchronously writes before checking the canary,
   ignores write errno, and may therefore be blocked before detection/dump.
   Its 15 s quiet threshold does not guarantee a dump or its retention.
4. `ramoops_witness_read()/write()` transfer 512 bytes at `0x3f00000`
   (66060288), containing the 32-byte record. DBGC slot 1 payload ends at
   65019903; free tail begins at 65019904. Plain witness `REQ_OP_WRITE`
   has no own flush/FUA: [ordinary completion need not imply persistence](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/block/writeback_cache_control.rst)
   if volatile caching is enabled. Such caching on this device is unverified.
5. The USB child closes durable input/output after fork and runs independent
   `dump_log(..., 900, 0, NULL, NULL)`; durable uses
   `dump_log(..., 900, 1, &sd, &sampler)`. Startup still opens logdump first
   (`init.c:1632–1660,1696–1738,1786–1791`). Nonfatal durable writes do not
   inherently keep an already-separate USB stream alive.

## 5. Open items and HANDOFF

**Do not carry forward “blocker found”, “eMMC stall proved”, “ROM-proof
witness”, or “spillfix completes boot” as established findings.**
eMMC/logdump blockage, allocation/reclaim delay, TZ behavior and subsequent
kernel state remain open; no captured stack/request completion evidence
establishes the proposed causal chain. No vendor-4.19 comparison was
verified in this correction.

Investigation order:

1. Use the already-decoded witness and distinct endpoint clocks above.
2. Treat early `-ENODEV` as unavailable readback; any separately authorized
   experiment needs readback after block readiness.
3. Require independent execution-progress and storage-path evidence before
   choosing eMMC blockage versus a kernel-wide stall. Recorder errno
   diagnostics are a proposal, not a proved fix.
4. Obtain third-request raw entry/returns and later progress using command
   markers, not a borrowed 420 s console-enabled wall time.

User's three next-session follow-ups remain **unexecuted**:

- [ ] Re-run `boot-ack-snapshot43-spillfix.img` for a full capture window;
  determine whether boot proceeds through keymaster/keystore2 and completes,
  without assuming command 3 succeeds.
- [ ] Investigate suspected eMMC/SDHCI write-path blockage (`7824900.mmc`,
  HS400/ADMA, late-fs); establish blocked requests/stacks rather than assume
  a measured stall window of 66–98 s.
- [ ] Investigate recorder behavior when logdump writes fail/block; assess
  nonfatal handling without promising that it preserves independent USB.

These are handoff items, not authorization in this report-only correction
to boot, flash, write partitions, change drivers/recorder, tune timeouts, or
add instrumentation. Existing code/image work is left untouched.

## 6. Read-only verification

The findings plan's exact ephemeral arithmetic/extraction command passed:
runs 1–9 and 11 prefixes/headers, run-11 witness, run-10 differing witness,
conditional HZ250 conversion (93.920 s), run-11 endpoint and resume intervals.
Additional read-only extraction checked the matched run-10/run-11 command
intervals, run-10 durable/DBGC endpoints, and run-11 SD last record.
Source and linked primary passages were read; no permanent test was added.

Saved witness decoding requires no next boot:

```sh
python3 -B -c 'from pathlib import Path; import struct; d=Path("porting/artifacts/snapshot43/run11-logdump.bin").read_bytes(); print(struct.unpack_from("<QQQII", d, 0x3f00000))'
```

Artifacts confirmed present: `run11-usb.log`, `run11-usb-capture.status`,
`run11-capture.log`, `run11-logdump.bin`, `run11-sd-ack-kmsg.log`.
No device behavior after all capture cutoffs was verified.

Repository retention at commit: only snapshot43 run-10/run-11 capture
evidence is tracked, including both 64 MiB partition dumps. Older logs are
ignored locally; their historical measurements were verified before pruning
and are not freshly reproducible from a checkout without those artifacts.

### Pre-commit safety review

Narrow fixes before committing the diagnostic code:

- Restrict register-capture assembly to ARM64; ARM32 keeps the standard
  SMCCC path.
- Restrict partition snapshot/witness diagnostics to built-in ramoops with
  BLOCK enabled; other configurations retain ordinary RAM pstore and QSEE.
- On witness-buffer allocation failure, close the just-opened file and leave
  cached pointers unset. A standalone check of the real open function failed
  on its second call before the fix, then passed failure/retry cleanup and
  successful caching after it (`test_ramoops_witness_open.py`).

ARM32 SCM, modular ramoops/QSEE, BLOCK=n ramoops and PSTORE_RAM=n QSEE
objects compiled in scratch configs; unsupported diagnostic references were
absent from their undefined-symbol lists. No scratch config replaced the
inspected snapshot43 config. The saved images/logs predate these fixes and
were not repacked or booted.

Known boot-only diagnostic limitation: a canary work item that sees SUSPEND
stops rearming, and resume does not restart it. The watchdog can therefore
report a false quiet-canary stall after suspend/resume. Suspend-aware
lifecycle handling remains outside this boot-evidence commit; do not use
that threshold as post-suspend stall proof.
