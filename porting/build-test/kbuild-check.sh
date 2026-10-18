#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
#
# Compile-check individual kernel source files against the existing ./out
# kbuild tree, without reconfiguring it and without producing a kernel.
#
# out/ was populated from a different source copy, so we take the saved
# command line from an existing .cmd file and re-point its absolute source-tree
# include paths (and the input file) at this repository.  The relative include
# paths are resolved from the object tree (CWD = out), which is exactly how
# kbuild invoked the compiler.
#
# Usage: porting/build-test/kbuild-check.sh <path/relative/to/repo.c> ...
set -euo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
objtree="$repo/out"

cmdref="$objtree/drivers/regulator/.core.o.cmd"
[ -f "$cmdref" ] || { echo "missing $cmdref (has out/ been built?)" >&2; exit 1; }

srcref=$(sed -n 's/^source_[^:]*:= //p' "$cmdref")
srctree=${srcref%%/drivers/regulator/core.c}

full=$(sed -n 's/^savedcmd_[^:]*:= //p' "$cmdref")
[ -n "$full" ] || { echo "could not read saved command from $cmdref" >&2; exit 1; }

# Keep the flag list, drop the '-c -o <obj> <src>' tail and the dependency dump.
flags=${full% -c -o *}
flags=${flags//$srctree/$repo}
flags=$(printf '%s' "$flags" | sed 's#-Wp,-MMD,[^ ]* ##')

mkdir -p /tmp/opencode
status=0
for src in "$@"; do
	out="/tmp/opencode/kbuild-check-$(basename "${src%.c}").o"
	echo "checking $src"
	if ! ( cd "$objtree" && eval "$flags" -c -o "$out" "$repo/$src" ); then
		status=1
	fi
done
exit $status
