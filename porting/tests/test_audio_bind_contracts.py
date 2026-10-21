#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source-contract checks for run340's PCM bind and MBHC cleanup failures."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class AudioBindContracts(unittest.TestCase):
    def test_compressed_dais_match_donor(self):
        text = (ROOT / "sound/soc/msm/msm-dai-fe.c").read_text()
        ops = dict(re.findall(
            r"struct snd_soc_dai_ops (\w+) = \{(.*?)\n\};", text, re.S))
        array = text.split("msm_fe_dais[] = {", 1)[1].split("\n};", 1)[0]
        compressed = set()
        multimedia = set()
        for block in array.split("\n\t},"):
            name = re.search(r'\.name = "(MultiMedia\d+)"', block)
            if not name:
                continue
            multimedia.add(name[1])
            dai_ops = re.search(r"\.ops = &(\w+)", block)[1]
            if "compress_new" in ops[dai_ops]:
                compressed.add(name[1])
                self.assertEqual(int(".capture =" in block) +
                                 int(".playback =" in block), 1, name[1])
        self.assertEqual(multimedia, {f"MultiMedia{i}" for i in range(1, 31)})
        self.assertEqual(compressed, {
            f"MultiMedia{i}" for i in
            (4, 7, 11, 12, 13, 14, 15, 17, 18, 19, 26, 27, 28, 29, 30)
        })

    def test_analog_mbhc_backend_and_failure_contract(self):
        msm = ROOT / "sound/soc/msm"
        kconfig = (msm / "Kconfig").read_text()
        analog = kconfig.split("config SND_SOC_ANALOG_CDC\n", 1)[1]
        analog = analog.split("\nconfig ", 1)[0]
        self.assertIn("select SND_SOC_MSM_WCD_MBHC", analog)
        mbhc = kconfig.split("config SND_SOC_MSM_WCD_MBHC\n", 1)[1]
        mbhc = mbhc.split("\nconfig ", 1)[0]
        self.assertIn("select SND_SOC_WCD_MBHC_LEGACY", mbhc)
        objects = re.search(r"^mbhc_dlkm-y := (.*)$",
                            (msm / "Makefile").read_text(), re.M)[1]
        self.assertIn("wcd-mbhc-legacy.o", objects.split())
        self.assertRegex((msm / "msm-analog-cdc.c").read_text(),
                         r"ret = wcd_mbhc_init\([^;]+;\s*"
                         r"if \(ret\)\s*return ret;")
        self.assertRegex((msm / "wcd-mbhc-v2.c").read_text(),
                         r'pr_err\("%s: mbhc function pointer is NULL[^;]+;'
                         r"\s*ret = -EINVAL;\s*goto err_mbhc_sw_irq;")


if __name__ == "__main__":
    unittest.main()
