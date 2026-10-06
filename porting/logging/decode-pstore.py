#!/usr/bin/env python3
"""Decode pstore/ramoops records captured on the device.

The kernel stores these deflate-compressed (CONFIG_PSTORE_COMPRESS=y), so a raw
`cat` of /sys/fs/pstore/dmesg-ramoops-0 is binary garbage. This handles both
compressed and plain records and prints the text.

    python3 decode-pstore.py pstore/dmesg-ramoops-0 pstore/pstore_ftrace-0

With no arguments it walks ./pstore (or /sys/fs/pstore when readable).
"""

import sys
import zlib
import pathlib


def decode(path: pathlib.Path) -> str | None:
    raw = path.read_bytes()
    if not raw:
        return None
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, zlib.MAX_WBITS | 16):
        try:
            return zlib.decompress(raw, wbits).decode("utf-8", "replace")
        except zlib.error:
            continue
    # not compressed: strip NUL padding the way the kernel writes it
    return raw.decode("utf-8", "replace").rstrip("\x00")


def main(argv: list[str]) -> int:
    if argv:
        paths = [pathlib.Path(a) for a in argv]
    else:
        root = pathlib.Path("pstore")
        if not root.is_dir():
            root = pathlib.Path("/sys/fs/pstore")
        paths = sorted(p for p in root.iterdir() if p.is_file()) if root.is_dir() else []

    if not paths:
        print("no pstore records found (empty = no crash recorded yet)", file=sys.stderr)
        return 1

    for p in paths:
        text = decode(p)
        print(f"===== {p} =====")
        if text is None:
            print("(empty)")
            continue
        lines = [l for l in text.splitlines() if l.strip()]
        print(f"{len(lines)} lines")
        if "ftrace" in p.name:
            print("(function graph: first frames)")
            print("\n".join(lines[:40]))
        else:
            print("(last 60 lines — the interesting part)")
            print("\n".join(lines[-60:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))