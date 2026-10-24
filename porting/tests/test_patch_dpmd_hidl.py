#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check hash rejection, exact patch scope, and protection of existing files."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


TOOL = Path(__file__).resolve().parents[1] / "tools/patch-dpmd-hidl.py"
SPEC = importlib.util.spec_from_file_location("patch_dpmd_hidl", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PatchDpmdTest(unittest.TestCase):
    def setUp(self):
        # Synthetic fixtures keep proprietary device binaries out of the tests.
        self.dpmd = bytearray(29272)
        self.dpmd[0x5468:0x546c] = bytes.fromhex("e0 03 13 32")
        self.dpmd = bytes(self.dpmd)
        self.hidl = b"synthetic HIDL library"
        expected = bytearray(self.dpmd)
        expected[0x5469] = 0x1b
        self.expected = bytes(expected)
        hashes = patch.multiple(
            MODULE, DPMD_SHA256=hashlib.sha256(self.dpmd).hexdigest(),
            HIDL_SHA256=hashlib.sha256(self.hidl).hexdigest(),
            PATCHED_SHA256=hashlib.sha256(self.expected).hexdigest())
        hashes.start()
        self.addCleanup(hashes.stop)

    def test_changes_only_the_mapping_size_byte(self):
        result = MODULE.patch_binary(self.dpmd, self.hidl, 4096)
        self.assertEqual(result, self.expected)
        self.assertEqual(len(result), len(self.dpmd))
        self.assertEqual([i for i, (a, b) in enumerate(zip(self.dpmd, result))
                          if a != b], [0x5469])

    def test_rejects_unknown_or_truncated_dpmd(self):
        for data in (b"", self.dpmd[:-1], b"X" + self.dpmd[1:]):
            with self.subTest(size=len(data)), self.assertRaisesRegex(ValueError, "unrecognized dpmd"):
                MODULE.patch_binary(data, self.hidl, 4096)

    def test_rejects_already_patched_binary(self):
        with self.assertRaisesRegex(ValueError, "unrecognized dpmd"):
            MODULE.patch_binary(self.expected, self.hidl, 4096)

    def test_rejects_wrong_hidl(self):
        with self.assertRaisesRegex(ValueError, "unrecognized libhidlbase"):
            MODULE.patch_binary(self.dpmd, self.hidl + b"X", 4096)

    def test_rejects_other_page_sizes(self):
        for page_size in (-1, 0, 16384, 65536):
            with self.subTest(page_size=page_size), self.assertRaisesRegex(ValueError, "page size"):
                MODULE.patch_binary(self.dpmd, self.hidl, page_size)

    def test_checks_instruction_even_if_input_hash_is_updated(self):
        data = self.dpmd[:0x5468] + b"XXXX" + self.dpmd[0x546c:]
        with patch.object(MODULE, "DPMD_SHA256", hashlib.sha256(data).hexdigest()):
            with self.assertRaisesRegex(ValueError, "unexpected instruction"):
                MODULE.patch_binary(data, self.hidl, 4096)

    def test_checks_output_hash(self):
        with patch.object(MODULE, "PATCHED_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "candidate SHA256"):
                MODULE.patch_binary(self.dpmd, self.hidl, 4096)

    def test_cli_preserves_inputs_and_refuses_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dpmd, hidl, output = [root / name for name in ("dpmd", "hidl", "candidate")]
            dpmd.write_bytes(self.dpmd)
            hidl.write_bytes(self.hidl)
            args = [str(dpmd), str(hidl), str(output), "--page-size", "4096"]
            with redirect_stdout(io.StringIO()):
                MODULE.main(args)
            self.assertEqual(output.read_bytes(), self.expected)
            output.write_bytes(b"keep existing output")
            for target in (output, dpmd, hidl, root / "symlink"):
                if target.name == "symlink":
                    target.symlink_to(output)
                args[2] = str(target)
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                    MODULE.main(args)
                self.assertEqual(exc.exception.code, 1)
            self.assertEqual(dpmd.read_bytes(), self.dpmd)
            self.assertEqual(hidl.read_bytes(), self.hidl)
            self.assertEqual(output.read_bytes(), b"keep existing output")

    def test_cli_rejection_creates_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dpmd, hidl, output = [root / name for name in ("dpmd", "hidl", "candidate")]
            dpmd.write_bytes(b"unrecognized input")
            hidl.write_bytes(self.hidl)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                MODULE.main([str(dpmd), str(hidl), str(output), "--page-size", "4096"])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
