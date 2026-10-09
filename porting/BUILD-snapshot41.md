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

## Build host

This machine builds it. The config is seeded from the **embedded IKCONFIG of
the shipping `Image.gz`** (`porting/artifacts/snapshot38/Image.gz`), not from
the local `out/` tree: `out/` is the older Fedora/build14 lineage and carries
`DRM_MSM`, `DRM_PANEL_OTM1911`, `DRM_FBDEV_EMULATION`, `VT` and
`SECURITY_SELINUX_BOOTPARAM`, none of which are in the shipping config.
Building there would change the display stack and the SELinux knob in one
step and make the run uninterpretable.

## Local build recipe

Historical recipe below: deleted `Image.gz`/`package.py` paths are former
scratch inputs, not current executable instructions. Extract preserved inputs
from `porting/artifacts/snapshot38/boot.img`; stage all intermediates in build
scratch. Current snapshot41 image is `porting/artifacts/snapshot41/boot.img`
(former root name `boot-ack-snapshot41-scm-all.img`); logs use `run<N>-*`.

```sh
cd ~/<path>/ack-android16-6.12
export ARCH=arm64 LLVM=1 LLVM_IAS=1

# 1. seed from the shipping kernel's own embedded config
mkdir -p out-snapshot41
gunzip -c porting/artifacts/snapshot38/Image.gz > /tmp/s38-image
python3 - <<'PY'
import zlib
d = open('/tmp/s38-image', 'rb').read()
i = d.find(b'IKCFG_ST')
open('out-snapshot41/.config', 'w').write(
    zlib.decompressobj(31).decompress(d[i+8:]).decode())
PY

# 2. the knob, then resolve
./scripts/config --file out-snapshot41/.config -e SECURITY_SELINUX_BOOTPARAM
make O=out-snapshot41 olddefconfig

# 3. assert before building
grep -x CONFIG_SECURITY_SELINUX=y          out-snapshot41/.config
grep -x CONFIG_SECURITY_SELINUX_BOOTPARAM=y out-snapshot41/.config

# 4. build
make O=out-snapshot41 -j"$(nproc)" Image.gz
make O=out-snapshot41 qcom/msm8953-xiaomi-tissot.dtb
cat out-snapshot41/arch/arm64/boot/Image.gz \
    out-snapshot41/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb \
    > out-snapshot41/arch/arm64/boot/Image.gz-dtb
```

`CONFIG_SECURITY_SELINUX_DEVELOP` is left `y` (its shipping value) rather
than dropped: the config is otherwise held identical to what shipped, and one
flipped symbol is easier to reason about than two.

### Verified config delta against the shipping kernel

Five values differ, four of them toolchain bookkeeping:

| symbol | shipping | snapshot41 |
|---|---|---|
| `CONFIG_SECURITY_SELINUX_BOOTPARAM` | not set | `y` |
| `CONFIG_AS_VERSION` | 210000 | 220108 |
| `CONFIG_CLANG_VERSION` | 210000 | 220108 |
| `CONFIG_LLD_VERSION` | 210000 | 220108 |
| `CONFIG_CC_VERSION_TEXT` | Android 21.0.0 | clang 22.1.8 |

The other 4,352 symbols are byte-identical. No display, storage, QSEE, ION
or security symbol changes.

### Known confound

The shipping kernel was built with Android clang 21.0.0; this host has clang
22.1.8. Codegen is not guaranteed identical across LLVM majors. The *config*
is the variable under test and it is held fixed; the toolchain difference is
an accepted, recorded unknown, not a silent one.
## Artifacts and packaging

From `out-snapshot41/`:

| file | purpose |
|---|---|
| `arch/arm64/boot/Image.gz` | compressed kernel |
| `arch/arm64/boot/Image.gz-dtb` | `Image.gz` + raw board DTB, the stock ROM layout |
| `arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb` | board DTB, must be byte-identical to snapshot38's |
| `.config` | resolved config, the acceptance-check reference |

Stage them under `porting/artifacts/snapshot41/` with a `SHA256SUMS`.

### Acceptance checks before packaging

1. `Image.gz-dtb == Image.gz + board.dtb` byte-for-byte.
2. `gzip -t Image.gz` exit 0.
3. Embedded `IKCONFIG` contains `CONFIG_SECURITY_SELINUX_BOOTPARAM=y` and
   **not** `# CONFIG_SECURITY_SELINUX_BOOTPARAM is not set`. This is the check
   that would have caught the previous 14 builds.
4. Embedded `IKCONFIG` still contains `CONFIG_QSEECOM=y`, `CONFIG_ION=y`,
   `CONFIG_SECURITY_SELINUX=y`.
5. `strings` on the decompressed `Image` still carries the `scm_send_desc` and
   `scm_pre` templates.
6. `board.dtb` SHA256 unchanged from snapshot38's `18a1081e…7aae8` — this
   build touches no device tree.

### Packaging

Copy `porting/artifacts/snapshot40/package.py` into the new directory and
point `IMAGE` at `boot-ack-snapshot41-scm-all.img`. Keep snapshot40's base
ramdisk: its `DIAG: pidns` probe fired correctly on device in run 1.

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