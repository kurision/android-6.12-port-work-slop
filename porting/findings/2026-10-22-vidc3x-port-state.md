# 2026-10-22: the state of the CAF vidc_3x forward port

**Evidence:** `porting/findings/2026-10-22-vidc3x-import-research.md` (the
inventory, the UAPI collision check and the 6.12 API survey),
`porting/tools/vidc-uapi-diff.py` and its output
`porting/artifacts/snapshot60/vidc-uapi-diff.txt`.

This is the status of the plan's Part B after the first two steps, and
what is left before the driver can be built and booted.

## Done

**B0 - the import** (commit `fa4add5f1`): the donor's
`drivers/media/platform/msm/vidc_3x/` (31 files, 34212 lines, plus
`governors/` and `vmem/`) and the four user space headers
`include/uapi/media/msm_vidc.h`, `msm_media_info.h`, `msm_vidc_private.h`
and `msm_vidc_utils.h` are in the tree, unchanged. The donor's kernel
internal header `include/media/msm_vidc.h` came with it.

**B1 - the user space interface** (commit `d7e462da4`): the CAF additions
to the two shared headers are in:

* `include/uapi/linux/videodev2.h`: the buffer flags, the events, the 42
  Qualcomm pixel formats, the decoder commands, and the buffer and event
  flags 6.12 removed (with the donor's values).
* `include/uapi/linux/v4l2-controls.h`: the 193 `V4L2_CID_MPEG_VIDC_*`
  control IDs and their enums, the two enum values 6.12 dropped, and the
  kernel side of the MPEG control class name.

`porting/tools/vidc-uapi-diff.py` checks that every one of those values
is the donor's, and reports the values that collide with an upstream
definition of the same kind. Its output is committed; the only collision
that matters is `V4L2_QCOM_BUF_DROP_FRAME` (0x00800000), which is
upstream's `V4L2_BUF_FLAG_REQUEST_FD` - see "Still open" below.

**B2 - the compile fixes, part one**: the API classes that the driver
needed, converted one at a time:

| donor | 6.12 |
|---|---|
| `vidioc_enum_fmt_vid_{cap,out}_mplane` | the core dispatches the mplane types to `vidioc_enum_fmt_vid_{cap,out}` |
| `VFL_TYPE_GRABBER` | `VFL_TYPE_VIDEO` |
| platform `.remove` returning `int` | `void` |
| `do_gettimeofday()` | `ktime_get_real_ts64()` |
| `struct timeval` in a kernel struct | `struct __kernel_v4l2_timeval` |
| `strlcpy()` | `strscpy()` |
| `vb2_qbuf(q, b)` | `vb2_qbuf(q, NULL, b)` (the driver has no media device) |
| `vb2_ops.get_userptr` with the direction | `get_userptr(vb, dev, vaddr, size)` |
| `dma_buf_vmap(dbuf)` | `dma_buf_vmap(dbuf, &map)`, which returns the error code |
| `vb2_queue.num_buffers` | `vb2_get_num_buffers(q)` |
| `debugfs_create_*()` returning a dentry | they return nothing in 6.12 |
| `pm_qos_add_request(PM_QOS_CPU_DMA_LATENCY)` | `cpu_latency_qos_add_request()` |
| `iommu_map()` with five arguments | with the allocation flags |
| `__assign_str(x, x)` | `__string(x, x)` and `__assign_str(x)` |
| the CAF fast SMMU mapping headers | the generic dma-buf API |
| CAF's subsystem framework | a shim, see below |

Two shims came with it:

* `include/soc/qcom/subsystem_restart.h` and
  `drivers/soc/qcom/subsystem-compat.c`: the CAF subsystem framework is
  not in 6.12. The firmware load is done the way this port's own upstream
  Venus driver does it (`request_firmware()` + `qcom_mdt_load()` into the
  reserved memory the device tree names + `qcom_scm_pas_auth_and_reset()`),
  and the subsystem restart notification is a no-op.
* `include/soc/qcom/boot_stats.h`: the CAF boot statistics driver is not
  in this tree, and the video codec only calls `boot_stats_init()` once.

One more change outside the driver: the port's display stack had a
`include/media/msm_media_info.h` of its own, and the video codec needs
the donor's header of the same name. The display one is now
`include/media/msm_mdp_media_info.h`; its two users (the DPU's
`dpu_formats.c` and `mdss_mdp_util.c`) were updated.

## Still open

1. **The driver does not build yet.** What is left is the bus bandwidth
   voting, the power domain and the clock handling, and the device tree.
   The bus voting is the port's `msm-bus` shim
   (`include/linux/msm-bus.h`), which votes with the index of the usecase
   in the table instead of a bandwidth in bytes per second; the plan
   `2026-10-22-bus-bandwidth-voting.md` is about that shim and the DDR
   votes, and the video codec is the largest consumer.
2. **The power rails.** The donor uses `regulator_get()` on
   `venus-supply` and `venus-core0-supply`; 6.12 uses the power domains
   (`power-domains` in the device tree), as the port's upstream Venus
   driver does. The order of the clock and the power domain operations
   has to match the donor's.
3. **The device tree.** The donor's `msm8953-vidc.dtsi` (209 lines) with
   the four context bank children and the two bus children, translated to
   the port's names: the power domains instead of the supplies, the
   port's SMMU stream for the context banks, and only the non-secure
   context bank (the secure one needs the TrustZone secure SMMU, which
   this tree does not have).
4. **The switch-over.** The upstream Venus driver and the CAF video codec
   must never both claim the hardware: the same commit that turns
   `CONFIG_MSM_VIDC_3X_V4L2` on turns `CONFIG_VIDEO_QCOM_VENUS` off and
   replaces the device tree node.
5. **The buffer flag collision.** `V4L2_QCOM_BUF_DROP_FRAME` is
   0x00800000, which is upstream's `V4L2_BUF_FLAG_REQUEST_FD`. 6.12's
   videobuf2 masks that bit off the flags it hands to the driver, and a
   queued buffer that has it set is treated as a request, which a queue
   without the requests API rejects with `-EBADR`. The value cannot
   change - the vendor OMX service is compiled against it - so the
   videobuf2 in this tree has to ignore the bit for a queue that does not
   use the requests API. `V4L2_QCOM_BUF_END_OF_SUBFRAME` (0x00000080) is
   upstream's `V4L2_BUF_FLAG_IN_REQUEST` and is masked off the same way.
6. **The 32-bit compat ioctls.** The vendor OMX service is 32 bit, so
   every ioctl goes through `v4l2-compat-ioctl32.c`. The research found
   that the three donor commits named in the plan
   (`e35529201880`, `17f07c01bc84`, `2ea36671164e`) are already
   subsumed by 6.12, so no change is needed there - but the compat path
   has to be exercised by the boot test, because the vendor service is
   32 bit.
7. **The boot test.** `/dev/video32` and `/dev/video33`, a dmesg without
   vidc errors, SMMU faults or HFI timeouts, `OMX.qcom.*` in
   `dumpsys media.player`, and a `screenrecord` that produces a file.
