# Petrol price map (AUT-1813)

A map view that shows live petrol/diesel prices across Australian states, sourced
from each state's official (or approved) fuel-price feed. The backend normalises
the per-state responses into one schema (AUT-1817) and the frontend plots them.

## State feeds

| State | Feed | Auth | Env var |
|-------|------|------|---------|
| WA | FuelWatch | none (public RSS/XML) | — |
| NSW | FuelCheck API | API key (NSW gov API Centre) | `NSW_FUELCHECK_API_KEY` |
| QLD | Fuel Prices | Consumer token (QLD open data) | `QLD_FUEL_PRICES_CONSUMER_TOKEN` |
| VIC | Servo Saver | Approved partner key | `VIC_SERVO_SAVER_API_KEY` |

WA needs no key. For the other three, an **empty/unset** key means that state's
source is silently disabled — the map still renders the states it can reach.

## Env var names (canonical — shared with AUT-1817)

```
NSW_FUELCHECK_API_KEY
QLD_FUEL_PRICES_CONSUMER_TOKEN
VIC_SERVO_SAVER_API_KEY
```

The normaliser (AUT-1817) reads these from the process environment with **no
baked-in defaults** — if a key is absent the corresponding state is skipped, it
is never impersonated with a leaked/guessed value.

## Scoping (AUT-1858)

These keys are injected **only** for the AutoBrain-managed tiers:

- `docker-compose.prod.yml` (Default tier) — backend + ai services.
- `docker-compose.hosted.yml` (Hosted / Oracle Cloud, EP5) — backend + ai + worker.

They are **not** present in `docker-compose.yml` (self-host). Self-hosted users
opt in by setting their own keys (below). Real keys are never committed to the
repo; on Hosted they are supplied via the Portainer stack env (EP5), not in the
compose file.

## Self-hosting: obtain + set the keys

1. **WA** — nothing to do; FuelWatch is public.
2. **NSW FuelCheck** — register an application at the
   [NSW Government API Centre](https://api.nsw.gov.au). Subscribe to the
   *FuelCheck* API; the issued API key (used as the OAuth client id/secret) goes
   in `NSW_FUELCHECK_API_KEY`.
3. **QLD Fuel Prices** — request a consumer token from the QLD Fuel Prices open
   data / API Centre and put it in `QLD_FUEL_PRICES_CONSUMER_TOKEN`.
4. **VIC Servo Saver** — approved-partner feed only. Set
   `VIC_SERVO_SAVER_API_KEY` once a key is issued to you; leave empty otherwise.

Set them in your `.env` (copy of `.env.example`):

```dotenv
NSW_FUELCHECK_API_KEY=your-nsw-fuelcheck-key
QLD_FUEL_PRICES_CONSUMER_TOKEN=your-qld-token
VIC_SERVO_SAVER_API_KEY=
```

`docker compose up -d` then injects them via `env_file: .env`. Leave any you
don't have blank to disable that state.

## Hosted / Default (AutoBrain-operated)

Nathan sets the real keys in the Portainer stack env for EP5 (hosted) and the
default dev/EP6 stack — they are interpolated through the `${VAR:-}` references
already added to the compose files and never appear in git.
