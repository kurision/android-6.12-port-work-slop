#!/usr/bin/env python3
"""Bounded retry loop for one port-kernel RAM boot.

Intermittent fastboot RAM-boot failures are known on this device: fastboot
reports Sending/Booting OKAY and the device returns to stock without the
kernel ever running. This retries a bounded number of times and stops as soon
as the port kernel is confirmed up, so a single reader is active at a time.
"""
import argparse, subprocess, sys, time

PORT_PREFIX = "6.12"


def sh(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, timeout=timeout).stdout.decode(
        "utf-8", "replace").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--usb-log", required=True)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--up-wait", type=int, default=180)
    a = ap.parse_args()

    for attempt in range(1, a.attempts + 1):
        print(f"== attempt {attempt}/{a.attempts}", flush=True)
        sh(["adb", "-s", a.serial, "reboot", "bootloader"])
        time.sleep(16)
        if not sh(["fastboot", "devices"]).startswith(a.serial):
            print("   fastboot did not enumerate", flush=True)
            continue

        # One reader at a time; never overlap.
        subprocess.run(
            ["timeout", "600", "/tmp/diagvenv/bin/python", "-B",
             "porting/logging/fastboot-boot-capture.py",
             "--image", a.image, "--log", f"{a.usb_log}.{attempt}",
             "--status", f"{a.usb_log}.{attempt}.status",
             "--boot-timeout", "420"],
            capture_output=True, timeout=700)

        end = time.time() + a.up_wait
        while time.time() < end:
            uname = sh(["adb", "-s", a.serial, "shell", "uname -r"], timeout=40)
            if uname.startswith(PORT_PREFIX):
                print(f"   PORT KERNEL UP: {uname}", flush=True)
                sh(["adb", "-s", a.serial, "shell",
                    "getprop sys.boot_completed; pidof surfaceflinger system_server"])
                return 0
            time.sleep(6)
        print("   port kernel never came up", flush=True)
    return 1


sys.exit(main())