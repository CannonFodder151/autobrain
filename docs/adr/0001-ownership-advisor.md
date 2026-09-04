# ADR 0001 — Ownership Advisor: Information Architecture, Routing & 9Router Contract

- Status: **Accepted** (CTO lock, 2026-09-04; parent AUT-2425)
- Owner: CTO (AUT-2452)
- Implements: AUT-2425 (Ownership Advisor umbrella)
- Sub-tasks unblocked: AUT-2445/2446/2447/2448/2449/2450/2451 (Founding Eng)

## 1. Context

AutoBrain's Ownership Advisor is a new in-app surface that turns the user's existing vehicle data into six actionable sub-modules — Vehicle Value, Replace, Upgrade, Finance, Dream Car, AI Advisor — plus a single front-door ("Ownership Advisor") home card with nested chips that route into each sub-module. Five of the six sub-modules are deterministic and one (AI Advisor) reasons over the structured outputs of the other five. The product rule **deterministic-first, AI fallback** applies; the AI module must never invent prices.

The feature sits behind the existing auth + sharing rules, the existing entitlement gate (paid-only), and the existing offline cache. Six sub-modules + a front-door shell must ship in parallel behind a frozen public API surface; this ADR locks that surface.

## 2. Decision

### 2.1 Front-door route layout (Flutter web + mobile)

All routes are under a new top-level namespace `/advisor/*`. One home card on the existing `HomeScreen` opens the Advisor; chips/taps inside the Advisor navigate to sub-modules. No new top-level nav item is added — the Advisor lives under the existing Garage entry, matching the established pattern (see `frontend/lib/app.dart` line 89 `home: licenseRequested() ? ... : HomeScreen()`).

| Route (Flutter `MaterialApp` `routes`) | Backend path | Screen |
|---------------------------------------|--------------|--------|
| `/advisor` | n/a (Flutter-side hub) | `AdvisorOverviewScreen` |
| `/advisor/value` | `GET /api/v1/advisor/value` | `AdvisorValueScreen` |
| `/advisor/replace` | `GET /api/v1/advisor/replace` | `AdvisorReplaceScreen` |
| `/advisor/upgrade` | `GET /api/v1/advisor/upgrade` | `AdvisorUpgradeScreen` |
| `/advisor/finance` | `GET /api/v1/advisor/finance` | `AdvisorFinanceScreen` |
| `/advisor/dream` | `POST /api/v1/advisor/dream` | `AdvisorDreamScreen` |
| `/advisor/ai` | `POST /api/v1/advisor/ai` | `AdvisorAIScreen` |

Web deep-links use **path segments** (`/advisor/value`), not hash fragments, so they survive the Flutter web engine's `history.replaceState` URL normalisation that already breaks `#/license`-style deep links (see `frontend/lib/app.dart:24` `initialFragment` workaround). The reset-password token flow keeps its fragment because the email link can't be rewritten.

### 2.2 Deep-link schema

Two equivalent forms are accepted (mirrors the existing Community Garage share-link pattern at `app.dart:46-57`):

- **Flutter web**: `https://<host>/advisor/{value|replace|upgrade|finance|dream|ai}` (preferred; canonical)
- **Mobile universal-link / app-link**: same path, handled by existing universal-link plumbing if configured (out of scope for this ADR — TBD; the path scheme is the same regardless of surface)

Path tokens are constrained to the closed set `{value, replace, upgrade, finance, dream, ai}`; unknown tokens fall through to the existing `HomeScreen`. Dream Car and AI are POST-only because they need a body (Dream needs a target vehicle; AI needs the user-selected question). All others are GET, returning a structured JSON the screen renders.

### 2.3 State model

Each sub-module owns its own screen-local state, fed from a single backend response per visit. No global advisor state, no shared cache, no Riverpod/Provider graph extension. Rationale: the existing screens (`valuation_screen.dart`, `valuation.py` etc.) follow the same "screen fetches on mount, owns the result" pattern; deviating would couple the feature to a state library not used in the codebase. Cross-module inputs (e.g. Value into Replace) are passed via the AI Advisor's request body, not via shared state — keeps each module independently testable.

| Module | State | Input source |
|--------|-------|--------------|
| Overview | none (static layout + nav) | n/a |
| Value | screen-owned `Valuation?` | `GET /advisor/value` (uses current vehicle) |
| Replace | screen-owned `ReplacePlan?` | `GET /advisor/replace` (uses current vehicle) |
| Upgrade | screen-owned `UpgradePlan?` | `GET /advisor/upgrade` |
| Finance | screen-owned `FinancePlan?` (form state for down-payment, term) | `POST /advisor/finance` |
| Dream | screen-owned `DreamLookup?` (form state for make/model/year) | `POST /advisor/dream` |
| AI Advisor | screen-owned `AdvisorResult?` (form state for question) | `POST /advisor/ai` |

### 2.4 Persistent vs ephemeral inputs

| Input | Storage | Why |
|-------|---------|-----|
| Current vehicle selection (the "this car" pointer for Value/Replace/Upgrade/Finance) | Persistent | Already in the existing `vehicleId` selection; comes from `HomeScreen` and is passed via the existing `Provider<AuthState>` vehicle context |
| Finance form (down payment, term, rate) | **Ephemeral** (screen-state only) | Re-entered per session; no schema migration, no PII to back up; finance inputs are exploratory |
| Dream Car target (make/model/year) | **Ephemeral** (screen-state only) | Same — exploratory |
| AI Advisor question text | **Ephemeral** (screen-state only) | Question is per-visit; never persisted server-side |
| Last-known cached advisor response per (user, vehicle, module) | **Persistent** (offline cache) | The existing `frontend/lib/core/offline_cache.dart` covers `GET /advisor/*` and `POST /advisor/finance|dream|ai` (cache key includes request body hash for POSTs) |

No new persistent inputs are introduced. No DB migration. No user-settings tab.

### 2.5 Caching key shape

Backend cache + frontend offline cache share one key shape:

```
key = sha256(f"advisor:{module}:{vehicle_id or ''}:{stable_body_hash or ''}")
```

- `vehicle_id` is the user's current vehicle UUID; absent for Dream Car (which has no current car) and for AI Advisor (vehicle_id is in the body).
- `stable_body_hash` is `sha256` of the canonical-JSON request body with object keys sorted, applied to `POST` requests (`/advisor/finance`, `/advisor/dream`, `/advisor/ai`). The hash is computed in `frontend/lib/core/offline_cache.dart` (one new line: a `_bodyKey` function — see api-spec §4 for the contract) so the cache layer doesn't need to know module semantics.
- TTL is **24 h** (matches `market_listing_cache` at `backend/app/services/market_data.py:21`). Frontend cache uses the same TTL for parity.
- AI Advisor cache invalidates if the user re-submits with a different question body — the cache key changes because the body hash changes.
- The Dream Car target market-data lookup reuses `market_listing_cache` (same `(make, model, year)` key shape), no duplicate storage.

### 2.6 9Router integration contract

The AI Advisor module is the only module in this feature that calls 9Router. It reuses the existing `ai/app/router_client.py` (`route()`, `enhance()`, `_AI_IMMUTABLE`) — no new module is added to the gateway; the backend's `backend/app/services/ai_client.py` gains one new wrapper `advisor_recommend()` (one-line, mirrors `estimate_value()` at line 56). No new `ai/app/modules/advisor.py` — the AI Advisor's "intelligence" is **prompted against the structured outputs of the other five modules**, not a new inference task.

#### System prompt (strict JSON, mirrors the existing pattern in `ai/app/router_utils.py`)

```json
{
  "decision": "keep | upgrade | replace | delay | strategy",
  "confidence": 0.0,
  "rationale": "<= 280 chars, plain prose",
  "next_actions": ["<imperative verb> <object>", "..."],
  "model": "9router/<combo>",
  "based_on": {
    "value": "<module output fingerprint>",
    "replace": "<module output fingerprint>",
    "upgrade": "<module output fingerprint>",
    "finance": "<module output fingerprint>",
    "dream": "<module output fingerprint or null>"
  }
}
```

`_AI_IMMUTABLE` for this module = `{ "confidence_max", "currency", "based_on" }`. The model can name the decision and write rationale/next_actions, but cannot alter the underlying module outputs (they're passed in immutable) and cannot exceed the deterministic confidence ceiling (computed from input completeness).

### 2.8 9Router fallback (the contractual case)

When 9Router is unreachable, disabled, errors, or times out, the AI Advisor returns a **deterministic recommendation** computed entirely from the five module outputs. Pseudocode:

```
if router_enabled() and router_reachable() and ai_responded_with_valid_schema:
    return router_enrichment(decision=router.decision, ...)
else:
    decision, confidence = deterministic_decision(value, replace, upgrade, finance, dream)
    rationale = top_rule_rationale(decision, value, replace, upgrade, finance)
    next_actions = top_rule_actions(decision, value, replace, upgrade, finance)
    return AdvisorResult(
        decision=decision, confidence=confidence, rationale=rationale,
        next_actions=next_actions,
        model="rule-based-fallback",   # matches existing pattern at module-breakdown.md:29
        based_on=fingerprints,
    )
```

The deterministic path is **already shipped today** as the rule-based baseline of the AI gateway (see `docs/ai-router-integration.md:60-67` and `docs/module-breakdown.md:31`). The fallback never leaves the user without a decision; the AI step only adds optional enrichment. `model: "rule-based-fallback"` is the same value already used by `resale`, `service-prediction`, etc. when the router is down — proven pattern.

### 2.9 Error / entitlement envelope

| HTTP code | Trigger | UI |
|-----------|---------|-----|
| 200 | Happy path | Render response |
| 200 + `model: "rule-based-fallback"` | 9Router unreachable | Render same response; sub-label "Local recommendation (AI advisor offline)" |
| 401 | No / bad token | Existing global 401 handler; no special-casing |
| 403 | Free account (all six modules) or demo account (AI Advisor) | Existing entitlement card "Upgrade to enable" |
| 404 | Vehicle not found / no accessible vehicle | Existing empty-state widget |
| 429 | Rate-limited (`require_ai_rate_limit` already wraps AI endpoints) | Existing rate-limit message |
| 503 | AI gateway itself down | Bubble 503 with `{detail: "Advisor AI is temporarily unavailable — showing local recommendation"}`; fallback rule fires.

## 3. Cross-cutting consequences

- **Modularity**: each of the six sub-modules is a standalone FastAPI router + Flutter screen + offline-cache entry. No cross-module imports inside `backend/app/api/v1/`; the AI Advisor composes them via HTTP. Matches the existing `api/v1/__init__.py:34-53` pattern.
- **Deterministic-first**: enforced at three points — (a) `route()` returning `None` on any router error (existing), (b) `_AI_IMMUTABLE` blocking override of measured numbers (existing), (c) the `deterministic_decision()` fallback above (new, lives in `backend/app/services/advisor.py`).
- **No DB migration**: no new persistent state. Existing `valuation.py` history table is reused for `/advisor/value`; nothing new in `models/`.
- **No new containers**: nothing new on the stack. All six modules live in the existing `backend` container; no new AI gateway module is needed.
- **No new external dependency**: 9Router integration is via the existing `AI_ROUTER_URL` env var (see `docs/ai-router-integration.md:25-33`).

## 4. Acceptance criteria

- [x] Route layout frozen: `/advisor/{value|replace|upgrade|finance|dream|ai}` plus the front-door `/advisor`.
- [x] Deep-link schema frozen: closed path set; web path (not fragment) so it survives `history.replaceState`.
- [x] State model frozen: screen-local state only; no global state.
- [x] Persistent vs ephemeral inputs frozen: only the existing `vehicleId` selection persists.
- [x] Caching key shape frozen: `sha256("advisor:{module}:{vehicle_id}:{stable_body_hash}")`, 24h TTL.
- [x] 9Router integration contract frozen: reuses `route()`/`enhance()`/`_AI_IMMUTABLE`; new wrapper `advisor_recommend()` in `ai_client.py`.
- [x] Fallback frozen: deterministic path returns the same shape; `model: "rule-based-fallback"`; no user-facing failure when 9Router is down.

## 5. Sign-off

- CTO: locked (this ADR)
- Founding Eng sub-tasks may proceed in parallel: AUT-2445 (Value), AUT-2446 (Replace), AUT-2447 (Upgrade), AUT-2448 (Finance), AUT-2449 (Dream), AUT-2450 (AI), AUT-2451 (Front door).
- Docs: `docs/adr/0001-ownership-advisor.md` (this file) + `docs/api-spec.md` §Ownership Advisor (added in same PR).