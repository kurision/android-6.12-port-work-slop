#!/bin/sh
# Reproduce (and later verify) the android-mainline msm8953-xiaomi-tissot.dts
# build locally, without a kernel checkout.
#
#   sh build-dts.sh <dts-dir> <dts-file> <out.dtb>
#
# <dts-dir> must contain msm8953.dtsi, pm8953.dtsi and pmi8950.dtsi (if any).
# include/ must hold the dt-bindings headers (fetched from android-mainline).
set -eu
DTSDIR=${1:-dts}
DTSFILE=${2:-msm8953-xiaomi-tissot.dts}
OUT=${3:-out.dts}
HERE=$(dirname "$0")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PRE=${PRE:-clang}
command -v "$PRE" >/dev/null 2>&1 || PRE=gcc

"$PRE" -E -P -nostdinc -undef -D__ASSEMBLY__ \
    -I "$HERE/include" -I "$DTSDIR" \
    -x assembler-with-cpp "$DTSDIR/$DTSFILE" -o "$WORK/pre.dts"

dtc -I dts -O dts -o "$OUT" -@ "$WORK/pre.dts"