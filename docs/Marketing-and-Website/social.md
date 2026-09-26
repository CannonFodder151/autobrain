# Social Media Strategy

## Overview

AutoBrain's social presence focuses on **LinkedIn and Facebook** as primary channels. Twitter/X is used for engineering threads. Instagram Reels are experimental. Discord is the community hub (not a marketing channel). All publishing routes through **Buffer** (MCP integration) with human CMO approval in Discord `#marketing`.

## Channels & Configuration

| Platform | Channel | Buffer Channel ID | Page/Handle | Status |
|----------|---------|-------------------|-------------|--------|
| LinkedIn | Company Page | `6a78595bb2d9d57743445c3c` | autobrainservice ("AutoBrain") | Active |
| Facebook | Page | `6a7859acb2d9d57743445d31` | AutoBrain | Active |
| Twitter/X | Profile | Not in Buffer | @autobrainservice | Manual only |
| Instagram | Profile | Not in Buffer | @autobrainservice | Experimental (Reels) |
| Threads | Profile | Not in Buffer | @autobrainservice | Not used |
| Bluesky | Profile | Not in Buffer | — | Not used |
| YouTube | Channel | Not in Buffer | AutoBrain | Not used |

**Buffer org:** "My Organization" (auto-detected via MCP).

## Publishing Rules (Buffer MCP)

Verified in AUT-163:

- **Scheduling type:** `automatic` (required — `notification` rejected: "Notification scheduling is not supported").
- **Facebook posts:** Require `metadata.facebook.type` (`post` | `story` | `reel`).
- **Draft-first:** Always `saveToDraft: true` until human CMO approves. Never auto-publish without sign-off.
- **Queue mode:** `mode: addToQueue` (draft = queue slot + approval).
- **Image assets:** `assets[].image.url` (public URL); `altText` in `image.metadata.altText`.
- **LinkedIn:** Supports link preview via `metadata.linkedin.linkAttachment`.
- **Facebook:** Supports link preview via `metadata.facebook.linkAttachment`.

## Content Pillars

| Pillar | Description | Channels | Frequency |
|--------|-------------|----------|-----------|
| **Product education** | How-to, feature spotlights, FAQ | LinkedIn, Facebook, Blog | 2–3×/week |
| **Engineering transparency** | Architecture decisions, deterministic-first AI, container consolidation | LinkedIn, Twitter/X, Blog | 1–2×/week |
| **Self-host advocacy** | Docker, MIT license, data ownership, VPS guides | LinkedIn, Facebook, Reddit, Blog | 1×/week |
| **Customer stories** | User garages, fuel savings, rego wins | LinkedIn, Facebook, Instagram | 1×/week |
| **Changelog / releases** | Version announcements, bug fixes | Discord #changelog, LinkedIn | Per release |
| **Community Garage teaser** | "Coming soon" federation, waitlist | LinkedIn, Facebook, Discord #updates | Monthly until launch |

## Approval Gates (MANDATORY)

Per company policy (AGENTS.md):

1. **Every asset is draft only** until the human CMO approves in Discord `#marketing` via the n8n Reporter embed.
2. **Full publishable content must be inline in the approval embed:** headline, body text, captions, hashtags, CTAs, target channel + timing.
3. **Human CMO has no Paperclip access** — never point them at an issue link.
4. **No auto-post, no auto-schedule.** Only schedule/publish after approval.
5. **Record approval on the issue** and report back what shipped.

## Content Creation Workflow

```
1. Social Media Manager drafts copy + art direction      → Outline "Social Queue" doc
2. Generate image (deterministic card or AI fallback)     → AI gateway /v1/social-image
3. Host PNG at public URL                                 → MinIO public / GitHub raw
4. Create draft post in Buffer                            → Buffer MCP create_post (saveToDraft=true)
5. Post approval embed to Discord #marketing              → n8n Reporter
6. Human CMO approves (👍 reaction or reply "approved")   → Discord
7. CMO agent switches Buffer post to scheduled/published  → Buffer MCP edit_post
8. Report shipped to Discord #updates / #changelog        → n8n Reporter
```

## Image Generation

See [Social Image Generation](./social-image-generation.md) for the deterministic-first pipeline (Pillow card generator + Pollinations AI fallback). Module: `ai/app/modules/social_image.py` → `POST /v1/social-image`.

## n8n Automation

- **WF-4 (Social Queue):** Reads Outline "Social Queue" doc → generates images → posts to Buffer. **Blocked:** n8n has no Buffer credential/node installed. Current path is agent-driven (CMO agent uses Buffer MCP tools).
- **Lead capture:** `lead.js` on website → n8n webhook → Discord `#support` thread + Outline log.
- **Weekly digest:** n8n cron (Mondays) → compiles changelog + metrics → Discord `#roadmap` embed.

## Metrics & Reporting

- **Buffer analytics:** Per-post (reactions, comments, impressions) + aggregated (date range, channel filter) via `get_aggregated_post_metrics`.
- **Weekly digest** → Discord `#roadmap`: top posts, engagement rate, follower delta.
- **Monthly review** → Discord `#updates`: funnel (impressions → clicks → demo signups → hosted activations).

## Crisis / Incident Comms

- Deployment team owns triage (Discord `#incidents`).
- CMO reports **customer-facing impact only** in `#incidents` + `#support`.
- No speculative posts. Approved holding statement template in Outline "Incident Comms".

## Related Docs

- [Social Image Generation](./social-image-generation.md) — image pipeline
- [Content Calendar](./content-calendar.md) — scheduled campaigns
- [Growth Metrics](./growth-metrics.md) — KPIs, funnel, Buffer analytics
- [Website Documentation](./website.md) — site pages, lead capture

Source: Buffer MCP verified channels (AUT-163), Phase 1 content calendar (AUT-3972), AGENTS.md approval policy.