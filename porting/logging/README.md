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