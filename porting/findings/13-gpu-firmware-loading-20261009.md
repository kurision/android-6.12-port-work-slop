# GPU firmware loading: stock 4.19 vs 6.12 (snapshot50 evidence, 2026-10-09)

## The blobs
Six files feed the Adreno 506 probe: `a530_pm4.fw` / `a530_pfp.fw`
(ringbuffer microcode), `a506_zap.mdt` + `.b00/.b01/.b02` (secure shader,
loaded via `qcom_mdt_load`). Harvested snapshot47 run4 via the diag
init's `fwblob` serial exfil; staged by `package-diag-boot.py
--firmware-dir` as `lib/firmware/qcom/*`.

## Stock 4.19 (verified live on 2819f2320604)
- Blobs live **flat** in `/vendor/firmware/` (18 files total: GPU six,
  `cpp_firmware_*`, `wlan/`, …). No `qcom/` subdir.
- Downstream driver requests **bare names** and probes **late**, after
  init mounts vendor — plain filesystem lookup finds them in place.
- ADSP/modem blobs are NOT there; they live on the modem partition
  (`/system/vendor/firmware_mnt`, vfat mmcblk0p1, shell-inaccessible).
  Backlog #2's payload.bin extraction plan stands.

## Upstream 6.12 (`drivers/gpu/drm/msm/adreno/adreno_gpu.c:445`)
`adreno_request_fw()` tries, in order:
1. `qcom/$fw` via `request_firmware_direct` — first deliberately, to
   avoid the usermode-helper timeout. Our ramdisk hits this:
   `loaded qcom/a530_pm4.fw from new location` (run1, t≈5 s).
2. Flat legacy name (`FW_LOCATION_LEGACY`) — stock-style flat staging
   would also work.
3. `request_firmware()` usermode helper — comment says *"I think mainly
   android"*. Dead on our build: no helper, 60 s timeout per blob.
The `qcom/` prefix follows the linux-firmware vendor-subdir reorg
(`MODULE_FIRMWARE("qcom/a530_pm4.fw")`, `a5xx_catalog.c:154`); stock's
downstream driver predates it.

## Why ramdisk staging for diag boots
Three compounding facts, all observed:
- Probe at ~5 s sees only the initramfs; vendor mounts at ~20–40 s.
- The kernel loader searches rootfs paths (`/lib/firmware/...`), never
  `/vendor/firmware` — waiting alone would not suffice.
- Flat-vs-`qcom/` prefix mismatch on top of the timing gap.
`fastboot boot` images must be self-contained, so the ramdisk carries
the blobs. Deferral (late sysfs re-bind post-mount) is possible but
needs path plumbing (copy+rename into a searched path on a read-only
fs, or `EXTRA_FIRMWARE_DIR` at vendor — fragile across mount timing).

## Product answer (not diag)
Bake the six blobs via `CONFIG_EXTRA_FIRMWARE` (tiny) or ship the
linux-firmware `qcom/` layout on system. No code changes needed.

## Side harvest (same listing)
`/vendor/firmware/wlan/prima/` (`WCNSS_qcom_wlan_nv.bin` et al.)
settled the WLAN question toward upstream `wcn36xx`, which references
that exact NV path (`wcn36xx.h:33`). See backlog #5.
