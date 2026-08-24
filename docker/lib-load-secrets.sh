#!/bin/sh
# AUT-1533 (AB-SEC): load secret-class env vars from *_FILE files.
# Sourced by docker/entrypoint.sh (backend/worker) and docker/ai/entrypoint.sh.
# Values live only in bind-mounted files (/run/secrets, root:1000 0640) — never
# in container env at `docker inspect` / /proc/*/environ time. Any var FOO with
# FOO_FILE pointing at an existing file gets exported from that file; missing
# files are skipped so optional credentials stay optional (parity with the old
# ${FOO:-} defaults).
set -u

for var in $(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)_FILE=.*/\1/p'); do
    eval "path=\${${var}_FILE}"
    if [ -f "$path" ]; then
        val=$(cat "$path")
        export "$var=$val"
        echo "[secrets] loaded $var from $path"
    fi
done

# AB-INFRA-004: derive authenticated redis URLs from the broker password file
# so the password never appears in plain env either. ponytail: hardcodes the
# compose service name/db indexes; revisit if a stack renames redis or remaps
# logical DBs.
if [ -n "${REDIS_PASSWORD_FILE:-}" ] && [ -f "$REDIS_PASSWORD_FILE" ] && [ -z "${REDIS_URL:-}" ]; then
    redis_pw=$(cat "$REDIS_PASSWORD_FILE")
    export REDIS_URL="redis://:${redis_pw}@redis:6379/0"
    export CELERY_BROKER_URL="redis://:${redis_pw}@redis:6379/1"
    export CELERY_RESULT_BACKEND="redis://:${redis_pw}@redis:6379/2"
    unset redis_pw
    echo "[secrets] derived authenticated REDIS_URL/CELERY_*_URL from $REDIS_PASSWORD_FILE"
fi
