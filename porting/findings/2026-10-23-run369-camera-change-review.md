# Review of the run368camera to run369-camera change

## Artifact comparison

Compared the actual packaged configs, DTBs, kernels and JSON reports, not
only the working-tree diff:

- Same base image, init SHA256, policy SHA256 and command line.
- Config difference: WLAN NV is embedded again and EXTRA_FIRMWARE_DIR is set.
- All 17 WCNSS/NV/Venus firmware files are restored to the ramdisk.
- Both arm64 Image headers report 53,870,592 bytes (131,072 bytes headroom).
- run369's kernel banner is `g0423a9133d37-dirty #19`; its build log confirms
  recompilation of the edited camera objects and a vmlinux relink.
- DT delta: the camera core at 0x1b00000 and the CCI timing tables. The full
  decompiled diff was saved at `/tmp/opencode/dtb-camera-368-369.diff`.

This rules out a changed init binary or command line in these two artifacts.
It does not establish the cause of the user's run369 dim-screen reset.

## Newly reachable IRQ-registration race

In run368 the CCI probe returned at the missing IRQ-resource lookup. The
run369 lookup fix allows the following previously unreachable sequence:

1. `msm_cci_probe()` requests an automatically enabled IRQ.
2. Only after request returns does it disable that IRQ.
3. It initializes the CCI master mutexes/completions later in probe.
4. The clocks are enabled still later, in `msm_cci_init()` on first use.

`msm_cci_irq()` immediately reads and writes CCI MMIO, and can signal those
completions or acquire queue locks. A pending IRQ delivered during step 1
can therefore access the unpowered controller and uninitialized state.
This is a source-level race, **not a confirmed cause of the observed reset**;
there is no attributable crash stack from that boot.

Upstream introduced `IRQF_NO_AUTOEN` specifically for the unsafe
request_irq()/disable_irq() window:

- Commit `cbe16f35bee6880becca6f20d2ebf6b457148552`,
  `genirq: Add IRQF_NO_AUTOEN for request_irq/nmi()`.
- Online cross-check:
  https://mailweb.openeuler.org/archives/list/kernel@openeuler.org/message/OBA6TJ6WD3JZBU27LXHNHNAODS33U7QD/
- Target implementation: `include/linux/interrupt.h` and
  `kernel/irq/manage.c` honor this flag at IRQ registration.

The working tree now requests CCI with `IRQF_NO_AUTOEN` and removes the
post-request disable. The initial disable depth remains one. The existing
enable after successful clock setup, disable before clock shutdown, and
subsequent enable/disable pairs remain unchanged. This is a CCI-specific
change, not a global change to the camera IRQ helper.

A host test extracts the actual request expression and models a pending
interrupt being delivered by request_irq(). It failed on run369's flags
(handler ran before probe was ready) and passes with NO_AUTOEN. The test
also checks that probe does not disable it a second time and that the
first runtime enable follows clock setup. All four host bring-up tests
pass; strict checkpatch of the CCI diff and `git diff --check` pass.
No kernel build or boot was performed for this correction.

## Other defects found; not reset conclusions

- `msm_camera_gpio_count()` divides the raw GPIO property cell count by
  two. The run369 DTB contains twelve CCI GPIO cells: four phandles plus
  four two-cell TLMM specifiers. The helper reports six GPIOs instead of
  four. This predates run369 but its CCI path is now reachable. It needs
  a phandle-aware count, not another fixed divisor.
- The board's `qcom,camera@0/@1/@2` nodes lack the compatible, cell-index
  and other defaults inherited by the donor from
  `msm8953-camera-sensor-mtp.dtsi`. The board overrides were imported
  without those base definitions. This prevents complete sensor bring-up;
  it does not itself prove an early reset.
- CCI publishes `g_cci_subdev` and creates its workqueues after populating
  children. Synchronous EEPROM child probes can run before that state is
  ready. It also ignores `legacy_msm_sd_register()` and GPIO-init failures.
- Clock-helper error cleanup uses an unsigned index in `for (--i; i >= 0;
  i--)`. A failed acquisition can walk past index zero. The failing clock
  acquisition needed to trigger this has not been observed in this boot.

These are follow-up review targets, not authorization to call the reset
solved or consume another boot cycle without a focused test plan.

## Reset evidence

The post-clear retry was captured automatically upon returning to main:
`porting/artifacts/snapshot60/run369-camera-reset-kTNWIqvX/`.
All decoded crash/snapshot headers were empty; pstore was empty; the
non-sleeping reset marker had no valid retained identity. The normal log
was main's boot and the orderly bootloader reset record cannot be
attributed to the failed camera boot. Cause remains **unverified**.
