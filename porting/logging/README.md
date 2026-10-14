# Logging during the port

A port that hangs is the normal case, not the exception. This is where logs come
from on this device, in the order you should reach for them.

## The four sources

| Source | Survives a crash? | Survives reboot? | What you get | Access |
|---|---|---|---|---|
| **UART console** (`/dev/ttyMSM0`, `qcom,msm-uartdm-v1.4` @0x78af000) | yes, if a cable is attached | n/a | everything from the first `printk`, including earlycon | test points on the board + a 3.3 V USB-TTL cable |
| **pstore / ramoops** (`/sys/fs/pstore`) | yes | **yes** | the tail of the log from the failed boot, plus function-graph trace if enabled | root only |
| **journald** (`journalctl`) | no | yes (per boot) | userspace: init, services, HALs | `journalctl -b`, `journalctl --list-boots` |
| **dmesg** | no | no | current boot's ring buffer | unprivileged |

Current state on the device (verified over ssh):

* `/sys/fs/pstore/` is mounted and **empty** — no crashes recorded yet.
* `ramoops-1` is registered as a console (`/proc/consoles`), so anything printed
  before the panic is already landing there.
* `systemd-pstore.service` is **enabled**, so the next boot archives any pstore
  record into the journal automatically.
* Kernel cmdline is `quiet loglevel=2` and `/proc/sys/kernel/printk` is
  `2 4 1 7` — the console is deliberately quiet. **That is the first thing to
  change when you are debugging.**
* No `console=` on the cmdline, so **no serial console** is registered even
  though `/dev/ttyMSM0` exists.

## Configure this in your port

Kernel command line (via lk2nd / U-Boot / the bootloader):

```
console=ttyMSM0,115200n8 earlycon=msm_serial_dm,0x78af000,115200n8 loglevel=7 ignore_loglevel
```

* `earlycon=msm_serial_dm` is valid for this board: upstream `msm_serial.c`
  declares `OF_EARLYCON_DECLARE(msm_serial_dm, "qcom,msm-uartdm", …)` and the
  node's second compatible is exactly `qcom,msm-uartdm`.
* Drop `ignore_loglevel` once things work; it floods.

Runtime:

```sh
sysctl -w kernel.printk=7 4 1 7      # unquiet without rebooting
echo 1 > /proc/sys/kernel/printk_devkmsg
```

Ramoops node — keep it, and grow the function trace:

```dts
ramoops@9ff00000 {
        compatible = "ramoops";
        reg = <0x0 0x9ff00000 0x0 0x100000>;   /* 1 MiB, matches this device */
        record-size = <0x1000>;                /* 4 KiB pmsg */
        console-size = <0x80000>;              /* 512 KiB dmesg */
        ftrace-size  = <0x10000>;              /* was 0x1000 (4 KiB) */
        pmsg-size    = <0x8000>;
};
```

Config symbols the reference kernel has: `CONFIG_PSTORE=y`,
`CONFIG_PSTORE_RAM=y`, `CONFIG_PSTORE_COMPRESS=y` (deflate — **the stored blobs
are zlib-compressed, see `decode-pstore.py`**), `CONFIG_PSTORE_CONSOLE=y`,
`CONFIG_PSTORE_PMSG=y`, `CONFIG_LOG_BUF_SHIFT=17`.

Not set on the reference kernel: `CONFIG_PSTORE_FTRACE`. Without it `ftrace-size`
is dead weight; with it you get a function graph across the crash boundary, which
is the single most useful feature when a port hangs mid-probe.

## Workflow

```sh
cd ../logging

# from this machine: run the collector on the phone and pull the result
./pull-logs.sh                      # -> ./logs/<date-time>/

# or, on the phone directly (needs root for pstore)
doas sh collect-logs.sh /tmp/port-logs.tar

# decode a stored pstore record
python3 decode-pstore.py /path/to/pstore/dmesg-ramoops-0
```

`pull-logs.sh` writes a dated directory under `logs/` containing `pstore/`
(decompressed where possible), `dmesg.txt`, `journal*.txt`, `sysfs/` state
snapshots and `meta.txt`. Keep one directory per boot attempt; they are small
(a few hundred KiB) and are the only record of a failed boot.

## What to do with a pstore record

1. `dmesg-ramoops-0` is the compressed ring buffer of the failed boot — the
   timestamped tail is at the end, so read the **last** lines first.
2. If the log stops mid-probe (no panic line), suspect a probe that never
   returned rather than a crash: compare with the working
   `artifacts/dmesg-live.txt` and look for the last subsystem that logged.
3. If it ends in `Unable to handle kernel ...` / `Call trace`, the top frame
   names the driver; check whether that driver's DT node exists in your port.
4. `pstore_ftrace-*` entries (only with `CONFIG_PSTORE_FTRACE`) are also
   deflate-compressed and contain a function graph — decode them the same way.

## Android temporary-boot evidence

From `porting/artifacts/snapshot<number>`, run
`ADB_SERIAL=2819f2320604 ../../logging/pull-run-evidence.sh <run> boot.img`
after the installed ROM returns. The collector refuses existing run outputs
before touching the phone. It retains exact 64MiB `runN-logdump.bin`, decodes
only the text prefix before NUL/60MiB, and exports validated ramoops snapshots,
genuine dmesg records and periodic printk tails with a `runN-ramoops.json`
provenance report. Failed pulls and stderr remain in the unique host scratch
directory.
Transport requires `shell_v2` and uses `adb shell -T`, preserving binary stdout,
separate stderr and remote exit status. `exec-out` merges stderr and loses remote
status ([ADB shell service](https://android.googlesource.com/platform/system/adb/+/master/shell_service.cpp?format=HTML));
transfer statistics must not be truncated off to pass the exact-size gate.

SD discovery requires an unambiguous card with sysfs type `SD` and a vfat first
partition. Only `ack-kmsg.log` is read; any mount created by the collector is
read-only and unmounted by its root shell. Error stdout is not a kernel log.
Format-valid SD is named `runN-sd.log` only when its common raw-text extent
matches and contains the capture header, kernel banner and a kmsg record;
otherwise it is `runN-sd-unverified.log`. Streams are never merged.
USB capture remains independent; give `usb-boot-capture.py` an explicit status
path in build scratch, not the snapshot folder. Retain prior raw/SD evidence
before clearing logdump or booting again.

Run the isolated collector regression with
`python3 porting/logging/test_pull_run_evidence.py`; it never contacts a phone.

`python3 -B porting/logging/test_ramoops_witness_open.py` compiles and runs
the real witness-open function with host-side allocation failure injection.
It checks retry cleanup and cached success without contacting hardware.
Git retains only snapshot43 run-10/run-11 capture evidence; older logs stay
ignored locally. Raw capture bytes are not whitespace-normalized.

`package-diag-boot.py --base-image IMG --kernel-dir DIR --init BIN --out OUT
--report JSON` builds a RAM-boot image from a base boot image: new kernel,
only the ramdisk `init` record replaced, cmdline console set to `ttynull`. It
asserts every other cpio record and header byte is unchanged.

Since snapshot45 qseecom writes one FUA record per SMC send/return and listener
wake/response to a 128-slot ring at logdump offset 0x3f10000.
`python3 porting/logging/decode-qsee-trace.py runN-logdump.bin` prints the
records by boot and seq, then a `LAST=` line naming where the run died.

## Tissot reset persistence after run106

The port reserves 1 MiB at `0x86800000`; stock 4.19 uses 4 MiB at
`0x91400000`. Stock's `/sys/fs/pstore` therefore does not expose the port's
reservation. Do not relocate ramoops into the stock range: it overlaps this
tree's Venus reservation. Recover committed samples from logdump instead:

```sh
python3 porting/logging/decode-pstore.py \
  --logdump run106-logdump.bin --output-prefix /existing/scratch/run106
```

Outputs refuse overwrites, including dangling symlinks. Each console/dmesg
filename identifies its slot, sequence and sample uptime; `-ramoops.json`
records validation and provenance. Legacy version0 slots remain explicitly
integrity/freshness-unverified. Run106 recovers console samples at 127.977 and
125.910 s but no valid dmesg panic/oops record.

### Ownership and next build

`pstore_blk` previously passed a literal `PARTLABEL=logdump` to `filp_open()`
when early resolution missed late MMC enumeration. Built-in pstore-blk now
resolves GPT labels at every open attempt, retries only ENOENT/ENODEV, and
preserves exclusive ownership. Retry attachment no longer emits a synthetic
panic dump.

This does **not** make the generic best-effort backend panic-safe: it has no
`panic_write`, and pstore permits only one backend. Diagnostic ramoops already
owns logdump; opening it for a second pstore layout must fail, not share bytes.
For the next image retain ramoops, remove all four inherited pstore-blk tokens,
and keep `ramoops.reset_capture=1`. With `package-diag-boot.py` and run105's
base image, use:

```sh
--drop-cmdline pstore_blk.blkdev=PARTLABEL=logdump \
--drop-cmdline pstore_blk.best_effort=1 \
--drop-cmdline pstore_blk.kmsg_size=32768 \
--drop-cmdline pstore_blk.pmsg_size=32768 \
--append-cmdline pstore.backend=ramoops
```

Size parameters are KiB, not bytes. Do not enable a whole-partition pstore-blk
layout over the diagnostic text/snapshot/witness/QSEE/reset ranges.

Rebuild **both kernel and DTB on Linux**, using the existing `out/.config` and
working toolchain. Run123 omitted Rust/ashmem; enable the existing driver
without replacing the rest of that run's config, and refuse an image if
Kconfig drops it again (commands below use Bash):

```sh
rust_make=(make O=out ARCH=arm64 LLVM=1
  RUSTC="${RUSTC:-rustc}" HOSTRUSTC="${HOSTRUSTC:-${RUSTC:-rustc}}"
  BINDGEN="${BINDGEN:-bindgen}")
"${rust_make[@]}" rustavailable || exit 1
scripts/config --file out/.config -e STAGING -e SHMEM -e RUST -e ASHMEM -e COMPAT
"${rust_make[@]}" olddefconfig || exit 1
for sym in RUST_IS_AVAILABLE RUST ASHMEM; do
  grep -qx "CONFIG_${sym}=y" out/.config || {
    echo "Missing built-in CONFIG_${sym}; do not package this image" >&2
    exit 1
  }
done
"${rust_make[@]}" Image.gz qcom/msm8953-xiaomi-tissot.dtb
```

On Fedora, install missing prerequisites with
`sudo dnf install rust rust-src bindgen-cli clang-libs`; for rustup, add
`rust-src` to the selected compiler's toolchain. `RUST_LIB_SRC` must point
to matching Rust library sources, and bindgen may require `LIBCLANG_PATH`.
See the [upstream Rust quick start](https://docs.kernel.org/6.16/rust/quick-start.html).
The normal `scripts/build-ack-tissot.sh` entrypoint now checks the same
availability and required built-ins before compiling.

`PSTORE_RAM` now selects CRC32 when BLOCK is enabled; run105 already has
`CONFIG_CRC32=y`. The DT adds `max-reason = <4>` for genuine emergency and
shutdown RAM dumps. Rebuild diagnostic init on the Mac:

```sh
zig cc -target aarch64-linux-musl -Os -static \
  -DANDROID_CAPTURE -DANDROID_EARLY_LOGCAT -DBOOT_DEADLINE_SECONDS=0 \
  scripts/initramfs-diag/init.c -o /tmp/ack-init-reset-logging
```

The headless, HAL and display reset-test service gates have been removed.
Rebuild diagnostic init; do not reuse `init-run110` or another gated binary.
Gatekeeper, composer, display-color, SurfaceFlinger and LiveDisplay must use
their original service definitions. Diagnostic capture, storage protections
and the read-only USB controller property correction remain enabled.

### Committed disk layout

Ranges are half-open. The userspace text writer is capped at 60 MiB so it
cannot overwrite reserved diagnostics; USB and optional SD mirrors are not
capped.

| Region | Start | End |
|---|---:|---:|
| Text prefix | `0` | `0x3c00000` |
| Two raw RAM slots, each 4 KiB header + 1 MiB payload | `0x3c00000` | `0x3e02000` |
| Two periodic printk slots, each 128 KiB | `0x3e02000` | `0x3e42000` |
| Stall witness | `0x3f00000` | `0x3f00200` |
| QSEE ring | `0x3f10000` | `0x3f20000` |
| Orderly reset capture | `0x3f30000` | `0x3f40000` |

MDSS re-probe markers (run117+) live in 4K carved from the ramoops
dmesg area (payload offset `0x76000`, 118 dmesg zones remain; last 8
bytes = `MARK` magic + boot id). Each 2 s snapshot copies the page, and
`decode-pstore.py` prints it as `diag marks boot_id=...`. Match the
boot id against that boot's `DIAG mark boot_id` line. `DIAG mark prev`
at the next port boot is best-effort only: after a silent reset the
phone boots stock, which does not reserve `0x86800000`.

Version1 preserves the 64-byte little-endian `<QQQQ8I>` header. Reserved words
at 48/52/56/60 contain version1, payload CRC32, header CRC32, zero. Header CRC
covers those 64 bytes with its own word zeroed; payload CRC covers actual
payload bytes, not block padding. The writer invalidates and flushes the target
header, writes and flushes payload, then publishes and flushes the CRC header.
Every write/flush error stops sampling rather than claiming durability.

Periodic tails capture the live printk buffer independently of the ramoops
console and export as `-printk-tail-...-periodic-printk.log`. They are **not**
panic dumps or ACKRESET1 records. CRCs verify stored bytes, not boot identity
or coherent atomic sampling of a concurrently updated RAM ring.

### Verification and limits

Host regressions execute the real C header/commit functions against a
volatile/durable storage model, inject all six write/flush failures, verify
decoder compatibility and 4 KiB padding, and exercise corrupt/torn records.
The ARM64 init prefix selftest checks exact boundary preservation, partial
writes, unchanged budget on failed writes, and continued mirror capture:

```sh
python3 -m unittest discover -s porting/logging -p 'test_*.py'
python3 porting/logging/test_pull_run_evidence.py
python3 porting/logging/test_decode_reset.py
python3 porting/logging/test_ramoops_witness_open.py
zig cc -target aarch64-linux-musl -Os -static \
  -DANDROID_CAPTURE -DANDROID_RAMOOPS_TEST \
  scripts/initramfs-diag/init.c -o /tmp/ack-prefix-selftest
# Push to an Android ARM64 target and execute: ack-prefix-selftest --prefix-only
```

Observed: 41 discovered tests pass; collector, five reset-decoder tests and
witness-open harness pass. Prefix selftest passes on both the Android ARM64
emulator and physical Tissot under stock 4.19.

Run107 exercised the Linux-built `be63c5ea5` kernel/DTB on Tissot with a
45-second diagnostic reboot deadline. Snapshot readiness and reset-capture
arming were observed. After stock returned, both raw console snapshots and
both periodic tails passed header/payload CRC32 validation; ACKRESET1 retained
64926 bytes, and USB recorded the successful reset-capture flush.
See `../TRACKER-kgsl-port.md`, "Run107", for exact image and record provenance.
This validates the orderly path, not spontaneous-reset or panic durability.

Never use a fabricated panic to prove attachment. ACKRESET1 applies only to
blocking orderly reboot/halt/poweroff, before MMC shutdown. Hardware watchdog,
firmware reset, panic or power loss may omit it. Process-context periodic disk
samples cannot guarantee the final unwritten panic/SEA lines; no sleeping
block I/O is added to panic or IRQ-disabled paths.

Relevant kernel contracts:
[pstore-blk driver and panic_write](https://docs.kernel.org/admin-guide/pstore-blk.html),
[ramoops persistence](https://docs.kernel.org/admin-guide/ramoops.html).
