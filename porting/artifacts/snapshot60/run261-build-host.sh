#!/usr/bin/env bash
# Build and package run261: the hardened APCC driver, same config, same base.
#
# The only source difference against run260 is drivers/clk/qcom/apcc-msm8953.c
# (and its host test, which is not part of the kernel). Config, ramdisk, init
# and command line are the run258/run260 ones, so a boot of this image tests
# the driver change and nothing else.
set -euo pipefail
REPO=/home/kurision/development/kernel/ack-kgsl
cd "$REPO"
SNAP="$REPO/porting/artifacts/snapshot60"
ACK_TREE=/home/kurision/development/kernel/ack-staged-run239
OUT_DIR=/home/kurision/development/kernel/ack-out-run261
export PATH=/usr/bin:$PATH
TC=/home/kurision/.rustup/toolchains/stable-x86_64-unknown-linux-gnu
export RUSTC="$TC/bin/rustc" HOSTRUSTC="$TC/bin/rustc"
export BINDGEN=/home/kurision/.cache/run164-bindgen0732/bin/bindgen
export RUST_LIB_SRC="$TC/lib/rustlib/src/rust/library" LIBCLANG_PATH=/usr/lib
test -r "$RUST_LIB_SRC/core/src/lib.rs"
test -r "$LIBCLANG_PATH/libclang.so"
test -f "$ACK_TREE/Makefile"
test ! -e "$OUT_DIR"
test ! -e "$SNAP/boot-run261.img"
test ! -e "$SNAP/kdir-run261"
test ! -e "$SNAP/package-run261.json"
trap 'rc=$?; printf "status=%s\n" "$rc" > "$SNAP/run261-build.status"' EXIT
df -h "$REPO" /tmp
/usr/bin/clang --version
"$RUSTC" -vV
"$BINDGEN" --version
python3 - <<'PY'
import pathlib, subprocess, shutil, hashlib, json
r=pathlib.Path.cwd(); s=r.parent/'ack-staged-run239'; records=[]
snap=r/'porting/artifacts/snapshot60'
old=json.loads((snap/'package-run258.json').read_text())
assert hashlib.sha256((snap/'boot-run258.img').read_bytes()).hexdigest()==old['sha256']
assert hashlib.sha256((snap/'init-run257').read_bytes()).hexdigest()==old['init_sha256']
for p in subprocess.check_output(['git','ls-files','-z']).decode().split('\0'):
    if not p or not (p in ('Makefile','Kconfig','Kbuild') or p.startswith(('arch/','drivers/','include/','kernel/','mm/','lib/','fs/','security/','scripts/','rust/','Documentation/devicetree/bindings/'))): continue
    a=r/p; b=s/p
    if not a.is_file(): continue
    changed=not b.exists() or a.read_bytes()!=b.read_bytes()
    if changed:
        b.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(a,b)
    assert a.read_bytes()==b.read_bytes(),p
    records.append(dict(path=p,sha256=hashlib.sha256(a.read_bytes()).hexdigest(),synced=changed))
(snap/'run261-source-verification.json').write_text(json.dumps(records,indent=2)+'\n')
prev=json.loads((snap/'run260-source-verification.json').read_text())
prevm={x['path']:x['sha256'] for x in prev}
now={x['path']:x['sha256'] for x in records}
changed=[p for p in sorted(set(prevm)&set(now)) if prevm[p]!=now[p]]
print('Verified source files:',len(records),flush=True)
print('Synchronized this run:',[x['path'] for x in records if x['synced']],flush=True)
print('Changed against run260:',changed,flush=True)
assert changed==['drivers/clk/qcom/apcc-msm8953.c'], changed
PY
mkdir "$OUT_DIR"
scripts/extract-ikconfig "$SNAP/kdir-run258/Image.gz" > "$OUT_DIR/.config"
test -s "$OUT_DIR/.config"
cp "$OUT_DIR/.config" "$SNAP/run261-prebuild.config"
make_args=(make -C "$ACK_TREE" "O=$OUT_DIR" ARCH=arm64 LLVM=/usr/bin/ LLVM_IAS=1 CC=/usr/bin/clang
 "RUSTC=$RUSTC" "HOSTRUSTC=$HOSTRUSTC" "BINDGEN=$BINDGEN"
 'RUSTFLAGS_AUTOFDO_CLANG=-Zdebuginfo-for-profiling -Cllvm-args=-enable-fs-discriminator=true -Cllvm-args=-improved-fs-discriminator=true')
"${make_args[@]}" rustavailable
"${make_args[@]}" olddefconfig
scripts/diffconfig "$SNAP/run261-prebuild.config" "$OUT_DIR/.config" | tee "$SNAP/run261-config.diff"
test ! -s "$SNAP/run261-config.diff"
for key in RUST_IS_AVAILABLE RUST ASHMEM SHMEM STAGING IKCONFIG IKCONFIG_PROC PSTORE_RAM QCOM_IOMMU ARM_SMMU QCOM_SCM ANDROID_BINDER_IPC USB_CONFIGFS USB_CONFIGFS_F_FS COMPAT CPUFREQ_DT QCOM_CLK_APCC_MSM8953 QCOM_APCS_IPC QCOM_RPMPD PM_GENERIC_DOMAINS_OF; do
 rg -qx "CONFIG_${key}=y" "$OUT_DIR/.config"
done
"${make_args[@]}" -j8 W=1 fs/pstore/ram.o kernel/reboot.o drivers/clk/qcom/apcc-msm8953.o drivers/mailbox/qcom-apcs-ipc-mailbox.o drivers/soc/qcom/msm8953-spm.o
"${make_args[@]}" -j8 Image.gz
"${make_args[@]}" dt_binding_check DT_SCHEMA_FILES=clock/qcom,apcc-msm8953.yaml
"${make_args[@]}" CHECK_DTBS=y qcom/msm8953-xiaomi-tissot.dtb
BOOT="$OUT_DIR/arch/arm64/boot"
cat "$BOOT/Image.gz" "$BOOT/dts/qcom/msm8953-xiaomi-tissot.dtb" > "$BOOT/Image.gz-dtb"
sha256sum "$SNAP/boot-run258.img" > "$SNAP/run261-base.sha256"
python3 -B porting/logging/package-diag-boot.py --base-image "$SNAP/boot-run258.img" \
 --kernel-dir "$SNAP/kdir-run261" --stage-kernel "$BOOT" --init "$SNAP/init-run257" \
 --keep-stock-console --out "$SNAP/boot-run261.img" --report "$SNAP/package-run261.json"
scripts/extract-ikconfig "$SNAP/kdir-run261/Image.gz" > "$SNAP/run261-embedded.config"
python3 - <<'PY'
import pathlib,json,hashlib,gzip,re,subprocess
s=pathlib.Path('porting/artifacts/snapshot60'); old=json.loads((s/'package-run258.json').read_text());new=json.loads((s/'package-run261.json').read_text())
for k in ['ramdisk_sha256','init_sha256','cmdline']:
    assert old[k]==new[k],k
prev=json.loads((s/'package-run260.json').read_text())
for k in ['ramdisk_sha256','init_sha256','cmdline']:
    assert prev[k]==new[k],k
for x in json.loads((s/'run261-source-verification.json').read_text()):
    assert hashlib.sha256(pathlib.Path(x['path']).read_bytes()).hexdigest()==x['sha256'],x['path']
symbols=subprocess.check_output(['/usr/bin/llvm-nm','-a','/home/kurision/development/kernel/ack-out-run261/vmlinux'],text=True)
for name in ['ramoops_witness_write','ramoops_witness_read','ramoops_stage_write','ramoops_qtrace_write','ramoops_reset_note']:
    assert name in symbols,name
(s/'run261-diagnostic-symbols.txt').write_text('\n'.join(x for x in symbols.splitlines() if any(n in x for n in ['ramoops_witness','ramoops_stage_write','ramoops_qtrace','ramoops_reset_note']))+'\n')
config=(s/'run261-embedded.config').read_text()
for key in ['RUST_IS_AVAILABLE','RUST','ASHMEM','CPUFREQ_DT','QCOM_CLK_APCC_MSM8953','QCOM_RPMPD']:
    assert f'CONFIG_{key}=y\n' in config,key
print('Preserved ramdisk, init and command line against run258 and run260; diagnostic helper symbols present.')
print(json.dumps(new,indent=2))
for m in re.finditer(rb'Linux version [^\0\n]+',gzip.decompress((s/'kdir-run261/Image.gz').read_bytes())):
    print('EMBEDDED BANNER:',m.group().decode())
PY
