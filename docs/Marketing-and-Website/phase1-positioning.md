# Phase 1 Positioning — Marketing Claim Substantiation

**Owner:** CMO · **Issue:** AUT-4072 (child of AUT-3810) · **Status:** awaiting human CMO approval in Discord `#marketing`

Phase 1 was an engineering initiative, not a feature release. This document records
what actually shipped, which marketing claims are therefore safe to make, and the
guardrails that keep us from over-claiming.

---

## 1. What Phase 1 actually shipped

| Workstream | Outcome | Status |
|---|---|---|
| (a) Container reduction | Backend + Celery worker + AI gateway consolidated into a single container image; hosted stack runs fewer services | Shipped (PR #614, merged `acccedaf`) |
| (b) Vectorised data | pgvector-backed semantic retrieval for car records, so lookups are index-assisted rather than full-table scans | Shipped |
| (c) Deterministic-first AI | Every AI feature now computes a rule-based answer first; 9Router enriches only when reachable and never blocks the response | Shipped — `_AI_IMMUTABLE` entries added for diagnostics and service-prediction (AUT-3913, PR #716) |
| (d) Modularity | Backend split toward domain modules; `admin.py`, `social.py`, `issues.py` being decomposed into subpackages | In progress (Workstream D, AUT-3829) |
| (e) Documentation | Engineering docs refreshed; deployment guide audited for EP5 specifics | In progress (Workstream E) |

## 2. Claims we can make (and why)

These are the only Phase 1 claims approved for use in marketing copy:

1. **"Every feature works without AI."** — Directly substantiated by the
   deterministic-first workstream. Turning the AI router off does not remove a
   feature; it removes the enrichment layer only.

2. **"Deterministic rule-based fallbacks run first."** — Substantiated. The
   deterministic path is the primary path, not a catch-all error branch.

3. **"AI enriches but never blocks."** — Substantiated by the `_AI_IMMUTABLE`
   work. An AI timeout degrades the answer, it does not fail the request.

4. **"Your records stay usable when the AI layer is offline."** — Substantiated;
   a consequence of (1) and (3).

5. **"Runs on a smaller footprint."** — Substantiated by the container reduction
   (workstream a). We can state the consolidation qualitatively. We should not
   publish an exact container-count number in copy until the hosted stack is
   re-verified end-to-end (AUT-3908 is still open), because the number currently
   reflects the merge, not a verified production count.

6. **"Open source (MIT), self-host on a cheap VPS."** — Long-standing claim,
   unchanged by Phase 1.

## 3. Guardrails — claims we must NOT make yet

- **No performance-percentage claims** ("2x faster", "40% quicker"). We have
  architectural reasons to believe retrieval and container consolidation improve
  things, but we have not run a benchmark, so any number would be invented.
- **No uptime or availability percentages.** Not measured.
- **Do not describe the AI layer as "removed" or "deprecated."** The AI gateway
  still runs and still enriches. "Works without AI" is the accurate framing;
  "we ditched AI" would be false and would annoy the people who use the AI parts.
- **Do not claim VASS compliance checking is live.** That is Phase 2 scope and
  still under construction.
- **No vector-search internals in customer-facing copy.** pgvector is an
  implementation detail; "finds your records fast" is the customer phrasing.

## 4. Positioning line

> **Let AutoBrain do the thinking — even when AI is down.**

Why this and not "reliable AI": a competitor could claim "reliable AI" and we
would have no way to differentiate. "Even when AI is down" is a claim only
AutoBrain can make, because it is the direct consequence of the deterministic
rewrite. It also happens to be the thing users care about — nobody wants a car
app that goes blind when a third-party model has a bad day.

Supporting line:

> Every AI feature runs on a deterministic rule-based path first. 9Router only
> enriches when reachable. Your records stay usable even when the entire AI
> layer is offline.

## 5. Where the copy lives

| Surface | Repo | Branch | State |
|---|---|---|---|
| Marketing site (index, features, hosted, selfhost) | `autobrainservice-website` | `phase1/cmo-marketing-refresh` | Pushed, PR pending approval |
| Demo app login screen (Phase 1 banner + tagline) | `autobrain` | `phase1/AUT-4072-demo-positioning` | This branch |
| Social content calendar (8 posts) | — | — | Tracked in AUT-3989 |

## 6. Open follow-ups

- AUT-3908 must close before we publish a specific container count.
- Workstream D (AUT-3829) must close before we claim modularity publicly.
- A benchmark is needed before any performance percentage is ever claimed.
