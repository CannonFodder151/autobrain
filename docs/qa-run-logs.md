# QA Run Logs

**Owner:** QA & User Testing. **Section:** Testing & QA. **Last reviewed:** 2026-08-10 (AUT-182).

Chronological log of verified test passes and verification runs. Real state only — mirrors repo `docs/qa-run-logs.md`. Newest first.

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
