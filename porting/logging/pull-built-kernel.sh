#!/usr/bin/env bash
# Pull freshly built kernel artifacts from the Linux build host out/ dir.
#
# Usage: pull-built-kernel.sh -p <password> [-H host] [-U user]
#                             [-R remote-out-dir] [-D local-dest-dir]
#
# Defaults target the run90 build:
#   host  192.168.4.114, user sneha
#   remote out: Documents/anil/kernel/android-6.12-port-work-slop/out
#   local dest: porting/artifacts/snapshot60/kdir-run90
#
# Pulls Image.gz, msm8953-xiaomi-tissot.dtb, Image.gz-dtb and kernel.config,
# plus System.map and vmlinux (skip with -n), banner-checked against
# Image.gz and hashed into SYMBOLS.SHA256SUMS.
# Each pull goes to a temp file and is hash-compared: identical files are
# kept untouched, replaced files are backed up under replaced-<timestamp>/.
# Password is never echoed; prefer SSHPASS env over -p (visible in ps).
set -euo pipefail

PASSWORD="${SSHPASS:-}"
SKIP_SYMBOLS=0
HOST="192.168.4.114"
USER="sneha"
REMOTE_OUT="Documents/anil/kernel/android-6.12-port-work-slop/out"
DEST="porting/artifacts/snapshot60/kdir-run90"

while getopts "p:H:U:R:D:nh" opt; do
	case "$opt" in
	p) PASSWORD="$OPTARG" ;;
	n) SKIP_SYMBOLS=1 ;;
	H) HOST="$OPTARG" ;;
	U) USER="$OPTARG" ;;
	R) REMOTE_OUT="$OPTARG" ;;
	D) DEST="$OPTARG" ;;
	h) sed -n '2,17p' "$0"; exit 0 ;;
	*) echo "usage: $0 -p <password> [-n] [-H host] [-U user] [-R remote-out-dir] [-D local-dest-dir]" >&2; exit 2 ;;
	esac
done

[[ -n "$PASSWORD" ]] || { echo "missing password: pass -p <password> or set SSHPASS" >&2; exit 2; }
command -v sshpass >/dev/null || { echo "missing tool: sshpass (brew install hudochenkov/sshpass/sshpass)" >&2; exit 1; }
command -v scp >/dev/null || { echo "missing tool: scp" >&2; exit 1; }

[[ -n "$DEST" ]] || { echo "empty destination: pass -D <local-dest-dir>" >&2; exit 2; }
if [[ ! -d "$DEST" ]]; then
	mkdir -p "$DEST" || { echo "cannot create destination: $DEST" >&2; exit 1; }
	echo "-- created destination: $DEST"
fi
REMOTE="$USER@$HOST"

# Probe the remote out dir read-only before pulling anything.
export SSHPASS="$PASSWORD"
sshpass -p "$PASSWORD" ssh -o BatchMode=no -o StrictHostKeyChecking=accept-new \
	"$REMOTE" "test -d '$REMOTE_OUT' && ls '$REMOTE_OUT/.config' '$REMOTE_OUT/arch/arm64/boot/Image.gz' '$REMOTE_OUT/arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb'"

# One config name: earlier pulls landed as .config.
if [[ ! -f "$DEST/kernel.config" && -f "$DEST/.config" ]]; then
	mv "$DEST/.config" "$DEST/kernel.config"
	echo "rename: .config -> kernel.config (name canonicalization, content unchanged)"
fi

BACKUP_DIR="$DEST/replaced-$(date -u +%Y%m%d-%H%M%S)"

pull_one() { # $1 = remote relpath, $2 = dest name
	local rel="$1" base="$2" tmp new_sum old_sum
	tmp="$DEST/.$base.incoming"
	sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=accept-new \
		"$REMOTE:$REMOTE_OUT/$rel" "$tmp"
	new_sum="$(shasum -a 256 "$tmp" | awk '{print $1}')"
	if [[ -f "$DEST/$base" ]]; then
		old_sum="$(shasum -a 256 "$DEST/$base" | awk '{print $1}')"
		if [[ "$new_sum" == "$old_sum" ]]; then
			echo "keep: $base already current ($new_sum)"
			rm -f "$tmp"
			return 0
		fi
		mkdir -p "$BACKUP_DIR"
		mv "$DEST/$base" "$BACKUP_DIR/$base"
		echo "replace: $base $old_sum -> $new_sum (old in $BACKUP_DIR/)"
	else
		echo "new: $base ($new_sum)"
	fi
	mv "$tmp" "$DEST/$base"
}

pull_one arch/arm64/boot/Image.gz Image.gz
pull_one arch/arm64/boot/dts/qcom/msm8953-xiaomi-tissot.dtb msm8953-xiaomi-tissot.dtb
pull_one .config kernel.config
# Image.gz-dtb is a local concatenation, not a kernel build output: rebuild
# it from the just-pulled pair so it can never go stale.
cat "$DEST/Image.gz" "$DEST/msm8953-xiaomi-tissot.dtb" > "$DEST/.Image.gz-dtb.incoming"
new_sum="$(shasum -a 256 "$DEST/.Image.gz-dtb.incoming" | awk '{print $1}')"
if [[ -f "$DEST/Image.gz-dtb" ]]; then
	old_sum="$(shasum -a 256 "$DEST/Image.gz-dtb" | awk '{print $1}')"
	if [[ "$new_sum" == "$old_sum" ]]; then
		echo "keep: Image.gz-dtb already current ($new_sum)"
		rm -f "$DEST/.Image.gz-dtb.incoming"
	else
		mkdir -p "$BACKUP_DIR"
		mv "$DEST/Image.gz-dtb" "$BACKUP_DIR/Image.gz-dtb"
		mv "$DEST/.Image.gz-dtb.incoming" "$DEST/Image.gz-dtb"
		echo "replace: Image.gz-dtb $old_sum -> $new_sum (old in $BACKUP_DIR/)"
	fi
else
	mv "$DEST/.Image.gz-dtb.incoming" "$DEST/Image.gz-dtb"
	echo "new: Image.gz-dtb ($new_sum)"
fi
unset SSHPASS

(cd "$DEST" && shasum -a 256 Image.gz msm8953-xiaomi-tissot.dtb Image.gz-dtb kernel.config > SHA256SUMS && cat SHA256SUMS && shasum -c SHA256SUMS)

# Symbols for decoding oops/SEA PCs (System.map, vmlinux for addr2line).
# Run118 showed why they must come from the same build: a System.map read
# from out/ after a rebuild named the wrong function. Kept out of
# SHA256SUMS (package-diag-boot.py hashes every file listed there) and
# banner-checked against Image.gz so a stale vmlinux is refused.
if [[ "$SKIP_SYMBOLS" != 1 ]]; then
	export SSHPASS="$PASSWORD"
	pull_one System.map System.map
	pull_one vmlinux vmlinux
	unset SSHPASS
	img_banner="$(gzip -dc "$DEST/Image.gz" | LC_ALL=C grep -a -o 'Linux version [^[:cntrl:]]*#[0-9][^[:cntrl:]]*' | head -1 | tr -d '\0' || true)"
	sym_banner="$(LC_ALL=C grep -a -o 'Linux version [^[:cntrl:]]*#[0-9][^[:cntrl:]]*' "$DEST/vmlinux" | head -1 | tr -d '\0' || true)"
	if [[ -z "$img_banner" || "$img_banner" != "$sym_banner" ]]; then
		echo "symbol mismatch: vmlinux is not the build in Image.gz" >&2
		echo "  Image.gz: $img_banner" >&2
		echo "  vmlinux:  $sym_banner" >&2
		exit 1
	fi
	echo "symbols match Image.gz: $img_banner"
	(cd "$DEST" && shasum -a 256 System.map vmlinux > SYMBOLS.SHA256SUMS && cat SYMBOLS.SHA256SUMS)
fi

echo "-- required symbols in pulled kernel.config:"
grep -E '^CONFIG_(TRACEPOINTS|PSTORE_RAM|BLOCK)=' "$DEST/kernel.config" || {
	echo "required CONFIG missing from pulled kernel.config" >&2
	exit 1
}
