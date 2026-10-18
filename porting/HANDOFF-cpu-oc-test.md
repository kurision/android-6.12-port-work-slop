# Handoff — MSM8953 CPU bring-up (oc-test → 6.12), 2026-10-18

**Source-only session. Nothing is enabled or wired, and no kernel build, image
or boot was performed or is authorized.** All new drivers below are compiled
against this tree's real `out/.config` and committed disabled.

Authoritative scope, design, provenance and per-gate detail live in
[plan/CPU-oc-test-to-612.md](plan/CPU-oc-test-to-612.md). This file is the
session state: what is on disk, what was measured, what is next, and what must
not be touched. `plan/CPU-oc-test-to-612.md` is the reference for *why*; this is
the reference for *where*.

Goal: make the MSM8953 CPUs report and scale correctly on the 6.12 port, using
the donor `../oc-test` (`687ee893ae5d6fd61c69397ea157973e50c06714`) as the
reference. User-approved scope is **stock fused bin-2 range only
(652.8–2016 MHz), no OC and no undervolt interface**, one shared APCS PLL and
one eight-core CPUFreq policy.

## Where HEAD is

Base target ACK `24bcdc3ed0d0c3bbb3f01179cd7862bd426d17c4` (6.12.93). Branch
`master`. Commits added this session, newest last:

| commit | what it does |
|---|---|
| `60d877157` | APM (`msm8953-apm.c`) + memory-ACC regulator, disabled; adds the plan doc |
| `fa6073a73` | live component audit finding + root-candidate packaging scripts |
| `6b64d90a3` | SAW4 voltage/AVS provider (`msm8953-spm.c`) + `qcom,saw2.yaml` entry |
| `010690c36` | accept SAW4 AVS minimum level 0 (FTS2 floor maps to VSET 0) |
| `82a8b7a93` | SPM-backed PM8953 S5 APC rail regulator + AVS-limit child |
| `735e597e1` | CPR4 port scoping written into the plan before editing |
| `6536a1cb6` | `porting/build-test/kbuild-check.sh` single-object compile checker |
| `9eb29e925` | **CPR3 core + CPR4-APSS closed-loop regulator port** |
| `4f92fd644` | `KBUILD_CHECK_EXTRA` support in the compile checker |
| `1c0fbcf33` | dt-bindings: `qcom,apcc-msm8953.yaml` + `qcom,apcc-msm8953.h` |
| `9e107d1d0` | **CCF CPU clock provider `apcc-msm8953.c` + host test, disabled** |

No commit carries a co-author or assisted-by trailer. HEAD is this document's
own commit, on top of the two gate 3 code commits listed above.

Gate 3 added three commits: the binding header plus schema first, then the
driver, then the porting record. They only add new files and two lines of
Kconfig/Makefile; nothing in the tree depends on them yet.

Working tree is dirty from **another session** (run234 GPU/adb work):
`porting/HANDOFF.md`, `porting/FAILING-COMPONENTS.md`, `porting/README.md`,
`porting/REFERENCE-boot-testing.md`, `scripts/initramfs-diag/init.c` and
untracked `porting/artifacts/snapshot60/*`. Do not reset, revert or reformat
those; this session did not touch them.

## What is on disk (compiled, disabled, unwired)

| source | config symbol | state |
|---|---|---|
| `drivers/soc/qcom/msm8953-apm.c`, `include/soc/qcom/apm.h` | `QCOM_MSM8953_APM` | provider only; no DT node, no consumer |
| `drivers/regulator/qcom-msm8953-mem-acc.c` | `REGULATOR_QCOM_MSM8953_MEM_ACC` | provider only |
| `drivers/soc/qcom/msm8953-spm.c`, `include/soc/qcom/msm8953-spm.h` | `QCOM_MSM8953_SPM` | SAW4.1 MMIO/AVS; no DT node |
| `drivers/regulator/qcom-msm8953-spm-regulator.c` | `REGULATOR_QCOM_MSM8953_SPM` | PM8953 S5 rail + AVS-limit child; no DT node |
| `drivers/regulator/cpr3-regulator.c`, `cpr3-util.c`, `cpr3-regulator.h`, `cpr4-apss-regulator.c`, `include/linux/regulator/cpr3-uv.h`, `include/linux/regulator/msm-ldo-regulator.h` | `REGULATOR_CPR3`, `REGULATOR_CPR4_APSS` | closed-loop CPR4; depends on the three providers above; no DT node |
| `drivers/clk/qcom/apcc-msm8953.c`, `include/dt-bindings/clock/qcom,apcc-msm8953.h` | `QCOM_CLK_APCC_MSM8953` | shared APCS PLL + 3 mux-dividers + corner-mapped rail voting; no DT node |

Every adaptation from the donor is listed in the plan under "Remaining
implementation / review gates", gate 2. The load-bearing ones: the donor SPM
header is replaced by the SAW4 provider, `msm_spm_probe_done()` became the real
`msm8953_spm_probe_done()`, `list_corner_voltage` is dropped (absent from the
6.12 `struct regulator_ops`) and the five `msm_spm_avs_*_irq` sites were removed
because all of them are `CPR_CTRL_TYPE_CPR3`-only and MSM8953 is CPR4 — not
stubbed.

**The CPR regulator deliberately keeps the donor corner encoding.**
`list_voltage(sel)` returns `sel + CPR3_CORNER_OFFSET` (1..N) and `set_voltage`
reads the core's min/max as corner(+offset). These are *not* microvolts. The
CPR DT constraints (`regulator-min/microvolt` = 1, max = 9) and the donor
consumer both speak that encoding. Do not "fix" it to microvolts.

## Measured baseline on the current port kernel

Ground truth for the state being replaced, read from the archived port logdump
that matches the running kernel (`6.12.93-4k #22 SMP PREEMPT` at
`root-audit-20261018T145300Z/preboot-logdump.bin:4`):

| line | value | meaning |
|---|---|---|
| `:160` | `cpuclk pll mode=00000000 lock=0 l=0 user=0000000f rate=0 kHz` | **the APCS HF PLL is not programmed and not locked** |
| `:161` | `c0 cfg=00000401 src=4 div=1` | CPU0-3 mux on src 4 = GPLL0 |
| `:162` | `c1 cfg=00000000 src=0 div=0` | CPU4-7 mux on src 0 = XO |
| `:163` | `cci cfg=00000403 src=4 div=3` | CCI mux on src 4 = GPLL0 |
| `:172` | `c1 switch: cfg=00000401 update_done` | the pstore diagnostic moved c1 from XO to GPLL0 |

So on the current port no cluster runs from the APCS PLL, CPU4-7 start on the
19.2 MHz XO, and only the diagnostic in `fs/pstore/ram.c` gives them a usable
clock. That diagnostic is also what the verified run234 GPU baseline runs on —
see gate 4 below before touching it.

## What is next

Order matters: each stage depends on the one before. Keep everything disabled
and unwired until the whole stack is ready, then enable in one reviewed step.

1. **Gate 3 — done as source.** `drivers/clk/qcom/apcc-msm8953.c` builds,
   is disabled and has no DT node, so nothing is wired yet. The decisions
   taken and the contract it imposes on the DTS are in the plan, gate 3.
2. **Gate 4 — retire the pstore diagnostic clock owner.** `fs/pstore/ram.c`
   `ramoops_debug_cpuclk()` (`:2181`) and `ramoops_cpuclk_c1_to_gpll0()`
   (`:2152`) ioremap `0xb011000` and write the c1 RCG (src 4, div 1) plus the
   core branch directly. Once a real provider owns these muxes, an external
   write makes CCF's cached `md->src`/`md->div` lie. The diagnostic must not be
   removed before the provider works, or CPU4-7 are left on XO.
3. **Gate 5 — CPU-only DTS + config.** APC rail, AVS child, SPM, APM, ACC, CPR
   and APCC nodes, CPU `clocks`/`clock-names`, and the CPU OPP table, as a CPU
   only include that composes with the navigation session's board DTS instead
   of overwriting it. Then `CONFIG_CPUFREQ_DT` etc. The CPU nodes must not
   declare `cpu-supply`: the clock provider owns the corner-encoded rail.
4. **Gate 6 — thermal.** TSENS is disabled; do not treat PMIC/battery
   temperature as CPU die temperature, and do not run sustained high-OPP stress
   before SoC temperature exists.
5. **Gate 7 — CPUIdle**, later, with its own PSCI conversion.

Gate 1 (SPM/AVS + APC rail sources) is done as sources; only their DT
declaration is outstanding and belongs to gate 5.

## Gate 3 inputs — verified against the upstream oracle today

Oracle: `msm8953-mainline/linux`, branch `alikates/6.4/cpufreq`, commit
`de022aeef8daeec136132b3692dfb51b2d3b63ef` — `drivers/clk/qcom/apcc-msm8953.c`
and `arch/arm64/boot/dts/qcom/msm8953.dtsi`. Fetched and read this session; this
is a WIP branch and the driver is not upstream-merged. Its DVFS wiring is
unfinished: the upstream CPU nodes carry no `operating-points-v2`, and the apcc
node has none either, so upstream's OPP block never runs there.

Reusable, verified facts:

- **Binding IDs** (`include/dt-bindings/clock/qcom,apcc-msm8953.h`):
  `APCC_CPU0_CLK 0`, `APCC_CPU4_CLK 1`, `APCC_CCI_CLK 2`, `APCC_CPU0_PLL 3`,
  `APCC_CPU4_PLL 4`, `APCC_CCI_PLL 5`, `APCC_NUM_CLOCKS 6`.
- **DT node** (upstream `msm8953.dtsi`): `apcc: clock-controller@b011050`,
  `compatible = "qcom,apcc-msm8953"`, `#clock-cells = <1>`, and six
  `reg`/`reg-names` pairs in this order: `cpu4-rcg-clk` `0xb011050 0x10`,
  `cpu4-pll-clk` `0xb016000 0x50`, `cpu0-rcg-clk` `0xb111050 0x10`,
  `cpu0-pll-clk` `0xb116000 0x50`, `cci-pll-clk` `0xb1d0000 0x50`,
  `cci-rcg-clk` `0xb1d1050 0x10`. The driver ioremaps by the *clock* name and
  uses `fast_io`, `reg_stride 4`, `max_register 0x34` for a PLL and `0xc` for a
  mux. CPU nodes use `clocks = <&apcc APCC_CPU0_CLK>` (CPU0-3) and
  `<&apcc APCC_CPU4_CLK>` (CPU4-7) with `clock-names = "cpu"`.
- **Alpha PLL**: custom reg map `L_VAL 0x08, ALPHA_VAL 0x10, USER_CTL 0x18,
  CONFIG_CTL 0x20, CONFIG_CTL_U 0x24, STATUS 0x28, TEST_CTL 0x30,
  TEST_CTL_U 0x34`; config `l = 34, config_ctl_val = 0x200d4828,
  config_ctl_hi_val = 0x6, test_ctl_val = 0x1c000000, test_ctl_hi_val = 0x4000,
  main_output_mask = BIT(0), early_output_mask = BIT(3)`. All of this matches
  the donor `apcs_hf_pll` in `../oc-test/drivers/clk/msm/clock-cpu-8953.c`
  (`base 0xb116000`, same config/test values, same main/early masks), which is
  the strongest available confirmation that the two implementations describe
  the same hardware.
- **Mux-div**: three clocks at `0xb111050`, `0xb011050`, `0xb1d1050` using this
  tree's `clk_regmap_mux_div_ops` with `parent_map = {5, 4, 2}`,
  `hid_width = 5`, `src_shift = 8`, `src_width = 3`, `reg_offset = 0`,
  `enable_reg = 8`, `enable_mask = BIT(0)`. The enable register matches the
  donor's `APCS_ALIAS1_CORE_CBCR_OFF 0x8` / enable `BIT(0)`.
- **Parent map cross-check (important).** `md->parent_map[i]` is the *register
  src value* of parent `i`, and in this tree's
  `clk-regmap-mux-div.c:145,172,183` it is used both to write src and to decode
  a read src back to a parent. So upstream asserts parent 0 (the APCS PLL) is
  src 5. That is confirmed by the donor, which lists exactly one source for all
  three muxes: `MUX_SRC_LIST({ &apcs_hf_pll.c, 5 })` — the APCS PLL's early
  output. Parents 1 and 2 are `muxsrc4` = `GPLL0_EARLY` (src 4) and `muxsrc2` =
  `GPLL2_EARLY` (src 2), extra bring-up sources the donor does not use. Note
  the donor's own `early_initcall(cpu_clock_pwr_init)` writes `SRC_SEL 5` with
  the comment "Source GPLL0" — **that comment is wrong**; src 5 is the APCS PLL
  early output, and the port's own diagnostic agrees (`fs/pstore/ram.c:2222`
  decodes `src == 5` as "the PLL" and treats everything else as unknown).
- **Rate notifiers**: `cpu_mux_div_pll_notifier` (PRE_RATE_CHANGE on the PLL
  while it is mux-selected) and `cpu_mux_div_notifier` (PRE_RATE_CHANGE on the
  mux) implement the "raise the divider before raising the parent" ordering,
  because CCF would otherwise always change the parent first. Preserve the
  behaviour; the donor achieves the same by driving the RCG itself.
- **API surface** is all present in this tree and was checked: `alpha_pll_config`
  field names, `PLL_OFF_*`/`PLL_OFF_MAX_REGS`,
  `clk_alpha_pll_regs[CLK_ALPHA_PLL_TYPE_DEFAULT]`, `pll_vco`/`VCO()`,
  `struct clk_alpha_pll`, `SUPPORTS_DYNAMIC_UPDATE`,
  `clk_alpha_pll_configure`, `struct clk_regmap_mux_div`, `mux_div_set_src_div`,
  `struct dev_pm_opp_config`, `devm_pm_opp_set_config`. This tree's
  `clk_alpha_pll_ops` still has `.round_rate`, which upstream's override
  (`rounddown(rate, prate)`) relies on. `clk-regmap-mux-div.o` is already part
  of `clk-qcom-y`, so the new driver needs no extra `select`.

All four decisions below are now resolved; the reasoning and the gate-5
contract are written up in the plan, gate 3. The facts they rested on are
kept here.

Decisions to make deliberately, not by copying:

- **OPP block.** Upstream's `probe()` tail runs only if the apcc node has
  `operating-points-v2`, then does `devm_pm_opp_set_config()` with
  `genpd_names = {"cpr"}` and `clk_names = {"cci"}` plus
  `devm_pm_opp_of_add_table()`. That is the mainline `apcc`/`cpr` genpd model,
  which is **not** our CPR port: our CPR is a regulator and its consumer
  requests corner-encoded voltages. Upstream's DT has no OPP here either, so
  the block is dead code on this SoC. Plan is to drop it and drive the CPU OPP
  table from cpufreq-dt with `cpu-supply = <&apc_vreg>` and corner-encoded
  `opp-microvolt`; record whichever way it is resolved.
- **SoC matching.** Upstream reads the *root* node compatible
  (`of_find_node_by_path("/")` + `of_match_node`) to pick a PLL count — a
  workaround for the same driver serving msm8953/sdm450/sdm632. For a
  single-SoC port, do not copy the root-node lookup; match the device node.
- **PLL count / VCO oddity.** Upstream passes `num_plls = 1` for msm8953 and
  `3` for sdm632, and in `register_pll()` the `if (num_plls)` branch overwrites
  the msm8953 `VCO(0, 652800000, 2208000000)` with `apcc_sdm632_pll_vcos[0]` =
  `VCO(0, 614400000, 2016000000)`. That looks like an upstream bug; the donor's
  `apcs_hf_pll` uses `min_rate 480000000 / max_rate 2784000000`. For our
  stock-bin-2 scope the honest range is 652.8–2016 MHz. Flagged, unresolved —
  decide and record.
- **Extra mux parents.** With three parents,
  `mux_div_determine_rate`/`__mux_div_set_rate_and_parent` can pick GPLL0 or
  GPLL2 for a rate the PLL "rounds badly", which would silently bypass the
  voltage/OPP path. Decide whether to keep all three parents or constrain the
  port to the PLL parent the donor uses.

## Verification available in this session (and its limits)

Single-object compile check against the existing `out/` build tree — this is
what "compile-verified" means throughout the plan:

```
KBUILD_CHECK_EXTRA='-DCONFIG_REGULATOR_CPR3 -DCONFIG_REGULATOR_CPR4_APSS' \
  porting/build-test/kbuild-check.sh drivers/regulator/cpr3-regulator.c ...
```

The extra `-D` is needed because `out/.config` (run164) predates these symbols;
the checker takes the saved command from `out/drivers/regulator/.core.o.cmd`
and re-points its source-tree paths at the repo. Toolchains present:
`clang` 23.1.3 and `aarch64-linux-gnu-gcc` 16.2.0. Strict
`scripts/checkpatch.pl` is clean (0 errors, 0 warnings) on every file added or
changed.

Host tests, all software-only: `porting/build-test/test-msm8953-apm.py`,
`test-msm8953-mem-acc.py`, `test-msm8953-spm.py`,
`test-msm8953-spm-regulator.py`, `test-msm8953-apcc.py`. They compile the
actual C functions against host MMIO/IPI/regmap/regulator mocks. They prove
nothing about probe, real timing, IPI delivery, supplier lifetime or
hardware. `test-msm8953-apcc.py` covers the corner plan lookup, the
above-plan refusal, the shared-rail vote and the rollback on regulator
failure. `qcom,saw2.yaml` was only parsed for syntax; `qcom,apcc-msm8953.yaml`
passed `make dt_binding_check` with dtschema installed. `test-msm8953-spm.py`
currently fails to build its host mock on this toolchain (`READ_ONCE`,
`EPROBE_DEFER` undeclared) and was not touched by this session.

### Build test, run238 (2026-10-18, authorized, host only)

Built on a staged copy of this tree, `/home/kurision/development/kernel/ack-staged-run238`
(`git archive HEAD` plus the fragment), because the repo root carries in-source
build residue and kbuild refuses an `O=` build there. The repo itself was not
cleaned. Every file under test was compared with `cmp` before building.

Toolchain per `BUIL_TISSOT.md`: rustc 1.99.0 from the stable toolchain, the
cached bindgen 0.73.2, libclang 22.1.8, `RUSTFLAGS_AUTOFDO_CLANG` with the
`-Zdebuginfo-for-profiling` spelling. Note the drift: the system clang is
23.1.3, not the 22.1.8 the table records.

Config: seeded from `kdir-run236/Image.gz` with `extract-ikconfig`, merged with
`porting/build-test/apcc.config`, `olddefconfig`. `scripts/diffconfig` against
the run236 config is exactly the seven intended symbols and nothing else:

```
QCOM_CLK_APCC_MSM8953 y       QCOM_MSM8953_APM y
QCOM_MSM8953_SPM y            REGULATOR_QCOM_MSM8953_MEM_ACC y
REGULATOR_QCOM_MSM8953_SPM y  REGULATOR_CPR3 y
REGULATOR_CPR4_APSS y
```

`REGULATOR_CPR3` has to be requested explicitly: `REGULATOR_CPR4_APSS` depends
on it rather than selecting it, so olddefconfig drops the CPR4 block without
it. All seven are `=y` in the embedded config of the built image
(`snapshot60/run238-embedded.config`).

- `Image.gz` built, 20044788 bytes, log `snapshot60/run238-build.log`.
- All six port drivers are in `vmlinux` (`apcc_msm8953`, `cpr3_regulator`,
  `cpr4_apss`, `msm8953_apm`, `msm8953_spm`, `msm8953_mem_acc`).
- `W=1` is now clean for `drivers/regulator/`, `drivers/clk/qcom/` and
  `drivers/soc/qcom/`. It was not before: three unused-local errors in the
  CPR3/CPR4 port, fixed in `399bedbc5`. Remaining `W=1` output is kernel-doc
  noise inherited from the vendor comments, not errors.
- The built DTB differs from the run236 one in exactly one property:
  `touchscreen-size-y` 2041 -> 1920, from commit `ae580fc8a` in this tree, not
  from this session. A boot image packaged from this tree would therefore not
  carry the verified run236 DTB. Resolve that before any boot test; the panel
  geometry is a hardware fact, do not guess it.

Nothing was packaged, flashed or booted.

Branch placement: these commits are on `combined`, which the repo was switched
to during this session. `master` still points at the pre-gate-3 handoff commit,
so `master` is four commits behind and needs a fast-forward or cherry-pick
depending on which branch the port is meant to live on. Not done here, because
moving a branch is the user's call.

## Constraints to keep

- **No kernel build, no image, no flash, no boot** without the user explicitly
  authorizing that step. A passing build never authorizes a boot.
- Do not edit the navigation-button session's board DTS, and do not change the
  shared phone's boot state. Do not test the prepared root candidate or touch
  logdump; coordinate with the user first.
- Only commit edits; no co-author or assisted-by trailers.
- Report "unverified" for anything not reproduced on device. Boot cycles are the
  scarce resource.
- Before concluding anything, check local history for a prior fix and check
  upstream/AOSP sources — several subsystems on this port were already solved
  once and the answer was in the history.

## Unverified / open

- Nothing in this CPU stack has run on hardware *in any functional sense*. The
  run238 boot proves the whole block compiles, ships and boots; it does not
  probe a driver, set a clock rate or vote a corner. See "run238 boot" below.



Base `boot-run237.img` (`aa2c85a3…`), because that base reaches the ROM with adb.
Packaged `boot-run238.img` (`cc2e3c9b…`) with
`porting/logging/package-diag-boot.py --keep-stock-console` and the run237
`init`. `fastboot boot` only, nothing flashed.

Everything except the kernel payload is provably identical to the base: ramdisk
sha256, init sha256, cpio record count, cmdline, and the DTB — the packaged dtb
is byte identical to the one inside `boot-run237.img`. That also retires the
panel-size worry recorded above: `touchscreen-size-y` 1920 is what run237
already shipped; 2041 was only in run236.

Device evidence, `snapshot60/run238-summary.json` and `run238-live/`:

- `fastboot` send OKAY 0.929 s, boot OKAY 1.196 s.
- `/proc/version` on the device is exactly the banner of the image built here,
  `#3 SMP PREEMPT Sun Oct 18 23:32:56`, so the port kernel that booted is this
  build and not run237's.
- `/proc/config.gz` pulled from the running kernel: all seven symbols are `=y`,
  so `apcc-msm8953.c`, the CPR3/CPR4 port, APM, SAW4 SPM, the memory-ACC and the
  SPM regulator are all live in the kernel that reached userspace.
- New boot id `791cef7c-f9dc-4b20-99fa-dddeef72793e`, `sys.boot_completed=1`,
  no kernel panic, no reboot and no kernel watchdog in the 23300-line all-buffer
  log. The crash buffer holds only stale Oct 9 ROM tombstones from an earlier
  boot, including one `droid.bluetooth` SIGABRT that is not this run.

No runtime evidence for the provider itself, as expected: it has no DT node, so
it never probes, never moves a mux and never votes a corner, and the pstore
diagnostic still owns the c1 mux exactly as before. Gate 4 is still the first
step that changes hardware behaviour.

Capture gap: this run produced no kernel console log. `dmesg` needs root and
this device has no `su`, the logcat kernel buffer is empty, and the diagnostic
USB gadget stream (`run238-usb.log`) is 0 bytes. The clock-state lines from
`root-audit-20261018T145300Z/preboot-logdump.bin` therefore could not be
re-observed; next run should pull the diag gadget or read pstore instead.

Still open:

- The PLL VCO range and the mux parent set are decided (plan, gate 3):
  652.8-2016 MHz, all three parents kept.
- The provider has a DT node from run239 but has still never probed, moved a
  mux or voted a corner; its PLL notifier has never fired. The regmap fix
  above is compile verified only.
- The device's state after run239: **stock 4.19**
  (`4.19.325-cip136-st20-perf-mglru-next-g5835eacd666d`), boot_id
  `d1843a2b-d6ac-4419-89ab-e8fb2ff82549`, after `adb reboot`. Nothing was ever
  flashed; every port boot was `fastboot boot`.

## run240 — the logdump read that ended the guessing

Booted `boot-run240.img` (`2b09aedb…`, same DTB as run239, only the regmap fix
in `f7ffd961f` differs). Android came up, adb came back, the screen was slow
again (load 14.4 before reboot), and the same two devices were still unbound.

Because the port kernel was launched with `ramoops.reset_capture=1` and then
rebooted, its console tail was sitting in the logdump partition. Reading
`/dev/block/mmcblk0p48` on stock with `su`, and decoding it, produced the
evidence three runs of inference could not:

- `run240-live/kernel-log.txt`, 115336 kmsg lines, is run240's full kernel log.
- `kernel-log.txt:479-480` is the whole failure in two lines:

      platform b116000.clock-controller: deferred probe pending: platform: wait
      for supplier /soc@0/cpr4-ctrl@b018000/thread/regulator
      platform b018000.cpr4-ctrl: deferred probe pending: platform: wait for
      supplier /soc@0/spmi@200f000/pmic@1/spm-regulator@2000/avs-limit-regulator

- The live SPMI enumeration in the same log lists only `pmic@0` and `pmic@2`.
  There is no `pmic@1` on this board.

Root cause, and it was never the DT's shape but its USID: the SoC level donor
file puts `pm8953_s5` under `qcom,pm8953@1`, but that is the generic variant.
The donor's **board** file, `mi8953/tissot/pmic.dtsi`, declares `qcom,pm8953@0`
for this phone. Fixed in `a0a6e785b`.

Lesson worth keeping: the donor SoC file and the donor board file disagree on
this USID, and only the live bus log says which one this board follows. The
regmap fix in `f7ffd961f` was real and independent, but it could not show up
because the rail it fixes was being requested from a PMIC that is not present.

Also from `kernel-log.txt`:

- `psci: [Firmware Bug]: failed to set PC mode: -1` (line 59).
- The pstore diagnostic's own measurement (lines 164-169) runs 1000000 loop
  iterations on every CPU before and after the c1 switch; that is the obvious
  suspect for the slow screen, and it predates this session.
- Clock state unchanged from the baseline: APCS PLL `lock=0 l=0`, c0 on GPLL0
  div 1, c1 on src 0, cci on GPLL0 div 3.

**Evidence loop that now works**: boot with `ramoops.reset_capture=1`, reboot to
stock, read the logdump partition with `su`, decode. No TTL adapter needed.
This is how every later gate should be verified.

Device after run240: stock 4.19, boot_id `223fcf9e-e04a-4fbc-8c58-e00c7629a90e`.
Nothing was ever flashed.

## run241 to run244 — the rail chain, and four separate faults

Four boots, each with the logdump read afterwards. The console log only became
readable once the port kernel's own capture could be pulled from stock, and
that is what turned guesses into answers.

| run | what it carried | what it showed |
|---|---|---|
| run241 | S5 moved to PMIC USID 0 | `probe ... failed with error -22`, no message from the driver |
| run242 | error messages added, DIAG spin measurement dropped | same bare -22; the per-CPU 1M-loop measurement gone |
| run243 | SPMI regmap created over the PMIC parent | still -22, now with `SPMI regmap creation failed` |
| run244 | regmap window widened past the PMIC base | ashmem present again, boot animation up but stuck |

Three faults, one per boot, all in the ported SPM regulator and all invisible
without a console log:

1. **The rail was on a PMIC that is not there.** The donor SoC file puts
   `pm8953_s5` under `qcom,pm8953@1`; the donor *board* file overrides that to
   `qcom,pm8953@0` for this phone, and the live SPMI bus agrees, enumerating
   only `pmic@0` and `pmic@2`. Fixed in `a0a6e785b`.
2. **The regmap window stopped at the PMIC base.** Every access is
   `spmi_base_addr` plus an offset reaching 0x6c, and regmap compares the
   absolute address against `max_register`, so the type register read at
   0x2004 was rejected. Fixed in `786e63b62`.
3. **The regmap was never created at all.** `__regmap_init()` switches on
   `config->reg_bits` and rejects the default arm with -EINVAL, and the
   config only set `max_register`. The SPMI base bus reads one address byte
   per register, so `reg_bits` is 8; mt6315 sets 16 because it uses the
   extended bus. Fixed in `a0616dc9e`.

Two port-level faults found on the way, both mine:

4. **The config resync dropped ashmem.** run242 and run243 had
   `# CONFIG_RUST is not set` and no `CONFIG_ASHMEM`, so SurfaceFlinger could
   not mmap its queue and the ROM never came up. Caused by re-resolving the
   config with an environment missing `RUST_LIB_SRC` and `LIBCLANG_PATH`,
   which `BUIL_TISSOT.md:82` warns about by name. `BUIL_TISSOT.md` is the
   documented wrapper and its required-symbol guard would have caught this;
   it was bypassed for the sake of preserving the run236 config, which was the
   wrong trade. Build through `scripts/build-ack-tissot.sh` from now on, with
   one fragment: `cat scripts/tissot-ack.config porting/build-test/apcc.config`
   because the wrapper merges exactly one and `apcc.config` is a delta.
5. **The GPU driver flooded the log.** `adreno_zap_stage()` printed one line
   per stage transition with `dev_info()` and no rate limit: 71162 of one
   boot's 118915 kernel log lines. The history settles it: commit `cd498fd1e`
   added it alongside prints that are deliberately rate limited
   (`kgsl_diag_submit()` keeps the first 50 then every 64th) or one-shot, so
   this one print was the exception, not the pattern. Removed in `2a9bac1c1`
   and verified absent from run244's vmlinux.

**Reading logdump without confusing boots**: the partition holds captures from
more than one boot. Sort by the `Linux version` banner and count only what
follows it, or you will attribute a previous run's log to the current one. That
mistake briefly made it look as if run244 still spammed zapstg.

Also from run244: the boot animation comes up and then stalls, `boot_completed`
never set, load average around 12. Its config differs from the run236 baseline
by `DEBUG_INFO_BTF` off and `RUST_INLINE_HELPERS` on, because the wrapper
rebuilds from `gki_defconfig`. A control build with the tissot fragment only,
no `apcc.config`, is the experiment that separates that from our symbols.

**What the first successful probe will and will not do.** With `a0616dc9e`
the APC rail probes for the first time. That probe is read-only: the port's
`qpnp_smps_init_voltage()` only reads the rail and deliberately leaves the
SPM's PMIC data as the bootloader programmed it (`reg->uv` is taken from the
read-back, no SPM write, matching the donor), and mode and step-rate init are
reads as well. The first write to that rail comes from the CPR4 controller
once it binds and programs a corner. So run245 is expected to be the first
boot in which anything moves the shared CPU voltage, and that is the thing to
watch: the logdump read after it should show the CPR's corner count and the
first voltage it programs.

Device after run244: stock 4.19, boot_id `bdb10da7-28a1-4081-8e44-1a1f2e6af574`.
Nothing was ever flashed.

## run239 — first boot of the wired CPU nodes, and what it broke

Gate 5a landed: `arch/arm64/boot/dts/qcom/msm8953-cpu.dtsi` (APCC clock
controller, SAW4, PM8953 S5 rail plus its AVS limit child, APM, memory-ACC
selector, CPR4 with the donor's per bin tables, CPU0-3 on `APCC_CPU0_CLK` and
CPU4-7 on `APCC_CPU4_CLK`), three new bindings, and `msm8953.dtsi` including
it. `dt_binding_check` clean on all four; `dtbs_check` reports no new warning
for any new node (the run cannot finish on this host: the installed
`dt-validate` rejects the kernel's dtb argument). The board file is untouched.

`boot-run239.img` (`0afa363b…`) on the run237 base, RAM boot only. It booted
Android and adb came back, but the wiring is not yet functional:

| node | result |
|---|---|
| `qcom-msm8953-apm` | bound |
| `qcom-msm8953-spm` | bound |
| `b116000.clock-controller` (APCC) | not bound |
| `b018000.cpr4-ctrl` (CPR4) | not bound |
| `pm8953_s5`, `apc_corner` | never registered |

Chain: no S5 rail -> no `apc_corner` -> CPR4 deferred on `vdd-supply` -> APCC
deferred on `vdd-cl-supply`.

Root cause found offline, in the port and not in the DTS:
`qcom_spm_reg_probe()` used `dev_get_regmap(pdev->dev.parent, NULL)`, but
neither the SPMI core nor the PMIC driver registers a regmap on the parent, so
every rail owned by this driver failed probe with "no parent SPMI regmap".
Fixed in `f7ffd961f` by creating it over the PMIC parent with
`devm_regmap_init_spmi_base()`, as `drivers/regulator/mt6315-regulator.c` does
for its own SPMI parent. Compile verified, W=1 clean, **not yet booted**.

What the DTS got right, from stock's own `regulator_summary` (the working
donor kernel): `pm8953_s5` is enabled at 1090 mV with 400-1140 mV limits and
`apc_corner` exists, i.e. the copied USID-1 node, register window and voltage
range are the ones that work on this phone. `test-msm8953-spm.py` still fails
to build its host mock (`READ_ONCE`, `EPROBE_DEFER` undeclared); pre-existing,
not touched.
