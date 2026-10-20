# Staged patches

> **Current state: CURRENT-STATE.md.** The entries below are the
> running log and are ordered newest first; the top entry is not
> necessarily the current state. Build, package and flash:
> [BUILD_TISSOT.md](../../BUILD_TISSOT.md).

Patches that are written but deliberately **not** in the tree, so that the next
boot stays single-variable. Apply with `git apply` when the work is actually
being tested.

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
