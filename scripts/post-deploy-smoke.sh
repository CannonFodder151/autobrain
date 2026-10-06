#!/usr/bin/env bash
# Post-deploy smoke checks for a deployed AutoBrain tier (demo / default / hosted).
#
# Usage:
#   scripts/post-deploy-smoke.sh [BASE_URL] [EXPECTED_FRONTEND_SHA]
#
# BASE_URL defaults to the hosted tier. EXPECTED_FRONTEND_SHA is optional; when
# given, /flutter_bootstrap.js must hash to it or the run reports FAIL.
#
# Signup contract (see docs/Engineering/api-spec.md): POST /api/v1/auth/signup
# takes {email, display_name} ONLY. There is no password field — the account is
# finished via the emailed setup link. Omitting display_name returns 422 and was
# misreported as a deploy failure (AUT-4687).
#
# Exit code: 0 all checks pass, 1 any check fails.
set -uo pipefail

BASE_URL="${1:-https://hosted.autobrainservice.app}"
EXPECTED_SHA="${2:-}"

FAILURES=0

pass() { printf 'PASS  %-28s %s\n' "$1" "${2:-}"; }
fail() { printf 'FAIL  %-28s %s\n' "$1" "${2:-}"; FAILURES=$((FAILURES + 1)); }

# 1. Backend health
health_body=$(curl -fsS --max-time 20 "$BASE_URL/health" 2>&1) \
  && pass "/health" "$health_body" \
  || fail "/health" "$health_body"

# 2. Frontend bundle SHA (only when the deploy run published an expected SHA)
if [ -n "$EXPECTED_SHA" ]; then
  actual_sha=$(curl -fsS --max-time 30 "$BASE_URL/flutter_bootstrap.js" 2>/dev/null | sha256sum | cut -d' ' -f1)
  if [ "$actual_sha" = "$EXPECTED_SHA" ]; then
    pass "/flutter_bootstrap.js" "$actual_sha"
  else
    fail "/flutter_bootstrap.js" "got ${actual_sha:-<none>} want $EXPECTED_SHA"
  fi
else
  pass "/flutter_bootstrap.js" "skipped (no expected SHA passed)"
fi

# 3. Signup round-trip. Unique email per run so repeat runs stay 201.
signup_email="qa.smoke.$(date +%s)@example.com"
signup_body=$(curl -sS --max-time 30 -w '\n%{http_code}' -X POST \
  "$BASE_URL/api/v1/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"display_name\":\"QA Smoke\",\"email\":\"$signup_email\"}" 2>&1)
signup_code=$(printf '%s' "$signup_body" | tail -n1)
signup_json=$(printf '%s' "$signup_body" | sed '$d')
if [ "$signup_code" = "201" ]; then
  pass "/api/v1/auth/signup" "201 $signup_json"
else
  fail "/api/v1/auth/signup" "$signup_code $signup_json"
fi

# 4. Ready probe
ready_code=$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' "$BASE_URL/ready" 2>&1)
if [ "$ready_code" = "200" ]; then
  pass "/ready" "200"
else
  fail "/ready" "$ready_code"
fi

# 5. AI gateway (AUT-4788). nginx proxies /ai/ -> backend:8001, so a 502 here
# means the gateway co-process is dead while the backend itself stays healthy —
# exactly the failure mode that shipped green for 5 releases. Any non-5xx
# response (200 without a key, 401/403 with one) proves the gateway is serving.
ai_code=$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' "$BASE_URL/ai/v1/modules" 2>&1)
case "$ai_code" in
  2*|401|403)
    pass "/ai/v1/modules" "$ai_code"
    ;;
  *)
    fail "/ai/v1/modules" "$ai_code (AI gateway unreachable or 5xx)"
    ;;
esac

[ "$FAILURES" -eq 0 ] || exit 1
