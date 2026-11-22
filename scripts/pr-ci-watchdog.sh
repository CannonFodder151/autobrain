#!/usr/bin/env bash
# pr-ci-watchdog.sh — AUT-649 PR/CI Watchdog routine.
#
# Triggered by .github/workflows/pr-ci-watchdog.yml on workflow_run completion
# (conclusion=failure). Per failed run:
#   1. Fetch job logs from the GitHub Actions API
#   2. Create a GitHub issue with failure details + logs
#   3. Create a Paperclip execution issue to wake the DevOps/Backend agent
#   4. Add postmortem template + MTTR labels to the GitHub issue
#   5. Set GitHub Action outputs (github_issue_url, paperclip_issue_url)
#
# Env (provided by the workflow):
#   FAILED_RUN_ID, FAILED_RUN_URL, FAILED_WORKFLOW, FAILED_BRANCH,
#   FAILED_SHA, FAILED_REPO
#   PAPERCLIP_API_URL, PAPERCLIP_COMPANY_ID
#   GH_TOKEN, PR_CI_WATCHDOG_WEBHOOK_SECRET, DISCORD_REPORT_WEBHOOK
set -euo pipefail

: "${FAILED_RUN_ID:?FAILED_RUN_ID required}"
: "${FAILED_RUN_URL:?FAILED_RUN_URL required}"
: "${FAILED_WORKFLOW:?FAILED_WORKFLOW required}"
: "${FAILED_BRANCH:?FAILED_BRANCH required}"
: "${FAILED_SHA:?FAILED_SHA required}"
: "${FAILED_REPO:?FAILED_REPO required}"
: "${PAPERCLIP_API_URL:?PAPERCLIP_API_URL required}"
: "${PAPERCLIP_COMPANY_ID:?PAPERCLIP_COMPANY_ID required}"
: "${GH_TOKEN:?GH_TOKEN required}"

# --- helpers ---------------------------------------------------------------

gh_api() {
  # Call the GitHub REST API with the repo-scoped token.
  gh api -H "Authorization: Bearer $GH_TOKEN" "$@"
}

log() { echo "[pr-ci-watchdog] $*"; }

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Map a failed workflow name to the agent that should own its fix.
owner_agent_for_workflow() {
  case "$1" in
    "Backend tests") echo "Backend Engineer" ;;
    "PR Checks") echo "Frontend Engineer" ;;
    "Security — PR gate (secrets, IaC, deps, flutter)"|"Security — full-resolution dependency scan"|"Security — rego-lookup-api PR dependency gate") echo "Security Officer" ;;
    "Publish images to Docker Hub"|"Build hosted images (multi-arch)"|"Build Shop images (private registry)"|"Upgrade instance chain (AUT-4982)") echo "DevOps Engineer" ;;
    "Compose structural checks") echo "Platform Engineer" ;;
    "Sync mobile app") echo "Mobile Release Engineer" ;;
    "Visual regression (desktop 1280/1440/1920)") echo "Frontend Engineer" ;;
    *) echo "DevOps Engineer" ;;
  esac
}

# Map agent name to Paperclip agent ID for issue assignment (wake agent).
agent_id_for_agent() {
  case "$1" in
    "DevOps Engineer") echo "6764b91c-3ed1-4a04-89b1-0395f72dd31a" ;;
    "Backend Engineer") echo "d98f790f-a1f8-4cd6-b69c-f174f1df6df0" ;;
    "Frontend Engineer") echo "cb213090-e7da-42b8-8e6c-98b1cc958296" ;;
    "Security Officer") echo "8724e44a-dbe4-4c8b-88a0-cc869ec5d245" ;;
    "Platform Engineer") echo "ed65484d-9f28-44f7-93e9-564d52d8536a" ;;
    "Mobile Release Engineer") echo "94fa93b9-0f26-44a2-bd87-4595acbed593" ;;
    "QA Lead") echo "0b3e4293-cfc2-44dd-8864-037a0c155802" ;;
    "Code Reviewer") echo "96ffe367-8c47-47ac-9283-f12d36a7a2ba" ;;
    "Documentation Manager") echo "a1f18cce-8e16-46b2-a427-d7f374a97488" ;;
    "CTO") echo "96ee06bb-8a7f-4d71-99bf-7173a9c11dff" ;;
    "CEO") echo "327762e1-6833-4ccc-8582-8e5635499b5e" ;;
    "Founding Engineer") echo "991b8240-4f16-4aca-9d9e-1f2cc74afd8d" ;;
    "SEO Designer") echo "964e9131-3341-4a5f-b599-ad7499a5a012" ;;
    "Discord Integration Engineer") echo "cc38e088-7a39-4629-a9b1-50fb9a34830b" ;;
    "CFO") echo "cdb579f8-7a32-4cd0-8f27-df58962cd4ba" ;;
    "Critical Reviewer") echo "79bffa06-a7ad-419c-88e9-071604918e60" ;;
    "Strategic Director") echo "5aae4f23-1778-4a3e-bde9-cbbf79636f84" ;;
    *) echo "" ;;
  esac
}

# --- step 1: gather failure details ----------------------------------------

log "Gathering failure details for run $FAILED_RUN_ID ($FAILED_WORKFLOW)"

# List jobs for the failed run to find the one(s) that failed.
jobs_json=$(gh_api "repos/$FAILED_REPO/actions/runs/$FAILED_RUN_ID/jobs" \
  --jq '.jobs[] | select(.conclusion=="failure") | {id, name, steps: [.steps[] | select(.conclusion=="failure") | {name, number}]} | @json' 2>/dev/null || echo "")

if [ -z "$jobs_json" ]; then
  log "No failed jobs found via jobs API; checking run conclusion directly"
  run_conclusion=$(gh_api "repos/$FAILED_REPO/actions/runs/$FAILED_RUN_ID" --jq '.conclusion' 2>/dev/null || echo "failure")
  log "Run conclusion: $run_conclusion"
fi

# Collect failed step names for the issue body.
failed_steps=""
while IFS= read -r line; do
  [ -z "$line" ] && continue
  job_name=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['name'])")
  steps=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(', '.join(s['name'] for s in d['steps']))")
  failed_steps+="  * Job: $job_name — failed steps: $steps"$'\n'
done <<< "$jobs_json"

# --- step 2: fetch logs for failed steps -----------------------------------

log "Fetching job logs"
log_section="### Failed Jobs & Logs
$(date -u +%Y-%m-%dT%H:%M:%SZ) UTC

Workflow: **$FAILED_WORKFLOW**
Branch: **$FAILED_BRANCH**
SHA: **$FAILED_SHA**
Run: [#$(echo "$FAILED_RUN_URL" | sed 's#.*/actions/runs/##')]($FAILED_RUN_URL)

"

# Append per-step logs (truncated to keep issue body manageable).
while IFS= read -r line; do
  [ -z "$line" ] && continue
  job_id=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id'])")
  job_name=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['name'])")
  log_section+="
#### Job: $job_name (id: $job_id)

"
  # Try to download the full job log (gh api follows the redirect to the log URL).
  if log_text=$(gh_api "repos/$FAILED_REPO/actions/jobs/$job_id/logs" 2>/dev/null); then
    # Truncate to last 300 lines to avoid bloating the issue.
    log_section+='```text'
    log_section+="
$(echo "$log_text" | tail -n 300)
"
    log_section+='```'
  else
    log_section+="*Log fetch failed for job $job_id*"
  fi
done <<< "$jobs_json"

# --- step 3: create GitHub issue ------------------------------------------

log "Creating GitHub issue"

OWNER_AGENT=$(owner_agent_for_workflow "$FAILED_WORKFLOW")
ISSUE_TITLE="[CI Failure] $FAILED_WORKFLOW failed on $FAILED_BRANCH @ $(echo "$FAILED_SHA" | cut -c1-7)"

# Build the issue body with postmortem template.
ISSUE_BODY=$(cat <<ISSUEBODY
## CI Failure: $FAILED_WORKFLOW

**Detected:** $(now_iso) UTC
**Workflow:** $FAILED_WORKFLOW
**Branch:** $FAILED_BRANCH
**Commit:** [$FAILED_SHA]($FAILED_RUN_URL/commit/$FAILED_SHA)
**Run:** [#$(echo "$FAILED_RUN_URL" | sed 's#.*/actions/runs/##')]($FAILED_RUN_URL)
**Owner Agent:** $OWNER_AGENT

$log_section

---

### Postmortem Template

\`\`\`
## Incident Summary
- **What failed:** $FAILED_WORKFLOW on branch $FAILED_BRANCH
- **When:** $(now_iso) UTC
- **Detected by:** PR/CI Watchdog (automated)
- **Severity:** TBD
- **Impact:** TBD

## Root Cause
TBD — owner agent to complete.

## Immediate Fix
TBD

## Prevention
TBD

## MTTR
- **Detection time:** $(now_iso) UTC
- **Resolution time:** TBD
- **MTTR:** TBD
\`\`\`

---

### Labels for MTTR tracking
- `ci-failure` — this issue tracks a CI failure
- `mttr:open` — MTTR clock is running (resolved when closed)
- `watchdog:auto-created` — created by PR/CI Watchdog automation

cc: @$OWNER_AGENT
ISSUEBODY
)

# Use gh to create the issue.
issue_create_out=$(gh issue create \
  --repo "$FAILED_REPO" \
  --title "$ISSUE_TITLE" \
  --body "$ISSUE_BODY" \
  --label "ci-failure,mttr:open,watchdog:auto-created" \
  2>&1) || {
  log "ERROR: gh issue create failed: $issue_create_out"
  exit 1
}

GITHUB_ISSUE_URL=$(echo "$issue_create_out" | tail -1)
GITHUB_ISSUE_NUMBER=$(echo "$GITHUB_ISSUE_URL" | sed 's#.*/issues/##')

log "GitHub issue created: $GITHUB_ISSUE_URL"

# --- step 4: create Paperclip issue to wake the agent ----------------------

log "Creating Paperclip execution issue to wake $OWNER_AGENT agent"

# Look up Paperclip agent ID for the owner agent (wake agent via assignment).
PAPERCLIP_OWNER_AGENT_ID="$(agent_id_for_agent "$OWNER_AGENT")"
if [ -z "$PAPERCLIP_OWNER_AGENT_ID" ]; then
  log "WARNING: No Paperclip agent ID for owner agent '$OWNER_AGENT'; issue will be unassigned"
fi

PAPERCLIP_ISSUE_TITLE="CI Failure: $FAILED_WORKFLOW on $FAILED_BRANCH"
PAPERCLIP_ISSUE_DESC=$(cat <<PAPERDESC
**GitHub Issue:** $GITHUB_ISSUE_URL
**Failed Workflow:** $FAILED_WORKFLOW
**Branch:** $FAILED_BRANCH
**Commit:** $FAILED_SHA
**Run URL:** $FAILED_RUN_URL
**Detected:** $(now_iso) UTC

This issue was auto-created by the PR/CI Watchdog (AUT-649).
Owner agent: $OWNER_AGENT
MTTR tracking: detection time $(now_iso) UTC.

Please triage, assign the correct owner, and close the linked GitHub issue when resolved.
PAPERDESC
)

# Try to create a Paperclip issue via the control plane API.
# Auth: use a service account PAT if available, otherwise skip gracefully.
PAPERCLIP_ISSUE_URL=""
if [ -n "${PAPERCLIP_SERVICE_TOKEN:-}" ]; then
  # Build jq args conditionally for assigneeAgentId
  jq_args=(--arg title "$PAPERCLIP_ISSUE_TITLE" --arg desc "$PAPERCLIP_ISSUE_DESC" --arg status "todo" --arg companyId "$PAPERCLIP_COMPANY_ID")
  jq_filter='{title:$title,description:$desc,status:$status,company_id:$companyId}'
  if [ -n "$PAPERCLIP_OWNER_AGENT_ID" ]; then
    jq_args+=(--arg assigneeAgentId "$PAPERCLIP_OWNER_AGENT_ID")
    jq_filter='{title:$title,description:$desc,status:$status,company_id:$companyId,assigneeAgentId:$assigneeAgentId}'
  fi

  paperclip_resp=$(curl -sS --max-time 30 \
    -X POST "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues" \
    -H "Authorization: Bearer $PAPERCLIP_SERVICE_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$(jq -nc "${jq_args[@]}" "$jq_filter")" 2>/dev/null) || echo "{}"

  PAPERCLIP_ISSUE_URL=$(echo "$paperclip_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || echo "")
  if [ -n "$PAPERCLIP_ISSUE_URL" ]; then
    log "Paperclip issue created: $PAPERCLIP_ISSUE_URL"
    [ -n "$PAPERCLIP_OWNER_AGENT_ID" ] && log "Assigned to agent ID: $PAPERCLIP_OWNER_AGENT_ID"
  else
    log "WARNING: Paperclip issue creation returned no URL: $paperclip_resp"
  fi
else
  log "PAPERCLIP_SERVICE_TOKEN not set — skipping Paperclip issue creation"
fi

# --- step 5: set GitHub Action outputs -------------------------------------

echo "github_issue_url=$GITHUB_ISSUE_URL" >> "$GITHUB_OUTPUT"
echo "github_issue_number=$GITHUB_ISSUE_NUMBER" >> "$GITHUB_OUTPUT"
echo "paperclip_issue_url=$PAPERCLIP_ISSUE_URL" >> "$GITHUB_OUTPUT"
echo "owner_agent=$OWNER_AGENT" >> "$GITHUB_OUTPUT"
[ -n "$PAPERCLIP_OWNER_AGENT_ID" ] && echo "owner_agent_id=$PAPERCLIP_OWNER_AGENT_ID" >> "$GITHUB_OUTPUT"

log "Watchdog complete. GitHub issue: $GITHUB_ISSUE_URL"