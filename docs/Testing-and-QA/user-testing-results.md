# User Testing Results

**Owner:** QA & User Testing. **Section:** Testing & QA. **Last reviewed:** 2026-08-10 (AUT-182).

Verified results from user-facing testing and bug intake triage. Real state only — mirrors repo `docs/user-testing-results.md`. Newest first.

## Triage process

Users/staff post to `#feature-requests` and `#bug-reports`; the n8n intake pipeline auto-creates a Paperclip issue (feature → CTO, bug → Founding Engineer) and reacts 👍. QA picks items from the queue, verifies the repro on the dev box, and records steps + expected vs actual on the issue.

## Verified bug reports

| Issue | Report | Repro verified | Result |
|-------|--------|----------------|--------|
| AUT-19 | Dropdown doesn't select a car but car card is populated | Yes (dev box) | Fixed — stale vehicle instance, added `==`/`hashCode` |
| AUT-20 | Sign-up "already have an account, sign in" → white page | Yes | Fixed — root-route `Navigator.pop()` |
| AUT-14 | Searching a motorcycle crashes the API | Reproduced | Opened for fix + regression test (rejected/cancelled upstream) |
| AUT-100 | Motorcycle rego lookup fails for VIC | Yes — VIC lookup returns | Use test plate `FZR60` for VIC testing |
| AUT-146 | Resale value way off (Crown shown ~2,253 vs ~14,000 real) | Yes | Valuation logic reviewed + reworked (see AUT-161 fix) |
| AUT-147 | Delete user/vehicle with shares → HTTP 500 (FK violation) | Found during AUT-133 deployment test | In review — Founding Engineer fix pending |

## Feature verification (user-facing)

| Feature | Result |
|---------|--------|
| Vehicle sharing / invites (AUT-16/21/115) | Verified on Demo, Default and Hosted (AUT-133) |
| Billing / Stripe (Hosted) | Verified go-live (AUT-117) |
| Sign-up email (M365 Direct Send) | Verified on Hosted EP5 (AUT-88/81/97) |

## Test passes against the dev box

Per AGENTS.md, test passes cover auth/MFA, vehicles CRUD, services/fuel, receipts, parts, mods, AI diagnostics (9Router), rego lookup, vehicle sharing/invites and billing. Each pass is logged to this section (QA Run Logs) and reported to `#testing` + `#updates` via the n8n Discord Reporter.

## Status card

The status-card chart (`/opt/autobrain-tools/status_card.py` on the dev box) is attached to test/status embeds when a picture helps.

## Sign-off

Release-blocking bugs are flagged to the CTO; fixes verified on retest before a release ships.
