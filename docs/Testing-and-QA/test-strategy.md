# Test Strategy

**Owner:** QA & User Testing. **Section:** Testing & QA. **Last reviewed:** 2026-09-28 (AUT-4395).

## Purpose

Define how AutoBrain is tested across the backend, AI gateway and frontend, what is covered, and how results are reported. Real state only — mirrors repo `docs/test-strategy.md`.

## Environments

| Environment | Where | Purpose |
|-------------|-------|---------|
| Dev box | `10.0.3.39` (Portainer endpoint 6, PaperClip-AutoBrain-Dev-Box) | Primary test target for agent test passes |
| Demo | `demo.autobrainservice.app` (demo@autobrainservice.app / demo) | Promotion tier 1 |
| Default | `default.autobrainservice.app` (Portainer endpoint 2) | Promotion tier 2 |
| Hosted | `hosted.autobrainservice.app` (Oracle VM 152.69.188.133, Portainer endpoint 5) | Production |

Mandatory promotion order **Demo → Default → Hosted** (per AUT-107). No tier is skipped when shipping.

All tiers run **pgvector/pgvector:pg17** (PostgreSQL + pgvector for embeddings) and **non-root containers** (nginx-unprivileged on :8080). The Hosted tier includes the **Community Garage federation hub** (`autobrain-federation-hub`, ghcr.io, AUT-333) which the backend registers with via `SOCIAL_FEDERATION_HUB_URL`.

## Automated tests

CI/CD runs via GitHub Actions on every push/PR to `main` (see `.github/workflows/ci-tests.yml`, `ci-queue-guard.yml`, `ci-triage-webhook.yml`, `security-scan.yml`, `visual_regression.yml`, `docs-sync.yml`). Tests also run manually in the running stack:

```bash
docker compose -f docker-compose.prod.yml exec backend pytest
docker compose -f docker-compose.prod.yml exec ai pytest
```

### Backend (`backend/tests/`)

87 test files covering auth, billing, services, vehicles, fuel, receipts, parts, mods, AI, rego, sharing, social, logging, search, workers, WebSocket, config guards, security, and demo seed/reset. Key suites:

| File | Covers |
|------|--------|
| `test_api.py` | Core smoke: auth (password hashing, JWT round-trip), `/health`, vehicle creation |
| `test_billing.py` | Billing paths (Stripe entitlements, pricing, checkout, sale) |
| `test_config_fail_closed.py` / `test_config_prod_guard.py` | Fail-closed defaults, production guard rails (AUT-200) |
| `test_search_sql_injection.py` / `test_search_scope.py` | Search param safety + IDOR scoping (AUT-203, AUT-134) |
| `test_services_extraction.py` | Fuel stats, timeline, vehicle limit, share invites (AUT-143) |
| `test_workers.py` | Celery tasks: receipt processed, embeddings (AUT-136, AUT-137) |
| `test_share.py` / `test_share_access.py` | Vehicle sharing + access control (AUT-133) |
| `test_aut206_security_hardening.py` | Security hardening assertions |
| `test_social_regression.py` / `test_issues_blog.py` | Community Garage federation + issues blog |
| `test_fuel_feeds.py` / `test_fuel_prices.py` | Servo Spy QLD/NSW/VIC feed ingestion + prices |

Full list: `ls backend/tests/`.

### AI gateway (`ai/tests/`)

| File | Covers |
|------|--------|
| `test_fallbacks.py` | Rule-based fallback engines (diagnostics, resale, receipt OCR, mod impact, service prediction) — deterministic, no 9Router needed |
| `test_auth.py` / `test_gateway_security.py` | AI gateway auth + security (rate limit, key rotation, whitelist) |
| `test_router_validation.py` | Response key/type whitelist (AUT-141) |
| `test_rate_limit.py` | Rate limiting + cost tracking |
| `test_advisor_*.py` | Advisor agents (dream, value, upgrade, replace, finance) |
| `test_car_check.py` / `test_car_check_ai.py` | CarCheck advisor |
| `test_parts_guide.py` | Parts guide agent |

Full list: `ls ai/tests/`.

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
11. **Community Garage** — federation hub posts, replies, My Builds, issue blog
12. **Servo Spy** — fuel station search + prices (QLD direct feed on Hosted/Default)

## Bug triage flow (Discord intake)

1. User/staff posts to `#bug-reports` or `#feature-requests`.
2. n8n polls every 2 min and auto-creates a Paperclip issue (bug → Founding Engineer, feature → CTO), then reacts 👍.
3. QA picks issues up from the queue, verifies the repro against the dev box, captures steps + expected vs actual, and adds repro notes to the issue.

## Codebase context — Graft

This repo is indexed with **trailhq/Graft** (`graft/`). Before grepping or reading source, use:

- `graft map` — orientation (clusters, hubs, hotspots)
- `graft ask "<task>" --source` — ranked nodes with inlined code spans
- `graft grep "<pattern>"` — exhaustive search grouped by symbol
- `graft callers <symbol> [--depth N]` — call graph in/out edges
- `graft skeleton <file>` — file API surface
- `graft build` — refresh graph (deterministic, no key)

Agent instructions in `AGENTS.md` include a Graft usage block (see `<!-- graft:start -->`).

## Reporting

- Each test pass is logged to an Outline doc (this section, `QA Run Logs`) and summarised to `#testing` + `#updates` via the n8n Discord Reporter (embed format).
- The status-card chart (`/opt/autobrain-tools/status_card.py` on the dev box) is attached to status embeds when a picture helps.
- Release-blocking bugs are flagged to the CTO; fixes are verified on retest.

## Related docs

- `docs/qa-run-logs.md` — chronological test pass log
- `docs/user-testing-results.md` — verified bug reports + feature verification
- `docs/change-validation-gate.md` — two-gate process (Security before build, QA after push)
- `docs/deployment-guide.md` — promotion order + release checklist (AUT-107)
- `docs/security.md` — security review scope
- `AGENTS.md` — agent instructions including Graft usage

## Sign-off bar

A release ships when: automated suites pass in the stack, the manual coverage areas pass against the dev box, promotion order is followed, and no release-blocking (must-fix) bugs remain open. Every change also passes the two-gate change validation process (Security before build, QA immediately after push) defined in `docs/change-validation-gate.md` (AUT-241).
