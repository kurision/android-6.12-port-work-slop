# FastRPC: the CAF ioctl mismatch, measured from the shipped library

**Date:** 2026-10-18 · **Tree:** `ack-kgsl` (6.12.93) · **Device:** tissot, run237 port boot

## What this settles

`porting/TRACKER-kgsl-port.md`, "Correction: the CAF ioctl numbering does not
match mainline's at all", concluded that a CAF-built `adsprpcd` "will hit
`default: -ENOTTY` on its INIT, MMAP, MUNMAP, INVOKE and GETINFO regardless of
what this driver implements", and noted that nothing in the logs recorded which
`cmd` actually arrived.

That conclusion is now measured, from the binary the device actually runs, and
**it is wrong in a way that matters**: three of the vendor's commands do *not*
return `ENOTTY`. Their encoded value matches a command this driver implements,
so they are accepted and executed against the wrong handler with a differently
shaped payload. That is worse than a clean rejection.
## Method

`/vendor/lib64/libadsprpc.so` was pulled from the running device
(`artifacts/snapshot60/live-audit-run237-20261018T170301Z/vendor-libs/`, 268,776
bytes) and disassembled. The ioctl constants are not stored as contiguous 32-bit
literals — aarch64 materialises each `_IOC` value as a `MOV`/`MOVK` pair into a
scratch register — so they are recovered by pairing the two instructions and
keeping the `'R'`-typed results.

Reproduce with `porting/tools/fastrpc-ioctl-audit.py`:

```bash
python3 porting/tools/fastrpc-ioctl-audit.py libadsprpc.so \
        --header include/uapi/misc/fastrpc.h
```

## Result

Vendor library issues **19** distinct `'R'`-typed commands. This driver
implements **10**. Of the vendor's 19:

| vendor cmd | nr | payload | CAF meaning | this driver does |
|---|---|---|---|---|
| `0xc0105201` | 1 | 16 | INVOKE | **runs `ALLOC_DMA_BUFF`** |
| `0xc0205202` | 2 | 32 | MMAP | `-ENOTTY` |
| `0xc0105203` | 3 | 16 | MUNMAP | **runs `INVOKE`** |
| `0xc0185204` | 4 | 24 | INVOKE_FD | `-ENOTTY` |
| `0xc0045205` | 5 | 4 | SETMODE | `-ENOTTY` |
| `0xc0285206` | 6 | 40 | INIT | `-ENOTTY` |
| `0xc0205207` | 7 | 32 | INVOKE_ATTRS | `-ENOTTY` |
| `0xc0045208` | 8 | 4 | GETINFO | `-ENOTTY` |
| `0xc0185209` | 9 | 24 | GETPERF | `-ENOTTY` |
| `0xc030520a` | 10 | 48 | INIT_ATTRS | **runs `MEM_MAP`** |
| `0xc028520b` | 11 | 40 | INVOKE_CRC | `-ENOTTY` |
| `0xc00c520c` | 12 | 12 | CONTROL | `-ENOTTY` |
| `0xc018520d` | 13 | 24 | MUNMAP_FD | `-ENOTTY` |
| `0xc0205210` | 16 | 32 | GET_DSP_INFO | `-ENOTTY` |
| `0xc00c5211` | 17 | 12 | not in the donor header | `-ENOTTY` |
| `0xc0185212` | 18 | 24 | not in the donor header | `-ENOTTY` |
| `0xc0405213` | 19 | 64 | not in the donor header | `-ENOTTY` |
| `0xc0305214` | 20 | 48 | not in the donor header | `-ENOTTY` |
| `0xc0385215` | 21 | 56 | not in the donor header | `-ENOTTY` |

Three collisions, all with equal payload size, so nothing in the ABI encoding
distinguishes them: a CAF INVOKE is fed to `fastrpc_dmabuf_alloc()` as a CAF
`fastrpc_ioctl_invoke`, a CAF MUNMAP is fed to `fastrpc_invoke()`, and a CAF
INIT_ATTRS is fed to `fastrpc_req_mem_map()`. Each pair of structs has the same
total size but a different field layout, so the handlers read plausible-looking
nonsense: a buffer pointer where a handle should be, a handle where a length
should be.

This explains the failure mode better than a wall of `ENOTTY`: the observed log
is `apps_dev_init: failed to setup fastrpc session in kernel` → `open_dev (-1)
failed` → `remote_handle_open failed … (errno Inappropriate ioctl for device)`,
and the errno in that last message belongs to whichever call actually failed,
which is not necessarily the first unsupported one.

## Two further consequences

**The vendor userspace is newer than the donor kernel's header.** Numbers 17
through 21 appear in the binary but exist in no CAF header in `../oc-test`; the
donor stops at 16. Their payloads are 12, 24, 64, 48 and 56 bytes. Any CAF ABI
layer needs definitions and semantics for five commands that no reference in
these trees documents, so their behaviour has to come from the Qualcomm release
that introduced them.

**ioctl 12 alone is not merely insufficient, it is not first.** The staged patch
at `porting/staged/fastrpc-ioctl12-control.patch` implements CONTROL correctly,
but the commands `apps_dev_init` issues before it — INIT (nr 6), which is the
attach/create call — are rejected outright, and three earlier calls are
misinterpreted rather than rejected.

## What this implies for the fix

The shape is unchanged from the tracker's "CAF ABI translation layer", with one
correction: the three colliding commands are the dangerous ones. A layer that
only adds the missing numbers and leaves the collisions in place converts a
clean `-ENOTTY` into silent misinterpretation for exactly the calls that were
previously at least visibly rejected. Every CAF command the library can issue
has to be routed deliberately, including the three that currently "work".

Runtime confirmation is still wanted, because the table says what the library
*can* issue, not which it issues in a given `apps_dev_init` sequence. Commit
`a4e96d04a` (`fastrpc: log the ioctl commands userspace actually issues`) prints
each command number the first time it arrives, which one boot would settle.

Nothing here was built, booted or flashed; the library was read from the running
device and analysed on the host.

## Implemented on `fix/components`

Three commits, none of them device-tested:

| commit | what |
|---|---|
| `9462a5ba6` | handlers take their payload by value; the copies move to the dispatcher, so the compat layer can hand them kernel pointers |
| `6946bd9cf` | `FASTRPC_IOCTL_CONTROL`, the implementation that was staged unapplied |
| `3b8db6b5d` | the CAF layer itself: 19 commands decoded, CAF precedence over the three collisions, and the six commands that map onto something implemented here |

`INVOKE` converts CAF's 16-byte argument array into this driver's 24-byte form
(fd `-1`, no attributes, which is what a plain invoke means); `INIT` maps onto
attach, create, create-static or sensors-attach per its flags, carrying CAF's
name-in-`file` for a static PD; `MMAP`, `MUNMAP` and `GET_DSP_INFO` are
field-for-field with the remote address copied back. The remaining thirteen are
refused by number with a message naming the number, so a boot reports which ones
userspace actually reaches.

The build-time assertions double as the check on the layouts: each CAF struct
is asserted to encode to the exact command value recovered from the shipped
library, and they all hold. Re-derived independently on the host from the CAF
definitions alone, they reproduce the same 19 values. When the first version was
built, five assertions failed because one struct had been reused for commands
with different payload sizes — the check caught that before any device saw it.

**Not verified:** no image has been built or booted with this. Whether
`apps_dev_init` now completes, and whether it needs any of the thirteen refused
commands, is unknown until it runs.
