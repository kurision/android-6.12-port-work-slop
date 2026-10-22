# The Media9 routing failure and the low-latency prepare failure are one bug: the PCM device numbers

**Evidence:** `porting/artifacts/snapshot60/run342-bootloop-20261022-000001/`
(kernel #54, the failure), `porting/artifacts/snapshot60/run343-audio-boot/`
(the same failure on the image with the two plan fixes), the ROM's own
configuration (`/vendor/etc/mixer_paths_mtp.xml`), the donor's machine
driver (`../oc-test/techpack/audio/asoc/msm8952.c`) and the port's
(`sound/soc/msm/msm8952.c`).

## The two symptoms

```
MSM8x16 Media9: ASoC: no backend DAIs enabled for MSM8x16 Media9, possibly missing ALSA mixer-based routing or UCM profile
q6asm_callback: cmd = 0x10bcd returned error = 0x1
msm_pcm_chmap_ctl_put: substream ref_count:0 invalid
```
and, in the ROM's audio HAL:
```
audio_hw_primary: pcm_open_prepare_helper: pcm_prepare returned -1
```

The first is upstream ASoC's DPCM complaining that the front end it is
preparing has no back end; the second is the HAL's reaction to the
`SNDRV_PCM_PREPARE` ioctl failing with `-EINVAL` (the DPCM code returns
`-EINVAL` for a front end without a back end,
`sound/soc/soc-pcm.c:2593`). They are the same failure, and the
"ASM_STREAM_CMD_CLOSE rejected" and "chmap ref_count:0" lines are its
consequences: the stream never opened, and the HAL closed it anyway.

## The cause: the port's PCM device numbers are not the donor's

The vendor HAL does not open the front end by name; it opens the PCM
device **by number**, and the number is a property of the kernel's dai
link table. The ROM's mixer path for the low latency usecase names the
front end it wants:

```xml
<!-- /vendor/etc/mixer_paths_mtp.xml:380 -->
<path name="low-latency-playback speaker">
    <ctl name="QUIN_MI2S_RX Audio Mixer MultiMedia5" value="1" />
</path>
```

So the low latency front end is **MultiMedia5**, and the mixer control the
HAL writes is the one for MultiMedia5.

The donor's dai link table puts MultiMedia5 at PCM device number **12**
(`../oc-test/techpack/audio/asoc/msm8952.c`, the links in order: 0
MultiMedia1, 1 MultiMedia2, 2 CS-Voice, 3 VoIP, 4 ULL, 5 Primary MI2S_RX
Hostless, 6 INT_FM Hostless, 7 AFE-PROXY RX, 8 AFE-PROXY TX, 9 Compress1,
10 AUXPCM Hostless, 11 Tertiary MI2S_TX Hostless, **12 MultiMedia5**, 13
Voice2, 14 MultiMedia9, ...).

The port's table had dropped the donor's VoIP (3) and Compress1 (9)
links, so every device after them moved down by two: MultiMedia5 was at
number **10** and MultiMedia9 - the link the port calls "MSM8x16 Media9"
- was at number **12**.

The HAL therefore opened number 12, which on the port is the Media9
front end, and then wrote the mixer control for MultiMedia5. The Media9
front end has no route to any back end (the donor's routing table has no
`{"QUIN_MI2S_RX Audio Mixer", "MultiMedia9", "MM_DL9"}` either, and the
donor does not need one because its front end to back end selection is
not DAPM path based), so ASoC found no back end for it:

```
MSM8x16 Media9: ASoC: no backend DAIs enabled for MSM8x16 Media9
```

The run342 logcat shows the HAL creating exactly the track that does
this, a fast track from system_server:

```
10-22 00:00:52.855   730  1342 I AF::AfPlaybackCommon: creating track with enforcement level 0 reason PRIVILEGED_APP shouldHarden 1
10-22 00:00:52.861  1180  5046 I AudioTrack: createTrack_l(0): AUDIO_OUTPUT_FLAG_FAST successful; frameCount 0 -> 969
10-22 00:00:52.926   691  5060 E audio_hw_primary: pcm_open_prepare_helper: pcm_prepare returned -1
```

and the kernel's answer, three lines later in the same boot, is the
Media9 error above.

## The fix

Restore the donor's dai link order, so that the PCM device numbers are
the donor's. The port already had the donor's order for everything
except the fourteen links it had dropped; they are added back at the
donor's positions, with the platforms the port has:

| device | donor's link | platform in the port |
|---|---|---|
| 3 | MSM VoIP (cpu `VoIP`) | `msm-pcm-dsp.0` (the donor's `msm-voip-dsp` is not built here) |
| 9 | MSM8952 Compress1 (cpu `MultiMedia4`) | `msm-pcm-dsp-noirq` (the donor's `msm-compress-dsp` is not built here) |
| 19-23 | Listen 1..5 Audio Service (cpu `LSM1`..`LSM5`) | `msm-pcm-dsp-noirq` (the donor's `msm-lsm-client` is not built here) |
| 24 | MSM8X16 Compress2 (cpu `MultiMedia7`) | `msm-pcm-dsp-noirq` |
| 28-32 | MSM8X16 Compress4..8 (cpu `MultiMedia11`..`MultiMedia15`) | `msm-pcm-dsp-noirq` |
| 38-40 | MSM8X16 Compress10..12 (cpu `MultiMedia17`..`MultiMedia19`) | `msm-pcm-dsp-noirq` |

The port's own "MSM8X16 Compress9" link already used the same trick
(the donor's Compress9 is the one compress link the donor builds as a
plain PCM, on `msm-pcm-dsp-noirq`).

After the change the two tables have the same 41 devices in the same
order, so every device number the vendor HAL uses is the donor's:

```
0 MultiMedia1        12 MultiMedia5       25 Quaternary MI2S_RX Hostless
1 MultiMedia2        13 Voice2            26 Senary_mi2s Capture
2 CS-Voice           14 MultiMedia9       27 MultiMedia10
3 VoIP               15 VoLTE             28..32 Compress4..8
4 ULL                16 VoWLAN            33 Compress9
5 Primary MI2S_RX    17 INT_HFP_BT        34 VoiceMMode1
6 INT_FM Hostless    18 MultiMedia6       35 VoiceMMode2
7 AFE-PROXY RX       19..23 Listen 1..5   36 MultiMedia8
8 AFE-PROXY TX       24 Compress2         37 QCHAT
9 Compress1          10 AUXPCM Hostless   38..40 Compress10..12
                     11 Tertiary MI2S_TX Hostless
```

The front ends themselves are unchanged: the links only carry the
platform that creates their PCM, and the platforms the port does not
build are replaced by the one it does, the way the port's own Compress9
link already does it.

## Not fixed here: the register read on the routing component

Every stream start logs one error:

```
msm-pcm-routing soc@0:msm-pcm-routing: ASoC: error at soc_component_read_no_lock on soc@0:msm-pcm-routing for register: [0x00000000] -5
```

The routing component has no regmap, so any register read on it fails
with `-EIO` (`sound/soc/soc-component.c:736`). The read comes from a
mixer control that is register based (`snd_soc_get_enum_double()` in
`sound/soc/soc-ops.c:67`), and the control's register is 0 because
`MSM_FRONTEND_DAI_MULTIMEDIA1` is 0
(`sound/soc/msm/msm-pcm-routing-v2.h:245`). The donor's routing
component has no regmap either, so the donor would fail the same read;
which control is read at that moment has not been established yet. It
does not stop the playback, but it is an error in the log and it is open.
