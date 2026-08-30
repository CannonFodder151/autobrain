#!/usr/bin/env bash
# Upgrade AutoBrain instances using the documented upgrade path (AUT-1847).
#
# Root cause: instances were never updated. CI builds/publishes the images
# (`build-hosted.yml`, `dockerhub-publish.yml`) but nothing pulled them into the
# running Portainer stacks. A Watchtower attempt on Portainer-Host had no
# registry credentials (`watchtower-noaccess`) and Hosted had none at all, so
# redeploy was always manual — and the Hosted stack's Portainer env was missing
# the required `POSTGRES_USER`/`POSTGRES_DB`, so its last manual redeploy FAILED
# at compose interpolation (`docker-compose.hosted.yml` used `${VAR:?...}`) and
# it could not update until the env was repopulated.
#
# Ownership (board direction, AUT-1847): deployment is NOT blind/automatic.
# CI publishes an image → a Discord notification asks the Deployment Lead to
# run the upgrade path → the Deployment Lead triggers `deploy-instances.yml`
# (workflow_dispatch), which runs THIS script. The script redeploys each
# Portainer stack via the API in the mandated promotion order (Demo →
# Default → Hosted, AUT-107) with `pullImage` so the freshly built images are
# pulled and changed services recreated, health-gates every tier, and refuses to
# promote to the next tier if the current one is unhealthy. The backend pulls
# + applies DB migrations on boot (docs/container-architecture.md), so a
# redeploy is a complete upgrade.
#
# Usage (Deployment Lead, after an image is published):
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

# Re-apply a stack, pulling the freshly published image and recreating changed
# services. $1=id $2=endpoint $3=json body file with {StackFileContent, Env, Prune}.
# `pullImage=true` is the load-bearing query param (AUT-1847): without it Portainer
# re-applies the same compose WITHOUT pulling, so the container keeps the old digest
# and the instance silently never updates — the exact bug this script fixes.
# AUT-1872: pullImage=true is a no-op for floating tags (:hosted/:latest). The
# reliable fix is to explicitly POST /endpoints/{ep}/docker/images/create per
# image BEFORE redeploy, so the new digest lands on the host and compose up
# recreates changed services.
pull_images() {
  local ep="$1" content="$2"
  echo "$content" | PORTAINER_API_KEY="$PORTAINER_API_KEY" API="$API" EP="$ep" python3 <<'PY_PULL'
import sys, re, subprocess, os
content = sys.stdin.read()
api = os.environ['API']
key = os.environ['PORTAINER_API_KEY']
ep = os.environ['EP']
images = re.findall(r'image:\s*([^\s#]+)', content)
for img in images:
    if '@sha256:' in img:
        continue  # immutable digest — no need to pull
    from_image = img
    cmd = ['curl', '-sk', '-X', 'POST',
           '-H', 'X-API-Key: ' + key,
           f'{api}/endpoints/{ep}/docker/images/create?fromImage={from_image}']
    print('==> Pulling ' + from_image + ' on EP' + ep, file=sys.stderr)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        print('WARN: pull failed for ' + from_image + ': ' + res.stderr[:200], file=sys.stderr)
    else:
        print('   pulled ' + from_image, file=sys.stderr)
PY_PULL
}

redeploy() {
  local id="$1" ep="$2" body="$3"
  # AUT-1872: Explicitly pull images first (pullImage=true is no-op for :hosted).
  local content
  content="$(cat "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('StackFileContent',''))")"
  pull_images "$ep" "$content"
  local resp
  resp="$(curl -sk -X PUT "${AUTH[@]}" -H "Content-Type: application/json" --data-binary "@$body" "$API/stacks/$id?endpointId=$ep&pullImage=true")"
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
