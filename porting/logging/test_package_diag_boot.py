#!/usr/bin/env python3
"""Focused safety tests for the protected firmware-mount patch."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "packager", Path(__file__).with_name("package-diag-boot.py"))
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)

MODEM = (b"/dev/block/bootdevice/by-name/modem\t/vendor/firmware_mnt\tvfat\t"
         b"ro,shortname=lower,uid=1000,gid=1000,dmask=227,fmask=337,"
         b"context=u:object_r:firmware_file:s0 wait,slotselect\n")
OTHER = (b"# protected fstab\n"
         b"/dev/block/bootdevice/by-name/userdata /data f2fs "
         b"nosuid,nodev,noatime wait,check,encryptable=footer\n")


class ModemFstabTest(unittest.TestCase):
    def test_only_masks_change(self):
        data = OTHER + MODEM
        result = packager.readable_modem_fstab(data)
        self.assertEqual(result, data.replace(b"dmask=227", b"dmask=222")
                         .replace(b"fmask=337", b"fmask=333"))
        self.assertEqual(packager.readable_modem_fstab(result), result)
        self.assertEqual(0o777 & ~0o333, 0o444)
        self.assertEqual(0o777 & ~0o222, 0o555)

    def test_reject_unexpected_mounts(self):
        for data in (OTHER, MODEM + MODEM,
                     MODEM.replace(b"ro,", b"rw,"),
                     MODEM.replace(b"fmask=337", b"fmask=000"),
                     MODEM.replace(b"uid=1000", b"uid=0"),
                     MODEM.replace(b"firmware_file", b"vendor_file"),
                     MODEM.replace(b"dmask=227", b"dmask=227,dmask=000")):
            with self.subTest(data=data), self.assertRaises(SystemExit):
                packager.readable_modem_fstab(data)

    def test_ramdisk_preserves_other_records(self):
        def record(name, data):
            fields = ["00000000"] * 13
            fields[1] = "%08x" % 0o100644
            fields[packager.FILESIZE_FIELD] = "%08x" % len(data)
            fields[packager.NAMESIZE_FIELD] = "%08x" % (len(name) + 1)
            return dict(name=name, fields=fields, data=data)

        records = [record("init", b"old init"),
                   record("ack-protected-fstab.qcom", OTHER + MODEM),
                   record("userdebug_plat_sepolicy.cil", b"known-good policy"),
                   record("force_debuggable", b""),
                   record("TRAILER!!!", b"")]
        cpio = packager.build_cpio(records, b"\0" * 16)
        for enabled in (False, True):
            output, count = packager.customize_ramdisk(
                cpio, b"new init", [], False, b"", enabled)
            updated, tail = packager.parse_cpio(output)
            self.assertEqual(count, len(records))
            self.assertEqual(tail, b"\0" * 16)
            for before, after in zip(records, updated):
                if before["name"] == "init":
                    self.assertEqual(after["data"], b"new init")
                elif enabled and before["name"] == "ack-protected-fstab.qcom":
                    self.assertEqual(after["data"],
                                     packager.readable_modem_fstab(before["data"]))
                    self.assertEqual(after["fields"], before["fields"])
                else:
                    self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
