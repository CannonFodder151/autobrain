# Community Garage — Feature Concept & Workflows (AUT-294)

> **STATUS: APPROVED by board 2026-08-11 (plan rev 7).** This page captures the approved concept, workflows, and decisions for the Community Garage federated social layer. Implementation is gated until current in-flight jobs + QA/security testing are green (req 15). Marketing runs as "coming soon" only.

## 1. Idea

A **federated, privacy-preserving social layer** for AutoBrain. Every AutoBrain instance ("server") keeps its own data — users, vehicles, mods, photos stay in that server's Postgres + MinIO. Servers that opt in register with a central **federation hub** and exchange **build posts** (car photos + specs + mod list), so a build shared on one server can be seen, liked, and commented on from any other participating server.

Display identity: `<Display name> from <Server Name>`.

## 2. Guiding principles

1. **Data stays local.** The hub is a router + registry, not a data store. Post metadata and media live on the origin server; remote servers see them on demand (signed short-lived access) — never a central warehouse.
2. **Opt-in everywhere.** Server admins have two independent controls: (a) federated participation on/off (off keeps social working locally), and (b) the entire feature on/off (off shows "Disabled by your admin"). Users opt in per build and choose exactly what to share. Nothing is public by default.
3. **Deterministic, reliable.** No AI in the critical path. Existing vehicle/mod data drives the post content. AI only for optional enhancements, with deterministic fallbacks.
4. **Gate everything on QA + security.** No publish until the feature passes extensive QA and security testing.
5. **Demo is separate.** The demo server does not participate in the hub and shows curated demo builds.
6. **Premium gating.** Community Garage is a premium entitlement: free accounts cannot create/share builds, browse the social feed, comment, or like. Enforced server-side.
7. **Per-server monetization.** Local social is free on every server. Federation participation is a paid server license: self-hosted instances joining the hub pay **$20/year/server**, collected by the **hub itself at join time**. AutoBrain-hosted instances are licensed free. **Stripe runs only on the federation hub — end servers contain zero billing code.**

## 3. Feature map (requirements 1–19)

| #  | Feature | Where |
|-----|---------|-------|
| 1   | Photo upload (car) | Backend media API → MinIO; Flutter picker |
| 2   | Opt-in to sharing a build | `SocialBuild` opt-in flag per vehicle |
| 3   | Cross-instance posts | Federation hub (relay) |
| 4   | Hub hosting | Oracle VM (AutoBrain-Hosted, 152.69.188.133) — new lightweight service |
| 5   | Data stays on each server | Hub routes only; origin server authoritative |
| 6   | Two-tier admin control | (a) Federated participation on/off → off keeps social local-only; (b) feature entirely on/off |
| 7   | Facebook-style scrolling feed, mod-list driven, photos on main screen | New Social feed screen; content from existing vehicles + mods data |
| 8   | Garage → Social navigation | App shell nav item |
| 9   | Disabled vs local-only states | Feature off → "Disabled by your admin"; federated off → normal feed, local builds only |
| 10  | Demo shows demo data, no participation | Demo instance unregistered; seeded demo builds |
| 11  | User chooses what to share | Per-build share scope (photos / specs / mods / odometer / notes) |
| 12  | Shareable build link | Public (or signed) deep-link to a build, cross-instance |
| 13  | Comment + like posts | Social interaction models, synced via hub |
| 14  | Server registration (email + server name) | Hub registry; display "<Display name> from <Server Name>" |
| 15  | Extensive QA + security testing | Dedicated test phase; no publish until green |
| 16  | Marketing "coming soon" | Website update + blog post + social posts (active now) |
| 17  | New branch; no mobile app until done | `feat/community-garage` |
| 18  | Thorough documentation | Outline docs + repo `docs/` mirrors |
| 19  | Clarifications/concerns as decisions | Raised and resolved — see §7 |
| R4a | Premium gating (free-account lock) | Server-side entitlement check on all social routes |
| R4b | Marketing starts now | Website teaser, blog post, social posts — "coming soon", not live |
| R5a | Per-server monetization ($20/yr) | Hub-run Stripe (embedded Checkout, annual subscription) paid inline during registration |
| R5b | Payment at join | Admin pays the hub server directly at registration; auto-activates subscription — no activation codes |

## 4. Architecture

### 4.1 Components

* **Origin server (each instance)** — existing backend + MinIO. New modules under `backend/app/social/`:
  * Models: `SocialBuild`, `SocialPhoto`, `SocialComment`, `SocialLike`, `SocialShareScope`.
  * API: `/social/feed`, `/social/posts`, `/social/posts/{id}/comments`, `/social/posts/{id}/likes`, `/social/posts/{id}/share-link`, `/social/uploads`.
  * Entitlements: `require_premium` guard on all social write + feed-read routes.
  * Services: `social/federation.py` (hub client), `social/media.py` (MinIO upload, webp compress on upload, signed URLs), `social/snapshot.py` (build shareable snapshot from vehicles + mods data).
* **Federation hub (new, Oracle VM — existing capacity)**:
  * Registry: `server_id`, `server_name`, `email (private, verification only)`, `public_key`, `status`, `opted_out`, `license_status`.
  * Licensing: **Stripe integration here and only here** — embedded Checkout + webhook receiver; join-time payment auto-activates; license expiry check on every federation write.
  * Routing: post metadata relayed between subscribers; comment/like events fanned out.
  * Verification: signed requests, per-server API keys, rate limiting, block list.
* **Frontend (Flutter web + mobile)** — new screens: `SocialScreen` (feed), `MyBuildsScreen` (My Builds tab: list + edit caption + unshare own builds), `SocialPostDetail`, `SocialCompose`, `ShareLinkView`, `ServerSettings`, Garage → Social nav, "Disabled by your admin" state, premium upsell states.
* **Demo** — no hub registration; `DEMO_MODE` seeds demo builds.

### 4.2 Data flow

1. Admin enables Community Garage on server A → server A registers with hub (email + server name + public key).
2. User shares vehicle V → snapshot stored locally as `SocialBuild`; outbox entry queued.
3. Hub routes build metadata to subscribed servers B, C. Media stays on A; B/C fetch via signed short-lived URLs.
4. User on B likes/comments → event routed back to A for authoritative storage + fanned out to others. Eventual consistency.
5. Share link → resolves to build on A regardless of viewer's server.
6. **Origin unavailable:** remote build is not shown at all (no degraded/placeholder content).
7. **Federated opt-out:** if admin disables federation but leaves the feature on, the Social feed serves local builds only. No "Disabled by your admin" banner. Share links still work for local builds.
8. **Premium gate:** every social route checks entitlement before serving; free accounts get a clear upsell state.

## 5. Monetization model

* **Local is free, federated costs.** Federated participation: **$20/year per participating self-hosted server**. AutoBrain-hosted servers licensed free (bundled).
* **Stripe lives on the federation hub ONLY** — no Stripe code, keys, or checkout on end servers.
* **Payment at join time:** self-hosted admin pays via embedded Stripe Checkout (annual subscription) during hub registration; payment auto-activates the subscription; no activation codes.
* **Lifecycle:** annual renewal (auto-renew default). Expiry grace period (14 days) → hub blocks that server's federated posts; reverts to local-only social.
* **Scope:** the license gates federation participation only — distinct from per-user premium gating.

## 6. Delivery phases

* **P0 — Planning** (AUT-294): plan doc + Outline doc + decisions. **DONE — approved.**
* **P1 — Backend + hub:** social models/API/media, federation hub service, Oracle VM deploy, two admin toggles, local-only feed mode, demo seeding, premium entitlement guard, hub-run Stripe licensing.
* **P2 — Frontend:** feed, compose, detail, share links, comments/likes, Garage→Social nav, disabled state, premium upsell states.
* **P3 — QA + security:** OWASP/ZAP, pen-test, abuse/moderation tests, paywall bypass tests, cross-instance E2E on dev box. **Gate: no publish until green.**
* **P4 — Launch + marketing:** marketing campaign runs now (teaser/blog/socials, "coming soon"); launch content after the gate clears.
* **P5 — Docs:** Outline + repo mirrors, maintained throughout.

Branch: `feat/community-garage`. No mobile app release until P4 completes.

## 7. Decisions (board-resolved 2026-08-11)

 1. **Federation topology** → Hub-and-spoke relay on Oracle VM.
 2. **Media handling** → Compress on upload → webp; origin-signed URLs only; if the remote instance is down, its builds are not shown at all.
 3. **Moderation** → Hub admin (AutoBrain team) + per-server admins.
 4. **Registration email** → Verification/contact only, never public.
 5. **Share-scope defaults** → Minimal: photos + make/model + mod list.
 6. **Comment/like sync** → Hub fan-out, eventual consistency.
 7. **Cost** → Existing Oracle VM capacity (152.69.188.133); no new infra.
 8. **Federated opt-out** → Local-only social (feed shows local builds only); feature off → "Disabled by your admin".
 9. **Premium gating** → Community Garage is a premium entitlement; free accounts locked out; enforced server-side.
10. **Marketing timing** → Campaign starts now, positioning as "coming soon"; feature unpublished until P3 gate clears.
11. **Monetization** → Local free, federated costs; $20/year/server via Stripe; Stripe on the hub only; join-time payment auto-activates; no activation codes.
12. **License scope** → Gates federation participation only.
13. **License expiry** → 14-day grace, then local-only revert; auto-renewal default.
14. **Hosted servers** → Licensed free as part of the hosted product; no Stripe flow.

## 8. Workstream owners

| Workstream | Owner |
|------------|-------|
| Backend + federation hub architecture | CTO → Founding Engineer |
| Hub deployment (Oracle VM) | Deployment Lead |
| Security & privacy design | Security Officer |
| QA + security test strategy | QA & User Testing + Senior QA Reviewer |
| Marketing "coming soon" (active now) | CMO → Social Media Manager |
| Documentation | Documentation Manager |
| Monetization / Stripe licensing (hub-only) | CTO → Founding Engineer + Deployment Lead |

## 9. Gating

Feature is **not actioned** until: (a) all current in-flight jobs complete, and (b) QA/security testing of the current stack is green. Implementation child issues are parked in `backlog` until this gate clears. **Exception:** the marketing campaign (website teaser, blog post, socials) is active now — "coming soon" only, never presented as live.

Source: [AUT-294](https://paperclip.nathanmartina.com/AUT/issues/AUT-294) — plan document (rev 7, approved).

---

# Community Garage — Issues Blog (AUT-627)

> **STATUS: PLANNED — board approved plan 2026-08-14.** Implementation is in flight (P1/P2 backend + frontend), gated on the P3 QA + security gate before launch. This section documents the approved design; nothing here is shipped until the gate clears. Schema tables are pending the P1 migration.

## 1. Concept

A **blog-style help forum** inside Community Garage. An owner posts a car problem ("engine won't start", "rattle at 60km/h") with vehicle context; other owners reply with help in a chronological comment thread; the author (or a helper) can mark the issue **resolved** and pin the answer. Reads like an old blog: newest posts first, tag browsing, full post pages.

- **Community, not vehicle-scoped:** posts are visible to every premium Community Garage user across the federated network — NOT scoped to the author's own vehicles (unlike `/search`).
- **Old-blog style:** reverse-chronological list → full post page → threaded comments. No infinite-swipe feed; a browsable archive.

## 2. Principles (inherited from Community Garage)

1. **Deterministic first, AI never in the critical path.** Search, tags, and list filters work without AI; AI is optional enhancement only, with deterministic fallback (same hybrid pattern as `search.py`).
2. **Reuse, don't rebuild.** Same premium gating, feature toggle (`SocialServerConfig`), media/rate-limit/ownership plumbing, federation relay, and moderation model as Community Garage.
3. **Premium-gated.** Free accounts cannot post or comment (server-side enforcement).
4. **Safety by design.** Plain-text rendering (no raw HTML → no stored XSS), payload caps, rate limits, moderation + report flow, full QA + security gate before launch.
5. **Opt-in per admin.** Lives under the existing Community Garage admin toggles; no new billing, no new infra.

## 3. Data model

New models in `backend/app/social/` (extend the Community Garage module):

```
social_issue_posts
  id, author_user_id, author_display_name, server_name
  title (<=150), body (<=4000, plaintext)
  vehicle_snapshot_json   # deterministic snapshot from vehicle at post time (make/model/year/mileage bucket) — same pattern as SocialBuild.snapshot_json
  tags (string[] of fixed vocabulary)
  status: open|answered|resolved (default open)
  resolved_comment_id (nullable, set on resolution)
  origin: local|remote|demo
  remote_post_id, remote_server_id   # federation identity (mirrors SocialBuild)
  status_hidden: bool                # admin moderation flag
  created_at, updated_at
  embedding vector(1536)             # title + body + tags, via existing pgvector hybrid path

social_issue_comments
  id, post_id (FK), author_user_id, author_display_name, server_name
  body (<=2000, plaintext), is_answer (bool, one per post)
  created_at

social_issue_flags
  id, post_id, flagged_by_user_id, reason (<=200), created_at
```

- Reuses `SocialServerConfig`, the federation client (`federation.py`), `media.py` (photos), and `rate_limit.py`.
- DB migration via the existing Alembic flow (AUT-643).
- **Not in the database until the P1 migration lands.**

## 4. API routes

Extends `backend/app/api/v1/social.py` (or a sibling `issues.py` router) under `/api/v1`:

| Method | Path | Purpose |
|---|---|---|
| GET    | `/social/issues` | Blog list — reverse-chronological; filters `tag`, `status`, `q`; pagination (`cursor`/`limit`) |
| POST   | `/social/issues` | Create issue post (premium write, rate-limited) |
| GET    | `/social/issues/{id}` | Full post page incl. comments |
| PATCH  | `/social/issues/{id}` | Author edit (title/body/status) |
| POST   | `/social/issues/{id}/comments` | Add help comment (premium write) |
| POST   | `/social/issues/{id}/comments/{cid}/answer` | Mark answer + set post `resolved` (author or helper) |
| POST   | `/social/issues/{id}/flag` | Report abuse |
| DELETE | `/social/issues/{id}` | Author delete (mirrors build delete; 404-for-non-owners) |
| Admin  | hide/restore + list flagged | Via the existing admin API pattern |

## 5. Search integration

Register `issue` in `_ENTITY_MAP` (`backend/app/services/search.py`) as a **community-visible** entity (no vehicle scope). Keyword ILIKE always runs; pgvector cosine similarity ranks when embeddings are available. Blog browse stays deterministic — keyword-only fallback is already built in.

## 6. Moderation

- Flag/report flow: `POST /social/issues/{id}/flag` (flags capped per user per time window).
- Admin hide/restore sets `status_hidden`; hidden posts are excluded from search and browse.
- No AI moderation decisions — rule-based flag thresholds → admin queue.

## 7. Delivery & gate

P1 backend (AUT-643) → P2 frontend (AUT-644) → P3 QA + security (AUT-645/646) blocks launch → P4 docs + marketing (this doc, AUT-648/647) → P5 launch (AUT-649). Branch: `feat/issues-blog`. **No release until P3 is green.**

Source: [AUT-627](https://paperclip.nathanmartina.com/AUT/issues/AUT-627) — plan document (rev 1, confirmed 2026-08-14).
