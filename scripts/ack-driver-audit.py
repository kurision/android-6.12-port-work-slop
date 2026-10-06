#!/usr/bin/env python3
"""Report which device-tree nodes the kernel tree can actually drive.

A node binds if *any* string in its `compatible` list is matched by an of_match
table in the tree, because DT binding uses fallback lists: "qcom,msm8953-sdhci",
"qcom,sdhci-msm-v4" is bound by the second entry. Scoring individual strings
separately understates coverage badly.

For each bound node the driver file is resolved to the CONFIG symbol its own
directory Makefile assigns, so the output says not just "bound" but "bound and
compiled in".

Usage:
  scripts/ack-driver-audit.py --dtb <path.dtb> --tree <kernel-tree> [--config <.config>]
                              [--only-unbound] [--only-disabled]

Exit status is 0 unless the dtb cannot be read.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
OF_MATCH_RE = re.compile(r'\.compatible\s*=\s*([^;]+);', re.DOTALL)
QUOTED_RE = re.compile(r'"([^"]+)"')
OBJ_RE = re.compile(r'obj-\$\(CONFIG_([A-Za-z0-9_]+)\)\s*\+=\s*(\S+)')
SCAN_DIRS = ("drivers", "sound", "net", "fs", "arch/arm64")
SKIP_SOURCES = {("drivers", "of", "platform.c")}

# Nodes the kernel core consumes directly rather than binding through of_match:
# CPUs and caches, memory and reservations, OPP tables, timers, firmware.
NOT_A_DEVICE_PREFIX = ("/cpus", "/reserved-memory", "/memory", "/timer", "/chosen",
                       "/firmware", "/aliases", "/soc@0/interrupt-controller")
NOT_A_DEVICE_COMPAT = ("operating-points-v2", "shared-dma-pool", "fixed-clock",
                       "arm,armv8-timer", "armv8-timer", "cache")


def nodes(dtb: Path) -> list[tuple[str, list[str], str]]:
    """(path, compatible list, status) for every node that declares a compatible."""
    listing = subprocess.run(["fdtget", "-l", str(dtb), "/"],
                             check=True, capture_output=True, text=True).stdout.split()
    found: list[tuple[str, list[str], str]] = []

    def walk(path: str) -> None:
        for name in subprocess.run(["fdtget", "-l", str(dtb), path],
                                   check=True, capture_output=True,
                                   text=True).stdout.split():
            child = f"{path.rstrip('/')}/{name}"
            try:
                raw = subprocess.run(["fdtget", "-t", "s", str(dtb), child, "compatible"],
                                     check=True, capture_output=True, text=True).stdout
            except subprocess.CalledProcessError:
                raw = ""
            if raw.strip():
                compat = [c for c in raw.split() if c]
                status = "okay"
                try:
                    status = subprocess.run(["fdtget", "-t", "s", str(dtb), child, "status"],
                                            check=True, capture_output=True,
                                            text=True).stdout.strip() or "okay"
                except subprocess.CalledProcessError:
                    pass
                found.append((child, compat, status))
            walk(child)

    walk("/")
    _ = listing
    return found


def of_matches(tree: Path) -> dict[str, str]:
    """compatible -> driver source file, for every of_match in the tree."""
    mapping: dict[str, str] = {}
    for scan in SCAN_DIRS:
        base = tree / scan
        if not base.is_dir():
            continue
        for src in base.rglob("*.c"):
            if tuple(src.relative_to(tree).parts) in SKIP_SOURCES:
                continue
            try:
                text = src.read_text(errors="ignore")
            except OSError:
                continue
            for rhs in OF_MATCH_RE.findall(text):
                # The right-hand side may be a plain string or a macro list such as
                # OF_MATCH_COMPATIBLE("a"), "b", so take every quoted string in it.
                for value in QUOTED_RE.findall(rhs):
                    mapping.setdefault(value, str(src.relative_to(tree)))
    return mapping


def symbol_table(tree: Path) -> dict[tuple[str, str], str]:
    """(driver directory, object name) -> CONFIG symbol, from obj-$(CONFIG_x)."""
    table: dict[tuple[str, str], str] = {}
    for makefile in tree.rglob("Makefile"):
        if "out" in makefile.parts or ".git" in makefile.parts:
            continue
        try:
            text = makefile.read_text(errors="ignore")
        except OSError:
            continue
        directory = str(makefile.parent.relative_to(tree))
        for symbol, obj in OBJ_RE.findall(text):
            table.setdefault((directory, obj), f"CONFIG_{symbol}")
    return table


def enabled_symbols(config: Path | None) -> set[str]:
    if not config or not config.is_file():
        return set()
    enabled = set()
    for line in config.read_text(errors="ignore").splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            if value.strip() in ("y", "m"):
                enabled.add(key)
    return enabled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dtb", required=True, type=Path)
    parser.add_argument("--tree", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--only-unbound", action="store_true",
                        help="print only nodes with no matching driver")
    parser.add_argument("--only-disabled", action="store_true",
                        help="consider only nodes with status = \"okay\"")
    args = parser.parse_args()

    if not args.dtb.is_file():
        print(f"no such dtb: {args.dtb}", file=sys.stderr)
        return 1

    matches = of_matches(args.tree)
    symbols = symbol_table(args.tree)
    enabled = enabled_symbols(args.config)

    total = driven = built = unbound = core = 0
    for path, compat, status in nodes(args.dtb):
        if args.only_disabled and status != "okay":
            continue
        if path.startswith(NOT_A_DEVICE_PREFIX) or any(c in NOT_A_DEVICE_COMPAT for c in compat):
            core += 1
            continue
        total += 1
        hit = next((c for c in compat if c in matches), None)
        if not hit:
            unbound += 1
            if args.only_unbound:
                print(f"NOBIND   {status:<6} {path:<44} {' '.join(compat)}")
            continue
        driven += 1
        src = matches[hit]
        obj = Path(src).name[:-2] + ".o"
        symbol = symbols.get((str(Path(src).parent), obj), "?")
        is_built = symbol in enabled
        built += int(is_built)
        if not args.only_unbound:
            state = "BUILT  " if is_built else "NOTBLD "
            print(f"{state} {status:<6} {path:<44} {symbol:<34} {src}")

    if not args.only_unbound:
        print(f"\n{total} device nodes: {driven} have a driver ({built} compiled in), "
              f"{unbound} have none, {core} are core-reserved nodes (cpus, opp tables, "
              f"memory, timer)")
        if unbound:
            print(f"Use --only-unbound to list the {unbound} nodes that need a ported "
                  f"or newly written driver.")
    return 0


if __name__ == "__main__":
    sys.exit(main())