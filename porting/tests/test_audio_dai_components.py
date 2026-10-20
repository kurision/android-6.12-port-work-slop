#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the CAF CPU/platform split without building or booting a kernel."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = r"struct snd_soc_dai_link_component\[\]"
CPU = re.compile(
    rf"\.cpus = \({COMPONENT}\)\{{(.*?)\n\t\t\}},"
    r"\s*\.num_cpus = (\d+),",
    re.S,
)
PLATFORM = re.compile(
    rf"\s*\.platforms = \({COMPONENT}\)\{{\s*"
    r'COMP_PLATFORM\("([^"]+)"\),\s*\},\s*\.num_platforms = (\d+),'
)


class AudioDaiComponents(unittest.TestCase):
    def test_cpu_platform_split(self):
        for filename, count in (("msm8952.c", 67),
                                ("msm8952-dai-links.c", 83)):
            with self.subTest(file=filename):
                text = (ROOT / "sound/soc/msm" / filename).read_text()
                cpus = list(CPU.finditer(text))
                self.assertEqual(len(cpus), count)
                for cpu in cpus:
                    self.assertEqual(cpu[2], "1", cpu[0])
                    names = re.findall(r'\.dai_name = "([^"]+)"', cpu[1])
                    self.assertEqual(len(names), 1, cpu[0])
                    platform = PLATFORM.match(text, cpu.end())
                    self.assertIsNotNone(platform, cpu[0])
                    self.assertEqual(platform[2], "1")
                    self.assertNotEqual(names[0], platform[1])
                    self.assertFalse(names[0].startswith((
                        "msm-pcm-", "msm-compress-", "msm-lsm-",
                        "msm-voip-", "msm-cpe-")), names[0])


if __name__ == "__main__":
    unittest.main()
