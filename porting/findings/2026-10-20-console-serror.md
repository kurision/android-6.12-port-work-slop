# A console that writes to hardware kills the boot on this phone

**Date:** 2026-10-20 · **Found on:** run304 (main) and the audio images
(run309-run314) · **Evidence:** `/tmp/opencode/run304-no-uart/`,
`/tmp/opencode/run304/logdump.bin`

## The symptom

The kernel stops early, the panel never leaves the splash, the phone
does not reboot, and a forced reboot brings it back (to a dim panel, then
to the ROM). No kernel log is visible: the console is `console=ttynull`,
and the port's `pstore_blk` never opens the logdump partition.

## What the logdump says

The logdump partition of a **main-branch** boot (run304, no audio in the
kernel) ends like this:

```
... failed to send del client cmd
... failed while handling packet from 1:16443
kworker/u33:1
synchronous external abort: Fatal exception
```

A **synchronous external abort** is an SError: a synchronous access to a
device that is not accessible. The last messages before it are the QRTR
namespace worker failing to reach the modem's QRTR node, which is the
known "the modem never comes up" state of this port.

## The cause

The command line of every image built by `build-kernel.sh` carries the
UART console:

```
earlycon console=ttyMSM0,115200
```

The early console writes to the UART's MMIO from the first printk
onwards, and the regular console keeps writing to it for the whole
boot. When the UART's clock is not on — after the modem's subsystem
restart handling, or at any other moment when the rail is down — the
write takes the SError, and the SError is fatal: the kernel stops
there. No panic, no reboot, no log.

The proof is the variant the user built from run304: **the same image
with only `earlycon` and `console=ttyMSM0,115200` removed boots to the
ROM**, and every byte outside the command-line field is unchanged
(`/tmp/opencode/run304-no-uart/verification.json`).

## What to do

* No console that touches hardware. The **null console** takes the
  messages: `console=ttynull` writes nothing anywhere and costs
  nothing, and the ramoops console zone still records the messages, so
  the kernel-side snapshotter can still carry them to the logdump
  partition.
* **No framebuffer console either.** `console=tty0` is the same class
  of problem: the fbdev's framebuffer is not necessarily mapped, and a
  console write to it takes the same abort.
* The UART console stays useful as a *diagnostic* — it is how the SError
  was found — but it is not safe in an image that has to boot.

## Why this was not seen before

Every earlier image carried the same command line, so every earlier
boot was one clock event away from the same death. The images that
booted (run289 to run305) were lucky; the ones that did not (run304,
and the audio images run309 to run314) were not. The audio stack was
never the cause of those hangs.

## The consequence for the audio work

The audio images run309 to run314 were all built with the UART console
and all hung before the userspace, which is why the card never
registered and why no sound card was found. The next audio image
carries the null console only.
