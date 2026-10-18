#!/usr/bin/env bash
# run234: reverts the run232-only diagnostic that pinned the GPU to its lowest
# power level. With the pin gone the source should be identical to run231, so
# the Build ID is expected to match run231's cc2a4241dd37c6764c28729ed07fa13eabd2dbaf
# -- a free check that the revert was exact. The pre-build config is asserted
# so a fragment change cannot ship silently.
set -euo pipefail
REPO=/home/kurision/development/kernel/ack-kgsl
SNAP="$REPO/porting/artifacts/snapshot60"
TC=/home/kurision/.rustup/toolchains/stable-x86_64-unknown-linux-gnu
export PATH=/usr/bin:$PATH
export RUST_LIB_SRC="$TC/lib/rustlib/src/rust/library" LIBCLANG_PATH=/usr/lib
args=(make -C /tmp/ack-run164-source "O=$REPO/out" ARCH=arm64 LLVM=1 LLVM_IAS=1 CC=clang "RUSTC=$TC/bin/rustc" "HOSTRUSTC=$TC/bin/rustc" BINDGEN=/home/kurision/.cache/run164-bindgen0732/bin/bindgen 'RUSTFLAGS_AUTOFDO_CLANG=-Zdebuginfo-for-profiling -Cllvm-args=-enable-fs-discriminator=true -Cllvm-args=-improved-fs-discriminator=true')
exec > >(tee "$SNAP/run234-build.log") 2>&1
date -Is
/usr/bin/clang --version
"$TC/bin/rustc" -vV
/home/kurision/.cache/run164-bindgen0732/bin/bindgen --version
"${args[@]}" rustavailable
"${args[@]}" olddefconfig
cmp /tmp/opencode/run234/config-before "$REPO/out/.config"
echo "config identical to the pre-build snapshot"
"${args[@]}" -j8 Image.gz
"${args[@]}" qcom/msm8953-xiaomi-tissot.dtb
cat "$REPO/out/arch/arm64/boot/Image.gz" "$REPO/out/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb" > "$REPO/out/arch/arm64/boot/Image.gz-dtb"
date -Is
