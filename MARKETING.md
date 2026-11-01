# AutoBrain — Positioning (Phase 1)

**From "AI demo" to posture-aware health scoring.**

## Problem
Teams ship without a single, concrete read on code/security readiness.

## Solution
AutoBrain quantifies readiness via a health score API. Phase 1 ships a working scoring surface across backend + AI modules with a tracked security posture review.

## Proof points
- `backend/app/api/v1/health_score.py` + `backend/app/services/health_score.py` — API-first health scoring
- `ai/app/modules/health_score.py` — AI module path for scoring
- `SECURITY_POSTURE_REVIEW.md` — security posture tracked as a product concern, not an afterthought
- `Dockerfile` — containerized, deployable from Phase 1

## Positioning statement
**AutoBrain: Ship with confidence. Get an objective health + security read before you merge.**

## Focus for Phase 1 messaging
- Lead with *readiness*, not *automation*
- Prove with API + review doc, not buzzwords
- Sell clarity: "What blocks release?" over "AI magic"
