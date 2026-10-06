#!/bin/sh
# AUT-5134: self-check for docker/preflight-secrets.sh.
# Run: sh scripts/test-preflight-secrets.sh
# No docker daemon needed. Cases 2 and 5 need a uid that is NOT root
# (root bypasses read permission, so the unreadable-file branch cannot
# be provoked as root); they are skipped with a notice when run as root.
set -eu

LIB="$(dirname "$0")/../docker/preflight-secrets.sh"
DIR=$(mktemp -d)
trap 'chmod -R u+rwx "$DIR" 2>/dev/null || true; rm -rf "$DIR"' EXIT
fails=0

fail() { echo "FAIL: $1"; fails=$((fails + 1)); }
pass() { echo "ok: $1"; }

# 1. Correct perms (dir 0750, file 0640) pass.
mkdir -p "$DIR/run/secrets"
printf 's3cr3t' >"$DIR/run/secrets/redis_password"
chmod 0750 "$DIR/run/secrets"
chmod 0640 "$DIR/run/secrets/redis_password"
if REDIS_PASSWORD_FILE="$DIR/run/secrets/redis_password" sh "$LIB" >/dev/null 2>&1; then
    pass "0750 dir + 0640 file is accepted"
else
    fail "0750 dir + 0640 file was rejected"
fi

# 2. The real AUT-5125 fault: dir 0640 has no traverse bit. Every *_FILE
#    load then dies with "Permission denied" and the container loops.
chmod 0640 "$DIR/run/secrets"
out=$(REDIS_PASSWORD_FILE="$DIR/run/secrets/redis_password" sh "$LIB" 2>&1) && rc=0 || rc=$?
if [ "$rc" = 1 ]; then
    pass "0640 dir fails fast (exit 1)"
else
    fail "0640 dir exited $rc, expected 1"
fi
if [ "$(printf '%s\n' "$out" | wc -l)" = 1 ]; then
    pass "error is a single line"
else
    fail "expected one line, got: $out"
fi
for needle in "$DIR/run/secrets/redis_password" "0750 root:1000" "0640 root:1000" "chmod 750"; do
    if printf '%s' "$out" | grep -q "$needle"; then
        pass "error names '$needle'"
    else
        fail "error missing '$needle': $out"
    fi
done
chmod 0750 "$DIR/run/secrets"

# 3. A missing optional credential stays optional (loader skips it).
if SMTP_PASSWORD_FILE="$DIR/run/secrets/not_provisioned" sh "$LIB" >/dev/null 2>&1; then
    pass "missing optional secret is skipped"
else
    fail "missing optional secret was fatal"
fi

# 4. No *_FILE env at all (plain env deployment) is not a fault.
if sh "$LIB" >/dev/null 2>&1; then
    pass "no *_FILE env exits 0"
else
    fail "no *_FILE env exited non-zero"
fi

# 5. A file that exists but cannot be read is fatal. Owner class with no
#    read bit reproduces it without root.
if [ "$(id -u)" = 0 ]; then
    echo "skip: unreadable-file case needs a non-root uid"
else
    chmod 0200 "$DIR/run/secrets/redis_password"
    out=$(REDIS_PASSWORD_FILE="$DIR/run/secrets/redis_password" sh "$LIB" 2>&1) && rc=0 || rc=$?
    if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q "not readable"; then
        pass "unreadable secret file fails fast"
    else
        fail "unreadable secret file: rc=$rc out=$out"
    fi
    chmod 0640 "$DIR/run/secrets/redis_password"
fi

# 6. A dir with no execute bit at all is reported even for root (root still
#    needs one execute bit to traverse), so this case is not skipped.
chmod 0644 "$DIR/run/secrets"
if REDIS_PASSWORD_FILE="$DIR/run/secrets/redis_password" sh "$LIB" >/dev/null 2>&1; then
    fail "0644 dir (group/other r-x) was accepted — expected failure for uid $(id -u)"
else
    pass "0644 dir is rejected"
fi

if [ "$fails" = 0 ]; then echo "OK: preflight-secrets.sh"; else echo "$fails failure(s)"; exit 1; fi