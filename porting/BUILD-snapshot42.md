# Snapshot42 — the fragment was never applied (display, audio, USB serial, SELinux knob)

## Root cause, established 2026-10-08

`scripts/tissot-ack.config` requests **80 built-ins**. The kernel actually on
the phone is missing **17** of them. Every one of those 17 is a subsystem that
has never worked in this port, and every one of them was attributed to
something else along the way.

| symbol | shipping kernel | what its absence caused |
|---|---|---|
| `CONFIG_DRM_MSM` | not set | **no display driver at all** |
| `CONFIG_DRM_PANEL_OTM1911` | not set | no driver for this device's actual panel |
| `CONFIG_DRM_FBDEV_EMULATION` | not set | kernel cannot modeset; panel keeps bootloader splash |
| `CONFIG_FB_CORE`, `CONFIG_FRAMEBUFFER_CONSOLE` | absent | no fbcon, no text console on the panel |
| `CONFIG_VT` | not set | no virtual terminal |
| `CONFIG_SECURITY_SELINUX_BOOTPARAM` | not set | `selinux=0` on the cmdline is inert |
| `CONFIG_USB_U_SERIAL_CONSOLE` | absent | no `ttyUSB`-style serial console |
| 8× `CONFIG_SND_SOC_QDSP6_*` | absent | no audio AFE/routing |
| `CONFIG_BT_QCOMSMD` | `=m` (fragment wants `y`) | no built-in Bluetooth transport |

Verified mechanically, not inferred:

```sh
# 1. the fragment does work when it is actually merged
make O=/tmp/fragcheck gki_defconfig
scripts/kconfig/merge_config.sh -m -O /tmp/fragcheck /tmp/fragcheck/.config \
        scripts/tissot-ack.config
make O=/tmp/fragcheck olddefconfig
# → CONFIG_DRM_MSM=y, CONFIG_DRM_PANEL_OTM1911=y,
#   CONFIG_DRM_FBDEV_EMULATION=y, CONFIG_VT=y,
#   CONFIG_SECURITY_SELINUX_BOOTPARAM=y

# 2. the shipping config is not that
#    17 of the fragment's 80 built-ins are missing from the shipped
#    Image.gz's embedded IKCONFIG
```

**Why it happened.** Every build from snapshot26 onward reused an existing
output directory seeded from the baseline config and ran a bare
`make olddefconfig`, hand-editing individual symbols. That path never calls
`merge_config.sh`, so the fragment was inert. `scripts/build-ack-tissot.sh`
does merge it — and already asserts `DRM_MSM` and `DRM_PANEL_OTM1911` as
required — but the recent builds bypassed the script.

`handoff-ack-mainline.md:44` warned about exactly this and it was not applied:
"Symbols that do not exist in ACK are dropped silently by olddefconfig, and
`merge_config.sh` only warns. Re-verify a fragment with `ack-driver-audit.py`
rather than trusting `make` output."

## The display finding is independent evidence for it

The panel driver is **already written** and already in this tree:
`drivers/gpu/drm/panel/panel-otm1911.c`, `compatible = "orisitech,otm1911"`,
hand-ported from the CAF `dsi-panel-otm1911-fhd-video.dtsi` descriptor for
this exact panel. `porting/findings/05-prior-art.md:45` already flagged it as
this device's panel, and postmarketOS boots the same panel with
`CONFIG_DRM_PANEL_MDSS_OTM1911_FHD=m`.

So the display stack was never missing a driver. It was compiled out.

## Change for snapshot42

No source change. **Build method change only:** use
`scripts/build-ack-tissot.sh`, which merges the fragment and fails the build
on any missing required symbol.

```sh
cd ~/<path>/ack-android16-6.12
OUT_DIR=out-snapshot42 ./scripts/build-ack-tissot.sh
```

This intentionally does **not** reuse the shipping config the way snapshot41
did. Snapshot41 holds the config fixed to isolate the SCM trace gate;
snapshot42 deliberately changes it, because that is the fix.

## Expected delta vs the shipping kernel

17 symbols, all in the direction the fragment asks for. Specifically gained:
display (`DRM_MSM`, `DRM_PANEL_OTM1911`, `FB_CORE`, `FRAMEBUFFER_CONSOLE`,
`DRM_FBDEV_EMULATION`, `VT`), the SELinux bootparam, USB serial console, the
eight `SND_SOC_QDSP6_*` audio symbols, and `BT_QCOMSMD` promoted `m` → `y`.

`CONFIG_QSEECOM`, `CONFIG_ION`, `CONFIG_SECURITY_SELINUX`, 4K pages, VFAT,
F2FS, EXT4, devtmpfs and the configfs ACM/FunctionFS pair are all requested by
the fragment too and must be verified `=y` before booting.

## Why this is expected to be visible

Every previous run died at a fixed ~72–101 s with a black screen and logdump
as the only channel. With `FB_CORE` + `FRAMEBUFFER_CONSOLE` + `VT` compiled in,
the same stall should print the console on the panel. That makes the next
diagnostic readable without SD, logdump or USB — and it is the first time the
port will show anything on the device at all.

## Risk

Low and bounded: still `fastboot boot` into RAM, nothing flashed, no slot
change, no ROM writes. The config change cannot make the userspace stall worse
than it already is — the stall happens long after the display would come up.

The real risk is **interpretation**: snapshot42 changes many symbols at once,
so if the stall moves or vanishes, it is not attributable to any single one.
That is acceptable because the SCM question is answered by snapshot41's
clean single-variable run, which boots first.