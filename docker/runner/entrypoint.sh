#!/bin/bash
# AUT-2469: entrypoint wrapper for ghcr.io/actions/actions-runner.
# Exchanges a long-lived GitHub PAT (from *_FILE secret) for a short-lived
# registration token, then delegates to the official image /entrypoint.sh.
set -euo pipefail

PAT_FILE="${GITHUB_PAT_FILE:-/run/secrets/github_pat}"
REGISTRATION_TOKEN="${GITHUB_ACTIONS_RUNNER_TOKEN:-}"

if [ -z "$REGISTRATION_TOKEN" ] && [ -f "$PAT_FILE" ]; then
    PAT="$(cat "$PAT_FILE")"
    echo "==> fetching registration token from GitHub API..."
    RESPONSE=$(curl -sf -X POST \
        -H "Authorization: Bearer $PAT" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/runners/registration-token" 2>&1) || true
    if [ -n "$RESPONSE" ]; then
        REGISTRATION_TOKEN=$(printf '%s\n' "$RESPONSE" | sed -n 's/.*"token":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi
    if [ -z "$REGISTRATION_TOKEN" ]; then
        echo "ERROR: failed to obtain registration token" >&2
        echo "Response: $RESPONSE" >&2
        exit 1
    fi
    export GITHUB_ACTIONS_RUNNER_TOKEN="$REGISTRATION_TOKEN"
fi

exec /entrypoint.sh "$@"
