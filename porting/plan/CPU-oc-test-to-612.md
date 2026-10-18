# MSM8953 CPU bring-up from oc-test

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
- CPU levels are encoded PMIC data, NOT microvolts. Their conversion and
  settling delays still belong in the pending APC rail regulator. No SPMI
  fallback or voltage/PMIC-type guess has been added to this MMIO service.
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

## Remaining implementation / review gates

1. **SPM/AVS first.** Donor `msm8953-pm.dtsi:16-34` uses system-CCI SAW at
   0xb1d2000, all CPUs in cpu-vctl-list, 500 us voltage timeout.
   `drivers/soc/qcom/spm_devices.c` provides probe_done, get/set_vdd and AVS
   limit/enable/disable. `drivers/regulator/spm-regulator.c:355-429,609-718`
   uses these for the APC rail and its hardware-AVS limit regulator.
   The isolated SAW4 MMIO provider now supplies this service, but the APC rail
   and AVS-limit regulator consumers remain to be ported. Trace PMIC subtype,
   voltage range/encoding, settling and fallback semantics before connecting
   them. Do not stub probe_done or AVS calls to success.
2. **CPR4 closed loop.** Preserve fuse interpretation, speed-bin filtering,
   per-corner target quotients, voltage floor/ceiling, APM threshold crossing,
   memory-ACC order, hardware loop limits, locking and error rollback.
   `cpr3_regulator_register()` explicitly requires SPM when hardware closed
   loop is selected (donor cpr3-regulator.c:6445-6461).
3. **CCF CPU provider.** Adapt the donor clock behavior to 6.12's clock
   framework; do not import its incompatible private struct-clk framework.
   Preserve both CPU muxes and CCI, PLL MX power voting, transition sequencing,
   valid clock-rate readback, error rollback and shared policy semantics.
   Review all affected sibling clocks on shared-PLL changes.
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
