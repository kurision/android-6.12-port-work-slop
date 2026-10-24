#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check module replacement without changing unrelated base ramdisk records."""

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "package_diag_boot", ROOT / "porting/logging/package-diag-boot.py")
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


def record(name, data=b"", mode=0o100644):
    fields = ["00000000"] * 13
    fields[1] = f"{mode:08x}"
    fields[4] = "00000001"
    fields[6] = f"{len(data):08x}"
    fields[11] = f"{len(name) + 1:08x}"
    return {"name": name, "fields": fields, "data": data}


class ModulePackaging(unittest.TestCase):
    def setUp(self):
        self.records = [record("init", b"old-init"),
                        record("ack-modules", mode=0o40755),
                        record("ack-modules/audio.ko", b"old-module"),
                        record("ack-modules/load-order", b"audio.ko\n"),
                        record("ack-modules/untouched.ko", b"keep-module"),
                        record("ack-vendor-file-contexts", b"keep-labels"),
                        record("lib", mode=0o40755),
                        record("lib/firmware", mode=0o40755),
                        record("lib/firmware/test.bin", b"firmware"),
                        record("TRAILER!!!")]

    def package(self, modules=(), firmware=None):
        data = PACKAGE.build_cpio(self.records, b"\0" * 16)
        packed, _ = PACKAGE.customize_ramdisk(
            data, b"new-init", firmware or [], False, b"", mod_entries=modules)
        return PACKAGE.parse_cpio(packed)

    def test_replace_modules_preserving_other_records(self):
        entries = [("ack-modules/audio.ko", b"new-module-longer"),
                   ("ack-modules/load-order", b"audio.ko\nnew.ko\n"),
                   ("ack-modules/new.ko", b"new-module")]
        after, tail = self.package(entries)
        self.assertEqual(tail, b"\0" * 16)
        by_name = {r["name"]: r for r in after}
        self.assertEqual(len(by_name), len(after))
        changes = dict(entries, init=b"new-init")
        for before in self.records:
            actual = by_name[before["name"]]
            if before["name"] not in changes:
                self.assertEqual(actual, before)
                continue
            self.assertEqual(actual["data"], changes[before["name"]])
            fields = before["fields"].copy()
            fields[6] = f'{len(actual["data"]):08x}'
            self.assertEqual(actual["fields"], fields)
        self.assertEqual(by_name["ack-modules/new.ko"]["data"], b"new-module")

    def test_identical_module_keeps_record(self):
        after, _ = self.package([("ack-modules/audio.ko", b"old-module")])
        self.assertEqual(after[2], self.records[2])

    def test_non_regular_module_rejected_even_if_identical(self):
        for mode in (0o120777, 0o40755):
            with self.subTest(mode=mode):
                self.records[2]["fields"][1] = f"{mode:08x}"
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.package([("ack-modules/audio.ko", b"old-module")])

    def test_firmware_replacement_still_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.package(firmware=[("lib/firmware/test.bin", b"different")])


if __name__ == "__main__":
    unittest.main()
