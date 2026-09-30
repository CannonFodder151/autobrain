# Test Strategy

**Owner:** QA & User Testing. **Section:** Testing & QA. **Last reviewed:** 2026-09-28 (AUT-4395).

## Purpose

Define how AutoBrain is tested across the backend, AI gateway and frontend, what is covered, and how results are reported. Real state only — mirrors repo `docs/test-strategy.md`.

## Environments

| Environment | Where | Purpose |
|-------------|-------|---------|
| Dev box | `10.0.3.39` (Portainer endpoint 6, PaperClip-AutoBrain-Dev-Box) | Primary test target for agent test passes |
| Demo | `demo.autobrainservice.app` (demo@autobrainservice.app / demo) | Promotion tier 1 |
| Default | Default deployment tier | Promotion tier 2 |
| Hosted | `hosted.autobrainservice.app` (Oracle VM 152.69.188.133, Portainer endpoint 5) | Production |

Mandatory promotion order **Demo → Default → Hosted** (per AUT-107). No tier is skipped when shipping.

## Stack context (current)

- **Database**: PostgreSQL 17 with **pgvector** extension (`pgvector/pgvector:pg17`) for embeddings
- **Containers**: Non-root, read-only filesystems, `cap_drop: ALL`, tmpfs for writable dirs (see `docker-compose.prod.yml` and `docker-compose.hosted.yml`)
- **AI gateway**: Runs inside the backend container on port 8001 (AUT-2000); 9Router provides model routing at `http://9router:20128/v1` (Hosted) or `http://10.0.3.17:20128/v1` (Dev/Default/Demo)
- **Federation hub**: Community Garage hub service deployed on Hosted (`hub.autobrainservice.app`), registered by backend via `SOCIAL_FEDERATION_HUB_URL` (AUT-333, AUT-532)
- **Worker**: Merged into backend (AUT-3153) — Celery worker+beat run as background processes in the backend container
- **Backup**: Off-site backup runs as Celery beat task in backend (AUT-3827); standalone `backup-agent` removed; the GUI service is now named `backup` (AUT-3944)
- **Container count (Hosted)**: 10 services (postgres, redis, minio, backend, dongle-server, frontend, hub, 9router, gh-runner, backup)

## Automated tests (CI/CD)

GitHub Actions workflows exist (`.github/workflows/`). Key pipelines:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci-tests.yml` | PR, push to main | Backend + AI gateway pytest suites |
| `ci-queue-guard.yml` | PR | Enforces test pass before merge |
| `security-pr-gate.yml` / `security-pr-gate-rego.yml` | PR | Security scans (Trivy, dependency, secrets) |
| `build-hosted.yml` / `dockerhub-publish.yml` | main | Multi-arch image builds for Hosted (ARM64) |
| `deploy-instances.yml` | manual | Deploy to Dev/Default/Demo/Hosted via Portainer |
| `docs-sync-gate.yml` | PR | Validates docs/ mirror vs Outline |

Run backend + AI tests locally against the stack:

```bash
docker compose -f docker-compose.prod.yml exec backend pytest
docker compose -f docker-compose.prod.yml exec backend pytest ai/tests/
```

### Backend (`backend/tests/`)

| File | Covers |
|------|--------|
| `test_api.py` | Core smoke: auth (password hashing, JWT round-trip), `/health`, vehicle creation |
| `test_billing.py` | Billing paths (Stripe entitlement, pricing, checkout) |
| `test_service_delete.py` | Service-record deletion |
| `test_service_scheduled_timeline.py` | Scheduled service timeline |
| `test_share.py` | Vehicle sharing |
| `test_share_access.py` | Share access control |
| `test_search_sql_injection.py` | SQL injection guards on search |
| `test_config_fail_closed.py` / `test_config_prod_guard.py` | Fail-closed config, prod guards |
| `test_ws_auth.py` | WebSocket auth |
| `test_assets_backup.py` | MinIO backup/restore roundtrip |
| `test_workers.py` | Celery tasks (embedding backfill, receipt processed) |
| `test_fuel_feeds.py` / `test_fuel_prices.py` / `test_fuel_api.py` | Fuel feeds, prices, API |
| `test_rego_*` | Rego lookup, rate limits, log redaction |
| `test_seed_reset_demo.py` / `test_issues_blog.py` | Demo seed + reset, Community Garage |
| `test_services_extraction.py` | Extracted service modules (fuel stats, timeline, limits, shares) |
| `test_ai_router_key_file.py` / `test_aut206_security_hardening.py` | AI router key loading, security hardening |
| `test_embed_on_create.py` / `test_embedding_cache.py` | pgvector embedding write path + cache |
| `test_aut1181_secret_guards.py` / `test_aut1607_rego_rate_limit.py` | Secret guards, rate limiting |
| `test_cors_wildcard_guard.py` / `test_nginx_bucket_prefix.py` | CORS, MinIO bucket prefix |
| `test_aut2249_ocr_review_guard.py` | OCR review flow |
| `test_dongle_firmware_api.py` / `test_device_verify_api.py` | OBD dongle firmware + device verify |
| `test_iap.py` | In-app purchase (Google/Apple) |
| `test_issues_federation.py` / `test_social_federation_config.py` | Community Garage federation |
| `test_logbook_club_reg.py` | ATO logbook + club rego |
| `test_market_data.py` | Market data scraper (Celery task) |

Full list: `ls backend/tests/ | grep -E '^test_'`.

### AI gateway (`ai/tests/`)

| File | Covers |
|------|--------|
| `test_fallbacks.py` | Rule-based fallback engines (diagnostics, resale, receipt OCR, mod impact, service prediction) — deterministic, no router dependency |
| `test_advisor.py` | Advisor AI flows |
| `test_auth.py` | AI gateway auth |
| `test_car_check.py` | Car check via AI |
| `test_gateway_security.py` | Gateway security (key validation, rate limits) |
| `test_parts_guide.py` | Parts guide generation |
| `test_rate_limit.py` | Rate limiting |
| `test_router_validation.py` | 9Router response validation (AUT-141) |
| `test_social_image.py` | Social image generation |

## Manual test coverage areas (dev box / hosted)

Run against the dev box and recorded on each test pass:

1. **Auth & MFA** — sign-up, sign-in, session flow
2. **Vehicles CRUD** — add, edit, delete, list
3. **Services & fuel** — log service, fuel entries, scheduled timeline
4. **Receipts** — upload, OCR extraction
5. **Parts** — parts inventory
6. **Mods** — modifications tracking
7. **AI diagnostics** — symptom → diagnosis via 9Router (fallback path when router down)
8. **Rego lookup** — AU rego lookup API (VIC test vehicle `1ZZZ999`)
9. **Vehicle sharing / invites** — share a vehicle, access control, unshare
10. **Billing (Stripe)** — hosted only; Demo/Default do not run Stripe
11. **Community Garage / federation** — issue blog, builds feed, federation registration
12. **Servo Spy / fuel stations** — NSW/QLD/VIC/SA feeds, price alerts
13. **OBD dongle** — firmware, device verify, VIN read, clear codes
14. **Market data / resale valuation** — scraper task, valuation snapshots
15. **ATO logbook** — trip GPS, club rego

## Graft usage (codebase indexing)

For codebase navigation during test planning and debugging:

```bash
# Install
npm install -g @nanonets/graft

# Build graph (deterministic, no key)
graft build

# Orient: directory clusters, hubs, hotspots
graft map

# Find code for a task
graft ask "fuel price alert notification flow"

# Exhaustive search
graft grep "fuel_price_alert"

# API surface of a file
graft skeleton backend/app/services/fuel_feeds.py

# Call graph (in/out edges)
graft callers generate_embedding
graft callers generate_embedding --direction out

# Blast radius of a diff
graft blast --base origin/main
```

See [AUT-3169](https://paperclip.nathanmartina.com/issues/AUT-3169) for agent wiring.

## Bug triage flow (Discord intake)

1. User/staff posts to `#bug-reports` or `#feature-requests`.
2. n8n polls every 2 min and auto-creates a Paperclip issue (bug → Founding Engineer, feature → CTO), then reacts 👍.
3. QA picks issues up from the queue, verifies the repro against the dev box, captures steps + expected vs actual, and adds repro notes to the issue.

## Reporting

- Each test pass is logged to an Outline doc (this section, `QA Run Logs`) and summarised to `#testing` + `#updates` via the n8n Discord Reporter (embed format).
- The status-card chart (`/opt/autobrain-tools/status_card.py` on the dev box) is attached to status embeds when a picture helps.
- Release-blocking bugs are flagged to the CTO; fixes are verified on retest.

## Sign-off bar

A release ships when: automated suites pass in the stack, the manual coverage areas pass against the dev box, promotion order is followed, and no release-blocking (must-fix) bugs remain open. Every change also passes the two-gate change validation process (Security before build, QA immediately after push) defined in `docs/change-validation-gate.md` (AUT-241).

## Cross-links

- [QA Run Logs](./qa-run-logs.md) — chronological test pass records
- [User Testing Results](./user-testing-results.md) — verified bugs, feature verification
- [Change Validation Gate](../Engineering/change-validation-gate.md) — AUT-241 two-gate process
- [Container Architecture](../Engineering/container-architecture.md) — non-root, read-only, pgvector
- [AI Router Integration](../Engineering/ai-router-integration.md) — 9Router, fallback engines
- [Federation Hub](../Engineering/obd2-dongle/README.md) — Community Garage hub

## Manual test coverage areas (dev box / hosted)

Run against the dev box and recorded on each test pass:

1. **Auth & MFA** — sign-up, sign-in, session flow
2. **Vehicles CRUD** — add, edit, delete, list
3. **Services & fuel** — log service, fuel entries, scheduled timeline
4. **Receipts** — upload, OCR extraction
5. **Parts** — parts inventory
6. **Mods** — modifications tracking
7. **AI diagnostics** — symptom → diagnosis via 9Router (fallback path when router down)
8. **Rego lookup** — AU rego lookup API (VIC test vehicle `1ZZZ999`)
9. **Vehicle sharing / invites** — share a vehicle, access control, unshare
10. **Billing (Stripe)** — hosted only; Demo/Default do not run Stripe

## Bug triage flow (Discord intake)

1. User/staff posts to `#bug-reports` or `#feature-requests`.
2. n8n polls every 2 min and auto-creates a Paperclip issue (bug → Founding Engineer, feature → CTO), then reacts 👍.
3. QA picks issues up from the queue, verifies the repro against the dev box, captures steps + expected vs actual, and adds repro notes to the issue.

## Reporting

- Each test pass is logged to an Outline doc (this section, `QA Run Logs`) and summarised to `#testing` + `#updates` via the n8n Discord Reporter (embed format).
- The status-card chart (`/opt/autobrain-tools/status_card.py` on the dev box) is attached to status embeds when a picture helps.
- Release-blocking bugs are flagged to the CTO; fixes are verified on retest.

## Sign-off bar

A release ships when: automated suites pass in the stack, the manual coverage areas pass against the dev box, promotion order is followed, and no release-blocking (must-fix) bugs remain open. Every change also passes the two-gate change validation process (Security before build, QA immediately after push) defined in `docs/change-validation-gate.md` (AUT-241).
