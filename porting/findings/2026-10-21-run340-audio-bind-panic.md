# run340: PCM misclassified as compressed audio, then MBHC cleanup panic

## Evidence and provenance

Recovery logdump pull saved as `porting/artifacts/snapshot60/run340-logdump.bin`
(67108864 partition bytes; SHA256
`2fc348f2d58b378d162a2b297200bbf6ba790c54d3670c5bd4897e2a0c55b2f0`).
The initial exec-out capture included 82 trailing dd-status bytes; those are
not partition contents. The decoder validates slot header and payload CRC32.

The diagnostic text prefix is from kernel #47, but slot1's console identifies
`6.12.93-4k-g565871d5a615-dirty #49`. Lower sequence numbers than the prior
boot do not establish staleness: sequences restart. Earlier chat statements
that these slots were stale or that this was a pre-initcall panic were wrong.

Decoded file, relative to the snapshot directory:
`run340-ramoops-slot1-seq30-ns21537442179-snapshot-console.log`.

* Lines 547-575: PID 1 runs /init, which loads the audio modules.
* Line 635: `wcd_mbhc_init: mbhc function pointer is NULL`.
* Lines 1190-1191: `Compress ASoC: Invalid direction for P 1, C 1`, then
  `snd_soc_dai_compress_new on MultiMedia1: -22`.
* Lines 1596-1618: fault PC `wcd_mbhc_deinit+0x1c0/0x214`, address 0x20;
  callers include `msm_anlg_cdc_soc_remove`, `snd_soc_component_remove`,
  `soc_cleanup_card_resources` and `snd_soc_bind_card`.
* Line 1643: `Kernel panic - not syncing: Oops: Fatal exception` at 21.53 s.

The user also reports a reset with `boot-run339-venusdiag.img` (#50). No new
recovery pull establishes its stack yet; do not attribute #49's stack to #50.

## Source cross-checks (not boot-verified fixes)

`sound/soc/msm/msm-dai-fe.c:78-82` puts `snd_soc_new_compress` in shared
multimedia ops. The donor sets `compress_new` per DAI, only on selected
compressed DAIs. Upstream v6.12 `soc_init_pcm_runtime()` calls the CPU DAI's
compressed constructor first and falls back to PCM only on `-ENOTSUPP`:
https://github.com/torvalds/linux/blob/v6.12/sound/soc/soc-core.c

The #49 embedded config enables ADC MBHC but not legacy. The analog codec's
zero-initialized detection selector chooses `WCD_DETECTION_LEGACY` (0).
`wcd-mbhc-legacy.h` substitutes an empty initializer when legacy is disabled;
`mbhc_fn` remains NULL. The Makefile also omits `wcd-mbhc-legacy.o`.
The donor Kbuild includes that object with CONFIG_SND_SOC_WCD_MBHC_LEGACY,
and its sdm450 config enables it. The same disabled-config stub exists online:
https://github.com/Butterfingerss/Kernel_xiaomi_raphael/blob/14-dsp/techpack/audio/asoc/codecs/wcd-mbhc-legacy.h

The analog component probe ignores `wcd_mbhc_init()`'s return. The missing
ops branch in that function also reaches cleanup without assigning an error.
Its remove callback unconditionally calls deinit, which dereferences mbhc_fn.
Fixing only that dereference would hide the missing initialization, not fix it.

Also present: q6afe flexible-array FORTIFY warning and msm-pcm-routing regmap
read/write errors. Neither is established as the fatal exception here; both
remain follow-up review targets. The card is not yet registered or tested.

No kernel changes, builds, flashes or boot cycles were performed during the
initial analysis above.

## Approved edits (unbuilt, not boot-tested)

* Split `msm_fe_Multimedia_dai_ops` into PCM and compressed ops, preserving
  startup and DAI probe in both. Only the donor's 15 compressed DAIs use
  `snd_soc_new_compress`; all 143 FE DAI assignments were compared with the
  donor. No offload ABI or ASoC core change is included.
* Make the analog CDC select CAF MBHC, have CAF MBHC select its legacy backend,
  and link `wcd-mbhc-legacy.o` alongside the existing ADC backend. This retains
  the analog codec's donor-default legacy detection algorithm, rather than
  changing its hardware behavior to fit the ADC-only build.
* Return `-EINVAL` for absent MBHC ops and propagate MBHC init errors from the
  analog component probe. A failed component probe is not marked probed by
  `soc_probe_component()`, so its remove callback does not run deinit on the
  failed initialization. IRQ/notifier cleanup remains in the initializer;
  its error paths now also destroy the initialized headphone PA locks.

Checks:

* `python3 porting/tests/test_audio_bind_contracts.py`: two tests pass; both
  fail against HEAD's pre-fix sources (negative control).
* All 143 FE DAI compressed/PCM assignments match the local donor.
* Focused `checkpatch.pl --strict --no-signoff`: no errors, warnings or checks.
* `git diff --check`: clean.
* Kernel API pattern scanner: only the pre-existing `%pK` warning at
  `wcd-mbhc-v2.c:1905`, outside the changed lines.
* The older `test_audio_dai_components.py` fails link-count assertions
  (51 versus 67/83); the same failures were reproduced with untouched HEAD
  sources. Its test and the machine-link definitions were left unchanged.

Check output is saved under `porting/artifacts/snapshot60/` as
`run340-audio-fix-checks.txt` and `run340-audio-existing-test-failures.txt`.
No build, olddefconfig, Sparse, flash or phone boot was requested or run.
The next requested build must resolve legacy MBHC enabled and include
`wcd-mbhc-legacy.o`; runtime card registration and safe teardown remain
unverified. Do not treat the source checks as proof that sound works.
