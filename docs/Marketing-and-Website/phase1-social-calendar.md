# Phase 1 Marketing Refresh — Social Content Calendar (AUT-3972)

**Status:** Draft — pending human CMO approval
**Owner:** CMO agent
**Parent:** AUT-3968

## Narrative pillars (Phase 1)

| Pillar | One line | Proof point |
|--------|----------|-------------|
| **Simpler** | Fewer containers, easier to run | 9 → 8 long-running containers; worker merged into backend |
| **Vectorised** | Your data is searchable in your own DB | 1536-dim embeddings, pgvector, `AI_ENABLED` toggle |
| **Deterministic-first** | Works even when AI is down | `enhance()` pattern; `model: rule-based+ai` / `rule-based-fallback` |
| **Modular** | Add a feature, not a service | 13 modules, 14 fallbacks, shared `router_utils` |
| **Docs rebuilt** | Docs stay in sync with code | 8-section mirror + Outline source of truth |

## Week 1 (launch week)

| Date | Channel | Asset | Hook | CTA |
|------|---------|-------|------|-----|
| W1-D1 | Website (index, features, hosted, selfhost, ai-data) | Updated copy | "AI is an enhancement, not a dependency" | demo.autobrainservice.app |
| W1-D1 | Blog | Phase 1 outcomes post | "Phase 1 complete: simpler, faster, works even when AI is down" | /blog |
| W1-D1 | Discord #updates | Embed | Engineering refresh shipped | — |
| W1-D2 | Facebook | Blog link + 2-line teaser | "Your car app shouldn't stop working because the model had a bad day." | blog link |
| W1-D3 | LinkedIn | Long-form post | "Deterministic-first AI: a reliability pattern for production" | blog link |
| W1-D4 | Twitter/X | Thread (4 tweets) | 1/4: rule engine runs first. 2/4: 9Router enriches only when reachable. 3/4: immutable fields locked. 4/4: `model` field tells you which you got. | demo link |
| W1-D5 | Discord #changelog | Embed | Customer-facing changelog summary | — |
| W1-D6 | Instagram | Reel (30s) | "Tap to disable AI — diagnostics, valuations, OCR still work" | demo link |

## Week 2 (deep-dive)

| Date | Channel | Asset | Hook | CTA |
|------|---------|-------|------|-----|
| W2-D2 | Blog follow-up | "How the `enhance()` pattern keeps your valuations honest" | Resale numbers are immutable; 9Router can't touch them | /ai-data.html |
| W2-D3 | LinkedIn | Case-styled post | "9 containers → 8: what consolidating your stack actually saves" | /selfhost.html |
| W2-D4 | Twitter/X | Single image | "Your data, vectorised: search your garage in plain English" | /selfhost.html |
| W2-D5 | Discord #support | Embed | FAQ: "Does AutoBrain work without an AI router?" | — |

## Week 3 (self-host push)

| Date | Channel | Asset | Hook | CTA |
|------|---------|-------|------|-----|
| W3-D1 | Blog | "Self-hosting AutoBrain in 6 steps — Phase 1 edition" | Leaner container stack, faster boot | /selfhost.html |
| W3-D2 | Facebook | Short video | "Run AutoBrain on a $5 VPS" | selfhost link |
| W3-D3 | Reddit r/selfhost | Text post (follow sub rules) | "MIT, Docker-only, your data never leaves" | GitHub |
| W3-D4 | Twitter/X | Thread | "Receipt OCR without a model call: Australian vendor keyword matching" | /ai-data.html |
| W3-D5 | Discord #roadmap | Embed | Phase 1 marketing refresh status + weekly digest | — |

## Recurring

- **Weekly digest** → Discord #roadmap (every Monday): 3-bullet status + next-week plan.
- **Changelog sync** → Discord #changelog (on every deploy): one embed per release.
- **Incidents** → Discord #incidents (Deployment team owns triage; CMO reports customer-facing impact only).

## Approval gates (MANDATORY)

Every asset above is **draft only** until the human CMO approves in Discord #marketing via the n8n Reporter embed. Full publishable content (headline, body, captions, hashtags, CTAs, target channel + timing) must be posted inline in the approval embed — the human CMO has no Paperclip access. No auto-post, no auto-schedule.

## Source of truth

- Website copy: `autobrainservice-website` repo, branch `phase1/cmo-marketing-refresh`
- Blog draft: `drafts/AUT-3971-phase1-outcomes-blog.md`
- Facts: `autobrain` repo — `ai/app/router_client.py`, `ai/app/fallbacks/`, `backend/app/services/vector_search.py`, `docker-compose.hosted.yml`, `docs/Deployment-and-Infrastructure/container-consolidation-migration.md`, `phase1-improvement-plan.md`