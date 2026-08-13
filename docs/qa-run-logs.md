# QA Run Logs

**Owner:** QA & User Testing. **Section:** Testing & QA. **Last reviewed:** 2026-08-10 (AUT-182).

Chronological log of verified test passes and verification runs. Real state only — mirrors repo `docs/qa-run-logs.md`. Newest first.

## 2026-08-13 — Pre-merge pass: AUT-523 billing hardening PR #107 (AUT-581, Gate 2)

Gate 2 verification of PR https://github.com/CannonFodder151/autobrain/pull/107 (branch `fix/AUT-523-billing-hardening` @ `c500753`, base `main` @ `574260b`). Change scope: billing entitlement hardening — an active subscription on a price this deploy doesn't map (e.g. a grandfathered pre-AUT-523 USD price archived in Stripe) **preserves** the user's entitlement instead of demoting them to free while Stripe keeps billing; demotion only on lapse/cancel. `plan_for_user` infers the plan from persisted entitlement for such subs. `scripts/stripe-setup.py` refuses to archive a wrong-currency price that active subscriptions still reference; `assert` → `sys.exit` (survives `python -O`).

**Suite: `backend/tests/test_billing.py` @ PR head — 18 passed** (14 pre-existing + 4 new). Ran from a fresh checkout at `c500753` with the pinned `requirements.txt` on Python 3.13; suite is self-contained (no live Stripe/Postgres needed). The 4 new tests, verified against the diff and by execution:

- `test_apply_subscription_preserves_entitlement_on_unknown_price` — active sub on unknown/archived price keeps `free_account=False` + plan caps (no silent demotion).
- `test_apply_subscription_demotes_non_active_unknown_price` — canceled sub on unknown price demotes to free (`free_account=True`, `max_vehicles=1`).
- `test_plan_for_user_unknown_price_active_sub_infers_plan` — active/trialing sub on unknown price infers `garage`/`enthusiast` from persisted entitlement.
- `test_stripe_setup_refuses_archive_while_active_subs_reference_price` — `scripts/stripe-setup.py` raises `SystemExit` and never calls `Price.modify` while an active sub references the price.

**Regression sanity (same file, all green):** pricing endpoint (`test_pricing_endpoint_public`, `test_pricing_matches_approved_plan`), checkout paths incl. promo codes (`test_checkout_*`, 6 tests) and early-adopter sale (`test_checkout_auto_applies_sale_on_monthly`, `test_pricing_no_sale_when_unconfigured`) — no regression in pricing/checkout/sale.

**Findings:** none. No release-blocking issues. Verdict: **deliverable** (failures would still be flagged; the parent AUT-523 owns any follow-up).

## 2026-08-11 — Post-push pass: AUT-218 search fix + AUT-205 merges (AUT-276, Gate 2)

Second post-push pass under the change validation gate. Covers commits merged to `main` after the AUT-249 base `b2ca584` (range `b2ca584..29f8c09`): the AUT-218 search-500 fix `da12cdf` (raw `IS NOT NULL` embedding filter — the ORM models don't map the pgvector column, so `getattr(model, vec_col).isnot(None)` raised `AttributeError`) and the AUT-205 batch — AUT-136 (push `receipt.processed` to the vehicle owner, not the vehicle id), AUT-141 (AI router response key/type whitelist), AUT-142 (OCR helpers → `app/ocr_utils.py`), AUT-143 (inline router logic → `services/`, incl. `search.py` import fix), AUT-200 (fail closed on default creds), AUT-137 (embedding backfill worker + queue on entity create/update + daily sweep).

**Automated suites (deterministic paths, run from `main` @ 29f8c09; no compose DB):**

- AI gateway `ai/tests/` — 35 passed (incl. new AUT-141 `test_router_validation.py`; AUT-142 OCR refactor green; AUT-249 baseline was 31)
- Backend `test_workers.py` — 1 passed (AUT-136: `receipt.processed` targets vehicle owner; exercises AUT-137 embed path)
- Backend `test_services_extraction.py` — 9 passed (AUT-143 extracted services: fuel stats, timeline, vehicle limit, share invites)
- Backend `test_config_prod_guard.py` — 7 passed (AUT-200 fail-closed default creds)
- Backend `test_config_fail_closed.py` — 3 passed
- Backend `test_search_sql_injection.py` — 2 passed
- Backend `test_ws_auth.py` — 5 passed
- Backend `test_assets_backup.py` — 2 passed

**Targeted verification — AUT-218 search fix (`da12cdf`):**

- Confirmed no `embedding` attribute exists on the entity models (root cause of the 500); no `getattr(model, vec_col).isnot(None)` remains.
- Fixed filter `text("{table}.{vec_col} IS NOT NULL")` compiles clean for the PostgreSQL dialect; `table`/`vec_col` come from the constant `_ENTITY_MAP` (never user input — no injection).
- Keyword path E2E against sqlite: scoped diagnostic returned, no 500 (deterministic fallback when embeddings are unavailable).
- Live 9Router `/embeddings` (`text-embedding-3-small`) returns a 1536-dim float vector; `generate_embedding()` works → vector path is live and additive to keyword.

**Live tier status:** the tested commits are merged under v0.3.7 — not yet deployed anywhere (demo still **0.3.6**, hosted still **0.3.5**). Promotion (Demo → Default → Hosted) pending deployment.

**Findings:** none release-blocking. Minor pre-existing lint F401 (`select as sa_select`, `workers/tasks.py:164`, commit `a795b4f6` — predates this scope). Test-isolation note: running `test_config_prod_guard.py` in the same pytest session as the sqlite-backed suites pollutes `os.environ` and forces a Postgres connect (DNS fail); the suites pass when run per-file — suite hygiene, not an app defect. DB-dependent suites (test_search_scope, test_share*, test_api, test_billing, test_service_*, test_logbook_club_reg) still need the compose Postgres; dev box SSH (`10.0.3.39`) not reachable this run — deferred to deployment-time pass.

## 2026-08-10 — Post-push pass: changes merged since 2026-08-08 (AUT-249, Gate 2)

First post-push pass under the change validation gate (docs/change-validation-gate.md). Changes merged to `main` since the last real app pass (2026-08-08, AUT-45): v0.3.6 release + auto version-cutting (AUT-240), CSP/X-Frame-Options/Referrer-Policy security headers (#32, AUT-236), WS auth fail-close (AUT-203), search SQL parameterization + search IDOR scoping (AUT-203/AUT-134), MinIO asset backup/restore admin endpoints (AUT-194), scripts executable bit (#35).

**Automated suites (run from `main` @ b2ca584, deterministic paths only):**

- AI gateway `ai/tests/` — 31 passed (fallbacks, auth, gateway security; no 9Router needed)
- Backend `test_config_fail_closed.py` — 3 passed
- Backend `test_search_sql_injection.py` — 2 passed (AUT-203 SQL param)
- Backend `test_ws_auth.py` — 5 passed (AUT-203 WS auth fail-close)
- Backend `test_assets_backup.py` — 2 passed (AUT-194 backup/restore roundtrip + archive members)

**Live tier check (hosted + demo):**

- `app_version` still **0.3.5** on both; `/` serves **no** CSP/X-Frame-Options/Referrer-Policy headers → v0.3.6 + security-header change are merged but **not yet deployed/promoted** to any tier. Promotion (Demo → Default → Hosted) pending deployment.

**Not runnable from this environment:** DB-dependent backend suites (test_search_scope, test_share*, test_api, test_billing, test_service_*, test_logbook_club_reg) need the compose Postgres; dev box SSH (`10.0.3.39`) not reachable this run — deferred to deployment-time pass. No release-blocking bug found in the runnable suites.

## 2026-08-10 — QA documentation pass (AUT-182)

Established this section. Wrote Test Strategy, QA Run Logs and User Testing Results (verified against the repo, Outline and Paperclip issues). No app changes tested.

## 2026-08-08 — Baseline smoke before Oracle cutover (AUT-45)

Baseline smoke on the live stack recorded ahead of the migration:

- Backend `/health` returned 200
- Rollback runbook + smoke checklist delivered as issue documents (DNS-flip rollback, on-prem stays up, 7-day green window, backup repoint guard)

## Rego lookup verification — Hosted (AUT-85/86)

- Redeployed `rego-lookup:hosted` on Oracle `152.69.188.133:8011` (Portainer EP5) with `PLAYWRIGHT=1` + `UNDETECTED=1`
- Verified VIC test vehicle **1ZZZ999** lookup succeeds
- Earlier arm64 blocker found and fixed during the redeploy

## Vehicle sharing — all tiers (AUT-133)

Deployed + verified vehicle sharing on **Demo → Default → Hosted** in mandatory promotion order:

- CI dockerhub-publish runs completed on `main`
- Found regression: deleting a user/vehicle with active shares → **HTTP 500 FK violation** (see AUT-147)

## Hosted billing go-live (AUT-117)

Verified Stripe billing on Hosted (`hosted.autobrainservice.app`, Oracle, Portainer EP5). Hosted-scoped change (Demo/Default don't run Stripe).

## Bug fixes verified

| Bug | Fix verified |
|-----|--------------|
| AUT-19 — dropdown doesn't select a car but card is populated | Yes — stale `Vehicle` instance across `_load()` refreshes; added `==`/`hashCode` |
| AUT-20 — sign-up "already have an account, sign in" white page | Yes — `Navigator.pop()` on root route fixed in `app.dart:48` |
| AUT-161 — car valuation on new cars | Yes — recent-model valuation no longer anchors to 2010 model base |

## Known open items

| Item | State |
|------|-------|
| AUT-147 — delete user/vehicle with shares → 500 FK violation (`vehicle_shares` not cleaned) | In review — routed to Founding Engineer |
| AUT-171 — QA re-review of backend/ai/frontend after AUT-134..143 fixes | Blocked — waits on fix issues; QA owns the re-review |
| AUT-172 — security re-review after AUT-134..143 | Blocked — Security Officer |
