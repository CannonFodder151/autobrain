# Petrol price map (AUT-1813)

A map view that shows live petrol/diesel prices across Australian states, sourced
from each state's official (or approved) fuel-price feed. The backend polls each
feed, normalises the responses into one schema (deterministic-first, no AI), and
caches them; the frontend plots them. State feeds are enabled per-source and only
poll when a key is configured (silent fallback to the last cached snapshot).

## Status

- Implemented: NSW. Source: Transport for NSW Fuel API (v2/fuel/prices),
  Basic-auth key/secret (2500 calls/month quota).
- Recorded: Nathan supplied the NSW key (2026-08-29). The live key is stored in
  Outline (AutoBrain collection) and wired into the hosted stack via a secret
  file mount. Never committed to the repo.

Viability: 95/100 for NSW. Other states tracked below as "coming soon" pending a
free feed.

## State feeds

| State | Feed | Auth | Env var(s) |
|-------|------|------|------------|
| WA | FuelWatch | none (public) | — |
| NSW | Transport for NSW Fuel API | HTTP Basic `key:secret` | `FUEL_NSW_API_KEY`, `FUEL_NSW_API_SECRET` |
| QLD | Fuel Prices | consumer token | *planned* (`FUEL_QLD_*`, AUT-1813 phase) |
| VIC | Servo Saver | approved partner key | *planned* (`FUEL_VIC_*`, AUT-1813 phase) |

WA needs no key. NSW is the only implemented source. QLD/VIC are planned phases
of AUT-1813 — when wired, their keys follow the same `FUEL_<STATE>_*` convention
and the same env-scoping rule below.

## How it works (deterministic-first)

- `backend/app/services/fuel_prices.py` polls the NSW feed and upserts one row
  per (state, station_code, fuel_type) into `fuel_prices`.
- `poll_nsw_fuel_prices` (celery beat, every 24h) is gated by
  `fuel_price_poll_state` keyed by instance id -> at most one successful poll
  per day per instance (Nathan's quota guard).
- `GET /api/v1/fuel-prices?state=NSW` serves the cached snapshot (offline-safe;
  serves the last good cache if a poll fails). No AI anywhere in this path.

## Canonical env var names (shared with the normaliser, AUT-1817)

NSW (implemented):

```
FUEL_NSW_API_KEY        # Transport for NSW app key (Basic-auth user)
FUEL_NSW_API_SECRET     # Transport for NSW app secret (Basic-auth password)
FUEL_NSW_ENABLED        # "true" to poll; "false"/empty disables
FUEL_NSW_API_URL        # optional override (defaults to the official endpoint)
FUEL_NSW_POLL_HOURS     # optional override (default 24)
```

The normaliser (`backend/app/services/fuel_prices.py`) reads these from the
process environment via `app.core.config` settings. There are **no baked-in
keys** — if `FUEL_NSW_API_KEY`/`FUEL_NSW_API_SECRET` are absent the source is
silently skipped (`enabled()` returns False), so an unconfigured instance never
polls an external feed (AUT-1858 / AUT-1817).

## Scoping (AUT-1858)

These keys are injected **only** for the AutoBrain-managed tiers:

- `docker-compose.prod.yml` (Default tier) — backend service (`FUEL_NSW_API_KEY`,
  `FUEL_NSW_API_SECRET`, `FUEL_NSW_ENABLED=true`, `${VAR:-}` empty defaults).
- `docker-compose.hosted.yml` (Hosted / Oracle Cloud, EP5) — backend + worker
  services, via the secret-file pattern (`FUEL_NSW_API_KEY_FILE` /
  `FUEL_NSW_API_SECRET_FILE` under `/run/secrets`, exported at container start by
  `docker/lib-load-secrets.sh`); `FUEL_NSW_ENABLED=true`.

They are **not** present in `docker-compose.yml` (self-host). Self-hosted users
opt in by setting their own keys (below). Real keys are never committed to the
repo: on Hosted they land in `/opt/autobrain/secrets` via
`scripts/seed-secrets.sh` (which now maps `FUEL_NSW_API_KEY`/`FUEL_NSW_API_SECRET`),
not in the compose file.

## Credential handling (security)

- FUEL_NSW_API_KEY / FUEL_NSW_API_SECRET are optional; FUEL_NSW_ENABLED
  defaults to false so self-hosted instances never poll an external feed unless
  they bring their own key.
- Hosted stack scopes the key via the secret-file pattern (/opt/autobrain/secrets,
  mounted read-only). See docs/security.md ("Secret-file pattern").
- The live key is recorded in Outline; do not paste it into this file or a commit.

## Storage schema

fuel_prices: id, state, station_code, station_name, brand, address, lat, lon,
fuel_type, price, currency(AUD), updated_at, fetched_at.
fuel_price_poll_state: instance_id, state, last_poll_at (per-instance gate).

## Self-hosting: obtain + set the keys

1. **WA** — nothing to do; FuelWatch is public.
2. **NSW Fuel API** — register an application at the
   [Transport for NSW Fuel API](https://api.transport.nsw.gov.au). Use the issued
   key + secret as HTTP Basic credentials in `FUEL_NSW_API_KEY` / `FUEL_NSW_API_SECRET`.
3. **QLD / VIC** — not yet wired; set their env vars once AUT-1813 ships them.

Set them in your `.env` (copy of `.env.example`):

```dotenv
FUEL_NSW_API_KEY=your-nsw-key
FUEL_NSW_API_SECRET=your-nsw-secret
FUEL_NSW_ENABLED=true
```

`docker compose up -d` then injects them via `env_file: .env`. Leave any you
don't have blank (and `FUEL_NSW_ENABLED=false`) to disable that source.

## Hosted / Default (AutoBrain-operated)

Nathan sets the real NSW key/secret in the Portainer stack env for EP5 (hosted)
and the default dev/EP6 stack, then runs `scripts/seed-secrets.sh <stack-env>`
so they become `fuel_nsw_api_key` / `fuel_nsw_api_secret` under
`/opt/autobrain/secrets`. The compose files reference them via `*_FILE`; they
never appear in git or `docker inspect`.

## Roadmap by state (free feed availability)

| State | Free feed | Status |
|-------|-----------|--------|
| NSW | Yes (Fuel API, keyed) | Live |
| WA | Yes (FuelWatch) | Planned |
| QLD | Yes (QLD Gov) | Planned |
| ACT | Yes (ACT fuel data) | Planned |
| VIC | Servo Saver (pending) | Coming soon |
| SA | No free feed | Blocked |
| TAS | No free feed | Blocked |
| NT | No free feed | Blocked |

Marketing "coming soon" page (CMO, AUT-1857) lists NSW/WA/QLD/ACT as supported
and SA/TAS/NT as coming soon.

## Confidence

95/100 for NSW. VIC depends on Servo Saver access; SA/TAS/NT need a paid feed
before viability improves.
