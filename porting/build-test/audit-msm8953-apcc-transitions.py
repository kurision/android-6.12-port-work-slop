#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the shared APCC transaction regression suite (host mocks, not hardware)."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("test-msm8953-apcc.py")),
                   run_name="__main__")
