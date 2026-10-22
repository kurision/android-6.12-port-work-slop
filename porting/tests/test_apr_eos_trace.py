#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile and exercise the production APR EOS tracer without a kernel build."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MSM = ROOT / "sound/soc/msm"


class AprEosTrace(unittest.TestCase):
    def test_packet_bounds_and_filtering(self):
        source = (MSM / "apr_tal_rpmsg.c").read_text()
        helper = re.search(r"static void apr_tal_trace_eos\(.*?^\}",
                           source, re.M | re.S)[0]
        apr = (MSM / "caf-include/ipc/apr.h").read_text()
        audio = (MSM / "caf-include/dsp/apr_audio-v2.h").read_text()
        header = re.search(r"struct apr_hdr \{.*?^\};", apr, re.M | re.S)[0]
        constants = "\n".join(re.findall(
            r"^#define (?:APR_BASIC_RSP_RESULT|ASM_DATA_CMD_EOS|"
            r"ASM_DATA_EVENT_EOS|ASM_DATA_EVENT_RENDERED_EOS)\s+\S+",
            apr + audio, re.M))
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint8_t u8;
static unsigned int logs;
static char last[512];
#define pr_info_ratelimited(...) \
    do { logs++; snprintf(last, sizeof(last), __VA_ARGS__); } while (0)
'''
        cases = r'''
/* Use an allocation of exactly len bytes to expose reads past the wire data. */
static void check(const struct apr_hdr *hdr, const u32 *payload,
                  int len, unsigned int expected)
{
    unsigned int before = logs;
    size_t size = len > 0 ? (size_t)len : 0;
    unsigned char *storage = malloc(size + 1);
    unsigned char *data = storage + 1; /* Deliberately unaligned. */
    assert(storage);
    memcpy(data, hdr, size < sizeof(*hdr) ? size : sizeof(*hdr));
    if (size > sizeof(*hdr))
        memcpy(data + sizeof(*hdr), payload, size - sizeof(*hdr));
    apr_tal_trace_eos("RX", data, len, 0);
    assert(logs == before + expected);
    free(storage);
}

int main(void)
{
    struct apr_hdr hdr = {
        .hdr_field = 5 << 4, .pkt_size = sizeof(hdr),
        .src_domain = 4, .src_svc = 7, .src_port = 0x101,
        .dest_domain = 5, .dest_svc = 7, .dest_port = 0x102,
        .token = 0x2000100, .opcode = ASM_DATA_EVENT_EOS,
    };
    u32 response[] = { ASM_DATA_CMD_EOS, 0x42, 0 };
    int len;

    apr_tal_trace_eos("RX", NULL, 20, 0);
    assert(logs == 0);
    for (len = -1; len < (int)sizeof(hdr); len++)
        check(&hdr, response, len, 0);
    check(&hdr, response, sizeof(hdr), 1);
    assert(strstr(last, "RX ret=0 len=20 hdr=20 pkt=20"));
    assert(strstr(last, "src=4:7:0x101 dest=5:7:0x102"));
    assert(strstr(last, "token=0x2000100 opcode=0x10bdd"));
    hdr.opcode = ASM_DATA_EVENT_RENDERED_EOS;
    check(&hdr, response, 20, 1);
    hdr.opcode = ASM_DATA_CMD_EOS;
    check(&hdr, response, 20, 1);
    apr_tal_trace_eos("TX", &hdr, sizeof(hdr), -11);
    assert(strstr(last, "TX ret=-11"));

    hdr.pkt_size = 21;
    check(&hdr, response, 20, 0);
    hdr.pkt_size = 19;
    check(&hdr, response, 20, 0);
    hdr.pkt_size = 20;
    hdr.hdr_field = 4 << 4;
    check(&hdr, response, 20, 0);
    hdr.hdr_field = 6 << 4;
    check(&hdr, response, 20, 0);
    hdr.hdr_field = 5 << 4;
    hdr.opcode = 0x12345678;
    check(&hdr, response, 20, 0);

    hdr.opcode = APR_BASIC_RSP_RESULT;
    for (len = 20; len < 28; len++) {
        hdr.pkt_size = len;
        check(&hdr, response, len, 0);
    }
    hdr.pkt_size = 28;
    check(&hdr, response, 28, 1);
    assert(strstr(last, "opcode=0x110e8 status=0x42"));
    response[0] = 0x12345678;
    check(&hdr, response, 28, 0);

    /* An extended header places the response after an extra header word. */
    hdr.hdr_field = 6 << 4;
    hdr.pkt_size = 32;
    response[1] = ASM_DATA_CMD_EOS;
    response[2] = 0x99;
    check(&hdr, response, 32, 1);
    assert(strstr(last, "hdr=24 pkt=32"));
    assert(strstr(last, "status=0x99"));
    return 0;
}
'''
        compilers = [name for name in ("gcc", "clang") if shutil.which(name)]
        self.assertTrue(compilers, "A host C compiler is required")
        with tempfile.TemporaryDirectory(prefix="apr-eos-test-") as tmp:
            src = Path(tmp) / "trace.c"
            exe = Path(tmp) / "trace"
            src.write_text("\n".join((harness, header, constants, helper, cases)))
            for compiler in compilers:
                with self.subTest(compiler=compiler):
                    subprocess.run([
                        compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-g", str(src),
                        "-o", str(exe),
                    ], check=True, capture_output=True, text=True)
                    # LeakSanitizer cannot run under a ptraced sandbox.
                    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                               UBSAN_OPTIONS="halt_on_error=1")
                    result = subprocess.run([str(exe)], env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
