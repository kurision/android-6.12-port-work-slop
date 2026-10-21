# Why a failing boot leaves no log, and how to get one

**Date:** 2026-10-21 · **Branch:** `main` · **Related:**
[2026-10-21-audio-stack-in-main.md](2026-10-21-audio-stack-in-main.md)

The port's boots sometimes stop at the splash, and this was hard to diagnose
because **every channel that should carry the log of a failing boot is
empty**. This writes down why each one is empty, with the measurements, and
what does work.

## Corrections (later on 2026-10-21)

* **Why the audio images leave nothing:** their kernels are 3.6 MB too large
  and overrun their own DTB, so they die before a console or a ramoops zone
  exists. See
  [2026-10-21-kernel-overruns-the-dtb.md](2026-10-21-kernel-overruns-the-dtb.md).
* **There are two failures, not one that audio makes more likely.** Every
  image over the size limit fails every time, with no log and no reset.
  Images that fit (#18, run322) fail now and then with a display lockup
  about 50 s in, which panics and resets itself
  ([2026-10-21-display-deadlock-boot-failure.md](2026-10-21-display-deadlock-boot-failure.md)).
* **"The console zone holds about 190 s" is wrong:** it held about 500 KB
  after 38 s of boot (`logs-2026-10-21/brightness-revert-125129/`). More
  importantly, at boot pstore copies a valid previous buffer to
  `/sys/fs/pstore` and then resets the zone (`fs/pstore/ram_core.c:542-566`),
  so reading `/sys/kernel/ramoops_raw` early, the protocol in "What does
  work", never recovers the previous boot. Read `/sys/fs/pstore` instead.
  It holds the previous boot only after a warm reset (a panic reboot); after
  a long-press reset or a detour through recovery it was empty every time.
* **The "failing boot's window" below is not from a failing boot.** The
  lines quoted come from a boot that worked; no failing boot of an
  oversized kernel has logged anything. The clock dependency cycles and the
  qseecom heaps are present in good boots too, and nothing points at them.

## The symptom is not audio-specific

The `ack-audio` stack in `main` was blamed first, because with the CAF 4.19
audio in the kernel the boot always stops at the splash. But:

* the same image with all five bring-up switches off
  (`msm_audio_off=1 msm_dsplib_off=1 msm_apr_off=1 msm_cdc_off=1
  msm_digcdc_off=1`) stops at the splash as well, so it is not the machine
  driver, the DSP library, the APR transport or either CDC;
* **a main-tree image without any audio stops at the splash sometimes too** -
  it can take two or three power cycles to get past it.

So there is an intermittent early-boot failure that the audio stack makes
much more likely, and the audio stack is not its cause.

## What the failing boot leaves behind: nothing

Three channels exist. All three are empty after a failed boot.

### 1. The `logdump` partition's text region: the recorder starts at 20.8 s

`scripts/initramfs-diag/init.c` reads `/dev/kmsg` and writes it to the
`logdump` partition (`dump_log()`), and the file it produces starts at the
*first* kernel message, because `/dev/kmsg` replays the ring buffer. But the
capture threads only start much later:

```
  6.480 s  ramoops: DIAG: previous reset page commit ret=0 offset=66322432
 20.839 s  DIAG: Android USB capture unavailable; storage continues
 20.840 s  DIAG: SD capture unavailable; other sinks continue
```

The partition only appears at all at 6.48 s (the kernel-side snapshotter's
first successful open of it; MMC block devices register at `device_initcall`),
and the userspace capture is only reached at ~20.8 s after the USB and SD
sinks have been tried and failed. **A boot that stops before 20.8 s writes
nothing**, and the partition keeps the last *successful* boot's log instead.
That is what every read of the partition after a failure showed: the good
boot's log, kernel `6.12.93-4k-gc0e9c6487bab-dirty #23`, ending at 921.7 s.

### 2. The kernel-side snapshot slots: the boot stops before the device opens

`fs/pstore/ram.c` has a periodic snapshotter that copies the live ramoops
reservation to the `logdump` partition every 500 ms, into two alternating
slots at offsets 62914560 and 63967232, "so the console log of a boot that
never reaches init is still there to be read". It is exactly the right idea
and it has never worked:

* the "snapshot38 logdump snapshotter ready" message appears in **no** boot
  log in this tree;
* after the failed boots both slot headers are **all zeros** (magic `RAMO` =
  0x52414d4f absent), and the port's own decoder says
  `header_valid=False ... rejected slot console=unavailable dmesg=0`.

The reason is the same 6.48 s: the snapshotter opens the partition when it
appears, and a boot that stops before that never commits a sample.

### 3. pstore: nothing to register

`/sys/fs/pstore` is empty after a failed boot. The ramoops region is
`ramoops@86800000` in the port's devicetree
(`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts:122`), a 4 MiB hole in
System RAM that nothing else claims. A *hang* writes no pstore record: the
`dmesg` zone is written at panic or orderly shutdown, and the phone is
power-cycled instead.

## What does work: the ramoops console zone in RAM

The port's own kernel-side snapshotter reads the reservation, and the
reservation is a **1 MiB** block at 0x86800000. Its last ~524 KB is the
pstore **console zone**, which printk writes from the very first message.
So the failing boot's kernel log *is* in RAM, and it survives into the next
boot - the port's pstore depends on exactly that ("previous reset page
commit" reads the previous boot's records at 6.48 s of the next boot).

The zone is a ring buffer, and it holds about 190 s of console output: read
too late, the next boot's own log has eaten the previous boot's.

Measured on the device:

```
$ adb shell 'cat /sys/kernel/ramoops_raw' > ramoops_raw.bin     # 1 MiB
$ # the printk stream starts at offset 487481 and runs to the end
```

**The protocol that works:** after a failure, boot a working image and read
`/sys/kernel/ramoops_raw` the moment adb appears (~40 s into the new boot).
The previous boot's tail - which is the hang point - is still in the zone,
because the new boot has only written ~40 s of console output by then.

`/tmp/opencode/capture-ramoops.sh` does exactly that: it polls for the
device and grabs the reservation on the first poll that finds it.

The RAM survives the reboot that follows a failure: the port's pstore reads
the previous boot's records across reboots, which is the same property.

## What the failing boot's window is

Putting the channels together, a failing boot stops somewhere between the
kernel's first messages and ~6.5 s, i.e. in the `device_initcall` /
`late_initcall` driver probes, before any userspace exists:

```
  0.443 s  OF: /soc@0/sound: could not get #gpio-cells for /soc@0/cdc_ext_pa_pinctrl
  0.446 s  /soc@0/clock-controller@1800000: Fixed dependency cycle(s) with mdss_dsi_pll
  0.485 s  /soc@0/clock-controller@1800000: Fixed dependency cycle(s) with mdss_dsi_pll
  0.538 s  SCSI subsystem initialized
  0.539 s  usbcore: registered new interface driver usb
  0.543 s  scmi_core: SCMI protocol bus registered
  0.545 s  platform ion:heap@1b: assigned reserved memory node qseecom_region@0
  0.549 s  ION heap system created
  0.554 s  Advanced Linux Sound Architecture Driver Initialized.
```

Two things in that window are worth a look when the log is in hand:

* the clock dependency cycles between the clock controller and the two MDSS
  DSI PLLs, broken by the clock framework, in the display path;
* the `qseecom_region` ION heaps at 0.545 s. The port's own devicetree
  comment says that without the TZ-shared carveout mapping "the first TA
  data transaction wedges silently" - and a wedge in the secure world is
  exactly the kind of thing that could be **intermittent**, because it
  depends on the state the previous boot left behind. That fits the symptom
  better than anything else found so far: the failure needs two or three
  power cycles, and it is not audio-specific.

Neither is a conclusion yet. They are the two places to look first in the
log of a failing boot.

## The next step

1. Flash the image that stops at the splash.
2. Let it stop. Force it off. Boot into recovery.
3. Flash a working image and reboot.
4. The moment adb appears, read `/sys/kernel/ramoops_raw`
   (`capture-ramoops.sh` does this) and decode the tail.

The tail of that reservation is the failing boot's last console output: the
hang point.
