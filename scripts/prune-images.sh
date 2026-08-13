#!/usr/bin/env bash
set -euo pipefail

# Prune dangling (untagged) Docker images on EP2 (Portainer-Host) and EP5
# (AutoBrain-Hosted) via the Portainer API. Deploy builds leave intermediate
# layers behind; prune after every deploy and on the weekly routine (AUT-350).
#
# Usage: PORTAINER_API_KEY=... scripts/prune-images.sh
# Only prunes dangling images (`docker image prune -f` equivalent); never
# removes tagged or in-use images.

PORTAINER_URL="${PORTAINER_URL:-https://portainer.nathanmartina.com}"
: "${PORTAINER_API_KEY:?set PORTAINER_API_KEY to the Portainer API key}"

prune() {
  local ep="$1"
  local before after reclaimed
  before=$(curl -sk -H "X-API-Key: $PORTAINER_API_KEY" \
    "$PORTAINER_URL/api/endpoints/$ep/docker/images/json?filters=%7B%22dangling%22%3A%5B%22true%22%5D%7D" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d), round(sum(i["Size"] for i in d)/1e9,2))')
  reclaimed=$(curl -sk -X POST -H "X-API-Key: $PORTAINER_API_KEY" \
    -H "Content-Type: application/json" \
    "$PORTAINER_URL/api/endpoints/$ep/docker/images/prune" \
    -d '{"filters":{"dangling":["true"]}}' \
    | python3 -c 'import sys,json; print(round(json.load(sys.stdin).get("SpaceReclaimed",0)/1e9,2))')
  after=$(curl -sk -H "X-API-Key: $PORTAINER_API_KEY" \
    "$PORTAINER_URL/api/endpoints/$ep/docker/images/json?filters=%7B%22dangling%22%3A%5B%22true%22%5D%7D" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d), round(sum(i["Size"] for i in d)/1e9,2))')
  echo "EP$ep  before='$before'  reclaimed=${reclaimed}GB  after='$after'"
}

prune 2
prune 5
