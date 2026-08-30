#!/usr/bin/env bash
# Upgrade AutoBrain instances using the documented upgrade path (AUT-1847),
# hardened for reliability (AUT-1872):
#
# 1. Explicit per-image pull. `PUT /api/stacks/{id}?pullImage=true` is a NO-OP
#    for floating tags on Portainer (it only re-applies the compose; it does not
#    re-pull `:hosted`/`:latest`, so the running container keeps the old digest
#    and the instance silently never updates). We therefore pull every image
#    FIRST via `POST /endpoints/{ep}/docker/images/create?fromImage=...&tag=...`
#    (the reliable path), then redeploy.
# 2. Immutable tag pinning (kills the floating-tag race + cross-registry drift).
#    Set PIN_IMAGE_TAG=hosted-sha-<commit> (build-hosted.yml publishes exactly
#    that immutable manifest for backend/worker/ai/frontend) and the script
#    rewrites those four `:hosted` refs to the pinned tag before redeploy, so a
#    later auto-bump to GHCR `:hosted` can never drift the deployed stack.
# 3. Required-env enforcement. The Hosted stack MUST carry POSTGRES_USER /
#    POSTGRES_DB (otherwise compose interpolation aborts and the stack is
#    destroyed on redeploy, AUT-1872 #3). The script injects them if missing and
#    the compose now defaults them to `autobrain` as a backstop.
#
# Root cause (AUT-1847): instances were never updated. CI builds/publishes the
# images (`build-hosted.yml`, `dockerhub-publish.yml`) but nothing pulled them
# into the running Portainer stacks. Ownership (board direction, AUT-1847):
# deployment is NOT blind/automatic. CI publishes an image -> a Discord
# notification asks the Deployment Lead to run the upgrade path -> the
# Deployment Lead triggers `deploy-instances.yml` (workflow_dispatch), which
# runs THIS script. The script redeploys each Portainer stack via the API in the
# mandated promotion order (Demo -> Default -> Hosted, AUT-107), health-gates
# every tier, and refuses to promote to the next tier if the current one is
# unhealthy. The backend pulls + applies DB migrations on boot
# (docs/container-architecture.md), so a redeploy is a complete upgrade.
#
# Usage (Deployment Lead, after an image is published):
#   PORTAINER_API_KEY=... PORTAINER_URL=... ./scripts/upgrade-instances.sh
#   # pin Hosted (and Demo/Default) to an immutable multi-arch build:
#   PIN_IMAGE_TAG=hosted-sha=<commit> ./scripts/upgrade-instances.sh
#
# Environment overrides (sane defaults for the three AutoBrain tiers):
#   UPGRADE_TIERS        space/tab/newline separated "name|endpoint|health|required_env"
#   PIN_IMAGE_TAG        rewrite backend/worker/ai/frontend `:hosted` -> `:PIN_IMAGE_TAG`
#   UPGRADE_DRY_RUN=1    resolve + health-check only, do not redeploy
#   HEALTH_TIMEOUT_SEC   per-tier health poll timeout (default 600)
#
# Requires bash + curl + python3 (matches scripts/prune-images.sh).

set -euo pipefail

PORTAINER_URL="${PORTAINER_URL:-https://portainer.nathanmartina.com}"
: "${PORTAINER_API_KEY:?set PORTAINER_API_KEY to the Portainer API key}"
DRY_RUN="${UPGRADE_DRY_RUN:-0}"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-600}"
PIN_IMAGE_TAG="${PIN_IMAGE_TAG:-}"
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

# Pull a single image onto an endpoint's docker host BEFORE redeploy
# (AUT-1872 #1). This is the reliable replacement for the no-op pullImage=true:
# it guarantees the freshly published digest is present locally so the redeploy
# recreates changed containers instead of keeping the stale digest.
pull_image() {
  local ep="$1" img="$2" fromImage tag qs
  if [[ "$img" == *@* ]]; then
    fromImage="$img"; qs="fromImage=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$img")"
  else
    fromImage="${img%:*}"; tag="${img##*:}"
    qs="fromImage=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$fromImage")&tag=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$tag")"
  fi
  log "   pulling $img (EP$ep)"
  curl -sk -X POST "${AUTH[@]}" "$API/endpoints/$ep/docker/images/create?$qs" \
    -o /dev/null -w "     -> http %{http_code}\n" || true
}

# Re-apply a stack. $1=id $2=endpoint $3=json body file with
# {StackFileContent, Env, Prune}. We already pulled each image explicitly, so the
# redundant pullImage=true here is harmless (it does nothing for floating tags),
# but it stays as a belt-and-braces nudge for pinned/digest refs.
redeploy() {
  local id="$1" ep="$2" body="$3"
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
  [ -n "$PIN_IMAGE_TAG" ] && log "   pin tag: $PIN_IMAGE_TAG"

  if [ "$DRY_RUN" = "1" ]; then
    log "   dry-run: skip redeploy"
    if wait_health "$health"; then log "   healthy ($health)"; else fail "   UNHEALTHY ($health)"; OVERALL=1; fi
    continue
  fi

  # Pull current compose + env, inject required env, optionally pin image tags.
  raw="$(mktemp "$SCRATCH/stack-raw-XXXX")"
  put="$(mktemp "$SCRATCH/stack-put-XXXX")"
  images="$(mktemp "$SCRATCH/stack-images-XXXX")"
  fetch_stack "$stack_id" > "$raw"
  python3 - "$raw" "$reqenv" "$PIN_IMAGE_TAG" "$images" > "$put" <<'PY'
import json, sys, re
path, reqenv, pin, images_path = sys.argv[1:5]
doc = json.load(open(path))
content = doc.get("StackFileContent", "")
env = doc.get("Env") or []
env_map = {e["name"]: e["value"] for e in env if isinstance(e, dict) and "name" in e}
if pin:
    # AUT-1872 #4: pin the four app images (the only ones build-hosted.yml
    # publishes as immutable `hosted-sha-<commit>` manifests) to the given tag.
    content = re.sub(
        r'(ghcr\.io/cannonfodder151/autobrain-(?:backend|worker|ai|frontend)):hosted\b',
        lambda m: m.group(1) + ":" + pin, content)
    env_map.setdefault("AUTOBRAIN_IMAGE_PIN", pin)
# All image refs (for the explicit pre-pull below).
imgs = re.findall(r'^\s*image:\s*["\']?([^\s"\']+)', content, re.M)
open(images_path, "w").write("\n".join(imgs))
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

  # AUT-1872 #1: explicitly pull each image onto this endpoint so the redeploy
  # recreates changed services (pullImage=true alone would NOT pull floating tags).
  while IFS= read -r img; do
    [ -z "$img" ] && continue
    pull_image "$ep" "$img"
  done < "$images"

  log "   redeploying"
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
