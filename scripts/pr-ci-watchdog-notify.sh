#!/usr/bin/env bash
set -euo pipefail

# AUT-500/AUT-655: PR/CI Watchdog routine completion notification
# Usage: pr-ci-watchdog-notify.sh <success|failure|blocked> "<summary with evidence links>" [issue-url]

STATUS="${1:-}"
SUMMARY="${2:-}"
ISSUE_URL="${3:-}"

if [[ -z "$STATUS" || -z "$SUMMARY" ]]; then
  echo "Usage: $0 <success|failure|blocked> \"<summary with evidence links>\" [issue-url]" >&2
  exit 1
fi

# Map status to Discord embed color
case "$STATUS" in
  success) COLOR="0x2ECC71" ;;
  failure|blocked) COLOR="0xE74C3C" ;;
  *) COLOR="0x3498DB" ;;
esac

# POST to Discord using the n8n Discord Reporter webhook
discord_url="${DISCORD_REPORT_WEBHOOK:-}"
if [[ -z "$discord_url" ]]; then
  echo "::warning::DISCORD_REPORT_WEBHOOK not set; skipping Discord notify"
  exit 0
fi

# Guard: webhook URL must be http(s)
case "$discord_url" in
  https://*|http://*) ;;
  *)
    echo "::warning::DISCORD_REPORT_WEBHOOK is not an http(s) URL; skipping Discord notify"
    exit 0
    ;;
esac

jq_payload=$(jq -nc \
  --arg title "PR/CI Watchdog — $STATUS" \
  --arg desc "$SUMMARY" \
  --arg color "$COLOR" \
  --arg status "$STATUS" \
  --arg issue "${ISSUE_URL:-none}" \
  '{channel:"incidents",title:$title,description:$desc,color:$color,author:"PR/CI Watchdog",fields:[{name:"Status",value:$status,inline:true},{name:"Issue",value:$issue,inline:true}]}')

curl -sS --max-time 30 -X POST "$discord_url" \
  -H "Content-Type: application/json" \
  -d "$jq_payload" || echo "::warning::Discord POST failed"