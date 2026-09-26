# Demo Environment Documentation (demo.autobrainservice.app)

## Overview

The demo instance is a **public, read/write AutoBrain environment** at `demo.autobrainservice.app` running on the **Demo stack** (Portainer endpoint 2 = Portainer-Host, 10.0.3.17). It is separate from the Default and Hosted stacks.

**Credentials:** `demo@autobrainservice.app` / `demo` (configurable via `DEMO_EMAIL`/`DEMO_PASSWORD`/`DEMO_DISPLAY_NAME` env vars).

**Purpose:** Let prospects try AutoBrain without signing up. Also used by QA for regression testing.

## Architecture

| Component | Detail |
|-----------|--------|
| **Host** | 10.0.3.17 (same as Default stack) |
| **Portainer endpoint** | 2 = Portainer-Host |
| **Stack name** | `demo` (separate from `default`) |
| **Compose file** | `docker-compose.yml` (not `.hosted.yml` or `.prod.yml`) |
| **Backend** | Runs with `DEMO_MODE=true` |
| **Frontend** | Flutter web build (same as other stacks) |
| **AI router** | 9Router on 10.0.3.17:20128/v1 (shared with Default) |
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
3. **Reset capability:** `DEMO_RESET=true` on boot wipes and re-seeds the demo user (used when seed data changes). `reset_demo()` clears `vehicle_shares` and issue-blog data first to avoid FK crashes (AUT-521).
4. **No federation:** Demo instance does **not** register with the federation hub. Community Garage shows only local demo builds.
5. **Premium entitlement:** Demo account has read-only Community Garage access (curated feed); write routes reject demo role.

## Demo Stack Differences

| Setting | Demo | Default | Hosted |
|---------|------|---------|--------|
| `DEMO_MODE` | `true` | `false` | `false` |
| `SOCIAL_FEDERATION_HOSTED` | `false` | `false` | `true` |
| Federation hub | Not registered | Optional | Auto-registered (free license) |
| Data persistence | Ephemeral (reset on demand) | Persistent | Persistent (backed up) |
| Public access | Yes (no auth wall) | Auth required | Auth required |
| Backups | None | Nightly (autobrain-backup) | Nightly + offsite |

## Reset & Maintenance

- **Manual reset:** Set `DEMO_RESET=true` in Portainer stack env → redeploy. Or run `reset_demo()` via backend shell.
- **Auto-reset on seed change:** CI sets `DEMO_RESET=true` when `backend/app/db/seed.py` changes (AUT-521).
- **Test verification:** `backend/tests/test_seed_reset_demo.py` runs in CI (sqlite, no Postgres/MinIO) and validates FK-safe ordering.
- **Health check:** `GET /health` returns `{"env": "demo", ...}` when `DEMO_MODE=true`.

## Known Constraints

- **Shared Postgres/MinIO with Default:** Resource contention possible. Demo is lower priority.
- **No backups:** Demo data is disposable.
- **Rate limits:** Demo users hit the same API rate limits as real users.
- **AI calls:** Go through shared 9Router; demo traffic counts against the same quota.
- **No email/SMTP:** Password reset, notifications disabled for demo.

## QA Usage

- `backend/tests/health_demo.test.py` — HTTP smoke tests against live demo URL.
- `backend/tests/test_demo_fuel_seed.py` — validates fuel seed data.
- Run locally: `DEMO_MODE=true pytest backend/tests/test_seed_reset_demo.py -q` (sqlite).

## Related Docs

- [Website Documentation](./website.md) — marketing site (separate repo)
- [Community Garage](./community-garage.md) — demo shows local-only social
- [Deployment Docs](../Deployment-and-Infrastructure/) — stack definitions

Source: `docker-compose.yml`, `backend/app/core/config.py`, `backend/app/db/seed.py`, `backend/tests/test_seed_reset_demo.py`.