snapshot39 — per-daemon liveness probe: RESULT

## Question

Across seven temporary boots the diagnostic kernel boots Android but boot never
completes: `vdc --wait cryptfs enablefilecrypto` (exec 5) is spawned and never
exits, so init blocks inside the post-fs-data trigger. keystore2 never publishes.
The plan was to answer "where is each daemon sitting at cutoff — blocked in
kernel (D), idle-blocked (S), zombie (Z), or absent".

## Answer

The probe cannot answer that question from the vantage point it was given, and
the reason is now measured rather than guessed.

The diagnostic recorder child runs in a mount namespace where it mounts its own
procfs, and it does not unshare a PID namespace. But the procfs it ends up with
does **not** contain Android's service processes. On run 5 (image
`fd8d79c52c87bfbd4f3dd45a5ff1b27e9c1ded458b73ca0b0d8b1299ff05e4ac`) the probe's
one-shot census of its own `/proc` (`run5-proccomm-census.txt`) contains:

* 161 entries, of which ~156 are kernel threads
* exactly **five** userspace processes: pid 1 `init`, and pids 154, 158, 159, 160
  all named `init` — these are the ramdisk-init lineage the recorder itself
  creates (154 is the recorder, `self=154`; 158/159/160 are the USB, guard and
  block-state children)
* highest pid visible: **162**

Android's own init reports, from the same boot:

    started service 'keystore2' has pid 334
    started service 'vendor.keymaster-3-0' has pid 336
    servicemanager ... Caller(pid=291 ...)
    vold ... Caller(pid=302 ...)

None of 291, 302, 334 or 336 is present in the recorder's `/proc`. The entry
count stays at 161 → 162 for the whole run and then `/proc` disappears
(`entries=0 comm_errno=2`) at teardown, while Android is still spawning services
up to pid 350.

So every `DIAG: daemon …` line necessarily reports `pid=0`: the watched daemons
are not merely unmatched or idle, they are **invisible** to the probe.

## What was ruled out, with evidence

| hypothesis | verdict | evidence |
|---|---|---|
| watch names never match the kernel's comm values | **ruled out** | the on-device census proves all comm reads succeed (`comm_errno=0`) and the matching logic resolves all six names against real processes on the host |
| SELinux denies the reads | **ruled out** | `comm_errno=0` on every tick; every one of the 161 comm reads succeeded |
| heartbeat too coarse for the stall window | **real, and fixed** | run 1 used a 20 s heartbeat; ticks landed at 23.6/43.6/63.6 s while the daemons started at 65.2 s, so no tick existed inside the stall. Cadence is now 1 s |
| `/proc` not mounted | **ruled out** | `opendir` succeeds; `entries` is nonzero |
| probe lines lost with the printk path | **ruled out** | probe lines are present in the logdump partition *and* the SD mirror, written straight to the capture fd |
| daemon genuinely blocked in `D`/`S`/`Z` | **not answerable** | requires a probe that can see the process |

## Why the plan's kernel-snapshot acceptance criterion cannot hold

The plan required probe lines to "survive in the kernel snapshot slots". They
cannot, by construction: the kernel snapshotter copies the **console ring**
(`fs/pstore` → the `DBGC`-signed payload), while the probe writes to the
**logdump block device**. The two channels are disjoint. The slots are still
valuable — they bracket the stall in kmsg — but they will never contain
`DIAG: daemon` lines.

## What a next round would need

The probe has to observe Android's process table from inside Android's own
process tree. The current recorder is PID 1's child in a separate mount
namespace; it cannot reach the pids Android's init creates. Options, cheapest
first:

1. Have the probe fork after Android's init is running and `setns()` into
   Android's PID namespace, the way the existing bootdevice guard already
   `setns()`s into PID 1's mount namespace. The guard is proof the pattern
   works in this codebase.
2. Read the daemon state from a source that does not require `/proc` in the
   global pid namespace — e.g. ask `servicemanager`/`hwservicemanager` for
   registered services, which would prove publication without process state.
3. Instrument the stall directly: a `ftrace`/`eBPF` hook on the
   `binder_ioctl`/`vdc` path, or an `init` property dump at the post-fs-data
   boundary.

Option 1 is the smallest change that keeps the existing evidence channels.

## Evidence index

| artifact | what it shows |
|---|---|
| `run5-proccomm-census.txt` | the 161-entry `/proc` view: 5 userspace processes, max pid 162 |
| `snapshot39-run5-logdump.bin` | full logdump pull; `DIAG: procdir` and `DIAG: proccomm` lines |
| `snapshot39-run5-sd-snapshot28-kmsg.log` | same probe lines interleaved with kmsg; Android's service pids |
| `snapshot39-run5-kernel-snapshot-slot{0,1}.bin` | console-ring snapshots bracketing the stall |
| `manifest.json` | per-run image hashes and outcomes |
| `daemon-probe-selftest-host` | host self-check for the probe (prefix match, last-`)` stat split, dedup, heartbeat, errno reporting, census) |