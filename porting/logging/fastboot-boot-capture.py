#!/usr/bin/env python3
"""fastboot-boot while streaming the diag gadget, without needing adb.

usb-boot-capture.py always starts with `adb reboot bootloader`. That fails when
the phone is already sitting in fastboot (adb is not up), which is exactly the
state a splash-stalled phone is left in. This variant skips that step: the
USB reader starts first, then `fastboot boot` runs on the already-present
fastboot device.

Read-only w.r.t. the phone: RAM boot only, nothing flashed.
"""
import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

import importlib.util

# usb-boot-capture.py has a dash in its name, so it is not importable by name.
_ubc_path = Path(__file__).resolve().parent / "usb-boot-capture.py"
_spec = importlib.util.spec_from_file_location("usb_boot_capture", _ubc_path)
ubc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ubc)


def wait_for_fastboot(serial_id: str, timeout: int = 60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = subprocess.run(["fastboot", "devices"], capture_output=True,
                             text=True).stdout
        if any(line.split()[0] == serial_id for line in out.splitlines()
               if line.split()):
            return
        time.sleep(0.5)
    sys.exit(f"fastboot device {serial_id} never appeared")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--log", required=True, type=Path)
    ap.add_argument("--status", required=True, type=Path)
    ap.add_argument("--adb-serial", default="2819f2320604")
    ap.add_argument("--boot-timeout", type=int, default=900,
                    help="give up waiting for the reader after N seconds")
    args = ap.parse_args()

    if not args.image.is_file():
        sys.exit(f"Missing image: {args.image}")
    for p in (args.log, args.status):
        if p.exists():
            sys.exit(f"Refusing to overwrite {p}")
    args.log.parent.mkdir(parents=True, exist_ok=True)

    done, result = threading.Event(), {}
    thread = threading.Thread(target=ubc.reader, args=(args.log, done, result),
                              daemon=True)
    thread.start()

    wait_for_fastboot(args.adb_serial)
    print(f"+ fastboot -s {args.adb_serial} boot {args.image}", flush=True)
    subprocess.run(["fastboot", "-s", args.adb_serial, "boot", str(args.image)],
                   check=True)

    if not done.wait(timeout=args.boot_timeout):
        sys.exit("reader did not finish within --boot-timeout; stopping early")
    thread.join()
    args.status.write_text(f"reason={result['reason']}\nbytes={result['count']}\n"
                           f"host_elapsed={result['elapsed']:.1f}\n")
    print(f"capture ended: {result['reason']}; bytes={result['count']}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())