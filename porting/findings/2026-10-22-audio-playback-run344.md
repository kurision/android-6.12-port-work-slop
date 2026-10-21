# run344: the q6 audio path plays, and the two open failures of run342 are gone

**Evidence:** `porting/artifacts/snapshot60/run344-audio/` (`dmesg-stream.txt`,
`logcat-stream.txt`), the run344 image (`porting/artifacts/snapshot60/boot-run344.img`,
kernel `6.12.93-4k-geebbbf38e47b-dirty`, flashed to `boot_b`), the donor
comparison in `porting/findings/2026-10-22-donor-baseline-video-audio.md`.

The image carries `d67199a80` (the `dma_buf_vunmap()` argument type) and
`b250002a2` (the `copy_{from,to}_iter()` return value), plus the two fixes
this session added:

* `ASoC: msm: pcm-q6: do not query the DSP for the path delay` - the q6
  platform's delay callback slept in atomic context.
* `ASoC: msm: q6afe: copy the in-band payload through a byte pointer` - the
  fortify check warned about a field-spanning write that cannot happen.

## What was measured

* The HAL opened the same stream as the donor:
  `start_output_stream: enter: stream(0xe50864c0)usecase(0:
  deep-buffer-playback) devices(0x2)`, `select_devices: changing use case
  deep-buffer-playback output device from(0: , acdb -1) to (2: speaker,
  acdb 1058)`, `enable_audio_route: apply mixer and update path:
  deep-buffer-playback speaker` - the same `acdb_dev_id 1058` and the same
  mixer path as the donor baseline.
* **Audio flowed:** `AudioTrack( 4760): stop(27): called with 310080 frames
  delivered`. 310080 frames at 48 kHz is 6.5 s of playback. In run342 the
  same test wrote 0 frames and logged `out_write: error -14`.
* The stream was closed normally: `out_standby: enter: stream (0xe50864c0)
  usecase(0: deep-buffer-playback)` and `disable_audio_route: reset and
  update mixer path: deep-buffer-playback speaker`.
* **The kernel log is clean.** 6666 lines of `dmesg -w` with no `WARNING:`,
  no `BUG:`, no `Call trace`, no `scheduling while atomic`, no `hung_task`,
  no soft lockup. The three failures of run342 are all absent:
  * no `MSM8x16 Media9: ASoC: no backend DAIs enabled`,
  * no `q6asm_callback: cmd = 0x10bcd returned error = 0x1`,
  * no `msm_pcm_chmap_ctl_put: substream ref_count:0 invalid`.
* The phone did not freeze or reboot during the test. The previous run
  (the run343 image) died within seconds of the first playback, with the
  atomic-sleep BUG below in the log.

## The failure the run343 boot found: a DSP round trip in atomic context

The run343 image (both fixes from the plan, no further change) froze the
phone 0.5 s into the first playback. The log
(`porting/artifacts/snapshot60/run343-audio-boot/dmesg-stream.txt`, line
4213) has:

```
BUG: scheduling while atomic: writer/4676/0x00000002
Call trace:
 schedule_timeout+0x94/0x1a8
 q6asm_get_path_delay+0xc0/0x1d4 [q6_dlkm ...]
 msm_pcm_delay_blk+0x24/0xa0 [platform_dlkm ...]
 snd_soc_pcm_component_delay+0xb8/0x130
 soc_pcm_pointer+0x58/0x9c
 snd_pcm_update_hw_ptr0+0x68/0x3e0
 snd_pcm_update_hw_ptr+0x14/0x20
 snd_pcm_delay+0xa4/0x180
 snd_pcm_ioctl_sync_ptr_compat+0x20c/0x7a4
```

`q6asm_get_path_delay()` is a DSP round trip: it takes a mutex and waits
for the answer. It was reached from the component's `.delay` callback,
which upstream 6.12 calls from `soc_pcm_pointer()`, i.e. from
`snd_pcm_update_hw_ptr0()` under `pcm_stream_lock_irq`
(`sound/core/pcm_native.c:3066`, `sound/soc/soc-pcm.c:1314`). That is
atomic context: sleeping there is the BUG above.

The donor does not have this problem because CAF 4.19 used a different
hook for it. The donor's `struct snd_soc_dai_ops` has
`delay_blk` (`../oc-test/include/sound/soc.h:818`), described in the donor
as "For platform-caused delay reporting, where the thread blocks waiting
for the delay amount to be determined", and the donor's ASoC core *skips*
the delay computation for any component that provides it
(`../oc-test/sound/soc/soc-pcm.c:1278`):

```c
		offset = component->driver->ops->pointer(substream);
		if (component->driver->delay_blk)
			return offset;
```

The donor's ALSA core never called `ops->delay_blk` either (no caller for
it anywhere in the donor's `sound/`), so on the donor the query never ran
and the runtime delay for the q6 front end stayed 0. Removing the
callback from the port restores exactly that behaviour.

## The second finding: a fortify warning about a copy that cannot overflow

The same run343 log (line 4167) has:

```
memcpy: detected field-spanning write (size 20) of single field
"&set_param->param_data" at sound/soc/msm/q6afe.c:1663 (size 0)
WARNING: CPU: 5 PID: 4676 at sound/soc/msm/q6afe.c:1663 q6afe_set_params+0x350/0x3e4
```

`param_data` is `u8 param_data[0]`, a zero-length array at the end of
`struct afe_port_cmd_set_param_v2`
(`sound/soc/msm/caf-include/dsp/apr_audio-v2.h:2047`). The packet is
allocated with room for the payload
(`size = sizeof(struct afe_port_cmd_set_param_v2) + packed_data_size`,
`q6afe.c:1634`), so the copy is inside the allocation. The check is
misled by a compiler bug: gcc and clang report the size of an array at
the end of an object as zero (gcc bug 101836, quoted in
`include/linux/fortify-string.h:662`), so the check sees a zero-length
destination field and warns about a field-spanning write. Six sites in
`q6afe.c` copy the payload the same way; all six now go through a byte
pointer.

The warning tainted the kernel (`Tainted: G W`) and it fired on every
`AFE_PORT_CMD_SET_PARAM_V2` with an in-band payload, i.e. on every
playback stream start.

## Still open

* `MSM8x16 Media9: ASoC: no backend DAIs enabled` did not appear in run344
  either, but it also did not appear in the run343 boot before the phone
  died: the low-latency path was never reached. The Media9 front end is
  only opened by some of the ROM's usecases, so this failure is still
  open, not fixed.
* The low-latency `pcm_prepare returned -1` was not reached either.
* Video decode is still the software `c2.android.avc.decoder`
  (`MediaCodec: [c2.android.avc.decoder] setting surface generation`),
  which is the Part B subject.
* `Adreno-GSL: ioctl_ion_cacheoperation: ioctl fd 171 code 0xc0104906
  failed: errno 25 Unknown ioctl code` - the GPU's ION cache ioctl is
  missing in the port's ION. Not an audio problem; recorded here because
  it is in the same log.
