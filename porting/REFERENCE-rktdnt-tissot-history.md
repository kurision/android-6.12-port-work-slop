# rktdnt: Tissot donor bring-up commit record

Recorded 2026-10-17. The history/source investigation is not a diagnosed
explanation for run210's reset. The approved source-only panel-policy
correction is recorded below; it has not been built or booted.

## Scope and attribution

- Donor: `/home/kurision/development/kernel/oc-test`, branch `oc-test-2ghz`,
  inspected HEAD `687ee893ae5d6fd61c69397ea157973e50c06714`.
- Author identity: **Raya Mahardika**, `94042378+rktdnt@users.noreply.github.com`.
- **20 authored commits across local refs; 18 reachable from donor HEAD.**
  Two additional commits were applied by rktdnt but authored by others.
- Dates below distinguish author date from integration/committer date. The
  first nine authored patches have August/September author dates but were
  committed on September 4; they are not a wall-clock boot-test timeline.
- Commit links point to the configured donor fork on GitHub; local Git
  objects/reachability are the authoritative inventory. No fetch was needed.
  Read-only subagent patch inspection also used the fork's public patch pages.
- Donor source HEAD is not a claim that the running stock image was compiled
  from this exact commit; its observed release names `g5835eacd666d`.

## Complete authored inventory

HEAD means reachable from the inspected donor HEAD, not necessarily that the
patch's effects survived later reversals. Order follows reverse Git history,
not a promise of strictly increasing commit dates across divergent refs.

| Commit | Authored | Committed | In HEAD | Subject / actual contribution |
|---|---|---|---|---|
| [`1ae06a7b8924`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/1ae06a7b8924458eb35c0996f7edd797d26ab6b5) | 2026-08-10 | 2026-09-04 | Yes | **ARM64: mi8953: Rebrand Tiffany into Tissot** — Renames Tiffany board/config/machine identities to Tissot; existing display sequencing is inherited, not newly authored here. |
| [`5a0bd0c28fa0`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/5a0bd0c28fa05dfc9cfccc82a2ab4144b10c3c64) | 2026-08-12 | 2026-09-04 | Yes | **techpack: xiaomi-msm8953: Generalize device-specific ifdefs to CONFIG_MACH_XIAOMI_MSM8953** — Broadens device-specific compile guards to the Xiaomi MSM8953 family across six files; runtime identity remains a separate condition. |
| [`25ce807e2b56`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/25ce807e2b563359a3b3b95740202111a4241ce4) | 2026-08-12 | 2026-09-04 | Yes | **ARM64: dts: vendor: qcom: tissot: Import device tree nodes and configurations** — Board memory/QSEE/ramoops import; LAB/IBB entries, L6/L10/L17 always-on, Synaptics disabled, panel ESD checks disabled. |
| [`8271d6f88579`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/8271d6f88579f43dc383769304f3a879230eb3dd) | 2026-08-19 | 2026-09-04 | Yes | **techpack: xiaomi-msm8953: fingerprint: Update FPC1020 and Goodix drivers for 4.19** — FPC/Goodix 4.19 adaptation; Goodix compatible updated; GPIO16-19 mux changes from blsp_spi7 to blsp_spi5. |
| [`9c6eaa3a05df`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/9c6eaa3a05dfdac9232d5bc783d2a2887f3065ee) | 2026-08-19 | 2026-09-04 | Yes | **techpack: audio-legacy: tissot: Fix audio routing, MBHC headset detection and SmartPA** — Microphone routing, headset polarity/button handling, valid ext-PA GPIO checks and family-wide audio guards. |
| [`5efaf041e96f`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/5efaf041e96fda998667310e02e0660423a5c266) | 2026-08-19 | 2026-09-04 | Yes | **sound: soc: codecs: Avoid duplicate max98927 driver build** — Disables duplicate upstream MAX98927 object because donor techpack supplies its own codec implementation. |
| [`21648b24a26c`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/21648b24a26c9143990bba79a0b5c2298dd95bea) | 2026-08-19 | 2026-09-04 | Yes | **ARM64: configs: vendor: Add Tissot config and update vendor defconfigs** — Adds Tissot config fragment and selects board/family, display, audio, fingerprint and Android boot/security features. |
| [`e4940a0a936e`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/e4940a0a936ebeca06b7d280c9fe11b5d368144f) | 2026-09-01 | 2026-09-04 | Yes | **msm8953: Default KERNEL_MODULES_INSTALL to $(TARGET_COPY_OUT_VENDOR)** — Default module install destination changes system to vendor; later reversed by a3e1d0b92f1d. |
| [`3e4e779f2d90`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/3e4e779f2d90908fbf46521b8f7911b531d20403) | 2026-09-01 | 2026-09-04 | Yes | **msm8953-perf_defconfig: Disable CONFIG_MSM_RDBG** — Disables MSM_RDBG module selection; does not disable modules globally. |
| [`1991a2226fc7`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/1991a2226fc7e7f329b625b54839956d998061d4) | 2026-09-22 | 2026-09-22 | Yes | **Merge https://github.com/LineageOS/android_kernel_qcom_sm8250 into 16.2** — LineageOS SM8250 merge/integration; imported authorship must not be attributed wholesale to rktdnt. |
| [`7ccc9d4b0ea6`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/7ccc9d4b0ea65d91d52e6492cc16958fb202337f) | 2026-09-23 | 2026-09-23 | Yes | **prima: Restore headers corrupted during sm8250 merge** — Repairs ten Prima headers damaged by merge; compilation/header restoration, not GPU or WLAN performance tuning. |
| [`a3e1d0b92f1d`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/a3e1d0b92f1dbc64c56d0c3ff240f4d92c88f202) | 2026-09-23 | 2026-09-23 | Yes | **Revert "msm8953: Default KERNEL_MODULES_INSTALL to $(TARGET_COPY_OUT_VENDOR)"** — Reverts e4940a0a936e; retained module destination returns to system. |
| [`1dd4197c3595`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/1dd4197c3595214e1a04057d17d2c31469cb7027) | 2026-09-23 | 2026-09-23 | Yes | **techpack: Remove techpack/data from Kconfig** — Disconnects techpack/data Kconfig to avoid imported default-module selections; implementation is not deleted. |
| [`d3e1fb34bced`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/d3e1fb34bcede983324e63ed65c2985d5c4c4783) | 2026-09-25 | 2026-09-25 | Yes | **configs: Enable CONFIG_USB_DWC3_MSM** — Enables USB_DWC3_MSM in base defconfig. |
| [`bb0c58e310cf`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/bb0c58e310cf9b97e2a6608ccc7e1b45fcf28265) | 2026-09-26 | 2026-09-26 | No — backup ref | **usb: dwc3: Fix duplicate symbol link errors with MSM and MSM_LEGACY** — Backup-only MSM/legacy DWC3 duplicate-provider selection/exclusion patch; not current donor HEAD policy. |
| [`f6b2180a52c8`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/f6b2180a52c877fe8f8f62f0d8fb7ee76975b9fb) | 2026-09-26 | 2026-09-26 | No — backup ref | **Revert "usb: dwc3: import port dwc3-msm_legacy from msm-4.9"** — Backup-only revert of legacy DWC3 import, on top of bb0c58e310cf. |
| [`9d3bf7da9553`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/9d3bf7da955375e6113e92621bcab8470ff441f4) | 2026-09-26 | 2026-09-26 | Yes | **Revert "usb: dwc3: import port dwc3-msm_legacy from msm-4.9"** — Retained legacy DWC3 revert, on a different parent; patch-equivalent to f6b2180a52c8, not a second sequential revert. |
| [`251a3d6dfd9a`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/251a3d6dfd9af9116fc06d99fc8e0b669d4ffeec) | 2026-09-30 | 2026-09-30 | Yes | **techpack: audio: Fix missing DAPM widgets and invalid route warnings** — Adds UL30 DAPM routes/widgets and gates CDC-DMA/AUXPCM registrations/routes in both audio trees. |
| [`213a5ca68a93`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/213a5ca68a93d2f680e81ed8fdcb42e3f7765816) | 2026-10-06 | 2026-10-06 | Yes | **msm8953: configs: Disable CONFIG_SDCARD_FS** — Disables SDCARD_FS in base defconfig; mi8953.config change is only a final newline. |
| [`6bb26f9e58a3`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/6bb26f9e58a388cee84ba2c74a26480adbb87b1a) | 2026-10-06 | 2026-10-06 | Yes | **techpack: audio: Re-enable AUXPCM hostless DAIs** — Partially reverses AUXPCM registration gating so unconditional machine links can resolve AUXPCM_HOSTLESS; retains other routing fixes. |

### Applied by rktdnt, authored by others

| Commit | Original author | Author / commit date | Contribution |
|---|---|---|---|
| [`82a3ace2b0f0e46c70af63f872456f959806948a`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/82a3ace2b0f0e46c70af63f872456f959806948a) | HeroBuxx | 2026-09-02 / 2026-09-04 | Removes duplicate legacy `msm8953-smp2p.dtsi` include; modern nodes already provide the required SMEM properties. |
| [`6a36368699192cc9812a72cfeb28f9d13773295e`](https://github.com/kurision/kernel_xiaomi_msm8953_fork/commit/6a36368699192cc9812a72cfeb28f9d13773295e) | Mika | 2026-08-17 / 2026-09-25 | Adapts the USB DWC3 node to 4.19: OTG, parent sysdev, PHY/LPM quirks, core ID, high-speed rather than super-speed. |

Both are reachable from inspected donor HEAD. They are not rktdnt-authored
patches, even though the committer identity is rktdnt.

### Reversals and inherited groundwork

- `bb0c58e310cf` and `f6b2180a52c8` survive under
  `refs/remotes/origin/backup-260926/16.2`, not donor HEAD.
- The two legacy-DWC3 reverts `f6b2180a52c8` and `9d3bf7da9553`
  have identical stable patch ID `d7ebfdae4e136e102453a226ea69b4d6df7d28c1`,
  but different parents and resulting trees. Do not apply/count both as
  sequential fixes on the retained branch.
- Module installation's vendor destination was reverted; it is not the
  retained integration policy. AUXPCM was a partial reversal, not a wholesale
  revert of the DAPM patch.
- Mika's `84d75d3af10b353220822013f10ec4f96915ce42` imported the unified
  Tiffany/Tissot DT, panel and pinctrl groundwork. Mika's
  `46698dc5ec83f6ecceb53925856822c417eb82c1` imported the panel-dependent
  suspend reset/power logic. The rktdnt rebrand mostly renames these paths,
  guards and identities. LAB/IBB entries already existed in Mika's top-level
  board DT before rktdnt also placed them in `display.dtsi`.
- None of the **19 authored non-merge patches** directly changes
  `drivers/gpu/` or the KGSL UAPI. The merge imports other contributors'
  work and is excluded from that statement. No isolated rktdnt GPU-rendering
  fix was found in this inventory.

## Useful findings for the 6.12 port

Paths below are relative to ACK unless prefixed `donor/`, which means the
inspected `oc-test` tree. These are source comparisons, not device validation.

### 1. Panel policy assignment gap: source-only correction applied

Inherited OTM1911 policy sets `panel_suspend_reset_flag = 2` and
`panel_suspend_power_flag = 2`. Before the approved correction, ACK had
the following gap (line references in this baseline list predate the patch):

- `drivers/video/fbdev/msm/mdss_dsi.c:3296-3309` still wraps the assignments
  in `IS_ENABLED(CONFIG_MACH_XIAOMI_TISSOT)`. That symbol is absent from
  run210's embedded config and the inspected generated configuration.
- The runtime helper always returns Tissot
  (`include/xiaomi-msm8953/mach.h:33-35`), but cannot activate compiled-out code.
- Independently, the assignments live only in the command-line panel-name
  branch. An empty panel configuration jumps to the DT preferred-panel path
  (`mdss_dsi.c:3231-3237,3347-3349`), bypassing the assignments even if the
  guard were enabled.
- Run210 actually logs `dsi specific cfg not present`, then OTM1911 selection
  (`porting/artifacts/snapshot60/run210-logdump.log:478-481`).
- The consumer remains active: `mdss_dsi_panel.c:517-529` uses flag 2/3 to
  choose high/low/high/low reset pulses with 10-ms delays during disable;
  otherwise it just drives reset low.

**[INFERENCE, pre-patch]** On this build/selection route, the inherited
OTM1911 reset flag remained zero, so the donor's special disable waveform
was not selected. This is a behavior-preservation gap, **not proof of
run210's system-reset cause**. Merely adding the old config symbol would
not fix the DT-fallback route.

**Approved correction applied, source-only:** `mdss_dsi_config_panel()`
now sets Tissot policy after successful node selection and before
`mdss_dsi_panel_init()`, covering command-line selection and DT fallback.
The old `CONFIG_MACH_XIAOMI_TISSOT`-gated assignment was removed from
`mdss_dsi_find_panel_of_node()`. The runtime Tissot check remains.
`of_node_name_eq()` compares the actual selected node, not the human-readable
`qcom,mdss-dsi-panel-name` property: OTM1911's node is
`qcom,mdss_dsi_otm1911_fhd_video`, whereas its human label is
`otm1911 fhd video mode dsi panel`. Both flags retain TD4310=1,
OTM1911=2 and FT8716=3; an unrecognized selected Tissot node resets both
to zero rather than retaining stale policy. No selected node means no
policy reassignment. Non-Tissot selections leave this policy untouched.

`porting/logging/test_mdss_panel_policy.py` extracts and compiles the actual
selection/configuration functions and OF node-name comparison, with host
boundaries for OF lookup and panel initialization. It checks both routes,
all mappings, unknown-node defaults from stale flags, failed command-line
lookup/controller fallback, no-panel behavior, policy visibility at init,
and the runtime machine condition with the old config gate both off and on.
Validation command (passed on the corrected source):

```sh
python3 porting/logging/test_mdss_panel_policy.py
```

Reset waveform/timings, regulator flags/voltages, clocks and pinmux were not
changed. No kernel build, packaging, boot or device operation was performed;
existing images and run210 evidence do not contain or validate this change.
The host regression passed; the original functions failed its policy assertion.
The flag value after selection and at panel disable, plus whether disable is
reached, remain discriminating device observations requiring separate approval.
Flag 2 with the matching waveform would falsify the earlier inactive-branch
prediction on a newly built image; it would not establish the reset cause.

### 2. Retained donor power-policy difference: always-on LDOs

`25ce807e2b56` adds `regulator-always-on` for L6, L10 and L17, retained at
`donor/arch/arm64/boot/dts/vendor/qcom/mi8953/tissot/pmic.dtsi:78-88`.
ACK's definitions at `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts:
278-281,298-301,323-326` do not carry those constraints.

The port originally bound panel VDD/VDDIO to L17/L6. Further investigation
found that this was not the donor's effective topology: Tissot includes
`donor/.../msm8953-qrd-sku3.dtsi:87-90`, which explicitly deletes DSI0
`vdd-supply`. Read-only inspection of the running stock DT confirms absence;
stock regulator_summary assigns panel VDD to the dummy regulator, not L17.

**Source-only correction applied:** removed the port-only DSI0 VDD-to-L17
binding. Normal 6.12 `regulator_get()` supports the same dummy fallback.
Before/after host DT compilation and resolved-phandle comparison show only
this supply connection removed. L6/LAB/IBB and all other semantic DT
properties remain unchanged. See
`artifacts/snapshot60/panel-supply-source-check.json`.

The donor's always-on constraints remain an outstanding policy difference;
they were not added. Stock and 6.12 both enable always-on regulators during
registration and propagate errors. Provider behavior must be verified before
moving an RPM enable into registration. No RPM timeout was suppressed and
no new kernel image was built or booted. This correction does not diagnose
run210's reset or prove visible rendering.

### 3. Already carried: do not rediscover these as missing fixes

- OTM1911 timings, DCS on/off commands, reset sequence and WLED contract:
  `msm8953-xiaomi-tissot-mdss.dtsi:379-447`.
- LAB/IBB panel supply entries and IBB's 10-ms post-on delay: `:472-488`.
- Disabled OTM1911 panel-status checking: `:441`.
- QSEE secure-app window at `0x84a00000`: board DTS `:70-79`.
  Its size is deliberately different for ACK's memory map. **Do not copy the
  donor reservation sizes or its ramoops address blindly.** The port's SoC DT
  reserves a Venus region at `0x91400000`, while donor uses that address for
  ramoops; ACK's ramoops is elsewhere.
- Modern SMP2P nodes are present in ACK `msm8953.dtsi:334-406`; the applied
  donor duplicate-include fix is a useful integration lesson, not an identified
  missing fix in this port.

### 4. Reset/TE pinctrl: source-only fidelity correction applied

Before this correction ACK grouped GPIO61/24 as GPIO and omitted reset's
active `output-high`. The approved DT change separates reset GPIO61
(active GPIO/8 mA/no pull/output-high, suspend GPIO/2 mA/pull-down) from
TE GPIO24 (active and suspend `mdp_vsync`/2 mA/pull-down). DSI0 selects
both groups. These donor settings predate rktdnt's display/board patches.

Android common 6.12 supports the function and pinconf properties directly.
Before/after host DT compilation and resolved-phandle comparison verified
exact pins, functions, strengths, bias/output settings, state references and
unchanged supply topology. Evidence:
`artifacts/snapshot60/panel-pinctrl-source-check.json`.
No kernel image build, boot or device pin write was performed; necessity
of TE muxing for this video-mode/ESD-disabled configuration and any
rendering/reset effect remain unverified.

Donor LAB/IBB initialization asks for 5.7 V; ACK has translated standard
regulator constraints/operations. Its driver records 5.5-V stock selector
observations. Neither fact authorizes changing physical voltages. Display
clocks/GDSC use translated 6.12 providers, not identical downstream bindings.

### 5. Useful non-display lessons, not immediate rendering patches

Follow-on applicability audit: after the panel-policy correction, remaining
Tissot/family compile guards in the imported display stack cover a panel
pointer with no imported consumer or redundant machine-header includes.
Other guarded runtime paths target other Xiaomi boards, not Tissot.
No additional functional guard change is justified; obsolete config symbols
were not enabled merely to expose dead/unconsumed branches.

The remaining audio/fingerprint work crosses a subsystem boundary:
run210 enables mainline QDSP6 and MAX98927, but this board DT has no sound
card/DAI-link endpoints and no donor `msm8952` machine/legacy routing stack.
The upstream codec already acquires the reset GPIO using descriptor APIs.
Donor MBHC/AUXPCM/DSM patches therefore cannot be applied to matching
existing machine-driver paths. Fingerprint FPC1020/Goodix implementations,
their kernel-side vendor ABI support and board nodes are absent from this port.
Restoring either function needs a separately scoped 6.12 integration,
not guard broadening or the addition of unbound DT nodes. Neither is
implemented by the display changes recorded above.


- **Guard coverage:** `5a0bd0c28fa0` explicitly broadened compilation gates;
  an unconditional machine helper alone does not preserve donor behavior.
- **One implementation per hardware function:** `5efaf041e96f` avoids two
  MAX98927 providers. The USB history similarly repairs competing DWC3
  providers. Run210 uses QCOM DWC3, not donor MSM/legacy glue. Do not copy a
  donor Makefile disablement when ACK uses the upstream implementation.
- **Audio dependency completeness:** `6bb26f9e58a3` restores AUXPCM DAIs
  needed by unconditional machine links. Trace machine links, DAI registrations
  and DAPM routes together rather than deleting apparently unused producers.
- **Fingerprint hardware data:** GPIO16-19 `blsp_spi5` and the Goodix
  compatible change are useful references. The fingerprint commit does not
  itself move the controller node despite broader commit-message wording.
- **Import cleanup:** Prima header repair, disabling RDBG/default data
  modules, and sdcardfs selection are integration/build lessons. None provides
  a demonstrated explanation for the current blink/reset.

## Reproducing the history inspection

```sh
cd /home/kurision/development/kernel/oc-test
git log --all --reverse --author=rktdnt \
  --format='%H %ad %cd %an <%ae> %s' --date=short
git log HEAD --author=rktdnt --format='%H %s'
git log --all --committer=rktdnt --format='%H %an | %cn | %s'
git show 25ce807e2b56
git show 46698dc5ec83
git for-each-ref --contains=bb0c58e310cf --format='%(refname)'
git for-each-ref --contains=f6b2180a52c8 --format='%(refname)'
```

The commit inventory, reachability, duplicate patch IDs and relevant diffs
were exercised against local Git; the selected current-source differences
were inspected. The history-inspection phase made no kernel source/config
changes, build, boot or electrical measurements. The subsequent approved
source-only policy correction and validated host regression are recorded in
section 1. Run210 evidence remains the device baseline.
