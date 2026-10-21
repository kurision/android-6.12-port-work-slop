# The audio images do not boot because the kernel overruns its own DTB

**Date:** 2026-10-21 · **Branch:** `main` · **Evidence:**
`porting/artifacts/snapshot60/logs-2026-10-21/layout-134234/` (the layout),
`.../run327-q6audio-boot-133712/` (the control that boots), the boot images
in `porting/artifacts/snapshot60/` and `../ack-kgsl-artifacts/`

## The symptom

Every image built on the CAF 4.19 audio stack stops at the splash with no
log in any channel and never resets itself: the audio branch's run307 to
run317a2, and main's run323 to run326. The audio bring-up switches
(`msm_audio_off=1` and the rest) made no difference, and neither did the
brightness revert (run325) or turning the periodic ramoops snapshotter off
(run326).

## The cause

The phone's bootloader loads the kernel and the DTB at fixed addresses and
never checks one against the other. The CAF audio stack made the kernel
3.6 MB larger, and that is enough to reach the DTB.

Measured on the running kernel (#18) with `/proc/iomem`, the
`/chosen/linux,initrd-*` properties and debugfs `memblock/reserved`:

| What | Physical range |
|---|---|
| Kernel, code to the end of `.bss` | `0x10080000 - 0x132affff` |
| DTB (81271 bytes, the size of `/sys/firmware/fdt`) | `0x13400000 - 0x13413d76` |
| initrd | `0x13600000 - 0x14e574db` |

So the kernel's whole in-memory footprint - `image_size` in the arm64 Image
header, which includes `.bss` - has to end below `0x13400000`:
**54001664 bytes (51.50 MiB)** from its load address.

CAF's LK does exactly this (lk2nd carries the same code):

* `project/msm8953.mk` sets `ABOOT_IGNORE_BOOT_HEADER_ADDRS`, so
  `update_ker_tags_rdisk_addr()` replaces the boot header's kernel, tags and
  ramdisk addresses with fixed per-target ones. The header's own addresses
  (`kernel@0x80008000`, `ramdisk@0x81000000`) are never used.
* `boot_linux_from_mmc()` decompresses the kernel, `memmove`s it to the
  kernel address, and only then `memmove`s the DTB to the tags address.
* Its overlap checks test the kernel against LK's own memory and the DDR
  bounds (`check_aboot_addr_range_overlap()`, `check_ddr_addr_range_bound()`),
  never against the tags or ramdisk address.

A kernel that is too large therefore has the DTB written over its own image
by the bootloader, and then zeroes the DTB (and the start of the initrd)
when it clears `.bss`. It dies before it has a device tree, a console or a
ramoops zone: nothing is logged anywhere, and no lockup or hung-task
detector is running yet to reset it. Which instruction it dies on is
**unverified**, and Xiaomi's LK binary may differ in detail from the CAF
source, but the addresses above are measured, not read from the source.

## The evidence: every image is on the side its size predicts

| Image | Kernel | `image_size` | Headroom | Booted |
|---|---|---|---|---|
| #18, `boot-test-vendorqrtr` | `gc6104317ff23` | 52625408 | +1376256 | yes |
| run304-no-uart | `gc6104317ff23` | 52625408 | +1376256 | no¹ |
| run322 | `gc0e9c6487bab` | 53346304 | +655360 | yes |
| **run327-q6audio** | `gde9c32349a2a` | 53346304 | +655360 | **yes** |
| run307 - run317a2 (audio branch, 11 images) | various | 57540608 - 57737216 | -3.5 to -3.7 MB | no |
| run323, run323a1, run324 | `g94f5ed1b91d0`, `geffd8684b5fc` | 57606144 | -3604480 | no |
| run325 (brightness revert) | `gde9c32349a2a` | 57606144 | -3604480 | no |
| run326-nosnap (snapshotter off) | `gde9c32349a2a` | 57606144 | -3604480 | no |
| **run328-q6audio-pad** | `gde9c32349a2a` | 57606144 | -3604480 | **no** (hard hang) |

¹ run304 died of the UART console abort recorded in `02917b2d9` ("run304 of
the main branch died that way"), a separate failure that the null console
has since removed. Its kernel fits below the DTB, so it is not a
counterexample; it is the one failure in this table with a different cause.

The decisive pair is run327 and run328. Both are run325's source with
run322's audio configuration (upstream QDSP6 on, CAF audio off). run328 adds
nothing but dead padding (`kernel/ack_sizepad.c`, never committed: 2867200
bytes of `.rodata` and 1392640 of `.bss`), bringing its `image_size` to
exactly run325's. run327 boots to `sys.boot_completed=1`; run328 hangs hard.
No CAF code is in either.

## What this changes

* **The CAF audio stack's code is not the cause**; its size is. So is any
  other 3.6 MB of kernel.
* **The brightness revert, the snapshotter and the thermal DTS change are
  not the cause** either: all three are in run327, which boots.
* **The intermittent display lockup is a separate bug.** #18 and run322 fit
  below the DTB and still sometimes panic about 50 s in, in the display's
  first kickoff after the splash handover
  (`logs-2026-10-21/display-panic/`). That one panics and resets itself; the
  DTB overrun never resets.
* **run327 has 640 KiB of headroom.** The next change that grows the kernel
  by that much will fail the same way. `porting/tools/build-kernel.sh` now
  refuses to package a kernel whose `image_size` is over the limit and warns
  below 1 MiB of headroom (`ACK_LK_KERNEL_LIMIT`, `ACK_LK_HEADROOM_WARN`).

## Making room for the audio stack

To bring the CAF audio stack back, the kernel has to lose at least 3604480
bytes of `image_size`, plus a margin. What two of the debug options in the
port's configuration cost, each turned off alone from the CAF-audio
configuration (`image_size` 57606144):

| Turned off | `image_size` | Saved | Still over by |
|---|---|---|---|
| `CONFIG_UBSAN` | 56557568 | 1048576 | 2555904 |
| `CONFIG_KALLSYMS_ALL` | 55443456 | 2162688 | 1441792 |

`FTRACE`, `SLUB_DEBUG`, `KFENCE` and `DEBUG_INFO_BTF` were not measured:
the run was stopped. The debug options stay on while the port is in
bring-up. The audio stack is being made loadable modules instead, which
takes its 3.6 MB out of `image_size` altogether: `msm-pcm-routing-v2.o`
alone is 2.3 MB (1.0 MB code, 0.46 MB data, 0.81 MB `.bss`).

## How the layout was captured

On a running port kernel, as root:

    cat /proc/iomem
    cat /sys/firmware/devicetree/base/chosen/linux,initrd-start   # big-endian
    cat /sys/firmware/devicetree/base/chosen/linux,initrd-end
    mount -t debugfs none /sys/kernel/debug   # if it is not mounted
    cat /sys/kernel/debug/memblock/reserved   # entry 2 is the DTB

and the image sizes from the boot images themselves: the kernel is the
gzip member at the start of the kernel payload, and `image_size` is the
little-endian u64 at offset 16 of the decompressed Image.

## Sources

* lk2nd's copy of CAF LK:
  [`project/msm8953.mk`](https://raw.githubusercontent.com/msm8953-mainline/lk2nd/main/project/msm8953.mk),
  [`app/aboot/aboot.c`](https://raw.githubusercontent.com/msm8953-mainline/lk2nd/main/app/aboot/aboot.c)
* `Documentation/arch/arm64/booting.rst:139`: "At least image_size bytes
  from the start of the image must be free for use by the kernel." The LK
  places the DTB inside that range once `image_size` passes 54001664.
