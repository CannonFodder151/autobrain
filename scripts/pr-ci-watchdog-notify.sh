#!/usr/bin/env bash
set -euo pipefail

# AUT-500: PR/CI Watchdog routine completion notification
# Usage: pr-ci-watchdog-notify.sh <success|failure|blocked> "<summary with evidence links>" [issue-url]

STATUS="${1:-}"
SUMMARY="${2:-}"
ISSUE_URL="${3:-}"
ROUTINE_TITLE="PR/CI Watchdog"
NOTIFY="/paperclip/instances/default/workspaces/5aae4f23-1778-4a3e-bde9-cbbf79636f84/discord_notify.sh"

if [[ -z "$STATUS" || -z "$SUMMARY" ]]; then
  echo "Usage: $0 <success|failure|blocked> \"<summary with evidence links>\" [issue-url]" >&2
  exit 1
fi

"$NOTIFY" "$STATUS" "$ROUTINE_TITLE" "$SUMMARY" "$ISSUE_URL"
