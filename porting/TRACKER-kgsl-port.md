# Tracker: kgsl 4.19 -> 6.12 port (tissot)

Goal: restore `/dev/kgsl-3d0` with the stock ioctl ABI so the vendor EGL
(`libGLESv2_adreno.so`, 2020 QC blob), sdm HWC and gralloc work unchanged
— the "GPU 3D" row of `porting/FAILING-COMPONENTS.md` (backlog #1).

Worktree: `../ack-kgsl`, branch `kgsl-port` (from `driver-fix` a1e4992dc).
The main tree stays untouched until this port has a boot verdict.
Last update: 2026-10-10 — Stage 3 in progress; successful KGSL probe recorded, capture/IOMMU investigation remaining.

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
  `69b20f3d...` (package-run41.json; payload e6a1ca... rebuilt #20).
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

## Run81: bandwidth attribute mapping (offline verified; boot pending)

- Add only the exact resolved `bw_mode_bitmap` path to the existing
  sysfs_graphics mappings. No new types/allow rules, no permissive mode.
  Failing-before compiled lookup returns generic sysfs; corrected lookup
  returns sysfs_graphics for both caps and bandwidth attribute.
  Merged compilation passes with init's flags; same five pre-existing
  neverallow violations without `-N`. Evidence: `run81-policy-check.log`.
- `boot-run81.img` sha256
  `853640cb9637f070374567cb252e9169c08360b45f6cfa9260ea6c1cffc0e17f`.
  Extracted-image comparison against run78: same kernel / cmdline / init
  and all other records; only debug CIL differs. Device effect unverified.

## Handoff to another machine

- Stop point: run80 verifies caps access; bandwidth attribute is the
  next reproduced composer blocker. Run81 is packaged and compile-
  checked only; do not describe it as boot-tested or boot-complete.
- Latest booted image is `snapshot60/boot-run78.img` (used for run80).
  Next image is `snapshot60/boot-run81.img`; control is the original
  `snapshot60/boot-run73.img`. Logs/evidence for runs78-80 are preserved.
- Preserve / transfer the real `snapshot60/base-guard-debug-fw.img`,
  `init-run32`, and all four `kdir-run73/` files. Do not reconstruct
  the policy-bearing base from captures or stock images.
- Next device step: read REFERENCE-boot-testing.md, archive any new
  device evidence, preclear with unused tag run81, then RAM-boot
  boot-run81.img and capture USB + ADB/logcat. Verify BW parsing, then
  follow the next actual failure. Allow at least eight minutes for
  initial collection: the run79 control exposed adb after 240 seconds.
- Last controlled action returned the phone to normal ROM for a
  successful run80 root-logdump pull. Final handoff ADB check found no
  device (`snapshot60/handoff-device-state.log`); current kernel is
  unverified. No further boot / clear / flash was attempted.
- Deferred kernel work remains: raw display markers collide with
  ramoops; pstore retries cannot resolve PARTLABEL and synthetic panic
  is unsafe; arbitrary MDP delay and removed idle-PC restore are not
  production fixes. Keep kernel unchanged until policy boot evidence
  is collected; no cause is established for run78's early return.


## Boot economy (AGENTS.md)
One change per boot. `package-diag-boot.py` capture, verdict recorded here
with file+line evidence before any claim. Reverts are one-line documented.
