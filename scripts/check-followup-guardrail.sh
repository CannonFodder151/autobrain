#!/usr/bin/env bash
# check-followup-guardrail.sh — AUT-1992
# Pre-exit check for Paperclip heartbeats: if a run surfaced follow-up signals
# (TODO, "next step", "create issue", new AUT-XXXX mentions, etc.) but did NOT
# create a child issue for $PAPERCLIP_TASK_ID, exit non-zero and print the
# reminder. Prevents the liveness-checker `needs_followup` defect and the
# "agent claimed AUT-XXXX-1 but never POSTed" hallucination class.
#
# Usage:
#   export PAPERCLIP_TASK_ID=...
#   bash scripts/check-followup-guardrail.sh /path/to/run-transcript.txt
#   # or, with no args: scans $PAPERCLIP_RUN_SCRATCH_DIR for any .txt/.md
#
# Exit codes:
#   0 = pass (no follow-up signals OR children exist)
#   1 = fail (signals present, no children) — run MUST NOT close yet
#   2 = skipped (env not ready or transcript not found) — non-blocking
#
# Companion snippet for the agent (paste at end of heartbeat, before PATCH):
#   bash scripts/check-followup-guardrail.sh "$PAPERCLIP_RUN_SCRATCH_DIR"
#   # if exit 1: create the child, then re-run; do not close the issue.

set -uo pipefail

: "${PAPERCLIP_API_URL:?PAPERCLIP_API_URL required}"
: "${PAPERCLIP_API_KEY:?PAPERCLIP_API_KEY required}"
: "${PAPERCLIP_COMPANY_ID:?PAPERCLIP_COMPANY_ID required}"
: "${PAPERCLIP_TASK_ID:?PAPERCLIP_TASK_ID required (set by the harness on assignment)}"

INPUT="${1:-${PAPERCLIP_RUN_SCRATCH_DIR:-}}"
if [[ -z "$INPUT" ]]; then
  echo "[guardrail] skipped: no transcript path and PAPERCLIP_RUN_SCRATCH_DIR unset" >&2
  exit 2
fi

# Collect transcript files
mapfile -t FILES < <(if [[ -d "$INPUT" ]]; then find "$INPUT" -maxdepth 3 -type f \( -name '*.txt' -o -name '*.md' -o -name '*.log' \) 2>/dev/null; else echo "$INPUT"; fi)
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "[guardrail] skipped: no transcript files under $INPUT" >&2
  exit 2
fi

# Concatenate, cap to 1 MiB to avoid runaway scan
CORPUS=$(cat "${FILES[@]}" 2>/dev/null | head -c 1048576)

# Follow-up signal patterns. Lowercase the corpus for matching.
LC=$(printf '%s' "$CORPUS" | tr '[:upper:]' '[:lower:]')

# Required: skip the noise from AGENTS.md template the agent already inlines
# (i.e. ignore matches inside the verbatim API example block we ship in AGENTS.md).
# Cheap approach: count signals in NON-example lines.
SIGNAL_COUNT=$(printf '%s' "$LC" \
  | grep -oE '\b(todo|follow[- ]?up|next step|create (a |an )?(child|sub[- ]?task|issue)|new (aut|issue)|assignee ?(should|must|will))' \
  | wc -l)

# Heuristic: 2+ signals = the agent likely surfaced follow-up work.
if [[ "$SIGNAL_COUNT" -lt 2 ]]; then
  echo "[guardrail] pass: $SIGNAL_COUNT follow-up signal(s) (threshold 2)"
  exit 0
fi

# Signals present — verify a real child exists for this issue.
RESP=$(curl -s --max-time 10 \
  "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues?parentId=$PAPERCLIP_TASK_ID" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "X-Paperclip-Run-Id: ${PAPERCLIP_RUN_ID:-}")

CHILD_COUNT=$(printf '%s' "$RESP" | python3 -c "
import sys, json
try:
  data = json.load(sys.stdin)
  items = data.get('list', data) if isinstance(data, dict) else data
  if not isinstance(items, list):
    print(-1); sys.exit(0)
  # Count children created during this run window (or all if no run id available)
  run_id = '${PAPERCLIP_RUN_ID:-}'
  if run_id:
    recent = [c for c in items if c.get('originRunId') == run_id or c.get('createdByAgentId') == '${PAPERCLIP_AGENT_ID:-}']
    print(len(recent) or len(items))
  else:
    print(len(items))
except Exception as e:
  print(-1)
")

if [[ "$CHILD_COUNT" -gt 0 ]]; then
  echo "[guardrail] pass: $SIGNAL_COUNT follow-up signal(s) and $CHILD_COUNT child(ren) for $PAPERCLIP_TASK_ID"
  exit 0
fi

cat >&2 <<EOF
[guardrail] FAIL: $SIGNAL_COUNT follow-up signal(s) detected in this run, but 0 children
  for parent $PAPERCLIP_TASK_ID. The liveness checker will mark this needs_followup.

  Required action BEFORE closing the issue:
    POST  $PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues
    body: {"title":"...","description":"...","status":"todo","priority":"high","parentId":"$PAPERCLIP_TASK_ID"}
    assert HTTP 201, copy the real identifier from the response body.

  Or, if you genuinely have no follow-ups: re-run the guardrail on a transcript
  that omits the TODO/next-step phrasing (the heuristic is signal-based).
EOF
exit 1
