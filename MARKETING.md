# AutoBrain — Positioning (Phase 1)

**From "AI demo" to a posture-aware product that works even when AI is down.**

## Problem
Teams ship without a single, concrete read on code/security readiness — and most "AI" tooling goes blind the moment a model has a bad day.

## Solution
AutoBrain runs every feature on a deterministic rule-based path first; 9Router only enriches when reachable. Phase 1 consolidated the backend + worker + AI gateway into a single image, added pgvector-backed semantic retrieval, and made the AI layer optional rather than blocking.

## Proof points
- `backend/app/services/vector_search.py` — pgvector-backed semantic retrieval for car records
- `ai/app/router_utils.py` — `_AI_IMMUTABLE` entries for diagnostics + service-prediction (deterministic-first AI)
- `backend/app/fallbacks/` (ai) — rule-based fallbacks run first, AI enriches only when reachable
- `docker/` — single consolidated container image (backend + worker + AI gateway)
- `docs/Marketing-and-Website/phase1-positioning.md` — CMO-approved claim substantiation

## Positioning statement
**AutoBrain: Let AutoBrain do the thinking — even when AI is down.**

## Phase 1 messaging guardrails
- Lead with *readiness*, not *automation*
- Prove with shipped code, not buzzwords
- "Works without AI" — accurate; "we ditched AI" — false
- No performance-percentage claims (no benchmark run yet)
- No VASS compliance claims (Phase 2 scope)
EOF