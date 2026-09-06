# Petrol price map (AUT-1813)

A map view that shows live petrol/diesel prices across Australian states, sourced
from each state's official (or approved) fuel-price feed. The backend polls each
feed, normalises the responses into one schema (deterministic-first, no AI), and
caches them; the frontend plots them. State feeds are enabled per-source and only
poll when a key is configured (silent fallback to the last cached snapshot).

## State feeds

| State | Feed | Auth | Env var(s) |
|-------|------|------|------------|
| WA | FuelWatch | none (public) | — |
| NSW | Transport for NSW Fuel API | HTTP Basic `key:secret` | `FUEL_NSW_API_KEY`, `FUEL_NSW_API_SECRET` |
| QLD | Fuel Prices | consumer token | *planned* (`FUEL_QLD_*`, AUT-1813 phase) |
| VIC | Servo Saver | approved partner key | `FUEL_VIC_API_KEY` (AUT-1932) |

WA needs no key. NSW and VIC are implemented. QLD is a planned phase of
AUT-1813 — when wired, its keys follow the same `FUEL_<STATE>_*` convention
and the same env-scoping rule below.

## Canonical env var names (shared with the normaliser, AUT-1817)

NSW (implemented):

```
FUEL_NSW_API_KEY        # Transport for NSW app key (Basic-auth user)
FUEL_NSW_API_SECRET     # Transport for NSW app secret (Basic-auth password)
FUEL_NSW_ENABLED        # "true" to poll; "false"/empty disables
FUEL_NSW_API_URL        # optional override (defaults to the official endpoint)
FUEL_NSW_POLL_HOURS     # optional override (default 24)
```

VIC (implemented):

```
FUEL_VIC_API_KEY        # Servo Saver approved partner key (AUT-1932)
FUEL_VIC_API_SECRET     # Servo Saver secret (optional, server-cached)
FUEL_VIC_ENABLED        # "true" to poll; "false"/empty disables
FUEL_VIC_URL            # optional override (defaults to api.servosaver.com.au)
```

The normaliser (`backend/app/services/fuel_prices.py`) reads these from the
process environment via `app.core.config` settings. There are **no baked-in
keys** — if `FUEL_NSW_API_KEY`/`FUEL_NSW_API_SECRET` are absent the source is
silently skipped (`enabled()` returns False), so an unconfigured instance never
polls an external feed (AUT-1858 / AUT-1817).

## Scoping (AUT-1858)

These keys are injected **only** for the AutoBrain-managed tiers:

- `docker-compose.prod.yml` (Default tier) — backend service (`FUEL_NSW_API_KEY`,
  `FUEL_NSW_API_SECRET`, `FUEL_NSW_ENABLED=true`, `${VAR:-}` empty defaults) +
  VIC (`FUEL_VIC_API_KEY`, `FUEL_VIC_API_SECRET`, `FUEL_VIC_ENABLED=true`,
  served only when an approved partner key is provisioned).
- `docker-compose.hosted.yml` (Hosted / Oracle Cloud, EP5) — backend + worker
  services, via the secret-file pattern (`FUEL_NSW_API_KEY_FILE` /
  `FUEL_NSW_API_SECRET_FILE` under `/run/secrets`, exported at container start by
  `docker/lib-load-secrets.sh`); `FUEL_NSW_ENABLED=true` + VIC
  (`FUEL_VIC_API_KEY_FILE`, `FUEL_VIC_API_SECRET_FILE`,
  `FUEL_VIC_ENABLED=true`, served only when an approved partner key is
  provisioned in `/opt/autobrain/secrets`).

They are **not** present in `docker-compose.yml` (self-host). Self-hosted users
opt in by setting their own keys (below). Real keys are never committed to the
repo: on Hosted they land in `/opt/autobrain/secrets` via
`scripts/seed-secrets.sh` (which now maps `FUEL_NSW_API_KEY`/`FUEL_NSW_API_SECRET`),
not in the compose file.

## Self-hosting: obtain + set the keys

1. **WA** — nothing to do; FuelWatch is public.
2. **NSW Fuel API** — register an application at the
   [Transport for NSW Fuel API](https://api.transport.nsw.gov.au). Use the issued
   key + secret as HTTP Basic credentials in `FUEL_NSW_API_KEY` / `FUEL_NSW_API_SECRET`.
3. **VIC Servo Saver** — obtain an approved partner key from Servo Saver
   (`api.servosaver.com.au`). Set `FUEL_VIC_API_KEY` (and optional
   `FUEL_VIC_API_SECRET`). Once provisioned, set `FUEL_VIC_ENABLED=true` to
   start polling (AUT-1932).
4. **QLD** — not yet wired; set env vars once AUT-1813 ships the QLD feed.

Set them in your `.env` (copy of `.env.example`):

```dotenv
FUEL_NSW_API_KEY=your-nsw-key
FUEL_NSW_API_SECRET=your-nsw-secret
FUEL_NSW_ENABLED=true
FUEL_VIC_API_KEY=your-vic-key
FUEL_VIC_ENABLED=true
```

`docker compose up -d` then injects them via `env_file: .env`. Leave any you
don't have blank (and `FUEL_<STATE>_ENABLED=false`) to disable that source.

## Hosted / Default (AutoBrain-operated)

Nathan sets the real NSW key/secret in the Portainer stack env for EP5 (hosted)
and the default dev/EP6 stack, then runs `scripts/seed-secrets.sh <stack-env>`
so they become `fuel_nsw_api_key` / `fuel_nsw_api_secret` under
`/opt/autobrain/secrets`. The compose files reference them via `*_FILE`; they
never appear in git or `docker inspect`.
