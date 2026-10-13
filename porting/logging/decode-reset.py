#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Decode opt-in ACKRESET1 evidence from a 64 MiB diagnostic logdump."""

import argparse
from pathlib import Path
import re

OFFSET = 0x3F30000
SIZE = 65536
HEADER = 512
PARTITION_SIZE = 67108864


def decode(blob):
    if len(blob) != PARTITION_SIZE:
        raise ValueError(f"expected {PARTITION_SIZE} bytes, got {len(blob)}")
    record = blob[OFFSET:OFFSET + SIZE]
    header = record[:HEADER].split(b"\0", 1)[0]
    if not header.startswith(b"ACKRESET1 "):
        return None
    match = re.fullmatch(
        rb"ACKRESET1 timestamp_ns=(\d+) action=(\d+) pid=(\d+) "
        rb"comm=([^\n]*) command=([^\n]*) tail_bytes=(\d+)\n", header)
    if match is None:
        raise ValueError("malformed ACKRESET1 header")
    length = int(match.group(6))
    if int(match.group(1)) == 0 or length > SIZE - HEADER:
        raise ValueError("invalid ACKRESET1 timestamp or tail length")
    return header + record[HEADER:HEADER + length]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logdump", type=Path)
    args = parser.parse_args()
    try:
        result = decode(args.logdump.read_bytes())
    except (OSError, ValueError) as error:
        parser.exit(1, f"decode-reset: {error}\n")
    if result is None:
        print("No ACKRESET1 record; this does not establish the reset cause.")
    else:
        import sys
        sys.stdout.buffer.write(result)


if __name__ == "__main__":
    main()
