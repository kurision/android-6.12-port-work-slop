# Snapshot41 — trace every QSEE SMC + a live `selinux=0` knob

## Why this build exists

Snapshot40 run 1 ended 0.4 ms after:

    QSEECOM: native ioctl 0xc0209703 nr 3 enter   keymaster pid 339, t=100.418419

with no `snapshot35 scm_*` line anywhere in the log. Two reasons, both fixed
here:

1. **The trace gate was too narrow.** `__scm_smc_call` traced only
   `owner 48 / svc 0 / cmd 1|6`. keymaster's stalled call is cmd `0x3`, so the
   one call that matters was the one call never printed. The gate is now every
   owner-48 svc-0 command; `__scm_smc_do_quirk`'s `__ratelimit(HZ, 8)` still
   bounds volume.
2. **`selinux=` was inert.** The resolved config of the shipping kernel says
   `# CONFIG_SECURITY_SELINUX_BOOTPARAM is not set`, so the `selinux=0` token
   has no handler. `scripts/tissot-ack.config` already requests it, but the
   VM builds reuse an existing output directory seeded from the baseline
   config, so the fragment value never reaches `olddefconfig` on those runs.

Build 14's runtime already proved SELinux is **not** the stall: the boot runs
to `mount_all --early`, `/data` mounts f2fs, listeners register, keystore2 and
keymaster start — all with `enforcing=1`. Permissive mode is built here as a
*diagnostic* knob, not as the fix.

## Changes

| file | change |
|---|---|
| `drivers/firmware/qcom/qcom_scm-smc.c` | `trace_send` = `owner == 48 && svc == 0` (was `cmd == 1 \|\| cmd == 6`) |
| `scripts/build-ack-tissot.sh` | `CONFIG_SECURITY_SELINUX` and `CONFIG_SECURITY_SELINUX_BOOTPARAM` added to the required-symbol assertion |

No other driver, no DT, no config fragment, no ramdisk change.

## VM build recipe

Same flow as snapshot38/39, **same output directory** (`out`), because the
point is to fix the existing config rather than start a new tree:

```sh
cd ~/ack-android16-6.12
git fetch && git checkout port-work && git pull        # revision: see below

# 1. turn the knob on in the SAME output dir
./scripts/config -e SECURITY_SELINUX_BOOTPARAM --file out/.config   # or:
#    scripts/config --file out/.config -e SECURITY_SELINUX_BOOTPARAM
./scripts/config --file out/.config -d SECURITY_SELINUX_DEVELOP
make O=out olddefconfig

# 2. assert before building — both must be =y
grep -x CONFIG_SECURITY_SELINUX=y           out/.config
grep -x CONFIG_SECURITY_SELINUX_BOOTPARAM=y out/.config

# 3. build
make O=out -j"$(nproc)" Image.gz
make O=out qcom/msm8953-xiaomi-tissot.dtb
cat out/arch/arm64/boot/Image.gz \
    out/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb \
    > out/arch/arm64/boot/Image.gz-dtb
```

`CONFIG_SECURITY_SELINUX_DEVELOP` is dropped on purpose: it only prints
additional denial detail and is not needed once the bootparam works.

## What to transfer

Six files into `porting/artifacts/snapshot41/` plus a `SHA256SUMS`:

    out/arch/arm64/boot/Image.gz
    out/arch/arm64/boot/Image.gz-dtb
    out/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb
    out/.config
    out/include/generated/banner          # release string, for provenance
    out/.config.old                       # pre-change config, for the diff

## Acceptance checks before packaging

1. `Image.gz-dtb == Image.gz + board.dtb` byte-for-byte.
2. `gzip -t Image.gz` exit 0.
3. Embedded `IKCONFIG` contains `CONFIG_SECURITY_SELINUX_BOOTPARAM=y` and
   **not** `# CONFIG_SECURITY_SELINUX_BOOTPARAM is not set`. This is the check
   that would have caught the previous 14 builds.
4. Embedded `IKCONFIG` still contains `CONFIG_QSEECOM=y`, `CONFIG_ION=y`,
   `CONFIG_SECURITY_SELINUX=y`.
5. `strings Image.gz | grep -c 'snapshot35 scm_pre'` > 0 and the new gate is
   present: the binary must still carry the scm trace templates.
6. `board.dtb` SHA256 unchanged from snapshot38's `18a1081e…7aae8` — this
   build touches no device tree.

## Packaging

Copy `porting/artifacts/snapshot40/package.py` into the new directory and
point `IMAGE` at `boot-ack-snapshot41-scm-all-selinux.img`. Keep snapshot40's
base ramdisk (it carries the `DIAG: pidns` probe, already exercised on device
— run 1 emitted one line successfully, so it stays).

Do **not** add `selinux=0` to the packaged cmdline for the default run. Two
runs are wanted, in this order:

- **run 1, cmdline unchanged.** The widened SCM gate alone. This is the
  experiment that matters: it shows whether keymaster's cmd `0x3` SMC is
  entered and whether a return ever arrives.
- **run 2, `selinux=0` appended.** Only after run 1, and only to prove the
  knob is live (`enforcing=0` in the audit line). One image, two boots.

## Expected outcome of run 1

| observation | conclusion |
|---|---|
| `scm_send_desc … cmd=3` then `scm_pre` then stream ends | the driver sent it and TZ never answered — a TrustZone/firmware-side problem |
| `scm_send_desc … cmd=3` with no `scm_pre` | the call is stuck before the SMC, i.e. in argument marshalling or the spill path |
| neither line | the stall is above `__scm_smc_call` entirely — the ioctl never reached SCM |

Absence of a line is weakened by the rate limiter: `__ratelimit(HZ, 8)` allows
8 per second, so a burst can be suppressed. The `scm_send_desc` line is *not*
rate-limited, so it is the reliable indicator; `scm_pre` is best-effort.

## Not established by this build

Whether a traced SMC that never returns is the *cause* of the cutoff or only
its final symptom. Snapshot38 already showed the cutoff endpoint varies
72.1–101.5 s with 13 traced sends and 12 returns, so a hang here would be
correlational until reproduced across runs.