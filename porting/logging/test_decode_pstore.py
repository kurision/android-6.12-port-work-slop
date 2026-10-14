#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Deterministic snapshot fixtures; no adb or retained hardware evidence needed."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zlib

spec = importlib.util.spec_from_file_location(
    "decode_pstore", Path(__file__).with_name("decode-pstore.py"))
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)


def raw_deflate(data):
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def ram_zone(data, size, start=None):
    capacity = size - decoder.RAM_HEADER.size
    assert len(data) <= capacity
    if len(data) == capacity:
        start = 0 if start is None else start
        # Put the oldest byte at the write cursor in the full circular buffer.
        storage = data[-start:] + data[:-start] if start else data
    else:
        assert start is None
        start = len(data)
        # Nonzero padding catches accidental recovery past the valid byte count.
        storage = data + b"X" * (capacity - len(data))
    return decoder.RAM_HEADER.pack(decoder.RAM_SIGNATURE, start, len(data)) + storage


def snapshot(blob, slot=0, seq=1, timestamp=1000, console=b"console\n"):
    base = decoder.SNAPSHOT_OFFSET + slot * decoder.SLOT_STRIDE
    blob[base:base + decoder.SLOT_STRIDE] = b"\0" * decoder.SLOT_STRIDE
    decoder.SNAPSHOT_HEADER.pack_into(
        blob, base, decoder.SNAPSHOT_MAGIC, seq, seq, timestamp,
        decoder.PAGE_SIZE, decoder.PAYLOAD_SIZE, decoder.RAMOOPS_PHYS,
        slot, 0, 0, 0, 0)
    payload = base + decoder.PAGE_SIZE
    for zone in range(decoder.DMESG_ZONE_COUNT):
        decoder.RAM_HEADER.pack_into(
            blob, payload + zone * decoder.DMESG_ZONE_SIZE,
            decoder.RAM_SIGNATURE, 0, 0)
    console_offset = payload + decoder.CONSOLE_OFFSET
    blob[console_offset:console_offset + decoder.CONSOLE_SIZE] = ram_zone(
        console, decoder.CONSOLE_SIZE)
    return payload


def put_dmesg(blob, payload, data, zone=0, start=None):
    offset = payload + zone * decoder.DMESG_ZONE_SIZE
    blob[offset:offset + decoder.DMESG_ZONE_SIZE] = ram_zone(
        data, decoder.DMESG_ZONE_SIZE, start)


def checksum_header(blob, base):
    struct.pack_into("<I", blob, base + 56, 0)
    struct.pack_into("<I", blob, base + 56,
                     zlib.crc32(blob[base:base + decoder.SNAPSHOT_HEADER.size]))


def commit_version1(blob, base):
    offset, length = struct.unpack_from("<II", blob, base + 32)
    payload = blob[base + offset:base + offset + length]
    struct.pack_into("<4I", blob, base + 48, 1, zlib.crc32(payload), 0, 0)
    checksum_header(blob, base)


def periodic_tail(blob, slot=0, seq=1, timestamp=3000, data=b"periodic printk\n"):
    assert len(data) <= decoder.TAIL_PAYLOAD_SIZE
    base = decoder.TAIL_OFFSET + slot * decoder.TAIL_SLOT_STRIDE
    blob[base:base + decoder.TAIL_SLOT_STRIDE] = b"\0" * decoder.TAIL_SLOT_STRIDE
    decoder.SNAPSHOT_HEADER.pack_into(
        blob, base, decoder.TAIL_MAGIC, seq, seq, timestamp,
        decoder.PAGE_SIZE, len(data), 0, slot, 0, 0, 0, 0)
    blob[base + decoder.PAGE_SIZE:base + decoder.PAGE_SIZE + len(data)] = data
    commit_version1(blob, base)
    return base


class SnapshotDecodeTests(unittest.TestCase):
    def setUp(self):
        self.blob = bytearray(decoder.PARTITION_SIZE)
        self.payload = snapshot(self.blob)

    def recover(self):
        return decoder.recover_logdump(self.blob, "fixture-logdump.bin", "run1")

    def test_console_uses_actual_console_zone_not_first_dmesg_magic(self):
        console = b"[0.000000] Linux version fixture\n\0\xffunterminated"
        self.payload = snapshot(self.blob, console=console)
        put_dmesg(self.blob, self.payload, b"not a dmesg or console record")
        report, files = self.recover()
        suffix = "-ramoops-slot0-seq1-ns1000-snapshot-console.log"
        self.assertEqual(files[suffix], console)
        record = report["slots"][0]["console"]
        self.assertEqual(record["file"], "run1" + suffix)
        self.assertEqual(record["kind"], "snapshot-console")
        self.assertEqual(record["size"], len(console))
        self.assertEqual(report["panic_or_oops_record_count"], 0)

    def test_full_console_wrap_boundaries_preserve_byte_order(self):
        capacity = decoder.CONSOLE_SIZE - decoder.RAM_HEADER.size
        data = (bytes(range(256)) * (capacity // 256 + 1))[:capacity]
        offset = self.payload + decoder.CONSOLE_OFFSET
        for start in (0, 1, capacity - 1, capacity):
            with self.subTest(start=start):
                self.blob[offset:offset + decoder.CONSOLE_SIZE] = ram_zone(
                    data, decoder.CONSOLE_SIZE, start)
                report, files = self.recover()
                self.assertEqual(report["slots"][0]["console"]["start"], start)
                self.assertEqual(next(value for name, value in files.items()
                                      if name.endswith("-snapshot-console.log")), data)

    def test_invalid_ring_bounds_and_nonatomic_partial_header_are_rejected(self):
        capacity = decoder.CONSOLE_SIZE - decoder.RAM_HEADER.size
        offset = self.payload + decoder.CONSOLE_OFFSET
        for start, size in ((1, 0), (capacity + 1, capacity),
                            (0, capacity + 1), (3, 2), (0, 2),
                            (0xFFFFFFFF, 0xFFFFFFFF)):
            with self.subTest(start=start, size=size):
                decoder.RAM_HEADER.pack_into(
                    self.blob, offset, decoder.RAM_SIGNATURE, start, size)
                report, files = self.recover()
                self.assertEqual(report["slots"][0]["console"]["status"], "invalid")
                self.assertEqual(set(files), {"-ramoops.json"})
        with self.assertRaisesRegex(ValueError, "truncated"):
            decoder.recover_zone(b"DBGC")

    def test_empty_console_and_empty_dmesg_explicitly_report_absence(self):
        snapshot(self.blob, console=b"")
        report, files = self.recover()
        self.assertEqual(set(files), {"-ramoops.json"})
        self.assertEqual(report["slots"][0]["console"]["status"], "empty")
        self.assertEqual(report["slots"][0]["dmesg_empty_zones"], 119)
        self.assertEqual(report["slots"][0]["dmesg_rejected_zones"], [])

    def test_mark_page_decodes_and_is_not_a_dmesg_zone(self):
        page = self.payload + decoder.MARK_OFFSET
        self.blob[page:page + decoder.DMESG_ZONE_SIZE] = b"\0" * decoder.DMESG_ZONE_SIZE
        struct.pack_into("<II", self.blob, page + 0x18, 0x48575652, 0x10100000)
        struct.pack_into("<II", self.blob, page + decoder.MARK_HDR,
                         decoder.MARK_MAGIC, 0x1234abcd)
        report, _ = self.recover()
        slot = report["slots"][0]
        self.assertEqual(slot["diag_marks"], {"boot_id": "0x1234abcd", "slots": [
            {"slot": "0x18", "tag": "0x48575652", "val": "0x10100000"}]})
        self.assertEqual(slot["dmesg_empty_zones"], 118)
        self.assertEqual(slot["dmesg_rejected_zones"], [])

    def test_plain_dump_has_independent_dump_and_snapshot_provenance(self):
        body = b"Panic#7 Part1\n[3.000000] actual fixture dump\n"
        put_dmesg(self.blob, self.payload, b"====1700000000.123456-D\n" + body)
        report, files = self.recover()
        record = report["slots"][0]["dmesg"][0]
        self.assertEqual(record["dump_timestamp_sec"], 1700000000)
        self.assertEqual(record["dump_timestamp_us"], 123456)
        self.assertEqual(record["dump_reason"], "Panic")
        self.assertEqual(record["dump_count"], 7)
        self.assertEqual(record["compression"], "none")
        self.assertEqual(files[record["file"][len("run1"):]], body)
        self.assertEqual(report["slots"][0]["timestamp_ns"], 1000)
        self.assertEqual(report["panic_or_oops_record_count"], 1)

    def test_raw_deflate_dump_is_decoded_without_its_ramoops_header(self):
        body = b"Oops#1 Part1\n" + b"[4.000000] fixture trace\n" * 100
        put_dmesg(self.blob, self.payload,
                  b"====1700000000.000007-C\n" + raw_deflate(body), zone=118)
        report, files = self.recover()
        record = report["slots"][0]["dmesg"][0]
        self.assertEqual(record["zone"], 118)
        self.assertEqual(record["payload_offset"], 118 * 4096)
        self.assertEqual(record["compression"], "raw-deflate")
        self.assertEqual(files[record["file"][len("run1"):]], body)

    def test_legacy_header_and_zero_or_signed_wall_clock_are_recoverable(self):
        body = b"Oops#1 Part1\nfixture trace\n"
        for seconds in (0, -1, -(1 << 63), (1 << 63) - 1):
            with self.subTest(seconds=seconds):
                data, record = decoder.recover_dmesg(
                    f"===={seconds}.000001\n".encode() + body)
                self.assertEqual(data, body)
                self.assertEqual(record["dump_timestamp_sec"], seconds)

    def test_full_dmesg_ring_is_unwrapped_before_header_validation(self):
        capacity = decoder.DMESG_ZONE_SIZE - decoder.RAM_HEADER.size
        header = b"====1700000000.000001-D\n"
        dump_header = b"Oops#1 Part1\n"
        body = dump_header + b"T" * (capacity - len(header) - len(dump_header))
        put_dmesg(self.blob, self.payload, header + body, start=capacity - 1)
        report, files = self.recover()
        record = report["slots"][0]["dmesg"][0]
        self.assertEqual(files[record["file"][len("run1"):]], body)

    def test_bad_compressed_streams_never_fall_back_to_plain_crash_text(self):
        body = b"Panic#1 Part1\nfixture panic\n"
        compressed = raw_deflate(body)
        for data in (body, compressed[:-1], compressed + b"trailing",
                     zlib.compress(body), b"\xff" * 8):
            with self.subTest(data=data):
                put_dmesg(self.blob, self.payload, b"====1.000001-C\n" + data)
                report, files = self.recover()
                self.assertEqual(report["dmesg_record_count"], 0)
                self.assertEqual(report["panic_or_oops_record_count"], 0)
                self.assertFalse(any("-dmesg" in name for name in files))
                self.assertEqual(report["slots"][0]["dmesg_rejected_zones"][0]["zone"], 0)

    def test_decompression_limit_matches_kernel_and_rejects_overflow(self):
        limit = 3 * (decoder.DMESG_ZONE_SIZE - decoder.RAM_HEADER.size)
        header = b"Panic#1 Part1\n"
        for size in (limit, limit + 1):
            with self.subTest(size=size):
                body = header + b"T" * (size - len(header))
                put_dmesg(self.blob, self.payload,
                          b"====1.000001-C\n" + raw_deflate(body))
                report, files = self.recover()
                if size == limit:
                    record = report["slots"][0]["dmesg"][0]
                    self.assertEqual(files[record["file"][len("run1"):]], body)
                else:
                    self.assertEqual(report["dmesg_record_count"], 0)
                    self.assertFalse(any("-dmesg" in name for name in files))

    def test_console_prefix_and_pmsg_text_do_not_become_crash_records(self):
        text = b"Kernel panic - not syncing: fixture text only\n"
        snapshot(self.blob, console=text)
        self.blob[:len(text)] = text
        offset = self.payload + 0xF7000
        self.blob[offset:offset + len(text)] = text
        malformed = (text, b"====1.000001-D\n" + text,
                     b"====9223372036854775808.000001-D\nPanic#1 Part1\ntrace\n",
                     b"====-9223372036854775809.000001-D\nPanic#1 Part1\ntrace\n",
                     b"====1.1000000-D\nPanic#1 Part1\ntrace\n",
                     b"====1.000001-Q\nPanic#1 Part1\ntrace\n",
                     b"====1.000001-D\nPanic#1 Part2\ntrace\n",
                     b"====1.000001-D\nPanic#1 Part1\n")
        for data in malformed:
            with self.subTest(data=data):
                put_dmesg(self.blob, self.payload, data)
                report, files = self.recover()
                self.assertEqual(report["panic_or_oops_record_count"], 0)
                self.assertEqual(report["dmesg_record_count"], 0)
                self.assertFalse(any("-dmesg" in name for name in files))

    def test_noncrash_dump_reason_is_not_called_panic(self):
        body = b"Shutdown#1 Part1\nfixture shutdown\n"
        put_dmesg(self.blob, self.payload, b"====1.000001-D\n" + body)
        report, _ = self.recover()
        self.assertEqual(report["dmesg_record_count"], 1)
        self.assertEqual(report["panic_or_oops_record_count"], 0)

    def test_corrupt_snapshot_metadata_blocks_recovery_from_good_payload(self):
        base = decoder.SNAPSHOT_OFFSET
        header = [decoder.SNAPSHOT_MAGIC, 1, 1, 1000, decoder.PAGE_SIZE,
                  decoder.PAYLOAD_SIZE, decoder.RAMOOPS_PHYS, 0, 0, 0, 0, 0]
        mutations = ((0, 0), (1, 0), (2, 2), (3, 0), (4, 4),
                     (5, decoder.PAYLOAD_SIZE - 1), (6, 0), (7, 1), (8, 1))
        for field, value in mutations:
            with self.subTest(field=field):
                changed = header.copy()
                changed[field] = value
                decoder.SNAPSHOT_HEADER.pack_into(self.blob, base, *changed)
                report, files = self.recover()
                self.assertFalse(report["slots"][0]["header_valid"])
                self.assertEqual(set(files), {"-ramoops.json"})
        header[1] = header[2] = 2  # Valid counters, wrong alternating slot.
        decoder.SNAPSHOT_HEADER.pack_into(self.blob, base, *header)
        report, files = self.recover()
        self.assertEqual(set(files), {"-ramoops.json"})
        snapshot(self.blob)
        self.blob[base + decoder.SNAPSHOT_HEADER.size] = 1
        report, files = self.recover()
        self.assertEqual(set(files), {"-ramoops.json"})

    def test_legacy_snapshot_integrity_is_explicitly_unverified(self):
        report, files = self.recover()
        slot = report["slots"][0]
        self.assertEqual(slot["version"], 0)
        self.assertEqual(slot["validation"], "legacy-structural-only")
        self.assertIn("unverified", slot["integrity"])
        self.assertIsNone(slot["header_crc_valid"])
        self.assertIsNone(slot["payload_crc_valid"])
        self.assertTrue(slot["header_valid"])
        self.assertEqual(files["-ramoops-slot0-seq1-ns1000-snapshot-console.log"], b"console\n")

    def test_version1_snapshot_checks_both_crcs(self):
        body = b"Panic#2 Part1\nfixture committed dump\n"
        put_dmesg(self.blob, self.payload, b"====1.000001-D\n" + body)
        commit_version1(self.blob, decoder.SNAPSHOT_OFFSET)
        report, files = self.recover()
        slot = report["slots"][0]
        self.assertEqual(slot["version"], 1)
        self.assertEqual(slot["status"], "crc-validated")
        self.assertTrue(slot["header_crc_valid"])
        self.assertTrue(slot["payload_crc_valid"])
        self.assertEqual(slot["freshness"], "unverified")
        self.assertEqual(slot["validation"], "header-and-payload-crc32-verified")
        self.assertEqual(files[slot["dmesg"][0]["file"][len("run1"):]], body)
        self.assertEqual(report["panic_or_oops_record_count"], 1)

    def test_version1_bad_header_or_payload_crc_blocks_all_snapshot_exports(self):
        base = decoder.SNAPSHOT_OFFSET
        for damaged in ("header", "payload"):
            with self.subTest(damaged=damaged):
                payload = snapshot(self.blob)
                put_dmesg(self.blob, payload, b"====1.000001-D\nPanic#1 Part1\ntrace\n")
                commit_version1(self.blob, base)
                offset = base + 24 if damaged == "header" else payload + decoder.CONSOLE_OFFSET + 12
                self.blob[offset] ^= 1
                report, files = self.recover()
                slot = report["slots"][0]
                self.assertTrue(slot["structure_valid"])
                self.assertFalse(slot["header_valid"])
                self.assertEqual(slot["header_crc_valid"], damaged != "header")
                self.assertEqual(slot["payload_crc_valid"], damaged != "payload")
                self.assertEqual(slot["validation"], "crc32-rejected")
                self.assertNotIn("console", slot)
                self.assertNotIn("dmesg", slot)
                self.assertEqual(report["dmesg_record_count"], 0)
                self.assertEqual(report["panic_or_oops_record_count"], 0)
                self.assertEqual(set(files), {"-ramoops.json"})

    def test_unknown_versions_and_conflicting_offsets_fail_even_with_header_crc(self):
        base = decoder.SNAPSHOT_OFFSET
        for field, value in ((8, 2), (4, decoder.PAGE_SIZE + decoder.SLOT_STRIDE),
                             (4, decoder.TAIL_OFFSET - base + decoder.PAGE_SIZE),
                             (5, decoder.PAYLOAD_SIZE + 1), (11, 1)):
            with self.subTest(field=field, value=value):
                snapshot(self.blob)
                commit_version1(self.blob, base)
                fields = list(decoder.SNAPSHOT_HEADER.unpack_from(self.blob, base))
                fields[field] = value
                decoder.SNAPSHOT_HEADER.pack_into(self.blob, base, *fields)
                checksum_header(self.blob, base)
                report, files = self.recover()
                self.assertFalse(report["slots"][0]["header_valid"])
                self.assertFalse(report["slots"][0]["structure_valid"])
                self.assertEqual(set(files), {"-ramoops.json"})
        for field in (9, 10):
            with self.subTest(legacy_nonzero_reserved=field):
                snapshot(self.blob)
                struct.pack_into("<I", self.blob, base + 48 + (field - 8) * 4, 1)
                report, files = self.recover()
                self.assertFalse(report["slots"][0]["header_valid"])
                self.assertEqual(set(files), {"-ramoops.json"})

    def test_invalidated_target_preserves_previous_committed_snapshot(self):
        previous = snapshot(self.blob, slot=1, seq=2, timestamp=2000, console=b"previous committed\n")
        commit_version1(self.blob, previous - decoder.PAGE_SIZE)
        target = snapshot(self.blob, seq=3, timestamp=3000, console=b"unpublished replacement\n")
        base = target - decoder.PAGE_SIZE
        self.blob[base:base + decoder.PAGE_SIZE] = b"\0" * decoder.PAGE_SIZE
        report, files = self.recover()
        self.assertEqual(report["slots"][0]["status"], "absent")
        self.assertTrue(report["slots"][1]["header_valid"])
        self.assertEqual(report["slots"][1]["seq"], 2)
        self.assertEqual(set(files), {
            "-ramoops.json", "-ramoops-slot1-seq2-ns2000-snapshot-console.log"})
        self.assertEqual(files["-ramoops-slot1-seq2-ns2000-snapshot-console.log"],
                         b"previous committed\n")

    def test_partial_version1_header_is_rejected_before_payload_recovery(self):
        base = decoder.SNAPSHOT_OFFSET
        for kept in (8, 32, 52, 56):
            with self.subTest(header_bytes=kept):
                snapshot(self.blob)
                commit_version1(self.blob, base)
                self.blob[base + kept:base + decoder.SNAPSHOT_HEADER.size] = (
                    b"\0" * (decoder.SNAPSHOT_HEADER.size - kept))
                report, files = self.recover()
                self.assertFalse(report["slots"][0]["header_valid"])
                self.assertEqual(set(files), {"-ramoops.json"})

    def test_overlapping_or_out_of_partition_layout_never_exports(self):
        for offset in (decoder.SNAPSHOT_OFFSET, 0x3F00000, decoder.PARTITION_SIZE):
            with self.subTest(tail_offset=offset), mock.patch.object(decoder, "TAIL_OFFSET", offset):
                with self.assertRaisesRegex(ValueError, "logdump range"):
                    self.recover()


    def test_bad_console_signature_does_not_hide_a_valid_dmesg_zone(self):
        struct.pack_into("<I", self.blob, self.payload + decoder.CONSOLE_OFFSET, 0)
        put_dmesg(self.blob, self.payload,
                  b"====1.000001-D\nOops#1 Part1\nfixture oops\n", zone=5)
        report, files = self.recover()
        self.assertEqual(report["slots"][0]["console"]["status"], "invalid")
        self.assertEqual(report["slots"][0]["dmesg"][0]["zone"], 5)
        self.assertTrue(any("-dmesg5-" in name for name in files))
        self.assertFalse(any("snapshot-console" in name for name in files))

    def test_stale_or_mixed_boot_slots_are_preserved_without_latest_selection(self):
        for seq, timestamp in ((100, 9999000), (2, 999), (2, 2000)):
            with self.subTest(seq=seq, timestamp=timestamp):
                snapshot(self.blob, slot=1, seq=seq, timestamp=timestamp,
                         console=b"other boot\n")
                report, files = self.recover()
                consoles = {data for name, data in files.items()
                            if name.endswith("-snapshot-console.log")}
                self.assertEqual(consoles, {b"console\n", b"other boot\n"})
                self.assertTrue(all(slot["freshness"] == "unverified"
                                    for slot in report["slots"]))

    def test_absent_and_wrong_sized_images_do_not_claim_a_crash(self):
        base = decoder.SNAPSHOT_OFFSET
        self.blob[base:base + decoder.SLOT_STRIDE] = b"\0" * decoder.SLOT_STRIDE
        report, files = self.recover()
        self.assertEqual([slot["status"] for slot in report["slots"]], ["absent", "absent"])
        self.assertEqual(report["dmesg_record_count"], 0)
        self.assertEqual(set(files), {"-ramoops.json"})
        for blob in (b"", bytearray(decoder.PARTITION_SIZE + 1)):
            with self.subTest(length=len(blob)):
                with self.assertRaisesRegex(ValueError, "expected"):
                    decoder.recover_logdump(blob, "fixture", "run1")

    def test_cli_writes_provenance_and_refuses_existing_or_dangling_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "raw.bin"
            image.write_bytes(self.blob)
            prefix = root / "run1"
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(decoder.main(["--logdump", str(image),
                                               "--output-prefix", str(prefix)]), 0)
            report = json.loads((root / "run1-ramoops.json").read_bytes())
            console = report["slots"][0]["console"]
            self.assertEqual((root / console["file"]).read_bytes(), b"console\n")
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            with self.assertRaisesRegex(ValueError, "overwrite"):
                decoder.decode_logdump(image, prefix)
            self.assertEqual(before, {path.name: path.read_bytes() for path in root.iterdir()})
            (root / "run2-ramoops.json").symlink_to("missing")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                decoder.decode_logdump(image, root / "run2")
            self.assertEqual([path.name for path in root.glob("run2*")], ["run2-ramoops.json"])

    def test_existing_device_record_mode_still_decodes_plain_and_deflate(self):
        body = b"Panic#1 Part1\nfixture dump\n"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dmesg-ramoops-0"
            for data in (body, raw_deflate(body), zlib.compress(body)):
                with self.subTest(data=data):
                    path.write_bytes(data)
                    self.assertEqual(decoder.decode(path), body.decode())
                    with redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(decoder.main([str(path)]), 0)
                    self.assertIn("fixture dump", output.getvalue())


class PeriodicTailDecodeTests(unittest.TestCase):
    def setUp(self):
        self.blob = bytearray(decoder.PARTITION_SIZE)

    def recover(self):
        return decoder.recover_logdump(self.blob, "fixture-logdump.bin", "run1")

    def test_periodic_tails_are_separate_samples_not_crash_or_reset_records(self):
        data = b"====1.000001-D\nPanic#1 Part1\nACKRESET1\nKernel panic - fixture text only\n"
        periodic_tail(self.blob, data=data)
        periodic_tail(self.blob, slot=1, seq=2, timestamp=4000, data=b"next sample\n")
        report, files = self.recover()
        self.assertEqual(report["periodic_tail_sample_count"], 2)
        self.assertEqual(report["dmesg_record_count"], 0)
        self.assertEqual(report["panic_or_oops_record_count"], 0)
        self.assertEqual(set(files), {
            "-ramoops.json", "-printk-tail-slot0-seq1-ns3000-periodic-printk.log",
            "-printk-tail-slot1-seq2-ns4000-periodic-printk.log"})
        for index, payload in enumerate((data, b"next sample\n")):
            slot = report["periodic_tail_slots"][index]
            tail = slot["tail"]
            self.assertTrue(slot["header_valid"])
            self.assertTrue(slot["header_crc_valid"])
            self.assertTrue(slot["payload_crc_valid"])
            self.assertEqual(slot["version"], 1)
            self.assertEqual(tail["kind"], "periodic-printk-tail")
            self.assertNotIn("dump_reason", tail)
            self.assertEqual(files[tail["file"][len("run1"):]], payload)

    def test_tail_lengths_use_only_declared_bytes_including_capacity_truncated_text(self):
        for length in (0, 1, decoder.TAIL_PAYLOAD_SIZE):
            with self.subTest(length=length):
                # A bounded tail may start/end mid-line; never invent a header or newline.
                data = (b"continued line" + b"T" * decoder.TAIL_PAYLOAD_SIZE)[:length]
                base = periodic_tail(self.blob, data=data)
                if length < decoder.TAIL_PAYLOAD_SIZE:
                    self.blob[base + decoder.PAGE_SIZE + length] = 0xFF
                report, files = self.recover()
                slot = report["periodic_tail_slots"][0]
                self.assertTrue(slot["header_valid"])
                self.assertEqual(slot["payload_len"], length)
                self.assertEqual(slot["tail"]["bytes"], length)
                self.assertEqual(report["periodic_tail_sample_count"], bool(length))
                if length:
                    self.assertEqual(files[slot["tail"]["file"][len("run1"):]], data)
                else:
                    self.assertEqual(slot["tail"]["status"], "empty")
                    self.assertEqual(set(files), {"-ramoops.json"})

    def test_bad_tail_header_and_payload_crcs_block_exports(self):
        for damaged in ("header", "payload"):
            with self.subTest(damaged=damaged):
                base = periodic_tail(self.blob)
                offset = base + 24 if damaged == "header" else base + decoder.PAGE_SIZE
                self.blob[offset] ^= 1
                report, files = self.recover()
                slot = report["periodic_tail_slots"][0]
                self.assertTrue(slot["structure_valid"])
                self.assertFalse(slot["header_valid"])
                self.assertEqual(slot["header_crc_valid"], damaged != "header")
                self.assertEqual(slot["payload_crc_valid"], damaged != "payload")
                self.assertNotIn("tail", slot)
                self.assertEqual(report["periodic_tail_sample_count"], 0)
                self.assertEqual(set(files), {"-ramoops.json"})

    def test_invalid_tail_sizes_offsets_identity_and_versions_are_rejected(self):
        mutations = ((5, decoder.TAIL_PAYLOAD_SIZE + 1), (5, 0xFFFFFFFF),
                     (4, decoder.PAGE_SIZE + decoder.TAIL_SLOT_STRIDE),
                     (4, decoder.SNAPSHOT_OFFSET), (6, decoder.RAMOOPS_PHYS),
                     (7, 1), (8, 0), (8, 2), (11, 1))
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                base = periodic_tail(self.blob)
                fields = list(decoder.SNAPSHOT_HEADER.unpack_from(self.blob, base))
                fields[field] = value
                if field == 8 and value == 0:
                    fields[9:] = [0, 0, 0]  # Fully legacy-shaped, but tails require version1.
                decoder.SNAPSHOT_HEADER.pack_into(self.blob, base, *fields)
                if value != 0 or field != 8:
                    checksum_header(self.blob, base)
                report, files = self.recover()
                self.assertFalse(report["periodic_tail_slots"][0]["header_valid"])
                self.assertEqual(set(files), {"-ramoops.json"})
        base = periodic_tail(self.blob)
        self.blob[base + decoder.SNAPSHOT_HEADER.size] = 1
        report, files = self.recover()
        self.assertEqual(set(files), {"-ramoops.json"})

    def test_truncated_tail_payload_and_partition_never_publish(self):
        data = b"periodic tail whose final bytes did not reach storage\n"
        base = periodic_tail(self.blob, data=data)
        end = base + decoder.PAGE_SIZE + len(data)
        self.blob[end - 8:end] = b"\0" * 8
        report, files = self.recover()
        self.assertFalse(report["periodic_tail_slots"][0]["header_valid"])
        self.assertEqual(set(files), {"-ramoops.json"})
        with self.assertRaisesRegex(ValueError, "expected"):
            decoder.recover_logdump(self.blob[:end - 1], "truncated.bin", "run1")

    def test_invalidated_tail_target_preserves_previous_committed_sample(self):
        periodic_tail(self.blob, slot=1, seq=2, timestamp=4000, data=b"previous tail\n")
        base = periodic_tail(self.blob, seq=3, timestamp=5000, data=b"unpublished tail\n")
        self.blob[base:base + decoder.PAGE_SIZE] = b"\0" * decoder.PAGE_SIZE
        report, files = self.recover()
        self.assertEqual(report["periodic_tail_slots"][0]["status"], "absent")
        self.assertTrue(report["periodic_tail_slots"][1]["header_valid"])
        self.assertEqual(report["periodic_tail_sample_count"], 1)
        self.assertEqual(set(files), {
            "-ramoops.json", "-printk-tail-slot1-seq2-ns4000-periodic-printk.log"})
        self.assertEqual(files["-printk-tail-slot1-seq2-ns4000-periodic-printk.log"], b"previous tail\n")

    def test_cli_tail_publication_and_namespace_overwrite_refusal(self):
        periodic_tail(self.blob)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "raw.bin"
            image.write_bytes(self.blob)
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(decoder.decode_logdump(image, root / "run1"), 0)
            report = json.loads((root / "run1-ramoops.json").read_bytes())
            tail = report["periodic_tail_slots"][0]["tail"]
            self.assertEqual((root / tail["file"]).read_bytes(), b"periodic printk\n")
            for index, dangling in enumerate((False, True)):
                prefix = root / f"run{index + 2}"
                existing = prefix.with_name(prefix.name + "-printk-tail-slot1-seq99-ns99-periodic-printk.log")
                if dangling:
                    existing.symlink_to("missing")
                else:
                    existing.write_bytes(b"existing evidence\n")
                with self.assertRaisesRegex(ValueError, "overwrite"):
                    decoder.decode_logdump(image, prefix)
                self.assertFalse(prefix.with_name(prefix.name + "-ramoops.json").exists())
                if dangling:
                    self.assertTrue(existing.is_symlink())
                else:
                    self.assertEqual(existing.read_bytes(), b"existing evidence\n")


if __name__ == "__main__":
    unittest.main()
