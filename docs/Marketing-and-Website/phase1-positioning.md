# AutoBrain Phase 1 — Marketing Positioning

**Audience:** prospective users, existing customers, partners  
**Tone:** confident, technical but accessible, outcome-focused  
**Status:** draft — awaiting human CMO approval in Discord #marketing

---

## The Headline

**AutoBrain Phase 1: Simpler, Faster, More Reliable**

We rebuilt the stack from the inside out. Fewer moving parts. AI that falls back to deterministic logic. Search that’s instant. Code you can actually maintain.

---

## Shipped Outcomes (Phase 1a–1e)

| Workstream | What Changed | User-Facing Impact |
|------------|--------------|-------------------|
| **1a – Container Consolidation** | Merged AI gateway into backend; consolidated backup-agent into Celery beat; removed orphaned volumes | Fewer containers to fail, faster deploys, lower infra cost |
| **1b – Vector Search (pgvector)** | Regulatory corpus (VASS) now in Postgres/pgvector; embeddings served locally | Instant mod-legality lookups; no external vector DB dependency |
| **1c – Deterministic-First AI** | 6 modules (OCR, odometer, fuel-OCR, parts-guide, condition, mod-impact) run deterministic paths first; AI only as fallback with confidence thresholds | Predictable results, lower latency, lower LLM cost, audit trail |
| **1d – Modularity** | Backend split into domain modules (vehicles, modifications, bookings, users, analytics); AI gateway split into gateway/inference/embeddings/prompts/eval; frontend feature modules with shared package | Faster iteration, clear ownership, testable boundaries |
| **1e – Documentation Refresh** | All repo docs rewritten, synced to Outline, ADRs current | Accurate onboarding, trustworthy specs, faster contributor ramp |

---

## Approved Claims & Guardrails

### ✅ You CAN Say
- “Deterministic-first AI with LLM fallback” (6 modules shipped)
- “Instant regulatory search via local vector store (pgvector)”
- “Simplified architecture — fewer containers, faster deploys”
- “Modular codebase — domain-driven, independently testable”
- “Works even when AI is down” (demo tagline)

### ❌ Do NOT Say
- “AI-free” or “no AI” — AI is still the fallback
- “100% deterministic” — confidence-gated fallback remains
- Specific container counts (impl changes)
- “Self-hosted only” — we offer hosted + self-hosted
- Any claim about features not yet shipped (VASS marketplace, Track mode, etc.)

---

## Website Copy Status (autobrainservice.app)

| Page | Phase 1 Section Added? | Human CMO Approved? |
|------|------------------------|---------------------|
| index.html | ✅ (hero + feature grid) | ⏳ Pending (PR #132) |
| features.html | ✅ (deterministic AI card) | ⏳ Pending |
| hosted.html | ✅ (architecture simplification) | ⏳ Pending |
| selfhost.html | ✅ (modularity note) | ⏳ Pending |
| ai-data.html | ✅ (vector search + deterministic paths) | ⏳ Pending |
| about.html | ✅ (Phase 1 outcomes summary) | ⏳ Pending |

**Branch:** `phase1/cmo-marketing-refresh`  
**PR:** #132 (open, blocked on Azure SWA staging quota)

---

## Demo Site Messaging (demo.autobrainservice.app)

**Tagline:** *“Your garage, your data — deterministic-first AI.”*  
**Banner (login screen):** Explains demo is read-only; every feature works with AI router disabled.  
**Footer note:** Phase 1 engineering refresh deployed.

**Branch:** `phase1/demo-site-messaging`  
**PR:** #761 (open, failing alembic heads smoke test — pre-existing, unrelated)

---

## Social Content Calendar (Phase 1 Narrative)

8 posts staged across 2 Discord embeds in #marketing:

1. **Architecture Simplification** — “Fewer containers. Faster deploys. Less to break.”
2. **Deterministic-First AI** — “AI when you need it. Deterministic when you don’t.”
3. **Refreshed Docs** — “Documentation that matches the code.”
4. **Performance Gains** — “Sub-200ms regulatory lookups.”
5. **Vector Search** — “Your regs, indexed locally. No external deps.”
6. **Modular Codebase** — “Domain boundaries you can actually test.”
7. **Community Spotlight** — User story / workshop partner quote
8. **Phase 2 Teaser** — “What’s next: VASS marketplace, Track mode, mobile split.”

**Tracking issue:** AUT-3989 (`in_review`) — awaiting human CMO approval in Discord #marketing  
**Scheduling:** Buffer (LinkedIn + Facebook) once approved

---

## Next Steps

1. **Human CMO approves** website copy (PR #132) + social calendar (AUT-3989) in Discord #marketing
2. **Infra unblocks**: Azure SWA staging quota cleaned up (Deployment team); alembic heads merged (Engineering)
3. **Merge PRs** → auto-deploy to demo.autobrainservice.app + autobrainservice.app
4. **Schedule social posts** via Buffer
5. **Post launch update** to Discord #updates + #roadmap

---

## Related Issues / PRs

- AUT-3970 — website copy (PR #132)
- AUT-3972 — social calendar (PR #759)
- AUT-3973 — demo site messaging (PR #761)
- AUT-3989 — human CMO approval tracking
- AUT-4050 — docs refresh (merged PR #771)
- AUT-3810 — Phase 1 parent initiative
