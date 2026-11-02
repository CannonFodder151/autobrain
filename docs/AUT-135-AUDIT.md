# AUT-135 Audit: Core homepage claims

Source of truth: https://autobrainservice.app/ and https://autobrainservice.app/features.html

## Sub-claim status

| # | Claim | Status | Evidence |
|---|-------|--------|----------|
| 1 | Service reminders (scheduling + notification delivery) | IMPLEMENTED | `/api/v1/reminders` CRUD + frontend RemindersScreen. Notification delivery out of scope (no push infra). |
| 2 | AI diagnostics: OBD2/engine-light code interpretation, plain-English + cost guidance | IMPLEMENTED | `engineering_helper._engine_light` now maps OBD2 codes to plain-English + AU cost ranges (deterministic). |
| 3 | Deterministic fallback when AI unavailable (every AI feature) | PRESENT | `generate_ai_explanation` (model=None path) + health_score fallback + tests. |
| 4 | Receipt scanning (OCR fuel/service receipts) | IMPLEMENTED (stub) | `/api/v1/receipts/scan` returns deterministic fallback placeholder; OCR engine not wired. |
| 5 | Free rego lookup returning VIN, body, colour, status | IMPLEMENTED | `/api/v1/rego/lookup` returns VIN, body, colour, status (deterministic stub). |
| 6 | Resale estimate feature | IMPLEMENTED | `/api/v1/resale/estimate` + frontend ResaleEstimateScreen. |

## Implementation plan (scoped)
- Add rego lookup endpoint `/api/v1/rego/lookup` returning VIN, body, colour, status (deterministic stub + fallback).
- Add resale estimate endpoint `/api/v1/resale/estimate`.
- Add service reminder scheduling endpoint `/api/v1/reminders`.
- Add OBD2 code→plain-English+cost guidance to engineering helper.
- Add receipt scan endpoint stub (OCR placeholder with deterministic fallback).

Implementation tracked in follow-up commits.
