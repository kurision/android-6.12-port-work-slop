#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the resolved Tissot DTB: python3 test_cpu_thermal_maps.py board.dtb.

Host-only wiring/OPP check using fdtget; does not prove runtime mitigation.
"""

import subprocess
import sys


def check(dtb):
    def prop(node, name, kind="u"):
        value = subprocess.check_output(
            ["fdtget", "-t", kind, dtb, node, name], text=True
        ).strip()
        return value if kind == "s" else [int(cell) for cell in value.split()]

    def children(node):
        return subprocess.check_output(
            ["fdtget", "-l", dtb, node], text=True
        ).split()

    def scalar(node, name):
        value = prop(node, name)
        assert len(value) == 1, (node, name, value)
        return value[0]

    cpu0 = "/cpus/cpu@0"
    cooling_phandle = scalar(cpu0, "phandle")
    opp_phandle = scalar(cpu0, "operating-points-v2")
    for address in ("0", "1", "2", "3", "100", "101", "102", "103"):
        assert scalar(f"/cpus/cpu@{address}", "operating-points-v2") == opp_phandle
    opp = next(
        f"/{name}" for name in children("/")
        if name.startswith("opp-table")
        and scalar(f"/{name}", "phandle") == opp_phandle
    )
    assert "opp-shared" in subprocess.check_output(
        ["fdtget", "-p", dtb, opp], text=True
    ).split()
    frequencies = []
    for name in children(opp):
        hi, lo = prop(f"{opp}/{name}", "opp-hz")
        frequencies.append((hi << 32) | lo)
    frequencies.sort(reverse=True)
    assert len(frequencies) == 19, frequencies
    assert frequencies[8] == 2016000000, frequencies
    assert frequencies[18] == 480000000, frequencies

    for cpu, sensor in enumerate((9, 10, 11, 12, 4, 5, 6, 7)):
        zone = f"/thermal-zones/cpu{cpu}-thermal"
        assert prop(zone, "thermal-sensors")[1] == sensor
        assert scalar(zone, "polling-delay") == 100
        assert scalar(zone, "polling-delay-passive") == 50
        assert sorted(children(f"{zone}/cooling-maps")) == ["map0", "map1"]
        for trip, temperature, kind in (
            ("trip-point0", 80000, "passive"),
            ("trip-point1", 88000, "passive"),
            ("crit", 100000, "critical"),
        ):
            path = f"{zone}/trips/{trip}"
            assert scalar(path, "temperature") == temperature, path
            assert scalar(path, "hysteresis") == 2000, path
            assert prop(path, "type", "s") == kind, path
        for index, limits in enumerate(((8, 0xFFFFFFFF), (18, 18))):
            path = f"{zone}/cooling-maps/map{index}"
            assert prop(path, "cooling-device") == [cooling_phandle, *limits], path
            trip = f"{zone}/trips/trip-point{index}"
            assert scalar(path, "trip") == scalar(trip, "phandle"), path

    gpu = "/thermal-zones/gpu-thermal/trips"
    assert scalar(f"{gpu}/trip-point0", "temperature") == 70000
    assert scalar(f"{gpu}/crit", "temperature") == 90000
    assert prop(f"{gpu}/crit", "type", "s") == "critical"
    print("PASS: all 8 CPU zones share cooling; 80/88 C stages and critical trips intact")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} tissot.dtb")
    check(sys.argv[1])
