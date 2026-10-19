# run265: the live boot, the CPU burn, and the GPU fence that never signals

Date: 2026-10-19. Follows
`cpu-boot-failure-analysis-run261-264-2026-10-19.md` and
`gpu-retirement-stall-run261-2026-10-19.md`. Companion to
`HANDOFF-cpu-session2-2026-10-19.md`, whose run numbering and next-action
list this file corrects in several places.

## 1. What run265 is

The run264 image booted by hand on the user's phone, with the passive
poller attached:

* image `boot-run264.img`, SHA256
  `3b6e518f84a770b72fba825aa103177ac330fa47754113318a549759abc3b934`
  (the same bytes as `boot-run261.img` plus a `console=tty0` cmdline token)
* the poller's samples are in `run265-poll/`, one file every 3-4 s
* the logdump was pulled afterwards with
  `bash ../../logging/pull-run-evidence.sh 265 boot-run264.img`:
  `run265-logdump.log` (2,317,480 readable bytes), `run265-logdump.bin`,
  `run265-ramoops.json` (two CRC32-verified snapshot slots, seq 305 and 304)
* the summary script is `run265-logdump-summary.py`

**It booted, ran 581 s and died with the USB link gone.** The port kernel
reached the ROM, the display came up, and the same GPU retirement stall as
run261 developed. The logdump this time has a real console.

## 2. Corrections to the handoff

| Handoff said | Evidence |
|---|---|
| "the last successful run was run262" | It was **run261**. `run261-live/adb-timeline.jsonl` has 42 sightings of `6.12.93-4k` with `policy0` at 2016000 kHz, `/dev/ashmem` present, `sys.boot_completed=running`, and the phone back on stock at t=453 s. run262/263/264 never enumerated: `run262-logdump.log` and `run264-logdump.log` are 0 bytes, and their `adb-timeline.jsonl` records `state:""` for the whole 460 s. The run262 *image* came up when the user booted it by hand, so the image was fine; the scripted boot of it died. |
| "no code change separates run261 from run262/263/264" | Correct, and that is the point: `package-run261/262/263/264.json` all carry `kernel_payload_sha256 = 59eb2793a5f7993002f544864f18e46250f51395f1eec8b69b802374bfe33d15`, the same `ramdisk_sha256` and the same `init_sha256`. run263's image SHA256 equals run261's exactly. **The only differences are cmdline tokens**: run262 adds `cpufreq.off=1`, run264 adds `console=tty0`, run263 adds nothing. The intermittent early death is therefore not a code regression and not a cmdline effect - it is runtime nondeterminism in a 1/4 sample. |
| "the coupled clock transaction is exonerated" | Still correct, and now redundant: run262 died early with `cpufreq.off=1`, so the coupled transaction did not run in that failure either. The APCC *handoff* (the probe, which always runs) is the remaining suspect in the 1-6 s window. |
| "a CPU-saturated system_server starves the GPU dispatcher" | **Wrong.** The machine is mostly idle the whole time. At t=123 s: `cpu 4564 302 9056 61263 4976 598 146` = 84 % idle, load average 5.51. At t=577 s: `cpu 11792 1725 29970 74273 12067 4653 6283` = 52 % idle, iowait 8.5 %, but a load average of 63. The load is **uninterruptible sleep**, not runnable work: `dma_fence_default_wait()` with `intr=false` sleeps in `TASK_UNINTERRUPTIBLE`, so every thread waiting on the never-signalled GPU fence is a D-state task. The GPU is not CPU-starved. |
| "`CONFIG_QCOM_TSENS` is not set" | Correct for the kernel that actually ran, but the reason is not the defconfig. `arch/arm64/configs/defconfig:714` does say `CONFIG_QCOM_TSENS=y`; the build never uses it. `run261-build-host.sh:59` takes the config from the **previous image** (`scripts/extract-ikconfig` of the run258 kernel) and runs `olddefconfig` on it, and `run261-embedded.config:3697` says `# CONFIG_QCOM_TSENS is not set`. The defconfig line is dead. |
| "the thermal zones are missing" | The zones exist (`arch/arm64/boot/dts/qcom/msm8953.dtsi:1985`, four CPU zones with `cooling-device = <&CPU0 THERMAL_NO_LIMIT THERMAL_NO_LIMIT>`), and the thermal *governors* are registered. What is missing is the link: the CPU nodes (`msm8953-cpu.dtsi:640-684`) have **no `#cooling-cells`**, so `&CPU0` is not a cooling device and the zones have nothing to throttle. The donor has `#cooling-cells = <2>` on all eight CPU nodes (`oc-test/.../msm8953-cpu.dtsi:63..190`). Two independent breaks: no sensor driver, and no cooling device. |
| "the fastrpc needs a reserved-memory child" | Wrong in two ways. `of_reserved_mem_device_init_by_idx()` (`drivers/of/of_reserved_mem.c:594`) parses a **`memory-region` phandle**, not a `reserved-memory` child, and the `qcom,fastrpc` binding (`Documentation/devicetree/bindings/misc/qcom,fastrpc.yaml`) does not allow such a child (`additionalProperties: false`). The `no reserved DMA memory for FASTRPC` line is a `dev_info` on a path whose failure the probe ignores, and upstream's own `msm8916.dtsi:2035` has the same shape and the same message. The real fastrpc defect is different - see section 6. |

## 3. The CPU side is working; what it lacks is thermal protection

Working, with evidence from `run265-logdump.log` and the live poller:

* One shared cpufreq policy over CPUs 0-7, the seven stock fused-bin-2 OPPs
  (652.8 .. 2016 MHz), governor `schedutil`; `time_in_state` at t=123 s shows
  9187 of 11620 ticks at 2016 MHz.
* The APCC handoff completes: `qcom-apcc-msm8953: boot state: pll 00000000
  00000000 00000000 0000000f mux 00000401 00000000 00000403` then `shared
  CPU/CCI domain, speed bin 2, CPU 799999804 CCI 399999902 Hz, corner 2`
  (t=8.07 s), followed by `cpufreq: cpufreq_online: CPU0: Running at unlisted
  initial frequency: 799999 KHz, changing to: 1036800 KHz` (t=8.11 s).
* **No** `CPU transition to N Hz failed` message, so every rate change the
  governor asked for was accepted by the coupled transaction.
* No soft lockup, no RCU stall, no hung task, no panic, no oops in the
  recovered console. `decode-reset.py` reports `No ACKRESET1 record`, so the
  death was not an orderly reboot.

The gap:

* The policy is pinned at the 2016 MHz top OPP for 79 % of the first 123 s
  while the machine is 84 % idle. That is correct `schedutil` behaviour for
  a *shared* policy with one thread at 100 % util, and that thread is
  system_server. So the frequency is a symptom, not the fault.
* Nothing can throttle the CPU: no TSENS driver in the kernel, and the CPU
  nodes are not cooling devices. The phone therefore runs at the top OPP
  until it dies of heat - run261 at ~326 s, run265 at ~581 s.

## 4. The CPU burn is a PowerManagerService binder storm, and our own log made it worse

The user's logcat line from the live run:

```
ramoops: DIAG signal_generate sig=7 code=2 sender_pid=925 sender_tgid=839
sender_comm=PowerManagerSer target_pid=925 target_tgid=839
target_comm=PowerManagerSer group=0 result=0
```

**PowerManagerService (tid 925, tgid 839 = system_server) raises SIGBUS on
itself in a loop.** The Android binder driver raises SIGBUS when a
transaction's buffer copy faults, so this is a failing binder transaction
being retried without backoff. `run265-logdump.log` has 6,081
`DIAG signal_generate` records - 44 % of the 13,764 parsed messages - and
**in the final two seconds of the console 237 of 237 messages are signal
records**. The last real message before the spam takes over is at t=553 s
(`QSEECOM: qseecom: smc 30000006 -> 0`); everything after it is the storm.

The same log shows the services around it are crash-looping:
`init: ... started service 'vendor.per_proxy' has pid 5316` followed by
`DIAG process_exit pid=5316 tgid=5316 comm=pm-service exit_code=0xff00
group_exit_code=0xff00 group_exit=1` (0xff00 = killed by a signal), plus
315 `failed to send del client cmd` and 151 `failed while handling packet
from 1:16443` records, and `init: processing action
(sys.init.updatable_crashing=1)`. `system_server` accounts for 2.07 of the
3.04 busy CPUs at t=578 s (TIME+ 19:58.59 over 578 s of uptime), and it is
almost all *system* time (187 % sys of 280 % busy).

Two separate things are true here, and the port caused one of them:

1. **The storm itself is a userspace problem** in the port's userspace
   stack, not a kernel defect. It is a symptom of the display stall (the
   power manager's binder client keeps asking for something the dead
   display path cannot answer).
2. **The port's own DIAG print turned a 12 messages/second event into an
   evidence-destroying flood.** The console is a 1 MiB ring; an unbounded
   print per signal evicted the kgsl messages the ring exists to preserve.
   This is now fixed (section 7).

## 5. The GPU stall, measured live

Live measurements from `run265-poll/` (the GPU interrupt count is the
retirement signal, and the kgsl interrupt is the only one that moves):

| uptime | kgsl_3d0_irq | rate | load avg |
|---|---|---|---|
| 123.1 s | 2762 | | 6.25 |
| 136.4 s | 2968 | 10 /s | |
| 154.6 s | 3077 | **6 /s** | |
| 185.8 s | 3871 | **46 /s** (recovered) | |
| 276.9 s | 5255 | 1.8 /s | 59.99 |
| 577.7 s | 5801 | **1.8 /s** | 63.01 |

The GPU goes quiet, comes back, and then goes quiet for good. At the same
time SurfaceFlinger reports `Faking VSYNC due to driver stall for thread
app` and `Total missed frame count: 696, HWC missed frame count: 696, GPU
missed frame count: 0`, and HWUI reports frame durations of 1.3 s, 11.8 s
and 11.3 s.

The mechanism, from the code:

* The display waits on the fence with `dma_fence_wait_timeout()`
  (`drivers/video/fbdev/msm/mdss_sync.c:392`). That path only looks at the
  core's `DMA_FENCE_FLAG_SIGNALED_BIT`
  (`drivers/dma-buf/dma-fence.c:786,803`).
* The kgsl's timeline fence reports itself as retired through its own
  `->signalled` callback (`kgsl_timeline.c:192`), which the port's
  `mdss_wait_sync_fence()` prints as `status:0x1`. The observed fence had
  `seqno:530304 timeline:532096 queued:532096 retired:532096 status:0x1`:
  the GPU retired the work, and the core bit was still not set.
* The core bit for this fence is set in exactly one place:
  `dma_fence_signal_locked()` called from `kgsl_timeline_signal()`
  (`kgsl_timeline.c:257`), and that function is called from exactly one
  place in the driver: `drawqueue_retire_timelineobj()`
  (`adreno_dispatch.c:406`) - the GPU **dispatcher's** retire path.
* `kgsl_timeline.c` and `kgsl_sync.c` are byte-identical to the donor's
  (0 changed lines); `adreno_dispatch.c` differs only in the port's DIAG
  dumps. So the suspect is not a kgsl porting difference but the dispatcher
  not running, or running with a stale seqno.

`kgsl_timeline_signal()` has a second, quieter failure mode that fits the
observation exactly:

```c
	if (seqno < timeline->value)
		goto unlock;      /* the fence list is NOT walked */
```

A call carrying a seqno below the value the timeline already reached
returns without walking the fence list, so a fence whose seqno lies between
that seqno and `timeline->value` is not signalled by that call.

**The kgsl debugfs `events` node and the kgsl sysfs state are not
readable from the adb shell**: debugfs is 0700 and adbd runs as `shell`
(`cat: /sys/kernel/debug/kgsl/events: Permission denied`), and every kgsl
sysfs attribute is 0600 root (the `snapshot/` counters are the only
readable ones, and they read 0). `tracefs` *is* readable but not writable,
so the kgsl tracepoints cannot be enabled from the shell. The only channel
that reaches the state is the kernel console, which is why the decision is
to print it there.

## 6. The fastrpc defect is an ioctl ABI mismatch, not a missing DMA region

The port's `include/uapi/misc/fastrpc.h` and the stock userspace's header
disagree on every ioctl number:

| ioctl | port (6.12 tree) | stock userspace (CAF 4.19) |
|---|---|---|
| INVOKE | `_IOWR('R', 3, struct fastrpc_invoke)` | `_IOWR('R', 1, ...)` |
| MMAP | `_IOWR('R', 6, ...)` | `_IOWR('R', 2, ...)` |
| MUNMAP | `_IOWR('R', 7, ...)` | `_IOWR('R', 3, ...)` |
| INIT | `_IOWR('R', 5, struct fastrpc_init_create)` | `_IOWR('R', 6, struct fastrpc_ioctl_init)` |
| GET_DSP_INFO | `_IOWR('R', 13, ...)` | `_IOWR('R', 16, ...)` |

The port's `fastrpc_device_ioctl()` answers `-ENOTTY` for anything it does
not know (`drivers/misc/fastrpc.c:2188`), and `-ENOTTY` is exactly what the
userspace reports:

```
adsprpcd: fastrpc_apps_user.c:2742: Error 0xffffffff: apps_dev_init: failed to setup fastrpc session in kernel
adsprpcd: fastrpc_apps_user.c:2870: Error 0xffffffff: apps_dev_init failed for domain 0, errno Inappropriate ioctl for device
```

"Inappropriate ioctl for device" is `ENOTTY`. The `FASTRPC_IOCTL_INIT` the
stock `adsprpcd` issues lands on the port's `default:` arm, and the session
setup fails, so the daemon restarts every 25 ms. This is a UAPI mismatch
between the port's driver and the stock ROM's userspace, and it is a
separate piece of work from the display stall.

## 7. Changes made in this session

All three are in the working tree, uncommitted, alongside the pre-existing
uncommitted work.

1. **`drivers/gpu/msm/kgsl_timeline.c`, `kgsl_timeline.h` - timeline
   retire/fence diagnostic.** `kgsl_timeline_signal()` now records, per
   call, the seqno it was asked to signal, the timeline value it holds, how
   many fences are still queued on the list, how many it actually signalled
   and whether the call was stale (`seqno < value`); the print happens
   after the timeline lock is dropped, because the retire path must not
   sleep under it. `kgsl_timeline_fence_alloc()` records whether the new
   fence was queued at all (`added=`) and the list length, because a fence
   that was created already retired is not the dispatcher's responsibility
   and a fence that was queued is. Output is sampled (the first 64 calls,
   then every 256th) because the console is a 1 MiB ring and an unbounded
   print here would evict the evidence it exists to preserve.
   This distinguishes "the dispatcher stopped calling", "the fence was never
   on the list" and "the call carried a stale seqno" in one boot.

2. **`fs/pstore/ram.c` - the per-event signal print is gone.** The counts
   are kept: the first occurrence of each signal number is printed once
   (so the sender is known - that line is what identified
   PowerManagerService), and a per-signal-number tally plus the totals are
   printed when the capture stops. `process_exit` is sampled the same way
   the snapshot liveness witness already is. The `apps_wdt` read is sampled
   the same way: it printed 3070 times in run265 and the registers never
   changed.

3. Nothing on the CPU frequency path was changed yet. The thermal gap is
   two separate pieces of work - a TSENS driver for this part (the tree's
   `drivers/thermal/qcom/tsens-v2.c` has no msm8953 sensor table) and the
   missing `#cooling-cells` / OPP `cooling-device` link - and it does not
   gate the GPU diagnosis, so it stays out of this build.

## 7a. run266: the instrument was on the wrong path, and the stall did not happen

`boot-run266.img` (`6d3846df4ac7e96e53eda3b16156ce66ebdb3c9676e882cd2bb0fec3150d2ee4`),
kernel payload `cc3f65d7b5e17175847614cb63b6a7a6714d1476430444e02687a94297127921`,
command line identical to run261. It is the run261 kernel plus the three
files above.

**Two results, one good and one bad.**

*Good: the boot did not stall.* The GPU interrupt rate stayed at 62/s from
197 s to 470 s (run265: 1.8/s), the load average fell from 12.7 to 5.8
(run265: 63), there was no `possible gpu syncpoint deadlock`, no
`sync_fence_wait failed` and no SIGBUS storm. The GPU kept retiring work
for the whole 480 s.

*Bad: the diagnostic produced nothing.* Not one `DIAG timeline_signal` or
`DIAG timeline_fence` line, although both strings were in the built kernel
(`strings vmlinux` shows them, and `kgsl_timeline_diag_fence.calls` is in
the symbol table). So those two functions were never called.

That is the useful part: **the fence the display waits on is not a
`kgsl_timeline.c` fence.** `mdss_wait_sync_fence()` printed
`drv:kgsl-timeline`, and that is `kgsl_sync_fence_driver_name()`
(`kgsl_sync.c:300`); `kgsl_timeline.c`'s fence reports `kgsl-sw-timeline`.
The real release path is:

```
adreno_dispatcher_work()            adreno_dispatch.c:2939
  -> kgsl_process_event_groups()     kgsl_events.c:309
     -> _process_event_group()       kgsl_events.c:66
        -> signal_event() -> kthread_queue_work(device->events_worker)
           -> kgsl_sync_fence_event_cb()   kgsl_sync.c:101
              -> kgsl_sync_timeline_signal() kgsl_sync.c:348
                 -> dma_fence_is_signaled_locked()
                    -> dma_fence_signal_locked()   <- sets the core bit
```

and the core bit is the only thing `dma_fence_wait_timeout()` looks at
(`drivers/dma-buf/dma-fence.c:786,803`). The display's wait therefore
depends on the **GPU dispatcher** and on nothing else.

**A measured hypothesis that turned out wrong:** the console volume. The
port's own DIAG output was 59 % of the run265 console, and the cmdline
routes the kernel log to a 115200-baud UART, where a line costs ~17 ms of
busy-wait. The obvious story was "the port's own printk starved the
dispatcher". `compare-printk-timing.py` kills it: run266 printed **more**
(21,876 messages, 45.6/s, an implied UART cost of 79 % of the boot) than
run265 (13,764 messages, 23.7/s, 41 %) and did **not** stall. The console
volume is not the cause.

## 7b. run267: the diagnostic on the right path, and it works

`boot-run267.img` (`f7ea34704e30cf06d0510c31b618b0658cc73a5f629b53096ccfbddedb3e5a23`),
kernel payload `db3acee2392c1f1625e2f2e364609e31551c0b7ff1a47aff2b045d3625b40b4b`,
command line identical to run261.

The instrument was moved onto the real path:
`kgsl_sync_timeline_signal()` (the fence release itself),
`kgsl_sync_fence_event_cb()` (the event group callback),
`_process_event_group()` (how many events are still queued) and
`_dispatcher_update_timers()` (whether the dispatcher re-armed its timer,
and which of the three conditions stopped it).

**run267 also did not stall**: at 426 s the load average was 4.61, the
per-CPU breakdown showed 67 % idle system-wide, and the GPU interrupt count
was still climbing steadily.

The instrument is validated on the healthy path:

```
401 x DIAG sync_timeline_signal   60.6 s .. 437.8 s
 64 x DIAG sync_fence_event
 64 x DIAG event_group
 64 x DIAG dispatcher_timers
```

with, for example,

```
t=60.644s  sync_timeline_signal name=kgsl-3d0_2-surfaceflinger(751)-surfaceflinger(766)
                    ts=4224 last=4224 pending=10 signalled=1 calls=1
t=437.829s sync_timeline_signal name=kgsl-3d0_10-com.evo.inware(5168)-RenderThread(8300)
                    ts=129280 last=129280 pending=2 signalled=1 calls=64
```

and, over the whole boot, `pending` between 1 and 119, `stale=1` never,
and `signalled=0` in 12 of the 401 calls (a fence that is on the list but
whose timestamp has not retired yet - normal).

One thing the healthy run already teaches: **`_dispatcher_update_timers()`
does not re-arm the timer most of the time** (`rearmed=0` in every sampled
call, mostly with `preempt=1 empty=1`). So "the timer was not re-armed" is
not by itself the fault; what matters is whether the dispatcher keeps
running at all, and the `sync_fence_event` / `sync_timeline_signal` lines
answer that.

**So the GPU stall is now diagnosable in one boot.** The next stalling
boot's logdump will say which link broke: no `sync_fence_event` (the
dispatcher stopped processing event groups), `sync_fence_event` but no
`sync_timeline_signal` (the event worker did not run the callback), or
`signalled=0` with a growing `pending` (the fence is queued but never
retired).

## 7c. The early hang: the host-side poller is the best-supported cause

Four early deaths and two successes, all with the same kernel payload:

| run | how it was booted | poller running during the boot window | result |
|---|---|---|---|
| 261 | host script | no | booted |
| 262 | host script | yes | died early |
| 263 | host script | yes | died early |
| 264 | host script | yes | died early |
| 265 | by hand | no (started after adb came up) | booted |
| 266 | by hand, poller started after adb came up | no | died early |
| 266 (2nd try) | by hand, no host activity at all | no | booted |

run266 is the clean experiment: the first attempt had the poller running
from before the `fastboot boot` and died early with an all-zero logdump;
the second attempt had **no host activity whatsoever** for 210 s after the
`fastboot boot` and came up, then ran to 480 s and was pulled cleanly.

**The mechanism is not established.** A plausible one: the poller runs
`adb -s <serial> shell ...` every 3-4 s, and `adb` keeps the USB transport
active while the phone is in fastboot and while the port kernel brings up
its gadget. Whatever the port's USB stack does when the host is polling it
at that rate, it is enough to turn a 1-in-4 boot failure into a 4-in-4 one.
**The practical rule that follows, and that run266 and run267 both used:
keep the host completely idle for the first ~200 s of a port boot.** The
poller is then started once adb is up, which is safe (run265 and run266
both ran the poller for hundreds of seconds after adb came up without
trouble).

## 7d. The CPU: healthy, but pinned at the top OPP with no way to throttle

The "CPU 100 %" a monitor shows is the **frequency**, not the utilisation.
At 190 s of run267:

```
cpu  18172 5408 28895 133356 6461 1936 467 0 0 0
```

= 67 % idle system-wide, ~86 % idle per core, load average 4.61 on eight
CPUs. But `scaling_cur_freq` is 2016000 kHz in every sample, and
`time_in_state` at 123 s put 9187 of 11620 ticks (79 %) at the top OPP.

Two separate causes, and the second is the real defect:

1. `schedutil` on a **shared** policy takes the maximum util of the
   policy's CPUs, so one busy thread puts the whole cluster at the top
   OPP. That is upstream behaviour, not a port bug.
2. **Nothing can pull it back down.** `CONFIG_QCOM_TSENS` is not set in the
   kernel that runs (`run261-embedded.config:3697`), and the CPU nodes
   (`msm8953-cpu.dtsi:640-684`) have no `#cooling-cells`, so the thermal
   zones' `cooling-device = <&CPU0 THERMAL_NO_LIMIT THERMAL_NO_LIMIT>`
   points at a node that is not a cooling device. The donor has
   `#cooling-cells = <2>` on all eight CPU nodes
   (`oc-test/.../msm8953-cpu.dtsi:63..190`). The zones exist, the
   governors are registered, and the whole throttle path is inert.

Until the thermal path is ported, the phone runs at 2016 MHz until it
dies of heat - run261 at ~326 s, run265 at ~581 s.

## 8. Still not proven

* Why the early hang in the 1-9 s window happens. The evidence channel
  still does not exist that early: the logdump snapshotter only becomes
  ready at t=8.98 s (the MMC block device registers at `device_initcall`),
  and the APCC handoff is at t=8.07 s, so a hang before ~9 s leaves an
  all-zero logdump. `initcall_blacklist=` remains the only lever that
  needs no rebuild.
* Why the GPU stalls at all. The release path is now instrumented on the
  right link, and two boots with the instrument (run266, run267) both came
  up clean, so the failing boot has not been caught yet. The stall is
  intermittent: it happened in run261 and run265 and not in run266/run267.
* What PowerManagerService is retrying, and why the binder transaction
  faults. The storm is downstream of the stall - it starts at t=40 s,
  while the first fence timeout is at 238 s - so it is a symptom, not the
  cause, but the thing it is retrying is still unknown.
* Whether the fastrpc UAPI mismatch is what makes `vendor.per_proxy`
  crash-loop.

## 9. The root question, and why Shizuku is not the answer

The kgsl state the bring-up needs is unreadable from the adb shell:

* `/sys/kernel/debug/kgsl` - the directory is 0755 but the shell is
  SELinux-denied on listing it and on reading `events`
  (`avc: denied { getattr } ... tcontext=u:object_r:sysfs:s0`).
* the kgsl sysfs attributes (`gpu_busy_percentage`, `dispatch/inflight`,
  ...) are 0600 root *and* SELinux-denied.
* the port kernel has no root: the ROM's enforcing policy is what applies,
  and `adb root` does not stick, so `su` is unavailable
  (`/product/bin/su` exists - Magisk is installed - but magiskd never
  starts, because the port's boot image carries the diag ramdisk instead
  of Magisk's patched one).

**Shizuku does not help on its own.** Started over adb it runs with the
`shell` uid in the `shell` SELinux domain, which is exactly the identity
that is already denied; it cannot read a 0600 root file or bypass a
`neverallow`. It only becomes useful if it is backed by root - which
requires Magisk's daemon, which requires the rooted boot image.

**The rooted boot image is therefore the real answer**, and the port's
packager is already shaped for it: `package-diag-boot.py` keeps the base
image's ramdisk and replaces only the `init` record
(`customize_ramdisk()`), and it can append CIL to the ramdisk's
`userdebug_plat_sepolicy.cil` record (`--policy-append FILE`).

Two ways to keep the root, in increasing order of work:

1. **Policy and mode only, no root at all.** The diag ramdisk's init is
   PID 1 and already root, so it can `chmod` the kgsl sysfs attributes
   and append CIL rules that let the `shell` domain read the kgsl
   debugfs and sysfs. That is enough for the whole kgsl state question
   and costs one ramdisk rebuild - no kernel build, no Magisk, no
   flashing.
2. **A Magisk-patched base image**, so `su` works on the port kernel.
   `magiskboot patch` produces a base whose ramdisk has `magiskinit` as
   `/init`; because the packager replaces the `/init` record, the diag
   init would have to be started *by* magiskinit (or the diag init would
   have to start magiskd itself) for both to survive. The device already
   has Magisk installed (`com.topjohnwu.magisk`), so the binaries are on
   the phone.

Kernel Flasher on the device (`com.github.capntrips.kernelflasher`) is the
AnyKernel3 path: `flash_ak3.sh` runs `update-binary 3 1 "$Z"`, which `dd`s
the image into the boot partition as root. That is how a *rooted* kernel
gets installed on a real phone, and it is why the base image's ramdisk
matters: a base that is already Magisk-patched keeps its root when the
kernel payload is replaced.

## 10. How to read the next run

* The early hang: the logdump is all zero for any death before ~9 s, so
  the only lever that needs no rebuild is `initcall_blacklist=`. The
  initcall names are in the vmlinux: `kgsl_3d0_init`, `mdss_mdp_driver_init`,
  `mdss_fb_init`, `mdss_dsi_driver_init`, `mdss_smmu_driver_init`,
  `apcc_msm8953_driver_init`, `adsp_driver_init`, `fastrpc_init`,
  `remoteproc_init`.
* The GPU stall: read the four `DIAG` lines in the logdump, in this
  order. `DIAG dispatcher_timers` (is the dispatcher alive and is it
  re-arming), `DIAG event_group` (are events queued), `DIAG
  sync_fence_event` (is the event callback firing), `DIAG
  sync_timeline_signal` (is the fence being released, and with how many
  fences still pending).
* The CPU: `scaling_cur_freq` and `stats/time_in_state` for the
  frequency, `/proc/stat` for the utilisation. A monitor that reports
  "100 %" is reporting the frequency.

