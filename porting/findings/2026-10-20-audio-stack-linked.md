# The CAF 4.19 audio stack is in the kernel and links

**Date:** 2026-10-20 · **Branch:** `ack-audio` · **Donor:** `../oc-test` (CAF 4.19)

This closes the gap described in
[2026-10-20-audio-dsp-library-gap.md](2026-10-20-audio-dsp-library-gap.md)
and in [2026-10-20-audio-machine-ported.md](2026-10-20-audio-machine-ported.md).
What is written here is what the code does. **What the phone does with it is
not yet measured** — see "Not proven" below.

## What came in

The donor's CAF 4.19 audio, ported to this kernel:

| part | donor file | note |
|---|---|---|
| the DSP library | `techpack/audio/dsp/*.c` | `q6asm`, `q6core`, `q6adm`, `q6voice`, `q6audio`, `rtac`, `cal_utils`, `sp_params`, `avtimer`, `msm_audio_ion`, `q6_init`, `msm_mdf`, `q6lsm` |
| the APR client | `techpack/audio/ipc/apr.c`, `apr_v2.c` | the client, and the subsys state helper |
| the APR transport | `techpack/audio/ipc/apr_tal_rpmsg.c` | the rpmsg driver |
| the WCD DSP glink manager | `techpack/audio/ipc/wcd-dsp-glink.c` | the analog CDC's calibration source |
| the WCD calibration hwdep | `techpack/audio/asoc/codecs/wcdcal-hwdep.c` | the headset calibration hwdep |
| the machine and the PCM platforms | the port's own `sound/soc/msm/` | ported in `867dfaaac` |

The headers are staged under `sound/soc/msm/caf-include/`, so the tree's own
`sound/` and `include/uapi/sound/` are untouched. The one exception is CAF's
compress parameter layout: it is staged as `caf-compress_params.h`, because
the tree's `include/uapi/sound/compress_params.h` is the AOSP one and the ROM's
AudioFlinger speaks that one.

## What was left out, and why

* **The WCD9335 codec.** This board has no tasha codec: the donor's Xiaomi
  boards delete the `sound-9335` node, and the audio is the analog CDC plus
  the MAX98927 speaker amplifier. The machine driver's DAI link tables and the
  WSA881x amplifier block are gone with it.
* **The slimbus slave helper.** It sets up the slimbus codecs. There are none.
  `q6_init.c` no longer calls it.
* **The tree's own APR** (`drivers/soc/qcom/apr.c`, `CONFIG_QCOM_APR`). It is
  CAF's later client for the same protocol and defines the same names. Its
  only user in this tree was the AVD stack, which is off.
* The **compress (offload), the listen service and the VoIP** PCM platforms
  are not built, and their links are not in the card. The compress one is
  staged but not built: CAF's compress parameter layout and the ROM's
  AudioFlinger disagree, and that is a userspace ABI decision, not a kernel
  one. The VoIP one is left out for the same reason as the compress one.
* **The tree's AVD stack** (`sound/soc/qcom/qdsp6/`). It is off. It is CAF's
  later generation and cannot coexist with the 4.19 one: `q6asm_cmd`,
  `q6asm_read`, `q6asm_run` and `apr_send_pkt` are defined by both.

The **microphone bias and headset control helper** is built. It is not the
codec, it is the headset detect and the bias regulator handling, and the
analog CDC uses it.

## The transport works out

The DSP library talks to the ADSP over the rpmsg device the ADSP announces as
`apr_audio_svc`. This tree's own devicetree already asks the remoteproc for
exactly that channel:

```
arch/arm64/boot/dts/qcom/msm8953.dtsi:1886:  qcom,smd-channels = "apr_audio_svc";
```

So the CAF 4.19 transport binds to the ADSP channel this tree already creates.
The tree's later APR is a *client* for the same channel and is not the
provider of it, which is why it could be turned off without losing the path
to the DSP.

## What had to change to build

* The DAI driver moved its `probe`, `remove`, `pcm_new` and `compress_new`
  from `snd_soc_dai_driver` into `snd_soc_dai_ops`.
* The PCM platforms became ASoC components: direct callbacks and
  `pcm_construct`, no `snd_soc_composite_driver`.
* `.copy_user` became `.copy` (iov_iter), `digital_mute` became
  `mute_stream`, `delay_blk` became `delay`, and `snd_soc_pcm_stream` grew
  an `aif_name`.
* The vendor ioctl needs a compat path: the PCM op, the component callback
  and the dispatch in `sound/core/pcm_compat.c`, and `snd_pcm_usr` in
  `sound/core/pcm_lib.c`.
* `SNDRV_HWDEP_IFACE_AUDIO_BE` and `SNDRV_HWDEP_IFACE_AUDIO_CODEC` were
  added to `include/uapi/sound/asound.h`.
* CAF exported three helpers it had declared `static`; this kernel's modpost
  refuses that, so they are global.
* The AFE and the WCD calibration hwdep both had their calibration tables
  global under the same two names; they are file local now.
* The MDF's teardown used the ARM IOMMU mapping this kernel no longer has; it
  uses the domain API.
* **This kernel's ASoC matches a link's codec by its component, not by its
  DAI.** A link's codec entry has to carry the name of the codec's component
  or its device node; an entry with only a DAI name is refused
  (`ASoC: Neither Component name/of_node are set`), and the card is then
  never registered. CAF only had to name the DAI, so every link in the
  machine driver had to be given a component: the dummy codec by its name
  (`snd-soc-dummy`), the two CDC codecs by their device node, taken from the
  tree by the names the tree gives them.
* A link whose **platform** is missing defers the whole card
  (`-EPROBE_DEFER`), so the links that named the compress, the listen
  service and the VoIP platforms were taken out: those platforms are not
  built. The tree carries the digital CDC, the first codec of the primary
  MI2S links, which it did not have before.

## Not proven

Nothing here says the phone makes a sound. That needs a boot:

* `cat /proc/asound/cards` — the card must register. It was
  `--- no soundcards ---` before.
* `dmesg | grep -i asoc` — the machine driver's probe, the DAI links, the CDC
  and the DSP bring-up.
* `logcat | grep listAudioPorts` — the ROM's vendor HAL calls it in a retry
  loop; the retries are a large part of the CPU load measured in
  [2026-10-20-high-cpu-retry-storms.md](2026-10-20-high-cpu-retry-storms.md).
* The PCM names, the mixer control names and the volume ioctls the ROM's
  vendor HAL uses are CAF 4.19's. They are preserved by construction, not by
  measurement.

The **component names** in the device tree have to match the ones the machine
driver looks up, or the DAI links do not resolve: `msm-pcm-dsp.0`,
`msm-pcm-dsp.1`, `msm-pcm-dsp.2`, `msm-pcm-routing`, `msm-pcm-afe`,
`msm-pcm-hostless`, `msm-pcm-voice`, `msm-pcm-loopback`,
`msm-pcm-dsp-noirq`, and the FE DAI `msm-dai-fe`. They do: the device tree
names the nodes after the drivers, and the kernel carries the same strings.
