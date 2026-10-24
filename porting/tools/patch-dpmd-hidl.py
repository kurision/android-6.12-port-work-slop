#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Create an offline dpmd copy with matching HIDL mapping-size requests.

Use the device's `getconf PAGESIZE` result for --page-size. This tool neither
installs nor executes the result. See ../findings/2026-10-24-live-failure-inventory.md.
"""

import argparse
import hashlib
from pathlib import Path


DPMD_SHA256 = "30a02d9a00f3496a1885409f6e6e5db7d4276fdb4ae56d1fec3d53e4ff9caeb8"
HIDL_SHA256 = "343d42aa7b046a2c060dd170e9ed68e668a04bf669babc4e672636d91a2dd535"
PATCHED_SHA256 = "61db21d3ac67a266576e99a8b2fbef304d3ae2a84ebc19e14ffe44ae0bb72646"
OFFSET = 0x5468
BEFORE = bytes.fromhex("e0 03 13 32")
AFTER = bytes.fromhex("e0 1b 13 32")


def patch_binary(dpmd, hidl, page_size):
    if page_size != 4096:
        raise ValueError("only the verified 4096-byte device page size is supported")
    if len(dpmd) != 29272 or hashlib.sha256(dpmd).hexdigest() != DPMD_SHA256:
        raise ValueError("unrecognized dpmd; input SHA256/size must match the verified binary")
    if hashlib.sha256(hidl).hexdigest() != HIDL_SHA256:
        raise ValueError("unrecognized libhidlbase.so; default mapping size is unverified")
    if dpmd[OFFSET:OFFSET + 4] != BEFORE:
        raise ValueError("unexpected instruction at dpmd file offset 0x5468")
    # Match the installed HIDL default (1 MiB minus two pages), keeping its check.
    patched = dpmd[:OFFSET] + AFTER + dpmd[OFFSET + 4:]
    if hashlib.sha256(patched).hexdigest() != PATCHED_SHA256:
        raise ValueError("candidate SHA256 differs from the verified result")
    return patched


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dpmd", type=Path)
    parser.add_argument("hidl", type=Path, help="matching /system/lib64/libhidlbase.so")
    parser.add_argument("output", type=Path, help="new output file; never overwritten")
    parser.add_argument("--page-size", type=int, required=True,
                        help="actual device getconf PAGESIZE result")
    args = parser.parse_args(argv)
    try:
        patched = patch_binary(args.dpmd.read_bytes(), args.hidl.read_bytes(),
                               args.page_size)
        with args.output.open("xb") as stream:
            stream.write(patched)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    print(f"{PATCHED_SHA256}  {args.output}")
    print("Offline candidate only; device behavior has not been validated.")


if __name__ == "__main__":
    main()
