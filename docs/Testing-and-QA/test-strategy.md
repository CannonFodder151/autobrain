# Test Strategy

**Owner:** QA & User Testing. **Section:** Testing & QA. **Last reviewed:** 2026-08-10 (AUT-182).

## Purpose

Define how AutoBrain is tested across the backend, AI gateway and frontend, what is covered, and how results are reported. Real state only — mirrors repo `docs/test-strategy.md`.

## Environments

| Environment | Where | Purpose |
|-------------|-------|---------|
| Dev box | `192.168.1.100` (Portainer endpoint 6, PaperClip-AutoBrain-Dev-Box) | Primary test target for agent test passes |
| Demo | `demo.autobrainservice.app` (demo@autobrainservice.app / demo) | Promotion tier 1 |
| Default | Default deployment tier | Promotion tier 2 |
| Hosted | `hosted.autobrainservice.app` (Oracle VM, Portainer endpoint 5) | Production |

Mandatory promotion order **Demo → Default → Hosted** (per AUT-107). No tier is skipped when shipping.

## Automated tests

There is **no CI/CD pipeline** at this time — GitHub Actions were removed. Tests run manually in the running stack:

```bash
docker compose -f docker-compose.prod.yml exec backend pytest
docker compose -f docker-compose.prod.yml exec ai pytest
```

### Backend (`backend/tests/`)

| File | Covers |
|------|--------|
| `test_api.py` | Core smoke: auth (password hashing, JWT round-trip), `/health`, vehicle creation |
| `test_billing.py` | Billing paths |
| `test_service_delete.py` | Service-record deletion |
| `test_service_scheduled_timeline.py` | Scheduled service timeline |
| `test_share.py` | Vehicle sharing |
| `test_share_access.py` | Share access control |

### AI gateway (`ai/tests/`)

`test_fallbacks.py` — rule-based fallback engines used when 9Router is unreachable (diagnostics, resale value, receipt OCR extraction, mod impact, service prediction). Fallbacks are deterministic and tested without a router dependency.

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
