# Handoff — Mi A1 (tissot): ACK 6.18 port, session of 2026-10-04

> **Current state: porting/CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUILD_TISSOT.md](BUILD_TISSOT.md).

Read this first in a new session, then [project-mainline.md](project-mainline.md) for the full record.

## Where things are

| What | Where | State |
| --- | --- | --- |
| Repo, branch | `/home/kurision/development/kernel/kernel_xiaomi_msm8953`, branch `project-mainline` | based on `main` @ `7f57b3823629` (MGLRU merged) |
| Research doc | `docs/project-mainline.md` | committed once (`531cf5c373d7`), then extended **uncommitted** |
| This handoff | `docs/handoff-ack-mainline.md` | uncommitted |
| ROM's own CAF tree | `/home/kurision/development/kernel/kernel_xiaomi_tissot` | 4.19.325, full `techpack/` — the driver donor |
| ROM images | `/home/kurision/development/kernel/evox_images/{boot.img,system.img}` | read-only reference |
| Device backup | `/home/kurision/development/kernel/tissot_backup_20261003/` | `gpt_primary.bin`, `partitions.txt` |
| **ACK base** | `/home/kurision/development/kernel/ack-android17-6.18` | shallow clone, branch `android17-6.18`, HEAD `89b3cc162` (6.18.32) |
| ACK build output | `../ack-android17-6.18/out` | with `scripts/tissot-ack.config` merged: `Image.gz` 17,477,414 B, dtb 43,482 B, `Image.gz-dtb` 17,520,896 B |
| Fork, 6.18 line | `/home/kurision/development/kernel/msm8953-linux-6.18` | branch `barni2000/6.18/develop`, base 6.18.0, head `5b7b995f3738`, 14 tissot commits + `qcom-spmi-haptics.c` |
| Tooling (this repo) | `scripts/build-ack-tissot.sh`, `scripts/tissot-ack.config`, `scripts/ack-driver-audit.py` | uncommitted |

The 6.12 fork clone was deleted (11 GB); its content is reproducible from the fork's tags.

Nothing was flashed. The phone has not been touched this session.

## What was established (all re-verifiable from the transcript in `project-mainline.md`)

1. **ROM**: Evox 12.2 / Android 17 on the phone, but the kernel actually running is this repo's CAF 4.19 fork, not Evolution-X's tree.
2. **ROM ships zero kernel modules.** `/vendor_dlkm` holds only `etc`; no `lib/modules` anywhere. Every CAF driver is built into the kernel image, whose payload is `Linux version 4.19.325-cip136-st20-perf-g9d3bf7da9553`.
3. **Boot contract is friendly.** `boot.img`: page 2048, `kernel_size=17513396`, `ramdisk_size=16799333`, `dt_size=0`, cmdline `androidboot.hardware=qcom msm_rtb.filter=0x237 ehci-hcd.park=3 androidboot.bootdevice=7824900.sdhci loop.max_part=7 androidboot.boot_devices=soc/7824900.sdhci buildvariant=user`. The payload is `gzip(Image)` with a **raw 259,283-byte DTB appended after the gzip stream** (FDT v17, found at boot.img offset 17,256,161). No `dtb` partition; `boot_a`/`boot_b` A/B exist.
4. **No CAF kernel above 4.19 targets SDM625** — 591 branches in `kernel/msm`, zero SDM625-family hits. Newest CAF anywhere is 5.15, and **no CAF 6.x tree exists at all** (CodeLinaro has `msm`, `msm-5.4`, `msm-5.10`, `msm-5.15`). CAF ships techpacks as separate per-domain repos in 5.x, and no 5.x tree has `msm8953*` DTS.
5. **Base chosen: ACK `android17-6.18`.** It matches the ROM's Android 17, carries `msm8953.dtsi` + `msm8953-xiaomi-tissot.dts`, and builds. Plain mainline 6.12 also builds but lacks `vendor_hooks.h` and the GKI/Android surface; binder is not the discriminator (mainline ships it, just off under `defconfig`).
6. **Fork patches worth mining**: `msm8953-mainline/linux` `6.12/main` is only 11 commits (haptics, touchscreen reset GPIO, DTS). The real driver work is on `7.1.3/main` (~100 commits: camss, venus, s5k2xx, qcom-smbchg, pm8994-fg, `qcom-spmi-haptics.c`). The tissot **panel driver is not in the fork at all** — it is in `msm8953-mainline/linux-panel-drivers`, which is why `compatible = "xiaomi,tissot-panel"` has no driver in the 6.12 clone.
7. **With `scripts/tissot-ack.config` merged onto `gki_defconfig`, ACK drives the whole upstream tissot dts**: 100 device nodes, 97 have a driver, 65 compiled in, 0 genuinely missing (the 3 "unbound" rows are tool artefacts: the RPM message SRAM description and two TCSR nodes whose `syscon` fallback is no longer an `of_match` driver in 6.18). Before the fragment, the same audit found 7 compiled-in nodes and no eMMC/SPMI/regulators. Every real gap is in nodes upstream leaves `disabled`: `mdss`/`mdp5`, `gpu`, `wcnss`, `lpass`, CCI, cameras, sensors, fingerprint.
8. **`Image.gz-dtb` already matches the ROM's layout** — `scripts/build-ack-tissot.sh` produces it by `cat Image.gz <dtb>`, the same thing CAF 4.19 does via `CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE`. `mkbootimg` and `unpack_bootimg` are installed in `/usr/bin`; `magiskboot` is at `../AnyKernel3/tools/magiskboot`.

## Gotchas that will bite again

- **Use absolute paths or `make -C`.** A bare `make` ran in the wrong tree and wrote a stray `.config` into the 4.19 repo (removed; `out/.config` untouched). The bash tool's cwd persists between calls but an `cd` in one call silently changes it for the next.
- **Put the NDK on PATH in the same command** as the build: `export PATH="$HOME/Android/Sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/linux-x86_64/bin:$PATH"`. Kconfig needs `ld.lld` on PATH or `defconfig`/`olddefconfig` fails with `linker 'ld.lld' not found`.
- **Single-dtb targets need the directory**: `make ... qcom/msm8953-xiaomi-tissot.dtb`, not the bare name.
- **`Image.gz-dtb` does not exist on arm64 in 6.x.** `arch/arm64/boot/Makefile` only offers `Image.zst Image.xz image.fit`. Build `Image.gz` and append the dtb by hand — which is exactly what the stock ROM does.
- `CONFIG_ARCH_QCOM` is not set by a plain `defconfig` on some paths; check `grep CONFIG_ARCH_QCOM .config` before chasing a "no rule to make target" dtb error.
- **Put the NDK on PATH in the same command as the build** — Kconfig needs `ld.lld` or `defconfig`/`olddefconfig` fails with `linker 'ld.lld' not found`.
- **Fragments are merged with `scripts/kconfig/merge_config.sh -m -O <outdir> <outdir>/.config <fragment>`**, then `olddefconfig`. Copying a fragment over `.config` instead silently loses the `gki_defconfig` base.
- **Symbols that do not exist in ACK are dropped silently** by `olddefconfig`, and `merge_config.sh` only warns. Re-verify a fragment with `ack-driver-audit.py` rather than trusting `make` output.
- **Single-dtb build targets need the directory**: `make ... qcom/msm8953-xiaomi-tissot.dtb`.

## Next session, in order

1. **Mine `barni2000/6.18/develop`** (no flash): 14 tissot commits, `qcom-spmi-haptics.c`, `remoteproc: qcom_q6v5_mss` PAS setup, `wcn36xx` fixes. Clone `msm8953-mainline/linux-panel-drivers` for the panel driver no tree contains.
2. **Port the fork's tissot dts onto ACK 6.18 and re-audit** — enabling `gpu`, `mdss`, `wcnss`, `lpass`, CCI in the device dts turns the audit into the real port backlog, node by node.
3. **First boot attempt (needs explicit approval)**: repack `boot.img` with `out/arch/arm64/boot/Image.gz-dtb`, the original ramdisk and the original cmdline, flash `boot_b`. Then `fastboot getvar current-slot`, `adb devices`, UART if available. The goal is the first failure message, not a boot.
4. **Then the CAF drivers** in risk order: camera, KGSL, display/MDP5, WLAN, audio/PIL, radio/IPA, then fingerprint, ALS, haptics, keypad backlight.
5. **Fallback**: CAF 4.19 + feature backports (EEVDF is the big one).

## Rules for the next session

- Nothing is flashed without an explicit go-ahead, and `boot_b` first so `boot_a` keeps the working ROM.
- Verify claims against source; cite file/branch/commit. `android.googlesource.com/kernel/common` `android17-6.18` is the ACK baseline; `76efa001ea197723c0423fdb9136e83b483f7aa1` on `android14-5.15` remains the pinned donor reference from AGENTS.md; `../kernel_xiaomi_tissot` (Evolution-X, 4.19.325) is the CAF donor for this work.
- `docs/project-mainline.md` is the living record — append to its Milestone log as things land rather than starting a new file.