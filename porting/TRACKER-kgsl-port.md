# Tracker: kgsl 4.19 -> 6.12 port (tissot)

Goal: restore `/dev/kgsl-3d0` with the stock ioctl ABI so the vendor EGL
(`libGLESv2_adreno.so`, 2020 QC blob), sdm HWC and gralloc work unchanged
— the "GPU 3D" row of `porting/FAILING-COMPONENTS.md` (backlog #1).

Worktree: `../ack-kgsl`, branch `kgsl-port` (from `driver-fix` a1e4992dc).
The main tree stays untouched until this port has a boot verdict.
Last update: 2026-10-13 — Stage 3 in progress; run89 returned before observed port ADB but preserved real early Android logcat; reset cause, panel PLL and GPU start remain unresolved.

## Status key (same as FAILING-COMPONENTS.md)
FIXING · BLOCKED · SCOPED · PARKED · WATCH · CLOSED

## Source of truth (verified 2026-10-10; do not re-derive)
| Fact | Evidence |
|---|---|
| donor | `kernel_xiaomi_msm8953/drivers/gpu/msm` — 90 files / 74,471 lines |
| uapi to preserve verbatim | `.../include/uapi/linux/msm_kgsl.h` — 1,884 lines, 62 `IOCTL_KGSL_*` |
| ABI drift check | CAF `graphics-kernel` `GRAPHICS.LA.14.0.r7-01700-lanai.0` header diffed vs donor: additive only (new flags/props/structs/ioctls; no existing struct layout or ioctl-number change) |
| ION | built in since `a33336265`; `CONFIG_ION=y` (`arch/arm64/configs/tissot_gki.fragment:8`) |
| zap SCM | `include/linux/firmware/qcom/qcom_scm.h:75,79` (`pas_init_image`, `pas_auth_and_reset`) |
| zap fw | diag ramdisk stages `lib/firmware/qcom/a506_zap.mdt` (findings/13); kgsl requests the **flat** name `a506_zap.mdt` (donor `adreno_a5xx.c` zapfw) — staging layout decision needed |
| kgsl DT binding | donor `adreno.c:923` = `qcom,kgsl-3d0` |
| DRM binding displaced | `adreno_device.c:283-291` dt_match (incl. kgsl-3d0 back-compat) + component table `msm_drv.c:1022-1027` |
| DT pwrlevels | donor reads OPP-v2 first (`adreno.c:989-990`), legacy `qcom,gpu-pwrlevels` second (`adreno.c:1108`) — the existing `operating-points-v2 = <&gpu_opp_table>` (5 OPPs, `msm8953.dtsi`) is reusable |
| icc | `drivers/interconnect/qcom/msm8953.c:1304-1307` — bimc/pcnoc/snoc/snoc-mm, **no gpu master** |

## Adjacent references (checked; none is a donor)
- `msm8953-mainline/linux` `6.12/main`–`6.19/develop` and LineageOS
  `android_device_xiaomi_mi89xx-mainline` `lineage-23.0` (Android 16): the
  mainline path, no kgsl. Keep as patch source if display/GPU ever moves
  to mainline (dwc3-gadget reverts for 6.13–6.16, dm-table reverts 6.15,
  wcnss PIL reversions).
- CAF `graphics-kernel` LA.14.0 tag: sync already dma_fence (48 refs; only
  `msm_hw_fence_destroy` to stub), `adreno.c` on icc.
- `qualcomm-linux/kgsl` `gfx-kernel.le.0.0` (meta-qcom): has A506
  (`ADRENO_REV_A506 = 506`) but still the private qcom IOMMU context API —
  modern-anatomy reference only.

## Churn inventory (counted; supersedes BACKLOG #1's 4–8 week estimate)
| Item | Files | Work | Status |
|---|---|---|---|
| sync framework -> dma_fence | kgsl_sync.c | 3 legacy sites (`sync_fence_create` x2, `timeline_create` x1) -> `sync_file_create()`; `kgsl_timeline.c` already dma_fence-based | SCOPED |
| msm_bus -> icc | adreno.c, adreno_snapshot.c, kgsl.c, kgsl_gmu.c, kgsl_pwrctrl.c + 2 headers | `of_icc_get`/`icc_set_bw`; add `mas_gpu` to msm8953 icc or fixed-vote stub | SCOPED |
| iommu shims | kgsl_iommu.c | `iommu_fault_block` x2, `iommu_addr_in_svm_ranges` x2 | SCOPED |
| build glue | drivers/gpu/{Kconfig,Makefile}, fragment | `QCOM_KGSL` + `QCOM_KGSL_IOMMU` + `CORESIGHT_ADRENO`, `=y` | SCOPED |
| misc API delta | at compile | iterate, log per error | SCOPED |

## Stages
- [x] 0. Tracker + worktree `kgsl-port` created
- [x] 1. DT glue: kgsl exclusive, DTB compiles — booted 2026-10-10, PASS (display safe with no GPU component)
- [x] 2. Vendor driver + kernel links — **done 2026-10-10** (see Stage 2 log):
      90-file donor compiles clean under clang 22.1.8, vmlinux links with
      kgsl built in, audit shows the gpu node BUILT. No boot claimed.
- [ ] 3. Boot #1 diag capture: kgsl probes, pwrlevels parse, `/dev/kgsl-3d0`,
      display + evidence channels intact
- [ ] 4. EGL/SF unlock (`EGL_BAD_ALLOC` gone)
- [ ] 5. Parity (render, suspend/resume, gpu cooling) + close FAILING-COMPONENTS rows

## Stage 1 log
- Exclusive binding: board override `&gpu { compatible = "qcom,kgsl-3d0",
  "qcom,adreno-506.0"; status = "okay"; }` in
  `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts` (drops the
  `qcom,adreno` fallback so DRM's dt_match stops claiming the node; SoC
  dtsi untouched, daisy/mido/vince boards unaffected).
- Removed `{ .compatible = "qcom,kgsl-3d0" }` from
  `drivers/gpu/drm/msm/adreno/adreno_device.c` (dt_match) **and**
  `drivers/gpu/drm/msm/msm_drv.c` (component table). The component one is
  the load-bearing edit: with the node present msm_drm waits forever for a
  GPU component that never binds, and display would die with the port.
- Verified: `make qcom/msm8953-xiaomi-tissot.dtb` builds; decompiled node
  shows the new compatible; zero `kgsl-3d0` matches left in drm/msm.
- KMS binding with no GPU component: verified in the Stage 1 boot verdict below.
- Not yet verified (needs a boot): flat-vs-`qcom/` firmware staging;
  the msm_bus/icc replacement.

## Stage 1 boot verdict (2026-10-10, PASS)
- Booted `porting/artifacts/snapshot59/boot-run1.img` via `fastboot boot`
  (serial 2819f2320604); logdump pre-cleared and readback verified zero.
- Durable log `run1-logdump.log` (37,847 B, both ramoops slots valid;
  `run1-sd.log` byte-identical):
  - `msm_mdp 1a01000.display-controller: bound 1a94000.dsi (ops dsi_ops)`
    — **KMS binds with no GPU component**, the Stage 1 hypothesis
    (`msm_drv.c:325-326` `priv->gpu == NULL` path) holds.
  - `panel-otm1911 …: panel status 0x9c (downstream expects 0x9c)` —
    display unaffected.
  - No kgsl/adreno probe lines: the GPU node is claimed by nobody, which
    is exactly the designed state until Stage 2 vendors the driver.
  - 0 × Oops/panic/WARNING/BUG/Call trace; `clk-rcg2` WARN count 0
    (same as snapshot58 run1 — the `CLK_OPS_PARENT_ENABLE` fix holds).
  - Evidence channels all live: SD capture, USB capture, ramoops sampler;
    diag init handed PID 1 to Android init successfully.
- The RAM-only boot then fell back to the installed 4.19 ROM
  (`uname_r=4.19.325-cip136-st20-perf-mglru-next-…`, `boot_completed=1`)
  — expected for `fastboot boot` after the diag window.
- Verdict: **Stage 1 CLOSED** — exclusivity change is display-safe.
  Committed as `f3248eda0` + `904b29167` on `kgsl-port`.

## Stage 2 log (2026-10-10, CLOSED for link; boot is Stage 3)
**False start, root cause**: the handoff's compile claim was unproven — the
driver had never been compiled in this worktree. `out/.config` was a stale
**Linux/x86 6.12.93, gcc** config (14:49; last arm64 build predated
vendoring), so `drivers/gpu/msm` was Kconfig-invisible and `make` reported
nothing to do. Reset `out/` and regenerated via
`ACK_TREE=$PWD JOBS=12 ./scripts/build-ack-tissot.sh`
(the handoff's `build-ack-tissol.sh` is a typo; the real script defaults
`ACK_TREE` to the unported `../ack-android16-6.12`, so `ACK_TREE=$PWD` is
required). Both traps fixed in `porting/HANDOFF-kgsl-port.md`.

**Config gate** (`out/.config`, final five lines): `CONFIG_ARCH_QCOM=y`
(gki_defconfig:62) + `CONFIG_NVMEM_QCOM_QFPROM=y`, `CONFIG_ARM_SMMU=y`,
`CONFIG_QCOM_KGSL=y`, `CONFIG_QCOM_KGSL_IOMMU=y` (tissot-ack.config final
four lines).

**Compile/link evidence**:
- `scripts/build-ack-tissot.sh` exit 0; `out/vmlinux` (245,062,992 B).
- 47 driver objects built; 48 `.c` sources minus `adreno_coresight.c`
  (resolves n — `CORESIGHT_ADRENO` off; documented harmless, `adreno_coresight.o`
  simply not compiled). `make -n drivers/gpu/msm/` = Nothing to be done.
- Build string: `6.12.93-4k-g83b44102f24e-dirty (clang version 22.1.8,
  LLD 22.1.8)` — toolchain is the system clang 22 (`scripts/build-ack-tissot.sh:21`
  `llvm_bin=/usr/bin`, `CC="ccache clang"` at :24); NDK path is no longer the default.
- Driver entry symbols in vmlinux: `kgsl_3d_init` (adreno.c:4219
  `module_init`) and `kgsl_core_init` (kgsl.c:5615). **There is no
  `kgsl_init` symbol in this driver** — the Stage-2 wording/handoff name
  is wrong; the linked proof is those two symbols:
  `nm out/vmlinux | grep -wE 'kgsl_3d_init|kgsl_core_init'`.
- `out/arch/arm64/boot/Image.gz-dtb` = 19,221,571 B,
  sha256 `eb5bd012e2d345c400ef8751687ced633a1fc907bdc55ef96ada791e5e0082ea`.
- Audit (`scripts/ack-driver-audit.py --dtb ... --tree . --config out/.config`):
  `BUILT   okay   /soc@0/gpu@1c00000   CONFIG_QCOM_KGSL   drivers/gpu/msm/adreno.c`
  — of_match `qcom,kgsl-3d0` (adreno.c:923) via tissot override
  (msm8953-xiaomi-tissot.dts:459-462). `--only-unbound` lists only the 4
  pre-existing no-driver nodes (rpm-msg-ram, tcsr ×2, ion) — gpu absent.
  Summary line: `98 device nodes: 94 have a driver (84 compiled in), 4 have none`.

**Port adaptations (driver-private, all under `drivers/gpu/msm/`; uapi
`msm_kgsl.h` untouched)**:
- `kgsl_pool.c`: `kern_addr_valid`→`virt_addr_valid` (removed generic),
  `NR_UNRECLAIMABLE_PAGES`→`NR_SLAB_UNRECLAIMABLE_B` (6.12 vmstat is
  byte-scaled), `totalram_pages` var→fn, static shrinker→allocated
  (`shrinker_alloc`/`shrinker_register`/`shrinker_free`).
- `adreno_dispatch.c`: `strlcpy`→`strscpy`, kobj `default_attrs`→
  `default_groups`, `__mutex_owner` re-entrancy guard dropped (6.12 keeps
  it kernel-internal; idle-timeout WARN remains the backstop).
- `kgsl_reclaim.c`: `pagevec`→`folio_batch` (`check_move_unevictable_pages`
  deleted upstream), `reclaim_address_space`→`reclaim_shmem_address_space`,
  `proc_reclaim_notifier_*` shimmed inert (a506 never sets
  ADRENO_PROCESS_RECLAIM; a6xx-only).
- `kgsl_iommu.c` + `gmu-iommu-compat.h`: 6.12 deleted the entire vendor
  iommu domain-attr API. Live path now uses the sanctioned adreno-smmu
  private interface (`include/linux/adreno-smmu-priv.h`): cb_num=0
  (qcom_adreno_smmu_alloc_context_bank) and ttbr0/contextidr via
  `get_fault_info()`; `adreno_smmu` priv is published on the platform
  device before attach (adreno.c:1481). Inert paths (secure/per-process
  pagetables, gpuhtw LLC) fail loudly via `-ENODEV` wrappers.
  `iommu_map`/`iommu_map_sg` gained the gfp arg (`GFP_ATOMIC`).
- `adreno_a6xx.c`/`adreno_a5xx.c`/`adreno_a3xx.c`: `<linux/clk/qcom.h>` and
  `<soc/qcom/subsystem_restart.h>` gone — new `adreno-zap-compat.h`
  (zap loader inert on a506: mmu->secured false), clk-flag + DDR-query
  shims in `adreno.h` (a3xx/a540/a512/a508/a509/a650-only paths).
- `msm-bus-compat.c`: wired into `drivers/gpu/msm/Makefile` (was in the
  tree but never added — link would fail); prop-index port to
  `of_property_read_u32_index`.
- Duplicate-symbol link errors vs in-tree drm/msm renamed into the kgsl
  namespace: `adreno_idle`→`kgsl_adreno_idle`, `a6xx_gmu_sptprac_is_on`→
  `kgsl_a6xx_gmu_sptprac_is_on`.
- `scripts/ack-driver-audit.py`: `symbol_table` now resolves composite
  Makefiles (`foo-y += bar.o` + `obj-$(CONFIG_X) += foo.o`), so kgsl and
  drm/msm objects report their real CONFIG symbol instead of `?`
  (coverage went 77→84 compiled-in; audit output was under-reporting).

**Environment warning**: any direct `make O=out ...` without the script's
env (`ARCH=arm64 LLVM=1 LLVM_IAS=1`) re-syncs kconfig for host arch and
silently destroys the merged config — observed once, fixed by re-running
the script. The script always regenerates the config first.

## Stage 3 log (2026-10-10, IN PROGRESS — kgsl boot #1 fault isolation)
Recorded run tags span `snapshot60/run2..run36`; evidence per tag in
`porting/artifacts/snapshot60/`. Full channel map + reasoning:
`porting/REFERENCE-boot-testing.md`.

| Run | Kernel | Result | Evidence |
|---|---|---|---|
| run2 | kgsl (NDK-era cfg reset) | DIES pre-userspace: reset to stock, empty logdump slots, 0-byte ACM | `run2-logdump.bin` 64 MiB, slots invalid |
| run3 | CONTROL: run1 known-good image | PASS | slots seq 173/174 valid (DBGC), 37,471 B SD |
| run4 | kgsl + `--keep-stock-console` | DIES (same as run2) | slots invalid |
| run5 | kgsl + kgsl-iommu DT glue + `late_initcall(kgsl_3d_init)` | DIES | slots invalid |
| run6 | CONTROL: same tree, `QCOM_KGSL=n` | PASS | slots seq 168/169 valid, 38,573 B SD log |
| run7 | kgsl + ramoops read-back + earlycon/`console=ttyMSM0` | user observed stuck at fastboot splash; kernel start unproven | pending |
| run8 | CONTROL re-boot (no-kgsl) to read ramoops | PASS; ACM 27,741 B; pstore read window missed (adb timeout) | `run8-usb.log` 27,741 B |
| run9 | kgsl + `late_initcall` on BOTH kgsl initcalls | DIES, empty slots; initcall panic not excluded (finding 3) | `run9-logdump.log` 0 B |
| run10 | CONTROL: run6 kernel + 378,677 zero-byte DTB pad (19,221,987 B) | **PASS** — size exonerated (29,215 B SD, slots 165/166) | `run10-sd.log` |
| run11 | CONTROL (mislabelled): its log carries `#1 Sat Oct 10 21:24:39` — the same build as the run6/run10/run14 `QCOM_KGSL=n` kernels — and contains zero `kgsl` lines | diag reached first-stage init (422 B ACM); SD 37,107 B | `run11-sd.log`, `run11-usb.log` |
| run12 | CONTROL re-boot (run10 image) | PASS; read window for ramoops missed | `run12-usb.log` |
| run13 | kgsl + direct CB reg reads + `qcom,global_pt` + review NULL guard | DIES, empty slots (pre-P0-fix kernel) | `run13-usb.log` 0 B |
| run14 | CONTROL: no-kgsl rebuilt on current DT (glue + stdout-path) | **PASS** — DT exonerated (slots 170/171, 37,025 B SD) | `run14-sd.log` |
| run15 | kgsl + P0 NULL-pdev fallback + P1 sg-map sign fix | DIES, empty slots | `run15-logdump.log` 0 B |
| run16 | CONTROL re-boot (run10 image) to read the record | PASS; **38,131 B ACM** — kernel log reached userspace; `sys.boot_completed=running` via adb after boot | `run16-usb.log`, `run16-sd.log` |
| run17 | run15 image re-boot (P0 fix) | reset to stock before adb window; 0-byte ACM | `run17-usb.log` 0 B |
| run25 | bus table + `interrupt-names`; the boot shipped a **stale** `kdir` (payload identical to run24), so only `init` + cmdline differed | DIED at the fastboot splash; unattributable, wasted cycle | `run25-logdump.log` 39,572 B |
| run26 | first boot with the donor `qcom,msm-bus,*` bus table | `-22` gone (`kgsl_pwrctrl_init` passes); now fails `-6` at `kgsl_request_irq` — names the real next site | `run26-usb.log` 39,843 B |
| run27 | kernel #11, which adds `interrupt-names = "kgsl_3d0_irq"` | **kgsl binds** — no `probe with driver failed`; `/dev/kgsl-3d0` opened by userspace (`kgsl_open` traces). Probe at `t=14.4 s` | `run27-usb.log` 42,447 B, `run27-sd.log` |
| run29 | + `init`: denial loop stopped, `dump_log` survives denied kmsg reads | **full boot** — capture 3,071,879 B / 26,605 lines to `t=932 s`, clean `DIAG: EOF`. Probe at `t=4.56 s` (was 14.4 s: the SELinux denial loop cost ~10 s, not the console) | `run29-sd.log`, `run29-logdump.log` |
| run31/32 | — | not booted: run numbers 30-33 already used by an earlier session | — |
| run34 | + msm-bus handle fix, regulator fix, iommu clock rename | **DIES ~60 s, zero evidence** — diag init never wrote anything | `run34-usb.log` 0 B |
| run35 | same, iommu clock rename reverted | **PASS** — 300 s+ Android. `GPU BW scaling failure` 0, `regulator 'vdd' disable timed out` 0, `supply vdd not found` 0, probe failures 0 | `run35-sd.log` 39,695 B, `run35-logdump.log` |
| run36 | run35 + iommu rename again, with `of_dma_configure` guarded | **DIES again** — confirms the rename, not the DMA call, is fatal | `run36-usb.log` 0 B |

**Findings (each backed by a run):**
1. Control boot (run6): identical tree, clang 22, ccache, config reset, DT glue —
   everything except `CONFIG_QCOM_KGSL=y` — **boots clean**. The vendored driver
   is the fault; environment/toolchain are exonerated.
2. **run10 (size A/B) exonerates size**: the *same* run6 control kernel, with only
   378,677 zero bytes appended to the DTB so `Image.gz-dtb` = 19,221,987 B
   (byte-identical to our kgsl images' size), **BOOTS FINE** — valid DBGC slots
   (seq 165/166), 29,215 B SD log, `DIAG: Android init exec succeeded`.
   Working boots: 18,843,310 B, 18,872,873 B, and 19,221,987 B (run10).
   **The discriminator is the kgsl driver, not size.**
3. **Invalidated — do not reuse.** The old claim "kgsl initcalls exonerated,
   empty logdump means no panic" rested on `pstore_blk` being the recording
   backend. It is not: `pstore_blk: failed to resolve 'PARTLABEL=logdump'!`
   then `failed to open ...: -2!` fires in every log (run24 log line 290,
   `t=2.756 s`), because the eMMC only appears ~1.2 s after `pstore_blk`'s
   probe. The backend that survives is the level-2 ramoops node
   (0x86800000, `msm8953-xiaomi-tissot.dts:118`), whose snapshotter is ready
   at `t=5.06 s` (`run24-usb.log:422`). Any death before that leaves no
   record at all, and the level ordering argument cannot be used to
   exonerate any initcall. The four `pstore_blk.*` cmdline tokens are dropped
   from run25: they never worked on this kernel and cost the console choice.
   The separate UDC-handoff capture cutoff is finding 3a.
4. **0-byte ACM capture ≠ failed boot** — run3/run6/run8/run10 all produced
   0-byte ACM but booted fine (adbd handoff ends the CDC-ACM stream).
   Truth = logdump slots + SD-log freshness (`pull-run-evidence.sh` prints
   `SD success: common extent matches` on success; `SD unverified` with stale
   byte counts means the diag userspace never ran).
5. **P0 NULL-pdev deref (subagent review)** — the kgsl-iommu node nested under
   `&gpu` (compatible matches no OF bus) never gets a platform device, so
   `of_find_device_by_node` returns NULL in both `_kgsl_iommu_probe` and
   `_kgsl_iommu_cb_probe`; the first `devm_clk_get(&pdev->dev)` / `ctx->dev =
   &pdev->dev` oopses in probe on every boot — invisible (oops at level 7,
   `pstore_blk` unresolved, `console=ttynull`) = the observed silent reset.
   Fixed in the run15/run17 kernel: fall back to `&device->pdev->dev` (same
   `iommus=<&gpu_iommu 0>` stream id). Still dies at run17, so the probe has
   at least one more fatal path. P1 also fixed: `iommu_map_sg` negative
   errno wrapped to success via `size_t mapped`; now `ssize_t` + `<= 0`.
6. **UDC-handoff capture cutoff (tooling, not kgsl)** — the diag init's
   `guard_usb_handoff` (`scripts/initramfs-diag/init.c:777-818`) unbinds the
   ACM function at the vendor stack's configfs switch, so `write_all(out,…)`
   fails; `write_capture` returned -1, which ended `dump_log` for **both**
   sinks. Control boots cut off identically (run16: 491 lines, last
   `seq=433, t=23.6 s`), so this was a capture defect masquerading as a
   boot defect. Fixed by making the sinks independent — a dead primary is
   retired (marked `-1`) while the SD mirror keeps running to the 900 s
   `dump_log` deadline — and by the new
   `sink_retirement_selftest` in `init.c`.
7. The stock 4.19's pstore ramoops is a **different region** (`0x91400000`,
   `su -c ls /sys/fs/pstore` works) than the port's (`0x86800000`), and its
   `/dev/mem` is absent — so reading our panic record needs a control boot
   with the same DT, pulled before that boot's own shutdown overwrites it.
8. DT glue the vendored driver always needed (donor
   `msm8953-gpu.dtsi`, `kgsl_msm_iommu`): `qcom,kgsl-smmu-v2` child under
   `&gpu` with `gfx3d_user` `qcom,smmu-kgsl-cb` + `iommus=<&gpu_iommu 0>` —
   added in Stage 3 (tissot dts:459-484). `kgsl_iommu_probe` returned
   -ENODEV without it.
9. pyserial for `usb-boot-capture.py`: `/tmp/diagvenv` (the system python has
   no `pip`; recreate with `uv venv` + `uv pip install`).
10. **`kgsl_get_bus_scale_table()` returned NULL** (run25 named it):
    `kgsl_pwrctrl_init` bails with `-EINVAL` on its *first* statement
    (`kgsl_pwrctrl.c:2267-2269`) when no bus table is found. The 6.12 tissot
    DT had neither a `qcom,gpu-bus-table*` child nor the donor's
    `qcom,msm-bus,*` properties on `&gpu`, so all three lookups failed.
    Fixed by porting the donor's 11-case table onto `&gpu`
    (`msm8953-gpu.dtsi:135-149`), which is exactly what the vendored
    `msm-bus-compat.c` shim parses. Verified: run26 no longer reports `-22`.
11. **msm-bus compat handle was decoded wrongly.** The vendor client handle is
    a 1-based slot index (`msm_bus_arb_adhoc.c` `gen_handle()` /
    `update_request_adhoc()` → `handle_list.cl_list[cl]`), but the shim's
    `msm_bus_scale_client_update_request()` treated it as a tagged pointer
    (`cl & ~1UL`). For the common `cl == 1` that yields NULL, so **every** GPU
    bandwidth vote returned `-EINVAL` ("GPU BW scaling failure: -22", thousands
    of times in run29). Fixed to index `clients[cl - 1]`; run35: 0 occurrences.
    The return value is ignored by its only caller, so this fix is otherwise
    inert.
12. **No discrete GPU rail exists on 6.12** — the gpu node has only
    `power-domains = <&gcc OXILI_GX_GDSC>` and the stock live DT has no
    `vdd-supply` on it either, so `devm_regulator_get(dev, "vdd")` returned the
    dummy regulator, which always reports itself enabled. `_regulator_disable()`
    then polled for its full 5 s timeout and logged "regulator 'vdd' disable
    timed out" on every GPU power-down. Fixed by not requesting a supply the DT
    does not describe (`get_legacy_regulators()`), which leaves `reg` NULL so
    the existing `IS_ERR_OR_NULL` guards short-circuit. run35: 0 occurrences.
13. **Do NOT rename the kgsl-iommu `clock-names`.** They resolve against the
    *gpu* device (no platform device exists for the node), so they legitimately
    do not resolve; `_kgsl_iommu_probe` returns `-ENODEV` there and, being a
    separate platform driver, that is non-fatal — the GPU binds and
    `/dev/kgsl-3d0` opens. Making the probe succeed instead (run34, run36)
    kills the phone ~60 s in, before the diag init writes anything, twice.
    Guarding the suspicious `of_dma_configure(ctx->dev, node, true)` call did
    **not** help (run36), so the fault is in the untested code past that early
    return — `of_platform_populate()` over the CB children, most likely. That
    needs its own evidence; do not retry it on a guess.
14. **Every image packaged from `snapshot59/base.img` silently loses adb.**
    The diag init needs `/ack-protected-fstab.qcom` and
    `/ack-vendor-file-contexts` in the ramdisk; without them
    `install_android_guard()` never runs, so `guard_usb_handoff()` never hands
    the UDC to adb and adbd can never come online. `snapshot59/base.img` does
    **not** carry them (verified by decompressing its ramdisk), and
    `package-diag-boot.py` does not stage them. Runs 20-25+ all show
    `DIAG: bootdevice guard inputs unavailable; alias not released`.
    Use `scripts/stage-guard-inputs.py` first, or package from
    `snapshot60/base-guard.img`, which carries both files. run39 does this and
    the log shows `guard installed ... fstab and vendor contexts before policy
    load`, `canonical alias and legacy wait path ready`, and
    `USB handoff rc appended ... errno=0`.
    **adb on 6.12 already worked** — see commit `fa37accb3` ("adb works on
    6.12": host enumerated `18d1:4ee7` with adb reporting `device`) and
    `f630f7c07`/`86cf5e369`, which also record the `+CONFIG_QRTR`,
    `+CONFIG_QRTR_SMD`, `-CONFIG_USB_FUNCTIONFS(_ETH)` requirement. The current
    `.config` satisfies that (QRTR=y, QRTR_SMD=y, QCOM_PD_MAPPER=y,
    USB_FUNCTIONFS absent). A missing guard in the base is a *packaging* gap,
    not a kernel defect — do not read "no adb" as a driver bug.

**Next:** the kgsl probe now **succeeds** (run27/run35/run37/run38/run39) and
the GPU is driven from userspace. Four driver bugs are fixed and verified by
absence — findings 10-12 plus the `qcom,highest-bank-bit` port (run38: the
`highest-bank-bit property is invalid` WARN is gone). Remaining:

- **The kmsg capture truncates**, and by differing amounts: run29
  (`run29-sd.log`) reached 932 s, run35 (`run35-sd.log`) 24.9 s, run39
  (`run39-logdump.log`) 19.2 s. The capture now idles to its deadline instead
  of aborting, but has no records left to write, and the *cause* of the lost
  read is not established — do not attribute it to SELinux enforcement or to
  fd lifetime without a cited denial line. This is what blocks any claim that
  no runtime GPU bug exists after ~30 s.
- **run39 has the guard inputs** (finding 14) and arms the USB handoff, but its
  capture ends at 19.2 s — before adbd would start — so the handoff completing
  is not yet confirmed. Re-check once the capture truncation is understood.
- **`of_platform_populate()` in `_kgsl_iommu_probe`** (finding 13), which needs
  its own evidence before it is touched again.


## Run40: policy-bearing package and fresh QSEE evidence (2026-10-12)

- Built the current tree with `build-ack-tissot.sh` (clang/LLD 22.1.8):
  `6.12.93-4k-g83b44102f24e-dirty`, `CONFIG_QCOM_KGSL=y`,
  `CONFIG_QCOM_KGSL_IOMMU=y`. Stock `msm_kgsl.h` still compares byte-identical
  against the donor. No QSEE/SCM, KGSL, clock-name or policy edits in this run.
- Packaged from the real `snapshot60/base-guard-debug-fw.img` (SHA256
  `c08cf6b24ae5517b65ad0a6d50fb23b198bab90c706e4f5f983d7ac69cda49c7`)
  and `init-run32`; all 664 non-init cpio records remained identical, including
  both guard inputs, `force_debuggable` and the 3,304,475-byte debug policy.
  `package-run40.json` records image SHA256
  `69b20f3d7302a31cab2e2a99f393afc3cd5128c239d8705254fd7732b1617beb`
  and freshly built Image.gz+DTB payload SHA256
  `e6a1ca4f45b5f4f07cb2fb37540076c7b95a9f0f9b82373eba4bf817631432b6`.
- Preceding logdump matched the already archived run39 binary; preclear
  verified 64 MiB zero readback (`run40-preclear.status`). `fastboot boot`
  succeeded; no flash or slot change. USB captured 472,292 bytes before
  disconnect, not a boot-failure verdict (`run40-usb-capture.status`).
- **6.12 adb and QSEE startup are observed.** Timeline lines 54–124 contain
  port identity observations (host elapsed 212–489 s).
  `run40-live1-logcat.log:139–154` records QISL activation and daemon running;
  `run40-usb.log:1717` records listener-readiness completion.
  The formerly stuck 1,164-byte keymaster request is sent at
  `run40-usb.log:1844–1846` and returns at line 1859 (~7.6 ms).
  PID 352 remains alive in `run40-live3-ps.log:266`.
  Registration fallback `32000206 -> -5`, then `32000201 -> 0`
  (`run40-usb.log:1629–1638`) matches run31, not a new QSEE failure.
  No reproduced QSEE startup failure; this does not prove every secure operation.
- **The reproduced graphics boundary is vendor composer, not QSEE.**
  `run40-usb.log:3335,3568` records composer SIGSEGV at 112.8/120.6 s,
  followed by SurfaceFlinger/zygote restarts. Live tombstones locate the null
  fault at `sdm::HWInfoDRM::GetHWResourceInfo()+208` in `libsdmcore.so`
  (`run40-live1-logcat.log:1127–1153,2026–2052`).
  Run33 has the same PC and library BuildId (`run33-logcat.log:237,283`).
  The missing/incompatible DRM resource contract remains **unverified**;
  no driver patch follows from the stack alone.
- Durable pull on the port failed (no `su`; scratch
  `/tmp/ack-evidence-e77r1jkc`). After return to installed 4.19, the existing
  pull tool saved 67,108,864 bytes, SHA256
  `f58048b1c6125f9cb3660a4ebe7a64a58fd965320a9dfee8b2d91b3e66b71dc2`.
  The 1,758,891-byte SD log matches the raw prefix; raw readable prefix is
  1,759,037 bytes and reaches 456.249 s (`run40-logdump.log:15261`).
  Both snapshot headers are valid but their DBGC rings are empty.
  `run40-logdump.log:14344,14559–14566` shows explicit `reboot,shell` and
  orderly shutdown, not evidence of a spontaneous QSEE reset.
- All three live logcat/process/property snapshots were collected. `dmesg`
  was denied in each; empty QSEE/readiness properties are not stopped-service
  evidence. `sys.boot_completed` was empty in these snapshots; boot completion
  is not established. The temporary host collector was stopped after the user
  reported the run done and 4.19 fallback was observed (~670 s, before its
  900 s maximum); no permanent collector was added.

**Next after run40:** investigate the composer DRM resource contract using
the captured tombstones and donor/AOSP display sources. The corrected real
ramdisk package restores evidence beyond run39's 19.2 s cutoff and confirms
6.12 adb; it does not establish why the guard-only run39 capture ended.
Retain the separate KGSL audit findings; do not bundle secure-memory, bus-vote,
or IOMMU-probe changes into this diagnostic result.

## MDSS Phase 1: compile+link gate (2026-10-13, no boot)

- Root cause (run40): stock `libsdmcore.so` selects its fbdev backend only if
  `/sys/devices/virtual/graphics/fb0/mdp/caps` exists (verified
  `GetDriverType` disassembly reads that path); on 6.12 the file is absent,
  the DRM backend is taken, and `HWInfoDRM::GetHWResourceInfo()+208`
  (`run40-live1-logcat.log:1147`) dereferences a null DRM-manager handle
  (`_ZN3sdm9HWInfoDRMC2Ev` never fills it on mainline MDP5). Same PC/library
  BuildId as run33 (`run33-logcat.log:237`). Fix direction per
  `porting/PLAN-mdss-display-port.md`: restore the real MDSS fbdev interface.
- Imported the tissot-needed donor subset into `drivers/video/fbdev/msm`
  (47 `.c`, headers, 3 UAPI headers byte-identical) and wired
  `drivers/video/fbdev/msm/{Kconfig,Makefile}` behind
  `CONFIG_FB=y,CONFIG_FB_MSM=y,CONFIG_FB_MSM_MDSS=y`
  (`scripts/tissot-ack.config`). `CONFIG_DRM_MSM` stays on and no DT nodes
  exist yet, so nothing binds: this build behaves like run40 plus inert code.
- Full `build-ack-tissot.sh` link passes (Image.gz 19,725,217 B);
  `nm out/vmlinux` shows `mdss_fb_init`, `mdss_mdp_probe`, `mdss_dsi_probe`;
  `CONFIG_QCOM_KGSL=y/CONFIG_QCOM_KGSL_IOMMU=y` retained. Not boot-tested:
  no boot cycle spent on an image with no new bound driver.
- Port decisions (all evidence-backed, no fake caps/stubs/bypasses):
  secure display/camera enable returns `-EOPNOTSUPP` before side effects
  (`mdss_mdp_secure_session_ctrl`); DMA lifetime owned by dma-buf attachment
  with contiguous-span validation (`mdss_smmu_map_dma_buf_v2`); splash
  early-map retired, splash disabled first cutover; 32-bit compat deferred
  (no 32-bit client identified, plan Q5); PMI/PWM backlight paths fail loudly
  (tissot uses WLED); `tracing_mark_write` renamed (collides with drm/msm
  DPU event); `linear_map` made static (collides with dm-linear).
- Genuine donor bug fixed on the way: `mdss_dsi_get_panel_cfg` copied
  `sizeof(arg_cfg)` (257) into caller `char[256]` buffers; fortify proved it
  after inlining. Bound is now `MDSS_MAX_PANEL_LEN`.
- Shared headers promoted for MDSS+KGSL: `include/linux/msm-bus.h`
  (+`update_context`), `include/linux/msm-bus-board.h`,
  `include/dt-bindings/msm/msm-bus-ids.h`, `include/linux/clk/qcom.h`
  (adreno.h now reuses it), `include/soc/qcom/event_timer.h` (feature off,
  honest no-op stubs), `include/media/msm_media_info.h`,
  `include/linux/display_state.h`, `include/video/{msm_dba.h,msm_hdmi_modes.h}`,
  `include/linux/msm_ext_display.h`, `include/xiaomi-msm8953/mach.h`
  (tissot-only). Optional core `fb_open_file/fb_release_file/fb_ioctl_file/
  fb_compat_ioctl_file` callbacks added (`include/linux/fb.h`,
  `drivers/video/fbdev/core/fb_chrdev.c`); legacy drivers unaffected.
- Next: Phase 2 cutover (8953 PLL CCF conversion, DT ownership swap with
  `power-domains = <&gcc MDSS_GDSC>`, PMI8950 LAB/IBB provider, splash
  quiesce before DMA attach). Port tasks for DSI/PLL/bias were delegated
  but the workers hit a usage limit and returned nothing; their research
  handoffs (`agent://MdssMemoryMap`, `agent://MdssClockDt`) are retained and
  already applied (DMA ownership, clock map, DT closure). No boot until the
  cutover binds hardware.

## Run41: cutover first light (2026-10-13, kernel #20 + DT overlay)

- First image with MDSS+PLL+DT bound: `boot-run41.img` SHA256
  `e6d878b4bac6cef3056ce788d4e1c60684068eb33ba54af00e826c53d4abe4d3`
  (package-run41.json:4-5; payload SHA256
  `e8677d4498c3ee432f2e49b7a51d8fe9bb5b7bc595f377faa7cb801e177a7cd9`,
  rebuilt #20).
  USB captured 469,822 bytes then adbd-handoff disconnect (expected).
- PLL provider probes and registers both PLLs
  (`run41-usb.log:214,217` "Registered DSI PLL ndx=0/1 clocks").
- MDP probe still fails `-12` on `unable to get MDSS irq`
  (`run41-usb.log:204,210`); DSI parent correctly defers forever
  (`mdss_dsi_probe: MDP not probed yet!`); system still reaches userspace
  with QSEE listeners + keymaster OK, 6.12 adb at ~212 s.
- Lesson used later: an MDP probe FAILURE is survivable (system boots
  degraded, composer SIGSEGVs as in run40). Only a hang/panic before diag
  init (~35 s) loses the boot.

## Run42/44/45: silent deaths + hybrid isolation (2026-10-13)

- `boot-run42.img` (kernel #21+, same DT plus mainline disables and
  `qcom,mdss-pref-prim-intf`): fastboot OKAY, then zero USB bytes, zero
  ramoops slots, stale SD, 4.19 fallback at ~72 s. Same for the
  `clk_ignore_unused pd_ignore_unused` variant (run45).
- Hybrid isolation (no rebuilds, offline repackaging only):
  run43 = kernel41 + DT42 boots to 6.12 adb; run44 = kernel42 + DT41
  falls back silent. DT innocent (also verified by decompiled-DTB diff:
  only intended disables/removals/additions). Killer is in kernel42's
  driver delta.
- `boot-run42.img` vs `boot-run41.img` are byte-identical sizes
  (37,969,920); payload hashes chain cleanly
  (img = kdir = out/ = `cee37da7...`). Gzip integrity verified.
  Not an image-mechanics failure.
- Evidence model correction: partition slots only update when diag init
  runs (the "logdump snapshotter"); zeros after preclear prove death
  before ~35 s, NOT before first printk. The 4.19 fallback then stomps
  0x86800000 (unreserved in 4.19), destroying any ramoops the dead
  session wrote. Pre-diag panics are therefore unrecoverable
  post-fallback; catch them only via pstore_blk revival or by keeping
  the failure past diag init.

## Run46/47 bisection + hard hang (2026-10-13, phone stuck)

- Reverted run42's six driver changes in two halves on branch
  `mdss-bisect` (WIP `e1bc5fab6`, bisect `db5ddd4a4`): first half
  (PLL handoff claim, DSI/rotator holds) still silent (run46);
  full revert of all six also reverts to run41-equivalent behavior and
  `boot-run47.img` reached 6.12 adb at ~170 s.
- Run47 then wedged hard 5+ min later: adbd up but `adb shell` hangs,
  `adb reboot` times out, USB stays enumerated (no re-enumeration, so no
  reboot cycle). Host USB reset unavailable (permission). Requires
  physical recovery (10 s power hold). A 30-min post-mortem adb watch
  (bg_20) is armed in case the PMIC watchdog fires.
- The wedge is new information: run41 stayed usable 250 s+ on nearly the
  same kernel. Delta run47-vs-run41 is essentially DT42 (mainline
  disables, pref-prim, labibb/pinctrl additions). Suspect the LABIBB
  SPMI path or a deferred-probe + regulator interaction; NOT proven.
- Resume plan once the phone answers: (1) pull run47 logdump/SD/USB
  (stale content expected; still check); (2) re-apply the six reverts'
  inverses one at a time ONLY if run47 proves stable — otherwise treat
  the wedge as the next blocker and read its logs first; (3) revive
  pstore_blk (fs/pstore/blk.c retry after eMMC appears) so future
  pre-diag panics persist to eMMC; (4) then continue MDP bring-up
  (the `platform_get_irq` -EPROBE_DEFER form, which unblocks the probe
  past the IRQ step into untested territory).

## Run48-65: MDP silent-death bisection (2026-10-13, cause unverified)

- Re-applying only the 4-hunk `mdss_mdp.c` change (modern
  `platform_get_irq` + defer-tolerant logging + splash-balance) on the
  otherwise fully-reverted tree restores the silent death (run48,
  fallback ~55 s, zero evidence). 13-run pattern is unanimous.
- Checkpoint bisection path (bail = `rc=-ENOMEM; goto probe_done`):
  run50 bail-after-IRQ boots; run51 after misc-IRQ boots; run52 after
  `debug_init` dies; run53 before `splash(true)` boots; run54 after
  `hw_rev_init` dies; run55 between `splash` and `hw_rev` dies;
  run56 (skip `clk_ctrl`+bus in splash) boots; run57 (clocks on) dies;
  run59 (all enables skipped) dies; run60 (also skip `pm_get_sync`)
  dies; run61 (vote+spinlock only) dies; run62 (also skip
  `idle_pc_restore`) boots.
- Bisection implicates the clock-on / idle-restore path, but the silent
  failures do not distinguish a bus hang, panic, or watchdog reset.
  Power/clock readiness is an unverified hypothesis, not a proved cause.
  `clk_ignore_unused pd_ignore_unused` did not make run63 succeed.
- Skipping `idle_pc_restore` is diagnostic only: DT still enables idle
  power collapse, and removing the restore also removes control-state
  recovery and clearing of `idle_pc` / `mem_retain`. Runtime resume is
  unverified. The full probe with the skip (run64) also failed later.
- Infrastructure: retries run at 6 s x 8, but still pass literal
  `PARTLABEL=logdump` to `filp_open`; run73 reports errno -2 throughout.
  Attachment and panic persistence are not proved. The synthetic panic
  marker would set the zone backend's `on_panic` without a `panic_write`.
  Dropping `oops=panic` does not establish that the silent failure is a hang.
- Run47-repeat and run51 notes: healthy boots die later from ORDERLY
  userspace reboots (`vold-failed` at 749 s, `apexd-failed` at 266 s)
  — a separate userspace-daemon class (vold/apexd never answer binder;
  adsprpcd restart storm + missing battery nodes in logcat). Next after
  MDP power.
- Tooling notes: `su` on 4.19 is `/product/bin/su` (bare `su` flakes
  with PATH); preclear needs 4.19 (no su on diag); always pull the
  logdump even on success (run53's was wiped by the next preclear).

## Run66-76: display probes, composer blocked on policy (2026-10-13)

- Delayed probing reads MDP `0x10100000` at 245 s (run66); DSI+PHY revs
  read at 64 s (run70). This demonstrates progress after delay, not a
  supplier-readiness dependency or the cause of the earlier failures.
- DSI `pre_clkon_cb` OOPS (`NULL+0x59`, run66 @247 s): empty
  `core-supply-entries` in DT leaves `vreg_config` NULL; guarded both
  directions in `msm_mdss_io_8974.c` (verified: no OOPS in run67+).
  DT completion (real `vdd` values) still needs donor numbers.
- fbcon `soft_cursor` OOPS on garbage `screen_base` (run70 @64.9 s):
  `CONFIG_FRAMEBUFFER_CONSOLE` off (Android never uses it).
- fb0 exists with plausible mode (1080x3840 virtual, 32bpp); MDP+DSI
  probe, panel parsed. `mm-pp-dpps` opens fb0 repeatedly (no failures).
- Composer (`hwcomposer-2-1`) restart-loops, never touches fb0:
  `SDM HWInfo::GetHWResourceInfo: .../fb0/mdp/caps not found` -> EINVAL.
  The file EXISTS; SELinux denies `hal_graphics_composer_default` read
  (`tcontext=sysfs`, generic label — DIAG base plat policy has no
  graphics genfscon; stock product policy presumably does).
- `enforcing=0` and `androidboot.selinux=permissive` both ignored (this
  init chain forces enforcing; our DIAG init does no SELinux setup
  before execing Android init). `selinux=0` untested (phone stuck in
  fastbootd, host fastboot unusable + adb unauthorized — needs hands).
- Permanent fix: product policy rule for the caps path (or equivalent);
  harness-only alternative is `setenforce 0` in DIAG init source
  (`snapshot26-init.c`, NDK available, rebuild flags unknown — risky).
  NEVER ship permissive; record here when done.
- Tooling: `su` is `/product/bin/su` (bare `su` flakes); DIAG `open_logdump`
  scans `/sys/class/block/*/uevent` for PARTNAME (works) while
  `/dev/block/*` needs ueventd (late) — pstore retry must use PARTLABEL
  (sysfs) or `/dev/mmcblk0p48` (devtmpfs), never `/dev/block/*`.

## Run77 plan: CIL policy delta for caps (packaged, untested 2026-10-13)

- `package-diag-boot.py` gains `--policy-append FILE` (appends to the
  ramdisk `userdebug_plat_sepolicy.cil`, records sha in the report;
  verified offline: rules land at the record tail, image repacks clean).
- `policy-mdss-caps.cil` (harness-only, NEVER ship): declares
  `sysfs_mdss_mdp_caps`, genfscons the exact denial path, allows
  `hal_graphics_composer_default` + `mm-pp-daemon` read (both scontexts
  verified verbatim from run73 AVC lines). Matches Sony/vendor
  convention (`sysfs_mdss_mdp_caps:file r_file_perms`).
- Source inspection identifies a possible debug-CIL load path; it does
  not prove selection or successful loading on the device.
- If the composer proceeds past caps, the product still needs the
  equivalent rule in its own policy — record it there, delete this delta.
- `enforcing=0` / `androidboot.selinux=permissive` both ignored by this
  init chain (our DIAG init does no SELinux setup before exec); `selinux=0`
  (run76) never booted — phone stuck in fastbootd first.
- Lineage init's `GetUserdebugPlatformPolicyFile` / `OpenSplitPolicy`
  select debug CIL conditionally; runtime selection remains unverified.
- run77 packaged with the run73 kernel and unchanged cmdline, but not
  boot-tested. Offline review subsequently proves its symlink-path
  genfscon leaves the real platform caps inode labeled generic sysfs.

## Run78: corrected caps mapping (offline verified; device boot failed)

- Run73 preserved AVC: `run73-logdump.bin` byte 495793 denies composer
  read of caps (`tcontext=sysfs`, enforcing); byte 616796 denies mm-pp.
- Run77 merged policy compiles, but actual genfs lookup of
  `/devices/platform/soc@0/1a00000.qcom,mdss_mdp/caps` returns sysfs.
  `fb0/mdp` is a symlink, not the inode path used by genfs labeling.
- Corrected delta reuses vendor `sysfs_graphics`, whose existing policy
  permits composer and mm-pp reads; no new types or allow rules.
  Merged with actual device vendor/system_ext/product/mapping inputs:
  secilc succeeds with init's `-N`; without it both baseline and delta
  report the same five pre-existing harness neverallow violations.
  Compiled genfs lookup now returns `u:object_r:sysfs_graphics:s0`.
  Evidence: `snapshot60/run78-policy-check.log`.
- `boot-run78.img` sha256
  `7df790910ba4f72584b88da32368a9ce48dcc653b0dfb83c9225510b1b175236`.
  Compared extracted records with run73: identical kernel/cmdline and
  all records except debug CIL. Package report cmdline field restored.
- Current stock logdump archived as `run78-stock-before-preclear.bin`;
  exact 67108864 bytes. `run78-preclear.status` proves readback all zero.
- Raw display marker writes overlap the ramoops header at 60 MiB
  (`fs/pstore/ram.c`); marker absence is not evidence of a splash failure.
  They remain in the unchanged run73 kernel for this single-variable
  policy boot and must be removed before another kernel cutover.
- Run78 returned to stock before any 6.12 adb response. Four-second
  collector: `run78-adb-timeline.log:12-117` has no device; line 120
  first records fallback 4.19. Composer behavior remains unverified.
- Debug policy selected / compiled (`run78-usb.log:859-861`), loaded
  (line 877), enforcing enabled (line 893). Last USB records show late
  MDP re-probe at 76.8 s (`:1356-1358`) and coldboot wait completing
  at 78.8 s. Durable text prefix ends at 69.6 s
  (`run78-logdump.log:1461`); SD matches the 198281-byte prefix.
  Two valid snapshot headers at 74.35 / 76.41 s have empty DBGC rings.
  No captured panic or reboot reason establishes why it returned stock.
- Next: boot the preserved run73 image as a new run79 control; do not
  reconstruct or change it. Only after the control can this failure be
  attributed to the policy delta versus the existing delayed-probe path.

## Run79: preserved run73 control (ADB reached; userspace still blocked)

- Booted the original `boot-run73.img`, no reconstruction; sha256
  `2d11fbc063a1c1515889c81039eabf189c8879824aa803373386f2c962bdce93`.
  `run79-preclear.status` proves zero readback before boot.
- MDP version read succeeds at 78.84 s (`run79-usb.log:1764`).
  Initial 240-second ADB collector saw no 6.12 response, but the late
  state capture at 247.93 s records 6.12 and enforcing
  (`run79-adb-late-state.log:1-3`). Boot completion remains unset.
  Do not treat a short no-ADB observation window as a failed boot.
- Composer caps denial reproduced (`run79-logcat-late.log:203`);
  caps open / display-core failure at lines 943-945. This control
  does not contain run78's policy delta.
- Crash triage in control logcat: composer PID 980 reports destroyed
  mutex FORTIFY at line 263; its service identity is recorded in
  `run79-logdump.log:5323`. Complete abort backtrace not captured.
  LiveDisplay aborts "Failed to initialize SDM backend" at lines
  322-344. dpmd aborts on different mmap size, stack through
  `ProcessState::init` / `init_child` at lines 281-306; same signature
  already exists in `run32-logcat.log:727`. These are userspace
  failures; no causal link to run78's early reset is established.
- Captured logcat before intentional reboot to stock for evidence
  retrieval. Raw 67108864 bytes, readable prefix 1429949 bytes;
  SD common extent matches 1429768 bytes, two valid snapshot slots.
  Run78 reset cause and corrected-policy composer behavior remain open.

## Run80: caps parsed; next blocker is bandwidth sysfs policy

- RAM-booted the unchanged `boot-run78.img` after run79's control.
  `run80-preclear.status` proves zero readback before boot. Extended
  collector observes 6.12 / enforcing through 459.46 s
  (`run80-adb-timeline.log:361-363`); boot completion remains unset.
- Composer parses caps successfully (`run80-logcat.log:1317-1323`):
  revision `0x10100000`, RGB=2 / VIG=1 / DMA=1 / Cursor=1,
  clock 400 MHz, bandwidth 3400000 KBps. This exercises the mapping.
- Next denial is `bw_mode_bitmap`, generic sysfs label, composer read
  (`run80-usb.log:3599`; `run80-logcat.log:194,1273-1278`).
  `GetDynamicBWLimits` then fails opening that file and propagates
  display-core error 11 (`run80-logcat.log:1325-1328`).
  [AOSP HWInfo reference](https://android.googlesource.com/platform/hardware/qcom/display/+/refs/heads/main/msm8996/sdm/libs/core/fb/hw_info.cpp)
  likewise reads dynamic BW only after parsing caps.
- Intentional reboot to stock for retrieval, not an observed spontaneous
  reset. Saved exact 67108864-byte raw logdump; 2271820-byte SD/common
  prefix matches; two valid snapshot slots at 533.75 / 535.80 s.

## Run81: bandwidth attribute mapping (ADB reached; recovery return)

- Add only the exact resolved `bw_mode_bitmap` path to the existing
  sysfs_graphics mappings. No new types/allow rules, no permissive mode.
  Failing-before compiled lookup returns generic sysfs; corrected lookup
  returns sysfs_graphics for both caps and bandwidth attribute.
  Merged compilation passes with init's flags; same five pre-existing
  neverallow violations without `-N`. Evidence: `run81-policy-check.log`.
- `boot-run81.img` sha256
  `853640cb9637f070374567cb252e9169c08360b45f6cfa9260ea6c1cffc0e17f`.
  Extracted-image comparison against run78: same kernel / cmdline / init
  and all other records; only debug CIL differs. BW parsing remains unverified.
- Before boot, archived the stock device's raw 67108864-byte logdump and
  logcat under `run81-preboot/`. `run81-preclear.status` proves zero
  readback. RAM-boot command succeeded; no flashing or kernel change.
- USB captured 345799 bytes, then disconnected
  (`run81-usb-capture.status`). PLL0 lock failure and HS clock enable
  `-22` occur at `run81-usb.log:2850-2858`; vsync poll timeout and
  frame timeout follow at lines 2918-2919. No causal reset verdict.
- ADB observed 6.12 / enforcing at uptime 207.08 through 239.38 s;
  boot completion remained unset (`run81-adb-timeline.log:185-220`).
  User observed return to stock recovery; no intentional reboot was
  issued after RAM-boot. Later ADB was unauthorized.
- Capture defect: collector deferred logcat until its nine-minute
  deadline instead of capturing during the live ADB window. Stopped it
  after the recovery report; no run81 Android logcat was saved.
- After the user returned the device to stock, root retrieval saved
  67108864 raw bytes; readable prefix 1176685 bytes. SD capture 1176627
  bytes matches the common extent; two valid DBGC snapshot slots at
  235.31 / 237.40 s. Final raw record is at 238.397 s
  (`run81-logdump.log:10231`); no explicit panic/reboot record was found.
- On-device audit proves caps and `bw_mode_bitmap` resolve to
  `sysfs_graphics` (`run81-logdump.log:8774-8775,9008-9009`).
  These are shell getattr denials, not composer read denials; label
  application is verified, successful composer BW parsing is not.

## Run82: unchanged run81 repeat (early return to stock; no port ADB)

- RAM-booted the exact `boot-run81.img`, SHA256
  `853640cb9637f070374567cb252e9169c08360b45f6cfa9260ea6c1cffc0e17f`.
  Archived preboot stock evidence in `run82-preboot/`;
  `run82-preclear.status` proves zero readback. No kernel/policy change.
- Continuous logcat collector was ready to stream on first 6.12 ADB
  response, but no port ADB window was observed. Stock 4.19 reappeared
  at host elapsed 148.17 s (`run82-adb-timeline.log:38`); user also
  reported the reset. No logcat segment was created.
- USB captured 191063 bytes (`run82-usb-capture.status`). Root retrieval
  saved 67108864 raw bytes and a matching 190821-byte raw/SD prefix.
  Valid DBGC slots at 67.12 / 69.17 s contain no later text than the
  raw prefix; last record at 66.726638 s is successful cleanup of
  `apexd-bootstrap` (`run82-logdump.log:1398-1402`).
- No explicit panic/reboot cause was found in the preserved port log.
  Stock boot reasons report `bootloader` (`run82-stock-state.log:3-4`);
  stock PMIC logs report PS_HOLD shutdown
  (`run82-stock-dmesg.log:322-326`). These do not identify the initiating
  port failure. Stock ramoops uses 0x91400000, not the port's region.
- Collector stop defect: it detected stock return only after seeing
  port ADB, so it kept waiting through this pre-ADB failure. Stopped
  after the user's report. Next collector must detect return to stock
  after transport loss even if port ADB never appeared.
- Composer BW parsing remains unverified. Do not attribute this earlier
  reset to the run81 PLL errors or infer a new policy failure.

## Run83: diagnostic image (abrupt reset at 153 s; no orderly reboot)

- Build host supplied `run83-from-build-host/boot-run83.img`, SHA256
  `3d7821e9e4fb0a2e6a8cf41391be89fb75eeff6a442dfe5c83b77bfce1e5b5c7`
  (kernel 6.12.93-4k-g25f51ef04013, clang 22.1.8). Verified before boot:
  header preserved except size/cmdline/id; cmdline is run81 plus
  `ramoops.reset_capture=1`; 665 ramdisk records with all non-init
  identical including sepolicy; DTB byte-identical to run81; kernel
  contains reset-capture markers, init contains the early-logcat
  service. Installed as `snapshot60/boot-run83.img` + `package-run83.json`.
  No policy delta, no debuggable flag, no firmware staging.
- Boot reached 153.46 s kernel time. surfaceflinger and zygote reached
  `running` (`run83-logdump.log:4397-4410`); hwcomposer pid 984 opened
  fb0 and retried interface starts. No composer `bw_mode_bitmap` or
  caps denial exists anywhere in the log: the run81 BW policy blocker
  did not recur as a denial. `max_brightness`/`gpu_model` generic-sysfs
  denials remain (10 composer denials). PLL0 lock failure, DSI clock
  `-22`, DSI cmd failures and frame timeouts persist.
- Reset capture was armed: 7 heartbeats to snapshot seq 70, valid DBGC
  slots at 151.19/153.24 s, raw+SD prefixes match (726366 bytes). No
  `ACKRESET1` record and no `DIAG: reset` line: the return was abrupt,
  not an orderly reboot or power-off. No panic, hung-task, RCU-stall
  or watchdog-bark signature in the preserved log.
- The log ends mid-warning-dump at 153.461 s, 3 ms after
  `gfx3d_clk_src: rcg didn't update its configuration` during
  `adreno_start` from `kgsl_worker_thr` (`run83-logdump.log:6336-6380`).
  KGSL was alive and reconfiguring GPU clocks when the reset hit. This
  timing is evidence of coincidence, not proof the GPU caused the reset.
- Early-logcat service started (pid 575), received SIGABRT at ~147 s,
  restarted (pid 1113). Its on-device file holds 299008 allocated zero
  bytes; all 20 tombstones likewise read back allocated zeros while
  sizes/mtimes persist. Stock-written files read back real content.
  Working hypothesis: port-boot file DATA stays in page cache and is
  lost on abrupt reset while journaled metadata persists; raw logdump
  block writes with explicit flush survive. Unproven; treat all
  port-boot /data file content as unreliable until a periodic-sync
  experiment proves otherwise.
- Next iteration is init-only (no kernel rebuild): the same kernel
  payload with an added `ack-sync-loop` service (`sync` every 5 s plus
  timestamp probe) so logcat/tombstone pages reach stable storage.
  `kdir-run83` was not handed back; reconstruct it by splitting the
  kernel payload at the DTB magic and re-hashing, or request it.


## Run84: sync-loop image (orderly reboot, reason vold-failed)

- Build host supplied a fully packaged `run84-from-build-host/boot-run84.img`
  plus matching `init-run84`. Verified before boot: report hashes match
  image bytes; header preserved except size/cmdline/id; cmdline is run81
  plus `ramoops.reset_capture=1`; 665 records, non-init identical
  including sepolicy; DTB byte-identical to run81/83; loose init matches
  packaged init and adds `ack-sync-loop`. Kernel rebuilt from the newer
  commit (version `gc0655a13e557`, same source for kernel code, same
  toolchain); payload differs from run83 only by build variation.
  Installed as `snapshot60/boot-run84.img` + `package-run84.json`.
- First `ACKRESET1` ever: `action=1 pid=1 comm=init command=vold-failed`
  at 203.519 s with a 64942-byte tail. Init performed a complete orderly
  shutdown (services SIGTERMed, /data cleanly unmounted, sync, `Reboot
  ending, jumping to kernel`). The return to stock was a deliberate
  init reboot, not a panic, hang or watchdog. Reset-capture mechanism
  works end-to-end.
- `vold.rc:10` sets `reboot_on_failure reboot,vold-failed`: vold (pid 326,
  alive at 144 s) vanished without any exit, crash, tombstone, OOM or
  denial trace in the complete primary kmsg. How vold died is still open;
  dpmd's SIGABRT tombstone (binder mmap size) is a confirmed red herring
  from an unrelated daemon.
- Display/composer story unchanged: SDM composer up, display id 0 at
  1080x1920, IComposer registered, SurfaceFlinger attached; no composer
  `bw_mode_bitmap`/caps denial anywhere; PLL0 lock failure, DSI `-22`,
  cmd failures and frame timeouts persist. No boot completion.
- Sync strategy validated: 942080-byte real logcat, a real dpmd
  tombstone and the sync-probe timestamps survived via orderly shutdown
  plus periodic sync. Run83's zeros are therefore explained as
  page-cache loss on abrupt reset (metadata journaled, data not),
  with raw logdump as the always-durable channel.
- New observation: both diagnostic shell services stopped producing
  output mid-boot (probe has 5 entries, logcat ends ~175 s) with no
  death/restart lines, suggesting they blocked (possibly in `sync`)
  rather than crashed. Unproven; needs a liveness marker in the loop.
- Host ADB saw 6.12 at elapsed 196-214 s but shell mostly timed out;
  4 streamed logcat segments captured 0 bytes. On-device service
  remains the primary Android-log channel.
- Vold-death forensics (all channels complete, still traceless): T317
  Looper spam is vndservicemanager shutdown noise, not the trigger.
  vold's last kmsg line is at 114.5 s, last logcat lines at 00:27:52,
  init confirms it alive at 144 s, yet it is absent from the shutdown
  inventory with no exit, crash, tombstone, OOM, denial or restart
  line anywhere. The ack shell services also go quiet ~165-175 s
  (5-entry probe, logcat ends) with no death lines, consistent with
  blocking rather than dying, unproven. A 42 ms primary-capture gap at
  202.567-202.609 s exists but is not evidence of anything hiding in it.
- Committed (needs init-only rebuild): sync-loop liveness marker
  (`N <uptime>` per iteration) to separate blocked-in-sync (storage
  stall) from service death on the next round.

## Run85: same-image repeat (BootAnimation plays; GPU start -110; abrupt reset)

- Same `boot-run84.img`, new run85 tag, full capture. No `ACKRESET1`:
  abrupt return again, unlike run84's orderly reboot. Failure modes
  vary run to run with the identical image.
- Furthest userspace yet: BootAnimation playing bootanimation.zip at
  ~213 s (`run85-early-logcat.log:8073`), SurfaceFlinger pacesetter
  with power modes set, SDM composer registered. Display stack is
  functionally up at the framework level; panel visibility unconfirmed.
- First hard KGSL functional failure: `kgsl kgsl-3d0: CP initialization
  failed to idle` (`rb=0 pos=C/C rbbm_status=800001C1`), then
  `gfx3d_clk_src: rcg didn't update its configuration` on the slumber
  path, then `start failed -110` at 221.276 s
  (`run85-logdump.log:8106-8193`). GPU never runs a command. No
  firmware/zap/GMU lines in kmsg either way; silent success or silent
  skip cannot be distinguished from this log.
- After the -110, primary kmsg ends at 223.1 s (heartbeat seq 100)
  while valid snapshots show the kernel alive at 235/237 s: ~12-14 s
  of silence, then reset with no panic, hung-task, OOM or watchdog
  trace. Shape matches a quiet hang followed by a silent reset, not
  an orderly reboot. The hang's owner is unproven.
- vold alive at 126 s with no death recorded; its run84 silent death
  did not reproduce in the channels covered, so vold instability is
  flaky, not deterministic. No boot completion in any run.
- Capture wins: host logcat streamed 1238 lines (170 KB) while adbd
  responded; on-device logcat kept 1,047,719 nearly-NUL-free bytes
  through the abrupt reset thanks to the sync loop; 12-entry sync
  probe survived. Periodic sync is now proven for abrupt resets too.

## Boot-blocker hypotheses (ranked, 2026-10-13; proofs pending)

- PLL lock (status 0xc): GDSC-cleanup cause falsified by run86
  (`pd_ignore_unused`, still 8 failures). Register programming mirrors
  the donor except an added VCO_TUNE/KVCO_CODE dance of unknown effect;
  DT carries a real fw_devlink cycle (folded gcc-mdss) with unknown
  broken edge. Proof test: failure-path register dump (committed in
  this tree, needs kernel rebuild) distinguishes unlatched config
  (power) from stuck sequencer (config/refclk) from impossible target
  (math).
- GPU CP-idle/-110: firmware names verified correct for A506
  (a530_pm4/pfp + a506_zap, all staged), no load errors, no IOMMU
  faults; ME_INIT path is donor-identical vendored code. Ranked:
  power/clock sequencing (gfx RCG warnings co-occur), then zap-auth
  path, then command-stream compat. Proof: same dump round plus GPU
  power/clock state at first open.
- Userspace crash cluster (13 in run85): binder-EINVAL null-derefs,
  stack_chk_fail x2, scudo heap abort x1, heap-garbage pointer x1.
  System pushes through; servicemanager-class deaths cascade to
  orderly reboot via reboot_on_failure. Needs KASAN or binder-UAPI
  audit; deferred until display/GPU move since it does not stop
  framework progress by itself.
- Second-opinion integration (2026-10-13; reviewer challenged, verified):
  GDSC falsification narrowed (pd_ignore_unused kills only boot-time
  cleanup, not per-access runtime-PM gating; power stays suspect).
  Strongest new PLL lead: commit() hardcodes RESETSM_CNTRL=0x38 AFTER
  commit_common programs the computed 48 (0x30); donor never writes
  0x7f/VCO_TUNE dance either. One-line revert implemented in this tree
  (unbuilt, untested); the committed fail-state dump rides the same
  image to confirm the latched value on the verdict boot.
  GPU correction: gfx3d RCG warnings fire on the slumber/teardown
  unwind, not power-up; best next datum is clock/power state sampled
  at ME_INIT submit entry. dpmd mmap abort is userspace double HIDL
  init (single libbinder mapped), not kernel evidence. Stock crash
  buffer is clean, so the crash cluster is port-induced but split:
  binder-flavored subset vs memory-safety remainder (KASAN deferred,
  no kernel-side primitive observed). PLL stays top-tier: HWC reports
  disconnected with no VSYNC, which gates composition and likely
  boot_completed. Also fixed: enable_seq lost its outer close brace
  during the diagnostic edit (caught before any build).
- Cycle/binder/GPU-supply closure (2026-10-13, no boot needed):
  cycle links go permissive both directions (core.c:1707-1753), so the
  PLL's own power_get cannot move MDSS_GDSC; GDSC rides MDP/DSI
  holders. Late attempts fail with GDSC held, so persistent 0xc is
  config/sequencing, not domain power. Binder UAPI is the stable
  v7/v8 ioctl set; dpmd stays a userspace double HIDL init. GPU node
  carries donor clocks/IRQ/bus/pwrlevels and reads back live RBBM,
  so coarse GPU power is on.

## Run87: diagnostic boot, no recovered Android logcat

- Delivered build-host run86 image was installed under unused run87 tag.
  Kernel identifies as `6.12.93-4k-gd3ca5dd866f6-dirty`
  (`run87-logdump.log:4`). Raw logdump and matching SD evidence were
  retrieved; no ACKRESET1 record was found.
- No port ADB window was observed; host timeline detected stock at
  elapsed 176 s. Preserved kernel text ends at 107.377 s, not a proven
  reset timestamp. Return cause remains unknown.
- Early-logcat overlay append succeeded (`run87-logdump.log:877`).
  Both `ack-early-logcat` and `ack-sync-loop` started at 101.6 s
  (3547-3554). Sync service argument expansion reported deprecated
  property syntax (3553), then SIGABRT at 102.122 s (3595).
  Neither on-device diagnostic file was available after return.
  `run87-early-logcat.log` contains only the missing-file error, not
  Android log data. Service startup is proven; successful capture is not.
- Four early PLL failure dumps report `vco=0`, `pm_active=1`,
  `iface_rate=0`, and LDO/CLKCFG registers zero (315-318, 415-418,
  663-666, 750-753). These establish the state at failed enable, not
  why rate programming was absent or whether it propagated later.
  No boot-completion, GPU-start, or composer verdict is established.
- Sync-loop source correction: escape shell dollar signs as `$$` in
  Android init service arguments. A host smoke compiled the real AOSP
  `ExpandProps` function: old command rejected; fixed command survived
  expansion and produced counter/uptime rows 1-3 when run by the shell.
  Init rebuild and device verification remain required; this does not
  explain the missing early-logcat file.
- PLL zero-rate interpretation narrowed further: the first dumps precede
  provider registration (`run87-logdump.log:513`); their warning stack
  runs through `clk_core_reparent_orphans_nolock` (393-396).
  GCC byte/pixel RCGs use `CLK_OPS_PARENT_ENABLE`, which prepares
  parents during orphan reparenting before rate programming
  (`drivers/clk/clk.c:2193-2196,3913-3918`). Thus these early zero-rate
  enables cannot establish a missing DSI set-rate during panel startup.
  Run87 contains no ME_INIT-submit datum; GPU start was not exercised.

## Run88: repaired sync loop, early return before observed ADB

- Verified build-host SHA256SUMS and kernel-directory payload against
  packaged image. Image SHA256
  `e0f5518856fde6701a5b06ff89b272e23652e995b6568c8a34f71bbb348b0a9c`.
  Kernel is rebuilt at `b37ecaa78917`, not identical to run87; DTB,
  cmdline and every non-init ramdisk record are unchanged. Static arm64
  init contains the corrected dollar escapes.
- Archived preboot raw/logcat in `run88-preboot/`; verified zero readback
  (`run88-preclear.stdout`). RAM boot succeeded; no flash performed.
  USB retained 451197 bytes (`run88-usb-capture.status`). Continuous
  collector ended at host elapsed 192.33 s with no observed port ADB
  and no logcat segments; user reported reset, stock kernel confirmed.
- Retrieved 67108864-byte raw dump and matching 452310-byte SD/common
  extent. Valid snapshot slots timestamped 107.127 / 109.177 s.
  Kernel text ends at 110.674 s (`run88-logdump.log:3707`), not a
  proven reset timestamp. No ACKRESET1 record was found.
- Both capture services started around 105.4 s
  (`run88-logdump.log:3528-3533`). Sync probe survived with
  `1 106.04 622.73` (`run88-sync-probe.log:1`): corrected command executed
  and its output persisted. Only one iteration is proven.
  Early-logcat pull failed with missing file; failure stderr retained.
  Service startup does not prove successful Android log capture.
- PLL dumps remain early zero-rate enables (315, 415, 658, 749).
  No ME_INIT-submit datum; GPU start was not exercised. No boot
  completion, composer, EGL, rendering or reset-cause verdict.
- Follow-up: logcat PID 572 connected to logd at 107.201 s
  (`run88-logdump.log:3610`). Capability denials for dac_override and
  sys_nice appear at 3608-3611; neither proves file-write denial.
  A stock-kernel smoke using the actual `u:r:shell:s0`, uid 0,
  gid log and supplemental shell/readproc groups successfully dumped
  and rotated logcat files (`run88-shell-logcat-smoke.log`).
  Probe files were removed; boot evidence was not altered.
- Surviving sync row precedes the logd connection. With five-second
  sleep after sync, a subsequent flush is not demonstrated before the
  110.674 s log cutoff. Lost unflushed file output is a hypothesis,
  not a proven startup failure or reset cause.
- Both reserved snapshot tails were decoded independently
  (`run88-slot0-strings.log`, `run88-slot1-strings.log`); neither
  establishes the reset cause. Stock dmesg reports Hard Reset/cold boot
  and PS_HOLD shutdown (322-326 in `run88-stock-dmesg.log`), which does
  not identify the requesting actor. No new tombstone timestamp from
  this boot was present in the preserved directory listing
  (`run88-stock-postreset.log`). Stock boot completed later.
- Approved run89 diagnostic source change: initial finite `logcat -d`
  dump, then `sync`, then `exec` continuous logcat, using `&&` so a
  failed initial dump/flush does not masquerade as successful setup.
  Same output path, rotation, service credentials and policy retained;
  continuous capture can repeat backlog records.
  Stock smoke executed the generated command in the actual shell
  domain/groups, reached streaming after the dump/flush, and captured
  an injected marker. Probe process/files removed.
- Run89 built locally with Homebrew Zig 0.17.0 targeting
  `aarch64-linux-musl`, static, `-Os`, ANDROID_CAPTURE and
  ANDROID_EARLY_LOGCAT, deadline zero. Static arm64 ELF verified;
  separate same-toolchain executable ran on stock 4.19.
  Packaged `snapshot60/boot-run89.img` SHA256
  `8bf159a2a7f7b8a28c0601d0d0a8e28f1262a4b22d38e07b89dcc4f17ea65e17`.
  Kernel/DTB/cmdline byte-identical to run88; 665 CPIO records with
  only init changed, including unchanged policy/firmware records.
  Init SHA256
  `639ae66c5f8c4aa9e728a4e9a54f319e5998cf87f29de974b4369c5e7d87d9c6`.
  No kernel rebuild; subsequently RAM-booted under run89 below.


## Run89: local init boot, early Android logcat survives return

- Archived preboot evidence and verified zero readback under unused
  run89 tag. RAM boot succeeded; USB retained 460268 bytes.
  Continuous host collector observed stock after transport loss at
  elapsed 200.30 s, with no observed port ADB or host logcat segments.
- Retrieved full 67108864-byte raw dump; readable prefix 459581 bytes.
  SD/common extent matches 459408 bytes. Valid snapshot timestamps
  119.872 / 121.954 s. Kernel text ends at 122.853 s
  (`run89-logdump.log:3748`), not a proven reset time.
  No ACKRESET1 record found; reset cause remains unknown.
- Recovered real `/data` early-logcat: 101136 bytes, 776 lines
  (`run89-early-logcat.log`). Logcat's nonblocking initial reader
  connected at 120.181 s (kernel log:3666). No later streaming-reader
  connection is recorded; full dump/sync/stream completion is unproven.
  Sync probe retained `1 122.07 715.28` (`run89-sync-probe.log:1`).
- Logcat shows vold/fscrypt user-0 setup and successful keystore work,
  with initial HAL registration near its tail (764-776). It contains
  no recovered fatal-signal or reboot-request record establishing the
  return cause. No ME_INIT entry recorded in kernel evidence; GPU start
  was not exercised. No framework boot-completion or rendering verdict.
- Stock 4.19.325, boot completed, root available, enforcing confirmed
  after retrieval (`run89-postreset-state.log:1-4`). No further boot,
  clear or flash performed. Local Zig-built init executed successfully
  far enough to install and launch the diagnostic services; full PID 1
  and capture-lifetime correctness are not established.

## Run90: kernel process/signal diag, collector lifecycle fully proven, same silent death

- Change: kernel commit a58d7a094 (opt-in process/signal reset-attribution
  evidence); init byte-identical to run89
  (`package-run90.json:init_sha256`). Packaged
  `snapshot60/boot-run90.img` SHA256 `efaa1c91838c9bb5...90121727`,
  kernel payload `322b1149...` (+2054 B vs run89), same run81 base,
  same cmdline. RAM boot succeeded; preclear verified zero
  (`run90-preclear.status`).
- New instrumentation works: 84 `process_exit`/`signal_generate` records
  in kernel evidence, all routine userspace churn (odrefresh exit 0,
  odsign SIGKILL by init, apexd/netbpfload/netd/sync exits). No fatal
  or reset-attributing signature.
- Collector lifecycle closed the run88/89 flush question: initial
  nonblocking dump connected (`run90-logdump.log:3747`, PID 592,
  t=106.006 s), first sync-loop sync completed exit 0
  (`run90-logdump.log:3726`, t=105.447 s), blocking streaming reader
  connected (`run90-logdump.log:3762`, PID 578, t=106.467 s) and
  streamed until ~1 s before kernel end. /data early-logcat gained
  720 lines / 93839 bytes this boot (lines 777-1496 of
  `run90-early-logcat.log`; run89's 776-line prefix was archived in
  `run90-preboot/early-logcat-rotation.log` — pre-boot delete step was
  skipped, file appends, boundary at line 776/777).
- Death: abrupt and silent. Kernel text ends t=112.028 s starting
  `vendor.wifi_hal_legacy` (`run90-logdump.log:3849`, record 3748,
  file end); logcat streams normally through 03:37:18.118 (~111.6 s).
  No panic text, no ACKRESET1 (decode-reset.py on `run90-logdump.bin`),
  no KGSL/GPU lines, ME_INIT never reached (4th consecutive run).
- Refutes run89's "dies during first sync" correlation: run90's first
  sync completed 6.6 s before death; sync probe line 2 = `1 104.79
  622.64` (`run90-sync-probe.log:2`); loop iteration 2 `cat` exit seen
  at 110.99 s, its echo lost with the reset (no fsync, expected).
- Timeline: stock visible 0-12 s, transport loss from 16 s, stock
  stable by continuation cont_elapsed=9, `continuation exit segs=0`
  (`run90-adb-timeline.log`) — port ADB never observed, 4th
  consecutive run. USB ACM reader died at host 143.5 s / 476311 bytes
  (`run90-usb-capture.status`).
- Evidence gap: no `run90-postreset-files.log`/`-state.log` pulled, so
  post-run tombstone delta is unverified (preboot archive holds
  run89's tombstones as `run90-preboot/tombstones.tgz`).
- Verdict: same image family now has runs 87/88/89/90 all dying
  abruptly with no kernel-log panic at 104-123 s uptime, mid
  vendor-HAL startup, no GPU start, no orderly record. Reset cause
  remains unknown; next diagnostic lever per handoff below.

## Handoff to another machine

- Stop point: run89 returned before observed port ADB but preserved real
  Android logcat. Reset cause remains unknown. Run85 remains GPU-start
  failure evidence; run89 did not exercise ME_INIT. Panel PLL lock, GPU
  CP idle and flaky userspace death remain open. No boot completion,
  EGL success or rendering verdict.
- Latest RAM-booted image is `snapshot60/boot-run89.img`; control remains
  the original `snapshot60/boot-run73.img`. Run81-89 tags are used.
- Preserve / transfer the real `snapshot60/base-guard-debug-fw.img`,
  `init-run32`, and all four `kdir-run73/` files. Do not reconstruct
  the policy-bearing base from captures or stock images.
- Treat HANDOFF-kgsl-port.md as a historical Stage 2 handoff.
  REFERENCE-boot-testing.md's original timing/capture sections are
  historical; this handoff and later run evidence take precedence.
  Its new opt-in early-reset section describes the pending experiment.
  Do not use its 150-second ADB window as a boot-failure verdict or run
  direct make without the required arm64 environment.
- Next step: diagnose early return using preserved run89 Android/kernel
  evidence before another boot or kernel change.
  GPU CP-idle and actual panel-start PLL state still need runtime data.
  Any repeat needs an unused run tag and continuous host capture
  alongside USB and ADB timeline.
  Allow at least eight minutes unless the device demonstrably exits
  the port kernel; do not treat a 150-second window as failure.
- Current state: stock 4.19.325, boot completed, root available, enforcing,
  confirmed after run89 return. Raw/SD, USB, timeline, early-logcat and
  sync probe are preserved. Earlier run84 logcat and tombstone retained.
  No further boot / clear / flash after run89 retrieval.
- Deferred kernel work remains: raw display markers collide with
  ramoops; pstore retries cannot resolve PARTLABEL and synthetic panic
  is unsafe; arbitrary MDP delay and removed idle-PC restore are not
  production fixes. Keep KGSL/MDSS unchanged; only the approved
  diagnostic pstore extension and init capture services are in scope.
  run83's reset is abrupt with GPU-clock activity at the cutoff, run84's
  is an orderly vold-failure reboot, run85's follows GPU start -110 and
  a quiet hang. Same image, three faces: failure modes are flaky.


## Boot economy (AGENTS.md)
One change per boot. `package-diag-boot.py` capture, verdict recorded here
with file+line evidence before any claim. Reverts are one-line documented.

## Run102: SD mirror disabled; early silent return persists

- Init-only change: SD mirroring is opt-in (`ANDROID_SD_MIRROR`), not
  enabled in run102. This does not disable the kernel's SD/MMC probe.
  Kernel payload `5a8a3ac2…` and cmdline match run101; no kernel rebuild.
- USB retained 203612 bytes (`run102-usb-capture.status`); full 64 MiB
  logdump retained. Tail at 64.504747 s, during deferred MDP re-probe,
  `xlog_status` (`run102-logdump.log:1498-1513`). This is the last
  recorded activity, not a measured reset time.
- `mmc1: Card stuck being busy!` remains at 5.901993 s
  (`run102-logdump.log:498`). Disabling the userspace mirror does not
  prevent the early card failure; its causal role remains unproven.
- Neither keymaster nor gatekeeper started before the cutoff. No
  `ACKRESET1` record (decode-reset.py); stock 4.19 returned without an
  observed 6.12 ADB window (`run102-adb-timeline.log:6-17`).
  Early-logcat contains only an error, not recovered Android output.

### HAL timing comparison through run102

Times are kernel uptime seconds. Gatekeeper's first QSEE ioctl is
attributed using the PID in init's service-start record; the filename
in the last column is `run<N>-logdump.log`. A dash means not observed,
not proof that an unlogged operation could not occur.

| Run | Gatekeeper first QSEE ioctl | Last kernel record | Gap | Evidence lines (first ioctl / tail) |
|---|---:|---:|---:|---|
| 87 | 106.439 | 107.377 | 0.938 | 3728 / 3746 |
| 88 | 109.115 | 110.674 | 1.559 | 3682 / 3707 |
| 89 | 121.301 | 122.853 | 1.552 | 3701 / 3748 |
| 90 | — | 112.029 | — | Service starts 3808; tail 3849 |
| 91 | 119.005 | 122.303 | 3.298 | 3731 / 3835 |
| 92 | — | 57.380 | — | 2027 |
| 93 | 133.094 | 135.961 | 2.867 | 3767 / 3813 |
| 94 | 109.108 | 122.565 | 13.456 | 3638 / 4590; clock WARN/unwind |
| 95 | 155.013 | 156.757 | 1.744 | 3787 / 3824 |
| 96 | — | 76.553 | — | 1451 |
| 97 | — | 74.340 | — | Keymaster send at 2372; tail 2381 |
| 98 | 124.865 | 126.102 | 1.237 | 3840 / 3859 |
| 99 | — | 64.448 | — | 1488; headless |
| 100 | — | 990.490 | — | 2955; SD failure/qseecomd exit storm |
| 101 | — | 549.681 | — | 2216; SD failure/qseecomd exit storm |
| 102 | — | 64.505 | — | 1513; early-init/MDP |

- Correlation, not confirmed causation: most late cutoffs follow
  gatekeeper's first QSEE ioctl by 0.9–3.3 s. Run90 has only a service
  start, run94 is a distinct clock-warning case, and early cutoffs
  show that neither HAL is necessary for every silent return.
- Run97 ends during keymaster activity before gatekeeper starts. It
  supports gating both, but does not by itself prove keymaster caused
  the return. A single shifted cutoff cannot establish causation in
  this flaky population.
- Completed experiment: run103 RAM-booted with keymaster+gatekeeper
  stubbed by `ANDROID_HALGATE`; unchanged run102 kernel/DTB/cmdline.
  Both binds succeeded and neither service started. Verdict below.

## Run103: paired HAL gate holds; fscrypt wait, user-forced reboot

- Locally rebuilt only init with Zig, static `aarch64-linux-musl`,
  `-Os -DANDROID_CAPTURE -DANDROID_EARLY_LOGCAT -DANDROID_HALGATE`.
  Ungated rebuild reproduces run102 init SHA256 exactly (`0aba507b…`).
  Gate list now contains only keymaster+gatekeeper, not run91's five HALs.
- `boot-run103.img` SHA256
  `540ec28d6e1f1df08aaf1a9e5425b49ee43f67cd64d800c42e525fd9a49296b7`.
  Packager verified 665 CPIO records with only init replaced.
  Kernel payload `5a8a3ac2…`, DTB and cmdline unchanged from run102.
  RAM-only fastboot boot succeeded; no kernel build or flash.
- Preboot run102 logdump matched its archived SHA256; preclear proved
  zero readback. Both HAL bind overlays returned errno=0 at 19.509 /
  19.512 s (`run103-logdump.log:879-880`). No service-start record for
  either HAL, no `qsee_send_desc` record.
- SD stuck-busy/-110 recurred, but early mount_all completed in 505 ms
  at 59.360 s (1964). QSEE daemon started at 61.439 s; eight listeners
  registered (2027-2104). SD failure alone does not invariably produce
  run100/101's mount delay and qseecomd exit storm.
- Init reaches `post-fs-data`, then waits for
  `vdc --wait cryptfs enablefilecrypto` at 62.937 s (2266-2269).
  Missing keymaster causes repeated interface-start failures; vold
  repeatedly waits for keystore2 (2272-2279 onward). No zygote start,
  later HAL startup or recovered early-logcat; sync file unchanged.
- USB retained 489898 bytes; raw logdump 67108864 bytes with a
  492108-byte readable prefix. Valid snapshots at 224.529 / 226.576 s.
  Last kernel record at 226.511309 s (3107), still waiting on keystore2.
  No ACKRESET1 record. No observed port ADB; stock first observed at
  host elapsed 284.32 s (`run103-adb-timeline.log:72-73`).
  Stock root/enforcing verified (`run103-postreset-state.log`).
- User reports forcing the reboot because the same messages repeated.
  This run is manually terminated, not a spontaneous-death sample.
  The log cutoff is not a reset timestamp; no exact manual-reboot
  uptime was captured. Absence of ACKRESET1 does not contradict the
  reported forced reboot.
- Verdict: survived beyond the 107-157 s window, but the intervention
  blocks an earlier dependency and never exercises the former late-HAL
  path. Confounded, not proof of either HAL as trigger. No spontaneous
  reset observed before manual termination; no boot-completion verdict.

### Diagnostic todos after run103

- [x] Record run102, preserve its evidence and add the HAL timing table.
- [x] Build init only; verify unchanged kernel/DTB/cmdline and baseline init.
- [x] Perform one paired-gate RAM boot; verify overlays and preserve
  USB/raw/timeline/post-return files and tombstones.
- [x] Run104: gatekeeper-only RAM boot completed; keymaster retained,
  fscrypt progressed, gatekeeper absent. Crash evidence recorded below.
- [ ] Reset attribution remains open; run104 captures an external abort.

## Run104: gatekeeper absent; synchronous external abort in cat

- User approved the follow-on boot. Only gatekeeper's vendor rc is
  stubbed by the existing `ANDROID_HALGATE`; keymaster is retained.
  Init rebuilt locally with the same Zig target and flags as run103.
- `boot-run104.img` SHA256
  `3e9db5a05494231ffe9ce169a44873dd6210240f72baff4324c2db7078f4241b`.
  Init SHA256 `d749d6fb…`; kernel payload `5a8a3ac2…`.
  Packager verified 665 CPIO records with only init replaced relative
  to run103; kernel/DTB/cmdline unchanged.
- Archived run103 preboot evidence and verified its logdump matches
  the existing archive. Run104 logdump preclear proved zero readback.
  RAM-only boot succeeded with continuous host USB/ADB capture.
  No kernel build, flash or host-initiated reboot after image entry.
- Gatekeeper override errno=0 at 33.862 s
  (`run104-logdump.log:880`); no gatekeeper service start. Keymaster
  starts at 129.341 s (2227), emits 35 send descriptors from 129.765
  to 151.765 s (2254-3516). Eight QSEE listeners register.
- `enablefilecrypto` exits status 0 at 132.501 s (2555); zygote starts
  at 156.342 s (3679). This run passes the paired gate's fscrypt
  confounder and reaches later HAL startup. SD stuck-busy remains,
  but mount_all --early takes 805 ms at 120.612 s (2060).
- USB captures `Internal error: synchronous external abort:
  0000000096000010 [#1] PREEMPT SMP` at 161.390266 s
  (`run104-usb.log:3835-3839`). CPU 0, PID 640, comm `cat`;
  kernel `6.12.93-4k-g58bcef21591f`, taints MACHINE_CHECK and WARN.
  ESR EC=0x25, DFSC=0x10: current-EL data abort, synchronous external
  abort. No faulting PC, LR, FAR or abort stack trace survives.
- Crash header is USB-only. Raw logdump's readable prefix stops at
  161.238 s (`run104-logdump.log:3841`), before the abort; byte search
  finds no abort header in raw or snapshot regions. Valid snapshots
  at 157.299 / 159.371 s. No ACKRESET1 record.
- USB retained 474046 bytes; raw logdump 67108864 bytes, readable
  prefix 473685 bytes. Early-logcat recovered 88592 bytes / 685 lines.
  Sync probe adds `1 155.41 993.73`; tombstone contents unchanged.
  No observed 6.12 ADB; stock returns at host elapsed 228.23 s
  (`run104-adb-timeline.log:58-59`). Stock boot-completed, root and
  enforcing verified (`run104-postreset-state.log:1-4`).
- Verdict: gatekeeper is not necessary for this post-zygote failure.
  A 161 s abort with gatekeeper absent does not confirm the earlier
  gatekeeper timing correlation, nor prove all prior silent returns
  share this cause. Keymaster remains a possible indirect contributor,
  not established by the crash context.
- [INFERENCE] `cat` may be ack-sync-loop's second `/proc/uptime` read:
  first iteration is retained at 155.41 s, with sync plus five-second
  sleep between iterations. PID 640's parent/argv were not captured;
  process name and timing are insufficient to assign the fault.

### Diagnostic todos after run104

- [x] Gatekeeper-only boot with keymaster retained; verify gate and
  progression, preserve raw/USB/Android logs and post-return state.
- [ ] Capture faulting PC/FAR/stack and identify PID 640's read path
  before changing a driver or attributing the abort to a subsystem.
- [ ] Distinguish external-abort failures from earlier silent returns;
  no extra boot performed in this request.

## Run105 preparation: early SEA context; Linux build received

- User approved capturing PC/FAR/stack after run104 and selected
  "I'll build on Linux". Built artifacts received; run105 verdict below.
- `arch/arm64/mm/fault.c:do_sea` now emits one kernel-mode-only
  `SEA:` record with ESR, raw FAR, FnV, raw PC/LR, PID/PPID and comm,
  then a fault-context backtrace before `arm64_notify_die`.
  Recoverable fixups and user-mode handling remain unchanged; no
  new Kconfig, exports, resets or driver changes.
- Exported focused patch:
  `porting/artifacts/snapshot60/run105-sea-context.patch`.
  Apply only if the Linux tree does not already contain this edit.
- Probe and build notes committed/pushed as `6b11c2e1c`. After pulling,
  no separate patch application is needed. Local clangd lacked kernel
  include configuration; user completed the Linux build and artifact pull.
- Incremental Linux build from the existing kernel worktree, preserving
  the run101/run104 merged out/.config and existing DTB:

  ```sh
  patch --dry-run -p1 < /path/to/run105-sea-context.patch
  patch -p1 < /path/to/run105-sea-context.patch
  export PATH="/usr/bin:$PATH"
  export ARCH=arm64 LLVM=1 LLVM_IAS=1 CC="ccache clang"
  sha256sum out/.config
  make O=out -j"$(nproc)" Image.gz
  sha256sum out/.config
  sha256sum out/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb
  tar -C out -czf /tmp/run105-sea-build.tgz \
      .config vmlinux System.map arch/arm64/boot/Image.gz \
      arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb
  ```

- Do not rerun gki_defconfig or merge fragments. The .config hashes
  before/after must match; unchanged DTB expected SHA256
  `71951fb1a5a989ca59a30762a33202229d86213c93f25d306a607f9bffb0c2c7`.
  Retain the matching vmlinux/System.map, not symbols from another build.
- [x] Build received: banner `6.12.93-4k-g6b11c2e1c578`, clang/LLD
  22.1.8. Early SEA diagnostic format present in decompressed Image.gz.
  All four pulled hashes verified; Image.gz-dtb concatenation checked.
- [x] Embedded config options identical to run104 and pulled kernel.config;
  DTB byte-identical. Required TRACEPOINTS/BLOCK/PSTORE_RAM retained.
- [x] Packaged `boot-run105.img`, SHA256
  `ea5095b6fae6e9f9ed10dd90cfce3529448d9470fa6771e2dfada3596942f5e3`.
  Kernel payload `cd415ff3…`, Image.gz `4403ae99…`, config `b7e1abe8…`.
  Init `d749d6fb…`, entire ramdisk and cmdline byte-identical to run104.
- [x] Archived run104 preboot evidence; current logdump hash matches it.
  Run105 preclear verified zero. Early-logcat's 88592-byte run104 prefix
  preserved, so any appended output must be separated from old records.
- [x] One RAM-only boot with USB/continuous ADB capture completed.
  Early return did not reproduce run104's SEA; no fault-context capture.
- Matching vmlinux/System.map were not included in the pulled directory;
  raw-address offline symbolization requires those exact build artifacts.

## Run105 result: early silent return; SEA path not reproduced

- Fastboot RAM boot succeeded; USB retained 200704 bytes before
  disconnect at host elapsed 108.94 s (`run105-usb-capture.status`).
  No host-initiated reboot after image entry. No observed 6.12 ADB;
  stock first seen at host elapsed 144.17 s
  (`run105-adb-timeline.log:37-38`). Stock boot-completed, root and
  enforcing verified (`run105-postreset-state.log:1-4`).
- Full 67108864-byte raw logdump retained, readable prefix 203629 bytes.
  Valid snapshots at 73.589 / 75.637 s. USB ends during SMMU rotator
  probe at 76.983 s; raw continues to 76.997781 s during DSI panel
  parsing (`run105-logdump.log:1489-1506`, `dyn_fps: min = 60, max = 60`).
  These are last captured activity, not measured reset timestamps.
- Gatekeeper bind errno=0 at 34.441 s (539). No keymaster or gatekeeper
  service start, QSEE send descriptors, zygote start or mount_all record.
  SD stuck-busy/-110 remains at 18.732 s (497-498). None of these tail
  correlations identifies the reset actor or proves an MDP/SMMU defect.
- Neither USB nor the complete raw dump (including snapshot regions)
  contains `SEA:` or `Internal error:`. No ACKRESET1 record. The new
  probe is compiled into the booted kernel, but its reporting path was
  not observed; run104's 161 s abort and faulting read path remain open.
- Retrieved early-logcat (88592 bytes) and sync-probe (174 bytes) are
  byte-identical to the preboot archives: both are run104 evidence,
  not new run105 output. Tombstone contents also unchanged.

### Diagnostic todos after run105

- [x] Verify rebuilt kernel/embedded config and one-variable packaging.
- [x] Run one probe boot and preserve raw/USB/timeline/post-return evidence.
- [ ] Reproduce the target SEA with the same diagnostic image under a
  fresh run tag before claiming PC/FAR/stack capture works on-device.
- [ ] Obtain matching vmlinux/System.map for any raw-address decoding.
- [ ] Keep early silent-return and post-zygote external-abort hypotheses
  distinct; no driver fix or extra boot performed in this request.

## Run106: unchanged run105 image; post-zygote silent return

- User approved one repeat. RAM-booted the existing `boot-run105.img`
  SHA256 `ea5095b6…` under unused run106 tag; no rebuild, repack, init,
  DTB or cmdline change. Archived run105 evidence and verified current
  logdump matches it; run106 preclear verified zero readback.
- USB retained 474023 bytes; raw logdump 67108864 bytes with a
  474116-byte readable prefix. Valid snapshots at 125.910 / 127.977 s.
  Last kernel record at 130.025225 s
  (`run106-logdump.log:3837`, qrtr service cgroup creation).
  No host-initiated reboot after image entry. No observed port ADB;
  stock first observed at host elapsed 196.23 s
  (`run106-adb-timeline.log:50-51`). Stock boot-completed/root/enforcing.
- Gatekeeper override errno=0 at 32.929 s (878), no gatekeeper start.
  Keymaster starts at 93.223 s (2238), 35 send descriptors from 93.685
  to 119.326 s (2275-3536). Fscrypt advances; zygote starts at
  125.077 s (3712), followed by vendor HALs.
- MDSS reports bootloader display off at 74.751 s (1806), then
  registers the 1080x1920 framebuffer at 74.781 s (1875), despite the
  same missing optional-resource/property messages. SD stuck-busy
  persists at 16.972 s (837); mount_all --early succeeds in 1491 ms
  at 85.571 s (2071).
- No SEA/abort header in USB or the entire raw dump; no ACKRESET1.
  This repeats the late silent profile with gatekeeper absent. It does
  not reproduce run104's external abort or identify the faulting read.
- Early-logcat retains the unchanged 88592-byte prefix and adds
  88127 bytes / 683 lines. Sync probe adds `1 123.64 768.21`.
  Tombstone contents unchanged. These new records are distinct from
  the run104 carry-over retained in run105.

### MDSS message assessment requested during run106

- `lut_clk`, `bimc_clk`, `mnoc_clk`, `throttle_bus_clk` are treated as
  optional (`mdss_mdp.c:1939-1958`); bus/iface/core acquisition failures
  do fail probe. Failed optional acquisition does not store an ERR_PTR
  in the zero-initialized clock array (1822-1839,2998).
- Missing `vbif_nrt_phys` does not fail probe (3049-3054); normal NRT
  client selection requires a non-NULL NRT base (`mdss_mdp.h:1398-1402`).
  This is not an exhaustive proof of every later VBIF access path.
- Missing pipe-reset offset retains zero and skips setup
  (`mdss_mdp.c:3638,3713-3728`). Missing bandwidth factors retain
  preinitialized defaults (4229-4241,4575-4592). Missing min/max FPS
  defaults to panel frame rate (`mdss_dsi_panel.c:2380-2418`).
- Therefore these messages do not justify invented DT register/clock
  entries or warning suppression as a reset fix. Actual required-resource
  failures, power/clock sequencing and splash handoff still warrant
  targeted correctness review; no MDSS code was changed.
- Splash state differs across samples: run104 off with late SEA,
  run105 on with early cutoff, run106 off with late silent cutoff.
  `mdss_mdp.c:3189-3215` selects different handoff/power paths based
  on that state. Correlation only; not a demonstrated causal defect.
- [ ] SEA PC/FAR/stack capture and raw-address symbolization still pending.
- [ ] Review actual MDSS power/handoff accesses separately from optional
  property logs; do not equate run104 SEA with every silent return.

## Reset logging repair after run106

- Priority changed from MDSS messages to recoverable reset evidence.
  Run106 raw recovery now exports console slots seq55 at 127.977 s and seq54
  at 125.910 s. No valid dmesg panic/oops record exists in these samples.
  Version0 has no CRC or commit guarantee; neither freshness nor same boot
  is established by consecutive counters alone.
- Built-in pstore-blk resolves late PARTLABEL devices without filesystem
  nodes, retries only transient lookup failures and preserves ownership.
  Removed the retry-attachment synthetic panic. Generic best-effort block
  I/O remains unsuitable for panic context and cannot coexist over the
  diagnostic ramoops layout.
- Raw snapshots and new direct printk tails use version1 header/payload
  CRC32 with invalidate/flush, payload/flush, publish/flush ordering.
  Userspace logdump text is capped at 60 MiB; mirrors continue beyond the
  cap. DT enables genuine emergency/shutdown RAM dumps.
- Verification: 41 discovered host tests, collector integration, five
  reset-decoder tests and witness-open harness pass. Actual run106 decoder
  CLI recovered two console files. Production/static test init builds pass;
  prefix-boundary/partial-write/mirror smoke passes on Android ARM64 emulator.
  Tissot was disconnected; no new-kernel phone boot or kernel build claimed.
- Build/packaging contract and non-overlapping disk ranges:
  `porting/logging/README.md`, "Tissot reset persistence after run106".
  Remove inherited pstore-blk cmdline tokens and retain ramoops ownership.

### Reset logging acceptance todos

- [x] Repair runtime PARTLABEL lookup and remove fake crash attachment.
- [x] Recover existing raw console/dmesg with provenance and legacy limits.
- [x] Verify C snapshot commit failure boundaries, CRC format, prefix cap
  and decoder/collector behavior using reachable host/Android smoke paths.
- [x] Linux rebuild of kernel and DTB with the existing configuration (run107).
- [x] New-image readiness: CRC32-committed snapshot and reset-capture armed.
- [x] Controlled orderly reboot: recover ACKRESET1 and valid version1 slots.
- [ ] Capture genuine SEA/panic/watchdog evidence if the fault recurs;
  absence still cannot prove no crash or identify the resetter.

## Run107: orderly-reset persistence acceptance passed

- User supplied `run107/` kernel/DTB/config; all four SHA256SUMS pass.
  Banner is `6.12.93-4k-gbe63c5ea5a0e`, with the CRC32 commit,
  reset-capture armed and SEA markers present. DTB has `max-reason=4`;
  config has built-in PSTORE_RAM/BLOCK/CRC32 and 4 KiB pages.
- Rebuilt init with capture, early-logcat, gatekeeper-only HAL gate and
  `BOOT_DEADLINE_SECONDS=45`. Packaged from run105, preserving its existing
  console via `--keep-stock-console`; no firmware/policy/other ramdisk
  change. Removed all four pstore-blk cmdline tokens and selected
  `pstore.backend=ramoops`; reset capture remains enabled.
  Boot SHA256 `54abe74e42a76b07b72ae904bfa7588613ae082d480a1b0ae3460bd31f314b63`.
- Archived current partition and diagnostic files in `run107-preboot/`.
  Preclear hash matches the archive; all-zero readback verified.
  `fastboot boot` accepted the image; nothing flashed.
- Kernel registered ramoops at 0.427 s, armed reset capture at 0.431 s,
  and reported CRC32-committed snapshots/tails ready at 4.531 s
  (`run107-logdump.log:160-164,468-469`). No pstore-blk open error seen;
  its generic PARTLABEL opener is not exercised by this ramoops-only boot.
- Deadline marker at 45.381 s, orderly notifier at 47.382 s, successful
  reset-capture flush at 47.394 s (`run107-usb.log:963-965`).
  This return was deliberately requested by the diagnostic deadline,
  not another spontaneous cutoff. No host reboot after image entry.
- Raw logdump is 67108864 bytes, readable prefix 139949 bytes; USB
  captured 140035 bytes. Decoder recovered both console slots and both
  periodic printk slots with valid version1 header **and** payload CRCs:

| Record | Slot | Sequence | Header uptime (s) |
|---|---:|---:|---:|
| Raw ramoops snapshot | 0 | 21 | 46.401171231 |
| Raw ramoops snapshot | 1 | 20 | 44.348233003 |
| Periodic printk tail | 0 | 21 | 46.416637481 |
| Periodic printk tail | 1 | 20 | 44.362904357 |

- `decode-reset.py run107-logdump.bin` recovered
  `ACKRESET1 timestamp_ns=47378926023 action=1 pid=178 comm=init command= tail_bytes=64926`.
  Its saved tail includes the deadline and orderly-reset messages;
  USB separately proves `reset capture persisted tail_bytes=64926`.
  Preclear plus current build/banner/deadline establishes this test's
  provenance; CRCs or consecutive counters alone would not.
- No genuine dmesg panic/oops record recovered, as expected for this
  controlled non-panic boot. SD pull unavailable; USB/raw/ACK evidence
  suffices for the persistence result. Stock 4.19 returned and then
  reached boot-completed=1, root available, SELinux Enforcing.
- [x] Orderly reboot persistence and post-stock console/tail recovery proven.
- [x] Remove only the 45 s test deadline for a later fault-reproduction boot (run108).
- [ ] Final unwritten SEA/panic lines and hardware-watchdog persistence remain
  unproven; run107 does not diagnose the earlier spontaneous reset cause.

## Run108: deadline removed; early silent reset during MDP re-probe

- Same run107 kernel payload and cmdline; init rebuilt with
  `BOOT_DEADLINE_SECONDS=0` as the only change. Boot SHA256
  `3566dd337c06d951eefd3a1adf88ba5f28635774bcfcd5c3ba6fa993353ef89b`.
  Preboot raw partition matched archived run107 evidence; archived
  early-logcat rotation removed; preclear zero readback verified.
  RAM boot only; no host reboot after image entry. Stock first observed
  at host elapsed 123.21 s (`run108-adb-timeline.log`).
- Raw logdump 67108864 bytes, readable prefix 215072 bytes; USB 214106
  bytes. Last raw record at 66.542461 s (`run108-logdump.log:1606`),
  8 records after `mdss_mdp: kicking late deferred re-probe` at
  66.536843 s (1598), inside `mdss_mdp_parse_dt` pipe setup. USB stops
  earlier at 66.394908 s.
- Four version1 slots pass header/payload CRCs: snapshots/tails seq27
  at 63.969/63.987 s and seq28 at 66.044/66.067 s. Reset region all
  zero: no ACKRESET1, so no orderly reboot path. No dmesg panic/oops,
  SEA, internal error or watchdog text.

### Cutoff versus late MDP re-probe, run90-run108

| Run | Last record (s) | Last re-probe kick (s) | Records after kick |
|---|---:|---:|---:|
| run102 | 64.505 | 64.494 | 15 |
| run105 | 76.998 | 76.783 | 37 |
| run108 | 66.542 | 66.537 | 8 |

Every other run that logged the kick continued 957-2737 records past it
(cutoffs 112-990 s). Runs 92/96/97/99 died before any kick (57-76 s).

- Classification: early cluster is a silent reset within milliseconds
  of the deferred MDP probe's hardware path (splash footswitch,
  `mdss_hw_rev_init`, then `mdss_hw_init`, `mdss_mdp.c:3114-3164`).
  Consistent with an unclocked/unpowered MDSS access hanging the bus and
  a firmware watchdog reset, matching the existing run62-64 workaround
  note (`mdss_mdp.c:1813`) and run104's external abort. `[INFERENCE]`:
  asynchronous text capture means the faulting access may follow the
  last stored line; the exact access is not identified.
- Late cluster (107-160 s) remains separate and unexplained.
- [ ] Add direct-eMMC markers around each MDP re-probe hardware access
  plus GDSC/clock state; reproduce the early reset to name the access.
- [ ] Fix power/clock ordering for the identified access, not skip it.

## Run109: SD card removed; late silent reset at display HAL start

- User removed the SD card; stock showed only `mmcblk0` (type MMC).
  RAM-booted the unchanged `boot-run108.img` (SHA256 `3566dd33…`) under
  run109 after archiving run108's partition (hash-equal) and preclear.
- Zero `Card stuck` / `error -110` lines: the SD wedge is gone. MDP
  re-probe at 66.537 s now completed (display off, framebuffer 66.579 s),
  zygote at 110.1 s. Silent cutoff at 125.297 s; no ACKRESET1, SEA,
  panic or oops; four version1 slots CRC-valid (seq54/55, 122.9-125.1 s).
  Stock first observed at host elapsed 187 s; no port ADB.
- DSI PLL still logs 30 `failed to lock` lines (status 0/0xc) from 4.68 s.

### Late cutoffs follow display-stack startup

Last services/display lines in the final 3 s of each late silent run:

| Run | Cutoff (s) | Display event before cutoff |
|---|---:|---|
| run87 | 107.38 | `display-color-hal-1-0` started 107.28 |
| run88 | 110.67 | `display-color-hal-1-0` starting 110.41 |
| run89 | 122.85 | `display-color-hal-1-0` started 122.46 |
| run91 | 122.30 | `surfaceflinger` started 120.15 |
| run93 | 135.96 | `display-color-hal-1-0` started 134.77 |
| run94 | 122.56 | `mdss_fb_open` by `mm-pp-dpps` 119.77 |
| run95 | 156.76 | `display-color-hal-1-0` started 156.49 |
| run98 | 126.10 | `mdss_fb_open` by HAL at 126.10 |
| run104 | 161.24 | `display-color-hal-1-0` started 158.92 |
| run106 | 130.03 | `display-color-hal-1-0` started 128.54 |
| run109 | 125.30 | `display-color-hal-1-0` started 124.90 |

- Run85 ended 1.6 s after `mdss_dsi_cmds_tx: failed to call cmd_dma_tx`.
  Early cluster (102/105/108) ends inside the MDP re-probe.
- `[INFERENCE]` Both clusters coincide with first MDSS hardware use:
  kernel re-probe early, userspace framebuffer open/power-on late.
  Correlation only; the faulting access is not identified. The MDSS
  port predates run84, so this is the existing driver, not a post-run85
  regression; the only MDSS-area change since is the DSI PLL RESETSM value.
- [x] Gate display HALs (hwcomposer, display-color, surfaceflinger) on an
  unused tag, init-only, to test whether late resets disappear — done as
  run110 below.

## Run110: display stack gated; reset recurs in kernel MDP re-probe

- Init-only change on the run108 kernel payload (`580ea3c7…`, cmdline
  identical, 665 CPIO records): new `ANDROID_DISPLAY_GATE` stubs
  `android.hardware.graphics.composer@2.1-service.rc`,
  `vendor.display.color@1.0-service.rc` and `/system/etc/init/
  surfaceflinger.rc`. Init SHA256 `78423028…`, boot `8731c440…`.
- Gate provably held: three `DIAG: display gate rc override … errno=0`
  lines; zero starts of `vendor.hwcomposer-2-1`, `display-color-hal-1-0`
  or `surfaceflinger` in the whole log. HAL-gate (gatekeeper) retained;
  no deadline; SD card still removed.
- Silent reset at 62.668 s, 0.22 s after the deferred MDP re-probe kick
  at 62.448 s (`mdss_mdp_defer_kick_fn`), inside DSI panel parse
  (`mdss_dsi_parse_dcs_cmds` lp-mode on/off, refresh-rate-range reads).
  No ACKRESET1, panic, oops or SEA; four version1 slots CRC-valid
  (seq26/27, 60.1-62.2 s). USB 198,798 bytes; readable prefix 201,869.
  Stock first observed at host elapsed 56.88 s; no port ADB.
- Verdict: the reset needs no userspace display stack at all — this boot
  never started hwcomposer, display-color or surfaceflinger, yet died in
  the same deferred re-probe window as runs 102/105/108. The resetter is
  below the HAL layer, in the kernel MDSS re-probe path. The late-cluster
  correlation (display HAL start → death) is not exonerated — this boot
  never reached that window — but a userspace-display trigger is no longer
  required to explain the resets.
- [x] Add direct-eMMC markers around each MDP re-probe hardware access
  plus GDSC/clock state — built and booted as run112 below.

## Run112: marker kernel boots; re-probe passes, late reset, tags empty

- Host built `e5322d6a7` (marker patch): payload `0f72ccf3…` (+158 B),
  banner `6.12.93-4k-ge5322d6a786c`, DTB/config untouched. Packaged as
  `boot-run112.img` (`24dd2809…`) with unchanged `init-run110`
  (display gate held: zero hwcomposer/display-color/surfaceflinger
  starts) and identical cmdline. Preclear zero-verified on a partition
  hash-equal to run110 evidence.
- Re-probe kicked at 68.587 s and PASSED (framebuffer 68.649 s); boot
  ran to a silent reset at 132.415 s amid routine service starts
  (gatekeeperd, update_engine) plus ART-internal SIGSEGV deliveries and
  routine exits. No ACKRESET1, panic, oops or SEA; four version1 slots
  CRC-valid (seq57/58, 129.7-132.0 s). USB 561,718 bytes. No port ADB.
- Marker pr_infos ran (probe-entry, rev_init, hw_init begin rev=269484032,
  hw_settings begin, intf_sel reads) but all 16 eMMC slots at `0x3F80000`
  read zero: the `filp_open` path failed silently under both tried
  names. The probe ran; the writer did not land. Fix queued: try
  by-name plus both mmc enumerations with `pr_err` on open/write
  failure and a readback verify (O_RDWR), so the next boot says why.
- [x] Markers-around-re-probe item from run110 — built and booted, but
  verdict deferred: this boot never took the early-cluster path, and
  the tags were empty. A late-cluster data point (132 s, gate held).

## Run113: writer fix names it — kworkers have no fs, all opens ENOENT

- Host built `2c3c39b67` (writer fix): payload `d644bb5a…`, banner
  `6.12.93-4k-g2c3c39b6786d`, DTB/config untouched. Packaged as
  `boot-run113.img` (`34f35ec8…`) with unchanged `init-run110`
  (display gate held: zero display starts) and identical cmdline.
  Preclear zero-verified on a partition hash-equal to run112 evidence.
- Silent reset at 153.953 s amid routine service starts (gatekeeperd,
  traced), same profile: no ACKRESET1, panic, oops or SEA; four
  version1 slots CRC-valid (seq61/62, 149.9-152.0 s). USB 551,649
  bytes. No port ADB. Another late-cluster point (154 s, gate held).
- Writer fix worked as a diagnostic: `mdss_mdp: marker open failed
  err=-2` (ENOENT) on every path, repeatedly from 78.87 s. Init's own
  opens of the same nodes succeed and no "no logdump" line appears,
  while ueventd is up — so `/dev` is populated; the opener's context
  is the problem. Deferred probe runs in a kworker, which has no
  fs_struct, so absolute-path resolution has no root: ENOENT for
  every name. Fix queued: borrow init's root under task_lock and open
  with `file_open_root` (both exported, declared in tree headers).
- [x] Writer-fix item from run112 — built, booted, root-caused the
  silent writer. Marker attribution still needs a boot with the
  root-borrowing opener, preferably one that takes the early path.

## Run114: pre-kick death — re-probe is not necessary either

- Root-fix kernel (`2fc6e428…`, banner `gd49bf21590bd`) packaged as
  `boot-run114.img` (`7d2b4655…`) with unchanged `init-run110` and
  cmdline; preclear zero-verified on a partition hash-equal to run113.
- Silent reset at 62.3 s in second-stage early-init (SetupCgroups).
  A slow secilc policy compile (~44.5-58.2 s, no kernel silence anomaly
  — heartbeats print every 10th sample, none missing) put this boot
  ~20 s behind schedule: first probe deferred at 12.78 s, kick due
  ~72.8 s, death well before it. No kick, no re-probe, no display
  userspace, no ACKRESET1/panic/oops. Snapshots CRC-valid (seq27/28,
  59.6-61.7 s); USB 175,560 bytes. No port ADB.
- Markers untested again: no tags AND no `marker open failed` pr_errs,
  consistent with the probe never running. The `file_open_root` fix
  still awaits a boot that reaches the re-probe.
- Falsification: run110 killed display-userspace necessity; run114
  kills re-probe necessity. The reset fires in at least three contexts
  (pre-kick like 92/96/97/99, inside re-probe like 102/105/108/110,
  post-display-HAL like 87-89/91/93-95/98/104/106/109/112/113) with
  healthy progression to the cutoff every time.
- PON reason1 reads `0x21` in every run including this one, but it is
  sampled at 1-15 s of each port boot, always after `adb reboot
  bootloader` + `fastboot boot` — constant by construction, so it
  cannot attribute the silent reset as currently sampled. Parked.
- Next: (a) re-boot the root-fix image until an early-path run
  validates the markers; (b) widen below drivers — audit what pets
  the PMIC/RPM/APPSS watchdogs on stock 4.19 vs this 6.12 tree
  (DT + config + driver), since a traceless random-time reset fits a
  watchdog better than any driver access now.

## Watchdog audit: stock pets one, the port builds none

- Stock 4.19 (live, read-only): no `/dev/watchdog*`, no
  `/sys/class/watchdog`; `msm_watchdog b017000.qcom,wdt: MSM Watchdog
  Initialized` with in-kernel `[msm_watchdog]` pet thread and
  `[irq/200-wdog-ti]` bark handler. All petting is in-kernel.
- This tree: `CONFIG_QCOM_WDT`/`CONFIG_PM8916_WATCHDOG` not set, no
  `msm_watchdog` driver exists in 6.12, no WDT node in `msm8953.dtsi`
  / `pm8953.dtsi` / tissot DTS, no petter anywhere (RPM/remoteproc
  kicks are IPC doorbells, not pets). `WATCHDOG_HANDLE_BOOT_ENABLED`
  idles with zero registered devices. Gap is in the fragment, not a
  merge accident.
- Hypothesis: firmware arms a WDT (normal Qualcomm boot state); stock
  pets it, the port never does → bark unheard, bite = traceless reset
  at firmware-programmed intervals. Variance (57-990 s) vs fixed
  timeout is unexplained — possibly bootloader dwell (countdown starts
  in XBL, our clock starts at kernel entry) and/or RPM-side petting of
  the PMIC WDT varying with system activity.
- Decisive test, no kernel rebuild for step one: dump the HW state at
  every boot — APPS WDT EN/STS/BARK/BITE via `ramoops_probe` (~0.4 s),
  PMIC POFF1/POFF2 + WDT S1/S2/S2CTL/S2CTL2 in the PON DIAG line.
  Queued as run115 (`fs/pstore/ram.c`, `drivers/power/reset/qcom-pon.c`,
  reads only). If EN=1/S2-enabled: enable driver + DT + pet loop and
  see deaths stop. No Kconfig/DT change in the dump commit.

## Run115: both watchdogs disarmed — theory dead for our boot path

- Host built `388532419` (WDT dumps): payload `c5f37244…`, banner
  `6.12.93-4k-g388532419224`, DTB/config untouched. Packaged as
  `boot-run115.img` (`5fbff13a…`) with unchanged `init-run110`
  (display gate held) and identical cmdline. Preclear zero-verified
  on a partition hash-equal to run114 evidence.
- Silent reset at 136.54 s amid routine exits (timekeep, pm-service),
  same profile: no ACKRESET1/panic/oops/SEA; snapshots CRC-valid
  (seq61/62, 134.1-136.3 s). USB 564,337 bytes. No port ADB.
- `DIAG apps_wdt en=00000000 sts=00000000 bark=00000000 bite=00000000`:
  APPS WDT never programmed. PMIC: `poff1=0x02 poff2=0x00` (not
  PMIC_WD/UVLO/OTST3), `wd_s1=0x0f wd_s2=0x03` but `s2ctl2=0x00`
  (S2 reset master-disabled): PMIC WDT cannot reset the phone.
- Stock regmap debugfs confirms live: `spmi0-00` PON block reads
  `0808=21 080c=02 080d=00 0854=0f 0855=03 0856=08 0857=00`
  (archived as `run115-pm8953-pon-regmap.log`). This opens post-reset
  cause reads from stock with no bootloader in between — but note the
  confound: every port boot follows `adb reboot bootloader`, so
  PON/POFF as sampled in port logs describe that transition, not the
  silent reset. A clean A/B (post-silent-reset stock dump vs
  post-orderly-reboot stock dump) is still open.
- Residual hole: the APPS dump used KPSS offsets; an APCS-layout WDT
  would read zero there while armed. Extended the dump with a second
  `apps_wdt2` line at 0x8/0xc/0x10/0x14 (queued, unbuilt).
- [x] WDT-dump item — both blocks disarmed during our boots; neither
  can be the resetter unless re-armed mid-boot by TZ/RPM (no evidence).
  Watchdog theory closed for the fastboot-boot path.

## Run116: borrowed root fails too; PON A/B identical; KPSS confirmed

- Root-fix kernel (`2fc6e428…`, banner `gd49bf21590bd`) packaged as
  `boot-run116.img` (`903ec706…`) with unchanged `init-run110`
  (display gate held: zero display starts) and identical cmdline.
  Preclear zero-verified on a partition hash-equal to run115 evidence.
- Silent reset at ~134.3 s, last line `mdss_fb_open` by `mm-pp-dpps`
  (same adjacency as run94; run110 died with no fb activity at all, so
  this stays coincidence-grade). No ACKRESET1/panic/oops. Snapshots
  CRC-valid (seq59/60, 130.3-132.5 s). USB 550,463 bytes. No port ADB.
- Re-probe kicked at 64.5 s and markers ran, but `file_open_root` on
  init's borrowed root failed ENOENT on all three paths — no "no init
  root" message, so the borrow itself worked and absolute resolution
  under it still failed (mechanism unexplained). VFS path abandoned.
- `apps_wdt2`: en2/sts2 zero, bark2/bite2 `0x7FFFF`/`0xFFFFF`. Stock
  pets via the KPSS offsets (downstream `msm_watchdog` writes
  `0x38`), which would be ineffective on an APCS block while stock
  never resets — so KPSS is the real layout, the WDT is truly off,
  and the APCS-offset values are GPTIMER-channel noise. Watchdog
  theory closed with both layouts covered.
- PON A/B experiment: post-silent-reset stock dump
  (`run116-post-silent-regmap.log`) vs post-orderly-reboot stock dump
  (`run116-post-orderly-regmap.log`) are byte-identical at every
  interesting offset (`0808=21 080c=02 080d=00 0854=0f 0855=03
  0856=08 0857=00`). PON/POFF cannot distinguish the silent reset
  from an orderly reboot — exhausted as an attribution path.
- Next: markers rewritten onto reserved RAM via `ramoops_diag_mark()`
  (no VFS, no task, works from any context; same 0x3F80000 slots, so
  decodes unchanged). Queued as run117.

## Run118 (queued): gate late mdss_hw_init on runtime-PM suspend

- Runs 116/117 died within ~30 ms of `mdss_fb_open` by `mm-pp-dpps`
  followed by `mdss_hw_init` register writes, after the re-probe had
  completed and powered the MDP back down (`intf_sel=0`, splash
  footswitch off). Touching MDP registers while the domain is down
  hangs the bus. The two late `mdss_hw_init` callers now skip their
  register writes when runtime PM reports suspended, emitting a skip
  marker plus `pr_err` instead; the probe path is untouched
  (byte-identical, still acquires `mdp_rev`).
- `drivers/video/fbdev/msm/mdss_mdp.c`: `MDSS_MARK_SKIP 0x80` slot
  added (tag `0x504B534D` "MSKP"); `mdss_mdp_idle_pc_restore` gates
  `mdss_hw_init(mdata)` on
  `pm_runtime_status_suspended(&mdata->pdev->dev)`; fall-through
  (`iommu_ctrl(0)` detach, `ctl_restore`, `idle_pc=false`) unchanged.
- `drivers/video/fbdev/msm/mdss_mdp_overlay.c`:
  `mdss_mdp_overlay_start` applies the identical guard on
  `&mfd->pdev->dev`; the `pm_runtime_get_sync` block and the
  iommu-attach/`EARLY_MAP`-clear/detach surround are unchanged.
- Deviations from the inline plan found during execution: (1) the
  mark wrapper is file-`static` in `mdss_mdp.c`, so the overlay side
  calls global `ramoops_diag_mark(0x80, 0x504B534D, 0)` directly
  (identical RAM bytes; new `#include <linux/pstore_ram.h>`);
  (2) second-opinion review caught a P0 (`MDSS_MARK_SKIP` used 600+
  lines above its `#define`) — fixed by moving the whole slot table
  verbatim to the file top and retargeting two pointer comments.
- Verification so far: `checkpatch.pl --strict` clean (0/0/0);
  second-opinion review PASS on the reworked diff (active path
  byte-identical; fall-through is status-quo-ante since early return
  would unbalance the iommu ref; `ctl_restore` skips powered-off
  ctls per `mdss_mdp_ctl.c:4360`).
- Known residual risk: the skip still falls through to
  `ctl_restore`/`ctl_start`/smmu-attribute. If run118 hangs *with*
  the SKIP mark set, the gate is insufficient and the follow-up is
  power-up sequencing, not more gating.
- Not yet built (macOS host cannot build): needs the Linux-host
  `make O=out ARCH=arm64 LLVM=1 Image.gz
  qcom/msm8953-xiaomi-tissot.dtb`, packaging as `boot-run118.img`
  via `package-diag-boot.py`, then preclear/capture/pull-evidence.
  Pass criteria: survival past the 134-137 s window, or SKIP mark
  (`0x80=0x504B534D`) plus skip `pr_err` in kmsg; the re-probe path
  must still complete with `mdp_rev=0x10100000`.

### Run118 revision: observe the late path, don't guess it

- Review of f834a9b1e: the `mdss_mdp_overlay_start` guard tests
  `&mfd->pdev->dev` right after `pm_runtime_get_sync()` on that same
  device succeeded (failure jumps to `end`); fb0 is a DT child of
  mdss_mdp, so the parent resumed too. It can never fire — removed.
  The `idle_pc_restore` guard (MDP device) is kept.
- The premise is half-supported: run116/117 `-logdump.log` (the
  userspace kmsg logger, ahead of the 2 s snapshots) end with
  `mdss_fb_open by mm-pp-dpps` -> `hw_init begin` -> `hw_settings table
  begin`, then 45 ms of unrelated lines in run117. `hw_init` had no end
  print, so death inside hw_init vs later (ctl_start / panel on with
  DSI PLL0 unlocked) is undecided. `Footswitch failed to enable`
  appears in no run110-117 log, so "domain down" is unproven. Run115
  (136.5 s) had no fb_open; runs 110/114 died before any MDP probe.
- RAM marks cannot see a ~45 ms death (snapshot period 2 s); the
  kmsg logger lands lines in logdump within ms. So breadcrumbs are
  `pr_info`, prefix `DIAG118`:
  - `mdss_mdp_diag_pwr()` reads GCC (always clocked): MDSS GDSCR
    PWR_ON (0x184d078 bit31), CBCR CLK_OFF of mdss ahb/axi/mdp
    (0x184d07c/080/088 bit31), plus MDP runtime-PM status. Logged at
    hw_init entry and before ctl_start.
  - `hw_init begin ... from %pS` names the caller (overlay_start vs
    idle_pc_restore); each `hw_settings[i] addr <- val` before the
    write; `hw_init end writes=N`.
  - overlay_start: EARLY_MAP clear, ctl_start rc, pp_resume rc,
    splash_cleanup rc; idle_pc_restore: ctl_restore pre/done.
- Package with `--append-cmdline ' panic=0'`: a Linux panic (e.g.
  SError from an unclocked access) then hangs instead of resetting
  (physical 10 s power-hold recovery; POFF should read KPDPWR_N 0x80).
  A reset at ~137 s anyway rules out Linux's panic path. Rationale:
  run116 A/B shows silent = PS_HOLD with WARM_RESET_REASON1=0x00
  (orderly stock reboot: 0x02); the port's mainline msm-poweroff drops
  PS_HOLD without setting the PMIC type (stock rest value 0x85A=0x08,
  DVDD_HARD_RESET), and panic->emergency_restart skips ACKRESET1 while
  smp_send_stop halts the snapshotter — a port panic has never been
  capturable in this pipeline.
- Readout: last `DIAG118` line = failing step; `gdsc_on`/`*_off` at
  that point = power truth; hang vs reset = panic vs firmware.

## Open defect (display, not reset): DSI PLL clock imbalance

- Every boot warns at ~2.5 s in `mdss_8953_pll_probe`:
  `mdss_dsi_pll0_pixel already disabled` + `clk_core_disable` WARN
  (reparent-orphans path), and the DSI PLL then fails to lock ~30x
  per boot. Non-fatal (boots run 130+s past it), present in all runs
  while deaths vary freely — not the resetter, but the likely root
  of the display misbehavior. Fix: balance enable/disable around
  provider registration. Tracked separately from the reset hunt.

