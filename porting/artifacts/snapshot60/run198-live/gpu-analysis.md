# run198 — GPU address-mode fix, and what it did and did not prove

Date: 2026-10-17. Image `boot-run198.img`, payload `0b042809…`, based on
`boot-run197.img` (which is `boot-run196.img` + the panel-regulator counter
fix). One source change vs run197, in `drivers/gpu/msm/adreno.c`.

## The change

`adreno_support_64bit()` is compiled as

```c
#if BITS_PER_LONG == 64
        return ADRENO_FEATURE(adreno_dev, ADRENO_64BIT);
#else
        return false;
#endif
```

Stock CAF 4.19 is a **32-bit ARM** kernel, so on stock tissot it is always
false and the A506 never enters 64-bit hardware address mode. This port is
**arm64**, and the A506 carries `ADRENO_64BIT`, so it was always true here.

That mattered because the port separately *withholds* `KGSL_MMU_64BIT`
(`adreno.c:1555`), which keeps `kgsl_iommu.c` on `setup_32bit_pagetable()`
and every PM4/IB gpuaddr at 32 bits — matching stock. The two decisions
disagreed: the MMU built 32-bit descriptors while
`a5xx_enable_64bit()` had already programmed 12 `ADDR_MODE_CNTL = 1`
registers (UCHE, RB, PC, GRAS, VSC, SP, TP, VPC, VFD, HLSQ).

All three `adreno_support_64bit()` uses are now gated on
`MMU_FEATURE(&device->mmu, KGSL_MMU_64BIT)`:

* `adreno.c:2211` — the start path
* `adreno.c:3140` — the retake path
* `adreno.c:2794` — `KGSL_PROP_DEVICE_BITNESS`, which was advertising **48**
  to gralloc/EGL while the MMU pool was 32-bit

## What it fixed

`DIAG uche-oob` reads `A5XX_UCHE_ADDR_MODE_CNTL` back. It now reports
`addr_mode=0`, matching stock, instead of `addr_mode=1`. The device-bitness
lie to userspace is gone. This was a genuine port-vs-stock divergence and is
fixed on its own merits.

## What it did NOT fix — and that is the useful result

The UCHE trap is unchanged, down to the address:

| | run196 | run198 |
|---|---|---|
| `addr_mode` | 1 | **0** |
| trap address | `0x139000` | **`0x139000`** |
| `cp_status` | `80423c68` | `80423c68` |
| `GPU hang detected` (~700 s) | 816 | 937 |
| `gpu fault ctx` | 517 | 593 |
| `gpu fault threshold exceeded` | 2 | 2 |
| first fault | t = 42.39 s | t = 41.87 s |

So the hardware address mode was **not** the cause. That kills the hypothesis
cleanly: it is now established that the UCHE rejects `0x139000` with the
hardware in exactly the regime stock uses.

## Where the first fault actually is

The log immediately around the first trap shows this is a **startup** fault,
not a workload fault. Within 12 ms of `ME_INIT submit` and the bring-up
probes:

```
DIAG bringup[me-unhalted]: rbbm=C00003C1 ... cp_status_1=8C42440A gfx_rate=650000000
DIAG ME_INIT submit: gfx_rate=650000000 active_freq=650000000 secured=0
DIAG gpu_smmu: cb=gfx3d_user sctlr=00001167 translating=1 fsr=00000400
DIAG gpu_memdesc: rb{gpu=0f800b000} memstore{gpu=0f8001000} ...
UCHE: Out of bounds access addr=0000000000139000
DIAG uche-oob: cp_status=80423c68 hw_fault=00000000 ib2=0000000000260140/0 addr_mode=0
DIAG cp-stall: rptr=fd wptr=fd
...
surfaceflinger[716]: gpu fault ctx 2 ctx_type GL ts 12672 status 800001C1 rb 0100/0209
```

The **first** GL context to submit anything — `surfaceflinger[716]`, context 2,
RB read 0x100 / write 0x209 — faults. Nothing has rendered yet.

`0x139000` is invariant across every run, every process and every context.
It is the first GPU SVM allocation (`SVM_BASE32 = uche_gmem_base + gmem_size
= 0x100000 + 0x22000 = 0x122000`; the first allocation lands at 0x139000),
so it is a structural address, not a coincidental one.

For reference, the UCHE's programmed GMEM window reads back as
`gmem=00100000-00121000` while the driver's own `SVM_BASE32` is `0x122000` —
the hardware quantises the max to page granularity (`0x121FFF` → `0x121000`).
That code is byte-identical to CAF, so it is not a port divergence and is not
by itself the cause.

## Status

The display bring-up defect is fixed and verified (see
`../run196-live/display-analysis.md`). The screen is black because the GPU
accepts commands, signals completion and produces no pixels. That fault is
still open; this run removed one real divergence from it and ruled that
divergence out as the cause.