#!/usr/bin/env bash
# test_pr_ci_watchdog.sh — Self-check for the PR/CI Watchdog script.
#
#   ./scripts/test_pr_ci_watchdog.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WATCHDOG="$ROOT/scripts/pr-ci-watchdog.sh"
NOTIFY="$ROOT/scripts/pr-ci-watchdog-notify.sh"

W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
cd "$W"
mkdir -p bin

# --- Mock gh API ---
cat > bin/gh <<'EOF'
#!/usr/bin/env bash
case "$1" in
  api)
    case "$2" in
      "repos/test/repo/actions/runs/12345/jobs")
        printf '{"id":67890,"name":"pytest","steps":[{"name":"Run tests","number":1}]}\n'
        ;;
      "repos/test/repo/actions/jobs/67890/logs")
        echo "Running tests..."
        echo "FAILED test"
        ;;
      "repos/test/repo/actions/runs/12345")
        echo '{"conclusion": "failure"}'
        ;;
      *)
        echo "{}"
        ;;
    esac
    ;;
  issue)
    if [[ "$2" == "create" ]]; then
      echo "https://github.com/test/repo/issues/42"
    fi
    ;;
  *)
    exec /usr/bin/gh "$@"
    ;;
esac
EOF
chmod +x bin/gh

# --- Mock curl ---
cat > bin/curl <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"Authorization: Bearer"* ]]; then
  echo '{"url": "https://paperclip2.nathanmartina.com/issues/100", "id": "100"}'
  exit 0
fi
exit 0
EOF
chmod +x bin/curl

# --- Mock jq ---
cat > bin/jq <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "-nc" ]]; then
  # Capture jq output for verification
  has_assignee=0
  for arg in "\$@"; do
    if [[ "\$arg" == *"assigneeAgentId"* ]]; then
      has_assignee=1
    fi
  done
  if [[ \$has_assignee -eq 1 ]]; then
    echo '{"title":"Test","description":"Test","status":"todo","company_id":"test","assignee_agent_id":"d98f790f-a1f8-4cd6-b69c-f174f1df6df0"}' > "$W/jq_output"
    cat "$W/jq_output"
  else
    echo '{"title":"Test","description":"Test","status":"todo","company_id":"test"}'
  fi
  exit 0
fi
exec /usr/bin/jq "\$@"
EOF
chmod +x bin/jq

# --- Mock python3 ---
cat > bin/python3 <<'EOF'
#!/usr/bin/env bash
input=$(cat)
arg="$*"
if echo "$arg" | grep -q "d\['name'\]"; then
  echo "$input" | sed 's/.*"name":"\([^"]*\)".*/\1/'
  exit 0
fi
if echo "$arg" | grep -q "d\['id'\]"; then
  echo "$input" | sed 's/.*"id":\([0-9]*\).*/\1/'
  exit 0
fi
if echo "$arg" | grep -q "d\['steps'\]"; then
  echo "$input" | sed 's/.*"steps":\[\(.*\)\].*/\1/' | sed 's/.*"name":"\([^"]*\)".*/\1/g'
  exit 0
fi
if echo "$arg" | grep -q "d.get('url'"; then
  echo "$input" | sed 's/.*"url": *"\([^"]*\)".*/\1/'
  exit 0
fi
exec /usr/bin/python3 "$@" <<< "$input"
EOF
chmod +x bin/python3

# --- Mock date ---
cat > bin/date <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "-u" && "$2" == "+%Y-%m-%dT%H:%M:%SZ" ]]; then
  echo "2026-11-22T12:00:00Z"
  exit 0
fi
exec /usr/bin/date "$@"
EOF
chmod +x bin/date

export PATH="$W/bin:$PATH"
export PAPERCLIP_API_URL="https://paperclip2.nathanmartina.com"
export PAPERCLIP_COMPANY_ID="df33b840-b692-45ba-9a95-62d2341c95e6"
export GH_TOKEN="mock-token"
export PAPERCLIP_SERVICE_TOKEN="mock-paperclip-token"
export DISCORD_REPORT_WEBHOOK="https://n8n.nathanmartina.com/webhook/discord-report"
export PR_CI_WATCHDOG_WEBHOOK_SECRET="mock-webhook-secret"

FAILURES=0
pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*"; FAILURES=$((FAILURES+1)); }

# --- Test 1: owner_agent_for_workflow function ---
echo "==> Test: owner_agent_for_workflow maps workflows to agents"
sed -n '/^owner_agent_for_workflow()/,/^}/p' "$WATCHDOG" > "$W/owner_fn.sh"
source "$W/owner_fn.sh"

check_map() {
  local workflow="$1" expected="$2"
  local actual
  actual="$(owner_agent_for_workflow "$workflow")"
  if [[ "$actual" == "$expected" ]]; then
    pass "$workflow -> $expected"
  else
    fail "$workflow -> expected $expected, got $actual"
  fi
}

check_map "Backend tests" "Backend Engineer"
check_map "PR Checks" "Frontend Engineer"
check_map "Security — PR gate (secrets, IaC, deps, flutter)" "Security Officer"
check_map "Security — full-resolution dependency scan" "Security Officer"
check_map "Security — rego-lookup-api PR dependency gate" "Security Officer"
check_map "Publish images to Docker Hub" "DevOps Engineer"
check_map "Build hosted images (multi-arch)" "DevOps Engineer"
check_map "Build Shop images (private registry)" "DevOps Engineer"
check_map "Upgrade instance chain (AUT-4982)" "DevOps Engineer"
check_map "Compose structural checks" "Platform Engineer"
check_map "Sync mobile app" "Mobile Release Engineer"
check_map "Visual regression (desktop 1280/1440/1920)" "Frontend Engineer"
check_map "Unknown workflow" "DevOps Engineer"

# --- Test 1b: agent_id_for_agent maps agent names to Paperclip IDs ---
echo "==> Test: agent_id_for_agent maps agent names to Paperclip agent IDs"
sed -n '/^agent_id_for_agent()/,/^}/p' "$WATCHDOG" > "$W/agent_id_fn.sh"
source "$W/agent_id_fn.sh"

check_agent_id() {
  local agent="$1" expected="$2"
  local actual
  actual="$(agent_id_for_agent "$agent")"
  if [[ "$actual" == "$expected" ]]; then
    pass "$agent -> $expected"
  else
    fail "$agent -> expected $expected, got $actual"
  fi
}

check_agent_id "DevOps Engineer" "6764b91c-3ed1-4a04-89b1-0395f72dd31a"
check_agent_id "Backend Engineer" "d98f790f-a1f8-4cd6-b69c-f174f1df6df0"
check_agent_id "Frontend Engineer" "cb213090-e7da-42b8-8e6c-98b1cc958296"
check_agent_id "Security Officer" "8724e44a-dbe4-4c8b-88a0-cc869ec5d245"
check_agent_id "Platform Engineer" "ed65484d-9f28-44f7-93e9-564d52d8536a"
check_agent_id "Mobile Release Engineer" "94fa93b9-0f26-44a2-bd87-4595acbed593"
check_agent_id "QA Lead" "0b3e4293-cfc2-44dd-8864-037a0c155802"
check_agent_id "Unknown agent" ""

# --- Test 2: Full watchdog execution ---
echo "==> Test: Full watchdog execution creates GitHub issue"
export FAILED_RUN_ID="12345"
export FAILED_RUN_URL="https://github.com/test/repo/actions/runs/12345"
export FAILED_WORKFLOW="Backend tests"
export FAILED_BRANCH="feature/test-branch"
export FAILED_SHA="abc123def456"
export FAILED_REPO="test/repo"
export GITHUB_OUTPUT="$W/github_output"

output="$(bash "$WATCHDOG" 2>&1)" || true
if echo "$output" | grep -q "GitHub issue created: https://github.com/test/repo/issues/42"; then
  pass "Watchdog creates GitHub issue"
else
  fail "Watchdog did not create GitHub issue. Output: $output"
fi

if [[ -f "$GITHUB_OUTPUT" ]]; then
  if grep -q "github_issue_url=https://github.com/test/repo/issues/42" "$GITHUB_OUTPUT"; then
    pass "GitHub issue URL output set"
  else
    fail "GitHub issue URL not in output"
  fi
  if grep -q "paperclip_issue_url=https://paperclip2.nathanmartina.com/issues/100" "$GITHUB_OUTPUT"; then
    pass "Paperclip issue URL output set"
  else
    fail "Paperclip issue URL not in output"
  fi
  if grep -q "owner_agent=Backend Engineer" "$GITHUB_OUTPUT"; then
    pass "Owner agent output set"
  else
    fail "Owner agent not in output"
  fi
  if grep -q "owner_agent_id=d98f790f-a1f8-4cd6-b69c-f174f1df6df0" "$GITHUB_OUTPUT"; then
    pass "Owner agent ID output set"
  else
    fail "Owner agent ID not in output"
  fi
else
  fail "GITHUB_OUTPUT file not created"
fi

# Verify assignee_agent_id was passed to Paperclip API (via jq output)
if [[ -f "$W/jq_output" ]] && grep -q "assignee_agent_id" "$W/jq_output"; then
  pass "assignee_agent_id passed to Paperclip API"
else
  fail "assignee_agent_id not passed to Paperclip API. jq_output: $(cat "$W/jq_output" 2>/dev/null || echo '(none)')"
fi

# --- Test 3: Notify script ---
echo "==> Test: pr-ci-watchdog-notify.sh runs without error"
# Just test it runs and validates args
notify_output="$(bash "$NOTIFY" 2>&1)" || true
if echo "$notify_output" | grep -q "Usage:"; then
  pass "Notify script shows usage on missing args"
else
  fail "Notify script missing usage message. Output: $notify_output"
fi

if bash "$NOTIFY" success "Test summary" "https://github.com/test/repo/issues/42" >/dev/null 2>&1; then
  pass "Notify script executes successfully"
else
  fail "Notify script execution failed"
fi

if bash "$NOTIFY" failure "Test failure summary" "https://github.com/test/repo/issues/42" >/dev/null 2>&1; then
  pass "Notify script executes with failure status"
else
  fail "Notify script execution with failure failed"
fi

if bash "$NOTIFY" blocked "Test blocked summary" "" >/dev/null 2>&1; then
  pass "Notify script executes with blocked status"
else
  fail "Notify script execution with blocked failed"
fi

# --- Test 4: Watchdog handles missing PAPERCLIP_SERVICE_TOKEN ---
echo "==> Test: Watchdog handles missing PAPERCLIP_SERVICE_TOKEN gracefully"
export PAPERCLIP_SERVICE_TOKEN=""
export GITHUB_OUTPUT="$W/github_output2"

output="$(bash "$WATCHDOG" 2>&1)" || true
if echo "$output" | grep -q "PAPERCLIP_SERVICE_TOKEN not set"; then
  pass "Watchdog warns about missing PAPERCLIP_SERVICE_TOKEN"
else
  fail "Watchdog did not warn about missing token. Output: $output"
fi

if [[ -f "$GITHUB_OUTPUT" ]]; then
  if grep -q "paperclip_issue_url=$" "$GITHUB_OUTPUT"; then
    pass "Paperclip issue URL is empty when token missing"
  else
    fail "Paperclip issue URL not empty when token missing"
  fi
else
  fail "GITHUB_OUTPUT file not created for missing token test"
fi

# --- Summary ---
echo ""
if [ "$FAILURES" -gt 0 ]; then
  echo "==> $FAILURES check(s) failed"
  exit 1
fi
echo "==> all checks passed"