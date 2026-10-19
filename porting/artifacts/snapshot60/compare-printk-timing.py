#!/usr/bin/env python3
"""Compare the printk timing of two port logdumps.

If the kernel log is written to a 115200-baud UART, every line costs
~17 ms of busy-wait, so the messages arrive in bursts separated by gaps.
This prints the inter-message interval distribution and the implied
console busy time.
"""
import re
import sys
from collections import Counter

LINE = re.compile(r"^(\d+),(\d+),(\d+),([^,]*),caller=T(\d+);(.*)$")
BAUD = 115200
BYTES_PER_LINE = 200  # measured average of the port's DIAG lines


def load(path):
    rows = []
    with open(path, errors="replace") as fh:
        for line in fh:
            m = LINE.match(line)
            if m:
                rows.append((int(m.group(3)), m.group(6).rstrip("\n")))
    return rows


def report(path):
    rows = load(path)
    ts = [r[0] for r in rows]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
    span = (ts[-1] - ts[0]) / 1e6 if len(ts) > 1 else 0
    print(f"=== {path}")
    print(f"  messages={len(rows)}  span={span:.1f}s  "
          f"rate={len(rows)/span if span else 0:.1f}/s")
    if not gaps:
        print("  no gaps")
        return
    gaps.sort()
    n = len(gaps)

    def pct(p):
        return gaps[min(n - 1, int(n * p))] / 1000.0  # ms

    print(f"  gap us: min={gaps[0]} p50={pct(0.5):.1f}ms p90={pct(0.9):.1f}ms "
          f"p99={pct(0.99):.1f}ms max={gaps[-1]/1000.0:.1f}ms")
    # The implied UART cost: each line is about BYTES_PER_LINE bytes.
    uart_ms = len(rows) * BYTES_PER_LINE * 1000.0 / (BAUD / 10.0)
    print(f"  implied UART time for these lines: {uart_ms/1000:.1f}s "
          f"of {span:.1f}s = {100*uart_ms/1000/span if span else 0:.0f}% of the boot")
    # How much of the console was the port's own DIAG output?
    diag = sum(1 for r in rows if "DIAG" in r[1])
    print(f"  DIAG lines: {diag} ({100*diag/len(rows):.0f}% of the console)")
    # The biggest gaps: where the console was silent.
    big = sorted(((g, ts[i + 1]) for i, g in
                   enumerate(gaps)), reverse=True)[:5]
    for g, t in big:
        print(f"    gap {g/1000.0:8.1f} ms before t={t/1e6:.3f}s")


for p in sys.argv[1:]:
    report(p)
    print()
