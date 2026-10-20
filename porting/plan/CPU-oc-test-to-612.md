# MSM8953 CPU bring-up from oc-test

> **Current state: CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUIL_TISSOT.md](../../BUIL_TISSOT.md).
>
> The per-run evidence this document cites (boot images, kernel directories,
> init binaries, logdumps) is no longer in the repository; it is
> git-ignored and disposable, and the boot images are in
> ../ack-kgsl-artifacts.

## Latest status after run258 (supersedes historical implementation status below)

The CPU stack exists and run258 booted, but APCC failed on CPU4/mailbox resource
overlap and CPUFreq remained absent. The user approved the subsequent source
repair: narrow MSM8953 mailbox ownership, restore PLL MX-AO SVS voting, implement
checked voltage-first firmware handoff, retain safe power references on errors,
and remove the pstore clock writer. That batch is implemented and host/focused-DT
checked, **not kernel-built or hardware-tested**. No idle/suspend/TSENS changes.
See [current CPU handoff](../HANDOFF-cpu-bringup-2026-10-19.md) for exact scope,
source hashes and the separately authorized build/boot gates. Prior design
descriptions below (alpha PLL operations, diagnostic ownership, absent OPPs)
are historical, not the current implementation contract.

## Scope approved 2026-10-18

User selected stock-range bring-up first: preserve the donor's shared PLL,
one eight-core CPUFreq policy and CPR4 closed-loop/APM/memory-ACC sequencing.
No OC, UV interface, kernel build or phone reboot is authorized at this stage.
Another session owns navigation-button work and the running device. Do not
edit its board DTS changes, or change the shared phone's boot state.

**NOT READY for the CPU build/run test yet.** Inactive APM, memory-ACC and SAW4
voltage/AVS providers are implemented below. CPU clock control, the APC rail
regulator and CPR4 are not implemented as a complete stack. No claim of CPU
frequency scaling on hardware.

This supersedes `02-phase2-cpufreq.md`'s independent big/little policies,
invented GCC CPUSS clocks and suggestion that voltage control is optional.
Those mistakes were already identified in `../findings/06-verification.md`.

## Evidence / provenance

- Target ACK: `24bcdc3ed0d0c3bbb3f01179cd7862bd426d17c4`, 6.12.93.
- Donor `../oc-test`: `687ee893ae5d6fd61c69397ea157973e50c06714`.
- Live evidence: `../artifacts/snapshot60/live-audit-20261018T143526Z/cpu.log:1-79,132-156`:
  eight CPUs online and accumulating work; cpufreq directory empty at :81-83.
- Rooted stock comparison:
  `../artifacts/snapshot60/root-audit-20261018T145300Z/cpu-stock.log`:
  one policy, affected CPUs 0-7, driver `msm`, governor schedutil, current/max
  2784000 kHz. This is the modified stock kernel, not stock silicon limits.
- Donor `drivers/clk/msm/clock-cpu-8953.c:110-214,247-278`: one HFPLL,
  two CPU muxes and CCI; cached CPU rates updated together; CCI = CPU * 2/5.
- Donor `arch/arm64/boot/dts/vendor/qcom/msm8953.dtsi:1067-1080`:
  all CPUFreq clocks resolve to the same a53_pwr_clk.
- Donor `docs/oc-uc.md:23-40`: captured bin 2, fuse revision 3, stock
  seven-corner 652.8–2016 MHz plan. Do not hardcode its measured voltages.
  The actual donor board includes the OC override; exclude that override.
- Donor OC commits `beb60e512460`, `df4a1f863991`, `cf0495baf273` were read.
  They change PLL range, corner counts/targets and the UV ABI. They are not
  prerequisites for stock-range bring-up and are outside this approved scope.

## Source changes implemented, disabled by default

### Array Power Mux

`drivers/soc/qcom/msm8953-apm.c`, `include/soc/qcom/apm.h` and
`CONFIG_QCOM_MSM8953_APM`. Derived from donor `drivers/power/qcom/apm.c`:

- :271-359: optional delay fields; :631-726: 8953 register offsets, mode/status
  values, IRQ-safe serialized switching and 500 us timeout.
- :823-853: donor consumer acquisition. New code uses a consumer-managed
  supplier link and a managed platform-device reference instead of an
  unreferenced global list. Deferred acquisition must occur during probe.
- Hardware supply status is read rather than trusting the donor's initial
  zero-initialized cached APCC enum. Unknown status is an error; timeout is
  propagated. No successful state is fabricated on a failed switch.
- Reserve/map only 0x2a8..0x2b3 within `pm-apcc-glb`, because the surrounding
  donor 4 KiB window also contains CPU clock registers. This avoids reserving
  their MMIO for the APM driver. Future clock DT resources must not overlap
  those three APM registers.
- No target node or config fragment enables it. It does not select a voltage
  or frequency; CPR must sequence the 850 mV threshold crossing.

### Memory-ACC corner regulator

`drivers/regulator/qcom-msm8953-mem-acc.c` and
`CONFIG_REGULATOR_QCOM_MSM8953_MEM_ACC`. Derived from donor
`drivers/regulator/mem-acc-regulator.c:140-165,195-208,245-299` and
`arch/arm64/boot/dts/vendor/qcom/msm8953-regulator.dtsi:338-350`:

- MSM8953-only, exact two-corner map 1->bit 1, 2->bit 0, L1 then L2;
  preserve unrelated register bits. DT positions/widths/map are validated.
- Exposes the donor's corner-selector convention through regulator core:
  values 1 and 2 are NOT physical microvolts. CPR decides when to request them.
- Read actual L1/L2 state and return errors for mismatched or stuck bits,
  instead of returning an assumed/cached success.
- Regulator core serializes get/set operations. Resources and registration
  are devm-managed. No enable callback gates a physical rail. No DT/config
  activation has been added.

### SAW4 voltage and AVS provider

`drivers/soc/qcom/msm8953-spm.c`, `include/soc/qcom/msm8953-spm.h` and
`CONFIG_QCOM_MSM8953_SPM`, disabled and unwired. The `qcom,saw2.yaml` binding
adds a specific MSM8953 system-CCI compatible, with the donor CPU-domain list.
The generic target SPM driver and its other SoCs are not changed.

- Donor `drivers/soc/qcom/msm-spm.c:98-120,192-208,455-619` supplies the SAW4.1
  offsets, reset/VCTL/PMIC_DATA3 sequence, 8-bit port-0 data, FSM-idle plus
  level acknowledgement, and 500 us timeout. Bad requests, no arbiter,
  dispatch errors, wrong levels and busy FSM states return errors.
- `spm_devices.c:118-140` routes voltage changes to an online CPU in the
  domain. New code keeps that behavior with a synchronous IPI and CPU-hotplug
  read lock; a raw spinlock serializes all register transactions even on RT.
  Stack request storage stays live until the callback completes.
- `msm-spm.c:274-305` supplies AVS bit 0 and the independent min/max fields
  of AVS_LIMIT. The donor `CONFIG_MSM_AVS_HW`-guarded bit-27/six-bit sequence
  is not enabled in `out-oc/.config` and has no Kconfig definition in the donor.
  Do not apply that older SAW1.1 sequence to SAW4 requests. New code preserves
  the programmed SAW4 AVS limits during a direct voltage request.
- The AVS minimum level 0 is valid, not an error: the `spm-regulator` AVS-limit
  regulator maps the FTS2-family floor (350 mV) to VSET 0 and passes it straight
  to `msm_spm_avs_set_limit` (`spm-regulator.c:609-673`). The provider therefore
  accepts min 0 (it only rejects `min > max` or a max above 0xff) and refuses to
  arm AVS while the ceiling is still unprogrammed.
- CPU levels are encoded PMIC data, NOT microvolts. Their conversion and
  settling delays still belong in the pending APC rail regulator. No SPMI
  fallback or voltage/PMIC-type guess has been added to this MMIO service.
- The APC rail is PM8953 S5. Donor boot logs (`out-lto/dmesg-boot.txt:258-259`,
  also out-merge/out-lto variants) show
  `spm_regulator_probe: name=pm8953_s5, range=LV, voltage=870000 uV,
  mode=AUTO, step rate=1200 uV/us`. 870000 uV is representable only with a
  5000 uV output step (FTS2 0 uV / FTS2p5 80000 uV VSET origin), not with the
  HF/ULT_HF 12500 uV or FTS426/HFS430 4000/8000 uV steps, so the S5 SMPS is an
  FTS2-family (type 0x1C) buck with the LV range. The pending rail port keeps
  the donor PMIC-type detection rather than hardcoding the type.
- The donor AVS min/max IRQ helpers (`msm-spm.c:307-363`, AVS_CTL bits 1/2) are
  reached only from CPR3 hardware-closed-loop paths
  (`cpr3-regulator.c:1541,5006,5850,5864,6589`). CPR4 instead enables its
  `vdd_limit_regulator`, which the `spm-regulator` AVS ops back with
  `msm_spm_avs_set_limit` plus `msm_spm_avs_enable/disable`. The provider
  therefore exposes no AVS IRQ surface and the CPR4 path needs none.
- Probe write fidelity was re-derived from the donor, not assumed:
  `spm_devices.c:729-737,875-881` writes only the `qcom,saw2-*` properties
  present in DT (four on MSM8953) through `upd_reg_shadow`, while
  `reg_init_values` is never populated (`memset`) and so is never flushed.
  The provider matches: four writes, no zeroing of AVS_LIMIT/RST/PMIC_DATA.
- Probe verifies SAW major/minor 4.1, PMIC-arbiter presence and all possible
  CPUs in the domain. It applies exactly the four initial system-CCI settings
  in donor `msm8953-pm.dtsi:16-34` and checks readback before publishing state.
  It sends no voltage request and does not enable AVS or program sequences.
- Consumers acquire a managed supplier handle through `qcom,saw` during
  probe. Device links order supplier/consumer removal; platform-device refs
  are released by consumer devres. No global per-CPU dangling supplier pointers
  or fake successful `msm_spm_probe_done()` shim.
- Host test `test-msm8953-spm.py` compiles the actual operations and dispatch
  wrapper against MMIO/IPI mocks. It does NOT validate real IPI delivery,
  hotplug/RT scheduling, MMIO timing, probe, DT schema or supplier lifetime.

### SPM-backed APC rail regulator

`drivers/regulator/qcom-msm8953-spm-regulator.c` and
`CONFIG_REGULATOR_QCOM_MSM8953_SPM`. Derived from donor
`drivers/regulator/spm-regulator.c`:

- Binds `qcom,spm-regulator` on the PM8953 S5/S6 SMPS child node, reads the
  PMIC type/subtype over the parent SPMI regmap and keeps the donor's type
  detection and per-type voltage ranges rather than hardcoding FTS2.
- Voltage requests go through the SAW4 provider (`msm8953-spm.h`) so the SPM
  keeps ownership of the PMIC VSET. A direct SPMI write is only used for
  `qcom,bypass-spm` or after a failed SPM request, matching the donor fallback.
- The optional child node registers the AVS minimum/maximum limit regulator
  that CPR4 enables. Enable/limits map to `msm8953_spm_set_avs` and
  `msm8953_spm_set_avs_limits`.
- Deliberate divergences from the donor, each recorded: no `qcom,cpu-num`
  (the SAW4 handle is one shared domain), no `qcom,recal-mask`/SMC
  recalibration (absent from the MSM8953 DT), no probe-time SPM seed write
  (the donor only reads at init), and a non-zero maximum-voltage-step floor to
  prevent an infinite ramp loop.
- Host test `test-msm8953-spm-regulator.py` compiles the real conversion,
  selector and step-rate functions and checks 870000 uV / level 174 and
  1200 uV/us against the donor boot log. It is not a probe, regmap or hardware
  test. The driver is disabled and unwired until CPR4 and the clock provider
  exist.

## Remaining implementation / review gates

1. **SPM/AVS and APC rail.** The isolated SAW4 MMIO provider and the
   SPM-backed APC rail regulator (with its AVS-limit child) now exist as
   disabled, unwired sources. What remains is the CPR4 consumer and the board
   DT declaration of the PM8953 S5 node, its `qcom,saw` link and the AVS-limit
   child. Do not stub probe_done or AVS calls to success.
2. **CPR4 closed loop.** Preserve fuse interpretation, speed-bin filtering,
   per-corner target quotients, voltage floor/ceiling, APM threshold crossing,
   memory-ACC order, hardware loop limits, locking and error rollback.
   `cpr3_regulator_register()` explicitly requires SPM when hardware closed
   loop is selected (donor cpr3-regulator.c:6445-6461).

   Scoping done 2026-10-18, before editing:

   - Files to port (donor): `cpr3-regulator.c` 6601, `cpr3-regulator.h` 1116,
     `cpr3-util.c` 2487, `cpr4-apss-regulator.c` 2042, plus two small headers
     `linux/regulator/cpr3-uv.h` and `linux/regulator/msm-ldo-regulator.h`
     (~12.3k lines total). Kconfig is `REGULATOR_CPR3` (core, selects
     `cpr3-util.o`) plus `REGULATOR_CPR4_APSS` which selects it.
   - The vendor helper names (`regulator_aging_adjust`, `regulator_config_*`,
     `regulator_update_ctrl_state`, `regulator_set_bhs_mode`, ...) are defined
     inside the cpr3 files, not in a patched regulator core, so no core
     changes are implied.
   - External prerequisites already exist in the target and match the donor
     signature: `soc/qcom/apm.h` (`msm_apm_ctrl_dev_get`, `msm_apm_get_supply`,
     `msm_apm_set_supply`, `enum msm_apm_supply`), the SAW4 provider
     (`msm8953_spm_*`) and the memory-ACC regulator (`vreg->mem_acc_regulator`
     consumer, `ctrl->mem_acc_threshold_volt`, `ctrl->mem_acc_corner_map`).
   - Silicon values are DT-provided (`qcom,cpr-fuse-*`, `qcom,cpr-corners`,
     `qcom,cpr-voltage-floor/ceiling`, `qcom,cpr-ro-sel`, ...); there is no
     `nvmem` path, the CPR hardware reads its own fuses. The SoC-specific
     numbers live in the board dtsi, not the C driver.
   - The target's `CONFIG_QCOM_CPR` / `drivers/pmdomain/qcom/cpr.c` is a
     different controller (qcs404 only, `qcom,qcs404-cpr`) and cannot serve
     MSM8953; the donor closed-loop CPR4 remains the only path.
   - Plan: port the core and CPR4-APSS as a disabled, unwired block, keep the
     CPR4 path and drop the unused CPR3/CPRH/MMSS variants only where removal
     is provably inert, and compile-check object by object before any boot.
   - Done 2026-10-18: `cpr3-regulator.c` (6576), `cpr3-util.c` (2487),
     `cpr3-regulator.h` (1116), `cpr4-apss-regulator.c` (2043) plus
     `linux/regulator/cpr3-uv.h` and `linux/regulator/msm-ldo-regulator.h`
     now build cleanly against this tree with clang and the real config.
     Kconfig `REGULATOR_CPR3` + `REGULATOR_CPR4_APSS`; the latter depends on
     the SAW4/APC-rail, memory-ACC and APM providers. Still disabled, still
     unwired, no boot.

     Adaptations to 6.12 (all compile-verified):
     - `#include <soc/qcom/spm.h>` becomes the SAW4 provider header, and the
       hardware-closed-loop gate `msm_spm_probe_done()` becomes
       `msm8953_spm_probe_done()`: a real readiness query against the single
       probed SAW4 domain, not a success stub.
     - The standard `struct regulator_ops` has no `list_corner_voltage`, so
       that field is dropped from both ops tables; the mapping helper is kept
       `__maybe_unused`. The corner-based regulator contract is otherwise
       unchanged: `list_voltage(sel)` returns `sel + CPR3_CORNER_OFFSET`,
       `set_voltage` interprets the core's min/max as corner(+offset), and
       `get_voltage` returns the current corner(+offset). This matches the
       donor consumer chain (see gate 3), which requests corner-encoded
       values, not physical microvolts.
     - The five `msm_spm_avs_*_irq` call sites are all `CPR_CTRL_TYPE_CPR3`
       only, and the ceiling handler that clears the AVS IRQ is registered
       only for `supports_hw_closed_loop && ctrl_type == CPR_CTRL_TYPE_CPR3`;
       MSM8953 is CPR4, so those paths are provably inert and were removed
       rather than stubbed. `regulator_register()`/`no_llseek`/
       `panic_notifier.h` and a `void` `.remove` are the remaining drift.
   - Consumer contract, recorded for gate 3 and the DTS gate: the donor does
     not use cpufreq-dt/`opp-microvolt`. `qcom,cpu-clock-8953` carries
     `vdd-cl-supply = <&apc_vreg>` and a `qcom,speedN-bin-vM-cl` rate-to-corner
     map; its vendor clock `vdd_class` calls `regulator_set_voltage()` on the
     CPR regulator with corner-encoded values, while `qcom,msm-cpufreq`
     (donor `drivers/cpufreq/qcom-cpufreq.c`) only sets the CPU clocks. So the
     ported CPR ops fit the donor consumer, and the clock provider must
     reproduce that vdd_class coupling rather than a plain mainline OPP table.

3. **CCF CPU provider.** Adapt the donor clock behavior to 6.12's clock
   framework; do not import its incompatible private struct-clk framework.
   Preserve both CPU muxes and CCI, PLL MX power voting, transition sequencing,
   valid clock-rate readback, error rollback and shared policy semantics.
   Review all affected sibling clocks on shared-PLL changes.

   Done 2026-10-18: `drivers/clk/qcom/apcc-msm8953.c`,
   `include/dt-bindings/clock/qcom,apcc-msm8953.h`,
   `Documentation/devicetree/bindings/clock/qcom,apcc-msm8953.yaml`, Kconfig
   `QCOM_CLK_APCC_MSM8953` (bool) and the Makefile entry. Built as a source,
   disabled, with no DT node, no image and no boot.

   One shared PLL, three mux-dividers, three exported clocks:
   - The PLL is `clk_alpha_pll` with `CLK_ALPHA_PLL_TYPE_HUAYRA_APSS`, whose
     register offsets are byte-for-byte the donor's `APCS_PLL_*` map
     (L 0x08, ALPHA 0x10, USER_CTL 0x18, CONFIG_CTL 0x20/0x24, STATUS 0x28,
     TEST_CTL 0x30/0x34), so no bespoke register array is needed. Config
     `l = 34`, `config_ctl_val 0x200d4828`, `config_ctl_hi_val 0x6`,
     `test_ctl_val 0x1c000000`, `test_ctl_hi_val 0x4000`, main output BIT(0),
     early output BIT(3): the donor's values. `SUPPORTS_DYNAMIC_UPDATE`
     because the donor reprograms a running PLL.
   - Each mux is this tree's `clk_regmap_mux_div_ops` with `hid_width 5`,
     `hid_shift 0`, `src_width 3`, `src_shift 8` and `parent_map {5, 4, 2}`,
     which is the donor's `is_half_divider` mux with the register src values.

   Decisions, made deliberately rather than copied from the WIP upstream:
   - **VCO.** `VCO(0, 652800000, 2016000000)`, the stock fused bin-2 range the
     user approved. Upstream's `if (num_plls)` branch overwrites the msm8953
     VCO with the sdm632 one, `VCO(0, 614400000, 2016000000)`, which is an
     upstream bug and is not copied. The donor's 480-2784 MHz OC range is out
     of scope. A request above the plan is refused with `-ERANGE` rather than
     rounded up into an unfused corner.
   - **SoC match and PLL count.** No root-node `of_match_node()` and no
     `num_plls`: single-SoC driver, device node compatible only.
   - **One PLL, three ids dropped.** All three upstream `*-pll-clk` entries
     alias the same APCS PLL (0xb016000/0xb116000/0xb1d0000 are the APSS APLL
     aliases and the donor drives one `apcs_hf_pll`). Exporting three ids for
     one register block would let two consumers reprogram it behind each
     other's back, so the binding exposes only the three mux clocks and the
     PLL is parent 0 of all three.
   - **Mux parents kept.** GPLL0 (src 4) and GPLL2 (src 2) stay, because the
     RCG really has those sources and the measured boot state parks c0/c1 on
     GPLL0; a single-parent provider would answer `get_parent` with
     "Can't find parent with src 4" on a boot that is working. The rail
     coupling is rate based, so a GPLL rate still gets a correct corner.
   - **Transition sequencing.** One PLL `PRE_RATE_CHANGE` notifier parks every
     mux still muxed on the PLL at its largest divider (divide by 64) before
     the PLL moves, the SDX55 pattern. Upstream's second notifier on the mux
     adds nothing on top of that. The src the notifier uses is the one CCF
     last programmed, which is all a clock driver can know about writes made
     outside it; gate 4 is what removes those external writes.
   - **OPP block dropped.** No `operating-points-v2` handling, no
     `devm_pm_opp_set_config()`, no genpd "cpr" domain. That is the mainline
     apcc/cpr genpd model, not our CPR regulator.
   - **The provider owns the rail.** This is the donor's `vdd_class`, ported:
     each of the three clocks votes the corner its new rate needs, the highest
     vote is programmed to the corner-encoded `vdd-cl` regulator, and the vote
     is applied *before* the frequency moves and rolled back if the rate
     change fails. That is what the donor's `clk_core_set_rate_nolock()` did:
     `vote_rate_vdd()` before `set_rate`, `unvote_rate_vdd()` after.
   - **Speed bin.** Read from PTE EFUSE bits 8-10 (donor resource `efuse`,
     0xa4124) and used to select `qcom,speedN-bin-v0-cl` and
     `qcom,speedN-bin-v0-cci`, with the donor's fallback to bin 0.

   Contract for gate 5, recorded here so the DTS does not fight the driver:
   the CPU nodes must **not** declare `cpu-supply`, because the provider owns
   the rail; the CPU OPP table carries `clock-frequency` only, and the `apcc`
   node needs `vdd-cl-supply = <&apc_vreg>` plus `clocks`/`clock-names` for
   XO, GPLL0 early and GPLL2 early. CCI keeps its own plan so a CCI rate change
   cannot leave the shared rail at a CPU corner.
4. **Replace the diagnostic clock owner deliberately.** Target
   `fs/pstore/ram.c:2152-2178,2226-2228` currently switches CPU4-7 to GPLL0.
   Keep this proven baseline until a real provider takes ownership; do not
   let it reprogram registered clocks behind CCF's cache.
5. **Isolated CPU DTS/config.** Add a CPU-only board include; integrate with
   the navigation session's DTS without overwriting it. Supply the APC rail,
   SPM, APM, ACC, CPR and CPU clock dependencies; validate bindings/resources.
   Enable CPUFreq only after suppliers exist. No fake single-OPP CPU info.
6. **Thermal gate.** TSENS is currently disabled and Android thermal HAL not
   ready. Do not treat PMIC/battery temperature as CPU die temperature or run
   sustained high-OPP stress before SoC temperature/cooling is available.
7. **Idle later.** The donor's PSCI hierarchy and latency values need their
   own conversion; do not copy numeric modes into generic idle states by guess.

## Online cross-checks

- Current upstream CPUFreq/CPUIdle documentation and AOSP android16-6.12
  CPUFreq documentation establish that online CPUs and scaling policies are
  different and that a registered clock/voltage scaling path is needed.
- MSM8953 mainline-derived 6.12 reference CPU clock conversion:
  [7c2d10338ed7dc854c893fe6fcb29f21249247b5](https://github.com/msm8953-mainline/linux/commit/7c2d10338ed7dc854c893fe6fcb29f21249247b5),
  `drivers/clk/qcom/apcs-msm8953.c`, blob
  `46b3e08746541da532a2595a41054c9a0fdf762f`. Confirms shared MSM8953 PLL,
  mux sources 4/5, CPU divide-by-1 and CCI divide-by-2.5.
- CPR reference
  [d1661d1ecda6edbe9f28ace039fb8d726942e897](https://github.com/msm8953-mainline/linux/commit/d1661d1ecda6edbe9f28ace039fb8d726942e897),
  `cpr4pd.c`, blob `1358d148ede15df87bebf3cf49f850f2f947182a`, calculates
  open-loop fuse voltages and controls APC/APM/ACC; it does NOT implement the
  donor CPR hardware closed loop. It is a comparison, not a drop-in equivalent.
- Target `Documentation/driver-api/device_link.rst:65-118` checked against
  acquisition/removal handling. Host tests do not prove supplier lifetime.
- Current upstream and AOSP `android16-6.12/drivers/soc/qcom/spm.c` independently
  confirm SAW4 AVS_CTL=0x904 / AVS_LIMIT=0x908 and CPU-routed voltage writes.
  Their SAW1.1 regulator path uses bit 27, but is not an MSM8953 substitute.
  [AOSP source](https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/drivers/soc/qcom/spm.c).
  Device-link ownership was also rechecked against current upstream docs.

## Checks and readiness

Run `python3 porting/build-test/test-msm8953-apm.py`,
`python3 porting/build-test/test-msm8953-mem-acc.py`, and
`python3 porting/build-test/test-msm8953-spm.py`. They compile only the
actual C switch/read functions against host register mocks. Cover switch
directions, invalid inputs, APM timeout/status mask, memory-ACC ordering,
unrelated bits and stuck/mismatched state. They do not compile the kernel
drivers or test hardware, probe/cleanup, bus ordering or real timing.

SAW4 model checks pass with host GCC and Clang. Strict checkpatch and the
advisory API-pattern scan pass. YAML parsing checks syntax only; full
`dt_binding_check`, kernel compilation and device tests have not run.

Before declaring ready: finish the remaining source path, run focused static
checks, review shipped config/DT dependency completeness and identify one exact
base artifact. Then ask for kernel build authorization. A build passing does
not authorize a boot. Arrange an exclusive device window and preserve evidence
before a RAM-only run. First prove registration/clock rates/corners; compare
controlled stock and port measurements before calling performance fixed.
