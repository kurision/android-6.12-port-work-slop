#!/bin/sh
# Fetch the dt-bindings headers needed to preprocess msm8953-xiaomi-tissot.dts
# outside a kernel checkout, so `build-dts.sh` works standalone.
#
#   sh fetch-includes.sh [branch]
#
# Default branch is android-mainline's upstream-master. Note that some headers
# are symlinks in git (e.g. include/dt-bindings/input/linux-event-codes.h ->
# ../../uapi/linux/input-event-codes.h); googlesource returns the *target path* as
# the file body, so this script copies the real content over such stubs.
set -eu

BRANCH=${1:-upstream-master}
BASE="https://android.googlesource.com/kernel/common/+/refs/heads/$BRANCH/include"
HERE=$(cd "$(dirname "$0")" && pwd)

HEADERS="

dt-bindings/clock/qcom,dsi-phy-28nm.h
dt-bindings/clock/qcom,gcc-msm8953.h
dt-bindings/clock/qcom,rpmcc.h
dt-bindings/gpio/gpio.h
dt-bindings/iio/qcom,spmi-vadc.h
dt-bindings/input/linux-event-codes.h
dt-bindings/interconnect/qcom,msm8953.h
dt-bindings/interconnect/qcom,rpm-icc.h
dt-bindings/interrupt-controller/arm-gic.h
dt-bindings/interrupt-controller/irq.h
dt-bindings/leds/common.h
dt-bindings/power/qcom,rpmhpd.h
dt-bindings/power/qcom-rpmpd.h
dt-bindings/soc/qcom,apr.h
dt-bindings/sound/qcom,q6afe.h
dt-bindings/sound/qcom,q6asm.h
dt-bindings/sound/qcom,q6dsp-lpass-ports.h
dt-bindings/spmi/spmi.h
dt-bindings/thermal/thermal.h
uapi/linux/input-event-codes.h
"

for h in $HEADERS; do
	mkdir -p "$HERE/include/$(dirname "$h")"
	if curl -fsSL "$BASE/$h?format=TEXT" | base64 -d > "$HERE/include/$h" 2>/dev/null; then
		:
	else
		echo "fetch failed: $h" >&2
	fi
done

# include/dt-bindings/input/linux-event-codes.h is a git symlink to
# ../../uapi/linux/input-event-codes.h. googlesource hands back the *target path*
# as the body, so replace it with the real header fetched above.
if [ -s "$HERE/include/uapi/linux/input-event-codes.h" ]; then
	cp "$HERE/include/uapi/linux/input-event-codes.h" \
	   "$HERE/include/dt-bindings/input/linux-event-codes.h"
	echo "resolved dt-bindings/input/linux-event-codes.h from the uapi copy"
fi

echo "headers under $HERE/include: $(find "$HERE/include" -name '*.h' | wc -l)"