# Snapshot38 — kernel-side ramoops snapshot to logdump

## Purpose
Snapshot35 proved a userspace raw-RAM sampler works but dies at the SELinux domain
transition. Snapshot37 proved the kernel-side replacement works but retained only the
newest sample, which missed the cutoff by ~1.0 s. Snapshot38 adds two alternating slots
so a freeze cannot destroy every sample.

## Change
`fs/pstore/ram.c` only. A kthread copies the 1 MiB ramoops reservation to the
`logdump` partition every 2 s, independently of any process, and flushes after each
sample.

Layout inside the 64 MiB `logdump` partition (above the growing kmsg text region):

| slot | header | payload |
|------|--------|---------|
| 0 | 62914560 | 62918656..63967231 |
| 1 | 63967232 | 63971328..65019903 |

Each header is 64 bytes: magic `0x52414d4f`, seq, index, timestamp_ns,
payload_offset, payload_len, phys_addr_lo, slot. The slot advances only after a
fully flushed write. Ordinary pstore, the `ramoops_raw` sysfs exporter, config and
the board DTB are unchanged.

## Defects found and fixed during this work
1. **`bi_sector` never set** (snapshot36). Every 1 MiB write landed at sector 0 and
   destroyed the kmsg text; USB captured 0 bytes. Fixed at `fs/pstore/ram.c:685`.
2. **Probe-time block lookup** (snapshot36). MMC block devices register at
   `device_initcall`, after ramoops probes at `postcore_initcall`, so the channel
   would have disabled itself. Moved to a retrying open inside the worker thread.
3. **Prefix partition match.** `memcmp(volname, "logdump", 7)` also matched a partition
   named `logdump*`; added an explicit terminator check.

## Two self-corrections
- The userspace sampler `EACCES` was **not** a per-read SELinux check (my first claim)
  and **not** a per-`pread` policy check (my second claim). The recovered kmsg shows
  `enforcing=1` flipping at t=60.229 and the sampler failing 4 ms *earlier* at t=60.229;
  the next denial is `pid=1 comm=init` on the diagnostic's own tmpfs file. It is a
  domain transition at enforcement. No fd-lifetime fix could have worked.
- Framebuffer logs were never disabled. The cmdline is byte-identical across
  snapshots 26/34/35/36/38, including `console=tty0 loglevel=8`. Display output was
  never captured, so whether it rendered is unverified.

## Results — 5 temporary boots of the two-slot image

| run | USB bytes | traced sends | returned | endpoint (s) | canary max |
|-----|-----------|--------------|----------|---------------|------------|
| snapshot35 | 136483 | 2 | 2 | 88.248 | 84 |
| snapshot37 | 140272 | 3 | 2 | 96.305 | 80 |
| snapshot38 r1 | 136880 | 2 | 2 | 82.318 | 78 |
| snapshot38 r2 | 0 | 2 | 2 | 72.117 | — |
| snapshot38 r3 | 141789 | 2 | 2 | 101.492 | 85 |
| snapshot38 r4 | 130706 | 0 | 0 | 101.487 | 85 |
| snapshot38 r5 | 141114 | 2 | 2 | 74.463 | 70 |

Both slots were valid in 4 of 5 runs, 2.044 s apart. In r1 slot 1's RAM content ended
on exactly the record where the USB stream ended, corroborating the live stream from
physical memory. In r3 the live stream continued 1.77 s past the newest sample,
confirming the snapshotter keeps sampling after logging stops — the capability
snapshot37 lacked.

## Findings

1. **The third-send theory is refuted.** snapshot38-r4 issued **zero** traced QSEE
   sends and still cut off in the same FBE/keystore2 window at 101.487 s. Across all
   runs: 13 traced sends, 12 returned 0; the single non-return was snapshot37's third
   send, and that run's behaviour is not reproduced elsewhere.
2. **No WAITQ traversal was ever observed**, so the waitq sleep/resume markers remain
   unexercised. Rate limiting also suppresses pre-SMC records; absence is not evidence
   of no attempt.
3. **The canary progressed past the final pre-SMC record in every run**, so no traced
   QSEE transport stalled.
4. **The cutoff endpoint varies from 72.1 s to 101.5 s** and always lands in the
   keystore2 / FBE `enablefilecrypto` window. It is not a fixed timeout.

## Not established
No root cause for the cutoff. No panic or secure reset proven — the ROM-side
`bootreason` after capture is `reboot`, which is also what a host-side session end
looks like. FBE completion, keystore2 handshake success and boot completion are **not**
established; transport success and manifest lookup are not evidence of them.

## Artifacts
`porting/artifacts/snapshot38/boot.img` (former root name
`boot-ack-snapshot38-kernel-snap-slots.img`), SHA256
`e797646f707c9b727224bb339070498c5427d6939c305257d7ff1b5eea9ceb27`.
Per-run raw/readable logdump uses `run<N>-logdump.bin`/`.log`.
Separate slot exports and manifests were removed; slots remain in the raw files.
## Device hand-off (important)
The SD card failed to initialise on the final ROM boot:

    mmc1: card never left busy state
    mmc1: error -110 whilst initialising SD card

No `mmc1:0001` node exists, so the card failed at transport/init level — not a
filesystem or vold issue. The card was healthy and fully readable minutes earlier
(`mmcblk1p1`, 30.5 GB) and was never formatted, repaired or written outside the
diagnostic recorder's mount. It is **not established** whether five back-to-back
temporary boots, each mounting the card without a clean unmount, contributed. A
power-cycle and re-seat is the next step; if it still fails, test it in a reader.

ADB reports `unauthorized` at hand-off, so the on-screen approval must be accepted
before further host-side device work.
