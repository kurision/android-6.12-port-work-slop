#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Reject corrupt reset records rather than attributing stale/invalid evidence."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "decode_reset", Path(__file__).with_name("decode-reset.py"))
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)


class ResetDecodeTests(unittest.TestCase):
    def record(self, header, tail=b""):
        blob = bytearray(decoder.PARTITION_SIZE)
        offset = decoder.OFFSET
        blob[offset:offset + len(header)] = header
        start = offset + decoder.HEADER
        blob[start:start + len(tail)] = tail
        return blob

    def test_maximum_tail_is_preserved_without_header_padding(self):
        tail = b"K" * (decoder.SIZE - decoder.HEADER)
        header = (b"ACKRESET1 timestamp_ns=70000000000 action=1 pid=1 "
                  b"comm=init command=recovery tail_bytes=65024\n")
        self.assertEqual(decoder.decode(self.record(header, tail)), header + tail)

    def test_oversized_tail_is_rejected(self):
        header = (b"ACKRESET1 timestamp_ns=70000000000 action=1 pid=1 "
                  b"comm=init command=recovery tail_bytes=65025\n")
        with self.assertRaisesRegex(ValueError, "tail length"):
            decoder.decode(self.record(header))

    def test_claimed_record_with_broken_header_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            decoder.decode(self.record(b"ACKRESET1 timestamp_ns=7000\n"))

    def test_empty_region_does_not_claim_a_reset(self):
        self.assertIsNone(decoder.decode(self.record(b"")))

    def test_short_partition_is_not_treated_as_missing_evidence(self):
        with self.assertRaisesRegex(ValueError, "expected"):
            decoder.decode(b"\0" * decoder.SIZE)


if __name__ == "__main__":
    unittest.main()
