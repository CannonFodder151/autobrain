# Marketing & Website

Website, demo, social, growth.

## Document List

| Document | Purpose |
|----------|---------|
| [website.md](./website.md) | Website documentation (autobrainservice.app) |
| [demo-environment.md](./demo-environment.md) | Demo environment ops (demo.autobrainservice.app) |
| [social.md](./social.md) | Social media strategy & Buffer workflow |
| [social-image-generation.md](./social-image-generation.md) | Social image generation pipeline (deterministic-first) |
| [per-post-og-image-workflow.md](./per-post-og-image-workflow.md) | Per-post OG image workflow & author bio schema (AUT-3115) |
| [community-garage.md](./community-garage.md) | Community Garage feature docs (federated social) |
| [content-calendar.md](./content-calendar.md) | Marketing content calendar & approval gates |
| [growth-metrics.md](./growth-metrics.md) | Growth KPIs, funnel, Buffer analytics, reporting |

## Section Map

```
Marketing & Website (this folder)
├── website.md                    ← NEW
├── demo-environment.md           ← NEW
├── social.md                     ← REPLACED (was Community Garage API)
├── social-image-generation.md    ← REFRESHED (AUT-163 verified)
├── per-post-og-image-workflow.md ← EXISTING (AUT-3115)
├── community-garage.md           ← EXISTING (AUT-294, board-approved)
├── content-calendar.md           ← NEW (from AUT-3972)
└── growth-metrics.md             ← NEW
```

## Sync Policy

- **Source of truth:** Outline (AutoBrain collection).
- **Mirror:** This `docs/Marketing-and-Website/` directory.
- **Update rule:** Every Outline change → same-PR repo mirror update. Every repo change → Outline update (CMO agent).
- **Phase 1 refresh:** All docs updated in branch `feat/AUT-4050-docs-refresh` (this PR).
- **Outline doc IDs:**
  - Marketing & Website parent: `/doc/FImUvTds57`
  - Social media strategy: `/doc/cSv134C6XL`
  - Social image generation: `/doc/PvXJk9RxL1`
  - Community Garage: `/doc/Uuu2hCFXFY`

## Related Repos

- `CannonFodder151/autobrainservice-website` — marketing site (private)
- `CannonFodder151/autobrain` — main monorepo (this docs mirror)
- `autobrainservice.app` — production website
- `demo.autobrainservice.app` — demo environment