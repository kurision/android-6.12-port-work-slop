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

## Live card enumeration after edits

At the user's next online check, adb returned:

```
Linux localhost 6.12.93-4k-g8e7f57886c76-dirty #51 SMP PREEMPT Wed Oct 21 22:55:57 +0545 2026 aarch64 Toybox
62.11 347.08
 0 [msm8953sndcardm]: msm8953-snd-car - msm8953-snd-card-mtp
                      msm8953-snd-card-mtp
```

`/proc/asound/pcm` listed devices 00-00 through 00-24, including duplex
MultiMedia1/2, VoiceMMode1/2 and `Senary_mi2s Capture multicodec-18`.
`getprop sys.boot_completed` returned empty. This is a transcription of the
first command's output, not a saved raw capture. The running banner uses the
older HEAD plus dirty edits, not the committed fix hash; exact image/module
provenance has not been verified.

USB disappeared before the follow-up evidence commands. Files in
`porting/artifacts/snapshot60/audio-online-20261021-230119/` contain only
`adb: no devices/emulators found`, not kernel logs. Card enumeration was
observed once; sustained boot, SELinux state, absence of new kernel errors
and playback/capture operation remain unverified. USB loss alone does not
establish a reset.

### Next live check: boot completed

Evidence: `porting/artifacts/snapshot60/audio-reboot-20261021-230250/`.
`status.txt` again lists card 0, enforcing SELinux and kernel #51 at 77 s.
The later `boot-state.txt` records uptime 112.95 s, `sys.boot_completed=1`,
system_server and both audio services running. Both boot-reason properties
report `reboot,checkpoint_commit_failed`; that is a reported reason, not a
verified underlying cause. AOSP associates checkpoint commit with userdata
checkpoint handling before BootComplete:
https://source.android.com/docs/core/ota/user-data-checkpoint

Live dmesg (131295 bytes), logcat (474503 bytes) and an exact 64 MiB logdump
were saved. Logdump SHA256:
`c6683f264c3a3a5240f65837673dffd54e123407655f6ba509d54b6c4162decd`.
CRC-verified snapshot slots seq145/146 sample uptime ~100 s and recover no
panic/oops dmesg records. Absence of a recovered record does not prove the
previous boot did not panic. The diagnostic prefix retains a mixed/stale
tail (including uptime 181 s beyond this capture's uptime); its old vold
shutdown lines cannot alone identify the preceding reset. No storage or
checkpoint state was changed. Playback/capture operation remains untested.

### Freeze and subsequent boot

The user reported a freeze and reboot. The freeze-time shell timed out, then
exec-out returned `error: closed`; evidence attempts are in
`audio-freeze-20261021-230500/` under the snapshot directory.

On the next connection, `audio-postfreeze-20261021-230617/status.txt` records
kernel #51, uptime 58.32 s, new boot ID
`b186c436-3be0-4d62-8c0a-546c2930b9d3`, enforcing SELinux, card 0 registered,
and an empty boot-completed property. Dmesg, logcat and the exact 64 MiB
logdump were captured. CRC-verified snapshots sample this boot at ~61 s;
no valid panic/oops dump was recovered. The connection disappeared again
before a later status check; this alone does not establish another reset.

`reset-decoded.txt` contains an orderly reset by PID 1 at 76.2 s with
command `Checkpoint commit failed`. However, its entire 64 KiB ACKRESET1
region is byte-identical to the earlier 23:02 pull (SHA256
`01fe0fd6d2612a7a06117752800d7f5b582266ba59e5fc3d21fb906f786254c0`).
It is evidence for an earlier reset, NOT fresh proof of the subsequent freeze
or reboot. ACKPATH1 decoding rejects the previous marker page's identity.
The cause of the user-reported freeze remains unverified.

## App-launch freeze: dma_buf_vunmap BUG on PCM close (kernel #53)

Reproduced live with `dmesg -w` streamed to the host:
`snapshot60/app-launch-watch-20261021-234713/dmesg-stream.txt`. On an app
launch at 272.2 s, `MSM8x16 Media9: ASoC: no backend DAIs enabled`, then
`__q6asm_cmd: DSP returned error[ADSP_EFAILED] opcode 68557`, then on close
`kernel BUG at drivers/dma-buf/dma-buf.c:2359!` (`BUG_ON(!iosys_map_is_equal)`)
via `msm_pcm_close` → `q6asm_audio_client_buf_free_contiguous` →
`msm_audio_ion_free` → `dma_buf_vunmap`. USB dropped ~25 s later. The KGSL
retired counts were still advancing in `kgsl-poll.txt` and the stall watcher
never fired; the GPU is not implicated in this freeze.

Cause: `msm_audio_ion_unmap_kernel()` kept the 4.19 call
`dma_buf_vunmap(dma_buf, vaddr)`. On 6.12 the second argument is a
`struct iosys_map *`; the `void *` converted silently, so the kernel compared
`vmap_ptr` with the first bytes of the audio buffer. Both calls also used
the variants that require `dmabuf->resv` held (upstream dynamic locking
series, https://lkml.iu.edu/2210.2/01464.html), the same mistake fixed for
qseecom in 13a9c029e. Fix: store the `struct iosys_map` and use
`dma_buf_vmap_unlocked`/`dma_buf_vunmap_unlocked`.

The BUG fires with `list_mutex` held, so later audio calls block; that this
is what produces the freeze-then-reset is inference, unverified. The reset
mechanism itself was not captured. The fix is not built or boot-tested.
The Media9 routing and ADSP_EFAILED remain separate open problems: the fix
only stops the close path from crashing; it does not make playback work.
`mdss_fb.c`/`mdss_mdp_splash_logo.c` call locked vmap/vunmap and should be
reviewed for the same locking problem.
