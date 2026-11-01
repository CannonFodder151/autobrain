#!/usr/bin/env bash
# Roll back a single AutoBrain tier to its previous image.
# Usage: PORTAINER_API_KEY=... PORTAINER_URL=... ./scripts/rollback-tier.sh <demo|default|hosted>
set -euo pipefail

TIER="${1:-?}"
PORTAINER_URL="${PORTAINER_URL:-https://portainer.nathanmartina.com}"
: "${PORTAINER_API_KEY:?set PORTAINER_API_KEY}"
AUTH=(-H "X-API-Key: $PORTAINER_API_KEY")
API="$PORTAINER_URL/api"

case "$TIER" in
  demo)   NAME="autobrain-demo";   EP=2 ;;
  default) NAME="autobrain-default"; EP=2 ;;
  hosted) NAME="autobrain-hosted"; EP=5 ;;
  *) echo "unknown tier: $TIER"; exit 1 ;;
esac

# Resolve stack id (Portainer 2.45 ignores ?name=).
ID="$(curl -sk "${AUTH[@]}" "$API/stacks" | python3 -c "import sys,json;d=json.load(sys.stdin);h=[s for s in d if s.get('Name')==sys.argv[1]];print(h[0]['Id'] if h else '')" "$NAME")"
[ -n "$ID" ] || { echo "stack $NAME not found"; exit 1; }

# Fetch current file, then PUT with pullImage=true (re-apply prior image).
BODY="$(mktemp)"
curl -sk "${AUTH[@]}" "$API/stacks/$ID/file" > "$BODY"
RESP="$(curl -sk -X PUT "${AUTH[@]}" -H "Content-Type: application/json" --data-binary "@$BODY" "$API/stacks/$ID?endpointId=$EP&pullImage=true")"
echo "$RESP" | python3 -c "import sys,json;d=json.loads(sys.stdin);print('rolled back', d.get('Status','?'))"
rm -f "$BODY"
