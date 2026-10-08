# Growth Metrics & Funnel

## Overview

This document defines the KPIs, funnel stages, measurement tools, and reporting cadence for AutoBrain growth. Metrics are tracked via **Buffer analytics** (social), **NGINX/server logs** (web), **backend telemetry** (product), and **Discord** (community). No third-party analytics (GA, Mixpanel, etc.) — privacy-first.

Every product-metric query below runs against the real schema in `docs/Engineering/database-schema.md`. Before adding a metric, confirm the table and column exist in `backend/app/models/` — several plausible-sounding tables (`servers`, `activity`, `sessions`) do **not** exist.

## North Star Metric

**Weekly Active Hosted Instances (WAHI)** — count of distinct AutoBrain-Hosted servers with ≥1 active user in the trailing 7 days. Correlates with revenue (hosted is free but drives federation hub licensing + premium upsell).

**What counts as an active instance:** a server is active if it has synced with the federation hub in the trailing 7 days (`social_server_config.last_inbox_sync` / `last_event_sync`). There is no per-request activity log — do not invent one. A hosted instance without a hub sync is unmeasurable for WAHI, not inactive; report it as such.

## Funnel Stages

```
Impressions (Buffer) → Clicks (UTM) → Demo Session → Hosted Signup → WAHI
                            ↓
                      Self-Host Deploy → GitHub Star / Docker Pull
```

| Stage | Metric | Tool | Target |
|-------|--------|------|--------|
| **Top** | Impressions (LinkedIn + FB) | Buffer `get_aggregated_post_metrics` | 50k/mo |
| **Top** | Profile visits | Buffer per-post clicks | 2k/mo |
| **Mid** | Demo sessions (unique) | NGINX logs `/demo*` + session cookie | 500/mo |
| **Mid** | Demo → Hosted signup click | UTM `demo_to_hosted` | 5% of demo sessions |
| **Bottom** | Hosted activations (new servers) | Federation hub registry | 20/mo |
| **Bottom** | WAHI (Week 4 retention) | Federation hub registry + `social_server_config` | 40% |
| **Advocacy** | GitHub stars | GitHub API | +100/qtr |
| **Advocacy** | Discord members | Discord API | +50/qtr |

## UTM Convention

All outbound links from social/website use:

```
utm_source=linkedin|facebook|twitter|discord|blog|reddit
utm_medium=social|organic|referral|email
utm_campaign=phase1-launch|selfhost-push|community-garage-teaser|changelog-<version>
utm_content=<asset-slug>  (e.g., blog-deterministic-ai, reel-ai-toggle)
```

Example: `https://demo.autobrainservice.app/?utm_source=linkedin&utm_medium=social&utm_campaign=phase1-launch&utm_content=blog-deterministic-ai`

## Buffer Analytics

**Tools:** Buffer MCP `get_aggregated_post_metrics` (org-level) + `get_post` (per-post).

**Query pattern (monthly):**
```bash
# Last 30 days, all channels
get_aggregated_post_metrics(orgId, startDateTime="2026-08-01T00:00:00Z", endDateTime="2026-08-31T23:59:59Z")

# LinkedIn only
get_aggregated_post_metrics(orgId, ..., channelIds=["<linkedin-channel-id>"])

# Tagged campaign
get_aggregated_post_metrics(orgId, ..., tags={in:["<tag-id>"]})
```

**Key metrics returned:** `postCount`, `reactions`, `comments`, `reach`, `impressions`, `engagementRate` (when all channels support it).

**Per-post deep dive:** `get_post(postId, includeMetrics=true)` → `reactions`, `comments`, `shares`, `clicks`, `impressions`, `metricsUpdatedAt`.

Channel and tag IDs are per-workspace values — read them from Buffer (`list_channels`) rather than pasting them into docs. See [Social Media Strategy](./social.md) for the verified publish rules.

## Website Metrics

**Source:** NGINX access logs on the marketing site host. Deployment team extracts weekly.

| Metric | Query | Notes |
|--------|-------|-------|
| Unique visitors (IP-anon) | `awk '{print $1}' \| sort -u \| wc -l` | Daily |
| Page views by path | `awk '/GET/ {print $7}' \| sort \| uniq -c \| sort -rn` | Exclude `/assets/*` |
| Demo clicks | `grep 'demo.autobrainservice.app'` | Referrer + UTM |
| Self-host clicks | `grep 'selfhost.html'` | Referrer + UTM |
| Blog reads | `grep '/blog/'` | Per-post via slug |

## Product Metrics (Backend)

**Source:** PostgreSQL (the backend DB only) + the federation hub registry. No external telemetry.

| Metric | Source | Cadence |
|--------|--------|---------|
| Hosted activations (new servers) | Federation hub registry — registered server count | Weekly |
| WAHI | Registered servers with a hub sync in the trailing 7 days | Weekly |
| Federated self-host licenses | Hub `server` records with an active license | Monthly |
| Premium conversion | `users.stripe_subscription_status` in the active set | Monthly |
| Demo engagement | Demo user rows in `users` (email from `DEMO_EMAIL`) + NGINX demo logs | Weekly |
| Self-host installs (est.) | Docker Hub pull count + GitHub clone traffic | Monthly |

**Conversion query (verified against `backend/app/models/user.py`):**

```sql
-- Premium conversion: active Stripe subscriptions, not the `role` column.
-- `users.role` holds admin/user/demo — there is no 'premium' role.
SELECT count(*)
FROM users
WHERE stripe_subscription_status IN ('active', 'trialing', 'past_due')
  AND created_at > now() - interval '30 days';
```

The active-status set is defined once in `backend/app/services/billing.py` (`ACTIVE_STATUSES`) — read it from there rather than hardcoding a second copy of the list. `past_due` counts as active because the subscription has not lapsed.

**Federation state per instance (real table):**

```sql
-- One row per server. hub_status: 'unregistered' | 'registered' | 'error'.
SELECT hub_status, feature_enabled, federation_enabled, last_inbox_sync
FROM social_server_config;

-- Instances that registered but have not synced in 7+ days: WAHI gaps.
SELECT server_name, last_inbox_sync
FROM social_server_config
WHERE hub_status = 'registered'
  AND last_inbox_sync < now() - interval '7 days';
```

Notes:

- **No `servers` table.** Hub-side registration and license records live in the federation hub service, which is a separate deploy with its own store — not the backend Postgres.
- **No `activity` or `sessions` table.** There is no generic event log or session table to query for active users; `social_server_config` sync timestamps and `devices.last_seen_at` are the real activity signals.
- **Demo logins** cannot be counted with a `sessions` query. Demo is a single seeded user (`seed_demo()`), so count demo *sessions* from NGINX access logs and demo *data* from the seeded rows.

## Reporting Cadence

| Report | Channel | Owner | Format |
|--------|---------|-------|--------|
| Weekly digest | Discord `#roadmap` | CMO agent | Embed: top 3 posts, WAHI delta, funnel snapshot |
| Monthly review | Discord `#updates` | CMO agent | Embed: full funnel, Buffer top/bottom 3, website top 5, product metrics |
| Quarterly board | Discord `#approvals` | CMO agent | Embed + Outline doc: YoY trends, CAC/LTV estimate, channel ROI |
| Incident impact | Discord `#incidents` | Deployment Lead + CMO | Embed: sessions affected, demo downtime, comms sent |

Report embeds through the n8n Discord Reporter webhook — never the Discord API directly. Format and colour conventions live in the root `AGENTS.md`.

## Dashboard (Manual, No Tool)

No live dashboard. CMO agent compiles the weekly/monthly embeds from raw queries. Future: n8n workflow to auto-generate the weekly digest from Buffer + NGINX + Postgres (when n8n gets Postgres + Buffer credentials).

## Attribution Model

**Last-touch UTM** for demo→hosted. **First-touch UTM** for GitHub stars (referrer header). Self-host installs are unattributed (Docker Hub doesn't pass referrer); proxy via GitHub traffic API.

## Baseline (2026-08, pre-Phase 1)

Historical baseline captured at the start of Phase 1. These numbers predate the container consolidation and the hub rollout, so do not present them as current.

| Metric | Value |
|--------|-------|
| Monthly impressions (LinkedIn+FB) | ~12k |
| Monthly demo sessions | ~80 |
| Monthly hosted activations | ~3 |
| WAHI (4-week retention) | ~25% |
| GitHub stars | 340 |
| Discord members | 120 |

## Related Docs

- [Social Media Strategy](./social.md) — channels, Buffer workflow
- [Content Calendar](./content-calendar.md) — campaigns driving funnel
- [Website Documentation](./website.md) — UTM landing pages
- [Database Schema](../Engineering/database-schema.md) — real tables and columns behind the product metrics
- [Container Architecture](../Engineering/container-architecture.md) — deployed services, non-root runtime
- [Marketing & Website Index](./index.md) — section overview, sanitisation rules

Source: Buffer MCP analytics (AUT-163), backend schema under `backend/app/models/`, NGINX logs, GitHub/Discord APIs. Product-metric queries verified against the repo schema.