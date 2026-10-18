#!/usr/bin/env python3
"""Compare the ioctls a vendor libadsprpc issues with what this driver accepts.

The CAF adsprpc headers and this driver number their ioctls differently, and
_IOC also encodes direction and payload size, so a CAF command either gets
rejected with -ENOTTY or, when number and size happen to agree, is accepted
and runs against the wrong handler with the wrong payload layout.

Usage:
    python3 fastrpc-ioctl-audit.py <libadsprpc.so> [--header include/uapi/misc/fastrpc.h]

The vendor constants are recovered from the aarch64 instruction stream: the
compiler materialises each _IOC value as a MOV/MOVK pair into a scratch
register, so it never appears as a contiguous 32-bit literal.
"""

import argparse
import re
import subprocess
import sys

MOV = re.compile(r"^\s*[0-9a-f]+:\s+mov\s+(w\d+|x\d+),\s+#(-?0x[0-9a-f]+)")
MOVK = re.compile(r"^\s*[0-9a-f]+:\s+movk\s+(w\d+|x\d+),\s+#(-?0x[0-9a-f]+),\s+lsl #16")

# adsprpc_shared.h in the donor tree; 17..21 are newer than that header.
CAF = {
    1: ("INVOKE", 16), 2: ("MMAP", 32), 3: ("MUNMAP", 16), 4: ("INVOKE_FD", 24),
    5: ("SETMODE", 4), 6: ("INIT", 40), 7: ("INVOKE_ATTRS", 32), 8: ("GETINFO", 4),
    9: ("GETPERF", 24), 10: ("INIT_ATTRS", 48), 11: ("INVOKE_CRC", 40),
    12: ("CONTROL", 12), 13: ("MUNMAP_FD", 24), 14: ("MMAP_64", 40),
    15: ("MUNMAP_64", 40), 16: ("GET_DSP_INFO", 32),
    17: ("(newer than donor)", 12), 18: ("(newer than donor)", 24),
    19: ("(newer than donor)", 64), 20: ("(newer than donor)", 48),
    21: ("(newer than donor)", 56),
}


def ioc(nr, size):
    return (3 << 30) | ((size & 0x3FFF) << 16) | (ord("R") << 8) | (nr & 0xFF)


def vendor_cmds(path):
    """Every 'R'-typed ioctl constant the library builds."""
    dis = subprocess.run(["llvm-objdump", "-d", "--no-show-raw-insn", path],
                         capture_output=True, text=True, check=True).stdout
    consts, reg = {}, None
    for line in dis.splitlines():
        m = MOV.match(line)
        if m:
            reg = (m.group(1), int(m.group(2), 16) & 0xFFFFFFFF)
            continue
        k = MOVK.match(line)
        if k and reg and k.group(1) == reg[0]:
            consts.setdefault((int(k.group(2), 16) << 16 | (reg[1] & 0xFFFF)) & 0xFFFFFFFF, True)
            reg = None
    return {c for c in consts if (c >> 8) & 0xFF == ord("R")}


def struct_size(src, name):
    m = re.search(r"struct\s+" + name + r"\s*\{(.*?)\n\};", src, re.S)
    if not m:
        return None
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    total = 0
    for decl in body.split(";"):
        decl = decl.strip()
        if not decl:
            continue
        if "[" in decl:
            inner = decl.split("[")[1].split("]")[0]
            total += eval(inner) if inner.isdigit() else 0
        elif "u64" in decl or "__u64" in decl:
            total += 8
        else:
            total += 4
    return total


def driver_cmds(header):
    """Commands this tree's driver implements, keyed by encoded value."""
    src = open(header).read()
    out = {}
    for name, nr, arg in re.findall(
            r"#define\s+(FASTRPC_IOCTL_\w+)\s+_(?:IOWR|IO)\('R',\s*(\d+),\s*(struct\s+\w+|u?int\d+_t|)", src):
        size = struct_size(src, arg.split()[1]) if arg.startswith("struct") else 4
        out.setdefault(ioc(int(nr), size), []).append(name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("library")
    ap.add_argument("--header", default="include/uapi/misc/fastrpc.h")
    args = ap.parse_args()

    driver = driver_cmds(args.header)
    print("driver implements (this tree):")
    for cmd, names in sorted(driver.items(), key=lambda x: x[0] & 0xFF):
        print(f"  {cmd:#010x}  nr {cmd & 0xFF:>2}  size {(cmd >> 16) & 0x3FFF:>2}  {', '.join(names)}")

    print("\nvendor library issues:")
    collisions = 0
    for cmd in sorted(vendor_cmds(args.library), key=lambda c: c & 0xFF):
        nr, size = cmd & 0xFF, (cmd >> 16) & 0x3FFF
        name, expect = CAF.get(nr, ("?", 0))
        if cmd in driver:
            print(f"  {cmd:#010x}  nr {nr:>2}  size {size:>2}  CAF {name:<16} COLLIDES with {', '.join(driver[cmd])}")
            collisions += 1
        else:
            note = "" if size == expect else f"  (header says {expect} B)"
            print(f"  {cmd:#010x}  nr {nr:>2}  size {size:>2}  CAF {name:<16} -ENOTTY{note}")

    print(f"\n{collisions} of the vendor's commands are accepted by the wrong handler")
    return 0


if __name__ == "__main__":
    sys.exit(main())