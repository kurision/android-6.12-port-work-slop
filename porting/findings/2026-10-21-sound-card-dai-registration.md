# Why there is no sound card: q6 DAI registration fails with -ENOMEM

Found from the two logdumps already pulled. No build, flash, edit or boot was
performed for this finding.

## Symptom

`/proc/asound/cards` is `--- no soundcards ---` on every image, including the
one that loads the machine module. When the machine module *does* run, the card
does not fail outright, it defers forever:

```
[   20.245584][  T212] msm8952-asoc-wcd c051000.sound: msm8952_asoc_machine_probe:of read string qcom,msm-ext-pa i 0 ret 0
[   20.245707][  T212] msm8952-asoc-wcd c051000.sound: Headset is using internal micbias
[   20.245785][  T212] msm8952-asoc-wcd c051000.sound: snd_soc_register_card failed (-517)
```

`-517` is `-EPROBE_DEFER`: a card component is not registered yet. It retries
once from the deferred-probe worker (36.779 s, same `-517`) and never binds.

Source: `porting/artifacts/snapshot60/run333g-reset-ynaswhda/logdump.bin`,
logdump snapshot slots at 63406092 and 64458764 (the fallback boot, which loads
`machine_dlkm.ko` early).

The missing component is the q6 DAI set:

```
[   20.218901][  T212] msm-dai-q6-dev soc@0:qcom,msm-dai-q6-sb-0-rx: ASoC: error - multiple DAI soc@0:qcom,msm-dai-q6-sb-0-rx registered with no name
[   20.218912][  T212] msm-dai-q6-dev soc@0:qcom,msm-dai-q6-sb-0-rx: ASoC: Failed to register DAIs: -12
```

27 DAIs fail this way on the **F boot too**, i.e. with no machine module
loaded, so the fault is independent of the module-loading problem:

`porting/artifacts/snapshot60/run333g-live-current/logdump-prefix.log`
(`grep -c "multiple DAI"` = 27).

Affected nodes: `afe-pcm-rx/tx`, `sb-0..6 rx/tx`, `bt-sco-rx/tx` (+ `-2`),
`int-fm-rx/tx`, `incall-record-rx/tx`, `incall-music-rx/tx`, `proxy-rx/tx`.

## Cause: the 4.19→6.12 DAI-naming default was inverted

`msm_dai_q6_component` (the component behind every `msm-dai-q6-dev` device)
declares no DAI names and no naming flag
(`sound/soc/msm/msm-dai-q6-v2.c:7117`):

```c
static const struct snd_soc_component_driver msm_dai_q6_component = {
	.name		= "msm-dai-q6-dev",
};
```

Its DAIs have no `.name` either (`msm_dai_q6_bt_sco_rx_dai`,
`msm_dai_q6_fm_rx_dai`, ...). Registration in 6.12
(`sound/soc/soc-core.c:2724`):

```c
dai = snd_soc_register_dai(component, dai_drv + i, count == 1 &&
			   component->driver->legacy_dai_naming);
```

so with the flag unset, a one-DAI component takes `fmt_multiple_name()`, which
refuses a nameless DAI (`soc-core.c:2620-2623`):

```c
if (dai_drv->name == NULL) {
	dev_err(dev, "ASoC: error - multiple DAI %s registered with no name\n", ...);
	return NULL;
}
```

and `snd_soc_register_dais()` turns the NULL into `-ENOMEM`.

Linux 4.19 has the opposite default
(`https://raw.githubusercontent.com/torvalds/linux/v4.19/sound/soc/soc-core.c`,
`snd_soc_register_dais()`):

```c
dai = soc_add_dai(component, dai_drv + i,
		  count == 1 && !component->driver->non_legacy_dai_naming);
```

i.e. 4.19's field is an opt-*out* (`non_legacy_dai_naming`), default 0, so CAF's
component structs got legacy DAI naming for free. 6.12 replaced it with an
opt-*in* (`legacy_dai_naming`), default 0. The component structs were carried
over verbatim, so every unnamed single DAI now fails.

`non_legacy_dai_naming` appears nowhere in this tree, and nothing in
`sound/soc/msm/` sets `legacy_dai_naming` — the conversion was simply missed.
This is the same class of bug the forward-porting reference warns about:
a donor default that a shim silently dropped.

## Fix (applied)

`.legacy_dai_naming = 1` added to `msm_dai_q6_component`
(`sound/soc/msm/msm-dai-q6-v2.c:7117`), with a comment recording why.
`git diff --check` and `scripts/checkpatch.pl --strict` are clean.

Built as **run335** with `porting/tools/build-kernel.sh run335` (base
`../ack-kgsl-artifacts/boot-run258.img`), the canonical config and module
list, no `@late` and no extra CIL. The build log records
`msm-dai-q6-v2.o` recompiled at line 4086; `platform_dlkm.ko` and the
kernel both report vermagic `6.12.93-4k-gbdb8c4cc8265-dirty`, so the
staged module belongs to the shipped Image. `/init` and the load order are
the standard ones (`machine_dlkm.ko` last in the early list).

Static checks: the script's `W=1` passes for its own objects; a direct
`W=1` build of `msm-dai-q6-v2.o` fails only on the file's four pre-existing
`-Wmissing-prototypes` errors, and with just that warning downgraded it
emits no others. `make C=1` was not run: `sparse` is not installed on the
build host. Boot verification is pending.

The six sibling components in the same file were checked and deliberately
left alone:

| component | DAIs have `.name` | DAIs have `.id` | flag effect |
| --- | --- | --- | --- |
| `msm_dai_q6_component` | no (16 arrays) | some 0 | **required** |
| auxpcm, spdif rx/tx, mi2s, meta-mi2s, tdm, cdc-dma | yes | always non-zero | none |

`fmt_single_name()` is chosen only when `dai_drv->id == 0 || dai_drv->name ==
NULL` (`soc-core.c:2669`), so a named DAI with a non-zero id takes
`fmt_multiple_name()` and keeps its name either way. Adding the flag there
would be dead code, so the diff stays to one field.

Pre-existing, unrelated findings from `check_kernel_api_patterns.py` in the
same file (not touched): `%pK` in printk at :4462, open-coded allocation
products at :4562 and :4577.

Not changed by this: the machine module still has to be present. Once the DAIs
register, `snd_soc_register_card()` should stop returning `-EPROBE_DEFER` and
the card should appear without any SELinux policy change, because the module
can then be loaded early like the other seven (pre-policy, no `sys_module`
check), and the whole late-load/dyntransition path is unnecessary.

## How to verify without guessing

1. Static: each affected component registers DAIs with `count == 1` and
   `.name == NULL`; confirm by reading the registration sites, not just the
   structs.
2. One boot with `machine_dlkm.ko` in the normal early list (no `@late`, no
   added CIL). Expected in the log: no `multiple DAI` lines, no
   `Failed to register DAIs`, and `snd_soc_register_card` returning 0 followed
   by the card in `/proc/asound/cards`.
3. If the card binds but audio still fails, the next layer is q6/APR (the
   `-ENOMEM` DAIs also explain why the DSP links were never established).

## What this does not explain

The run333g reset at ~5 min. The machine probe is benign here (`-517`, no
crash) and the q6 DAI failure happens with or without the module, so the
reset is still unattributed. It stops mattering if the late loader is dropped:
the fix above needs no dyntransition, no `sys_module` grant and no staged
files, so the next image differs from the known-booting one only in the audio
driver flag.
