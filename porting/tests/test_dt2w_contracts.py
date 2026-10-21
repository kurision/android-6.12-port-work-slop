#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source-level DT2W ordering/ABI guards; not a hardware or concurrency test."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRIVER = (ROOT / "drivers/input/touchscreen/edt-ft5x06.c").read_text()


def function(name):
    start = DRIVER.index("\n{", DRIVER.index(" " + name + "("))
    end = DRIVER.index("\n}", start)
    return DRIVER[start:end]


class Dt2wContracts(unittest.TestCase):
    def ordered(self, text, *tokens):
        positions = [text.index(token) for token in tokens]
        self.assertEqual(positions, sorted(positions))

    def test_unblank_records_intent_even_before_entry_completes(self):
        notifier = function("edt_ft5x06_fb_event")
        self.assertNotIn("gesture_active", notifier)
        self.assertIn("ev->info->node != 0", notifier)
        self.ordered(notifier, "spin_lock_irq", "display_off = off",
                     "if (!tsdata->pm_blocked)", "schedule_work",
                     "spin_unlock_irq")
        self.assertIn("off && !tsdata->display_off", notifier)

    def test_pm_drains_work_before_hardware_and_requeues_after_resume(self):
        suspend = function("edt_ft5x06_ts_suspend")
        self.ordered(suspend, "pm_blocked = true", "spin_unlock_irq",
                     "cancel_work_sync", "edt_ft5x06_display_update",
                     "PMOD_REGISTER_HIBERNATE", "regulator_disable")
        resume = function("edt_ft5x06_ts_resume")
        self.ordered(resume, "regulator_enable", "unblock:",
                     "pm_blocked = false", "schedule_work")
        self.assertIn("if (!blocked)", function("edt_ft5x06_display_work"))

    def test_irq_is_drained_outside_mutex(self):
        for name in ("edt_ft5x06_display_update", "edt_ft5x06_gesture_cleanup"):
            with self.subTest(function=name):
                self.ordered(function(name), "disable_irq(", "mutex_lock(",
                             "mutex_unlock(")
        self.assertNotIn("mutex_lock", function("edt_ft5x06_ts_isr"))

    def test_enter_verifies_firmware_before_arming_wake(self):
        enter = function("edt_ft5x06_gesture_enter")
        self.ordered(enter, "edt_ft5x06_release_input", "regmap_write",
                     "regmap_read", "if (state != 1)",
                     "device_wakeup_enable", "enable_irq_wake",
                     "gesture_active, true")
        self.assertIn("device_wakeup_disable", enter)
        self.assertIn("edt_ft5x06_gesture_reset", enter)
        release = function("edt_ft5x06_release_input")
        self.assertIn("input_report_key", release)
        self.assertIn("input_mt_report_slot_state", release)
        self.assertIn("input_sync", release)

    def test_leave_restores_reporting_and_balances_wake(self):
        self.ordered(function("edt_ft5x06_gesture_leave"), "disable_irq_wake",
                     "edt_ft5x06_gesture_reset", "gesture_active, false",
                     "device_wakeup_disable")
        self.assertIn("edt_ft5x06_restore_reg_parameters",
                      function("edt_ft5x06_gesture_reset"))
        self.ordered(function("edt_ft5x06_gesture_cleanup"),
                     "unregister_sysctl_table", "fb_unregister_client",
                     "cancel_work_sync", "disable_irq(")

    def test_rom_abi_is_bounded_and_board_gated(self):
        init = function("edt_ft5x06_gesture_init")
        self.assertIn("if (!tsdata->gesture_wakeup)", init)
        for token in ('"dev/xiaomi_msm8953_touchscreen"', '"enable_dt2w"',
                      ".mode = 0644", "SYSCTL_ZERO", "SYSCTL_ONE"):
            self.assertIn(token, init)
        handler = function("edt_ft5x06_dt2w_sysctl")
        self.assertIn("proc_dointvec_minmax", handler)
        self.assertNotIn("schedule_work", handler)
        board = (ROOT / "arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dts")
        binding = (ROOT / "Documentation/devicetree/bindings/input/touchscreen/"
                   "edt-ft5x06.yaml")
        self.assertIn("edt,gesture-wakeup;", board.read_text())
        self.assertIn("edt,gesture-wakeup:", binding.read_text())


if __name__ == "__main__":
    unittest.main()
