# CPU repair checkpoints — 2026-10-19

These are source/evidence checkpoints, **not known-good CPU DVFS revisions**.

| Commit | Change | Evidence / limit |
|---|---|---|
| `2d56bc749` | Document coupled CPU IDs, read-only CCI and required MX-AO domain | Binding document and focused compiled-DT validation passed |
| `22529fab4` | Reserve only MSM8953's four-byte mailbox IPC register | CPU4 `-EBUSY` reproduced in runs257/258; host probe/send checks pass; hardware coexistence unverified |
| `931064e41` | Shared CPU/CCI transactions, MX/rail lifetime pins, split boot handoff, shared policy; remove pstore CPU4 clock writer | 49 rate pairs and 349 MMIO fault positions pass; real CCF/genpd and hardware DVFS remain unverified |
| `9c1bc7000` | Shared non-static diagnostic prototypes and retained file reference; guard exports and update host mocks | Five diagnostic suites pass; fixes source/W=1 declarations, not an established splash/reset cause |

The APCC checkpoint includes the accumulated transaction implementation required
by the new ownership/handoff repair. No fake CPU identification, OC/UV, TSENS or
idle/suspend implementation was added. Removing the pstore CPU4 switch is a
functional ownership transfer, **not just removing log messages**.

## Device results must stay attached to their actual artifacts

| Run | Image SHA256 | Result |
|---|---|---|
| 258 | `527a8bcbd8ee59d14b4a079ea44a192dd20b6a54e5ad97b53f8b15dd161e94fa` | Agent-observed Android boot/ashmem, absent CPUFreq and CPU4 mapping `-EBUSY`; user-visible severe lag; two SystemUI ANRs |
| 259 | `6fa41d995d9d2f6ebded85c933611d4b01d0be478a866ed677416771f5fb1a71` | User-built after the initial agent build failed; user reports splash/reset; recovered bytes are entirely stale run258 data |
| 260 | Not yet established at this checkpoint | Fresh cumulative build/package started with diagnostic interfaces restored; no agent boot yet |

Run259's entire recovered 67108864-byte logdump matches run258 SHA256
`a4c095fb0d333237f0109996c4b1187dde8de5d1f653afb9a40049cdd4594742`.
Its `#1 15:19:00` banner does not match run259's `#2 17:45:43` kernel. Do not
attribute the old reset note, snapshots or APCC error to the new image.
An early-panic recording blackout is still possible; absence of fresh records
does not prove the bootloader never entered Linux.

The user-built staged tree had whole diagnostic functions/calls commented out.
Preserved source diffs and hashes are under
`artifacts/snapshot60/run259-user-capture/`. Restoration reconciles the staged
tree without changing the approved APCC source. The committed tree already had
the diagnostic implementations, so the restoration commit's source diff is
principally declaration/header ownership and the file-reference annotation.

## Checks and intentionally uncommitted work

- Host checks: seven CPU suites with GCC/Clang; five diagnostic suites.
- Strict checkpatch code/style checks pass. New-file MAINTAINERS reminders are
  informational; the SPDX parser could not run because Python `ply` is missing.
- Standalone DT compilation, focused APCC schema/wiring checks pass. Full-board
  DT validation retains inherited findings. Sparse is unavailable.
- Each intermediate commit was not separately kernel-built or boot-tested.
  The in-progress run260 build uses the complete working tree, including the
  existing prerequisite edits listed below; do not conflate it with a clean
  checkout build of these commits alone.
- Pre-existing PM8953 matching, S5 extended-SPMI access, CPR numeric-table cells,
  AVS pause/restore, related earlier tests, diagnostic-init changes and unrelated
  documentation remain unstaged. They were not silently folded into these
  commits. The CPU DTS commit includes only sharing/MX/comment hunks.
- Boot images, 64 MiB dumps, source-wide manifests, output trees and previous
  unrelated artifacts remain outside the commits. Do not delete the only copy
  of an ignored known-good image; metadata hashes cannot recreate its ramdisk.

Full chronology: [CPU handoff](../HANDOFF-cpu-bringup-2026-10-19.md).
Procedures: [BUIL_TISSOT.md](../../BUIL_TISSOT.md) and
[boot-testing reference](../REFERENCE-boot-testing.md).
