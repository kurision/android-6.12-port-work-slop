# The boot failure is a display-driver deadlock, not the audio stack

**Date:** 2026-10-21 · **Branch:** `main` · **Evidence:** the pstore records of the
failing boot, recovered from `/sys/fs/pstore` of the next boot

## Corrections (later on 2026-10-21)

This finding conflates two failures. Read these before the rest.

* **It is not why the audio images, or anything after run322, fail to
  boot.** Those kernels are 3.6 MB too large and overrun their own DTB; they
  die before any log exists and never reset. See
  [2026-10-21-kernel-overruns-the-dtb.md](2026-10-21-kernel-overruns-the-dtb.md).
  What this finding describes is the *other* failure: an intermittent lockup
  on kernels that fit (#18, run322), about 50 s in, which panics and resets
  itself.
* **The panic record is real** and is in
  `porting/artifacts/snapshot60/logs-2026-10-21/display-panic/` (kernel
  `gc6104317ff23 #18`). The excerpts below were transcribed by hand: the
  real trace reads `vfs_open+0x28/0x4c`, and the `59.659` line is a separate
  RCU stall report at the same place (`console-ramoops-0.clean.txt:3739`).
* **"All eight CPUs at 100% system" is wrong.** The utilization block is
  five 4 s samples of CPU0 alone (`kernel/watchdog.c:420-429`). The other
  CPUs kept running: T216 logs a DIAG line every 2 s through the stall.
* **"0% hardirq" does mean something.** `CONFIG_IRQ_TIME_ACCOUNTING=y` is
  already on and live (`sched_clock` runs at 19.2 MHz, above the 1 MHz
  threshold in `kernel/time/sched_clock.c:232`). With the DSI error handlers
  printing exactly once, this argues against reading B (an interrupt storm
  on CPU0).
* **The DSI timeout is not the trigger.** The same
  `mdss_dsi_timeout_status: status=1` follows the display HAL's fb open in
  boots that come up (`logs-2026-10-21/fixed-boot-vendorqrtr/logdump-text.txt:3801`,
  `run322-recon-082839`, both run322 hang-test resets). Bit 0 is outside the
  BTA/LP_RX mask CAF uses (`mdss_dsi_host.c:3235`), so it is not an ACK
  timeout, and the prints are CAF's own `pr_err`, not the port's DIAG.
* **What does differ:** in every boot that comes up, the first kickoff logs
  `DIAG dsi_on: ctrl=0 cold bring-up`, `dsi_on: done` and
  `kickoff post-commit`, and the DSI error handler runs a second time
  followed by `mdss_mdp_video_intf_recovery`. In the panic boot none of these
  appears: the thread stopped in `mdss_mdp_video_display()` before panel-on.
* **Unsourced:** the `kernel_panic,oomdlockup:_hung_tasks` boot reason and
  the `7999` history entry appear in no artifact; AOSP `bootstat` would
  produce `kernel_panic,softlockup:_hung_tasks` for this panic. The
  vendorqrtr capture's own history is `bootloader,73`.
* **The WLED/backlight work does not change the odds.** The panic boot (#18)
  predates `d3998f3ec`, and reverting it (run325) left the later images
  failing; they fail on size.
* **The recovery procedure at the end does not work as written.** At boot,
  pstore copies a valid previous buffer out to `/sys/fs/pstore` and then
  resets the zone (`fs/pstore/ram_core.c:542-566`), so a raw read of
  `/sys/kernel/ramoops_raw` only ever holds the current boot. The previous
  boot's records survive only a warm reset (a panic reboot); after a forced
  long-press reset or a detour through recovery, pstore was empty every
  time.

## The symptom, restated

The port's phone stops at the boot splash, sometimes needs two or three power
cycles to get past it, and sometimes reaches the home screen and then reboots.
It is **not** audio-specific: a main-tree image without the CAF 4.19 audio
stack does it too, and the audio images with all five bring-up switches off
do it as well.

## The failure, as the kernel recorded it

`sys.boot.reason` after the failure:

```
kernel_panic,oomdlockup:_hung_tasks
```

and the pstore dmesg record of that boot:

```
watchdog: BUG: soft lockup - CPU#0 stuck for 34s! [android.hardwar:687]
CPU#0 Utilization every 4s during lockup:
	#1: 100% system,	  0% softirq,	  0% hardirq,	  0% idle
	... (all eight CPUs at 100% system)
CPU: 0 UID: 1000 PID: 687 Comm: android.hardwar Tainted: G        W
pc : _raw_spin_unlock_irqrestore+0x1c/0x5c
lr : mdss_mdp_irq_enable+0x104/0x164
Call trace:
 _raw_spin_unlock_irqrestore+0x1c/0x5c
 mdss_mdp_irq_enable+0x104/0x164
 mdss_mdp_video_display+0x84/0x434
 mdss_mdp_display_commit+0xa40/0x1060
 mdss_mdp_overlay_kickoff+0xbb0/0x15c4
 mdss_mdp_overlay_on+0x264/0x284
 mdss_fb_blank_unblank+0x218/0x35c
 mdss_fb_blank_sub+0xc4/0x298
 mdss_fb_open+0x11c/0x268
 fb_open+0xb0/0x16c
 chrdev_open+0x1a0/0x244
 do_dentry_open+0x238/0x53c
 vfs_open+0x28+0x4c
 path_openat+0xa64+0xd10
 do_filp_open+0xb0+0x154
 do_sys_openat2+0x84+0xec
 __arm64_sys_openat+0x70+0x9c
Kernel panic - not syncing: softlockup: hung tasks
```

The console record of the same boot puts the trigger in place, 0.001 s after
the framebuffer is opened:

```
 49.664  mdss_fb_open: mdssfb_80000 by android.hardwar pid=687 par=ok
 49.665  mdss_hw_init: mdss_mdp: hw_init begin rev=269484032
 49.665  mdss_mdp_overlay_start: DIAG123 overlay_start pre: rgb0 ndx=0x8 src0=90001000 SPLASH size=07800438
 49.665  mdss_mdp_overlay_start: DIAG118 overlay_start splash_cleanup rc=0
 49.665  mdss_dsi_fifo_status: status=44441000
 49.665  mdss_dsi_ack_err_status: status=10000000
 49.665  mdss_dsi_timeout_status: status=1        <<< the DSI link timed out
 ...     (nothing from the display driver for the next ten seconds)
 59.659  [C0] lr : mdss_mdp_irq_enable+0x104/0x164      <<< the soft lockup detector
 ...     (nothing)
 84.042  Kernel panic - not syncing: softlockup: hung tasks
```

So: `android.hardware` (the display HAL) opens the framebuffer at 49.66 s,
the DSI link **times out without an ACK** in the same millisecond, and the
commit path never comes back.

## The mechanism: not settled, and the two readings that fit

Two readings fit the evidence, and they are not the same bug.

### Reading A: a lock interaction in the interrupt-enable path

The interrupt is armed under two locks:

```c
/* mdss_mdp_irq_enable(), process context */
	spin_lock_irqsave(&mdp_lock, irq_flags);         /* lock 1, mdss_mdp.c */
	...
	mdata->mdss_util->enable_irq(&mdss_mdp_hw);       /* -> mdss_enable_irq() */
	spin_unlock_irqrestore(&mdp_lock, irq_flags);

/* mdss_enable_irq(), mdss_util.c */
	spin_lock_irqsave(&mdss_lock, irq_flags);         /* lock 2 */
	...
		enable_irq(hw->irq_info->irq);              /* the GIC line is armed here */
	spin_unlock_irqrestore(&mdss_lock, irq_flags);
```

and the handler takes `mdp_lock` (lock 1) in `mdss_irq_handler()`. Both
functions are **byte-identical to the CAF 4.19 donor**
(`../oc-test/drivers/video/fbdev/msm/`): the port did not introduce this
pattern, it inherited it. CAF does not hit it because its panel does not time
out at the moment the framebuffer is opened.

What does *not* follow from this, though: with `spin_lock_irqsave` on CPU0
the interrupt cannot be handled on CPU0, it can only be delivered to another
CPU, whose handler then spins on `mdp_lock` until CPU0 releases it. Nothing
in the shown critical section sleeps or waits for the handler, so on its own
this is a latency and hard-lockup hazard, not a deadlock.

### Reading B: interrupt starvation from an already-asserted source

The DSI error latches are already set **before** the interface interrupt is
armed:

```
 49.665  mdss_dsi_fifo_status: status=44441000
 49.665  mdss_dsi_ack_err_status: status=10000000
 49.665  mdss_dsi_timeout_status: status=1
```

(`mdss_dsi_ack_err_status()` and `mdss_dsi_timeout_status()` are the error
handlers; they do write the status back to clear it, so the handler ran.)
Arming a level-triggered source whose error condition is already asserted,
and whose clearing happens in the handler, can turn into an interrupt storm:
the GIC re-asserts the line after every EOI. The task then never gets
scheduled, the soft lockup detector fires, and the reported stack is the
task's frozen context - the instruction right after `spin_unlock_irqrestore`
cleared `PSTATE.I` - which is exactly the `pc`/`lr` pair in the report.

This reading also explains the intermittency better: a DSI link that
sometimes ACKs and sometimes does not is a marginal link, not a deterministic
lock-order bug. A deterministic bug would fail every boot.

### What would settle it

* `softlockup_all_cpu_backtrace=1` and `hardlockup_all_cpu_backtrace=1`:
  where the *other* seven CPUs are. In `queued_spin_lock_slowpath` it is a
  lock (reading A); in `mdss_irq_handler` or the DSI handler it is an
  interrupt storm (reading B); in `console_unlock`/`vprintk` it is printk
  re-entrancy on the framebuffer console - which is this very display
  driver, and the port's own DIAG printk runs in the commit path.
* A per-source interrupt counter, printed once from process context: a storm
  identifies itself, and names the block (MDP or DSI0) that re-asserts.
* `CONFIG_IRQ_TIME_ACCOUNTING` on, before reading "0% hardirq" in the
  utilization dump; without it, hardirq time is counted as system time.
* Lockdep (`CONFIG_PROVE_LOCKING`) to state any `mdp_lock`/`mdss_lock`
  inversion explicitly. Note that two different locks are called `mdp_lock`
  (one in `mdss_mdp.c`, one per DSI controller in `mdss_dsi_host.c`), so
  read lockdep by class address, not by name.
* A/B boots, each a repackage and a flash: mask the DSI error/ack/timeout
  sources until after the first commit; arm the interface interrupt outside
  the locks; remove the port's DIAG printk from the display and IRQ paths.
  Each of those moves one mechanism out of the picture.


## Why the phone reboots and tries again

The panic path explains the loop. `panic=60` is on the command line, so the
kernel does not reset immediately:

```
 88.269  pstore: backend (ramoops) writing error (-28)
 88.269  Rebooting in 60 seconds..
```

So the phone sits at the splash for a minute after the panic (the panel
handover never completed, so the splash is what is on screen), then resets,
the bootloader starts it again, and the next attempt may or may not take the
same path. That is the "rebooting and trying again" behaviour, and it is
why an image can be good for half an hour and then panic:

* `boot-test-vendorqrtr` (kernel `gc6104317ff23`) ran 26 minutes fine in the
  fixed-boot evidence and then panicked at 84 s in the display path on a
  later boot of the **same image**;
* `persist.sys.boot.reason.history` shows the same shape:
  `kernel_panic,oomdlockup:_hung_tasks,7999` - a boot that ran 7999 s and
  then died the same way.

The trigger is a race in the panel's DSI link, not a property of the image.
What changes the odds between images is the display path's code: `run322`
and the merged audio images carry the newer WLED/backlight work
(`d3998f3ec`, `c0e9c6487`), while the images that ran for hours are the
older display code.


## What follows from this

* The CAF 4.19 audio stack is **exonerated**. It was the obvious suspect
  because the audio images fail every time, but a main-tree image without
  any audio fails the same way, and the failure is in the display path.
* The **panel's DSI link failing to ACK at the display bring-up** is the
  thing to fix. The port's own diagnostics print the three status registers
  that show it (`mdss_dsi_fifo_status`, `mdss_dsi_ack_err_status`,
  `mdss_dsi_timeout_status`), and `status=1` on the timeout register says
  the link timed out in the same millisecond the framebuffer was opened.
* The interrupt-enable path is worth hardening either way: arming a
  level-triggered source whose error condition is already asserted, under
  two locks whose handler also takes one of them, is fragile whatever the
  panel does.

## How the evidence was recovered

The failing boot leaves no log in the `logdump` partition (the userspace
capture starts at 20.8 s, the partition exists from 6.5 s, and a boot that
stops at 49 s still writes - but a *later* successful boot overwrites it).
What does survive is the port's ramoops region: the console zone holds the
failing boot's messages and pstore registers the panic record.

    adb shell 'cat /sys/kernel/ramoops_raw'        # 1 MiB, the console zone
    adb pull /sys/fs/pstore/dmesg-ramoops-0        # the panic record
    adb pull /sys/fs/pstore/console-ramoops-0      # the console record

Read them in the *next* boot: the console zone is a ring buffer that holds
about 190 s of output, and the panic record is written by the kernel at the
panic.

`porting/findings/2026-10-21-failing-boot-has-no-log.md` has the details of
why the other three channels come up empty.
