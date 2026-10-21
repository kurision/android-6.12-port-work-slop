# 2026-10-22: CAF 4.19 -> 6.12 audio conversion sweep

## Scope and method

Audit of `sound/soc/msm/` (plus the ION/dma-buf files the audio stack pulls
in) in the ACK 6.12 port, looking for 4.19 -> 6.12 API conversions that
**compile** but **behave differently**.

* Port tree: `/home/kurision/development/kernel/ack-kgsl`
* Donor tree: `/home/kurision/development/kernel/oc-test`
  (CAF 4.19; `techpack/audio/asoc/` for the ASoC layer,
  `techpack/audio/dsp/` for the DSP/ADSP layer)
* Base state audited: **`eebbbf38e47b1d09e490030cdddb397a89aed362`**
  ("porting: plan the vidc_3x video port and the audio playback fixes").
  All `file:line` references below are against that commit.
* The tree has since advanced to `4698570a2` ("ASoC: msm: q6afe: copy the
  in-band payload through a byte pointer"), whose two new commits are
  `fdfca326d` ("ASoC: msm: pcm-q6: do not query the DSP for the path
  delay") — which is the fix for **finding 1** — and `4698570a2` itself.
  Line numbers for `sound/soc/msm/q6afe.c` shift by about +19 lines in
  `4698570a2`; every other cited file is unchanged. Findings 2 through 8
  are still present in `4698570a2`.
* Every port file was diffed against its donor counterpart. Where a file
  differs only in the DAI-link/`dai_name` spelling, that is a mechanical
  rewrite and is not reported. Only differences that change runtime
  behaviour are reported.
* The 6.12 API contract was read from the tree itself
  (`drivers/dma-buf/dma-buf.c`, `include/linux/dma-buf.h`,
  `include/linux/dma-resv.h`, `sound/core/pcm_lib.c`, `sound/soc/soc-pcm.c`,
  `sound/soc/soc-component.c`, `sound/soc/soc-dai.c`, `include/sound/pcm.h`,
  `include/sound/soc-dai.h`, `include/sound/soc-component.h`), and cross
  checked against upstream v6.12 (`raw.githubusercontent.com/torvalds/linux/v6.12/...`).
  Upstream commit hashes quoted below were read from the upstream GitHub API
  and are real; where a commit could not be verified, the text says so.

**A clean compile is not evidence of correct behaviour.** Several findings
below are in code that compiles without a warning.

---

## Findings (ordered by severity)

### 1. DEADLOCK/ATOMIC-SLEEP — the component `.delay` callback does a blocking DSP round trip from the IRQ-disabled pointer path

**Port** (`sound/soc/msm/msm-pcm-q6-v2.c`):

```c
2844: static snd_pcm_sframes_t msm_pcm_delay_blk(struct snd_soc_component *component,
2845: 		struct snd_pcm_substream *substream)
2846: {
...
2853: 	ret = q6asm_get_path_delay(prtd->audio_client);
2854: 	if (ret) {
2855: 		pr_err("%s: get_path_delay failed, ret=%d\n", __func__, ret);
2856: 		return 0;
2857: 	}
...
2871: static struct snd_soc_component_driver msm_soc_component = {
...
2883: 	.delay		= msm_pcm_delay_blk,
```

**Donor** (`oc-test/techpack/audio/asoc/msm-pcm-q6-v2.c:2856-2887`) has the
same function body, but hangs it off a *different* hook:

```c
static struct snd_soc_component_driver msm_soc_component = {
	.name		= DRV_NAME,
	.ops		= &msm_pcm_ops,
	.pcm_new	= msm_asoc_pcm_new,
	.delay_blk      = msm_pcm_delay_blk,
};
```

and the donor's ASoC core deliberately **never** calls it:

* `oc-test/sound/soc/soc-pcm.c:1278-1279` — in `soc_pcm_pointer()`:
  ```c
  		if (component->driver->delay_blk)
  			return offset;
  ```
  i.e. the donor's core returns *before* computing any delay when a
  component provides `delay_blk`.
* `oc-test/sound/soc/soc-pcm.c:1303-1320` — `soc_pcm_delay_blk()` is the
  only other user, and it is installed as `rtd->ops.delay_blk`
  (`oc-test/sound/soc/soc-pcm.c:3558,3569`).
* `oc-test/include/sound/pcm.h:83` declares `int (*delay_blk)(struct
  snd_pcm_substream *substream);` in `struct snd_pcm_ops`.
* A whole-tree grep of the donor shows **no caller of `ops->delay_blk`
  anywhere** in `sound/`:
  ```
  $ grep -rn "delay_blk" --include=*.c --include=*.h .   # donor
  include/sound/pcm.h:83
  include/sound/soc.h:818
  sound/soc/soc-pcm.c:1278, 1303, 1314, 1315, 3558, 3569
  techpack/audio/asoc/msm-pcm-q6-v2.c:2856, 2887
  ```
  So in the donor the DSP query was **dead code**: `runtime->delay` stayed 0
  and `q6asm_get_path_delay()` was never called.

**The 6.12 contract** (in-tree):

* `include/sound/soc-component.h:155` — the component driver now owns the
  delay hook:
  ```c
  	snd_pcm_sframes_t (*delay)(struct snd_soc_component *component,
  				 struct snd_pcm_substream *substream);
  ```
* `sound/soc/soc-component.c:1006-1034` — `snd_soc_pcm_component_delay()`
  calls `component->driver->delay(component, substream)` for every component.
* `sound/soc/soc-pcm.c:1315-1330` — `soc_pcm_pointer()` calls it:
  ```c
  	offset = snd_soc_pcm_component_pointer(substream);
  	/* should be called *after* snd_soc_pcm_component_pointer() */
  	snd_soc_pcm_dai_delay(substream, &cpu_delay, &codec_delay);
  	snd_soc_pcm_component_delay(substream, &cpu_delay, &codec_delay);
  ```
* `sound/core/pcm_lib.c:289,310` — `snd_pcm_update_hw_ptr0()` calls
  `pos = substream->ops->pointer(substream);`, i.e. `soc_pcm_pointer()`.
* `sound/core/pcm_lib.c:1903-1922` — `snd_pcm_period_elapsed_under_stream_lock()`
  calls `snd_pcm_update_hw_ptr0(substream, 1)`.
* `sound/core/pcm_lib.c:1936-1944` — `snd_pcm_period_elapsed()` runs it under
  `guard(pcm_stream_lock_irqsave)(substream)`, i.e. **with interrupts
  disabled**.

**Who reaches it**: `sound/soc/msm/msm-pcm-q6-v2.c:162, 202, 230, 306` call
`snd_pcm_period_elapsed(substream)` from `event_handler()`, the ADSP APR
interrupt callback. So the chain is:

ADSP IRQ -> `event_handler()` -> `snd_pcm_period_elapsed()` (IRQs off) ->
`snd_pcm_update_hw_ptr0()` -> `soc_pcm_pointer()` ->
`snd_soc_pcm_component_delay()` -> `msm_pcm_delay_blk()` ->
`q6asm_get_path_delay()`.

**What sleeps**: `sound/soc/msm/q6asm.c:10986-11026` (unchanged from the
donor):

```c
11007: 	rc = wait_event_timeout(ac->cmd_wait,
11008: 			(atomic_read(&ac->cmd_state) >= 0),
11009: 			msecs_to_jiffies(TIMEOUT_MS));
```

That is a **sleeping wait with interrupts disabled**, and worse, it is a
round trip to the DSP whose *reply* is delivered on the same APR interrupt
that is currently being serviced. The DSP cannot answer until the callback
returns; the callback will not return until the DSP answers. The wait can
only end by timing out (`TIMEOUT_MS`).

**Severity**: DEADLOCK/ATOMIC-SLEEP.

**Runtime evidence** (added by the port after this audit started, commit
`fdfca326d`, which quotes the run343 dmesg stream
`porting/artifacts/snapshot60/run343-audio-boot/dmesg-stream.txt` line 4213):

```
BUG: scheduling while atomic: writer/4676/0x00000002
q6asm_get_path_delay+0xc0/0x1d4 [q6_dlkm]
msm_pcm_delay_blk+0x24+0xa0 [platform_dlkm]
snd_soc_pcm_component_delay+0xb8+0x130
soc_pcm_pointer+0x58+0x9c
snd_pcm_update_hw_ptr0+0x68+0x3e0
```

The stack matches the chain derived above exactly, so this finding is
confirmed at runtime and not only from the source.

**Upstream commits**: the delay hook moved from the codec/DAI to the
component in the 6.x ASoC rework; the two relevant upstream commits are
`403f830e7a0b` ("ASoC: soc-component: add snd_soc_pcm_component_delay()")
and `8544f08c8162` ("ASoC: soc-dai: update snd_soc_dai_delay() to
snd_soc_pcm_dai_delay()"). The specific "the component delay is called from
the pointer path" placement is upstream behaviour in 6.12 and is proved by
the in-tree references above.

**Proposed minimal fix** (implemented by the port in commit `fdfca326d`,
after this audit started): delete the callback and its registration, i.e.
restore the donor's effective behaviour (runtime delay 0, no DSP query from
the IRQ path).

```diff
--- a/sound/soc/msm/msm-pcm-q6-v2.c
+++ b/sound/soc/msm/msm-pcm-q6-v2.c
@@ -2844,26 +2844,6 @@
-static snd_pcm_sframes_t msm_pcm_delay_blk(struct snd_soc_component *component,
-		struct snd_pcm_substream *substream)
-{
-	...
-	ret = q6asm_get_path_delay(prtd->audio_client);
-	...
-}
-
 static struct snd_soc_component_driver msm_soc_component = {
 	...
-	.delay		= msm_pcm_delay_blk,
 	.pcm_construct	= msm_asoc_pcm_new,
 };
```

(`q6asm_get_path_delay()` itself is still needed by the compress path and
must stay.)

---

### 2. SILENT-BEHAVIOUR — `msm_routing_get_adm_topology()` was reduced to a no-op while removing an always-false comparison

**Port** (`sound/soc/msm/msm-pcm-routing-v2.c`):

```c
1257: static int msm_routing_get_adm_topology(int fedai_id, int session_type,
1258: 					int be_id)
1259: {
1260: 	int topology = NULL_COPP_TOPOLOGY;
1261: 	int app_type = 0, acdb_dev_id = 0;
1262:
1263: 	pr_debug("%s: fedai_id %d, session_type %d, be_id %d\n",
1264: 	       __func__, fedai_id, session_type, be_id);
1265:
1268: 		goto done;
1269:
1270: 	app_type = fe_dai_app_type_cfg[fedai_id][session_type][be_id].app_type;
...
1290: done:
1291: 	pr_debug("%s: Using topology %d\n", __func__, topology);
1292: 	return topology;
1293: }
```

**Donor** (`oc-test/techpack/audio/asoc/msm-pcm-routing-v2.c:1257-1293`) is
identical except for one line:

```c
 	if (cal_data == NULL)
 		goto done;
```

`cal_data` is an **array**, in both trees:

* port: `sound/soc/msm/msm-pcm-routing-v2.c:56`
  `static struct cal_type_data *cal_data[MAX_ROUTING_CAL_TYPES];`
* donor: `oc-test/techpack/audio/asoc/msm-pcm-routing-v2.c:56` — identical.

So `cal_data == NULL` compares an array's address with 0: **always false**.
The donor therefore always fell through into the LSM/ADM topology lookup.
The port deleted the `if` line (to silence the always-true `-Waddress`
diagnostic) but left the `goto done;` behind, so the port **never** performs
the lookup and always returns `NULL_COPP_TOPOLOGY`.

**Effect**: every routing session is set up with the "no COPP topology"
value instead of the topology selected from the calibration data. The
function's own debug print says "Using topology %d" and always prints the
fallback. This is silent — no error, no warning, and the code after the
`goto` is unreachable, so the compiler does not warn either.

**Severity**: SILENT-BEHAVIOUR (functional regression in the routing path;
a plausible contributor to "no backend DAIs enabled for MSM8x16 Media9",
which is still an open problem in `porting/findings/2026-10-21-run340-audio-bind-panic.md`).

**Upstream commit**: not applicable — this is a port-introduced edit, not an
upstream API change. The line was introduced by the port commit
`867dfaaac2f1` ("ASoC: msm: build the sound card, and port the PCM platform
layer"), confirmed by `git blame -L 1260,1275 HEAD -- sound/soc/msm/msm-pcm-routing-v2.c`.

**Proposed minimal fix**: restore the fall-through and keep the semantics
of the donor (the array test was dead code, so the correct conversion is to
drop the test *and* the `goto`, not the test alone).

```diff
--- a/sound/soc/msm/msm-pcm-routing-v2.c
+++ b/sound/soc/msm/msm-pcm-routing-v2.c
@@ -1265,8 +1265,6 @@
 	pr_debug("%s: fedai_id %d, session_type %d, be_id %d\n",
 	       __func__, fedai_id, session_type, be_id);
 
-		goto done;
-
 	app_type = fe_dai_app_type_cfg[fedai_id][session_type][be_id].app_type;
```

---

### 3. SILENT-BEHAVIOUR — the AFE PCM lost its copy callback, so the AFE proxy path is now dead code

**Port** (`sound/soc/msm/msm-pcm-afe-v2.c`):

```c
600: static int msm_afe_copy(struct snd_pcm_substream *substream, int channel,
601: 			unsigned long hwoff, void __user *buf, unsigned long fbytes)
...
838: static const struct snd_pcm_ops msm_afe_ops = {
839: 	.open           = msm_afe_open,
840: 	.hw_params	= msm_afe_hw_params,
841: 	.trigger	= msm_afe_trigger,
842: 	.close          = msm_afe_close,
843: 	.prepare        = msm_afe_prepare,
844: 	.mmap		= msm_afe_mmap,
845: 	.pointer	= msm_afe_pointer,
846: };
...
866: static struct snd_soc_component_driver msm_soc_component = {
867: 	.name		= DRV_NAME,
868: 	.probe		= msm_afe_afe_probe,
869: };
```

**Donor** (`oc-test/techpack/audio/asoc/msm-pcm-afe-v2.c:837-870`):

```c
static const struct snd_pcm_ops msm_afe_ops = {
	.open           = msm_afe_open,
	.copy_user      = msm_afe_copy,
	.hw_params	= msm_afe_hw_params,
	...
};

static struct snd_soc_component_driver msm_soc_component = {
	.name		= DRV_NAME,
	.ops		= &msm_afe_ops,
	.pcm_new	= msm_asoc_pcm_new,
	...
};
```

The port dropped three things at once (the commit that did it is
`988aa8e28` "ASoC: msm: build and register the AFE PCM", which says
"Three pieces of this file's API are gone here and are dropped rather than
emulated: snd_pcm_ops.copy_user, the component driver's .ops, and
.pcm_new."):

1. `.copy_user = msm_afe_copy` — the only path that pushes user data into
   the AFE proxy port.
2. `.ops = &msm_afe_ops` — the whole PCM operation set.
3. `.pcm_new = msm_asoc_pcm_new`.

**Why this is a behaviour change, not just an API rename**: in 6.12 the
per-PCM operations come from the *component* driver, not from
`snd_pcm_ops`:

* `sound/soc/soc-component.c:1087-1103` — `snd_soc_pcm_component_copy()`
  dispatches to `component->driver->copy(component, substream, channel,
  pos, iter, bytes)`.
* `include/sound/pcm.h:56-86` — the 6.12 `struct snd_pcm_ops` has
  `.copy(substream, channel, pos, struct iov_iter *iter, bytes)`; the
  4.19 `.copy_user`/`.copy_kernel` pair is gone
  (`6c0217b11066` "ALSA: pcm: Drop obsoleted PCM copy_user and copy_kernel
  ops", `205d3e030a02` "ASoC: pcm: Drop obsoleted PCM copy_user ops").
* `include/sound/soc-component.h` — the component driver has
  `.open/.close/.prepare/.hw_params/.trigger/.pointer/.copy/.mmap`.

With the AFE component driver carrying none of those, the AFE proxy
callbacks are unreachable:

* `msm_afe_copy()` (port line 600) is the only caller of
  `afe_rt_proxy_port_write()` / `afe_rt_proxy_port_read()` (port lines
  522, 561). Nothing calls `msm_afe_copy()` any more.
* `msm_afe_ops` (port line 838) is referenced by nothing.
* `msm_asoc_pcm_new()` (port line 849) is referenced by nothing.

Whole-tree check:

```
$ grep -rn "msm_afe_ops\|msm_afe_copy\|msm_asoc_pcm_new" sound/soc/msm/
sound/soc/msm/msm-pcm-afe-v2.c:600:static int msm_afe_copy(...)
sound/soc/msm/msm-pcm-afe-v2.c:838:static const struct snd_pcm_ops msm_afe_ops = {
sound/soc/msm/msm-pcm-afe-v2.c:849:static int msm_asoc_pcm_new(...)
```

(the `msm_asoc_pcm_new` hits in the other files are different, per-driver
functions that *are* wired to `.pcm_construct`.)

**Effect**: even if the "MSM AFE-PCM RX/TX" links (`sound/soc/msm/msm8952.c:1965`
and `:1980`, `sound/soc/msm/msm8952-dai-links.c:226,241`) do create a PCM,
no user data is ever handed to the AFE proxy port. The AFE proxy path
cannot work.

**Severity**: SILENT-BEHAVIOUR (the AFE proxy endpoints are inert).

**Upstream commits** for the API shape: `cf393babb37a` ("ALSA: pcm: Add copy
ops with iov_iter"), `66201cacc33d` ("ASoC: component: Add generic PCM copy
ops"), `6c0217b11066`, `205d3e030a02` (see above).

**Proposed minimal fix**: convert the donor's `copy_user` callback to the
6.12 `iov_iter` `.copy` signature and put the PCM operations back on the
component driver. The other callbacks (`msm_afe_open`, `msm_afe_close`,
`msm_afe_prepare`, `msm_afe_hw_params`, `msm_afe_trigger`,
`msm_afe_pointer`, `msm_afe_mmap`) also need the
`struct snd_soc_component *` first argument that 6.12 uses; only the
signatures change, the bodies are unchanged. Sketch (the
`msm_afe_*` signature changes are elided):

```diff
--- a/sound/soc/msm/msm-pcm-afe-v2.c
+++ b/sound/soc/msm/msm-pcm-afe-v2.c
@@
-static int msm_afe_copy(struct snd_pcm_substream *substream, int channel,
-			unsigned long hwoff, void __user *buf, unsigned long fbytes)
+static int msm_afe_copy(struct snd_soc_component *component,
+			struct snd_pcm_substream *substream, int channel,
+			unsigned long hwoff, struct iov_iter *iter,
+			unsigned long fbytes)
 {
 	...
-	if (copy_from_user(hwbuf, buf, fbytes)) {
+	if (copy_from_iter(hwbuf, fbytes, iter) != fbytes) {
 		ret = -EFAULT;
 		goto fail;
 	}
 	...
-	if (copy_to_user(buf, hwbuf, fbytes)) {
+	if (copy_to_iter(hwbuf, fbytes, iter) != fbytes) {
 		ret = -EFAULT;
 		goto fail;
 	}
 }
@@
 static struct snd_soc_component_driver msm_soc_component = {
 	.name		= DRV_NAME,
+	.open		= msm_afe_open,
+	.close		= msm_afe_close,
+	.prepare	= msm_afe_prepare,
+	.hw_params	= msm_afe_hw_params,
+	.trigger	= msm_afe_trigger,
+	.pointer	= msm_afe_pointer,
+	.copy		= msm_afe_copy,
+	.mmap		= msm_afe_mmap,
+	.pcm_construct	= msm_asoc_pcm_new,
 	.probe		= msm_afe_afe_probe,
 };
```

Note the `copy_from_iter() != fbytes` form: the `*_iter()` helpers return the
number of bytes **copied**, so a short copy must be compared against the
requested length — upstream commit `e14ebde5df2a` ("ALSA: pcm: Fix error
checks of default read/write copy ops"), see the "copy_* return-value
semantics" section below.

---

### 4. UNSAFE — `dma_buf_map_attachment()`/`dma_buf_unmap_attachment()` are called without the dma-buf reservation lock

**Port** (`sound/soc/msm/msm_audio_ion.c`):

```c
117: 	alloc_data->table = dma_buf_map_attachment(alloc_data->attach,
118: 				DMA_BIDIRECTIONAL);
...
165: 			dma_buf_unmap_attachment(alloc_data->attach,
166: 						 alloc_data->table,
167: 						 DMA_BIDIRECTIONAL);
```

**Donor** (`oc-test/techpack/audio/dsp/msm_audio_ion.c:117,165`) has the
identical calls. In CAF 4.19 they were correct: the donor's
`drivers/dma-buf/dma-buf.c:860-895` takes no lock and asserts nothing:

```c
struct sg_table *dma_buf_map_attachment(struct dma_buf_attachment *attach,
					enum dma_data_direction direction)
{
	...
	sg_table = attach->dmabuf->ops->map_dma_buf(attach, direction);
```

**The 6.12 contract** (in-tree, and identical to upstream v6.12):

* `drivers/dma-buf/dma-buf.c:1532-1542` — "Convention for importers / 1.
  Importers **must hold** the dma-buf reservation lock when calling these
  functions: ... `dma_buf_map_attachment()`, `dma_buf_unmap_attachment()`,
  `dma_buf_vmap()`, `dma_buf_vunmap()`".
* `drivers/dma-buf/dma-buf.c:1544-1560` — the *unlocked* variants
  (`dma_buf_map_attachment_unlocked()`, `dma_buf_unmap_attachment_unlocked()`,
  `dma_buf_vmap_unlocked()`, `dma_buf_vunmap_unlocked()`) are the ones that
  must be called **without** the lock held; they take it themselves.
* `drivers/dma-buf/dma-buf.c:1833` — `dma_buf_map_attachment()`:
  `dma_resv_assert_held(attach->dmabuf->resv);`
* `drivers/dma-buf/dma-buf.c:1936` — `dma_buf_unmap_attachment()`:
  `dma_resv_assert_held(attach->dmabuf->resv);`
* `include/linux/dma-resv.h:312` — `#define dma_resv_assert_held(obj)
  lockdep_assert_held(&(obj)->lock.base)`.

Cross-checks inside this tree that the port's form is the wrong one:

* `drivers/iio/industrialio-buffer.c:1690,1697` takes the lock explicitly
  (`iio_dma_resv_lock(dmabuf, nonblock)`) and then calls the plain
  `dma_buf_map_attachment()` — the correct pattern.
* `drivers/gpu/msm/kgsl.c:3172,3216`,
  `drivers/media/common/videobuf2/videobuf2-dma-contig.c:708,719,751`,
  `drivers/gpu/drm/drm_prime.c:964,982,1080` all use the
  `*_unlocked()` variants because they do not hold the lock.

**The port already uses the `_unlocked` variants for vmap/vunmap**
(`sound/soc/msm/msm_audio_ion.c:247` `dma_buf_vmap_unlocked()` and `:298`
`dma_buf_vunmap_unlocked()`), but the attachment mapping was left in the
4.19 form. The two calls are in the *same* function pair
(`msm_audio_dma_buf_map()` / `msm_audio_dma_buf_unmap()`), so the
inconsistency is visible side by side.

**Practical impact in this build**: `CONFIG_LOCKDEP` is not enabled
(`out/.config` has only `CONFIG_LOCKDEP_SUPPORT=y`; `CONFIG_PROVE_LOCKING`,
`CONFIG_DEBUG_MUTEXES` and `CONFIG_DEBUG_ATOMIC_SLEEP` are all not set), so
`lockdep_assert_held()` compiles to nothing
(`include/linux/lockdep.h:392`) and no splat is produced. The violation is
therefore silent here. What is lost is the exclusion of the exporter's
migration/fence: between `dma_buf_map_attachment()` and the use of
`alloc_data->table->sgl->dma_address` (`sound/soc/msm/msm_audio_ion.c:27-28`,
`:128`) the buffer is not protected against the exporter moving it, and
`dma_buf_unmap_attachment()`'s `dma_buf_unpin()` (which itself asserts the
lock) runs unprotected for dynamic importers.

**Severity**: UNSAFE (protocol violation; silent in this configuration
because lockdep is off). It is a latent deadlock/race source if the same
code is used with a dynamic importer or with `CONFIG_LOCKDEP` enabled.

**Upstream commits** (verified via the upstream GitHub API, all present in
v6.12):

* `47e982d5195d76c621d21d2f1911159175d0839e` — "dma-buf: Move
  dma_buf_map_attachment() to dynamic locking specification" (Dmitry
  Osipenko, 2022-10-17). *This is the commit that added
  `dma_resv_assert_held()` to `dma_buf_map_attachment()` and
  `dma_buf_unmap_attachment()`.*
* `19d6634d8789573a9212ce78dbb4348ffd4f7f78` — "dma-buf: Add unlocked
  variant of attachment-mapping functions" (adds
  `dma_buf_map_attachment_unlocked()` / `dma_buf_unmap_attachment_unlocked()`).
* `56e5abba8c3ec5c6098007693f9cefafaa2aa010` — "dma-buf: Add unlocked
  variant of vmapping functions" (adds `dma_buf_vmap_unlocked()` /
  `dma_buf_vunmap_unlocked()`) — the pair the port's fix `d67199a80` used.

**Proposed minimal fix** (use the self-locking variants, exactly as the
port already does for vmap/vunmap):

```diff
--- a/sound/soc/msm/msm_audio_ion.c
+++ b/sound/soc/msm/msm_audio_ion.c
@@ -117,2 +117,2 @@
-	alloc_data->table = dma_buf_map_attachment(alloc_data->attach,
+	alloc_data->table = dma_buf_map_attachment_unlocked(alloc_data->attach,
 				DMA_BIDIRECTIONAL);
@@ -165,3 +165,3 @@
-			dma_buf_unmap_attachment(alloc_data->attach,
+			dma_buf_unmap_attachment_unlocked(alloc_data->attach,
 						 alloc_data->table,
 						 DMA_BIDIRECTIONAL);
```

---

### 5. DATA-CORRUPTION/UNSAFE — the explicit cache flush before the SCM call was removed from `msm_mdf.c`

**Port** (`sound/soc/msm/msm_mdf.c`):

```c
364: 	scm_buffer->dest_info_size =
365: 		sizeof(struct msm_mdf_dest_vm_and_perm_info) * SUBSYS_MAX;
366:
367: 	/* The SCM call takes the arguments by value, and this buffer is
368: 	 * an ordinary allocation, so there is nothing to flush for it.
369: 	 */
370:
371: 	desc.args[0] = scm_buffer->dma_start_address;
372: 	desc.args[1] = scm_buffer->dma_end_address;
373: 	desc.args[2] = virt_to_phys(&(scm_buffer->dest_info[0]));
374: 	desc.args[3] = scm_buffer->dest_info_size;
```

**Donor** (`oc-test/techpack/audio/dsp/msm_mdf.c:364-370`):

```c
 	/* flush cache required by scm_call2 */
 	dmac_flush_range(scm_buffer, ((void *)scm_buffer) +
 					sizeof(struct msm_mdf_protect_mem));

 	desc.args[0] = scm_buffer->dma_start_address;
 	desc.args[1] = scm_buffer->dma_end_address;
 	desc.args[2] = virt_to_phys(&(scm_buffer->dest_info[0]));
 	desc.args[3] = scm_buffer->dest_info_size;
```

The port's justification is factually wrong: the SCM does **not** take
`dest_info` by value. `desc.args[2]` is the *physical address* of
`scm_buffer->dest_info[0]` and `desc.args[3]` its size, so the secure world
reads that array out of memory. The donor flushed the cache for exactly
that reason ("flush cache required by scm_call2").

The donor's flush was `dmac_flush_range()`, which on CAF's arm64 is
`__dma_flush_area()` — a clean+invalidate of the cache lines
(`oc-test/arch/arm64/include/asm/cacheflush.h:137-139`). That API does not
exist in 6.12 arm64 (`arch/arm64/include/asm/cacheflush.h` in this tree has
no `dmac_flush_range`), so *something* had to change; but deleting the
flush and asserting that nothing needs flushing is not a conversion, it is
a behaviour change with an incorrect rationale.

**Effect**: the `TZ_MPU_LOCK_NS_REGION` SCM call can be handed stale
`dest_info` (VM ids and permissions) and lock the wrong VM range, or fail
to lock the intended one. This is the memory-protection setup for the MDF
(audio DSP) memory pool on a non-coherent SMMU.

**Severity**: DATA-CORRUPTION/UNSAFE. The exact 6.12 replacement for a
kernel-linear buffer that the secure world reads via SMMU still has to be
chosen and validated; it is not simply "drop the flush". This report does
not claim a fix.

**Upstream commit**: not applicable — `dmac_flush_range()` was removed from
arm64 long before 6.12 (the 6.12 arm64 header has no such macro and
`include/linux/dma-mapping.h` has no `dma_cache_wb()`); the donor's call
was a CAF/arm64-4.19 idiom. The replacement is "upstream commit not
identified".

**Proposed fix**: none proposed; this needs a decision plus a runtime
check. At minimum, the port must not claim the flush is unnecessary: the
`dest_info` array is read from memory by the SCM and must be made visible
to it (e.g. a clean of the buffer before the `scm_call2()`, with the
correct 6.12/arm64 primitive chosen for a kernel-linear allocation).

---

### 6. SILENT-BEHAVIOUR — the AFE clock-source getter now fails with `-EINVAL` on this platform

**Port** (`sound/soc/msm/q6afe.c`):

```c
8947: 	/* an array member is never NULL; an empty name means unset */
8948: 	if (!clkinfo_per_port[idx].clk_src_name[0])
8949: 		return -EINVAL;
8950: 	strscpy(clk_src, clkinfo_per_port[idx].clk_src_name,
8951: 				CLK_SRC_NAME_MAX);
```

**Donor** (`oc-test/techpack/audio/dsp/q6afe.c:8903-8910`):

```c
 	if (clkinfo_per_port[idx].clk_src_name == NULL)
 		return -EINVAL;
 	strlcpy(clk_src, clkinfo_per_port[idx].clk_src_name,
 				CLK_SRC_NAME_MAX);
```

`clk_src_name` is an array member in both trees
(`sound/soc/msm/q6afe.c:279`: `char clk_src_name[CLK_SRC_NAME_MAX];`), so
the donor's `== NULL` test was **always false** and the donor always
copied the (possibly empty) name and returned 0. The port replaced the
dead test with a *live* one, which changes the result.

Nothing on this platform ever sets the name:

* `afe_set_source_clk()` (`sound/soc/msm/q6afe.c:8967-8986`) is only called
  from `sound/soc/msm/q6afe.c:9273,9277`, and those calls are guarded by
  `if (clk_src_name[0][0] != 0)` on the *static* array
  `clk_src_name[CLK_SRC_MAX][CLK_SRC_NAME_MAX]` (`:344`), which is filled
  by `afe_set_clk_src_array()`.
* In the donor, `afe_set_clk_src_array()` is called only from
  `oc-test/techpack/audio/asoc/qcs405.c:10832` — a different platform.
  `grep -rn "afe_set_clk_src_array" sound/soc/msm/` in the port finds no
  caller.

So on msm8952 `clkinfo_per_port[idx].clk_src_name` is always the empty
string, and the port's new test makes `afe_get_clk_src()` fail for every
port. The single caller is `afe_set_pll_clk_drift()`
(`sound/soc/msm/q6afe.c:9064`), which is itself called from
`sound/soc/msm/msm-pcm-routing-v2.c:31184`:

```c
9064: 	ret = afe_get_clk_src(port_id, clk_src_name);
9065: 	if (ret) {
9066: 		pr_err("%s: cannot get clk src name for port id 0x%x\n",
9067: 			__func__, port_id);
9068: 		return -EINVAL;
9069: 	}
```

**Effect**: the "AFE clock drift" mixer control now always fails with
`-EINVAL` on this platform, where the donor succeeded (with an empty clock
source name). It is a debug/tuning control, not the normal playback path.

**Severity**: SILENT-BEHAVIOUR (narrow: one mixer control).

**Upstream commit**: not applicable; the donor's test was dead code and the
port changed the semantics.

**Proposed minimal fix**: keep the donor's effective behaviour — i.e. drop
the test rather than replacing it with a live one (or keep the empty-name
case working):

```diff
--- a/sound/soc/msm/q6afe.c
+++ b/sound/soc/msm/q6afe.c
@@ -8947,4 +8947,2 @@
-	/* an array member is never NULL; an empty name means unset */
-	if (!clkinfo_per_port[idx].clk_src_name[0])
-		return -EINVAL;
 	strscpy(clk_src, clkinfo_per_port[idx].clk_src_name,
```

---

### 7. SILENT-BEHAVIOUR — the DAI stub platform drivers lost their `.remove` callback

**Port** (`sound/soc/msm/msm-dai-stub-v2.c`):

```c
276: static void msm_dai_stub_dev_remove(struct platform_device *pdev)
277: {
278: 	snd_soc_unregister_component(&pdev->dev);
279: }
...
287: static struct platform_driver msm_dai_stub_dev = {
288: 	.probe  = msm_dai_stub_dev_probe,
289: 	.driver = {
...
295: };
...
313: static void msm_dai_stub_remove(struct platform_device *pdev)
314: {
315: 	pr_debug("%s:\n", __func__);
316:
317: }
...
327: static struct platform_driver msm_dai_stub_driver = {
328: 	.probe  = msm_dai_stub_probe,
329: 	.driver = {
```

**Donor** (`oc-test/techpack/audio/asoc/msm-dai-stub-v2.c:283-300,313-345`):

```c
 static struct platform_driver msm_dai_stub_dev = {
 	.probe  = msm_dai_stub_dev_probe,
 	.remove = msm_dai_stub_dev_remove,
 	.driver = { ... },
 };
...
 static struct platform_driver msm_dai_stub_driver = {
 	.probe  = msm_dai_stub_probe,
 	.remove = msm_dai_stub_remove,
 	.driver = { ... },
 };
```

The port converted the two `remove` callbacks to `void` (correct for 6.12:
platform `.remove` returns void since v6.11) and then **deleted the
assignments** instead of keeping them. The result:

* `msm_dai_stub_dev_remove()` (line 276) and `msm_dai_stub_remove()`
  (line 313) are dead code.
* `snd_soc_unregister_component()` is never called for the stub DAI
  component, so on a device removal / module unload the component and its
  registered DAIs stay in the ASoC component list.

**Severity**: SILENT-BEHAVIOUR (resource leak on teardown; the functions are
also unreferenced, so the object should not build warning-free — the
run344 build log `porting/artifacts/snapshot60/run344-build.log` is
incremental and does not show this object being compiled, so this is *not*
verified from a build).

**Upstream commit**: the `void` platform `.remove` conversion is upstream
("platform: Provide a remove callback that returns no value", v6.11); the
deletion of the assignment is a port-introduced slip, not an upstream
change.

**Proposed minimal fix**:

```diff
--- a/sound/soc/msm/msm-dai-stub-v2.c
+++ b/sound/soc/msm/msm-dai-stub-v2.c
@@ -287,6 +287,7 @@
 static struct platform_driver msm_dai_stub_dev = {
 	.probe  = msm_dai_stub_dev_probe,
+	.remove = msm_dai_stub_dev_remove,
 	.driver = {
@@ -327,6 +328,7 @@
 static struct platform_driver msm_dai_stub_driver = {
 	.probe  = msm_dai_stub_probe,
+	.remove = msm_dai_stub_remove,
 	.driver = {
```

---

### 8. SILENT-BEHAVIOUR (low) — `kzfree()` was converted to `kfree()`, dropping the zeroing the donor did

**Port** (`sound/soc/msm/rtac.c`):

```c
2013: 	if (rtac_asm_buffer == NULL) {
2014: 		kfree(rtac_adm_buffer);
2015: 		goto nomem;
2016: 	}
...
2027: 		kfree(rtac_adm_buffer);
2028: 		kfree(rtac_asm_buffer);
...
2045: 		kfree(rtac_adm_buffer);
2046: 		kfree(rtac_asm_buffer);
2047: 		kfree(rtac_afe_buffer);
...
2052: 		kfree(rtac_adm_buffer);
2053: 		kfree(rtac_asm_buffer);
2054: 		kfree(rtac_afe_buffer);
2055: 		kfree(rtac_voice_buffer);
...
2067: 	kfree(rtac_adm_buffer);
2068: 	kfree(rtac_asm_buffer);
2069: 	kfree(rtac_afe_buffer);
2070: 	kfree(rtac_voice_buffer);
```

**Donor** (`oc-test/techpack/audio/dsp/rtac.c:2014,2027-2028,2045-2047,
2052-2055,2067-2070` — the same lines) uses `kzfree()`.

The donor's `kzfree()` **does zero the memory** before freeing
(`oc-test/mm/slab_common.c:1605-1616`):

```c
void kzfree(const void *p)
{
	size_t ks;
	void *mem = (void *)p;
	...
	ks = ksize(mem);
	memzero_explicit(mem, ks);
	kfree(mem);
}
```

In 6.12 `kzfree()` no longer exists: upstream renamed it to
`kfree_sensitive()` (which keeps the `memzero_explicit()`) and then removed
the alias. This tree has `kfree_sensitive()` at `include/linux/slab.h:451`
and `mm/slab_common.c:1307`. The port's `kfree()` therefore compiles but
**drops the zeroing**, so the freed RTAC calibration buffers (which hold
userspace-supplied calibration data) can leave their contents in the freed
slab pages.

**Severity**: SILENT-BEHAVIOUR (low). Not a functional break, but a
hardening regression versus the donor, and the 6.12 API has an exact
equivalent.

**Upstream commits** (verified via the upstream GitHub API):
* `453431a54934` — "mm, treewide: rename kzfree() to kfree_sensitive()"
  (the rename that makes `kzfree()` unavailable and `kfree_sensitive()` the
  replacement).
* `23224e45004ed84c8466fd1e8e5860f541187029` — "mm: remove kzfree()
  compatibility definition" (removes the alias).

**Proposed minimal fix**: use `kfree_sensitive()`.

```diff
--- a/sound/soc/msm/rtac.c
+++ b/sound/soc/msm/rtac.c
@@
-		kfree(rtac_adm_buffer);
+		kfree_sensitive(rtac_adm_buffer);
```

(same for the other 14 call sites listed above)

---

### 9. OK-NOTE (low) — a `pr_debug()` format/argument mismatch was inherited from the donor and is now correct; a `%d` -> `%zu` change is correct

* `sound/soc/msm/q6asm.c:429-431` (port):
  ```c
  			pr_debug("COLD: apr_send_pkt at %lld sec %ld microsec\n",
  				out_cold_tv.tv_sec,
  				out_cold_tv.tv_nsec / 1000);
  ```
  The donor had `pr_debug("%s: COLD: apr_send_pkt at %ld sec %ld microsec\n",
  out_cold_tv.tv_sec, out_cold_tv.tv_usec);` — a `%s` with **no** `__func__`
  argument, i.e. a donor bug. The port's `timespec64` conversion removed the
  stray `%s` and the format now matches its arguments. No change needed.
* `sound/soc/msm/q6voice.c:2767-2768`: `%d` -> `%zu` for
  `col_data->cal_data.size`. The member is `size_t size;`
  (`sound/soc/msm/caf-include/dsp/audio_cal_utils.h:13-17`), so `%zu` is the
  correct specifier and the donor's `%d` was the bug. No change needed.
* `sound/soc/msm/q6voice.c:4464`: `ver_info->services[0].api_version` ->
  `ver_info->services->api_version`. `struct avcs_fwk_ver_info` has
  `struct avcs_svc_api_info services[];`
  (`sound/soc/msm/caf-include/dsp/apr_audio-v2.h:11708`), a flexible array
  member, so the two spellings are the same object. No change needed.

---

## Checked and clean (no findings)

Each item below was swept and produced no behavioural difference between
the port and the donor. The file:line evidence is given so the coverage can
be checked.

**copy_*/user/iter return-value semantics**
* `sound/soc/msm/msm-pcm-q6-v2.c:854` (`copy_from_iter(bufptr, xfer, iter)
  != xfer`) and `:1026` (`copy_to_iter(bufptr+offset, xfer, iter) != xfer`)
  — correct, matches the core's own convention at
  `sound/core/pcm_lib.c:2062-2064` (`default_write_copy`) and
  `:2095-2097` (`default_read_copy`). Fixed by `b250002a2`.
* `sound/soc/msm/msm-pcm-afe-v2.c:500,589`,
  `sound/soc/msm/msm-compress-q6-v2.c:3045,3050,3052,3108`,
  `sound/soc/msm/q6afe.c:7816`, `sound/soc/msm/wcd9xxx-core.c:721,831`,
  `sound/soc/msm/rtac.c` (many), `sound/soc/msm/q6asm.c:319,373`,
  `sound/soc/msm/adsp_err.c:69`, `sound/soc/msm/apr.c:72`,
  `sound/soc/msm/audio_calibration.c:413,430,499`,
  `sound/soc/msm/avtimer.c:436`, `sound/soc/msm/q6afecal-hwdep.c:85,117,140`,
  `sound/soc/msm/wcdcal-hwdep.c:82,114,137`,
  `sound/soc/msm/wcd-dsp-glink.c:336,340,410`,
  `sound/soc/msm/msm-pcm-voice-v2.c:351`,
  `sound/soc/msm/msm-pcm-routing-v2.c:31261` — all still
  `copy_{from,to}_user()`, whose contract (returns the number of bytes
  **not** copied) did not change in 6.12. The `if (copy_from_user(...))`
  test is still correct. Only the `*_iter()` family changed semantics.

**dma-buf / ION**
* `sound/soc/msm/msm_audio_ion.c:247` `dma_buf_vmap_unlocked()` and `:298`
  `dma_buf_vunmap_unlocked()` — correct (self-locking variants), fixed by
  `d67199a80`.
* `sound/soc/msm/msm_audio_ion.c:90` `dma_buf_attach()` and `:135,:169`
  `dma_buf_detach()` — these must be called **without** the lock
  (`drivers/dma-buf/dma-buf.c:1543-1552`), and the port does not hold it.
  Correct.
* `sound/soc/msm/msm_audio_ion.c:241,301,663,665` `dma_buf_begin_cpu_access()`
  / `dma_buf_end_cpu_access()` — must be called without the lock
  (`drivers/dma-buf/dma-buf.c:1554-1555`). The port does not hold it.
  Correct.
* `sound/soc/msm/msm_audio_ion.c:480` `dma_buf_get(fd)` / `:508,:327,:172`
  `dma_buf_put()` — reference counting is balanced: `msm_audio_ion_import()`
  takes one reference at `:480` and the free path drops it at `:172`; the
  error paths in `msm_audio_ion_buf_map()` (`:327`) and
  `msm_audio_ion_import()` (`:508`) drop it exactly once. Attach/detach
  pairing: `dma_buf_attach()` at `:90` is matched by `dma_buf_detach()` at
  `:135` (error path) and `:169` (normal path); `dma_buf_map_attachment()`
  at `:117` is matched by `dma_buf_unmap_attachment()` at `:165`.
* ION API: `sound/soc/msm/msm_audio_ion.c:383,386` use
  `ion_alloc(bufsz, ION_HEAP(ION_SYSTEM_HEAP_ID), 0)` /
  `ION_HEAP(ION_AUDIO_HEAP_ID)`. The heap ids and the `ION_HEAP()` macro are
  identical in both trees (`include/uapi/linux/msm_ion.h:43,54,99` in the
  port, `oc-test/drivers/staging/android/uapi/msm_ion.h:43,54,99` in the
  donor), and `ion_alloc()` is byte-for-byte the same function
  (`drivers/staging/android/ion/ion.c:1032` port,
  `oc-test/drivers/staging/android/ion/ion.c:1095` donor). The port's
  `ion_dma_buf_get_flags()` (`drivers/staging/android/ion/ion.c:949-956`)
  returns `buffer->flags`, exactly like the donor's
  (`oc-test/.../ion/ion.c:1008-1015`), so the `ION_FLAG_CACHED` test at
  `sound/soc/msm/msm_audio_ion.c:108,658` keeps its meaning.

**ALSA/ASoC callback signatures**
* `.copy` (iov_iter) conversions: `sound/soc/msm/msm-pcm-q6-v2.c:791,957,
  1095` and `sound/soc/msm/msm-pcm-q6-noirq.c:587` use
  `struct iov_iter *`, matching
  `include/sound/soc-component.h` and `sound/soc/soc-component.c:1087-1103`.
  The `buf += xfer` removal in the playback loop
  (`sound/soc/msm/msm-pcm-q6-v2.c:854-860`) is correct: `copy_from_iter()`
  advances the iterator itself.
* `.pointer` / `.ack` / `.trigger` / `.open` / `.close` / `.prepare` /
  `.hw_params` / `.ioctl` / `.compat_ioctl` / `.mmap` were converted to the
  `struct snd_soc_component *` first-argument form in
  `sound/soc/msm/msm-pcm-q6-v2.c:631,673,791,957,1095,1108,1119,1130,1143,
  1164,1204,1288` and the equivalent places in
  `sound/soc/msm/msm-pcm-q6-noirq.c:194,277,416,518,543,551,587,594,623,
  647`, `sound/soc/msm/msm-pcm-voice-v2.c:150,229,255,279,290,340`,
  `sound/soc/msm/msm-pcm-loopback-v2.c:247,373,430,491`,
  `sound/soc/msm/msm-pcm-routing-v2.c:30582,30604,30673`,
  `sound/soc/msm/msm-pcm-hostless.c:16`. All match
  `include/sound/soc-component.h`. `.ack` for compress
  (`sound/soc/msm/msm-compress-q6-v2.c:2971,5534`) is unchanged from the
  donor and still matches `include/sound/soc-dai.h:392`.
* DAI `.probe`/`.remove` moved from `snd_soc_dai_driver` to
  `snd_soc_dai_ops`: `sound/soc/msm/msm-dai-q6-v2.c:2826-2828,2836-2838,
  12219-12221` and `sound/soc/msm/msm-dai-stub-v2.c:38-41`. This is the
  6.12 shape (`include/sound/soc-dai.h:275-276`; `snd_soc_dai_driver` has
  no `.probe`/`.remove`, `include/sound/soc-dai.h:406-424`). The per-DAI
  call count is unchanged: the donor's `snd_soc_register_dai()` also called
  `dai->driver->probe(dai)` once per DAI
  (`oc-test/sound/soc/soc-core.c:1439`).
* `snd_soc_dai_ops.set_channel_map()` now takes
  `const unsigned int *tx_slot/rx_slot`:
  `sound/soc/msm/msm-dai-q6-v2.c:2722,9212,12038` and
  `sound/soc/msm/msm-dai-stub-v2.c:26-28` — matches
  `include/sound/soc-dai.h:304-306`. The implementations only *read* those
  arrays (port `:2758,2760,2796,2798,9290,9311,9382,9403,12068,12091`),
  so adding `const` is behaviour-preserving.
* `.digital_mute` -> `.mute_stream`:
  `sound/soc/msm/msm-dai-q6-v2.c:2815,2844` and `:12198,12226`. The 6.12
  signature is `int (*mute_stream)(struct snd_soc_dai *dai, int mute, int
  stream)` (`include/sound/soc-dai.h:320`) and the port's functions match
  that argument order; the core calls it with
  `dai->driver->ops->mute_stream(dai, mute, direction)`
  (`sound/soc/soc-dai.c:388`). The donor's `digital_mute(dai, mute)` had no
  direction, so the port's added `stream` parameter is the correct
  conversion. The port ignores `stream`, exactly as the donor ignored the
  direction.
* `rtd->cpu_dai` -> `snd_soc_rtd_to_cpu(rtd, 0)` and
  `rtd->codec_dai` -> `snd_soc_rtd_to_codec(rtd, 0)`:
  `sound/soc/msm/msm8952.c:1193,1352,1446,1520`,
  `sound/soc/msm/msm8952-slimbus.c:1865,1958,2096,2187,2343,2409`,
  `sound/soc/msm/msm-pcm-afe-v2.c:367,389,641`. Index 0 is the first
  CPU/codec DAI, which is what the 4.19 `rtd->cpu_dai`/`rtd->codec_dai`
  members pointed at.
* `rtd->dai_link->cpu_dai_name` -> `rtd->dai_link->cpus[0].dai_name`:
  `sound/soc/msm/msm-pcm-q6-v2.c:1467`,
  `sound/soc/msm/msm-pcm-q6-noirq.c:960`,
  `sound/soc/msm/msm-compress-q6-v2.c:1721,4357,4408,4460,4633,4689,
  4764`.
* `platform .remove` returning void: converted in
  `sound/soc/msm/msm_audio_ion.c:819`, `sound/soc/msm/msm-pcm-q6-v2.c:2925`,
  `sound/soc/msm/msm-pcm-q6-noirq.c:1444`,
  `sound/soc/msm/msm-pcm-voice-v2.c:834`,
  `sound/soc/msm/msm-pcm-loopback-v2.c:1521`,
  `sound/soc/msm/msm-pcm-routing-v2.c:31654`,
  `sound/soc/msm/msm-pcm-afe-v2.c:879`,
  `sound/soc/msm/msm-dai-stub-v2.c:276,313`,
  `sound/soc/msm/msm-dai-q6-v2.c:4695,6457,7109,7381,7418,7451,7555,7785,
  11909,12790,12827`, `sound/soc/msm/msm-dai-fe.c:2799`,
  `sound/soc/msm/msm-compress-q6-v2.c:5563`,
  `sound/soc/msm/msm8952.c:3579`, `sound/soc/msm/avtimer.c:581`,
  `sound/soc/msm/msm_mdf.c:618`. All correct — with the exception of
  finding 7, where the callback was dropped rather than converted.
* `class_create(THIS_MODULE, "avtimer")` -> `class_create("avtimer")`:
  `sound/soc/msm/avtimer.c:517` — correct for 6.12.
* `devm_ioremap_nocache()` -> `devm_ioremap()`:
  `sound/soc/msm/avtimer.c:487,495` — on arm64 `ioremap_nocache()` was an
  alias of `ioremap()`; behaviour preserved.
* `pm_qos_*` -> `cpu_latency_qos_*`:
  `sound/soc/msm/msm-pcm-hostless.c:25`,
  `sound/soc/msm/sdm660-cdc-irq.c:324,369,402`,
  `sound/soc/msm/wcd9xxx-irq.c:182,221` — matches
  `include/linux/pm_qos.h:149-153`; the request object is still
  `struct pm_qos_request` (`include/sound/pcm.h:479`).
* `regmap` `use_single_rw` -> `use_single_read` + `use_single_write`:
  `sound/soc/msm/wcd9xxx-core.c:72-73` — matches
  `include/linux/regmap.h:449-450`.
* `snd_soc_component_read32()` -> `snd_soc_component_read()`:
  `sound/soc/msm/msm-analog-cdc.c:233,248,465,503,507,578,623,625,627,
  629,631,816`,
  `sound/soc/msm/msm-digital-cdc.c:248,304,359,409,438,457,465,473,482,642`,
  `sound/soc/msm/msm-digital-cdc-legacy.c:291,347,400,450,479,498`,
  `sound/soc/msm/sdm660-cdc-irq.c:196`,
  `sound/soc/msm/wcd9335.c:1114,1119,1237,1315,1325,1602` — the 6.12
  helper returns `unsigned int`, the same width as the removed
  `read32()`.
* `strlcpy()` -> `strscpy()`:
  `sound/soc/msm/avtimer.c:223`,
  `sound/soc/msm/q6voice.c:770,963,967,971,975,979,983,987,1032,1087,1091,
  1095,1099,1103,1107,1111,1168,7678,10133`,
  `sound/soc/msm/msm-pcm-loopback-v2.c:234`,
  `sound/soc/msm/msm-pcm-routing-v2.c:3647,31256`,
  `sound/soc/msm/q6afe.c:8951,8980,9000,9073,11300` — the return value is
  unused at every one of these sites, and `strscpy()` NUL-terminates, so the
  only difference is that `strscpy()` does not zero the tail of the
  destination. No behavioural use of that in the port.
* `kzfree()` -> `kfree()`: `sound/soc/msm/rtac.c:2014,2027-2028,2045-2047,
  2052-2055,2067-2070` — **this is finding 8**, not a clean item: the
  donor's `kzfree()` zeroed the memory and 6.12's equivalent is
  `kfree_sensitive()`.

**Atomic context / sleeping callbacks**
* `sound/soc/msm/msm-pcm-q6-v2.c:2883` was the **only** `.delay` assignment
  in `sound/soc/msm` (verified with
  `grep -rn "\.delay\s*=" sound/soc/msm/`). All other ASoC hooks in the
  port (`open`, `close`, `prepare`, `hw_params`, `trigger`, `pointer`,
  `copy`, `ioctl`, `mmap`) are process-context calls in 6.12
  (`sound/soc/soc-pcm.c`, `sound/soc/soc-component.c`).
* The `.pointer` callbacks themselves are atomic-safe in the port:
  `sound/soc/msm/msm-pcm-q6-v2.c:1130-1140` (reads `prtd->pcm_irq_pos`
  only), `sound/soc/msm/msm-pcm-afe-v2.c:820-836`,
  `sound/soc/msm/msm-pcm-q6-noirq.c:551-584` (reads registers only).
  The DSP-side sleeps are in `event_handler()` but they are *not* in the
  pointer path (the `wait_event_timeout()` calls in
  `msm_pcm_playback_copy()` `:815` and `msm_pcm_capture_copy()` `:982` run
  from the ALSA write/read path, which is process context).

**Timers, timekeeping**
* `grep -rn "timer_list\|setup_timer\|init_timer\|mod_timer\|del_timer"
  sound/soc/msm/` finds exactly one hit,
  `sound/soc/msm/caf-include/soc/qcom/subsystem_restart.h:51`
  (`struct timer_list timer;`), which is a CAF header copied verbatim and
  is not used by the audio stack. No timer API conversion issue.
* `do_gettimeofday()` / `gettimeofday()`: no hits in `sound/soc/msm/`.
  `sound/soc/msm/avtimer.c:338-360` converted `struct timespec` +
  `getrawmonotonic()/get_monotonic_boottime()/ktime_get_ts()/ktime_get_real_ts()`
  to `struct timespec64` + `ktime_get_raw_ts64()/ktime_get_boottime_ts64()/
  ktime_get_ts64()/ktime_get_real_ts64()` — the 1:1 equivalents.
* `sound/soc/msm/q6asm.c:404-417` `get_monotonic_timeval()` ->
  `get_monotonic_timespec()` and the four `struct timeval` globals ->
  `struct timespec64` (`:267-270`): the printed values are still
  microseconds (`tv_nsec / 1000`), matching the donor's `tv_usec`.

**Cache maintenance for the DSP-written buffers**
* `sound/soc/msm/msm_audio_ion.c:642-680` `msm_audio_ion_cache_operations()`
  is byte-identical to the donor
  (`oc-test/techpack/audio/dsp/msm_audio_ion.c:641-679`) and still calls
  `dma_buf_begin_cpu_access()`/`dma_buf_end_cpu_access()` around the
  access. As in the donor, **no caller exists** in either tree
  (`grep -rn "msm_audio_ion_cache_operations" sound/soc/msm/` finds only
  the definition and the header), so the audio path relies on
  `dma_buf_begin_cpu_access()` in `msm_audio_ion_map_kernel()`
  (`sound/soc/msm/msm_audio_ion.c:241`) exactly as the donor did — no
  divergence introduced by the port.
* The donor's `techpack/video/msm/vidc/msm_smem.c` (the non-coherent-SMMU
  cache-maintenance code the task refers to) has **no counterpart in the
  port**: `find . -name "msm_smem*"` returns nothing, and the vidc_3x port
  is only *planned* (commit `eebbbf38e`). There is therefore nothing to
  compare in the audio tree; the vidc port must carry the donor's cache
  operations over. This is a gap to close when the vidc port starts, not
  a defect in the current tree.

---

## Working-tree state (as of the end of the audit)

`git log --oneline -3` at the end of the audit:

```
4698570a2 ASoC: msm: q6afe: copy the in-band payload through a byte pointer
fdfca326d ASoC: msm: pcm-q6: do not query the DSP for the path delay
eebbbf38e porting: plan the vidc_3x video port and the audio playback fixes
```

* `fdfca326d` — **implements the fix for finding 1**: it removes
  `msm_pcm_delay_blk()` and the `.delay = msm_pcm_delay_blk` assignment from
  `sound/soc/msm/msm-pcm-q6-v2.c`, restoring the donor's effective behaviour
  (runtime delay 0, no DSP query from the IRQ path). The commit's own
  comment describes the same reasoning as finding 1 above.
* `4698570a2` — replaces the flexible-array-member
  `memcpy(&x->param_data, ...)` in `sound/soc/msm/q6afe.c` with an
  offset-based copy to silence a FORTIFY "field-spanning write" diagnostic.
  Unrelated to this sweep; the change looks behaviour-preserving
  (`param_data` is the last member and the allocation reserves `sizeof(pl)`
  past the struct), but it was not reviewed in depth here.

Findings 2 through 8 are **not** addressed by these two commits.

---

## Summary table

| # | Severity | Location | Class |
|---|----------|----------|-------|
| 1 | DEADLOCK/ATOMIC-SLEEP | `sound/soc/msm/msm-pcm-q6-v2.c:2844,2883` | `.delay` callback sleeps in the IRQ-disabled pointer path — runtime-confirmed, **fixed by `fdfca326d`** |
| 2 | SILENT-BEHAVIOUR | `sound/soc/msm/msm-pcm-routing-v2.c:1268` | always-false test removed, `goto` kept -> function is a no-op |
| 3 | SILENT-BEHAVIOUR | `sound/soc/msm/msm-pcm-afe-v2.c:600,838,866` | `.copy`/`.ops` dropped -> AFE proxy path is dead code |
| 4 | UNSAFE | `sound/soc/msm/msm_audio_ion.c:117,165` | dma-buf reservation lock not held for map/unmap_attachment |
| 5 | DATA-CORRUPTION/UNSAFE | `sound/soc/msm/msm_mdf.c:367` | cache flush before `scm_call2()` removed |
| 6 | SILENT-BEHAVIOUR | `sound/soc/msm/q6afe.c:8948` | always-false NULL test replaced by a live one -> `-EINVAL` |
| 7 | SILENT-BEHAVIOUR | `sound/soc/msm/msm-dai-stub-v2.c:287,327` | platform `.remove` dropped instead of converted |
| 8 | SILENT-BEHAVIOUR (low) | `sound/soc/msm/rtac.c:2014,2027-2028,2045-2047,2052-2055,2067-2070` | `kzfree()` -> `kfree()` drops the donor's zeroing; 6.12 has `kfree_sensitive()` |
| 9 | OK-NOTE | `sound/soc/msm/q6asm.c:429`, `q6voice.c:2767,4464` | donor format bugs correctly fixed by the port |

No kernel source file was modified, and no build was run, for this audit.
