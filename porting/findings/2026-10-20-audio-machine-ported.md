# The audio machine: the stack was never built, and the port of the PCM layer

**Date:** 2026-10-20 · **Tree:** `ack-kgsl` (6.12.93) · **Device:** tissot

## The cause of "no sound card"

`AudioSystem: Function: listAudioPorts Line: 1914 Failed` was reported 276
times per logcat window on the running phone. The vendor audio HAL opens
`/dev/snd` and finds only a timer, because there is no card: the phone has
no sound card at all.

The reason was not the device tree. `sound/soc/Makefile` gated the whole
`sound/soc/msm/` directory on `CONFIG_SND_SOC_WCD9335`, which is the
*upstream* WCD9335 codec's symbol. Commit `5ddf6b81d` renamed the port's
own copy of that driver to `CONFIG_SND_SOC_MSM_WCD9335`, so that the two
copies could be told apart, and `porting/tools/build-kernel.sh` turns the
upstream symbol off. The gate therefore never fired: **the machine
driver, the SDM660 CDC, the WCD9335, the AFE and the q6afe driver had
never been compiled into any kernel the build script produced.** The
device tree was not missing; the code was not in the kernel.

Fixing the gate is what turned the rest of this work into a list of
compile errors, which is how the rest of the port was found.

## What the port needed, and what it got

The donor (`oc-test`, CAF 4.19) and this kernel (Google's ACK
android16-6.12) are two generations of CAF's ASoC. The kernel side moved:

| CAF 4.19 (donor) | this kernel | what it meant |
| --- | --- | --- |
| DAI `probe`/`remove`/`compress_new`/`pcm_new` in `snd_soc_dai_driver` | the same fields in `snd_soc_dai_ops` | the CAF sources had to move the four fields into the ops |
| `snd_soc_component_driver.ops` (a `snd_pcm_ops`) and `.pcm_new` | the component's own callbacks plus `.pcm_construct` | the PCM platforms had to become components |
| `struct snd_pcm_ops.copy_user` (a user pointer) | `.copy` (an `iov_iter`) | the copy path had to be rewritten around the iterator |
| `struct snd_pcm_ops.compat_ioctl` | not present | the field, the component callback and the compat dispatch were added |
| `snd_pcm_delay_blk` | `.delay` | the delay callback had to take the component and drop the DAI |
| `set_channel_map` with writable slot maps | the slot maps are `const` | the signatures were corrected |
| `digital_mute` | `mute_stream` | renamed, with the stream argument added |
| `struct snd_soc_pcm_stream` without `aif_name` | the same | the field was added; CAF's frontend DAI routes on it |
| `pm_qos_remove_request` | `cpu_latency_qos_remove_request` | renamed |
| `strlcpy` | `strscpy` | renamed in v6.8 |
| `platform_driver.remove` returning `int` | returning `void` | the callbacks were retyped |
| `/* fallthrough */` | `fallthrough;` | the kernel's spelling |

CAF's ALSA extensions the tree did not have were added as well:
`snd_pcm_add_usr_ctls()` and `struct snd_pcm_usr` in
`sound/core/pcm_lib.c`, next to the volume extension the port already
carries, and `SNDRV_HWDEP_IFACE_AUDIO_BE`/`AUDIO_CODEC` in the uapi
header.

The audio sources that came across from the donor are the PCM platform
layer: `msm-pcm-routing-v2.c` (31,805 lines), `msm-pcm-q6-v2.c`,
`msm-pcm-q6-noirq.c`, `msm-pcm-hostless.c`, `msm-pcm-voice-v2.c`,
`msm-pcm-loopback-v2.c`, `msm-pcm-routing-devdep.c`, `msm-dai-q6-v2.c`,
`msm-dai-fe.c` and `msm-dai-stub-v2.c`, with the uapi headers CAF needs
(`audio_effects.h`, `voice_params.h`, `devdep_params.h`, `lsm_params.h`)
staged under `sound/soc/msm/caf-include/uapi/`.

## The device tree

The machine driver in this kernel does not read the older
`asoc-platform`/`asoc-cpu` lists: it names the components it wants, and a
component is found by the name of its device node. The PCM platforms are
therefore named `<driver>.<id>`, which is the form the ASoC core parses an
id out of a platform device name.

`arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-audio.dtsi` carries the
sound node (`qcom,msm8952-audio-codec`, with the four CSR GPIO muxes the
driver maps), the analog CDC (`qcom,pmic-analog-codec`, the codec the
card talks to), the nine PCM platforms, the frontend DAI, the backend
DAIs (one node per AFE port) and the CDC's pinctrl groups. The topology
is the donor's `mi8953/tissot/audio.dtsi` and `msm8953-audio.dtsi`, with
the property names this kernel's drivers read.

## What is not done

* **The compress (offload) and the listen-service platforms are not
  built.** They need CAF's `compress_params.h`, whose layout differs from
  the one this kernel's userspace expects: the old vendor audio HAL wants
  CAF's, the ROM's own AudioFlinger wants upstream's. That is a
  userspace ABI decision, not a porting one, so the offload PCM is left
  out of this slice. MP3/AAC offload and the listen service do not work.
* **The tasha (WCD9335) codec is not in the tree.** Xiaomi's boards
  delete it, so the card has no slimbus codec: the routes that need one
  are skipped. The analog CDC carries the microphone, the headphone and
  the speaker path.
* **Nothing here has been built into a kernel or run.** The sound/soc
  tree compiles clean and the device tree builds; whether the card
  registers, and whether the vendor HAL finds it, is not established.
* The AFE and the q6afe driver are in the tree but the AFE's own
  `qcom,msm-afe` node and the `qcom,audio-ref-clk` clock provider are
  not in the device tree yet.

## The CPU consequence

`porting/findings/2026-10-20-high-cpu-retry-storms.md` has the
measurements: the missing sound card is what makes the ROM's
`AudioSystem::listAudioPorts` fail 276 times per window, and that retry
loop is the largest single consumer of system time on the phone
(`system_server` at 37 % CPU, 1.65 CPU-seconds of system time per ten
seconds). The other retry loops in that finding are the modem, the
devfreq nodes, the touchscreen sysctl and Bluetooth, and they are
independent of this work.
