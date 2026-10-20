# FastRPC: what the vendor adsprpcd actually asks for, measured on the phone

**Date:** 2026-10-20 · **Tree:** `ack-kgsl` (6.12.93) · **Device:** tissot,
run294 on the phone since 12:08

## What it settles

The `adsprpcd` restart loop on the running phone is the CAF ioctl mismatch
that [2026-10-18-fastrpc-abi-measured.md](2026-10-18-fastrpc-abi-measured.md)
measured, and the port's CAF layer **is** in the running kernel. One command
of that layer is still refused, and it is the only command the library
needs.

This records which command it is, what it carries, what the port has to
answer, and what the library will ask for next.

## The evidence: the logdump partition

The full boot log is in the `logdump` partition, and the kernel logs every
ioctl number the first time it arrives (`fastrpc: log the ioctl commands
userspace actually issues`).

```
qcom,fastrpc remoteproc0:smd-edge.fastrpcsmd-apps-dsp.-1.-1: ioctl nr 8, cmd 0xc0045208, 4-byte payload
qcom,fastrpc remoteproc0:smd-edge.fastrpcsmd-apps-dsp.-1.-1: CAF ioctl 8 is not implemented   (x60)
```

One line of trace, and the only refusal in the whole log. **The library
issues exactly one command in this path**: number 8, `cmd 0xc0045208`, four
bytes of payload.

The port's CAF table encodes that command as
`CAF_IOCTL_GETINFO = _IOWR('R', 8, __u32) = 0xc0045208`, with a static
assert on the value, so the encoding matches the library byte for byte.
What is missing is the handler.

## The errno says which layer answered

The library's message on the phone is:

```
adsprpcd: vendor/qcom/proprietary/adsprpc/src/fastrpc_apps_user.c:1348:
  Error 0xffffffff: remote_handle_open failed for adsp_default_listener
  (errno Operation not supported on transport endpoint)
```

On this ROM, `EOPNOTSUPP` is "Operation not supported on transport
endpoint" and `ENOTTY` is "Inappropriate ioctl for device" — `stty` on a
non-tty prints the latter, and the ROM's `libc.so` carries both strings.

The port answers a CAF command it recognises but does not implement with
`-EOPNOTSUPP`, and an ioctl it does not recognise at all with `-ENOTTY`.
So this message says the CAF table **recognised** the command and refused
it: the layer is in the kernel and is doing its job.

The 2026-10-18 finding quotes the same line with "Inappropriate ioctl for
device". That is `ENOTTY`, the errno from *before* the CAF layer landed,
when the command was not recognised at all. The errno moved when the layer
landed; the command is still missing.

## What the command carries

`/vendor/lib64/libadsprpc.so` (268,776 bytes) was pulled from the phone and
disassembled. The ioctl constants are not contiguous literals — aarch64
materialises each `_IOC` value as a `MOV`/`MOVK` pair — so they are
recovered by pairing the two instructions.

The GETINFO call site:

```
1c6c0:  mov  w1, #0x5208
1c6c4:  add  x2, sp, #0xc          ; the payload
1c6c8:  movk w1, #0xc004, lsl #16
1c6cc:  mov  w0, w20               ; the fd
1c6d0:  bl   ioctl
```

and, a little earlier, the store that fills the payload:

```
1c5c8:  mov  w9, #0x220            ; 544 bytes per entry
1c5d0:  umaddl x8, w19, w9, x8     ; &table[w19]
1c5d4:  ldr  w20, [x8, #0x84]      ; the fd of that entry
1c5dc:  str  w19, [sp, #0xc]       ; the payload is w19
```

`w19` indexes the per-domain table, and the fd comes from that entry, so
**the payload is the domain id**. The library opens the device first — the
`fd == -1` path at `1c5e4` — and issues GETINFO immediately afterwards.

The CAF kernel's own semantics for the same command, from the donor
(`oc-test/drivers/char/adsprpc.c`, `fastrpc_get_info()`), are the same
shape: the input is the channel id (`cid`), the session for that channel is
allocated, and the output is whether that session's SMMU is enabled.

So the port's handler — input = channel id, 0 = ADSP/apps, 2 = SDSP/sensors,
attach to that process domain, output = 1 — is the right shape, and the
library asks for domain 0.

## The command the library asks for next

Right after a successful GETINFO the library branches into its attribute
query:

```
1c604:  mov  w1, #0x5211
1c608:  mov  x2, sp
1c60c:  movk w1, #0xc00c, lsl #16  ; 0xc00c5211
1c614:  bl   ioctl
```

That is CAF ioctl **17**, twelve bytes, and the payload is
`{domain, attribute}` with the value read back from offset 8 of the same
twelve bytes (`ldr w8, [sp, #0x8]`). The port already recognises the
command — it is in the CAF table as `CAF_IOCTL_UNKNOWN_17`, with the same
`0xc00c5211` value asserted — and refuses it.

**The GETINFO handler is necessary and not sufficient.** The next boot will
log `CAF ioctl 17 is not implemented`, and the library will be asking for
attribute 257.

The library tolerates the failure for attributes 22 and 25 (it sets a flag
and carries on), and reports it for anything else, which is why the phone
says "failed to get attribute 257 for domain 0".

## The header that answers it

CAF's 2022 and later `adsprpc_shared.h` has the command, and the attribute
with it. The donor's copy is the 2020 one and stops at number 16; the
newer header is in the public CAF trees, and it is a different numbering
for the same driver:

```c
#define FASTRPC_IOCTL_GET_DSP_INFO \
		_IOWR('R', 17, struct fastrpc_ioctl_capability)

struct fastrpc_ioctl_capability {
	uint32_t domain;
	uint32_t attribute_ID;
	uint32_t capability;
};

#define FASTRPC_MAX_DSP_ATTRIBUTES	(256)
#define FASTRPC_MAX_ATTRIBUTES		(258)
```

So **number 17 is `GET_DSP_INFO`**: one attribute, the domain, the
attribute id, and the capability the kernel answers with. The ids below
256 are the DSP's own attributes and are answered by querying the DSP; the
ids above it are the kernel's own capabilities, and CAF answers them from
a table rather than from the DSP:

```c
#define PERF_CAPABILITY_SUPPORT	(1 << 1)
#define KERNEL_ERROR_CODE_V1_SUPPORT	1
#define USERSPACE_ALLOCATION_SUPPORT	1
#define DSPSIGNAL_SUPPORT		1

static uint32_t kernel_capabilities[FASTRPC_MAX_ATTRIBUTES -
					FASTRPC_MAX_DSP_ATTRIBUTES] = {
	PERF_CAPABILITY_SUPPORT,	/* 256 */
	KERNEL_ERROR_CODE_V1_SUPPORT,	/* 257 */
	USERSPACE_ALLOCATION_SUPPORT,	/* 258 */
	DSPSIGNAL_SUPPORT		/* 259 */
};
```

**Attribute 257 is "the driver has the second generation of the error
codes".** The port's own file already had the command as an unknown
twelve byte payload, and the value it builds — `0xc00c5211` — is this
command's encoding, byte for byte.

The disassembly of the shipped library agrees with the header in every
detail, and it also says what the library does with the answer:

* the payload is `{domain, attribute}` and the value comes back at offset
  8, which is this struct's third field;
* the answer is cached in a global that is initialised to `-1`, and every
  API entry point queries it once, on first use, and then reads the
  cached value — so the library asks once per process, not once per call;
* the library also asks for attributes 256 and 128, and compares both
  answers with `2`, which is `PERF_CAPABILITY_SUPPORT`.

## What the port answers, and why

The implementation is staged, not in the tree, so that the next boot
tests the `GETINFO` fix alone:
`porting/staged/fastrpc-ioctl17-get-dsp-info.patch`.

| attribute | the port's answer | why |
|---|---|---|
| 256, perf | 0 | CAF's value is a bit mask and the client compares it with 2, CAF's second generation of the perf counters. This driver has upstream's perf counters, and answering 2 would send the client down an invoke path this driver does not have. |
| 257, error codes | 1 | The driver does not translate the DSP's errors: the invoke returns the DSP's own value, here and in the donor, so the client sees the DSP's error. The DSP is the ROM's own firmware and the ROM's own driver answers 1 for it, so the client is told what it is told on the ROM it ships with. |
| 258, userspace allocation | 1 | The userspace allocates the memory the DSP asks for. This driver has `FASTRPC_IOCTL_ALLOC_DMA_BUFF` for that, and its CAF control answers `kalloc_support` with 1. |
| 259, signalling | 0 | CAF's lightweight driver based signalling, the `dspsignal` ioctls 23 to 27. This driver does not have them. |
| below 256 | the DSP's own answer | the same query the upstream ioctl makes, through `fastrpc_get_dsp_info()` |

An id that is neither below 256 nor one of the four is refused with
`EOVERFLOW`, which is what CAF does.

**Not verified:** nothing has run this. The port's copy of the file
compiles clean with the kernel's own flags, and the command's encoding is
asserted against the value recovered from the shipped library, but the
answers above are reasoned, not measured.

## What is still open

* **The four commands with no header.** The vendor library issues 19
  commands, and 18 to 21 exist in no CAF header in the donor — their
  semantics have to come from the Qualcomm release that introduced them.
  The port refuses them by number, which is the honest answer, and the
  kernel log names the one the library actually reaches.
* **Whether the DSP answers attribute 128 at all.** The library asks for
  it and compares the answer with 2. It is below 256, so it is a DSP
  attribute and it goes through the DSP query, which needs a DSP that
  answers the capability query. That is the next thing to find out.

## How it was measured

```bash
# the full boot log, on the phone
adb shell 'dd if=/dev/block/by-name/logdump bs=1M count=16 | strings | grep "ioctl nr"'

# the library
adb pull /vendor/lib64/libadsprpc.so
llvm-objdump -d --no-show-raw-insn libadsprpc.so
```

The port's own tool for the same library is
`porting/tools/fastrpc-ioctl-audit.py`; it lists every `'R'`-typed command
the library can build, and this finding is about the one it actually
builds during `apps_dev_init`.
