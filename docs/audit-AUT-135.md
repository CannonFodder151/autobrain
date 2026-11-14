
## Detailed verification (live app logic)
- Rego lookup: `/api/v1/rego/lookup` returns deterministic data (TCRWN/VIC → Toyota Crown 1997) with VIN/body/colour/status; also `/api/v1/vehicles/rego-lookup` exists. Fallback implemented in `app.services.rego`.
- Reminders: `/api/v1/reminders` (POST/GET) + Home Assistant `/api/v1/ha/service-reminders`. Notification service has rego-expiry reminders and scheduling logic.
- Diagnostics/OBD: OBD routes under vehicles; diagnostics use `run_diagnostics` → AI gateway with deterministic fallback (`ai/app/fallbacks/diagnose.py`) providing plain-English explanation, severity, parts, cost ranges/cost guidance.
- Receipts: receipt upload/OCR under vehicles receipts; AI fallback `ai/app/fallbacks/ocr.py` + fuel OCR; processing pipeline present.
- Resale: `/api/v1/resale/estimate` + vehicle resale endpoints; deterministic `app.services.resale` fallback present.
- Fallbacks: comprehensive fallbacks under `ai/app/fallbacks/` for all AI-backed features.

All homepage claims verified present with deterministic fallbacks. Routes registered in API v1.
