# KernelSU "allow root" soft-lockup panic — 2026-10-20

Status: **cause proven from the logdump; fix applied, not yet verified on device.**

## Symptom

The phone froze and then rebooted while the KernelSU-Next manager was granting
root to an app (FKM). The manager itself was the process that died.

## Evidence

Read back from the `logdump` partition (`/dev/block/mmcblk0p48`, 64 MiB) after
the phone came back up. The panic region was still present in the ring:

```
[  775.170070][    C5] watchdog: BUG: soft lockup - CPU#5 stuck for 25s! [e.zeykvw.hpbcyd:14424]
[  775.170123][    C5] pstate: 20400005 (nzCv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[  775.170129][    C5] pc : _raw_spin_unlock_irqrestore+0x1c/0x5c
[  775.170145][    C5] lr : ksu_mark_running_process+0x44/0x68
[  775.170221][    C5] Call trace:
[  775.170223][    C5]  _raw_spin_unlock_irqrestore+0x1c/0x5c
[  775.170229][    C5]  ksu_mark_running_process+0x44/0x68
[  775.170234][    C5]  do_set_app_profile+0x5c/0xa4
[  775.170243][    C5]  ksu_supercall_handle_ioctl+0x3d0/0x428
[  775.170248][    C5]  anon_ksu_ioctl+0x10/0x20
[  775.170252][    C5]  __arm64_sys_ioctl+0xa0/0xec
[  775.170303][    C5] Kernel panic - not syncing: softlockup: hung tasks
```

The manager's own structured records in the logdump show the grant and the
walk that followed it:

```
6,22612,749069405,-,caller=T14424;KernelSU: set root profile, key: com.franco.kernel, uid: 10401, gid: 0, context: u:r:ksu:s0
6,22613,749069470,-,caller=T14424;KernelSU: tp_marker: mark process: pid:1, uid: 0, comm:init
6,22614,749078313,-,caller=T14424;KernelSU: tp_marker: unmark process: pid:225, uid: 0, comm:init
...
[  775.162516][T14424] KernelSU: tp_marker: mark process: pid:18203, uid: 0, comm:head
[  775.170070][    C5] watchdog: BUG: soft lockup - CPU#5 stuck for 25s!
```

The first mark is at 749.069470 s and the watchdog fires at 775.170070 s:
**26.1 s in the marking loop**, which is the soft-lockup window. Counted in
the saved logdump: **5,067** `tp_marker: mark/unmark process` lines before the
panic, all from `T14424`. `ls /proc/*/task | wc -l` on the live phone:
**4,211** threads.

## Cause

The grant-root flow that crashed is `SET_APP_PROFILE`, not `SET_SEPOLICY`:

- `do_set_app_profile()` calls `ksu_mark_running_process()` after saving the
  profile (`drivers/kernelsu/supercall/dispatch.c:389`).
- `ksu_mark_running_process()` takes `tracepoint_reg_lock` with IRQs disabled,
  then calls `ksu_mark_running_process_locked()`.
- That function walks every process/thread under `tasklist_lock` and, before
  this fix, did one `pr_info()` per thread
  (`drivers/kernelsu/hook/tp_marker.c`, old lines 101-108).

On a 4,211-thread phone that is ~5,000 synchronous console/logdump lines,
roughly 400 KB at ~80 bytes each. At the serial console rate this exceeds the
25 s soft-lockup threshold, so the watchdog panics with
`softlockup: hung tasks` and the phone reboots. The arithmetic matches the log:
the stream is still running when the 25 s timer expires.

This is not a local divergence: `KernelSU-Next/KernelSU-Next` `dev`
`kernel/hook/tp_marker.c` has the same per-thread `pr_info()`. It is an upstream
defect that only bites a device with this many threads and a slow console.

The earlier note in `CURRENT-STATE.md` that blamed `KSU_IOCTL_SET_SEPOLICY` was
not supported by this crash. The log shows `do_set_app_profile`; the
`synchronize_rcu` stall seen in a later section of the same ring is
`rcu_tasks_kthread` during shutdown (`rcu_tasks_trace_postscan`), not the
policy rewrite.

## Fix

`drivers/kernelsu/hook/tp_marker.c`: remove the per-thread `pr_info()` calls,
count marked/unmarked threads, and emit one summary line after the walk.

## Verification

Not yet verified on device. After rebuilding and flashing:

1. Grant root to an app from the manager.
2. Confirm the kernel log has one `tp_marker: refreshed running processes:
   N marked, M unmarked` line and no `soft lockup` / `Kernel panic`.
3. Confirm the app is actually granted (profile persisted, root works).

If the grant then reaches a separate `SET_SEPOLICY` path and stalls in
`synchronize_rcu`, that is a different bug and needs its own log; do not fold
it into this finding.

## Evidence location

The raw 64 MiB partition copy and `strings` dump were saved outside the repo
(`/tmp/opencode/logdump-ksu-freeze-20261020.bin` and `.txt`) because the
logdump ring is overwritten by each boot. The quotes above are from that copy.
