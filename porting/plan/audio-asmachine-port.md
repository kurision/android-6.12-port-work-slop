# Audio on tissot: what the port actually needs

> **Current state: CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUILD_TISSOT.md](../../BUILD_TISSOT.md).

**Measured 2026-10-19** against the donor tree `../oc-test/techpack/audio` and
this tree. No code written yet; this is the closure and the sequence.

## Correction

An intermediate note in this session claimed this tree's ASoC was "stripped"
because `snd_soc_read`, `snd_soc_update_bits` and `snd_soc_codec_get_drvdata`
were absent. That was wrong and was based on a bad search. `sound/soc/codecs/
wm8994.c` here is 4,710 lines, identical to upstream v6.12, and upstream v6.12
does not use `snd_soc_read()` in that file either. This tree's ASoC is vanilla
6.12; those symbols simply are not what the tree's header set exposes.

## What the donor builds for this SoC

The machine driver for msm8953 in CAF is named after the platform's internal
codename, SDM450, not after the chip:

| object | lines | gated by |
|---|---|---|
| `asoc/msm8952.c` | 3,666 | `CONFIG_SND_SOC_SDM450` |
| `asoc/msm8952-dai-links.c` | 1,679 | `CONFIG_SND_SOC_EXT_CODEC_SDM450` |
| `asoc/msm8952-slimbus.c` | — | same |

The codec family is the WCD series, `asoc/codecs/wcd*`, **43,176 lines** across
`wcd9xxx` core/irq/resmgr/slimslave/utils/mbhc/clsh plus the per-chip
`wcd9335`, `wcd934x`, `wcd937x` and `wcd938x` directories. On top of that the
AFE and DSP PCM paths (`msm-pcm-afe-v2.c`, `msm-dai-q6-v2.c`, `msm-dai-fe.c`,
`msm-audio-effects-q6-v2.c`, `msm-compress-q6-v2.c`).

**Total: roughly 50,000 lines of vendor audio code**, before any 6.12 API work.
The single largest item on the whole port by an order of magnitude.

## Measured attempt

The port was started in the tree and driven until it stopped being a guess.
What that established, all measured:

- The WCD variant is **WCD9335**, from the donor's own platform config
  `techpack/audio/config/sdm450auto.conf`: `CONFIG_SND_SOC_WCD9335=m`,
  `CONFIG_WCD9XXX_CODEC_CORE`, `CONFIG_SND_SOC_WCD_MBHC`,
  `CONFIG_SND_SOC_WCD_MBHC_LEGACY`, `CONFIG_WCD_DSP_GLINK`. Not 937x or 938x.
- Only **one** genuinely missing ASoC symbol in the whole closure:
  `snd_soc_component_read32`. The private-helper step this document originally
  proposed is unnecessary: `snd_soc_dapm_add_routes_mi2s` and its siblings are
  used by CAF's *other* machine drivers, not by the tissot one. The earlier
  "25 symbols missing" figure was measured across every CAF machine driver.
- The tissot config also selects the **SDM660 CDC**
  (`CONFIG_SND_SOC_SDM660_CDC`, `CONFIG_SND_SOC_ANALOG_CDC`,
  `CONFIG_SND_SOC_DIGITAL_CDC_LEGACY`), and `msm8952.h` includes the SDM660 CDC
  headers unconditionally. So the closure is not the WCD plus a machine: it is
  the machine, the SDM660 analog and digital CDC, the WCD9335 and its core, the
  MBHC helpers, `msm-pcm-routing-v2`, `msm-pcm-afe-v2` and `msm-dai-fe`.
- The Kconfig wiring is straightforward and was validated. One recursion has to
  be resolved: `WCD9335` cannot `select SOUNDWIRE` while `SOUNDWIRE` is implied
  by `SOUNDWIRE_QCOM`.
- The CAF private headers stage cleanly. `techpack/audio/include` splits into
  `asoc/`, `dsp/`, `soc/`, `ipc/`, `linux/` and `uapi/sound/`, and a few more
  live outside it, in the CAF `include/soc/qcom/`.

## The 6.12 adaptations this port actually needed

All measured while compiling the WCD9335 closure with `W=1`, not inferred:

| CAF 4.19 | this tree | note |
|---|---|---|
| `snd_soc_component_read32()` | `snd_soc_component_read()` | 6.12 already returns the value directly, CAF's name is just old. 91 call sites in `wcd9335.c` alone |
| `struct soc_multi_mixer_control`, `SOC_SINGLE_MULTI_EXT`, `snd_soc_info_multi_ext()` | **absent upstream** | Qualcomm addition; added to this tree's `include/sound/soc.h` and `sound/soc/soc-ops.c` |
| `SND_SOC_DAPM_MICBIAS_E()` | **absent upstream** | likewise; added to `include/sound/soc-dapm.h` |
| `strlcpy()` | `strscpy()` | removed in v6.8 |
| `snd_info_create_subdir()` | `snd_info_card_create()` plus `snd_info_create_card_entry()` | the ALSA info API was reworked |
| `snd_soc_card_change_online_state()` | **absent upstream** | dropped with a comment; it only matters for subsystem restart, which is not wired on this port |
| `regmap_config.use_single_rw` | `use_single_read` plus `use_single_write` | split upstream |
| `slim_device_id` carrying a string name | manufacturer/product form | **structural**, see below |
| platform `.remove` returning `int` | `void` | since v6.11 |
| i2c `.probe(client)`, `.remove` | `.probe(client, id)`, `void .remove` | |
| function definitions in a header | `static inline` | `-Wmissing-prototypes` is fatal here, and several CAF headers define stubs that way |
| `CONFIG_WCD9XXX_CODEC_CORE` | the symbol name must be kept | the staged CAF headers are guarded by it, so renaming the symbol silently compiles its declarations out |

### The one structural decision

CAF binds the codec through slimbus, using a `slim_device_id` whose `name` is
compared against the DT compatible. This tree's `slim_device_id` is the
manufacturer/product struct from `include/linux/mod_devicetable.h`, so CAF's
table cannot exist here. Rather than invent manufacturer and product codes, the
codec is bound through its **platform** driver, which CAF also implements
(`tasha_codec_driver` with `tasha_probe`), and CAF's slim probe path is left out
with a comment saying why. That removed 338 lines of glue that would otherwise
have referenced a struct shape this tree does not have.

This is where the port stops being mechanical, and it is the shape the rest of
the closure will take: where CAF's API has no 6.12 equivalent, decide and
document rather than fabricate.


## What this tree has today

- `CONFIG_SND_SOC=y`, vanilla ASoC, 416 codecs, `include/sound/soc.h` matching
  upstream v6.12.
- `CONFIG_SND_SOC_MAX98927=y` and the `max98927` codec node in the board DTS —
  the speaker amplifier is wired, but nothing drives it.
- No `sound/soc/msm/` machine driver, no WCD codec, `CONFIG_SND_SOC_MSM` absent
  from `configs/tissot-ack-resolved.config`, `# CONFIG_SND_SOC_QCOM is not set`,
  and no WCD symbols.

The CAUSE of `AudioSystem: listAudioPorts failed` is therefore not a tuning
problem: there is no sound card to enumerate. The vendor audio HAL opens
`/dev/snd`, finds only a timer, and gives up.

## Sequence

1. **`snd_soc_component_read32`.** The single ASoC symbol this closure needs
   that upstream's `include/sound` does not expose. Small, and everything else
   waits on it.
2. **WCD9335 and its core.** `wcd9335{,-regmap,-tables}.c`, the
   `wcd9xxx-{core,core-init,irq,resmgr-v2,slimslave,utils,rst,soc-init,common-v2}.c`
   set, and the mbhc/clsh helpers.
3. **SDM660 CDC.** `msm-analog-cdc` and `msm-digital-cdc`, which
   `msm8952.h` includes unconditionally and the platform config selects.
4. **Machine driver.** `msm8952.c`, its dai-links and slimbus, plus
   `msm-pcm-routing-v2`, `msm-pcm-afe-v2` and `msm-dai-fe`.
5. **DT wiring.** `msm-asi2`, `qcom,msm-audio-apr`, slimbus, mi2s/pdm/tdm for the
   codec, and the AFE/QDSP6 nodes the PCM layer expects. Register order matters
   and the vendor HAL expects CAF's node names.
6. **Policy.** SELinux labels for the new device nodes, as done earlier for
   battery and backlight.

## Risks, in order of how likely they are to bite

- **The ASoC helper is not optional.** Without `snd_soc_component_read32`
  nothing in steps 2-4 compiles.
- **The closure is bigger than the WCD.** The machine header drags in the SDM660
  CDC whether or not a first reading suggests it is needed; that family is part
  of this platform's own configuration.
- **The DSP leg is separate.** Row 8 of the component audit is only fixed in
  source. Even a perfect card will not produce sound through the DSP-backed PCM
  path until the FastRPC CAF layer is running on hardware.
- **No iteration without the phone.** Every one of these steps is judged by
  probe logs and by whether the vendor HAL finds a card, not by compiling. There
  is no substitute for a boot cycle between steps.

## Recommendation

Do not start this as a blind forward-port. The first slice that is worth writing
is step 1 plus the WCD core, and even that cannot be judged without a device. A
boot cycle that also tests the already-written nav-key and FastRPC changes would
give this port the evidence it currently lacks entirely.

Nothing here has been built, booted or flashed.
## Port status, 2026-10-19

Building with W=1 on fix/components: efea7da77 (WCD9335 codec, wcd9xxx
core, mbhc, class-H, DSP glink manager), 63dda8dbd (SDM660 CDC and its
regs and irq), 874b7a623 and a28ce6944 (their headers). Twenty-two
objects.

Not yet building: msm8952.c, the machine driver. Its DAI-link table
still names cpu_dai_name, platform_name and codec_dai_name, 143 sites,
which this tree replaces with the cpus[] and codecs[] component arrays.
That conversion decides which DAI each route reaches and there is no
test here that would catch a mistake until the phone makes a sound.

## What audio still needs, measured 2026-10-19

The drivers are in; what is left is not a transcription. Three things, in
dependency order:

1. **The AFE driver.** CAF's `qcom,audio-ref-clk` node, which supplies the
   codec's external clock, is a clock provider whose prepare() calls
   `afe_set_lpass_clk_cfg()` in CAF's `techpack/audio/dsp/q6afe.c` — **11,391
   lines**, plus its 593-line header and the ADSP loader, SSR and glink glue
   around it. This tree has no AFE, so the clock provider has nothing to
   program. This is larger than everything ported so far in this series
   combined.
2. **The clock provider**, `audio-ext-clk.c`, 341 lines, once the AFE exists.
3. **The pinmux and DT.** This tree's `msm8953.dtsi` has no audio pin groups at
   all, so CAF's tissot `pinctrl.dtsi` (263 lines, of which the pri TLMM lines
   are gpio88/91/93) plus the SoC-level audio pin groups have to come across,
   and with them `msm8953-audio.dtsi` (516 lines) and tissot `audio.dtsi`
   (148 lines).

The driver compatibles match the donor's nodes exactly, so nothing here is a
guessing problem; it is a volume problem. A DT written without the clock
provider would compile, probe, and produce silence.

## The audio clock provider is a rewrite, not a port

CAF's `audio-ext-clk.c` embeds `struct clk` by value in each of its clock
objects and registers them with `clk_init()`. In this kernel both
`struct clk` and `struct clk_core` are private to `drivers/clk/clk.c`;
out-of-tree providers only get `struct clk_hw` plus `struct clk_ops`,
and `clk_register(dev, hw)` is the exported entry point. So the provider
has to be written against `clk_hw` ops, not translated.

What it does, from the donor: a GPIO-controlled clock, a pinctrl-state
clock, and an LPASS clock whose prepare/unprepare call
`afe_set_lpass_clk_cfg()`, which is why the AFE had to land first. The DT
node is `qcom,audio-ref-clk` with `qcom,codec-ext-clk-src`,
`qcom,codec-lpass-ext-clk-freq` and `qcom,codec-lpass-clk-id`; CAF picks
which of its clocks to build from `qcom,audio-ref-clk-gpio` and
`qcom,node_has_rpm_clock`.

Tissot uses the LPASS variant (`AUDIO_LPASS_MCLK_2`, 9.6 MHz, id 0x300)
with no GPIO and no RPM parent, so only the AFE-backed clock and its ops
are actually needed.

## The audio clock provider is not needed on tissot

Chasing the last provider turned out to be the wrong target. CAF's
`qcom,audio-ref-clk` node exists to feed the WSA881x headphone amplifier
codec -- it is the `clocks` entry of `wsa881x-i2c-codec@f`. Tissot has
no WSA881x: its audio dtsi carries a MAX98927 speaker amplifier and
explicitly deletes `asoc-wsa-codec-names`, `asoc-wsa-codec-prefixes` and
`msm-vdd-wsa-switch-supply` from the sound node.

So the provider has no consumer here and the clk_hw rewrite is not on
tissot's path. The codec MCLK comes from `qcom,msm-mclk-freq` instead,
which the machine driver and the CDC read as a property.

Audio therefore needs the pinmux and the DT, and no longer needs a
clock provider. `audio-ext-clk-up.h` stays staged because
`wcd9xxx-soc-init.c` includes it.

## What the DT still needs behind it

Writing the sound card node first would reference drivers that do not exist
here yet. CAF's `asoc-platform` list pulls in ten PCM platforms and
`asoc-cpu` pulls in roughly thirty DAI endpoints:

- PCM: `msm-pcm-dsp.0/.1/.2` (msm-pcm-q6-v2), `msm-voip-dsp`,
  `msm-pcm-voice`, `msm-pcm-loopback`, `msm-compress-dsp`,
  `msm-pcm-hostless`, `msm-pcm-afe`, `msm-lsm-client`,
  `msm-pcm-routing`, `msm-pcm-dsp-noirq`
- DAI: q6 auxpcm, six mi2s endpoints, ten slimbus endpoints, bt sco,
  int fm, afe pcm and proxy, the incall endpoints and the proxies
- codecs: `msm-stub-codec.1`, `msm-dig-codec` and the WCD9335
  analog codec, plus the pinctrl groups for the mi2s lines, the cross
  connection detect, the PDM lines and the EU/US switch

Of those, `msm-dai-q6-v2.c`, `msm-dai-fe.c` and the routing header are
already staged; the PCM platforms are staged but not built, and the
loopback, compress, effects, LSM and stub codec are not ported at all.

So the remaining order is: port the PCM platforms (starting with
`msm-pcm-dsp-noirq`, which every playback route goes through), then the
stub codec, then write the DT. The DT is the last step, not the first.

## The PCM platforms need CAF ALSA extensions too

msm-pcm-q6-noirq.c, the DSP PCM playback goes through, fails on
snd_pcm_volume. That type is not upstream; CAF adds
snd_pcm_add_volume_ctls() and struct snd_pcm_volume to include/sound/pcm.h
and plumbs them through sound/core/pcm.c.

Third CAF API this kernel lacks, after the clk_hw split for the clock
provider and the component arrays for the sound card. The audio port is
therefore CAF audio down to ALSA, not a driver list.
