#!/bin/sh
# Run logging/collect-logs.sh on the phone and pull the result into
# ./logs/<date-time>/ so each boot attempt keeps its own directory.
#
#   ./pull-logs.sh [ssh-host]        default: user@172.16.42.1
#
# Password auth goes through generated expect scripts (macOS ships expect).
# Override the password with PMOS_PASSWORD=... if it ever changes.
set -eu

HOST=${1:-user@172.16.42.1}
HERE=$(cd "$(dirname "$0")" && pwd)
PASS=${PMOS_PASSWORD:-147147}
STAMP=$(date -u '+%Y%m%d-%H%M%S')
DEST="$HERE/logs/$STAMP"
REMOTE=/tmp/port-logs-$STAMP.tar
EXP=$(mktemp -d)
trap 'rm -rf "$EXP"' EXIT

SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o PreferredAuthentications=password -o PubkeyAuthentication=no"

# expect does not survive inline quoting, so write real scripts.
cat > "$EXP/push.exp" <<EOF
#!/usr/bin/expect -f
set timeout 300
spawn scp $SSH_OPTS $HERE/collect-logs.sh $HOST:/tmp/collect-logs.sh
expect {
    -re "(?i)password:" { send "$PASS\\r"; exp_continue }
    eof
}
catch wait result
exit [lindex \$result 3]
EOF

cat > "$EXP/ssh.exp" <<EOF
#!/usr/bin/expect -f
set timeout 600
spawn ssh -tt $SSH_OPTS $HOST \$env(CMD)
expect {
    -re "(?i)password:" { send "$PASS\\r"; exp_continue }
    eof
}
catch wait result
exit [lindex \$result 3]
EOF

cat > "$EXP/pull.exp" <<EOF
#!/usr/bin/expect -f
set timeout 600
spawn scp $SSH_OPTS $HOST:$REMOTE $DEST/logs.tar
expect {
    -re "(?i)password:" { send "$PASS\\r"; exp_continue }
    eof
}
catch wait result
exit [lindex \$result 3]
EOF

chmod +x "$EXP"/*.exp
mkdir -p "$DEST"

echo "==> uploading collector to $HOST"
"$EXP/push.exp" >/dev/null

echo "==> running collector (root needed for /sys/fs/pstore)"
CMD="doas sh /tmp/collect-logs.sh $REMOTE" "$EXP/ssh.exp" | tail -20

echo "==> pulling $REMOTE"
"$EXP/pull.exp" >/dev/null

( cd "$DEST" && tar xf logs.tar && rm -f logs.tar )

if [ -d "$DEST/pstore" ] && [ -n "$(ls -A "$DEST/pstore" 2>/dev/null)" ]; then
	python3 "$HERE/decode-pstore.py" "$DEST"/pstore/* > "$DEST/pstore-decoded.txt" 2>&1 || true
	echo "==> decoded pstore records into $DEST/pstore-decoded.txt"
fi

echo "==> saved to $DEST"
[ -f "$DEST/summary.txt" ] && sed -n '1,25p' "$DEST/summary.txt"