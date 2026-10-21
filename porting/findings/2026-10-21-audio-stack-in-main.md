# The CAF 4.19 audio stack is in main; the boot hang is not yet explained

> **Explained later on 2026-10-21:** the hang is the stack's size, not its
> code. The audio kernels' `image_size` reaches past the DTB the bootloader
> places at `0x13400000`. See
> [2026-10-21-kernel-overruns-the-dtb.md](2026-10-21-kernel-overruns-the-dtb.md).

**Date:** 2026-10-21 · **Branch:** `main` (merge `94f5ed1b9`) · **Donor:** `ack-audio`
(CAF 4.19, from `../oc-test`)

This records where the audio work stands after it was merged into main, and
what is measured and what is not.

## What is in main now

The complete CAF 4.19 audio stack, from the `ack-audio` branch:

| part | file |
|---|---|
| the DSP library | `sound/soc/msm/q6asm.c`, `q6core.c`, `q6adm.c`, `q6voice.c`, `q6audio-v2.c`, `q6lsm.c`, `q6_init.c`, `rtac.c`, `sp_params.c`, `avtimer.c`, `q6common.c` |
| the APR client and transport | `sound/soc/msm/apr.c`, `apr_v2.c`, `apr_tal_rpmsg.c` |
| the analog and digital CDC | `sound/soc/msm/msm-analog-cdc.c`, `msm-digital-cdc-legacy.c`, `msm-dts-srs-tm-config.c`, `digital-cdc-rsc-mgr.c` |
| the machine driver and its links | `sound/soc/msm/msm8952.c`, `msm8952-dai-links.c` |
| the WCD DSP glink manager | `sound/soc/msm/wcd-dsp-glink.c` |

The configuration follows the branch: `CONFIG_SND_SOC_MSM8952=y`,
`CONFIG_SND_SOC_ANALOG_CDC=y`, `CONFIG_SND_SOC_DIGITAL_CDC_LEGACY=y`,
`CONFIG_WCD_DSP_GLINK=y`, and the tree's own later AVD stack and its APR
client are out, because they define the same names as CAF 4.19's.

The transport is the one that already worked: the DSP library talks to the
ADSP over the rpmsg channel the ADSP announces as `apr_audio_svc`, and this
tree's devicetree already asks the remoteproc for exactly that channel
(`arch/arm64/boot/dts/qcom/msm8953.dtsi:1886`).

## The merge kept main's build and init handling

`porting/tools/build-kernel.sh` and `scripts/initramfs-diag/init.c` are
**byte-identical to main's version before the merge**. The command line and
the `/init` handling that boot the phone today were fixed in main and are
not touched here. The branch's `ACK_EXTRA_CMDLINE` hook is therefore not
carried over; the bring-up switches are added with the packager's
`--append-cmdline` instead, on an already built image.

## The boot hang: measured, not explained

The audio images hang before the phone is usable, and the hang is early
enough that `adb` never comes up (no adbd, no `sys.boot_completed`).

What is **measured**:

* The audio image without any switch hangs.
* The image with `msm_audio_off=1` (the machine driver does not register)
  hangs as well, so the machine driver's own probe is not the whole story.
* The image with all five bring-up switches on
  (`msm_audio_off=1 msm_dsplib_off=1 msm_apr_off=1 msm_cdc_off=1
  msm_digcdc_off=1`) was built but not given a clean run: the phone was
  reflashed with another image in between. **That run is still owed.**

What is **not** measured: where the boot stops. The port's own channels for
it were checked and none of them carried the audio boot's log:

* The logdump partition holds the **previous** boot's log, not the hung
  audio boot's: the periodic snapshotter in `fs/pstore/ram.c` writes the
  live ramoops reservation there every 500 ms, but the snapshot slots at
  offsets 62914560 and 63967232 of the partition were **all zeros** after
  the hang, so the hung boot never committed a sample. The text region
  holds the main tree's run320 boot (kernel `#21`, `adbd` started at
  39.5 s), not the audio boot.
* The ramoops region is at `0x86800000` in the port's devicetree
  (`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts:122`); the ROM's
  devicetree reserves a different one (`ramoops@91400000`), so the
  recovery build cannot read it, and there is no `/dev/mem` in recovery.
* The bootloader does not support `fastboot fetch`, so a partition cannot
  be read from fastboot.

So the next step is the cheap one: run the all-switches-off image to
completion. If it boots, the hang is inside the CAF 4.19 audio stack and
the switches bisect it one part at a time. If it still hangs, the cause is
outside those five parts - the devicetree changes, or the machine driver's
own probe of the sound card.

The switches live in the drivers, so each step of that bisection is a
repackage and a flash, not a build:

```
msm_audio_off      sound/soc/msm/msm8952.c          the machine driver
msm_dsplib_off     sound/soc/msm/q6_init.c          the DSP library
msm_apr_off        sound/soc/msm/apr_tal_rpmsg.c    the APR transport
msm_cdc_off        sound/soc/msm/msm-analog-cdc.c   the analog CDC
msm_digcdc_off     sound/soc/msm/msm-digital-cdc-legacy.c  the digital CDC
```

## What the phone should show when it works

* `cat /proc/asound/cards` - the card must register. It was
  `--- no soundcards ---` before.
* `dmesg | grep -i asoc` - the machine driver's probe, the DAI links, the
  CDC and the DSP bring-up.
* `logcat | grep listAudioPorts` - the ROM's vendor HAL calls it in a
  retry loop, and the retries are a large part of the CPU load measured in
  [2026-10-20-high-cpu-retry-storms.md](2026-10-20-high-cpu-retry-storms.md).

## The component naming, in one paragraph

This kernel's ASoC matches a link's codec by its **component**, not by its
DAI. A link's codec entry has to carry the name of the codec's component or
its device node; an entry with only a DAI name is refused (`ASoC: Neither
Component name/of_node are set`) and the card is then never registered.
CAF only had to name the DAI, so every link in the machine driver was
given a component: the dummy codec by its name (`snd-soc-dummy`), the two
CDC codecs by their device node. The component names in the devicetree have
to match the ones the machine driver looks up: `msm-pcm-dsp.0`,
`msm-pcm-dsp.1`, `msm-pcm-dsp.2`, `msm-pcm-routing`, `msm-pcm-afe`,
`msm-pcm-hostless`, `msm-pcm-voice`, `msm-pcm-loopback`, `msm-pcm-dsp-noirq`,
and the FE DAI `msm-dai-fe`.

## Evidence

| file | what |
|---|---|
| `../ack-kgsl-artifacts/boot-run317-audio.img` | the first audio image from the audio branch (fixed init, clean command line) - hangs |
| `../ack-kgsl-artifacts/boot-run317a1-audio.img` | the same with `msm_audio_off=1` - hangs |
| `../ack-kgsl-artifacts/boot-run317a2-audio.img` | the same with all five switches - **not yet run to completion** |
| `/tmp/opencode/audio317/logdump-hung.bin` | the logdump partition read from recovery: the main tree's run320 log, with the audio boot's snapshot slots empty |
