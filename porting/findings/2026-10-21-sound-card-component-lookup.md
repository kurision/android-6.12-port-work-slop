# Why the sound card still deferred after the DAI fix: component name lookup

Follows `2026-10-21-sound-card-dai-registration.md`. That fix made the q6 DAIs
register, but run335 still had no card. This records the next layer, the fix,
and what is still unverified.

## Symptom

run335 (the DAI-registration fix) boots, loads all eight audio modules, and
still reports:

```
porting/artifacts/snapshot60/run335-live/asound-cards.txt
--- no soundcards ---
```

`msm8952_asoc_machine_probe` still returns `-517` from
`snd_soc_register_card()`. The q6 DAI registration errors are gone.

## Cause: names in the links vs names derived from the device node

`soc_dai_link_sanity_check()` (`sound/soc/soc-core.c:939`) checks the codec,
then the platform, then the CPU component of every link. Each check calls
`soc_find_component()`, which compares `dlc->name` with the component's name.
A component with no `dlc->of_node` and no matching name makes the check return
`-EPROBE_DEFER` at `component_not_found` (`soc-core.c:1026`), before any DAI is
looked up.

The machine driver names its platforms and q6 CPU DAIs the way the vendor
driver did (`msm8952.c`, `COMP_PLATFORM("msm-pcm-dsp.0")`,
`.dai_name = "msm-dai-q6-dev.241"`, ...). In 6.12 the component name is derived
from the device name, and an OF platform device under `soc@0` is named
`soc@0:<node-name>`. The live component list shows it:

```
porting/artifacts/snapshot60/run335-live/asoc-components.txt
7:soc@0:msm-pcm-dsp.0
...
```

The first link, `MSM8952 Media1`, has the dummy codec (component
`snd-soc-dummy`, present) and platform `msm-pcm-dsp.0` (component
`soc@0:msm-pcm-dsp.0`). The codec check passes, the platform check compares
`"msm-pcm-dsp.0"` with `"soc@0:msm-pcm-dsp.0"` and fails, so the card defers on
that link and never reaches the CPU DAI lookup. The same mismatch applies to
every q6 CPU DAI name (`msm-dai-q6-dev.240` vs
`soc@0:qcom,msm-dai-q6-afe-pcm-rx`), so fixing only the platform would just move
the deferral to the next check.

This is deterministic from the sanity-check code plus the live component list;
the earlier kprobe session (kretprobe on `snd_soc_add_pcm_runtimes` returned
`-517`, `snd_soc_find_dai` was never called) agrees, but that trace was not
saved under `porting/artifacts/`, so the saved evidence here is the component
list and the source path.

## Second, independent reason the card could not bind: AUXPCM never probed

The machine driver always includes the two primary AUXPCM backend links
(`msm-dai-q6-auxpcm.1`). The port's AUXPCM node had only
`qcom,msm-dai-q6-dev-id = <1>`, but `msm_auxpcm_dev_probe()` requires
`qcom,msm-cpudai-auxpcm-mode/sync/frame/quant/num-slots/slot-mapping/data`,
`qcom,msm-cpudai-auxpcm-pcm-clk-rate` and `qcom,msm-auxpcm-interface`
(`sound/soc/msm/msm-dai-q6-v2.c:4469-4620`). The probe failed, the platform
device `soc@0:qcom,msm-auxpcm-dev` exists but is not bound, and there is no
AUXPCM component in `asoc-components.txt`. Even with the name lookup fixed, the
card would have deferred on those two links.

## Fix applied

1. `sound/soc/msm/msm8952.c:2970` — before the existing codec pass, resolve
   every platform `name` through `asoc-platform-names` / `asoc-platform` and
   every CPU `dai_name` through `asoc-cpu-names` / `asoc-cpu`, set `of_node`
   and clear the name. Names not in the lists (the front-end DAIs such as
   `MultiMedia1`) are left alone and still resolve by DAI name, as before.
2. `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot-audio.dtsi:130` — add the
   two lists: 9 platforms and 21 q6 CPU DAIs. The lists are parallel and
   aligned; every name used by the links the card actually includes
   (`msm8952_dai`, `msm_int_be_dai`, the quin link) is present.
3. `...msm8953-xiaomi-tissot-audio.dtsi:466` — complete the AUXPCM node with the
   donor's primary-AUXPCM properties, so the component registers.

The `msm-dai-q6-mi2s.6` key maps to the senary node (`qcom,msm-dai-q6-mi2s-senary`,
dev-id 5), matching the donor's `msm-audio-lpass.dtsi` and the port's
`msm_dai_q6_mi2s_dai[5]` = `Senary MI2S`.

## Verification done

- `git diff --check` clean; `scripts/checkpatch.pl --strict` clean (0 errors,
  0 warnings, 0 checks).
- `check_kernel_api_patterns.py sound/soc/msm/msm8952.c` reports nothing.
- DTS preprocessed with `cpp` and compiled with the in-tree `scripts/dtc/dtc`
  to a DTB. No new warnings. Decompiled DTB confirms 9/9 platform and 21/21
  CPU phandles, each resolving to the intended node, and the completed AUXPCM
  node.
- Not run: `make W=1`, `make C=1` (sparse is not installed), `CHECK_DTBS`,
  build, boot. No build was started for this finding.

## What the next boot has to show

1. No `snd_soc_register_card failed (-517)` for `c051000.sound`.
2. `snd_soc_register_card` returns 0, `/proc/asound/cards` lists the card.
3. `soc@0:qcom,msm-auxpcm-dev` is bound and an AUXPCM DAI appears in
   `/sys/kernel/debug/asoc/dais`.
4. If the card binds but playback fails, the next layer is q6/APR/DSP
   (`msm-pcm-routing` DAPM and the q6 AFE ports), not component lookup.
