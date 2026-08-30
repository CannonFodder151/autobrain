#!/bin/sh
# AUT-1533: self-check for docker/lib-load-secrets.sh. Run: sh scripts/test-secrets-loader.sh
set -eu
DIR=$(mktemp -d)
LIB="$(dirname "$0")/../docker/lib-load-secrets.sh"
fail() { echo "FAIL: $1"; rm -rf "$DIR"; exit 1; }

printf 's3cr3t' > "$DIR/simple"
printf 'brokerpw' > "$DIR/redis"
printf -- '-----BEGIN RSA PRIVATE KEY-----\nline "quoted" $dollar \nline2\n-----END RSA PRIVATE KEY-----\n' > "$DIR/pem"
: > "$DIR/empty"

# 1. simple value, 2. multiline PEM with quotes/dollars, 3. empty file, 4. missing file skipped.
env SIMPLE_FILE="$DIR/simple" PEM_FILE="$DIR/pem" EMPTY_FILE="$DIR/empty" \
    ABSENT_FILE="$DIR/nope" REDIS_PASSWORD_FILE="$DIR/redis" \
    sh -c '
        . '"$LIB"'
        [ "$SIMPLE" = "s3cr3t" ] || echo "FAIL simple"
        [ "$EMPTY" = "" ] || echo "FAIL empty"
        [ -n "${ABSENT:-}" ] && echo "FAIL absent-set"
        case "$PEM" in *"line \"quoted\" \$dollar"*"line2"*) ;; *) echo "FAIL pem";; esac
        [ "${REDIS_URL:-}" = "redis://:brokerpw@redis:6379/0" ] || echo "FAIL redis_url"
        [ "${CELERY_BROKER_URL:-}" = "redis://:brokerpw@redis:6379/1" ] || echo "FAIL broker"
    ' < /dev/null > "$DIR/out" 2>&1 || true

grep -q FAIL "$DIR/out" && { cat "$DIR/out"; fail "loader assertions"; }
grep -q "loaded SIMPLE from" "$DIR/out" || fail "no load log"

# Explicit REDIS_URL must win (no clobber).
env REDIS_PASSWORD_FILE="$DIR/redis" REDIS_URL="redis://custom" \
    sh -c '. '"$LIB"'; [ "$REDIS_URL" = "redis://custom" ] || exit 1; [ -z "${CELERY_BROKER_URL:-}" ] || exit 1'

rm -rf "$DIR"
echo "OK: secrets loader"
