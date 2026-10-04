# Demo Environment Documentation (demo.autobrainservice.app)

## Overview

The demo instance is a **public, read/write AutoBrain environment** at `demo.autobrainservice.app` running on the **Demo stack** (Portainer endpoint 2 = Portainer-Host). It is separate from the Default and Hosted stacks.

**Credentials:** `demo@autobrainservice.app` / `demo` (configurable via `DEMO_EMAIL`/`DEMO_PASSWORD`/`DEMO_DISPLAY_NAME` env vars).

**Purpose:** Let prospects try AutoBrain without signing up. Also used by QA for regression testing.

## Architecture

| Component | Detail |
|-----------|--------|
| **Host** | `<PORTENER_HOST_IP>` (same as Default stack) |
| **Portainer endpoint** | 2 = Portainer-Host |
| **Stack name** | `demo` (separate from `default`) |
| **Compose file** | `docker-compose.yml` (not `.hosted.yml` or `.prod.yml`) |
| **Backend** | Runs with `DEMO_MODE=true` |
| **Frontend** | Flutter web build (same as other stacks) |
| **AI router** | 9Router at `<INTERNAL_9ROUTER_URL>` (shared with Default) |
| **Database** | Postgres (shared instance with Default stack, separate DB) |
| **MinIO** | Shared instance, separate bucket prefix |
| **Public URL** | `https://demo.autobrainservice.app` |

## DEMO_MODE Behaviour

When `DEMO_MODE=true` (in `backend/app/core/config.py`):

1. **Auth bypass:** The demo user (`DEMO_EMAIL`) is auto-created/updated on every boot via `seed_demo()`.
2. **No registration required:** Visitors can log in with the known credentials or use the "Try demo" button (auto-login via session cookie).
3. **Data seeding:** `seed_demo()` populates:
   - 1 demo user (`Demo Garage`)
   - 3–5 demo vehicles with realistic data
   - Fuel logs, service records, OBD codes, receipts, valuations
   - **≥15 Issues Blog posts** with replies (AUT-712)
   - Social builds (Community Garage) — local only, no federation
4. **Reset capability:** `DEMO_RESET=true` on boot wipes and re-seeds the demo user (used when seed data changes). `reset_demo()` clears `vehicle_shares` and issue-blog data first to avoid FK crashes (AUT-521).
5. **No federation:** Demo instance does **not** register with the federation hub. Community Garage shows only local demo builds.
6. **Premium entitlement:** The demo user is seeded with `role='demo'` and `free_account=False`, so it **keeps read-only Community Garage access** (its curated demo feed). Social write routes reject it via `require_premium_write`, which chains to `require_write` and rejects the demo role. Both guards live in `backend/app/api/deps.py`; only `free_account=True` (a free-tier account) is locked out of Community Garage entirely.

## Demo Stack Differences

| Setting | Demo | Default | Hosted |
|---------|------|---------|--------|
| `DEMO_MODE` | `true` | `false` | `false` |
| `SOCIAL_FEDERATION_HOSTED` | `false` | `false` | `true` (licensed free on the hub) |
| Federation hub | Not registered | Optional (`SOCIAL_FEDERATION_HOSTED=false`) | Auto-registered |
| Compose file | `docker-compose.yml` | `docker-compose.prod.yml` | `docker-compose.hosted.yml` |
| Services | — | postgres, redis, minio, backend, frontend | 9 long-running (adds dongle-server, hub, 9router, backup) |
| Data persistence | Ephemeral (reset on demand) | Persistent | Persistent |
| Backups | None | Operator-managed | `backup` service (hourly snapshot in Celery beat, AUT-3827) + offsite |

Backups and data-persistence expectations for the hosted stack come from the Deployment team; the demo instance is disposable by design and gets none.

## Reset & Maintenance

- **Manual reset:** Set `DEMO_RESET=true` in Portainer stack env → redeploy. Or run `reset_demo()` via backend shell.
- **Auto-reset on seed change:** CI sets `DEMO_RESET=true` when `backend/app/db/seed.py` changes (AUT-521).
- **Test verification:** `backend/tests/test_seed_reset_demo.py` runs in CI (sqlite, no Postgres/MinIO) and validates FK-safe ordering.
- **Health check:** `GET /health` returns `{"env": "demo", ...}` when `DEMO_MODE=true`.

## Known Constraints

- **Shared Postgres/MinIO with Default:** Resource contention possible. Demo is lower priority.
- **No backups:** Demo data is disposable.
- **Rate limits:** Demo users hit the same API rate limits as real users.
- **AI calls:** The demo account is seeded read-only, and AI modules reject the demo role (`require_ai` in `backend/app/api/deps.py`), so demo visitors do not consume AI-router quota.
- **No email/SMTP:** Password reset, notifications disabled for demo.

## QA Usage

- `backend/tests/test_seed_reset_demo.py` — validates FK-safe reset ordering (sqlite).
- `backend/tests/test_demo_fuel_seed.py` — validates fuel seed data.
- `backend/tests/test_health_demo.py` — health endpoint env reporting.
- `backend/tests/health_demo.test.py` — HTTP smoke tests against the live demo URL (opt-in; skipped by default).
- Run locally: `DEMO_MODE=true pytest backend/tests/test_seed_reset_demo.py -q` (sqlite).

## Related Docs

- [Website Documentation](./website.md) — marketing site (separate repo)
- [Community Garage](./community-garage.md) — demo shows local-only social
- [Growth Metrics](./growth-metrics.md) — demo is the mid-funnel metric; how to count it
- [Deployment & Infrastructure](../Deployment-and-Infrastructure/index.md) — stack definitions
- [Container Architecture](../Engineering/container-architecture.md) — service-level runtime

Source: `docker-compose.yml`, `backend/app/core/config.py`, `backend/app/db/seed.py`, `backend/app/api/deps.py`, `backend/tests/test_seed_reset_demo.py`.