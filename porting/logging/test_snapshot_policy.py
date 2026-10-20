#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the real snapshot worker with mocked waits and block writes."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RAM = ROOT / "fs/pstore/ram.c"

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define PAGE_SIZE 4096
#define SZ_1M (1024 * 1024)
#define RAMOOPS_PATH_MAGIC 1
#define RAMOOPS_PATH_OFFSET 2
#define RAMOOPS_RAW_PHYS 3
#define RAMOOPS_RAW_DMESG_CNT 4
#define SZ_4K 4096
#define RAMOOPS_SNAP_INTERVAL_MS 2000
#define RAMOOPS_SNAP_FAST_MS 200
#define RAMOOPS_SNAP_MAX_FAILURES 10
#define RAMOOPS_SNAP_OFFSET 0
#define RAMOOPS_SNAP_SLOTS 2
#define RAMOOPS_SNAP_VERSION 1
#define RAMOOPS_TAIL_OFFSET 0
#define smp_load_acquire(p) (*(p))
#define msecs_to_jiffies(ms) (ms)
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)

struct completion { int unused; };
struct ramoops_snapper {
    void *file;
    char *buf;
    void *tail_buf;
    struct completion wake;
    unsigned long long seq;
    unsigned int failures;
    bool warned;
};
static char buffer[8192], ramoops_reset_previous[4096];
static struct ramoops_snapper ramoops_snapper;
static bool ramoops_reset_capture = true, ramoops_snap_fast = true;
static bool stopped, stop_on_request;
static unsigned int waits, snapshots, previous_commits, watchdog_reads;
static unsigned int requests, failed_snapshots;

static bool kthread_should_stop(void) { return stopped; }
static int ramoops_snap_open_logdump(struct ramoops_snapper *s)
{
    s->file = buffer;
    return 0;
}
static int wait_for_completion_interruptible_timeout(struct completion *c, int ms)
{
    (void)c;
    assert(ms == RAMOOPS_SNAP_INTERVAL_MS);
    if (waits++ > 8) {
        stopped = true;
        return 0;
    }
    if (requests) {
        requests--;
        if (stop_on_request)
            stopped = true;
        return 1;
    }
    return 0;
}
static void ramoops_snap_init_header(void *buf, unsigned long magic,
        unsigned long seq, unsigned long len, unsigned long phys, unsigned int slot)
{
    (void)buf; (void)magic; (void)seq; (void)len; (void)phys; (void)slot;
}
static int ramoops_snap_commit(struct ramoops_snapper *s, void *buf,
        unsigned long offset)
{
    (void)s; (void)buf; (void)offset;
    previous_commits++;
    return 0;
}
static int ramoops_snap_take(struct ramoops_snapper *s)
{
    snapshots++;
    s->seq++;
    if (failed_snapshots) {
        failed_snapshots--;
        return -5;
    }
    return 0;
}
static void ramoops_debug_apps_wdt(void) { watchdog_reads++; }
"""

CHECKS = r"""
static void check(unsigned int pending, unsigned int failures, bool stop,
        unsigned int expected)
{
    memset(&ramoops_snapper, 0, sizeof(ramoops_snapper));
    ramoops_snapper.buf = buffer;
    stopped = false;
    stop_on_request = stop;
    waits = snapshots = previous_commits = watchdog_reads = 0;
    requests = pending;
    failed_snapshots = failures;
    assert(ramoops_snap_thread(NULL) == 0);
    assert(snapshots == expected);
    assert(previous_commits == 1);
    assert(watchdog_reads == 0);
    assert(waits < 12);
}
int main(void)
{
    check(0, 0, false, 0); /* Timeouts must not write periodic snapshots. */
    check(1, 0, false, 1); /* Explicit panic wake still captures once. */
    check(1, 1, false, 2); /* A transient failure keeps the panic retry. */
    check(2, 1, false, 3); /* A later explicit request can capture again. */
    check(1, 11, false, 11); /* Permanent failures must remain bounded. */
    check(1, 0, true, 0);  /* Stopping the worker must not write a sample. */
    return 0;
}
"""


class SnapshotPolicyTests(unittest.TestCase):
    def test_gpu_heartbeat_blocks_are_commented_out(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler)
        names = {
            "adreno-zap-compat.h": ["ramoops_stage_write(stage"],
            "kgsl.c": ['"DIAG submit '],
            "kgsl_timeline.c": ['"DIAG timeline_signal ', '"DIAG timeline_fence '],
            "kgsl_sync.c": ['"DIAG sync_fence_event ', '"DIAG sync_timeline_signal '],
            "kgsl_events.c": ['"DIAG event_group '],
            "kgsl_pwrctrl.c": ['"DIAG gpu_state '],
            "adreno_dispatch.c": ['"DIAG dispatcher_timers '],
            "adreno_a5xx.c": ['"DIAG ME_INIT submit:'],
        }
        for filename, messages in names.items():
            with self.subTest(file=filename):
                text = (ROOT / "drivers/gpu/msm" / filename).read_text()
                # Preserve only the #if 0 regions and their non-directive text.
                # Host cpp checks those real guards without kernel headers.
                lines = []
                inside = False
                for line in text.splitlines():
                    if line.startswith("#if 0"):
                        inside = True
                        lines.append(line)
                    elif inside:
                        lines.append(line)
                        if line.startswith("#endif"):
                            inside = False
                commented = "\n".join(lines) + "\n"
                for message in messages:
                    self.assertIn(message, commented)
                active = subprocess.run([compiler, "-E", "-P", "-x", "c", "-"],
                                        input=commented, text=True,
                                        capture_output=True, check=True).stdout
                self.assertFalse(active.strip())

    def test_explicit_panic_and_reset_capture_remain(self):
        source = RAM.read_text()
        start = source.index("void ramoops_panic_snapshot(void)")
        end = source.index("static int ramoops_reset_notify", start)
        self.assertIn("complete(&s->wake)", source[start:end])
        self.assertIn("register_reboot_notifier(&s->reset_nb)", source)
        self.assertIn("wake_up_process(s->task)", source)

    def test_worker_is_panic_only(self):
        source = RAM.read_text()
        policy = re.search(r"^#define RAMOOPS_PERIODIC_SNAPSHOTS\s+\d+",
                           source, re.M)[0]
        start = source.index("static int ramoops_snap_thread(void *unused)")
        end = source.index("\n/*\n * Stall witness", start)
        program = STUBS + "\n" + policy + "\n" + source[start:end] + CHECKS
        compilers = [c for c in ("cc", "clang") if shutil.which(c)]
        self.assertTrue(compilers, "a host C compiler is required")
        with tempfile.TemporaryDirectory(prefix="snapshot-policy-",
                                         dir="/tmp/opencode") as tmp:
            path = Path(tmp) / "check.c"
            binary = Path(tmp) / "check"
            path.write_text(program)
            for compiler in compilers:
                with self.subTest(compiler=compiler):
                    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra",
                                    "-Werror", str(path), "-o", str(binary)],
                                   check=True, capture_output=True)
                    subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
