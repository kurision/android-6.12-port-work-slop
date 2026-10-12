#!/usr/bin/env python3
"""Poll adb on a fixed cadence through a diag boot, one line per poll.

Runs alongside usb-boot-capture.py: the device resets out from under adb when
the kernel boots, so a slow poll cadence misses the 6.12 window entirely and
reports the stock 4.19 kernel instead. 4 s is the shortest cadence that does
not starve the USB reader thread.
"""
import subprocess
import sys
import time

SERIAL = "2819f2320604"
POLL_SECONDS = 4
DURATION_SECONDS = 150


def adb(*args):
    try:
        out = subprocess.run(["adb", "-s", SERIAL, *args],
                             capture_output=True, text=True, timeout=8)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"ERR {exc}"
    return (out.stdout or out.stderr).strip().replace("\n", " | ") or "-"


start = time.time()
while time.time() - start < DURATION_SECONDS:
    elapsed = time.time() - start
    kernel = adb("shell", "uname", "-r")
    booted = adb("shell", "getprop", "sys.boot_completed")
    print(f"t={elapsed:6.1f} uname={kernel} boot_completed={booted}", flush=True)
    time.sleep(POLL_SECONDS)