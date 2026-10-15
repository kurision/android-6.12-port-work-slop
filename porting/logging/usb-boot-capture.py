#!/usr/bin/env python3
"""Temporary-boot one image while capturing its diagnostic USB kmsg stream.

One script for every snapshot: no per-snapshot reader copies.

Usage:
    usb-boot-capture.py --image <boot.img> --log <usb.log>
                        [--adb-serial S] [--status <file>]

What it does, in order:
  1. Fails early if the image is missing or the log file already exists
     (exclusive create, so a run can never silently append to an old log).
  2. Starts the USB reader thread first (waits for 18d1:9008/tissot-diag).
  3. Reboots only the selected device to bootloader and runs
     `fastboot boot <image>` (RAM only; nothing is flashed).
  4. Streams serial bytes to --log with fsync per chunk until the device
     EOF marker, then writes a small --status file.

`-usb-capture.status`, matching the snapshot28/29 convention.

Prerequisite: `python3 -m pip install --break-system-packages pyserial`
(fails fast at startup if missing, before touching the phone).
"""
import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial
from serial.tools import list_ports

VID, PID, SERIAL, BAUD = 0x18D1, 0x9008, "tissot-diag", 115200
EOF_MARKER = b"DIAG: EOF Android USB kmsg dump complete"


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True, type=Path,
                    help="Boot image to `fastboot boot` (RAM only, no flash)")
    ap.add_argument("--log", required=True, type=Path,
                    help="USB capture output (must not exist; created exclusively)")
    ap.add_argument("--adb-serial", default="2819f2320604",
                    help="ADB serial of the target phone")
    ap.add_argument("--status", type=Path, default=None,
                    help="Status file (default: <log> with -usb.log -> -usb-capture.status)")
    return ap.parse_args()


def default_status(log: Path) -> Path:
    name = log.name
    if name.endswith("-usb.log"):
        return log.with_name(name[:-len("-usb.log")] + "-usb-capture.status")
    return log.with_suffix(log.suffix + ".status")


OPEN_TIMEOUT_SECONDS = 30.0


def open_with_retry(port: str):
    """Open the CDC-ACM port, waiting out udev ownership.

    The device node appears in list_ports() before udev has applied the
    OWNER/MODE rule, so an immediate open can raise PermissionError and cost
    the whole kernel log. Retry until OPEN_TIMEOUT_SECONDS, then give up so a
    genuinely missing port is still reported.
    """
    deadline = time.monotonic() + OPEN_TIMEOUT_SECONDS
    while True:
        try:
            return serial.Serial(port, BAUD, timeout=1)
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            print("waiting for udev ownership of " + port, flush=True)
            time.sleep(0.25)


def reader(log: Path, done: threading.Event, result: dict):
    started = time.monotonic()

    count, reason, recent = 0, "waiting", b""
    try:
        with log.open("xb", buffering=0) as out:
            print("waiting for 18d1:9008 serial tissot-diag", flush=True)
            while True:
                hits = [p for p in list_ports.comports()
                        if p.vid == VID and p.pid == PID and p.serial_number == SERIAL]
                if hits:
                    port = hits[0].device
                    break
                time.sleep(0.25)
            print(f"opening {port}", flush=True)
            # udev creates the node before it applies
            # /etc/udev/rules.d/99-ack-kernel-log.rules, so a first open can
            # hit EACCES. Wait for the rule instead of losing the whole log.
            stream = open_with_retry(port)
            with stream:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        continue
                    out.write(chunk)
                    count += len(chunk)
                    recent = (recent + chunk)[-256:]
                    if EOF_MARKER in recent:
                        reason = "device-complete-marker"
                        break
    except Exception as exc:  # Serial disconnect / OS error: record, don't traceback
        reason = f"reader-error: {exc}"
    finally:
        result.update(reason=reason, count=count, elapsed=time.monotonic() - started)
        done.set()


def run(cmd: list[str]):
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def wait_for_fastboot(serial_id: str, timeout: int = 120):
    for _ in range(timeout * 2):
        out = subprocess.run(["fastboot", "devices"], capture_output=True, text=True).stdout
        if any(line.split()[0] == serial_id for line in out.splitlines() if line.split()):
            return
        time.sleep(0.5)
    sys.exit(f"fastboot device {serial_id} never appeared")


def main() -> int:
    args = parse_args()
    if not args.image.is_file():
        sys.exit(f"Missing image: {args.image}")
    if args.log.exists():
        sys.exit(f"Refusing to overwrite log: {args.log}")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    status = args.status or default_status(args.log)
    if status.exists():
        sys.exit(f"Refusing to overwrite status: {status}")

    done, result = threading.Event(), {}
    thread = threading.Thread(target=reader, args=(args.log, done, result), daemon=True)
    thread.start()

    run(["adb", "-s", args.adb_serial, "reboot", "bootloader"])
    wait_for_fastboot(args.adb_serial)
    run(["fastboot", "-s", args.adb_serial, "boot", str(args.image)])

    # No host deadline: the device EOF marker (or a disconnect) ends the run.
    done.wait()
    thread.join()
    status.write_text(f"reason={result['reason']}\nbytes={result['count']}\n"
                       f"host_elapsed={result['elapsed']:.1f}\n")
    print(f"capture ended: {result['reason']}; bytes={result['count']}", flush=True)
    return 0


if __name__ == "__main__":
    main()
