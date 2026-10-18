# run186 results

Image `boot-run186.img` sha256 `649ca6ad09a120e45854a529a60b9cbdec0c395df7a6ed1dddc0b0c28b7f0e36`,
kernel payload `42b3691a76b2cc42787819c0e33cd55074fd23ba69685215c5882cff9bc35bc9`.
Base `boot-run185.img`; ramdisk/init/cmdline byte-identical to run185. Only the kernel differs.

Build: `/tmp/ack-run164-source` -> `out-run164`, `run186-build.log`. Stale pre-edit log kept as
`run186-build-pre.log`.

## Verdict: the boot failure is a BUILD defect, not the SMMU change

`/dev/ashmem` is missing, so SystemServer crash-loops and `sys.boot_completed` never gets set.

- `kdir-run186/Image.gz` does **not** contain the string `Using Rust implementation`;
  `kdir-run185/Image.gz` does. ashmem was not compiled in.
- `out-run164/.config` has no `CONFIG_ASHMEM`, no `CONFIG_RUST`, no `CONFIG_RUST_IS_AVAILABLE`.
- `out-run164/.config.old` (the pre-build state) had all three, plus `rustc 1.99.0` / LLVM 23.01.
- `out-run164/.config` mtime is 2026-10-17 09:45:54 — rewritten by the run186 build.
- `bindgen` is absent on this host and the local rustc reports LLVM 22.01.8, so
  `make rustavailable` fails; kconfig then drops RUST and ASHMEM even though
  `scripts/tissot-ack.config` requests `CONFIG_ASHMEM=y`.

Cause: the run186 build was a bare incremental `make Image.gz`, which re-ran syncconfig
without the `rustavailable` guard that `scripts/build-ack-tissot.sh` performs. That script
would have aborted before touching the phone. run185's config came from a host with
rustc 1.99.0 + bindgen.

## The SMMU change itself did what it was meant to

From `run186-usb.log`:

    1c48000 (GPU):     ias=39 aarch64=1 tcr=00802019 tcr2=00038012 sctlr=000010e7
    1e20000 (display): ias=32 aarch64=0 tcr=80802020 tcr2=00038062 sctlr=000000e7

GPU bank on the AArch64/39-bit walk, display bank untouched on 2-level. The gating worked.

## run185's 3-level regression did NOT recur

Counted over the recovered logdump (`run186-logdump.log`, 818,197 B) and the USB capture:

| signature | run186 | run185 |
|---|---|---|
| `CP initialization failed to idle` | 0 | 0 |
| `no suitable EGLConfig` | 0 | 0 |
| SMMU translation fault (`FSR` TF) | 0 | first TF seen |
| `GPU fault` | 4 | 0 in capture window |

**Not a clean A/B**: with ashmem gone, SurfaceFlinger cannot allocate buffers, so the GPU
path is being exercised differently than on run185. Do not credit the SMMU change yet.

The 4 faults are the known CP-stall signature, not a new fault class:

    surfaceflinger[721]: gpu fault ctx 2 ctx_type GL status 800001C1 rb 0100/0209 rb sw r/w
    ... (x4, t=42.79-42.99 s) then: gpu fault threshold exceeded 3 faults in 3000 msecs

`status 0x800001C1` = `GPU_BUSY_IGN_AHB + CP_BUSY + GPMU_MASTER_BUSY + HI_BUSY` with
`CP_ME_BUSY` clear — the RBBM_STATUS decode already recorded in HANDOFF.

## Live evidence (the manual boot, boot_id 3d7719a3)

- `logcat-all.log`, 17,814 lines. SurfaceFlinger alive with 5,609 lines — it gets an EGL
  config this time; it fails at present with `NO_RESOURCES (6)`, not at config choice.
- SystemServer crash loop, repeated:
  `java.lang.RuntimeException: Failed to create ashmem: No such file or directory`
  at `ApplicationSharedMemory.create` (SystemServer.java:1004).
- `adsprpcd` crash loop: `remote_handle_open failed for adsp_default_listener (errno
  Inappropriate ioctl for device)`. Kernel side: `qcom,fastrpc ... no reserved DMA memory
  for FASTRPC` (also present in run185 — not a run186 regression).
- `sys.boot_completed` never set; `init.svc.bootanim` = `running` at 75 s.

## Device-side artifacts

- `/data/anr`: 60 files, newest 2026-10-09 15:05. **None from today.**
- `/data/tombstones`: newest tombstone_31.pb, 2026-10-09. **None from today.**
- `/data/system/dropbox`: empty.
- `find /data -maxdepth 3 -newermt "2026-10-17 06:00"` returned **0** files. The port boots
  left no ANR, tombstone or dropbox artifact on the device.

## Stale message now incorrect

    (NULL device *): KGSL_MMU_64BIT withheld: GPU SMMU aperture is 32-bit

The GPU aperture is now 39-bit (`ias=39`), so this withholding is no longer justified.
Whether KGSL should be given 64-bit VA is untested.

## Booting observed

Three port-kernel boots were seen, only one captured:

| boot_id | how | kernel log |
|---|---|---|
| `329f9cc8` | `fastboot-boot-capture.py`, automated | 422,382 B / 3,269 lines, cutoff at t=41.0 s |
| `5b2c7215` | — | none |
| `3d7719a3` | manual | none; logcat only, recovered via logdump |

The two unlogged boots mean the USB capture is not a reliable sample of "a run186 boot".
Device returned to stock 4.19 (`339a33cb`), `sys.boot_completed=1`, nothing flashed.

## Recovered pstore

`pull-run-evidence.sh` reported `raw success: 67108864 bytes; readable prefix: 818197 bytes`.

- slot0 seq=37 ts=76890126845, slot1 seq=38 ts=78943232313 — both header-and-payload CRC32 verified.
- periodic printk tails seq=37/38, both CRC verified.
- No dmesg crash record and no panic/oops record recovered. Per the tool this does not prove
  no crash occurred.
- `SD unavailable/error: 0 bytes` — the diag SD mirror produced nothing this run.
- Slot content starts mid-boot at t=34.13 s and ends at t=78.58 s.
- `diag marks boot_id=0x115526e5`, which matches none of the three boot_ids observed above.
  Slot-to-boot attribution is **unverified**.

## Files

    run186-usb.log                                  422,382 B automated capture
    run186-usb-capture.status                       reader-error (adbd handoff), 422,382 bytes, 44.9 s
    run186-logdump.bin / .log                       67,108,864 / 818,197 B
    run186-ramoops.json                             recovery report
    run186-ramoops-slot{0,1}-seq{37,38}-*.log        524,276 B each, CRC verified
    run186-printk-tail-slot{0,1}-seq{37,38}-*.log    ~126,900 B each, CRC verified
    run186-live/logcat-all.log                      17,814 lines
    run186-live/boot-state.log                      uname/boot_id/uptime/boot props
    run186-live/device-anr-tombstones.txt           /data/anr + /data/tombstones listing
    run186-live/tombstones-and-today.txt            su listing + today-filtered find
    run186-live/device-dropbox.txt                  empty dropbox
    run186-live/data-recent.txt                     today-filtered find under /data
    run186-build.log, run186-build-pre.log          build logs
    package-run186.json, kdir-run186/, boot-run186.img