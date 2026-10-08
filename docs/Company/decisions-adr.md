# Decisions Log & ADRs

Architecture Decision Records for AutoBrain. Newest first. Each entry is immutable once accepted — supersede, don't edit.

---

## ADR-001: All AI Calls Route Through 9Router

**Status:** Accepted
**Date:** 2026-07
**Deciders:** CEO, CTO

**Context:** Different roles and features needed different models. Direct provider calls scattered across the codebase made cost tracking impossible and blocked model swaps.

**Decision:** Every AI feature routes through the company's 9Router instance (OpenAI-compatible at `http://10.0.3.17:20128/v1`). C-suite uses the `9router/CEO` combo; all other roles use `9router/Employee`. If 9Router is unreachable, agents must say so rather than silently switching providers.

**Consequences:**
- Single choke point for cost, observability, and model policy.
- 9Router becomes a single point of failure — hosted environment runs its own instance to mitigate.
- Provider key management moves to Paperclip secrets.

---

## ADR-002: Deterministic Paths Before AI

**Status:** Accepted
**Date:** 2026-07
**Deciders:** CEO, Founding Engineer

**Context:** AI-generated answers were non-deterministic, slow, and expensive for lookups that could be answered with a rule.

**Decision:** Every AI function must have a deterministic path first. AI is the fallback. Rego lookups, price calculations, and OBD code decoding use structured data, not generation.

**Consequences:**
- Higher reliability and lower latency for the common path.
- Requires vectorised data stores so deterministic lookups stay fast.
- Target: ≥50% reduction in AI function calls during Phase 1.

---

## ADR-003: Mobile App Split Into Separate Repo

**Status:** Accepted
**Date:** 2026-08
**Deciders:** CEO, CTO

**Context:** The Flutter app mixes mobile and web targets in `frontend/`. Mobile has a different release cadence, different secret handling, and a different audience.

**Decision:** Split the mobile app into private repo `CannonFodder151/autobrain-mobile`. `frontend/` retains the web app.

**Consequences:**
- Tighter secret isolation for the mobile app.
- Independent CI/CD and release cadence.
- Requires an initial extraction PR and a Mobile Engineer hire.

---

## ADR-004: PR Auto-Merge After QA + Security Sign-Off

**Status:** Accepted
**Date:** 2026-09-03 (AUT-2230, AUT-2364)
**Deciders:** CEO

**Context:** Nathan was being repeatedly asked to approve PRs. He does not approve PRs. PR review was a bottleneck.

**Decision:** Every PR is squash-merged once QA, Security, and OCR sign-off is clean. The PR Gardener performs the merge. PRs never route through `#approvals` or `request_confirmation` interactions. No issues titled "Approve" or "[Approval]" for PRs.

**Amended (AUT-5561):** the merge is performed by the Paperclip gate script `merge-gated.mjs`, not by arming GitHub auto-merge. GitHub's own gate cannot express "QA **and** Security": `main` allows one approving review, so an armed auto-merge fires on a single role's approval. `allow_auto_merge` is therefore `false` on the repo, and the two-role requirement is enforced where it can be — in the gate script, which refuses unless both roles signed off at the exact current head from two distinct identities.

**Consequences:**
- Nathan's attention is reserved for genuine board decisions: budget, hires, contracts, major architecture, policy, incidents.
- Approved PRs must be merged immediately — never left open.
- PR Gardener skill is responsible for driving non-ready PRs back to green.
- The gate is bound to the head SHA it verified, so a push after sign-off blocks the merge instead of riding along on a stale approval.

---

## ADR-005: Post-Deploy QA Is Mandatory

**Status:** Accepted
**Date:** 2026-09 (AUT-3624)
**Deciders:** CEO

**Context:** Deployments were being marked complete without verification, letting regressions reach users.

**Decision:** Every deployment to any environment (Dev, Demo, Default, Hosted) must be followed by QA verification. The deploying agent creates a child issue `Post-deploy QA: {environment} — {change}` assigned to QA & User Testing. A deployment is not complete until QA signs off.

**Consequences:**
- Adds a mandatory step to every deploy.
- Regressions caught by GUI smoke tests (login, core features, API health).
- QA findings create follow-up bugs; Deployment Lead hotfixes or rolls back.

---

## ADR-006: Discord Is the Status and Approval Portal

**Status:** Accepted
**Date:** 2026-08
**Deciders:** CEO

**Context:** Status and approvals were scattered. The company needed one place for live state and board sign-off.

**Decision:** Discord server "AutoBrain HQ" is the main status and approval portal. All posts go through the n8n Discord Reporter as embeds — never bare text, never the Discord API directly. Channels: `status`, `approvals`, `updates`, `roadmap`, `incidents`, `ops`, `testing`, `support`, `changelog`, plus staff-only `feature-requests` and `bug-reports`.

**Consequences:**
- `status`, `approvals`, `updates`, `roadmap`, `incidents` are private (AutoBrain Staff role).
- `support` and `changelog` are public.
- Feature/bug intake auto-creates Paperclip issues via n8n workflow — do not duplicate.

---

## ADR-007: Outline Is the Documentation Source of Truth

**Status:** Accepted
**Date:** 2026-08
**Deciders:** CEO, Documentation Manager

**Context:** Documentation drifted between the wiki and the public repo.

**Decision:** Outline (collection: AutoBrain) is the internal source of truth and holds all docs including per-instance secrets. The public GitHub `docs/` directory is a sanitised mirror. Both are updated in the same change.

**Consequences:**
- No stale mirrors: Documentation Manager audits for drift and raises issues to the owning department.
- Public repo never contains secrets, internal endpoints, or board-sensitive notes.
- One topic per page, working index required.

---

## ADR-008: Batch Issues Must Be Decomposed Before Starting

**Status:** Accepted
**Date:** 2026-08-31 (AUT-1975)
**Deciders:** CEO

**Context:** Agents claimed to create sub-tasks by writing comments or inventing identifiers like `AUT-1964-1`.

**Decision:** When an issue lists multiple discrete items, immediately decompose into child issues — one per item — before moving the batch issue to `in_progress`. Each child sets `parentId`, `goalId`, and `assigneeAgentId`. Child `status` must be `todo` to wake the assignee. A batch issue with zero children is a defect.

**Consequences:**
- Real identifiers come from the Paperclip API (201 response), never invented.
- The liveness checker marks `needs_followup` and blocks parents that surface follow-ups but create zero children.

---

## ADR-009: Clone Repos With the gh Credential Helper, Never Tokenised URLs

**Status:** Accepted
**Date:** 2026-09
**Deciders:** CEO, Security Officer

**Context:** Embedding the GitHub PAT in a clone URL persists the token into `.git/config`, leaking it to disk.

**Decision:** `github_pat` is injected as env `GITHUB_TOKEN`. Clone with the plain HTTPS URL only; the gh credential helper injects auth at fetch time. Scratch clones are purged with `rm -rf` when done and never kept in `/tmp`.

**Consequences:**
- No token on disk in `.git/config`.
- Credential hygiene is auditable by the Security Officer's public-repo secret scan.

---

## ADR-010: Graft for Codebase Indexing

**Status:** Accepted
**Date:** 2026-09 (AUT-3168)
**Deciders:** CEO, CTO

**Context:** Agents needed fast, deterministic orientation into large repos.

**Decision:** Use `trailhq/Graft` for codebase indexing and context on every AutoBrain repo. `graft build` produces a deterministic tree-sitter graph (no key); `graft build --deep` adds LLM-written summaries. `graft map` orients, `graft ask` finds code, `graft grep` searches exhaustively, `graft callers` traces call graphs, `graft blast` shows the blast radius of a diff.

**Consequences:**
- Wiring is committed; the `graft/` graph itself is a gitignored local cache.
- Each teammate runs `graft build` after checkout.
