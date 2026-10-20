#!/usr/bin/env python3
"""Pull the phone's evidence channels into one readable folder.

Read-only on the device: no reboot, no flash, no partition erase. Everything
lands in a timestamped directory with a manifest, so a failed boot can be
compared with a good one later.

    porting/logging/collect-logs.py [--out DIR] [--serial SERIAL]

The folder contains:
    device.txt             uname, cmdline, boot reason, uptime, boot_id
    dmesg.log              live kernel ring buffer
    pstore/                /sys/fs/pstore (previous-boot crash records)
    logdump.bin            raw logdump partition (64 MiB)
    logdump-text.txt       decoded kernel-log text region of logdump.bin
    logdump-reset.txt      ACKRESET record decoded from logdump.bin
    MANIFEST.json          sizes, sha256 sums and capture time
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

SERIAL_DEFAULT = "2819f2320604"
LOGDUMP_PARTITION = "/dev/block/by-name/logdump"
LOGDUMP_SIZE = 67108864
LOGDUMP_TEXT_END = 0x3C00000


def adb(serial, args, timeout=120, binary=False):
    cmd = ["adb", "-s", serial] + args
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode and not binary:
        sys.exit(f"adb {' '.join(args)} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout


def text(serial, command):
    return adb(serial, ["shell", "-T", command], timeout=60).decode(errors="replace")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None,
                    help="target directory (default: artifacts/logs/<UTC timestamp>)")
    ap.add_argument("--serial", default=SERIAL_DEFAULT)
    args = ap.parse_args()

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = pathlib.Path(args.out or f"../ack-kgsl-artifacts/logs/{stamp}").resolve()
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "serial": args.serial,
        "device": text(args.serial, "getprop ro.product.device"),
        "files": {},
    }

    def record(name, data):
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest["files"][name] = {"bytes": len(data), "sha256": sha256(data)}

    device = "\n".join([
        "uname: " + text(args.serial, "uname -a").strip(),
        "cmdline: " + text(args.serial, "cat /proc/cmdline").strip(),
        "uptime: " + text(args.serial, "cat /proc/uptime").strip(),
        "boot_id: " + text(args.serial, "cat /proc/sys/kernel/random/boot_id").strip(),
        "boot_completed: " + text(args.serial, "getprop sys.boot_completed").strip(),
        "boot_reason: " + text(args.serial, "getprop sys.boot.reason").strip(),
        "boot_reason_history: " + text(args.serial, "getprop persist.sys.boot.reason.history").strip(),
    ]) + "\n"
    record("device.txt", device.encode())

    record("dmesg.log", adb(args.serial, ["shell", "-T", "dmesg"], timeout=90, binary=True))

    listing = text(args.serial, "ls /sys/fs/pstore").split()
    for name in listing:
        data = adb(args.serial, ["shell", "-T", f"cat /sys/fs/pstore/{name}"], timeout=60, binary=True)
        record(f"pstore/{name}", data)
    manifest["files"]["pstore/"] = {"entries": listing, "note": "empty means the previous boot left no pstore record"}

    blob = adb(args.serial, ["shell", "-T", f"cat {LOGDUMP_PARTITION}"], timeout=180, binary=True)
    if len(blob) != LOGDUMP_SIZE:
        sys.exit(f"short logdump read: {len(blob)} bytes (expected {LOGDUMP_SIZE})")
    record("logdump.bin", blob)

    record("logdump-text.txt", blob[:LOGDUMP_TEXT_END].split(b"\0", 1)[0])

    try:
        import importlib.util
        here = pathlib.Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location("decode_reset", here / "decode-reset.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        record("logdump-reset.txt", module.decode(blob) or b"")
    except Exception as exc:  # the reset record is optional, the bundle is not
        record("logdump-reset.txt", f"not decoded: {exc}\n".encode())

    with (out / "MANIFEST.json").open("w") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    print(f"logs in {out}")
    for name, info in manifest["files"].items():
        if "bytes" in info:
            print(f"  {name}: {info['bytes']} bytes sha256={info['sha256'][:16]}")
        else:
            print(f"  {name}: {info}")


if __name__ == "__main__":
    main()
