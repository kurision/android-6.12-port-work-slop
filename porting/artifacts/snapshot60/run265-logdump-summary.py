#!/usr/bin/env python3
"""Summarise a port logdump: message rate over time, per-subsystem counts.

The logdump text region is "<prio>,<seq>,<ts_us>,<flag>,caller=T<n>;<text>".
"""
import re
import sys
from collections import Counter, defaultdict

path = sys.argv[1]
LINE = re.compile(r"^(\d+),(\d+),(\d+),([^,]*),caller=T(\d+);(.*)$")

rows = []
with open(path, errors="replace") as fh:
    for line in fh:
        m = LINE.match(line)
        if m:
            rows.append((int(m.group(1)), int(m.group(2)), int(m.group(3)),
                         int(m.group(5)), m.group(6).rstrip("\n")))

print(f"parsed {len(rows)} messages")
if not rows:
    sys.exit(0)

ts = [r[2] for r in rows]
print(f"timestamp field: min={min(ts)} max={max(ts)} (us -> "
      f"{min(ts)/1e6:.1f}s .. {max(ts)/1e6:.1f}s)")
print(f"seq range: {min(r[1] for r in rows)} .. {max(r[1] for r in rows)}")

# Which lines are in the last second of the log?
last = max(ts)
print(f"\n=== messages in the final 2 s (t >= {last/1e6-2:.1f}s) ===")
tail = [r for r in rows if r[2] >= last - 2_000_000]
print(f"count = {len(tail)}")
c = Counter()
for r in tail:
    text = r[4]
    key = text.split(":")[0][:60]
    if "signal_generate" in text:
        key = "DIAG signal_generate"
    elif "process" in text:
        key = "DIAG process"
    c[key] += 1
for k, v in c.most_common(12):
    print(f"  {v:8d}  {k}")

print(f"\n=== message rate per 10 s (whole log) ===")
buckets = Counter()
for r in rows:
    buckets[r[2] // 10_000_000] += 1
for k in sorted(buckets):
    print(f"  t={k*10:6d}s  {buckets[k]:6d}")

print(f"\n=== subsystem counts (whole log) ===")
c2 = Counter()
for r in rows:
    text = r[4]
    if "signal_generate" in text:
        c2["DIAG signal_generate"] += 1
    elif "kgsl" in text:
        c2["kgsl"] += 1
    elif "ramoops" in text:
        c2["ramoops"] += 1
    elif "mdss" in text or "sde" in text:
        c2["mdss/sde"] += 1
    else:
        c2[text.split(":")[0][:50]] += 1
for k, v in c2.most_common(20):
    print(f"  {v:8d}  {k}")

# The last 40 non-spam messages
print(f"\n=== last 30 non-signal-generate messages ===")
keep = [r for r in rows if "signal_generate" not in r[4]]
for r in keep[-30:]:
    print(f"  t={r[2]/1e6:9.3f}s  {r[4][:150]}")
