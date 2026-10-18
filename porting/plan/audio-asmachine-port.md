# Audio on tissot: what the port actually needs

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

The staged files were then removed rather than committed: they do not compile
yet, and leaving tens of thousands of lines of non-building vendor code in the
tree would make the next boot's behaviour depend on unfinished work.

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