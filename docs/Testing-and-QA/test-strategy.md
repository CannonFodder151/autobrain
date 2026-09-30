# Test Strategy

**Owner:** QA & User Testing. **Section:** Testing & QA. **Last reviewed:** 2026-09-30 (AUT-4395).

Internal hosts, IPs and Portainer endpoints are deliberately omitted from this
public-repo copy — see [Sanitisation](#sanitisation-this-copy-is-public).

## Purpose

Define how AutoBrain is tested across the backend, AI gateway and frontend, what is covered, and how results are reported. Real state only. Mirrors the Outline page of the same name; this repo copy is the sanitised public mirror.

## Environments

| Environment | Where | Purpose |
|-------------|-------|---------|
| Dev box | Portainer endpoint 6 (`PaperClip-AutoBrain-Dev-Box`), address `<DEV_BOX_IP>` | Primary test target for agent test passes |
| Demo | `demo.autobrainservice.app` (demo@autobrainservice.app / demo) | Promotion tier 1 |
| Default | Default deployment tier | Promotion tier 2 |
| Hosted | `hosted.autobrainservice.app` (Oracle VM `<HOSTED_VM_IP>`, Portainer endpoint 5) | Production |

Mandatory promotion order **Demo → Default → Hosted** (per AUT-107). No tier is skipped when shipping.

## Stack context (current)

- **Database**: PostgreSQL 17 with the **pgvector** extension for embeddings
- **Containers**: image-level non-root (`USER autobrain` in `docker/backend/Dockerfile`). `docker-compose.prod.yml` adds `read_only: true` + `cap_drop: ALL` + tmpfs for `postgres`, `redis`, `minio`, `backend`, `frontend`. `docker-compose.hosted.yml` currently applies that hardening to **frontend only** — Hosted `backend` runs with a writable rootfs. Do not assume parity between the two files; read the file you are testing against.
- **AI gateway**: Co-located in the backend container — `uvicorn ai_app.main:app --port 8001` runs alongside the main API in the same `command` (AUT-2000). 9Router provides model routing at `http://9router:20128/v1` on Hosted (in-network service name) or the LAN 9Router host on Dev/Default/Demo.
- **Federation hub**: Community Garage `hub` service deployed on Hosted (`hub.autobrainservice.app`), registered by the backend via `SOCIAL_FEDERATION_HUB_URL` (AUT-333, AUT-532)
- **Worker**: Merged into backend (AUT-3153) — `celery ... worker -B` runs as a background process inside the backend container
- **Backup**: Off-site snapshot push runs as a Celery beat task in backend (`app.workers.tasks.backup_offsite_hourly`, AUT-3827); the standalone `backup-agent` service was removed. The separate `autobrain-backup` service is the backup *target* and remains in the stack.
- **Container count (Hosted)**: 10 services — postgres, redis, minio, backend, dongle-server, frontend, hub, gh-runner, 9router, autobrain-backup

## Sanitisation (this copy is public)

`docs/` in this repository is a public mirror of the internal Outline wiki. Per
AUT-4272 it must carry **no secrets and no internal-only content**:

- Internal host addresses, private IPs and public infrastructure IPs are written
  as placeholders (`<HOSTED_VM_IP>`, `<DEV_BOX_IP>`, `<PORTENER_HOST_IP>`), not literals.
- Credentials are written as `<SECRET_NAME>` placeholders, never values.
- Paperclip issue links are referenced by identifier (`AUT-XXXX`) without the
  internal control-plane hostname.
- Full environment addresses, Portainer endpoint IDs and reporter webhooks stay in
  the internal Outline copy only.

If you add an environment detail here, use the placeholder form.

## Automated tests (CI/CD)

GitHub Actions workflows live in `.github/workflows/`. Key pipelines:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci-tests.yml` | PR, push to main | **Backend** pytest only. `tests/test_health_demo.py` is the blocking gate; the full suite runs with `\|\| true`, so a full-suite failure is reported but does not fail the job (AUT-2119) |
| `backend-pytest-smoke.yml` | PR, push to main | Smoke pytest for model-metadata + alembic-head regressions (AUT-2277) |
| `security-pr-gate.yml` / `security-pr-gate-rego.yml` / `security-scan.yml` | PR | Security gates (Trivy, dependency, secrets) |
| `trivy-image-scan.yml`, `rego-arm64-build.yml` | PR / main | Image CVE scanning, rego-lookup ARM64 build |
| `visual_regression.yml` | PR (frontend paths), push to main | Desktop visual regression at 1280/1440/1920 |
| `code-review.yml` | PR | Automated code review |
| `build-hosted.yml` / `dockerhub-publish.yml` | main | Multi-arch image builds (Hosted is ARM64) |
| `deploy-instances.yml` | manual | Deploy to Dev/Default/Demo/Hosted via Portainer |
| `docs-sync-gate.yml` | PR | Validates `docs/` mirror vs Outline |
| `ci-queue-guard.yml` | schedule (every 10 min) | Cancels queued CI runs orphaned by a deleted/merged branch (AUT-1720). **Not** a test gate |

> **Coverage gap:** the AI gateway suite (`ai/tests/`) is **not** run by any
> workflow. It is not copied into the backend image either — `docker/backend/Dockerfile`
> copies `ai/app` → `ai_app` only — so `pytest ai/tests/` does not work inside the
> running container. AI gateway tests run only from a developer checkout with
> dependencies installed. Tracked in AUT-4748.

Run the backend suite locally against the stack:

```bash
docker compose -f docker-compose.prod.yml exec backend pytest

# AI gateway suite — from a checkout, not the container
cd ai && pytest
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

Graft (`trailhq/Graft`) builds a deterministic tree-sitter graph of the monorepo.
QA uses it to find the code under test, check its blast radius, and keep the
`docs/`-vs-code claims in this section honest.

```bash
# Install
npm install -g @nanonets/graft

# Build graph (deterministic tree-sitter, no API key needed)
graft build

# Orient: directory clusters, hubs, hotspots
graft map

# Find code for a task
graft ask "fuel price alert notification flow"

# Exhaustive search, grouped by enclosing symbol
graft grep "fuel_price_alert"

# API surface of one file
graft skeleton backend/app/services/fuel_feeds.py

# Call graph (in-edges by default; --direction out for callees)
graft callers generate_embedding
graft callers generate_embedding --direction out

# Blast radius of a diff
graft blast --base origin/main

# Freshness check — exits 1 if graft/ drifted
graft check
```

The `graft/` graph is a local cache and is gitignored. Queries auto-refresh the
graph first; pass `--no-refresh` to skip. Agent wiring was added in AUT-3169.

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
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md) — tier topology, promotion order
- [CI/CD](../Deployment-and-Infrastructure/ci-cd.md) — workflow reference
- [Vector Store](../Engineering/ai/vector.md) — pgvector schema and embeddings
