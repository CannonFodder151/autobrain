# Ownership Advisor — AI Advisor (User Guide & Architecture)

The **Ownership Advisor** is AutoBrain's home-screen feature that answers the
question every enthusiast actually asks: *"What's the smartest ownership
decision for my car right now?"* It is the unified entry point that combines
vehicle value, replacement cost, upgrade paths, finance, dream-car affordability
and the AI Advisor recommendation behind one card.

This page covers the **AI Advisor module** (the last tab in the feature). The
other modules live as their own AI gateway modules; see the cross-links at the
bottom.

## Home-screen card

One entry point only. Tapping it opens the feature, which surfaces six internal
tabs:

1. **Value** — current market value, comparable listings, trade-in estimate
2. **Replace** — used/new replacement cost and the funding gap
3. **Upgrade** — upgrade options, similar vehicles, trade-up analysis
4. **Finance** — buy outright / finance / lease (future novated lease)
5. **Dream Car** — any-vehicle lookup, affordability, repayments
6. **AI Advisor** — *this document*

All six tabs feed the AI Advisor. The home screen shows one icon so the
feature can grow without renaming.

## What the AI Advisor does

Given a vehicle and the structured outputs of the other five modules, the AI
Advisor returns one of four decisions plus the reasoning:

```json
{
  "decision": "keep" | "upgrade" | "delay" | "strategy",
  "confidence": 0.0,
  "rationale": "...",
  "next_actions": ["..."]
}
```

- `keep` — your current car is the smart money move; specific reasons why.
- `upgrade` — there's a clear upgrade path worth pursuing; which car and why.
- `delay` — wait, the numbers will move in your favour; what to watch.
- `strategy` — split, lease-to-buy, novated, or other non-binary play.

The advisor **never invents prices**. It reasons only over the structured
outputs of the Value / Replace / Upgrade / Finance / Dream modules. Any number
in the response (value, gap, repayment, affordability) is one of those
module outputs verbatim, with its source attribution.

## Architecture

```
mobile ──► backend (FastAPI)
            └─ POST /api/v1/advisor/ai   {vehicle_id, tab_outputs}
                 └─ ai gateway (ai/app/advisor/ai.py)
                      ├─ fallbacks/advisor.py  → deterministic baseline
                      ├─ router_client.enhance(advisor, payload, baseline)
                      │    └─ 9Router POST /v1/chat/completions  (9router/Employee)
                      └─ validated, clamped result
```

- **Route:** `POST /advisor/ai` on the AI gateway; backend wrapper
  `backend/app/services/ai_client.py::run_advisor_ai(...)`.
- **Cache:** 24h, keyed by `(vehicle_id, sorted_module_outputs_hash)` via the
  Phase 1 vector store ([AUT-1967](/AUT/issues/AUT-1967)). Same inputs = same
  answer for 24h, so users see stable recommendations and the router isn't
  called twice for the same state.
- **Provenance:** the `model` field on the response is one of `rule-based-fallback`,
  `rule-based+ai`, or `deterministic-only`. Callers log which path answered.

## Data model

The advisor is a thin layer over module outputs; it does not own its own
tables. It reads:

| Source | Table / endpoint | Fields used |
|--------|-----------------|-------------|
| Vehicle | `vehicles` | make, model, year, odometer, fuel, condition, service history |
| Value | `/v1/resale` | estimated_value, low, high, currency, used_price, rrp |
| Replace | `/v1/replace` | used_replacement_cost, new_replacement_cost, funding_gap |
| Upgrade | `/v1/upgrade` | options, similar_vehicles, trade_up_analysis |
| Finance | `/v1/finance` | scenarios (outright, finance, lease), monthly, total_cost |
| Dream | `/v1/dream` | target_vehicle, affordability, estimated_repayment |

The advisor's only persisted state is the **advice cache** (24h TTL, keyed as
above) and an **advice log** for audit: `(vehicle_id, requested_at, inputs_hash,
decision, confidence, model, router_provenance_id)`. No PII, no chat history.

## AI Advisor contract

9Router is called in OpenAI chat-completions format, exactly like the other
AI modules. See [AI Router Integration (9Router)](../doc/autobrain-ai-router-integration-9router-EE71nK1qkm)
for the routing rule that every module follows.

System prompt (paraphrased — see `ai/app/advisor/prompt.py`):

> You are an ownership advisor for a single vehicle. You will receive structured
> results from five modules (Value, Replace, Upgrade, Finance, Dream). Reason
> strictly over those numbers. Never invent or estimate a market value,
> repayment, or affordability figure — if a number is absent, say so. Return
> a JSON object with `decision` (one of keep / upgrade / delay / strategy),
> `confidence` (0..1), `rationale` (≤ 280 chars, plain English), and
> `next_actions` (≤ 3 concrete steps). Do not include numbers you were not
> given. Do not include markdown.

`_AI_IMMUTABLE` for the advisor module:

- `estimated_value`, `low`, `high`, `currency` (from Value)
- `used_replacement_cost`, `new_replacement_cost`, `funding_gap` (from Replace)
- `monthly`, `total_cost`, `apr` (from Finance)
- `affordability`, `estimated_repayment` (from Dream)

These are ground truth from the deterministic modules; the router **cannot**
override them. The router may add `rationale`, `next_actions`, `confidence`
nudges, or `strategy` sub-types.

### Failure behaviour

- 9Router disabled / unreachable / HTTP error / timeout → `route()` returns
  `None` → the advisor returns the **deterministic baseline** untouched. The
  baseline is a small rule tree (e.g. if funding_gap > 0.5 * estimated_value
  → suggest `keep`; if upgrade saves ≥ 15% on 5-year TCO → suggest `upgrade`).
- A complete gateway failure is a clean 503, never a crash.
- The mobile app shows *"We're using a quick rule-based recommendation while
  the advisor reconnects"* when `model` is `rule-based-fallback`.

## Cross-links

- Feature spec / parent: [AUT-2425](/AUT/issues/AUT-2425)
- AI Advisor implementation: [AUT-2450](/AUT/issues/AUT-2450)
- Information architecture / API surface: [AUT-2452](/AUT/issues/AUT-2452)
- 9Router routing rule: [AI Router Integration (9Router)](../doc/autobrain-ai-router-integration-9router-EE71nK1qkm)
- Module catalog: [AI Modules — Module Breakdown](../doc/autobrain-module-breakdown-vSLUSQBpU2)
- Phase 1 cache (24h vector store): [AUT-1967](/AUT/issues/AUT-1967)

> Owned by Documentation Manager; updated as the feature ships. Departments
> update their section in the same change as the code. See the
> [Documentation Policy](../doc/documentation-policy-ENJQh7Wa40).