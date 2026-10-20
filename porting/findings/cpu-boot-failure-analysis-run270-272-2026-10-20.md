# run270-272: the hang is after the panel lights, and the GPU dispatcher stops

Date: 2026-10-20. Follows
`cpu-boot-failure-analysis-run265-2026-10-19.md`. Same branch of work,
one more session.

## 1. What run270 is

The run267 image, booted by the script with the host completely idle for
the boot window. It **hung**: the panel was lit but dim, the USB link was
gone, and the phone had to be power-cycled by hand. Evidence:
`run270-ramoops.json` (all slots absent) and `run270-logdump.log` (0
readable bytes).

**The all-zero logdump, plus the dim screen, is what narrows the early
hang to a 6-second window.** The dim screen means the panel was powered
and lit, i.e. the MDSS had already come up (the MDSS probe is at 3.06 s
in the good boots). The empty logdump means the hang was before the
logdump sink existed, i.e. before 8.98 s (the MMC block device registers
at `device_initcall`; the snapshotter's first commit is at 8.98 s). The
APCC clock handoff is at **8.07 s**, inside that window and after the
display is live.

**And the "the host poller causes the early death" theory is dead.**
run270 hung with **no host activity at all** during the boot window, and
run270's logdump is empty. The earlier 4-deaths-with-poller /
2-successes-without correlation was confounded. The early hang is the
port's own, and it is intermittent.

## 2. What run271 is, and what it settles

`boot-run271.img`
`57d0284d82cb821372392c184fc885508cd461c70bd2558750634e644b7c9930` -
the **run267 kernel, bit for bit** (`kernel_payload_sha256`
`db3acee2392c1f1625e2f2e364609e31551c0b7ff1a47aff2b045d3625b40b4b`, same
ramdisk, same init), with one cmdline token added:
`initcall_blacklist=apcc_msm8953_driver_init`.

No kernel build was needed for that: `run271-272-package-variants.sh`
re-packages the same `kdir-run267` with a different command line.

**With the APCC driver blacklisted there is no cpufreq policy at all**
(`/sys/devices/system/cpu/cpufreq/` is empty), the CPU stays on the
firmware's GPLL0 at 800 MHz, and the coupled clock transaction never
runs - not at boot, not at any frequency change.

**And the GPU still stalls.** The kgsl interrupt rate fell from 24/s to
11/s between t=581 s and t=661 s, and the load average climbed 14 -> 51,
exactly as in run265. So:

> **The GPU stall is not the APCC handoff, not the coupled clock
> transaction, and not the cpufreq policy at all.** It happens with the
> whole CPU clock driver blacklisted.

## 3. The fence release chain, measured

run271's logdump is the first boot that both stalls *and* carries the
diagnostic. The four lines say exactly where the chain breaks:

| Line | Calls | Time span |
|---|---|---|
| `DIAG event_group` | 64 | 141.9 s .. **149.4 s** |
| `DIAG sync_fence_event` | 64 | 148.8 s .. **152.1 s** |
| `DIAG dispatcher_timers` | 64 | 148.8 s .. **162.6 s** |
| `DIAG sync_timeline_signal` | 225 | 148.8 s .. **680.5 s** |

The sampling is every 256th event after the first 64, so these are not
truncations of the output: the calls themselves stopped.

* `_process_event_group()` stopped at **t=149.4 s**.
* `kgsl_sync_fence_event_cb()` stopped at **t=152.1 s**.
* `_dispatcher_update_timers()` stopped at **t=162.6 s** - which means
  `adreno_dispatcher_work()` stopped running.
* The fence releases carried on to t=680 s, but they came from the *other*
  caller: `kgsl_add_fence_event()` calls `kgsl_sync_timeline_signal()`
  directly when the timestamp has **already** retired
  (`kgsl_sync.c:214-216`). A fence whose timestamp has *not* yet retired
  gets an event registered, and that event is only ever released by the
  event group - which had stopped.

> **The GPU stall is the GPU dispatcher stopping.** The event groups are
> only processed by `kgsl_process_event_groups()`, which only the
> dispatcher calls; without it, every fence that is not already retired
> is never released, and the display's fence wait times out.

The dispatcher's own re-arm decision was, in **every** sampled call,
`inflight=N preempt=1 empty=1 rearmed=0`: the dispatcher never re-armed
its own timer, in the healthy boot either (run267). That is normal: the
dispatcher is normally driven by the GPU's completion interrupt through
`adreno_cp_callback()` -> `adreno_dispatcher_schedule()`. When the
interrupts stop arriving, the dispatcher stops, and nothing re-arms it.

So the question becomes: **why did the GPU's interrupts stop arriving?**

## 4. The GPU interrupt handler is pathologically slow

From the poller's `/proc/stat` and `/proc/interrupts` in run271
(`CONFIG_HZ=250`):

| uptime | user | system | idle | irq | softirq | kgsl interrupts |
|---|---|---|---|---|---|---|
| 453 s | 67350 | 149642 | 92520 | 31796 | 6040 | 7823 |
| 661 s | 110544 | 242305 | 93153 | **52063** | 9302 | 12040 |

Between 453 s and 661 s the hard-IRQ time grew by 20,267 ticks = **81 s
of hard-IRQ time in 208 s of wall time**, and the only interrupt whose
count moved was the GPU's (4217 deliveries). That is **19 ms of
interrupts-disabled time per GPU interrupt**.

The tick rate shows it too: the idle ticks advanced at 204/s at t=453 s
and at 141/s at t=661 s. The missing ~30 % of ticks is time with
interrupts disabled.

**So the handler is stalling the whole system**, and the system time
grows by 92,663 ticks (371 s, 1.8 CPUs) over the same window. There are
no GPU fault messages in the log, so the GPU is not faulting; the handler
is just slow.

The suspects inside `adreno_irq_handler()` are the GMU AHB-fence poll
loop (`udelay(1)` x `FENCE_RETRY_MAX`=100) and the keepalive/GMU
counter reads. The "Status=0x%x Unmasked status=0x%x" message that the
fence-retry path prints is **not** in the log, so the fence loop never
reached its limit; the time is somewhere else.

`adreno.c` now times the handler and the fence poll and prints
`DIAG irq slow total=... fence=... retries=... st=...` when the handler
exceeded 1 ms, at most once a second.

## 5. The system-wide churn follows the dispatcher

run271's logdump, in time order:

| t | what |
|---|---|
| 58.9 s | `apexd-bootstrap` finishes normally (not a fault) |
| 148.7 s | the first GPU submit - the compositor starts drawing |
| 178.2 s | `init: processing action (sys.init.updatable_crashing=1)` - the system flags itself as crash-looping |
| 180.7 s | `failed to send del client cmd` and `failed while handling packet from 1:16440` begin - both from `net/qrtr/ns.c`, the **modem** transport - and they never stop: 1866 and 973 of them |
| 728.4 s | `apexd-unmount-all` |

So the loudest symptom of the stall is on the **modem/QRTR** side, and it
starts two seconds after the dispatcher stops. It is a consequence, not
the cause: the QRTR peer (the modem) is going away and coming back.

And the GPU's own state changes at the same moment: the port's
`DIAG ME_INIT submit` line shows `rbbm` (A5XX_RBBM_STATUS) going from
`c00003c1` to `1` between t=180.67 s and t=180.79 s, i.e. 45 us after
the first QRTR failure. The GPU's RBBM status changing is the GPU
not working.

## 6. The CPU side, again

* The load average of 51 in run271 is **not** runnable work: the last
  port-kernel sample shows 1/3818 runnable. It is uninterruptible
  sleep, as in run265 - threads blocked in `dma_fence_default_wait()` on
  fences that are never released.
* The machine is still 52-63 % idle throughout. **The CPU is not
  saturated and never was.**
* The frequency is pinned at the top OPP because there is no thermal path
  to pull it down (the same finding as before): `# CONFIG_QCOM_TSENS is
  not set` in the kernel that runs, and the CPU nodes have no
  `#cooling-cells`, so the thermal zones have nothing to throttle. run271
  had no cpufreq at all and still died of heat later than run265 did,
  because the CPU was at 800 MHz.

## 7. What is now proven, and what is not

Proven:

* The early hang is between the MDSS probe (3.06 s) and the logdump sink
  (8.98 s), with the panel lit. The APCC handoff (8.07 s) is in that
  window; it is not yet proven to be the cause.
* The GPU stall is not the APCC driver, the coupled clock transaction or
  the cpufreq policy: it happens with all of them removed.
* The GPU stall is the **dispatcher stopping**: the event groups stop
  being processed at t=149.4 s and the event callback stops at 152.1 s,
  so fences that are not already retired are never released.
* The GPU interrupt handler costs **19 ms of interrupts-disabled time
  per interrupt**, and the tick rate falls by a third.

Not proven:

* Why the GPU interrupts stop arriving (the 19 ms handler is the
  leading suspect, and the new timing print will say how much of the 19
  ms is the fence poll).
* Whether the 19 ms is the cause or the symptom. A slow handler means
  the GPU's completion interrupts are served late, and the dispatcher's
  work is scheduled from them, so a slow handler can starve the
  dispatcher - but something has to make the handler slow first.
* Why the modem's QRTR peer goes away and comes back.

## 8. Next

1. **Boot run272** (the run267 kernel with
   `initcall_blacklist=mdss_mdp_driver_init`, packaged by
   `run271-272-package-variants.sh`): the display never comes up, so the
   early hang can be tested with no panel live. If the phone then boots
   reliably, the display being live during the 3-9 s window is what
   kills it.
2. **Build the IRQ-handler timing** (the `DIAG irq slow` print) and boot
   it: the next boot says how much of the 19 ms is the fence poll.
3. **The modem**: the QRTR peer going away is the loudest symptom and it
   is unexplained. The port boots the modem from `mdm.mdt`; the donor
   does the same, so a port-vs-donor difference in the modem's remoteproc
   or its `adsp`/`adsprpc` is worth checking.
