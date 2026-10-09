#!/usr/bin/env python3
"""Decode the snapshot45 QSEE trace ring from a logdump partition image.

Layout: 128 slots x 512 bytes at 0x3f10000 (fs/pstore/ram.c); each slot holds
a 200-byte struct qsee_trace_rec (drivers/misc/qseecom.c).
"""

import struct
import sys

OFFSET = 0x3F10000
SLOTS = 128
SLOT_LEN = 512
MAGIC = 0x3143525445455351
REC = struct.Struct("<QQQ6I10Q3Q4Q16s")
EVENTS = {1: "SMC_SEND", 2: "SMC_RET", 3: "LISTENER_WAKE", 4: "LISTENER_RESP"}

assert REC.size == 200


def parse(slot):
    v = REC.unpack_from(slot)
    magic, seq, kt, boot, event, pid, smc, arginfo, ret = v[:9]
    if magic != MAGIC:
        return None
    return {
        "seq": seq, "ktime": kt, "boot_id": boot, "event": event, "pid": pid,
        "smc": smc, "arginfo": arginfo, "ret": struct.unpack("<i", struct.pack("<I", ret))[0],
        "args": v[9:19], "rets": v[19:22], "extra": v[22:26],
        "comm": v[26].split(b"\0", 1)[0].decode(errors="replace"),
    }


def hexes(values):
    return ",".join(f"{x:#x}" for x in values)


def line(r):
    name = EVENTS.get(r["event"], f"UNKNOWN({r['event']})")
    return (f"seq={r['seq']} t={r['ktime'] / 1e9:.6f} {name} pid={r['pid']} "
            f"comm={r['comm']} smc={r['smc']:#010x} argc={r['arginfo'] & 0xf} "
            f"args={hexes(r['args'][:7])} ret={r['ret']} rets={hexes(r['rets'])} "
            f"extra={hexes(r['extra'])}")


def classify(r):
    event = r["event"]
    if event == 1:
        return f"LAST=SMC_SEND without SMC_RET -> died inside SMC {r['smc']:#010x}"
    if event == 3:
        return f"LAST=LISTENER_WAKE -> died waiting for listener {r['extra'][0]}"
    if event == 4:
        return "LAST=LISTENER_RESP -> died after listener response"
    if event == 2:
        return "LAST=SMC_RET -> died outside SMC"
    return f"LAST=UNKNOWN({event})"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: decode-qsee-trace.py LOGDUMP_BIN")
    with open(sys.argv[1], "rb") as f:
        f.seek(OFFSET)
        ring = f.read(SLOTS * SLOT_LEN)
    if len(ring) != SLOTS * SLOT_LEN:
        sys.exit(f"decode-qsee-trace: {sys.argv[1]} is shorter than {OFFSET + SLOTS * SLOT_LEN:#x}")

    records = [r for r in (parse(ring[i * SLOT_LEN:(i + 1) * SLOT_LEN])
                           for i in range(SLOTS)) if r]
    if not records:
        print("no QSEE trace records")
        return

    groups = {}
    for r in records:
        groups.setdefault(r["boot_id"], []).append(r)
    for boot, recs in groups.items():
        recs.sort(key=lambda r: r["seq"])
        seqs = {r["seq"] for r in recs}
        lo, hi = recs[0]["seq"], recs[-1]["seq"]
        missing = [s for s in range(lo, hi + 1) if s not in seqs]
        print(f"boot_id={boot:#010x} records={len(recs)} seq={lo}..{hi} "
              f"missing={missing if missing else 'none'}")
        for r in recs:
            print(line(r))

    last = max(records, key=lambda r: r["seq"])
    print(f"last: {line(last)}")
    print(classify(last))


if __name__ == "__main__":
    main()
