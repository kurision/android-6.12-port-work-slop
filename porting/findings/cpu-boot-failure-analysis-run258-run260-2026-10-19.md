# CPU boot-failure analysis: what changed since run258, and what could not boot

> **Historical record - 2026-10-19.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

Date: 2026-10-19. Scope: the source delta between the run258 image and the
run260 image, the evidence that bounds the failure, the ranked suspects, and
the source hardening that follows from them.

No boot cycle was consumed. No device was touched. The second-opinion review
that was requested could not run: the requested model
(`opencode/deepseek-v4.1-flash-free`) returned "Rate limit exceeded" on every
attempt, including a two-word probe, so the findings below rest on source,
donor and measured-hardware evidence only.

## 1. The delta, established from the build manifests

The two builds each recorded a SHA256 for every source file they used
(`porting/artifacts/snapshot60/run258-source-verification.json`,
`run260-source-verification.json`; 69622 and 69625 files). Diffing those
manifests gives the exact source that produced each image, which is stronger
than a commit range: it includes the uncommitted working-tree edits.

**Exactly nine files differ between run258 and run260.** Everything else,
including the uncommitted PMIC/S5/CPR-table/AVS and diag-init edits, is
byte-identical in the two builds and therefore cannot explain the
regression.

| File | Change | Runtime meaning |
|---|---|---|
| `drivers/clk/qcom/apcc-msm8953.c` | rewritten (~1264 lines) | first-ever programming of the live CPU clock path |
| `arch/arm64/boot/dts/qcom/msm8953-cpu.dtsi` | `power-domains = <&rpmpd MSM8953_VDDMX_AO>`, `power-domain-names = "mx"` on the apcc node | the platform bus now attaches and powers the shared MX domain |
| `drivers/clk/qcom/Kconfig` | `QCOM_CLK_APCC_MSM8953` depends on `QCOM_RPMPD && PM_GENERIC_DOMAINS_OF` | build-time only; the resolved config diff was empty |
| `drivers/mailbox/qcom-apcs-ipc-mailbox.c` | MSM8953 reserves only the 4-byte doorbell at `0xb011008` | the `-EBUSY` that kept APCC out of the hardware path disappears |
| `fs/pstore/ram.c` | deletes `ramoops_cpuclk_c1_to_gpll0()` | removes the early CPU4-7 clock/branch workaround |
| `include/linux/pstore_ram.h`, `drivers/misc/qseecom.c`, `drivers/gpu/msm/adreno-zap-compat.h` | shared prototypes moved into the header | declaration only, no behaviour |
| `Documentation/devicetree/bindings/clock/qcom,apcc-msm8953.yaml` | documentation | none |

The compiled DTB delta is only the two power-domain lines: `opp-shared;` was
already present in the run258 DTB and is not part of this delta.

The same manifests show that **run259 (built by the user from a different
staged tree) and run260 have byte-identical** `apcc-msm8953.c`,
`msm8953-cpu.dtsi`, `qcom-apcs-ipc-mailbox.c` and `drivers/clk/qcom/Kconfig`.
They differ only in the diagnostic restoration (`fs/pstore/ram.c`,
`pstore_ram.h`, `qseecom.c`, `adreno-zap-compat.h`). Two independently built
images with the same CPU-repair sources fail the same way, so the regression
is in that source delta, not in one build or one packaging step.

## 2. What the zero logdump bounds

run260's pre-cleared 64 MiB logdump partition read back as **all zero**
(67108864 bytes, SHA256
`3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351`), with
no console text, no snapshot slot, no periodic tail and no reset record.

That partition is written by exactly two things:

1. the userspace diag init (`scripts/initramfs-diag/init.c`), which copies
   `/dev/kmsg` into it, and
2. the in-kernel periodic snapshotter (`fs/pstore/ram.c`,
   `RAMOOPS_SNAP_INTERVAL_MS` 2000 ms), whose first sample in run258 landed
   at 4.9 s.

A kernel that hangs or dies between the ramoops console registration
(~0.8 s, `postcore_initcall`) and ~4.9 s leaves the partition untouched.
That window contains `device_initcall` (level 6), where the APCC driver
probed at 3.45 s in run258. A panic before the logdump block device was open
would look the same, because `ramoops_panic_snapshot()` cannot write before
the snapshotter has opened the partition.

`init/main.c:1709` calls `smp_init()` and `init/main.c:1717` calls
`do_basic_setup()`, so all eight CPUs are already up before any initcall
runs. CPU4-7 running at XO speed is therefore not by itself a boot blocker;
it is a performance problem, not a hang.

## 3. Measured hardware state at boot

From run258's logdump lines 162-166 (the port's own pstore diagnostic, which
reads the same registers the driver does):

```
pll  mode=00000000 lock=0 l=0 user=0000000f   APCS HF PLL 0xb116000: off
c0   cmd=00000002 cfg=00000401 src=4 div=1    CPU0-3 RCG 0xb111050: GPLL0
c1   cmd=00000002 cfg=00000000 src=0 div=0    CPU4-7 RCG 0xb011050: XO
cci  cmd=00000002 cfg=00000403 src=4 div=3    CCI RCG 0xb1d1050: GPLL0
```

The deleted pstore writer then set `c1` to `cfg=00000401` (GPLL0) and
`CBCR (0xb011058) |= BIT(0)`, read back `cbcr=00000003`.

Donor ground truth (`/home/kurision/development/kernel/oc-test`):

* `clock-cpu-8953.c:44-56`: the APCS HF PLL registers are MODE 0x00, L 0x08,
  ALPHA 0x10, USER 0x18, CONFIG_LO 0x20, CONFIG_HI 0x24, STATUS 0x28,
  TEST_LO 0x30, TEST_HI 0x34; the lock bit is **MODE bit 31**; the cold-init
  values are post_div 0x100, config 0x200D4828, config_hi 0x6,
  test_lo 0x1C000000, test_hi 0x4000, source 19.2 MHz.
* `clock-pll.c:29-32`: MODE bits are `PLL_OUTCTRL` bit 0, `PLL_BYPASSNL`
  bit 1 (active low), `PLL_RESET_N` bit 2 (active low).
* donor enable order (`clock-pll.c` ~400-540): `BYPASSNL`, 10 us, `RESET_N`,
  **200 us**, then poll the lock bit for ~400 us reading it twice to reject
  the early transient locks, `panic("failed to lock %s PLL")` if it never
  locks, then `OUTCTRL`.
* `clock-cpu-8953.c:1032-1099` (`early_initcall cpu_clock_pwr_init`): read
  back the PLL L; if it is zero, cold-init the PLL and set 652800000; then
  program **only** the CPU4 alias1 RCG to `CFG = (5<<8)|1` (the APCS PLL,
  divide by 1), pulse the update bit, and set `CBCR |= BIT(0)`. The donor
  never touches the c0 or the CCI mux at boot, and never moves the running
  CPU0 cluster off GPLL0 at boot.

The run260 implementation reproduced the donor's register values and bit
sequence exactly, but not its *scope* and not its *timing*.

## 4. Ranked suspects

**1. The APCC probe programmed the live clock path for the first time.**
In run258 the probe failed at the resource map, before any hardware write.
With the mailbox repair it got through, and `apcc_handoff()` then performed
the whole coupled transaction at `device_initcall`:

* it re-programmed the **CCI mux** (`0xb1d1050`) from `div 3` to `div 4`,
  i.e. it changed the rate of the interconnect the running CPUs use, and
  re-issued an update handshake on the **CPU0 mux** that clocks the running
  CPUs - neither of which the donor does at boot;
* it programmed the APCS PLL with a **lock budget shorter than the donor's**:
  `usleep_range(50, 60)` plus a single 200 us `regmap_read_poll_timeout`
  against the donor's 200 us delay plus ~400 us of double-checked polling.
  The donor *panics* rather than continue when the lock is missed, so the
  hardware does lock inside the donor's budget; the port's budget could
  report a lockable PLL as a timeout;
* the rollback (`apcc_restore()`) is itself destructive: with a cold saved
  PLL it clears MODE bits 0-2 (output off, bypass, reset) and rewrites the
  saved registers without re-running the enable sequence, so the failure
  path touches the clock path a second time.

**2. The new `power-domains` on the clock node.** `drivers/base/platform.c:1399`
attaches (and powers on) the shared MX genpd domain for the APCC device;
`:1406` detaches it with `power_off` when the probe fails.
`drivers/pmdomain/core.c:894-901` only keeps the domain up while a device in
it holds a runtime-PM reference. The port's own virtual device
(`genpd_dev_pm_attach_by_id` + `pm_runtime_resume_and_get`) is created
inside `apcc_pin_power()`, which the probe called **after**
`apcc_pin_inputs()`; a failure in the input-clock acquisition therefore left
the MX domain with only the platform-bus attachment, and the detach powered
the shared MX rail off. The MX vote itself is an RPM request that can block
for `RPM_REQUEST_TIMEOUT` (5 s, `drivers/soc/qcom/smd-rpm.c:134`), inside
the failure window.

**3. The mailbox change** is correct in isolation and is not a fault; its
significance is that it is the enabler: it is what let the APCC probe reach
the hardware path for the first time.

**4. The deleted pstore writer** is not a boot blocker by itself - run258
also had a failed APCC probe and still booted - but it removed the only
fallback that gave CPU4-7 a usable clock. If the APCC probe *fails* rather
than hangs, run260 leaves CPU4-7 on XO with no DVFS at all, which is worse
than run258's lag and is a plausible watchdog bite.

**5. Not suspects:** the declaration-only files, the binding, the Kconfig
change (empty resolved config diff), and `opp-shared` (already in the run258
DTB).

## 5. Source hardening applied

`drivers/clk/qcom/apcc-msm8953.c`, plus its host suite:

1. **The boot handoff is now the donor's sequence**
   (`apcc_handoff()`, `apcc-msm8953.c:920`): program the PLL, then move only
   the CPU4 alias1 mux to it and enable the CPU4 core branch. The running
   CPU0 cluster and the CCI keep the firmware's configuration, and the
   coupled transaction stays in the rate-change path, where the donor
   performs the same kind of mux writes and where the port's existing
   rollback and fault-injection coverage applies. The handoff verifies the
   donor's end state (CPU4 on the PLL at 652.8 MHz, branch enabled, CPU0 and
   CCI unchanged) and rolls back through the same restore path on failure.
2. **Donor-length PLL lock budget** (`apcc_wait_lock()`,
   `apcc-msm8953.c:354`): 200 us after the reset is de-asserted, then up to
   200 poll iterations that read the lock bit twice, matching the donor's
   rejection of transient locks.
3. **The shared MX domain is protected from a failed probe**: the probe now
   calls `apcc_pin_power()` before `apcc_pin_inputs()`
   (`apcc-msm8953.c:1028`), so the domain reference exists before any
   fallible step and the platform bus's `power_off` detach cannot drop the
   shared MX rail from under its other users.
4. **The park no longer writes muxes that do not need it**
   (`apcc_park()`, `apcc-msm8953.c:325`): each output keeps its own divider
   and a mux that is already on GPLL0 is not written at all, so the running
   CPU0 mux and the live CCI divider are not touched while parking. The
   restore (`apcc_restore()`, `apcc-msm8953.c:483`) mirrors that and only
   rewrites a mux whose configuration actually changed. The corner that
   covers the parked rates is now computed per output
   (`apcc_parked_rate()`, `apcc-msm8953.c:560`), because a parked output
   keeps its divider and therefore its own rate.

## 6. Checks and limits

* Host suites pass with GCC and Clang: APCC, APCS mailbox, SPM, SPM
  regulator, APM, memory-ACC, CPR tables. The APCC suite now also asserts
  that the handoff leaves the CPU0 mux and the CCI register images
  byte-identical.
* Strict checkpatch on the driver is clean; the kernel API pattern scan
  reports no findings.
* The APCC fault-injection position counts changed (82/82/75 for the
  one-shot MMIO sweep, 60 for the cold split handoff) because the park now
  performs fewer MMIO operations. Fewer injected positions is a coverage
  change, not a coverage loss in kind: the same fault classes are still
  swept, over the shorter operation sequence.
* **Not verified here:** kernel compilation of the changed driver, the DT
  build, runtime behaviour, actual frequencies, voltages, CPR control, and
  whether the hardened boot reaches userspace. No image was built and no
  device was touched. Host mocks do not run the real CCF, genpd, runtime PM,
  regulator or resource core.
* A second-opinion review by an external model was requested and could not
  be obtained (provider rate limit). It should be run before the next
  build if the provider is available.

## 7. Recommended next step

Still one boot cycle, still one variable. Two candidates, in order of cost:

1. **Package-only control** on the existing run260 payloads: append
   `initcall_blacklist=apcc_msm8953_driver_init` to the command line. No
   kernel build is needed. If that image boots to Android, the failure is
   inside the APCC probe path and the hardened driver is the next thing to
   test; if it still splash/resets with a zero logdump, the cause is not
   the APCC probe and the mailbox change and the DT power-domain change
   have to be re-examined on their own.
2. **Build the hardened driver** (W=1 objects plus the board DTB) and boot
   it as run261. The hardening removes the two writes the donor never makes
   at boot and matches the donor's lock budget, so a clean boot would
   confirm the scope of the defect rather than the individual step.

Either way, preserve the run260 evidence first, use a fresh run namespace
(`run261*` is free), and gate the logdump preclear on a real
package-verification record rather than a build status.
