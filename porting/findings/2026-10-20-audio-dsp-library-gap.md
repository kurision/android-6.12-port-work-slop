# The audio stack needs a CAF generation the tree does not have

**Date:** 2026-10-20 · **Tree:** `ack-kgsl` (6.12.93) · **Donor:** `../oc-test`
(CAF 4.19)

## What the build does now

With the build gate fixed, the sound tree compiles and the device tree
builds. The build reaches the **link**, and the link fails with the
symbols the CAF 4.19 audio stack needs from CAF 4.19's DSP library.

## The gap, measured

The port's audio is CAF 4.19: the machine driver, the PCM platforms and
the DAIs are the donor's. They call the DSP through CAF 4.19's
libraries:

| needed by | CAF 4.19 symbols |
| --- | --- |
| `msm-pcm-routing-v2.o` | 47 (`q6asm_*`, `q6core_*`, `adm_*`, `cal_utils_*`, `rtac_*`, `msm_audio_ion_*`, `apr_*`) |
| `msm-pcm-q6-v2.o` | 37 |
| `q6afe.o` | 30 |
| `msm-pcm-voice-v2.o` | 24 |
| `msm-pcm-q6-noirq.o` | 13 |
| `msm-pcm-loopback-v2.o` | 11 |

The donor has that library in `techpack/audio/dsp/` — **60,073 lines**
across `q6asm.c` (11,448), `q6voice.c` (10,222), `q6afe.c` (11,391),
`q6adm.c` (5,525), `q6core.c` (2,195), `q6lsm.c` (2,998), `usf.c`
(2,470), `rtac.c` (2,074), `q6core.c`, `cal_utils`, `msm_audio_ion.c`
(839) and the rest — plus CAF 4.19's APR client in
`techpack/audio-legacy/ipc/apr.c`.

This tree does not have it. It has CAF's **later** AVD stack, which came
with the ACK snapshot (`sound/soc/qcom/qdsp6/`, 31 files) and a different
API:

| CAF 4.19 | this tree |
| --- | --- |
| `q6asm_open_write_v4`, `q6asm_is_cpu_buf_avail`, `q6asm_media_format_block_multi_ch_pcm_v4` | `q6asm_open_write`, `q6asm_media_format_block_multi_ch_pcm` |
| `q6core_get_svc_api_info`, `q6core_init_uevent_data` | the same names, a different signature set |
| `apr_register`, `apr_reset`, `apr_start_rx_rt`, `apr_end_rx_rt`, `apr_get_subsys_state` | `apr_send_pkt(struct apr_device *, struct pkt_router_svc *)` and `apr_driver_register` |
| a whole voice stack (`voc_*`) and ADM (`adm_*`) | absent |

So the two generations cannot coexist: `q6asm_cmd`, `q6asm_read`,
`q6asm_run`, `q6asm_map_memory_regions`, `q6asm_media_format_block_multi_ch_pcm`,
`q6asm_audio_client_alloc` and `apr_send_pkt` are defined by **both**,
so bringing the 4.19 library in means replacing the tree's.

The tree's AVD stack is currently **unused**: without a CAF audio machine
nothing binds to it. The port's own `sound/soc/msm/q6afe.o` (CAF 4.19's
AFE) is what the port's machine driver talks to.

## Two ways forward

**A. Bring CAF 4.19's DSP library with the audio stack.** Port the
donor's `techpack/audio/dsp/` (60k lines) and
`techpack/audio-legacy/ipc/apr.c` into the port's own namespace, and
turn the tree's `sound/soc/qcom/qdsp6/` stack off. One CAF generation
throughout, which is also the generation the old vendor audio HAL was
written against.

**B. Move the audio machine and the PCM layer to the tree's CAF
generation.** Fetch CAF 12/13's `techpack/audio/asoc/` (the
`msm-asoc-card` machine and the newer PCM components), port them to
this tree, and keep the tree's AVD stack. Smaller port, but the sources
are not in the ACK snapshot and not in the donor, and the device tree
has to be written for that generation.

## What the machine driver still has to lose

Independently of the library, the machine driver carries the paths for
boards this port does not target, and they are what the linker still
cannot resolve:

* the **tasha** (WCD9335 over slimbus) codec: the donor's Xiaomi
  boards delete the `sound-9335` node, and the machine only reaches the
  tasha tables when the card name contains "tasha"
  (`msm8952-dai-links.c`), which this board's `qcom,model` does not.
  The table still *references* `tasha_codec_ver()` and
  `msm8952_slimbus_2_hw_params`, so it has to go.
* the **WSA881x** headphone amplifier: the machine's probe reads
  `asoc-wsa-codec-names`, which the donor's tissot audio deletes, so
  the block is dead but still references
  `wsa881x_get_presence_count()` and `wsa881x_get_probing_count()`.
* the **shared machine helpers** (`msm_snd_hw_params`, the
  `be_hw_params_fixup` set, the mi2s/tdm/quin helpers) live in the
  donor's `msm8952-slimbus.c` and are used by the machine's own link
  tables, so they have to move to a file that stays.

The WCD9xxx stack, the WSA881x helpers, the audio reference clock
provider and CAF's slimbus extensions (`slim_user_msg`,
`slim_reservemsg_bw`, `slim_query_ch`, `slim_get_slaveport`,
`slim_define_ch`, `slim_dealloc_ch`, `slim_control_ch`,
`slim_connect_sink`, `slim_connect_src`, `slim_disconnect_ports`,
`slim_bulk_msg_write`, `slim_remove_device`) are all only needed by
that tasha path, and are already out of the build.
