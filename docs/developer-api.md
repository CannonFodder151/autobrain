# AutoBrain Public Developer API v1

Welcome to the AutoBrain Public Developer API. This API allows you to build integrations with AutoBrain vehicle data — vehicles, service records, fuel logs, diagnostics, logbook trips, and more.

## Base URL

```
https://api.autobrain.app/api/v1
```

## Authentication

The API uses **API Keys** for authentication. Include your key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: abapi_abc123..." https://api.autobrain.app/api/v1/vehicles
```

### API Key Scopes

Keys are granted specific scopes that control access:

| Scope | Description |
|-------|-------------|
| `read:vehicles` | List and view vehicles |
| `read:services` | View service records |
| `read:fuel` | View fuel logs |
| `read:diagnostics` | View diagnostics |
| `read:logbook` | View logbook trips |
| `read:analytics` | View analytics/valuation |
| `write:services` | Create/update service records |
| `write:fuel` | Create/update fuel logs |
| `write:diagnostics` | Create/update diagnostics |
| `write:logbook` | Create/update logbook trips |
| `webhooks:read` | List webhooks and deliveries |
| `webhooks:write` | Create/update/delete webhooks |
| `admin:keys` | Manage API keys (create/revoke) |

## Rate Limiting

Each API key has a configurable rate limit (default: 60 requests/minute). Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

## Endpoints

### Vehicles

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| GET | `/vehicles` | `read:vehicles` | List all vehicles |
| POST | `/vehicles` | `write:vehicles` | Create a vehicle |
| GET | `/vehicles/{id}` | `read:vehicles` | Get a vehicle |
| PATCH | `/vehicles/{id}` | `write:vehicles` | Update a vehicle |
| DELETE | `/vehicles/{id}` | `write:vehicles` | Delete a vehicle |
| GET | `/vehicles/{id}/timeline` | `read:vehicles` | Get unified timeline |

### Services

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| GET | `/vehicles/{id}/services` | `read:services` | List services |
| POST | `/vehicles/{id}/services` | `write:services` | Create service |
| GET | `/vehicles/{id}/services/{sid}` | `read:services` | Get service |
| PATCH | `/vehicles/{id}/services/{sid}` | `write:services` | Update service |
| DELETE | `/vehicles/{id}/services/{sid}` | `write:services` | Delete service |
| GET | `/vehicles/{id}/services/export` | `read:services` | Export CSV/PDF/ZIP |

### Fuel

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| GET | `/vehicles/{id}/fuel` | `read:fuel` | List fuel logs |
| POST | `/vehicles/{id}/fuel` | `write:fuel` | Add fuel log |
| PATCH | `/vehicles/{id}/fuel/{fid}` | `write:fuel` | Update fuel log |
| DELETE | `/vehicles/{id}/fuel/{fid}` | `write:fuel` | Delete fuel log |
| GET | `/vehicles/{id}/fuel/stats` | `read:fuel` | Fuel statistics |
| GET | `/vehicles/{id}/fuel/export` | `read:fuel` | Export CSV/ZIP |

### Diagnostics

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| POST | `/vehicles/{id}/diagnostics` | `read:diagnostics` | Run AI diagnosis |
| GET | `/vehicles/{id}/diagnostics` | `read:diagnostics` | List diagnostics |
| POST | `/vehicles/{id}/diagnostics/{did}/resolve` | `write:diagnostics` | Mark resolved |
| DELETE | `/vehicles/{id}/diagnostics/{did}` | `write:diagnostics` | Delete diagnostic |

### Logbook (ATO Trips)

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| POST | `/vehicles/{id}/logbook` | `write:logbook` | Start trip |
| GET | `/vehicles/{id}/logbook` | `read:logbook` | List trips |
| GET | `/vehicles/{id}/logbook/stats` | `read:logbook` | Trip statistics |
| PATCH | `/vehicles/{id}/logbook/{eid}` | `write:logbook` | Update/end trip |
| DELETE | `/vehicles/{id}/logbook/{eid}` | `read:logbook` | Delete trip |
| GET | `/vehicles/{id}/logbook/export` | `read:logbook` | Export CSV |

## Webhooks

Register HTTPS endpoints to receive real-time events.

### Event Types

| Event | Description |
|-------|-------------|
| `vehicle.created` | New vehicle added |
| `vehicle.updated` | Vehicle details changed |
| `vehicle.deleted` | Vehicle removed |
| `service.due` | Service became due |
| `service.completed` | Service marked completed |
| `fuel.entry` | Fuel log added |
| `fuel.receipt` | Fuel receipt uploaded |
| `rego.expiry` | Registration expiring soon |
| `diagnostic.created` | New diagnostic |
| `diagnostic.resolved` | Diagnostic resolved |
| `odometer.updated` | Odometer reading changed |
| `logbook.trip` | Trip started/ended |
| `notification.received` | Push notification sent |

### Payload Format

All webhook POSTs include:

```json
{
  "event": "service.completed",
  "timestamp": "2026-11-11T10:30:00Z",
  "delivery_id": "uuid",
  "vehicle_id": "uuid",
  "data": { ... }
}
```

### Signature Verification

Each delivery includes `X-Autobrain-Signature: sha256=<hex>`. Verify with your webhook secret:

```python
import hmac, hashlib

def verify(payload_bytes: bytes, secret: str, signature: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
```

### Retry Policy

Failed deliveries retry with exponential backoff: 1min, 2min, 4min, 10min, 20min (configurable). After max retries, the webhook is paused.

## Developer Dashboard

Manage API keys and webhooks at: **https://app.autobrain.app/developer**

## SDKs & Samples

### Python

```python
import httpx

class AutoBrainClient:
    def __init__(self, api_key: str, base_url: str = "https://api.autobrain.app/api/v1"):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key}
        )

    async def get_vehicles(self):
        resp = await self.client.get("/vehicles")
        resp.raise_for_status()
        return resp.json()

    async def get_services(self, vehicle_id: str):
        resp = await self.client.get(f"/vehicles/{vehicle_id}/services")
        resp.raise_for_status()
        return resp.json()

    async def add_fuel(self, vehicle_id: str, litres: float, price: float, odometer: int):
        resp = await self.client.post(
            f"/vehicles/{vehicle_id}/fuel",
            json={"litres": litres, "price_per_litre": price, "odometer_km": odometer}
        )
        resp.raise_for_status()
        return resp.json()
```

### JavaScript (Node/Browser)

```javascript
class AutoBrainClient {
  constructor(apiKey, baseUrl = "https://api.autobrain.app/api/v1") {
    this.baseUrl = baseUrl;
    this.headers = {
      "X-API-Key": apiKey,
      "Content-Type": "application/json"
    };
  }

  async request(path, options = {}) {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: { ...this.headers, ...options.headers }
    });
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    return resp.json();
  }

  async getVehicles() {
    return this.request("/vehicles");
  }

  async getServices(vehicleId) {
    return this.request(`/vehicles/${vehicleId}/services`);
  }

  async addFuel(vehicleId, litres, price, odometer) {
    return this.request(`/vehicles/${vehicleId}/fuel`, {
      method: "POST",
      body: JSON.stringify({ litres, price_per_litre: price, odometer_km: odometer })
    });
  }
}
```

### cURL Examples

```bash
# List vehicles
curl -H "X-API-Key: abapi_..." https://api.autobrain.app/api/v1/vehicles

# Add fuel log
curl -X POST -H "X-API-Key: abapi_..." \
  -H "Content-Type: application/json" \
  -d '{"litres": 45.5, "price_per_litre": 1.89, "odometer_km": 125000}' \
  https://api.autobrain.app/api/v1/vehicles/VEHICLE_ID/fuel

# Create webhook
curl -X POST -H "X-API-Key: abapi_..." \
  -H "Content-Type: application/json" \
  -d '{"label": "My Home Assistant", "url": "https://ha.example.com/webhook", "events": ["service.due", "fuel.entry"]}' \
  https://api.autobrain.app/api/v1/developer/webhooks
```

## Error Responses

| Code | Meaning |
|------|---------|
| 400 | Bad request (validation error) |
| 401 | Invalid/missing API key |
| 403 | Scope not granted |
| 404 | Resource not found |
| 422 | Unprocessable entity |
| 429 | Rate limited |
| 500 | Server error |
| 503 | Service unavailable |

Errors follow RFC 7807 format:
```json
{
  "detail": "Invalid or revoked API key",
  "status": 401
}
```

## Changelog

- **v1.0** (2026-11-11): Initial release
  - Vehicle, service, fuel, diagnostics, logbook endpoints
  - Webhooks with 14 event types
  - API key management with scopes and rate limits
  - OpenAPI docs at `/docs`

## Support

- Documentation: https://docs.autobrain.app
- Issues: https://github.com/autobrain/api/issues
- Email: developers@autobrain.app