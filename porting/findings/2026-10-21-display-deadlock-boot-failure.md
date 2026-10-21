# The boot failure is a display-driver deadlock, not the audio stack

**Date:** 2026-10-21 · **Branch:** `main` · **Evidence:** the pstore records of the
failing boot, recovered from `/sys/fs/pstore` of the next boot

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

## The deadlock

```c
/* mdss_mdp_irq_enable(), process context */
	spin_lock_irqsave(&mdp_lock, irq_flags);
	...
	writel_relaxed(irq.irq_mask, mdata->mdp_base + reg.clr_off);
	writel_relaxed(mdata->mdp_irq_mask[irq.reg_idx],
			mdata->mdp_base + reg.en_off);
	mdata->mdss_util->enable_irq(&mdss_mdp_hw);   /* the HW IRQ is enabled here */
	spin_unlock_irqrestore(&mdp_lock, irq_flags);

/* mdss_irq_handler(), interrupt context */
	if (intr & MDSS_INTR_MDP) {
		spin_lock(&mdp_lock);                  /* the handler takes the same lock */
		mdata->mdss_util->irq_dispatch(MDSS_HW_MDP, irq, ptr);
		spin_unlock(&mdp_lock);
```

The hardware interrupt is enabled while the lock its own handler takes is
held, and the interrupt is delivered to whichever CPU the GIC picks. Whether
this deadlocks depends on the interrupt arriving in that window - which is
why it is intermittent, and why it is triggered by the DSI timeout: the
timeout is what makes the interrupt arrive right then.

Both functions are **byte-identical to the CAF 4.19 donor**
(`../oc-test/drivers/video/fbdev/msm/`): the port did not introduce this
pattern, it inherited it. CAF does not hit it because its panel does not time
out at the moment the framebuffer is opened.

## What follows from this

* The CAF 4.19 audio stack is **exonerated**. It was the obvious suspect
  because the audio images fail every time, but a main-tree image without
  any audio fails the same way, and the failure is in the display path.
* The **panel's DSI link failing to ACK at the display bring-up** is the
  thing to fix. The port's own diagnostics already print the three status
  registers that show it (`mdss_dsi_fifo_status`, `mdss_dsi_ack_err_status`,
  `mdss_dsi_timeout_status`), and `status=1` on the timeout register says
  the link timed out in the same millisecond the framebuffer was opened.
* The inherited CAF race is worth fixing on its own account: enabling an
  interrupt under the lock its handler takes is a deadlock waiting for the
  right interrupt routing, whatever the panel does.

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
