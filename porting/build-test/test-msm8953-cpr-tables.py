#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check CPR table dimensions in the bring-up DTS source, not compiled/live DT."""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def check(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)

    def rows(name):
        match = re.search(re.escape(name) + r"\s*=\s*([^;]+);", source)
        assert match, f"missing {name}"
        return [[int(cell.strip("()"), 0) for cell in group.split()]
                for group in re.findall(r"<([^>]*)>", match[1])]

    def shape(name, expected):
        actual = [len(row) for row in rows(name)]
        assert actual == expected, f"{name}: row lengths {actual}, expected {expected}"

    bins = rows("qcom,cpr-speed-bin-corners")[0]
    bin_count = rows("qcom,cpr-speed-bins")[0][0]
    combos = rows("qcom,cpr-fuse-combos")[0][0]
    fuse_corners = rows("qcom,cpr-fuse-corners")[0][0]
    assert len(bins) == bin_count and combos % bin_count == 0
    revisions = combos // bin_count
    assert rows("qcom,cpr-corners") == [[n] * revisions for n in bins]
    active = [n for n in bins if n]

    for name in ("qcom,cpr-voltage-ceiling", "qcom,cpr-voltage-floor",
                 "qcom,mem-acc-voltage", "qcom,corner-frequencies"):
        shape(name, active)
    shape("qcom,cpr-floor-to-ceiling-max-range",
          [n for n in active for _ in range(revisions)])
    # MSM8953_MISC_FUSE_VAL_COUNT is BIT(1): two possible misc fuse values.
    shape("qcom,cpr-misc-fuse-voltage-adjustment",
          [n for n in active for _ in range(2)])
    shape("qcom,cpr-corner-fmax-map", [fuse_corners] * bin_count)
    for name in ("qcom,cpr-open-loop-voltage-fuse-adjustment",
                 "qcom,cpr-closed-loop-voltage-fuse-adjustment"):
        shape(name, [fuse_corners] * combos)


if __name__ == "__main__":
    check((REPO / "arch/arm64/boot/dts/qcom/msm8953-cpu.dtsi").read_text())
    print("PASS: CPR per-bin, per-revision and misc-fuse table dimensions")
