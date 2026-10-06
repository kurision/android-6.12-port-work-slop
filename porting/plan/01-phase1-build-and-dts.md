# Phase 1 — make the tissot device tree build

**Goal:** `msm8953-xiaomi-tissot.dts` preprocesses and compiles, the image boots
to a UART console with all 8 CPUs.

## Why it is blocked

`msm8953-xiaomi-tissot.dts:10` includes `"pmi8950.dtsi"` and line 148 overrides
`&pmi8950_wled`; no such file exists upstream. Verified with the standalone
harness in `porting/build-test/`:

```
fatal error: 'pmi8950.dtsi' file not found
```

## Steps

1. **Add `arch/arm64/boot/dts/qcom/pmi8950.dtsi`** — `drafts/pmi8950.dtsi` is
   ready to drop in. It defines `pmic@3` (USID 3) with:
   * `haptics@c000` — `qcom,pmi8950-haptics`,`qcom,spmi-haptics`,
     irq short/play, `qcom,actuator-type = <1>`, brake pattern `<3 3 0 0>`,
     wave rate 5263 µs — transcribed from `artifacts/tissot-live.dts:2660-2671`.
   * `leds@d800` — `qcom,pmi8950-wled`, regs 0xd800/0xd900, ovp/short irqs,
     current limit 20 mA, OVP 29.5 V, `status = "disabled"` (the board file
     enables it and adds `num-strings`/`external-pfet`/`cabc`).
   * `labibb` with `lab` and `ibb` — the DSI panel's VSP/VSN rails. Upstream
     `drivers/regulator/qcom-labibb-regulator.c` matches `"qcom,pmi8998-lab-ibb"`,
     which is the second string in the CAF compatible, so these bind with no
     driver work.

   *Not included on purpose:* `pwm` (disabled in CAF too) and the charger /
   fuel-gauge nodes — no upstream driver exists for either, so they would be
   dead weight.

2. **Fix the five `dtc` warnings** so the tree passes `dtc -Werror` in CI:
   * `unique_unit_address`: `i2c@78b7000`/`spi@78b7000`, `i2c@7af5000`/`spi@7af5000`,
     `i2c@7af6000`/`spi@7af6000`, `i2c@7af7000`/`spi@7af7000` share addresses.
     Upstream convention is to keep the node and drop the duplicate unit-address
     from the one that does not need it (or rename to `i2c@1` style), which is
     what other msm dtsis do.
   * `avoid_unnecessary_addr_size` on `dsi@1a94000`: drop
     `#address-cells`/`#size-cells` from the DSI host node.

3. **Decide the boot path** and adjust `reserved-memory` accordingly:
   * booting with the **stock Android bootloader** → keep the three
     `/delete-node/` lines;
   * booting with **your own DTB** (lk2nd / fastboot explicit dtb / U-Boot) →
     delete `/delete-node/ &adsp_fw_mem;`, `&qseecom_mem;`, `&wcnss_fw_mem;` so the
     regions are reserved by the DT itself (sizes verified against the device:
     adsp 0x1200000, ssecmem 0x1900000, wcnss 0x700000).

4. **Build**: `make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- msm8953-xiaomi-tissot.dtb`,
   then the image/`Image.gz-dtb`, then flash through whatever bootloader you use.

## Risks

* PMI8950 base node will probe the SPMI PMIC even with all children disabled —
  that is harmless (the same happens for pm8953/pmic@0).
* `qcom,spmi-pmic` at USID 3 with no driver for WLED/haptics: the nodes stay
  inert. No error spam, but also no backlight/haptics until phase 3.

## Verification

```sh
# on the device, after booting the new kernel
cat /proc/device-tree/model; echo
cat /proc/cpuinfo | grep -c processor          # expect 8
dmesg | grep -E 'psci|smp: Brought up|Machine model'
```

Accept when: 8 CPUs online, no DT-related errors, console on UART/serial.
Record the new `dmesg` in `artifacts/` before starting phase 2.