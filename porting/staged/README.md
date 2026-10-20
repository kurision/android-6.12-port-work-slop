# Staged patches

> **Current state: CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUILD_TISSOT.md](../../BUILD_TISSOT.md).

Patches that are written but deliberately **not** in the tree, so that the next
boot stays single-variable. Apply with `git apply` when the work is actually
being tested.

## fastrpc-ioctl17-get-dsp-info.patch

Answers CAF's number 17, `GET_DSP_INFO`: one attribute, the domain, the
attribute id, and the capability the kernel answers with.

The vendor `adsprpcd` asks for attribute 257 right after it asks for the
channel id, and the port refuses it. CAF's 2022 and later
`adsprpc_shared.h` says what 17 is and what 257 means: the ids below 256
are the DSP's own attributes, the ids above it are the kernel's own
capabilities, and 257 is "the driver has the second generation of the
error codes". The disassembly of the shipped library agrees: the payload
is `{domain, attribute}`, the value comes back at offset 8, and the
command is `0xc00c5211` — the same twelve bytes the port already carried
as an unknown command.

The answers are the ones this driver can honestly give: the userspace
allocation capability is one (the driver has `ALLOC_DMA_BUFF`, and its CAF
control answers `kalloc_support` with one), the error-code capability is
one (the driver does not translate the DSP's errors, here or in the
donor, so the client sees the DSP's own error, and the ROM's own driver
answers one for the ROM's own firmware), the perf capability is zero
(this driver has upstream's perf counters, not CAF's second generation of
them, and the client would then use an invoke path that does not exist
here), and the signalling capability is zero (the `dspsignal` ioctls, 23
to 27, are not implemented).

**Not verified:** no image has been built or booted with this. The port's
own copy of the file compiles clean with the kernel's flags, and the
command's encoding is asserted against the value recovered from the
shipped library, but nothing has run it.

**Kept out of the tree so that the next boot tests one thing:** the
`GETINFO` handler that is already committed. Apply with
`git apply porting/staged/fastrpc-ioctl17-get-dsp-info.patch`.

## fastrpc-ioctl12-control.patch

Implements `FASTRPC_IOCTL_CONTROL` (ioctl 12) in `drivers/misc/fastrpc.c`, plus
the `enum fastrpc_control_type`, the four payload structs and
`struct fastrpc_ioctl_control` in `include/uapi/misc/fastrpc.h`.

Struct layout and encoded ioctl were checked to be byte-identical to
`oc-test/drivers/char/adsprpc_shared.h:247-282` (`sizeof` 12, cmd `0xc00c520c`).
`KALLOC` (3) and `DSPPROCESS_CLEAN` (6) are real implementations;
`LATENCY` (1), `WAKELOCK` (4) and `PM` (5) return `-EOPNOTSUPP` because this
driver has no PM QoS path and no cpuinfo RMID; `SMMU` (2) is rejected because the
donor rejects it too, with the same errno. Nothing stubs success.

**Do not expect this to fix adsprpcd.** See
`porting/TRACKER-kgsl-port.md`, "The CAF ioctl numbering does not match
mainline's". Only ioctl nr 13 coincides, and its payload differs even there, so
a CAF-built `adsprpcd` will hit `-ENOTTY` on its INIT, MMAP, MUNMAP, INVOKE and
GETINFO no matter what this driver implements. This ioctl is correct and needed
eventually; it is not sufficient on its own.

Untested on hardware. Kept out of the tree so that investigating the SystemServer
boot blocker is not confounded by it.
