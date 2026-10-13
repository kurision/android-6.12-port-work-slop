#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute the real snapshot writer against a volatile/durable storage model."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "decode_pstore", Path(__file__).with_name("decode-pstore.py"))
DECODER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DECODER)


def function(source, name):
    start = source.index("static ", source.index(name) - 32)
    end = source.index("\n}\n", start) + 3
    return source[start:end]


class SnapshotCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="ack-commit-test-")
        cls.folder = Path(cls.scratch.name)
        source = (ROOT / "fs/pstore/ram.c").read_text()
        start = source.index("struct ramoops_snap_header {")
        header = source[start:source.index("\n};", start) + 3]
        version = next(line for line in source.splitlines()
                       if line.startswith("#define RAMOOPS_SNAP_VERSION")) + "\n"
        init_header = function(source, "ramoops_snap_init_header(")
        commit = function(source, "ramoops_snap_commit(")
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint64_t __le64;
typedef uint32_t __le32;
#define PAGE_SIZE 4096
#define ALIGN(n, a) (((n) + (a) - 1) & ~((a) - 1))
#define cpu_to_le64(n) ((uint64_t)(n))
#define cpu_to_le32(n) ((uint32_t)(n))
#define le32_to_cpu(n) ((uint32_t)(n))
static unsigned long crc32_le(unsigned seed, const void *data, size_t len)
{ return crc32(seed ^ ~0U, data, len) ^ ~0U; }
static uint64_t ktime_get_ns(void) { return 1000000000; }
#define MAX_SLOT (PAGE_SIZE + 1048576)
static unsigned char volatile_bytes[MAX_SLOT], durable_bytes[MAX_SLOT];
static unsigned char staging[MAX_SLOT];
static size_t slot_bytes, largest_payload;
static int operation, fail_at;
struct block_device { int unused; };
struct ramoops_snapper { struct block_device *bdev; };
static int ramoops_snap_bio_write(struct block_device *bdev, void *data,
                                 size_t len, u64 offset)
{
    (void)bdev;
    assert(offset + len <= slot_bytes);
    assert(offset % PAGE_SIZE == 0 && len % PAGE_SIZE == 0);
    if (++operation == fail_at)
        return -EIO;
    if (offset == PAGE_SIZE)
        largest_payload = len;
    memcpy(volatile_bytes + offset, data, len);
    return 0;
}
static int blkdev_issue_flush(struct block_device *bdev)
{
    (void)bdev;
    if (++operation == fail_at)
        return -EIO;
    memcpy(durable_bytes, volatile_bytes, slot_bytes);
    return 0;
}
'''
        main = r'''
int main(int argc, char **argv)
{
    struct block_device disk;
    struct ramoops_snapper snapper = { .bdev = &disk };
    const uint64_t raw_magic = 0x52414d4f;
    const uint64_t tail_magic = 0x314c4941544b4341ULL;
    const char old_console[] = "old console\n";
    const char new_console[] = "new console\n";
    const int tail = argc > 2 && !strcmp(argv[2], "tail");
    const size_t actual = tail ? 13 : 1048576;
    const size_t console_offset = PAGE_SIZE + 0x77000;
    uint32_t ring[3];
    int ret;
    assert(argc >= 2);
    fail_at = atoi(argv[1]);
    slot_bytes = tail ? 0x20000 : MAX_SLOT;
    memset(staging, 0xa5, sizeof(staging));
    if (tail) {
        memcpy(staging + PAGE_SIZE, "periodic log\n", actual);
    } else {
        memset(staging + PAGE_SIZE, 0, actual);
        ring[0] = 0x43474244;
        ring[1] = ring[2] = sizeof(old_console) - 1;
        memcpy(staging + console_offset, ring, sizeof(ring));
        memcpy(staging + console_offset + sizeof(ring), old_console,
               sizeof(old_console) - 1);
    }
    ramoops_snap_init_header(staging, tail ? tail_magic : raw_magic, 1,
                             actual, tail ? 0 : 0x86800000, 0);
    memcpy(volatile_bytes, staging, slot_bytes);
    memcpy(durable_bytes, staging, slot_bytes);
    if (!tail) {
        memcpy(staging + console_offset + sizeof(ring), new_console,
               sizeof(new_console) - 1);
    }
    ramoops_snap_init_header(staging, tail ? tail_magic : raw_magic, 3,
                             actual, tail ? 0 : 0x86800000, 0);
    ret = ramoops_snap_commit(&snapper, staging, 0);
    assert(ret == (fail_at ? -EIO : 0));
    if (!fail_at && tail) {
        size_t index;
        assert(largest_payload == PAGE_SIZE);
        for (index = PAGE_SIZE + actual; index < 2 * PAGE_SIZE; index++)
            assert(durable_bytes[index] == 0);
    }
    assert(fwrite(durable_bytes, 1, slot_bytes, stdout) == slot_bytes);
    return 0;
}
'''
        unit = cls.folder / "commit.c"
        unit.write_text(harness + header + "\n" + version + init_header + commit + main)
        cls.binary = cls.folder / "commit"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        str(unit), "-lz", "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def image(self, failure, tail=False):
        args = [str(self.binary), str(failure)]
        if tail:
            args.append("tail")
        data = subprocess.run(args, capture_output=True, check=True).stdout
        blob = bytearray(DECODER.PARTITION_SIZE)
        offset = DECODER.TAIL_OFFSET if tail else DECODER.SNAPSHOT_OFFSET
        blob[offset:offset + len(data)] = data
        return blob

    def test_completed_raw_commit_is_decodable(self):
        report, files = DECODER.recover_logdump(self.image(0), "fixture", "check")
        slot = report["slots"][0]
        self.assertTrue(slot["header_valid"])
        self.assertTrue(slot["header_crc_valid"] and slot["payload_crc_valid"])
        self.assertEqual(slot["seq"], 3)
        self.assertEqual(files[slot["console"]["file"].removeprefix("check")],
                         b"new console\n")

    def test_failed_raw_commit_never_publishes_new_identity(self):
        for failure in range(1, 7):
            with self.subTest(failure=failure):
                report, files = DECODER.recover_logdump(
                    self.image(failure), "fixture", "check")
                slot = report["slots"][0]
                if failure <= 2:
                    self.assertTrue(slot["header_valid"])
                    self.assertEqual(slot["seq"], 1)
                    self.assertEqual(files[slot["console"]["file"].removeprefix("check")],
                                     b"old console\n")
                else:
                    self.assertFalse(slot["header_valid"])
                    self.assertNotIn("console", slot)

    def test_unaligned_text_is_padded_but_crc_covers_only_actual_bytes(self):
        report, files = DECODER.recover_logdump(self.image(0, True), "fixture", "check")
        slot = report["periodic_tail_slots"][0]
        self.assertTrue(slot["header_valid"])
        self.assertEqual(slot["payload_len"], 13)
        self.assertEqual(files[slot["tail"]["file"].removeprefix("check")],
                         b"periodic log\n")

    def test_failed_tail_commit_is_not_exported_as_new_sample(self):
        for failure in range(1, 7):
            with self.subTest(failure=failure):
                report, _ = DECODER.recover_logdump(
                    self.image(failure, True), "fixture", "check")
                slot = report["periodic_tail_slots"][0]
                if failure <= 2:
                    self.assertTrue(slot["header_valid"])
                    self.assertEqual(slot["seq"], 1)
                else:
                    self.assertFalse(slot["header_valid"])
                    self.assertNotIn("tail", slot)


if __name__ == "__main__":
    unittest.main()
