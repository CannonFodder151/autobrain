#!/bin/sh
# AUT-5134: deterministic secrets preflight — runs as the container uid (1000)
# before any bootstrap, so a host-side secrets dir that lost its read/traverse
# perms fails in seconds with ONE actionable line instead of a silent crash
# loop. Real outage: on 2026-09 the hosted `/data/autobrain/secrets` was mode
# 0640 (no traverse bit), so every `*_FILE` load failed with
# `cat: /run/secrets/<name>: Permission denied`, Settings() validation failed
# and the backend exit-1'd in a restart loop for ~16 min with no alert.
#
# Contract (keep in sync with scripts/seed-secrets.sh + the deployment guide):
#   secrets dir  0750 root:1000   (uid/gid 1000 needs r-x to traverse)
#   secret files 0640 root:1000   (group 1000 needs r to read)
#
# Optional credentials stay optional: a `*_FILE` path that simply does not exist
# is skipped, exactly like lib-load-secrets.sh. Only PERMISSION faults are
# fatal — that is the difference between a clear boot error and the loop this
# closes.
#
# Exit codes: 0 = every referenced secret is readable; 1 = a permission fault
# (message on stderr); 2 = preflight could not run (e.g. no env).
set -u

# Host path is only used to print the exact remediation command; inside the
# container the secrets dir is bind-mounted at the *_FILE targets.
SECRETS_HOST_DIR="${SECRETS_HOST_DIR:-/data/autobrain/secrets}"
REQUIRED="required: secrets dir 0750 root:1000, secret files 0640 root:1000"

fault() {
    # One line, offending path + what is wrong with it + required mode + fix.
    echo "autobrain preflight: $1 — $REQUIRED; fix on host: $2" >&2
    exit 1
}

files=$(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)_FILE=.*/\1/p')
[ -n "$files" ] || exit 0

for var in $files; do
    eval "path=\${${var}_FILE:-}"
    [ -n "$path" ] || continue
    dir=$(dirname "$path")
    # No directory at all => nothing is mounted here; plain env is being used.
    [ -d "$dir" ] || continue

    if [ ! -x "$dir" ]; then
        got=$(stat -c '%a %U:%G' "$dir" 2>/dev/null || echo "mode unknown")
        fault "$path unreadable: dir $dir is [$got], not traversable by uid $(id -u)/gid $(id -g)" \
              "chown root:1000 $SECRETS_HOST_DIR && chmod 750 $SECRETS_HOST_DIR"
    fi

    # Only a file that exists but cannot be read is a fault; a missing optional
    # credential keeps the loader's skip-and-continue behaviour.
    if [ -e "$path" ] && [ ! -r "$path" ]; then
        got=$(stat -c '%a %U:%G' "$path" 2>/dev/null || echo "mode unknown")
        fault "$path not readable: file is [$got], uid $(id -u)/gid $(id -g) has no read bit" \
              "chown root:1000 $SECRETS_HOST_DIR/* && chmod 640 $SECRETS_HOST_DIR/*"
    fi
done

exit 0
