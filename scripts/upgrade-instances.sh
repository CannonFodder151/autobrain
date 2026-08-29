#!/usr/bin/env bash
# Upgrade AutoBrain instances automatically using the documented upgrade path.
#
# Root cause (AUT-1847): instances were never auto-updated. CI builds/publishes
# the images (`build-hosted.yml`, `dockerhub-publish.yml`) but nothing pulled
# them into the running Portainer stacks. A Watchtower attempt existed on
# Portainer-Host (`watchtower-noaccess`, no registry credentials) and Hosted
# had none at all, so both halves silently never recreated containers. There is
# also no redeploy automation, and the Hosted stack's Portainer env is missing
# the required `POSTGRES_USER`/`POSTGRES_DB` (`docker-compose.hosted.yml` uses
# `${POSTGRES_USER:?...}`), so its last manual redeploy FAILED at compose
# interpolation — it literally cannot update until the env is repopulated.
#
# Fix: this script IS the upgrade path. It redeploys each Portainer stack via
# the Portainer API in the mandated promotion order (Demo → Default → Hosted,
# AUT-107) with `pullImage`, health-gates every tier, and refuses to promote to
# the next tier if the current one is unhealthy. The backend pulls + applies DB
# migrations on boot (docs/container-architecture.md), so a redeploy is a
# complete upgrade.
#
# Usage:
#   PORTAINER_API_KEY=... PORTAINER_URL=... ./scripts/upgrade-instances.sh
#
# Environment overrides (sane defaults for the three AutoBrain tiers):
#   UPGRADE_TIERS        space/tab/newline separated "name|endpoint|health|required_env"
#   UPGRADE_DRY_RUN=1    resolve + health-check only, do not redeploy
#   HEALTH_TIMEOUT_SEC   per-tier health poll timeout (default 600)
#
# Requires bash + curl + python3 (matches scripts/prune-images.sh).

set -euo pipefail

PORTAINER_URL="${PORTAINER_URL:-https://portainer.nathanmartina.com}"
: "${PORTAINER_API_KEY:?set PORTAINER_API_KEY to the Portainer API key}"
DRY_RUN="${UPGRADE_DRY_RUN:-0}"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-600}"
SCRATCH="${PAPERCLIP_RUN_SCRATCH_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$SCRATCH"

AUTH=(-H "X-API-Key: $PORTAINER_API_KEY")
API="$PORTAINER_URL/api"

# name | endpoint_id | health_url | "k=v,k=v" required env the stack must carry
DEFAULT_TIERS="
autobrain-demo|2|https://demo.autobrainservice.app/health|
autobrain|2|https://default.autobrainservice.app/health|
autobrain-hosted|5|https://hosted.autobrainservice.app/health|POSTGRES_USER=autobrain,POSTGRES_DB=autobrain
"

TIERS="${UPGRADE_TIERS:-$DEFAULT_TIERS}"

log() { echo "$(date -u +%FT%TZ) [upgrade] $*"; }
fail() { echo "$(date -u +%FT%TZ) [upgrade] ERROR: $*" >&2; }

# Resolve a stack id + endpoint by exact name (Portainer 2.45 ignores ?name=).
resolve_stack() {
  local name="$1"
  curl -sk "${AUTH[@]}" "$API/stacks" \
    | python3 -c "import sys,json
d=json.load(sys.stdin)
hits=[s for s in d if s.get('Name')==sys.argv[1]]
if not hits:
    sys.exit(1)
print(hits[0]['Id'], hits[0]['EndpointId'])" "$name"
}

# Fetch {StackFileContent, Env} of a stack.
fetch_stack() {
  local id="$1"
  curl -sk "${AUTH[@]}" "$API/stacks/$id/file"
}

# Re-apply a stack (pull images + recreate changed services). $1=id $2=endpoint
# $3=json body file with {StackFileContent, Env, Prune}.
redeploy() {
  local id="$1" ep="$2" body="$3"
  local resp
  resp="$(curl -sk -X PUT "${AUTH[@]}" -H "Content-Type: application/json" --data-binary "@$body" "$API/stacks/$id?endpointId=$ep")"
  printf '%s' "$resp" | python3 -c "import sys,json
raw=sys.stdin.read().strip()
try:
  d=json.loads(raw)
except Exception:
  print('ERR non-json: '+raw[:200])
else:
  s=d.get('Status') if isinstance(d,dict) else None
  if isinstance(d,dict) and (s in (1,2,3,4,5,6) or 'Id' in d):
    print('ok (status=%s)' % s)
  else:
    print('ERR '+str(d)[:200])"
}

wait_health() {
  local url="$1" deadline=$(( $(date +%s) + HEALTH_TIMEOUT_SEC ))
  while :; do
    if curl -fsS --max-time 10 "$url" >/dev/null 2>&1; then return 0; fi
    if [ "$(date +%s)" -ge "$deadline" ]; then return 1; fi
    sleep 10
  done
}

OVERALL=0
while IFS= read -r line; do
  line="$(echo "$line" | tr -d '[:space:]')"
  [ -z "$line" ] && continue
  IFS='|' read -r name ep health reqenv <<< "$line"

  log "=== tier: $name (EP$ep) ==="
  resolved="$(resolve_stack "$name")" || { fail "stack '$name' not found"; OVERALL=1; continue; }
  stack_id="${resolved%% *}"; ep="${resolved##* }"
  log "   stack id=$stack_id endpoint=$ep"

  if [ "$DRY_RUN" = "1" ]; then
    log "   dry-run: skip redeploy"
    if wait_health "$health"; then log "   healthy ($health)"; else fail "   UNHEALTHY ($health)"; OVERALL=1; fi
    continue
  fi

  # Pull current compose + env, inject any required-but-missing env, redeploy.
  raw="$(mktemp "$SCRATCH/stack-raw-XXXX")"
  put="$(mktemp "$SCRATCH/stack-put-XXXX")"
  fetch_stack "$stack_id" > "$raw"
  python3 - "$raw" "$reqenv" > "$put" <<'PY'
import json, sys
path, reqenv = sys.argv[1], sys.argv[2]
doc = json.load(open(path))
content = doc.get("StackFileContent", "")
env = doc.get("Env") or []
env_map = {e["name"]: e["value"] for e in env if isinstance(e, dict) and "name" in e}
for pair in reqenv.split(","):
    pair = pair.strip()
    if not pair:
        continue
    k, v = pair.split("=", 1)
    if k not in env_map:        # only fill gaps; never overwrite a real value
        env_map[k] = v
body = {"StackFileContent": content, "Env": [{"name": k, "value": vv} for k, vv in env_map.items()], "Prune": False}
sys.stdout.write(json.dumps(body, ensure_ascii=False))
PY
  log "   redeploying (pullImage)"
  result="$(redeploy "$stack_id" "$ep" "$put")"
  log "   redeploy result: $result"

  if wait_health "$health"; then
    log "   healthy ($health) — promote"
  else
    fail "   UNHEALTHY ($health) after redeploy — STOPPING promotion"
    OVERALL=1
    break
  fi
done <<< "$TIERS"

# Post-upgrade prune of dangling images on the two production hosts (AUT-350).
if [ "$DRY_RUN" != "1" ] && [ "$OVERALL" = "0" ] && [ -x "${0%/*}/prune-images.sh" ]; then
  log "=== post-upgrade prune (EP2, EP5) ==="
  PORTAINER_URL="$PORTAINER_URL" PORTAINER_API_KEY="$PORTAINER_API_KEY" "${0%/*}/prune-images.sh" || true
fi

if [ "$OVERALL" = "0" ]; then
  log "DONE: all tiers upgraded via the upgrade path"
else
  fail "upgrade FAILED — see tiers above"
fi
exit $OVERALL
