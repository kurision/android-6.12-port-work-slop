# qseecom 6.12 build-fix handoff — 2026-10-06

> **Historical record - 2026-10-06.** This is what
> the evidence showed at the time and has not been rewritten. The
> current state is [CURRENT-STATE.md](../CURRENT-STATE.md).

## Status
Fedora build completed; fetched Image.gz-dtb is 16,936,518 bytes, SHA256
`b4bd964e617892ccaf9e33b2d904a11050d35a5ecb4322152fa15f6ddfc5a108`.
Gzip integrity, ARM64 Image, appended Tissot DTB and updated QSEECOM
strings verified. Snapshot16 temporary boot returned OKAY but produced no
USB/recorder output; recovered logdump is still snapshot15, not a new log.
Snapshot16 same-kernel probe-disabled test restored Android init startup.
New supplied step2 enabled kernel now also reaches Android init: QSEECOM logs
QSEE version 0x1001000 at 3.10 s and proceeds beyond shmbridge warnings.
qseecomd still exits 255 with SELinux access denied on mmcblk1p4. No full
driver acceptance claimed. Enabled capture finished: records 0–1422 without
gaps, recorder EOF, 120 s final quiet; no kernel panic observed, qseecomd exits
255. Disabled reader was temporary-booted directly via fastboot, without
OrangeFox/installed-ROM between runs. Its USB capture completed: records
0–1437 without gaps, recorder EOF, 120 s final quiet. USB pstore opening
failed with ENOENT after Android root handoff; `files=0` is NOT evidence
of an empty pstore. Pre-handoff storage dump remains to be retrieved.
Return manually to fastboot, then temporary-boot OrangeFox to read logdump.
Source now snapshots pstore into an inherited read-only mapping before
handoff. Corrected snapshot17b image is compiled/staged, NOT booted;
root-removal runtime smoke is pending recovery access. No async fallback
unless the durable dump establishes genuine empty pstore. No flashing.

## Round 1 — 6.12 API migration (`drivers/misc/qseecom.c`)
- 16× `strlcpy`→`strscpy`; 2× `access_ok` 2-arg (now :1573, :2077).
- 19× `kzfree`→`kfree_sensitive`; `%x`→`%lx` for `dma_buf_flags`.
- Bridge: `qseecom_destroy_bridge_callback` deleted; both
  `dma_buf_set_destructor` calls gone; `qseecom_create_bridge_for_secbuf`
  is a no-op `return 0` (caller at old :1493 treats nonzero as fatal, so the
  mapping path is preserved); `qseecom_register_heap_shmbridge` tail calls
  the stub then `return 0` (ownership-neutral: create allocates nothing).
- `qseecom_vaddr_map` (`:1432-1473`): `dma_buf_kmap`→`dma_buf_vmap` +
  `iosys_map` (`#include <linux/iosys-map.h` added); unmap uses
  `IOSYS_MAP_INIT_VADDR` + `dma_buf_vunmap`. `begin/end_cpu_access` untouched.
- Self-inflicted bug fixed same session: declaration edit dropped
  `int ret = 0;` → restored at `:1443`.
- Preemptive: `ion.c:1116` `strlcpy`→`strscpy` (same error class, past limit).

## Round 2 — compat migration (user-reported build failure)
- `compat_qseecom.c:22-44`: file-local `qseecom_compat_alloc_user_space()`
  (carve 16-byte-aligned shadow from `compat_user_stack_pointer()`,
  `access_ok`-gated, NULL on fault) replaces 19× `compat_alloc_user_space`;
  `qseecom_copy_in_user()` (stack bounce ≤64 B; sites move 32/64 B) replaces
  5× `copy_in_user`. Native `qseecom_ioctl` untouched — 30 native cases
  consume `__user` via `copy_from_user`; full kernel-pointer refactor
  rejected as higher-risk blind rewrite. 32-bit ABI translation unchanged.
- `ion/compat_ion.c:31`: same pattern as `ion_compat_alloc_user_space()`,
  2 sites (would have failed next). `compat_get_int` is file-local, fine.
- One stray-line incident during editing (`PUT 818 …` header inserted as
  text at old :801-802) caught by grep sweep and removed; site :818 then
  converted normally. Final: 19/19 + 2/2 alloc, 5/5 copy sites.

## Verification evidence (all tool-observed, Mac side)
- Zero bare `strlcpy|kzfree|VERIFY_WRITE|dma_buf_set_destructor|`
  `dma_buf_kmap|kunmap|copy_in_user|compat_alloc_user_space|set_fs|get_fs`
  across all four files (remaining hits: log strings + comments only).
- Overlays extract byte-identical (`cmp` OK).

## Overlays (apply in order on VM checkout, no clean/config reset)
| File | Size | SHA256 | Contains |
|---|---|---|---|
| `porting/artifacts/qseecom-612-api-fix.tar.gz` | 58,348 | `95edd3bc…79ea` | qseecom.c (pre-ret-fix), ion.c, manifest |
| `porting/artifacts/qseecom-612-compat-fix.tar.gz` | 55,652 | `46bdf0e9…b13b` | qseecom.c (ret fix, supersedes), compat_qseecom.c, compat_ion.c, manifest (all 4 current hashes) |

Historical tree hashes before later compile fixes: qseecom.c `7802cad0…ebf26b0`,
compat_qseecom.c `149fe11e…545f68`, ion.c `9eb281a9…8752`,
compat_ion.c `f2bea458…b64fc2`.

## Next (Fedora VM + device)
1. Rebuilt kernel is already fetched and validated; do not reapply older
   overlays over user's subsequent driver fixes.
2. Snapshot16 boot image preserves snapshot15 ramdisk and changes only kernel
   payload/size/header ID. Fastboot accepted it but no recorder start was written.
3. Recovery verified boot_a unchanged and logdump identical to snapshot15.
   Empty USB capture and no exposed pstore mean the early failure is unresolved.
4. Probe-disabled DTB isolation image retains exactly the same compressed kernel
   and ramdisk; Android init and mounts work, recorder EOF captured.
   It cannot count as QSEECOM acceptance. Durable isolation dump retrieved:
   records 0–1301 without gaps, storage EOF, matching USB overlap.
   Phone is in temporary OrangeFox; boot_a unchanged. Recovery/ACK ramoops
   use different physical regions, so empty recovery pstore is not definitive.
5. Boot bar unchanged: `/dev/qseecom 0660 system drmrpc`,
   `/dev/ion 0664 system system`, no qseecomd-255 loop,
   `vendor.sys.listeners.registered=true`, `mount_all --late` reached.

## Open risks
- Compat stack-carve helper replicates removed core logic locally; proven
  path preserved but untested on device. 32-bit qseecomd usage on tissot
  unknown — if 64-bit only, compat never runs (must still compile).
- `qseecom_copy_in_user` partial-copy fault semantics differ slightly from
  `copy_in_user`; callers only test nonzero → ioctl fails either way.
- Further `-ferror-limit`-hidden errors possible (compat_ion was one);
  sweep more `drivers/staging/android/ion/` + `drivers/misc/` if log shows
  new `error:` lines.
