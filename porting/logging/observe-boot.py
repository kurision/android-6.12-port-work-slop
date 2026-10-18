#!/usr/bin/env python3
"""Bounded, read-only boot observer for one RAM-boot run.

Polls identity and boot state on a fixed cadence, streams logcat to a file,
and stops itself after --seconds. It never reboots, never clears anything and
never writes to the device.
"""
import argparse, json, os, subprocess, time

PROBE = ("uname -r; cat /proc/sys/kernel/random/boot_id; "
         "cut -d' ' -f1 /proc/uptime; getprop sys.boot_completed; "
         "getprop dev.bootcomplete; getprop init.svc.bootanim; "
         "pidof surfaceflinger; pidof system_server; "
         "ls -l /dev/ashmem 2>&1")


def adb(serial, *args, binary=False):
    cmd = ["adb", "-s", serial] + list(args)
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if binary:
        return r.stdout
    return (r.stdout + r.stderr).decode("utf-8", "replace").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--seconds", type=int, default=480)
    ap.add_argument("--interval", type=int, default=4)
    ap.add_argument("--out", required=True, help="jsonl sample file")
    ap.add_argument("--logcat", help="logcat stream file")
    ap.add_argument("--logcat-final")
    a = ap.parse_args()

    # logcat streams forever, so it gets its own long-lived process rather than
    # a per-iteration call that would block until the adb timeout fires.
    lc = None
    lcproc = None
    if a.logcat:
        lc = open(a.logcat, "wb")
        lcproc = subprocess.Popen(
            ["adb", "-s", a.serial, "logcat", "-v", "threadtime", "-b", "all"],
            stdout=lc, stderr=subprocess.DEVNULL)
    end = time.time() + a.seconds
    while time.time() < end:
        rec = {"t": round(time.time(), 3)}
        state = adb(a.serial, "get-state")
        rec["state"] = state
        if state == "device":
            rec["probe"] = adb(a.serial, "shell", PROBE).splitlines()
        with open(a.out, "a") as f:
            f.write(json.dumps(rec) + "\n")
        time.sleep(a.interval)

    if lcproc:
        lcproc.terminate()
        lcproc.wait(timeout=30)
        lc.close()
    if a.logcat_final:
        with open(a.logcat_final, "wb") as f:
            f.write(adb(a.serial, "logcat", "-b", "all", "-d", binary=True))


main()