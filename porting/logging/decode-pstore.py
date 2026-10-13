#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Decode device pstore records or recover the tree's raw logdump snapshots.

    python3 decode-pstore.py pstore/dmesg-ramoops-0
    python3 decode-pstore.py --logdump run106-logdump.bin --output-prefix run106

The logdump mode writes byte-faithful, circular-buffer-ordered console and
validated dmesg payloads, separately named periodic printk tails, and a JSON
provenance/validation report. Console and printk tails are live periodic samples,
not crash/reset records. Retained dmesg zones can predate the sampled boot.
Version1 verifies header/payload CRCs; legacy version0 integrity is unverified.
Neither format has a boot ID, and CRCs do not make the live RAM copy atomic.
With no arguments, the device-record mode walks ./pstore or /sys/fs/pstore.
"""

import argparse
import json
import re
import struct
import sys
import zlib
import pathlib


def decode(path: pathlib.Path) -> str | None:
    raw = path.read_bytes()
    if not raw:
        return None
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, zlib.MAX_WBITS | 16):
        try:
            return zlib.decompress(raw, wbits).decode("utf-8", "replace")
        except zlib.error:
            continue
    # not compressed: strip NUL padding the way the kernel writes it
    return raw.decode("utf-8", "replace").rstrip("\x00")


# fs/pstore/ram.c: ramoops_snap_header and ramoops_raw_geometry_valid().
PARTITION_SIZE = 64 * 1024 * 1024
SNAPSHOT_OFFSET = 60 * 1024 * 1024
PAGE_SIZE = 4096
PAYLOAD_SIZE = 1024 * 1024
SLOT_STRIDE = PAGE_SIZE + PAYLOAD_SIZE
SLOT_COUNT = 2
SNAPSHOT_MAGIC = 0x52414D4F
RAMOOPS_PHYS = 0x86800000
SNAPSHOT_HEADER = struct.Struct("<QQQQ8I")
TAIL_OFFSET = 0x3E02000
TAIL_SLOT_STRIDE = 0x20000
TAIL_PAYLOAD_SIZE = TAIL_SLOT_STRIDE - PAGE_SIZE
TAIL_SLOT_COUNT = 2
TAIL_MAGIC = 0x314C4941544B4341  # b"ACKTAIL1", little-endian
RAM_HEADER = struct.Struct("<III")
RAM_SIGNATURE = 0x43474244
DMESG_ZONE_SIZE = 4096
DMESG_ZONE_COUNT = 119
CONSOLE_OFFSET = 0x77000
CONSOLE_SIZE = 512 * 1024
# Current writer and the older uncompressed ramoops header understood by ram.c.
KMSG_HEADER = re.compile(rb"\A====(-?[0-9]{1,19})\.([0-9]{1,6})(?:-([CD]))?\n")
DUMP_HEADER = re.compile(
    rb"\A(Panic|Oops|Emergency|Shutdown|Unknown)#([1-9][0-9]*) Part1\n")


def recover_zone(zone: bytes) -> tuple[bytes, dict]:
    """Match persistent_ram_save_old() ordering, rejecting impossible headers."""
    if len(zone) < RAM_HEADER.size:
        raise ValueError("truncated persistent-RAM header")
    signature, start, size = RAM_HEADER.unpack_from(zone)
    capacity = len(zone) - RAM_HEADER.size
    if signature != RAM_SIGNATURE:
        raise ValueError(f"bad persistent-RAM signature 0x{signature:08x}")
    if size > capacity or start > size:
        raise ValueError(f"invalid ring bounds start={start} size={size} capacity={capacity}")
    # Before wrapping, the write cursor equals the byte count. A mismatch can
    # result from the non-atomic size/cursor updates in persistent_ram_write().
    if size < capacity and start != size:
        raise ValueError(f"inconsistent partial ring start={start} size={size}")
    data = zone[RAM_HEADER.size:]
    return data[start:size] + data[:start], {
        "start": start, "size": size, "capacity": capacity,
    }


def recover_dmesg(data: bytes) -> tuple[bytes, dict]:
    """Require both the ramoops timestamp header and the real kmsg dump header."""
    match = KMSG_HEADER.match(data)
    if match is None:
        raise ValueError("missing or malformed ramoops dmesg header")
    seconds, microseconds = int(match[1]), int(match[2])
    if not -(1 << 63) <= seconds < (1 << 63) or microseconds >= 1000000:
        raise ValueError("invalid ramoops dmesg timestamp")
    compressed = match[3] == b"C"
    payload = data[match.end():]
    if compressed:
        # platform.c writes raw DEFLATE and reads into 3 * psinfo->bufsize.
        # No fallback to arbitrary text if the declared compressed stream fails.
        limit = 3 * (DMESG_ZONE_SIZE - RAM_HEADER.size)
        inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        try:
            payload = inflater.decompress(payload, limit + 1)
        except zlib.error as error:
            raise ValueError("corrupt raw DEFLATE dmesg payload") from error
        if len(payload) > limit or inflater.unconsumed_tail:
            raise ValueError("dmesg decompression exceeds kernel buffer limit")
        if not inflater.eof or inflater.unused_data:
            raise ValueError("truncated raw DEFLATE dmesg payload or trailing bytes")
    dump = DUMP_HEADER.match(payload)
    if dump is None or dump.end() == len(payload):
        raise ValueError("missing kmsg dump reason/header or log payload")
    return payload, {
        "dump_timestamp_sec": seconds,
        "dump_timestamp_us": microseconds,
        "compression": "raw-deflate" if compressed else "none",
        "dump_reason": dump[1].decode("ascii"),
        "dump_count": int(dump[2]),
        "part": 1,
        "boot_scope": "undetermined: current or retained prior-boot dump",
    }


def validate_logdump_layout() -> None:
    """Keep all fixed slots outside the other logdump consumers' extents."""
    ranges = [("diagnostic prefix", 0, SNAPSHOT_OFFSET),
              ("witness", 0x3F00000, 0x3F10000),
              ("QSEE ring", 0x3F10000, 0x3F20000),
              ("ACKRESET1", 0x3F30000, 0x3F40000)]
    for label, offset, stride, count in (
            ("ramoops", SNAPSHOT_OFFSET, SLOT_STRIDE, SLOT_COUNT),
            ("periodic printk tail", TAIL_OFFSET, TAIL_SLOT_STRIDE, TAIL_SLOT_COUNT)):
        ranges.extend((f"{label} slot{index}", offset + index * stride,
                       offset + (index + 1) * stride) for index in range(count))
    for label, start, end in ranges:
        if not 0 <= start < end <= PARTITION_SIZE:
            raise ValueError(f"invalid logdump range for {label}: {start}..{end}")
    ranges.sort(key=lambda item: item[1])
    for previous, current in zip(ranges, ranges[1:]):
        if previous[2] > current[1]:
            raise ValueError(f"overlapping logdump ranges: {previous[0]} and {current[0]}")


def validate_slot(blob: bytes, index: int, base: int, *, kind: str, magic: int,
                  stride: int, length: int | None, phys: int,
                  legacy: bool = False) -> tuple[dict, bytes | None]:
    """Reject a slot before exporting anything unless its contract validates."""
    header = blob[base:base + PAGE_SIZE]
    actual_magic, seq, sample, timestamp, offset, payload_len, address, slot, *reserved = (
        SNAPSHOT_HEADER.unpack_from(header))
    version, payload_crc, header_crc, reserved_tail = reserved
    result = {
        "kind": kind, "slot": index, "logdump_offset": base, "magic": actual_magic,
        "seq": seq, "sample_index": sample, "timestamp_ns": timestamp,
        "payload_offset": offset, "payload_len": payload_len,
        "phys_addr_lo": address, "declared_slot": slot, "version": version,
        "structure_valid": False, "header_valid": False, "status": "invalid",
        "validation": "rejected", "integrity": "unverified: rejected slot",
        "header_crc_valid": None, "payload_crc_valid": None,
    }
    if not any(header):
        result.update(status="absent", error="empty or invalidated header page")
        return result, None
    count = SLOT_COUNT if legacy else TAIL_SLOT_COUNT
    checks = (
        (actual_magic == magic, "bad slot magic (invalidated or torn header possible)"),
        (seq > 0 and sample == seq, "invalid sequence/sample index"),
        (timestamp > 0, "invalid sample timestamp"),
        (offset == PAGE_SIZE and payload_len <= stride - PAGE_SIZE
         and (length is None or payload_len == length), "unsupported payload geometry"),
        (address == phys, "unexpected payload physical address"),
        (slot == index and slot == (seq - 1) % count, "invalid slot/sequence identity"),
        (version == 1 or (legacy and version == 0), f"unsupported header version {version}"),
        (reserved_tail == 0 and not any(header[SNAPSHOT_HEADER.size:])
         and (version != 0 or not any(reserved)), "nonzero reserved header bytes"),
    )
    errors = [message for valid, message in checks if not valid]
    if errors:
        result["error"] = "; ".join(errors)
        return result, None
    result["structure_valid"] = True
    payload = bytes(blob[base + offset:base + offset + payload_len])
    if version == 1:
        crc_header = bytearray(header[:SNAPSHOT_HEADER.size])
        crc_header[56:60] = b"\0" * 4
        calculated_header_crc = zlib.crc32(crc_header)
        calculated_payload_crc = zlib.crc32(payload)
        result.update(header_crc32=header_crc, payload_crc32=payload_crc,
                      calculated_header_crc32=calculated_header_crc,
                      calculated_payload_crc32=calculated_payload_crc,
                      header_crc_valid=header_crc == calculated_header_crc,
                      payload_crc_valid=payload_crc == calculated_payload_crc)
        errors = []
        if not result["header_crc_valid"]:
            errors.append("header CRC32 mismatch")
        if not result["payload_crc_valid"]:
            errors.append("payload CRC32 mismatch")
        if errors:
            result.update(error="; ".join(errors), validation="crc32-rejected",
                          integrity="rejected: CRC32 validation failed")
            return result, None
        result.update(status="crc-validated", validation="header-and-payload-crc32-verified",
                      integrity="verified: header and payload CRC32")
    else:
        result.update(status="structurally-valid", validation="legacy-structural-only",
                      integrity="unverified: legacy version0 has no CRC or commit marker")
    result.update(header_valid=True, freshness="unverified")
    return result, payload


def slot_provenance(slot: dict, source: str) -> dict:
    return {"source": source, **{key: slot[key] for key in (
        "slot", "seq", "sample_index", "timestamp_ns", "logdump_offset",
        "version", "validation", "integrity", "freshness")}}


def slot_pair_summary(slots: list[dict]) -> str:
    valid = sorted((slot for slot in slots if slot["header_valid"]),
                   key=lambda slot: slot["seq"])
    if len(valid) < 2:
        return "insufficient valid slots to compare"
    older, newer = valid
    compatible = (newer["seq"] == older["seq"] + 1
                  and newer["timestamp_ns"] > older["timestamp_ns"])
    return ("compatible with consecutive samples; same boot not proven"
            if compatible else "stale or mixed-boot slots possible; no latest boot selected")


def recover_logdump(blob: bytes, source: str, output_prefix: str) -> tuple[dict, dict[str, bytes]]:
    """Recover each slot independently; never guess which boot is newest."""
    if len(blob) != PARTITION_SIZE:
        raise ValueError(f"expected {PARTITION_SIZE} logdump bytes, got {len(blob)}")
    validate_logdump_layout()
    report = {
        "source": source,
        "output_prefix": output_prefix,
        "notes": [
            "Sample timestamps are monotonic uptime ns, not wall-clock time.",
            "Console is live RAM at the snapshot, not a prior-boot pstore crash record.",
            "Periodic printk tails are process-context samples, not panic or ACKRESET1 records.",
            "Dmesg zones may retain prior-boot dumps; their boot is not identified.",
            "Version1 requires structural validation and header/payload CRC32 before export.",
            "Legacy version0 lacks CRCs/commit markers and remains integrity-unverified.",
            "CRCs verify stored bytes, not freshness, boot identity or atomic live RAM sampling.",
            "Records in different slots may duplicate one dump; counts are not crash events.",
        ],
        "slots": [],
        "periodic_tail_slots": [],
    }
    files = {}
    crash_records = 0
    for index in range(SLOT_COUNT):
        base = SNAPSHOT_OFFSET + index * SLOT_STRIDE
        result, payload = validate_slot(
            blob, index, base, kind="ramoops-snapshot", magic=SNAPSHOT_MAGIC,
            stride=SLOT_STRIDE, length=PAYLOAD_SIZE, phys=RAMOOPS_PHYS, legacy=True)
        report["slots"].append(result)
        if payload is None:
            continue
        seq, timestamp = result["seq"], result["timestamp_ns"]
        provenance = slot_provenance(result, source)
        stem = f"-ramoops-slot{index}-seq{seq}-ns{timestamp}"
        console = {"kind": "snapshot-console", "boot_scope": "live console of the sampled boot",
                   "provenance": provenance}
        result["console"] = console
        try:
            data, ring = recover_zone(payload[CONSOLE_OFFSET:CONSOLE_OFFSET + CONSOLE_SIZE])
            console.update(ring)
            console.update(status="recovered" if data else "empty", bytes=len(data))
            if data:
                suffix = stem + "-snapshot-console.log"
                files[suffix] = data
                console["file"] = output_prefix + suffix
        except ValueError as error:
            console.update(status="invalid", error=str(error))
        result["dmesg"] = []
        result["dmesg_empty_zones"] = 0
        result["dmesg_rejected_zones"] = []
        for zone_index in range(DMESG_ZONE_COUNT):
            zone_offset = zone_index * DMESG_ZONE_SIZE
            try:
                data, ring = recover_zone(payload[zone_offset:zone_offset + DMESG_ZONE_SIZE])
                if not data:
                    result["dmesg_empty_zones"] += 1
                    continue
                data, record = recover_dmesg(data)
                suffix = (f"{stem}-dmesg{zone_index}-sec{record['dump_timestamp_sec']}"
                          f"-us{record['dump_timestamp_us']}.log")
                files[suffix] = data
                record.update(kind="ramoops-dmesg", zone=zone_index, payload_offset=zone_offset,
                              file=output_prefix + suffix, bytes=len(data), ring=ring,
                              provenance=provenance)
                result["dmesg"].append(record)
                crash_records += record["dump_reason"] in ("Panic", "Oops")
            except ValueError as error:
                result["dmesg_rejected_zones"].append({"zone": zone_index, "error": str(error)})
    for index in range(TAIL_SLOT_COUNT):
        base = TAIL_OFFSET + index * TAIL_SLOT_STRIDE
        result, data = validate_slot(
            blob, index, base, kind="periodic-printk-tail", magic=TAIL_MAGIC,
            stride=TAIL_SLOT_STRIDE, length=None, phys=0)
        report["periodic_tail_slots"].append(result)
        if data is None:
            continue
        tail = {"kind": "periodic-printk-tail", "status": "recovered" if data else "empty",
                "boot_scope": "periodic live printk sample; no crash/reset event established",
                "bytes": len(data), "provenance": slot_provenance(result, source)}
        result["tail"] = tail
        if data:
            suffix = (f"-printk-tail-slot{index}-seq{result['seq']}"
                      f"-ns{result['timestamp_ns']}-periodic-printk.log")
            files[suffix] = data
            tail["file"] = output_prefix + suffix
    report["slot_pair"] = slot_pair_summary(report["slots"])
    report["periodic_tail_slot_pair"] = slot_pair_summary(report["periodic_tail_slots"])
    report["periodic_tail_sample_count"] = sum(
        bool(slot.get("tail", {}).get("file")) for slot in report["periodic_tail_slots"])
    report["dmesg_record_count"] = sum(len(slot.get("dmesg", [])) for slot in report["slots"])
    report["panic_or_oops_record_count"] = crash_records
    files["-ramoops.json"] = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    return report, files


def recovery_summary(report: dict) -> list[str]:
    lines = []
    for slot in report["slots"]:
        console = slot.get("console", {})
        lines.append(f"slot{slot['slot']}: magic=0x{slot['magic']:08x} seq={slot['seq']} "
                     f"timestamp_ns={slot['timestamp_ns']} header_valid={slot['header_valid']} "
                     f"version={slot['version']} validation={slot['validation']} "
                     f"integrity={slot['integrity']} "
                     f"console={console.get('status', 'unavailable')} "
                     f"dmesg={len(slot.get('dmesg', []))}"
                     + (f" error={slot['error']}" if "error" in slot else ""))
    lines.append(f"slot pair: {report['slot_pair']}; freshness remains unverified")
    for slot in report["periodic_tail_slots"]:
        lines.append(f"periodic-tail-slot{slot['slot']}: seq={slot['seq']} "
                     f"timestamp_ns={slot['timestamp_ns']} header_valid={slot['header_valid']} "
                     f"version={slot['version']} validation={slot['validation']} "
                     f"integrity={slot['integrity']} "
                     f"tail={slot.get('tail', {}).get('status', 'unavailable')}"
                     + (f" error={slot['error']}" if "error" in slot else ""))
    lines.append(f"periodic tail slot pair: {report['periodic_tail_slot_pair']}; "
                 "periodic samples are not crash/reset records")
    if not report["dmesg_record_count"]:
        lines.append("No valid dmesg dump record recovered from the snapshot slots.")
    if not report["panic_or_oops_record_count"]:
        lines.append("No valid panic/oops dmesg crash record recovered; this does not prove no crash occurred.")
    return lines


def decode_logdump(path: pathlib.Path, prefix: pathlib.Path) -> int:
    report, files = recover_logdump(path.read_bytes(), str(path), prefix.name)
    outputs = [(prefix.with_name(prefix.name + suffix), data) for suffix, data in files.items()]
    owned = [output for output, _ in outputs]
    for namespace in ("-ramoops*", "-printk-tail*"):
        owned.extend(prefix.parent.glob(prefix.name + namespace))
    if any(output.exists() or output.is_symlink() for output in owned):
        raise ValueError(f"refusing to overwrite recovered evidence for {prefix}")
    for output, data in outputs:
        with output.open("xb") as stream:
            stream.write(data)
    print("\n".join(recovery_summary(report)))
    print(f"recovery report: {prefix}-ramoops.json")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=pathlib.Path, help="device pstore records")
    parser.add_argument("--logdump", type=pathlib.Path, help="exact 64 MiB raw logdump image")
    parser.add_argument("--output-prefix", type=pathlib.Path, help="recovered file prefix (default: image stem)")
    args = parser.parse_args(argv)
    if args.logdump is not None:
        if args.paths:
            parser.error("--logdump cannot be combined with device record paths")
        prefix = args.output_prefix or args.logdump.with_suffix("")
        try:
            return decode_logdump(args.logdump, prefix)
        except (OSError, ValueError) as error:
            parser.exit(1, f"decode-pstore: {error}\n")
    if args.output_prefix is not None:
        parser.error("--output-prefix requires --logdump")
    if args.paths:
        paths = args.paths
    else:
        root = pathlib.Path("pstore")
        if not root.is_dir():
            root = pathlib.Path("/sys/fs/pstore")
        paths = sorted(p for p in root.iterdir() if p.is_file()) if root.is_dir() else []

    if not paths:
        print("no pstore records found (empty = no crash recorded yet)", file=sys.stderr)
        return 1

    for p in paths:
        text = decode(p)
        print(f"===== {p} =====")
        if text is None:
            print("(empty)")
            continue
        lines = [l for l in text.splitlines() if l.strip()]
        print(f"{len(lines)} lines")
        if "ftrace" in p.name:
            print("(function graph: first frames)")
            print("\n".join(lines[:40]))
        else:
            print("(last 60 lines — the interesting part)")
            print("\n".join(lines[-60:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))