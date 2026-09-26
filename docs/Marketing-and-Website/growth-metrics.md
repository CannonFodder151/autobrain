# Growth Metrics & Funnel

## Overview

This document defines the KPIs, funnel stages, measurement tools, and reporting cadence for AutoBrain growth. All metrics are tracked via **Buffer analytics** (social), **NGINX/server logs** (web), **backend telemetry** (product), and **Discord** (community). No third-party analytics (GA, Mixpanel, etc.) — privacy-first.

## North Star Metric

**Weekly Active Hosted Instances (WAHI)** — count of distinct AutoBrain-Hosted servers with ≥1 active user in the trailing 7 days. Correlates with revenue (hosted is free but drives federation hub licensing + premium upsell).

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
| **Bottom** | Hosted activations (new servers) | Backend `server_created` event | 20/mo |
| **Bottom** | WAHI (Week 4 retention) | Backend weekly active query | 40% |
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
get_aggregated_post_metrics(orgId, ..., channelIds=["6a78595bb2d9d57743445c3c"])

# Tagged campaign
get_aggregated_post_metrics(orgId, ..., tags={in:["tag-phase1"]})
```

**Key metrics returned:** `postCount`, `reactions`, `comments`, `reach`, `impressions`, `engagementRate` (when all channels support it).

**Per-post deep dive:** `get_post(postId, includeMetrics=true)` → `reactions`, `comments`, `shares`, `clicks`, `impressions`, `metricsUpdatedAt`.

## Website Metrics

**Source:** NGINX access logs (Oracle VM, Portainer endpoint 3).  
**Extraction:** `grep` + `awk` on `/var/log/nginx/access.log` (Deployment team runs weekly).

| Metric | Query | Notes |
|--------|-------|-------|
| Unique visitors (IP-anon) | `awk '{print $1}' | sort -u | wc -l` | Daily |
| Page views by path | `awk '/GET/ {print $7}' | sort | uniq -c | sort -rn` | Exclude `/assets/*` |
| Demo clicks | `grep 'demo.autobrainservice.app'` | Referrer + UTM |
| Self-host clicks | `grep 'selfhost.html'` | Referrer + UTM |
| Blog reads | `grep '/blog/'` | Per-post via slug |

## Product Metrics (Backend)

**Source:** Postgres + custom events (no external telemetry).

| Metric | SQL / Event | Cadence |
|--------|-------------|---------|
| Hosted servers created | `SELECT count(*) FROM servers WHERE created_at > now() - interval '30 days'` | Weekly |
| WAHI | `SELECT count(DISTINCT server_id) FROM activity WHERE at > now() - interval '7 days'` | Weekly |
| Premium conversion | `SELECT count(*) FROM users WHERE role='premium' AND created_at > now() - interval '30 days'` | Monthly |
| Demo logins | `SELECT count(DISTINCT user_id) FROM sessions WHERE email LIKE 'demo@%' AND created_at > now() - interval '7 days'` | Weekly |
| Self-host installs (est.) | Docker Hub pull count + GitHub clone traffic | Monthly |

## Reporting Cadence

| Report | Channel | Owner | Format |
|--------|---------|-------|--------|
| Weekly digest | Discord `#roadmap` | CMO agent | Embed: top 3 posts, WAHI delta, funnel snapshot |
| Monthly review | Discord `#updates` | CMO agent | Embed: full funnel, Buffer top/bottom 3, website top 5, product metrics |
| Quarterly board | Discord `#approvals` | CMO agent | Embed + Outline doc: YoY trends, CAC/LTV estimate, channel ROI |
| Incident impact | Discord `#incidents` | Deployment Lead + CMO | Embed: sessions affected, demo downtime, comms sent |

## Dashboard (Manual, No Tool)

No live dashboard. CMO agent compiles the weekly/monthly embeds from raw queries. Future: n8n workflow to auto-generate weekly digest from Buffer + NGINX + Postgres (when n8n gets Postgres + Buffer credentials).

## Attribution Model

**Last-touch UTM** for demo→hosted. **First-touch UTM** for GitHub stars (referrer header). Self-host installs are unattributed (Docker Hub doesn't pass referrer); proxy via GitHub traffic API.

## Baseline (2026-08, pre-Phase 1)

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
- [Buffer Analytics Integration](../Engineering/buffer-mcp-integration.md) — technical details

Source: Buffer MCP analytics (AUT-163), backend telemetry, NGINX logs, GitHub/Discord APIs.