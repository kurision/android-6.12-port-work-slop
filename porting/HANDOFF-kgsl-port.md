# Handoff: kgsl 4.19 → 6.12 port (tissot) — mid Stage 2

For the next agent. Everything is committed on the `kgsl-port` worktree;
nothing depends on untracked files.

**Worktree**: `/home/kurision/development/kernel/ack-kgsl` (branch
`kgsl-port`, branched from `driver-fix` a1e4992dc). Main tree untouched.
Open it in an editor with: `code /home/kurision/development/kernel/ack-kgsl`.

**Commits**:
| | |
|---|---|
| `f3248eda0` | Stage 1: GPU node bound to kgsl exclusively, drm/msm claim removed |
| `904b29167` | Stage 1 boot package + verdict |
| `08aec7abf` | Stage 1 boot verdict recorded (PASS) |
| `7ba68117a` | Stage 2 WIP: driver vendored + compat shims (this handoff's base) |

**Progress tracker**: `porting/TRACKER-kgsl-port.md` — source-of-truth
table, churn inventory, stage list. Update it, don't duplicate it.

## Where we are

Stage 1 (DT exclusivity) is **CLOSED — booted and PASSED** 2026-10-10 on
snapshot59: KMS binds with no GPU component
(`msm_mdp 1a01000.display-controller: bound 1a94000.dsi (ops dsi_ops)`),
panel `0x9c`, zero oops/WARN, evidence channels all live. The vendor kgsl
driver must now claim that node.

Stage 2 (vendor the 90-file donor driver + compile-clean) is **~85% done,
not committed-clean**. The last actions were compat fixes in
`kgsl_gmu.c`/`gpu-iommu-compat.h` that have **not yet been recompiled** —
that is your first task.

## Your first command

```
cd /home/kurision/development/kernel/ack-kgsl
make -s O=out drivers/gpu/msm/ 2>&1 | grep -E "error:|warning: " | head -20
```

Expect a short tail of errors; iterate per-file as we did (see the
change log in `7ba68117a`'s message for the style). When the driver dir
builds clean:

```
ACK_TREE=/home/kurision/development/kernel/ack-kgsl JOBS=12 ./scripts/build-ack-tissot.sh
nm out/vmlinux | grep -i kgsl | head
```

Exit criteria for Stage 2: kernel links, the driver entry symbols
`kgsl_3d_init` (adreno.c:4219) and `kgsl_core_init` (kgsl.c:5615) present in
vmlinux (there is no `kgsl_init` symbol in this driver), `Image.gz-dtb`
produced, and the audit shows the GPU node **BUILT**
(`CONFIG_QCOM_KGSL`, `/soc@0/gpu@1c00000`, `drivers/gpu/msm/adreno.c`).

## What stage 2 already did (don't redo it)

**Vendored**: donor `kernel_xiaomi_msm8953/drivers/gpu/msm` (90 files,
74,471 lines) → `drivers/gpu/msm/`. UAPI header copied **verbatim**
(`include/uapi/linux/msm_kgsl.h` — that header is the 2020 blob's ABI
contract; do not touch it). Also copied: `include/linux/msm_kgsl.h`,
`include/linux/msm_adreno_devfreq.h`, `include/soc/qcom/cx_ipeak.h`,
`include/dt-bindings/regulator/qcom,rpmh-regulator-levels.h`.

**Wiring**: `drivers/Kconfig` sources `drivers/gpu/msm/Kconfig`;
`drivers/gpu/Makefile` has `obj-$(CONFIG_QCOM_KGSL) += msm/`;
`scripts/tissot-ack.config` has `CONFIG_NVMEM_QCOM_QFPROM=y`,
`CONFIG_ARM_SMMU=y`, `CONFIG_QCOM_KGSL=y`, `CONFIG_QCOM_KGSL_IOMMU=y`.
Build is **built-in (=y)** by design (single `fastboot boot` image).
Non-obvious gotcha already found: the donor's `depends on QCOM_QFPROM`
is `NVMEM_QCOM_QFPROM` in 6.12 — without the rename the whole driver is
Kconfig-invisible and merges silently drop it.

**Compat layers written (new, driver-private — keep them contained in
`drivers/gpu/msm/`):**
- `msm-bus.h` + `msm-bus-compat.c` — vendor `msm_bus_scale_*` client API,
  parses the vendor DT format (`qcom,msm-bus,name/num-cases/num-paths/
  vectors-KBps`), votes go to the icc path named **`gpu_icc_path`**; if
  no such DT path exists the vote is accepted and logged once (bus voting
  is perf/power only). Model taken from `xkhelper/aston-mainline`
  (kgsl on mainline 6.14) — reference if you need to extend it.
- `include/soc/qcom/secure_buffer.h` + `secure_buffer_compat.c` —
  `hyp_assign_table()` on `qcom_scm_assign_mem()`.
- `gmu-iommu-compat.h` — dead-path shims so the GMU/a6xx files compile
  (they are inert on a506; don't waste time on them, keep them building).
- `Makefile` gains `ccflags-y += -Wno-implicit-fallthrough` (vendored
  tree never written against the modern switch checks).

**Per-file API fixes already applied** (full list in commit
`7ba68117a`): Kconfig governor selects, `NVMEM_QCOM_QFPROM` dep,
`DEVFREQ_NAME_LEN`, guarded `MM_UNRECLAIMABLE` accounting,
`of_fdt_get_ddrtype`/`arch_setup_dma_ops`/`strlcpy`/`strtobool`
removals, GUP flags, `vm_flags_set/clear`, `DMA_BIT_MASK(64)`,
single-arg `__assign_str`, `irqreturn_t`, `dcache_*_poc` cache ops,
`timespec64`, `vmf_insert_pfn`, pm_qos-class removal, 1-arg
`class_create`, `of_platform.h` include, `iommu_map` gfp arg,
cmd-db aux-data 2-arg conversion.

## What remains (stage 3, after the driver builds)

The DT glue is the next real chunk. The vendor GPU DT to harvest from is
`kernel_xiaomi_msm8953/arch/arm64/boot/dts/vendor/qcom/msm8953-gpu.dtsi`
(kgsl-3d0 node with clocks, bus vectors, pwrlevels, iommu context banks,
zap-shader region). Known items, in order:

1. **Clock names differ**: vendor uses `core_clk/iface_clk/mem_iface_clk/
   alt_mem_iface_clk/rbbmtimer_clk/alwayson_clk`; our mainline node in
   `msm8953.dtsi:1048` uses `core/iface/mem_iface/alt_mem_iface/rbbmtimer/
   alwayson`. Check whether the driver uses `devm_clk_bulk_get` (names
   then don't matter) before editing anything.
2. **Pwrlevels**: our OPP-v2 table is reusable — the donor reads
   `operating-points-v2` first (`adreno.c:989-990`), legacy
   `qcom,gpu-pwrlevels` second. Vendor values are in the dtsi above.
3. **Bus**: add `interconnects`/`interconnect-names = "gpu_icc_path"` to
   the GPU node, and a `mas_gpu` node to
   `drivers/interconnect/qcom/msm8953.c` (the provider has bimc/pcnoc/
   snoc/snoc-mm but **no gpu master today**). Until then the compat
   no-ops — GPU still functions.
4. **IOMMU**: our tree's `gpu_iommu` is `iommu@1c48000`
   (`qcom,msm8953-iommu`), the vendor DT used `qcom,kgsl-smmu-v2` at
   `0x1c40000` with two context banks. Driver uses the generic API, so
   verify the phandle/stream-id mapping works with the mainline node.
5. **Zap shader**: SCM `pas_auth_and_reset/init_image` exist in the ACK
   (`include/linux/firmware/qcom/qcom_scm.h:75-79`). Firmware staging:
   the diag ramdisk carries `lib/firmware/qcom/a506_zap.mdt`; kgsl
   requests the **flat** name `a506_zap.mdt` (`adreno_a5xx.c` zapfw) —
   decide flat copies vs a `qcom/` symlink at packaging time.

## Boot etiquette (from AGENTS.md — the scarce resource)

- One change per boot; `package-diag-boot.py` (usage in
  `porting/logging/README.md`), logdump partition pre-cleared with
  `porting/logging/clear-logdump.sh <tag>`; capture and decode before
  claiming anything; record the verdict in the tracker with file+line
  evidence.
- The snapshot59 flow that just worked: kernel from
  `scripts/build-ack-tissot.sh` → `kdir/` (`Image.gz`, `Image.gz-dtb`,
  dtb, `SHA256SUMS`) → `python3 porting/logging/package-diag-boot.py
  --base-image <snapshot58/base.img> --kernel-dir <kdir> --init
  out-snapshot58/diag/init --out boot-run1.img --report package-run1.json`
  → `fastboot boot` → `pull-run-evidence.sh 1 boot-run1.img`.
- USB capture needs pyserial: this host has no pip; use
  `uv run --with pyserial python3 porting/logging/usb-boot-capture.py …`
  and launch it **detached** (`setsid nohup …`) — killing the reader
  mid-run breaks the gadget.
- Never touch `porting/artifacts/` base images without checking git
  history (`.gitignore:186-193` ignores them; a deleted base costs the
  next build its packaging input).

## Reference trees (all verified read-only, none is a donor)

- `../kernel_xiaomi_msm8953` — 4.19.325 donor, SoC DT source.
- CAF `graphics-kernel` `GRAPHICS.LA.14.0.r7-01700-lanai.0` (codelinaro,
  fetchable by raw URL) — how CAF migrated kgsl to icc + dma_fence; its
  uapi is a strict superset of our donor's.
- `qualcomm-linux/kgsl` `gfx-kernel.le.0.0` — has A506 but private
  Qualcomm IOMMU API; anatomy reference only.
- `xkhelper/aston-mainline` `aston-6.14` — kgsl on mainline 6.14; the
  kgsl_bus.c icc design we copied.
- `../ack-6.6` — ACK android15-6.6, bare GKI: **no kgsl at all**. Do not
  let anyone resurrect the "port from 6.6" idea.

## Open decisions / risks to keep in view

- `priv->gpu == NULL` KMS path is now boot-proven; with kgsl bound the
  DRM adreno component is gone permanently on this tree — intended.
- ION is already in-tree (commit `a33336265`), so stock gralloc/HWC
  allocations work; EGL unlocks once `/dev/kgsl-3d0` probes.
- Vendor blob ABI is preserved by the verbatim uapi header; any *future*
  pull from a newer kgsl must re-run the uapi diff (superset test):
  add-only is safe, struct-layout changes are not.
