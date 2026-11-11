#!/bin/bash
#
# AutoBrain Public API v1 - cURL Examples
# Requires: curl, jq (for pretty JSON output)
#
# Usage: export AUTOBRAIN_API_KEY="abapi_..." && ./curl-examples.sh
#

set -euo pipefail

API_KEY="${AUTOBRAIN_API_KEY:-}"
BASE_URL="https://api.autobrain.app/api/v1"

if [[ -z "$API_KEY" ]]; then
  echo "Error: Set AUTOBRAIN_API_KEY environment variable"
  exit 1
fi

# Helper: pretty print JSON or raw
api_get() {
  curl -sS -H "X-API-Key: $API_KEY" -H "Accept: application/json" "$BASE_URL$1" | jq .
}

api_post() {
  curl -sS -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -H "Accept: application/json" "$BASE_URL$1" -d "$2" | jq .
}

api_patch() {
  curl -sS -X PATCH -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -H "Accept: application/json" "$BASE_URL$1" -d "$2" | jq .
}

api_delete() {
  curl -sS -X DELETE -H "X-API-Key: $API_KEY" -H "Accept: application/json" "$BASE_URL$1" | jq .
}

echo "=== AutoBrain API v1 cURL Examples ==="
echo "Base URL: $BASE_URL"
echo

# -------------------------------------------------------------------
# VEHICLES
# -------------------------------------------------------------------

echo "--- List all vehicles ---"
api_get "/vehicles"

# Get first vehicle ID for subsequent examples
VEHICLE_ID=$(curl -sS -H "X-API-Key: $API_KEY" "$BASE_URL/vehicles" | jq -r '.[0].id // empty')
if [[ -n "$VEHICLE_ID" ]]; then
  echo
  echo "--- Get vehicle $VEHICLE_ID ---"
  api_get "/vehicles/$VEHICLE_ID"

  echo
  echo "--- Get vehicle timeline ---"
  api_get "/vehicles/$VEHICLE_ID/timeline"

  # -------------------------------------------------------------------
  # SERVICES
  # -------------------------------------------------------------------
  echo
  echo "--- List services for $VEHICLE_ID ---"
  api_get "/vehicles/$VEHICLE_ID/services"

  # -------------------------------------------------------------------
  # FUEL
  # -------------------------------------------------------------------
  echo
  echo "--- List fuel logs for $VEHICLE_ID ---"
  api_get "/vehicles/$VEHICLE_ID/fuel"

  echo
  echo "--- Add fuel log ---"
  api_post "/vehicles/$VEHICLE_ID/fuel" '{
    "litres": 45.5,
    "price_per_litre": 1.89,
    "odometer_km": 125000,
    "fill_date": "'$(date -I)'"
  }'

  echo
  echo "--- Fuel stats ---"
  api_get "/vehicles/$VEHICLE_ID/fuel/stats"

  # -------------------------------------------------------------------
  # DIAGNOSTICS
  # -------------------------------------------------------------------
  echo
  echo "--- Run AI diagnostics ---"
  api_post "/vehicles/$VEHICLE_ID/diagnostics" '{
    "symptoms": "Engine runs rough at idle, check engine light on",
    "obd_codes": ["P0300", "P0301"]
  }'

  echo
  echo "--- List diagnostics ---"
  api_get "/vehicles/$VEHICLE_ID/diagnostics"

  # -------------------------------------------------------------------
  # LOGBOOK
  # -------------------------------------------------------------------
  echo
  echo "--- Start logbook trip ---"
  TRIP=$(api_post "/vehicles/$VEHICLE_ID/logbook" '{
    "started_at": "'$(date -Iseconds)'",
    "start_odometer_km": 125000,
    "purpose": "work",
    "description": "Commute to office"
  }')
  ENTRY_ID=$(echo "$TRIP" | jq -r '.id // empty')

  if [[ -n "$ENTRY_ID" ]]; then
    echo
    echo "--- End logbook trip ---"
    api_patch "/vehicles/$VEHICLE_ID/logbook/$ENTRY_ID" '{
      "ended_at": "'$(date -Iseconds)'",
      "end_odometer_km": 125025,
      "status": "completed"
    }'
  fi

  # -------------------------------------------------------------------
  # WEBHOOKS
  # -------------------------------------------------------------------
  echo
  echo "--- List webhooks ---"
  api_get "/developer/webhooks"

  echo
  echo "--- Create webhook (example URL - replace with your endpoint) ---"
  api_post "/developer/webhooks" '{
    "label": "Test Webhook",
    "url": "https://webhook.site/your-unique-url",
    "events": ["service.due", "fuel.entry", "rego.expiry"],
    "max_retries": 5
  }'

  # Get first webhook ID
  WEBHOOK_ID=$(curl -sS -H "X-API-Key: $API_KEY" "$BASE_URL/developer/webhooks" | jq -r '.[0].id // empty')
  if [[ -n "$WEBHOOK_ID" ]]; then
    echo
    echo "--- Get webhook deliveries ---"
    api_get "/developer/webhooks/$WEBHOOK_ID/deliveries"

    echo
    echo "--- Test webhook ---"
    api_post "/developer/webhooks/$WEBHOOK_ID/test" '{
      "message": "Test payload from cURL example"
    }'
  fi

  # -------------------------------------------------------------------
  # API KEY MANAGEMENT
  # -------------------------------------------------------------------
  echo
  echo "--- List API keys ---"
  api_get "/developer/keys"

  echo
  echo "--- Create API key (read-only) ---"
  api_post "/developer/keys" '{
    "label": "Read-only key for Grafana",
    "scopes": ["read:vehicles", "read:services", "read:fuel", "read:diagnostics", "read:logbook"],
    "rate_limit": 60,
    "rate_window_seconds": 60
  }'

else
  echo "No vehicles found. Create a vehicle first via the app."
fi

echo
echo "=== Done ==="