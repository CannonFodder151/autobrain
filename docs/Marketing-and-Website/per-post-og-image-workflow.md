# Per-Post OG Image & Author Bio Schema (AUT-3115)

Status: **implemented** on branch `feature/per-post-og-image-author-bio`, pending merge.

## Overview

AUT-3115 adds unique OG/Twitter images and a `Person` author schema to all 33 blog posts, replacing the shared generic `og-image.png` and `Organization` author.

### Changes per post

| Before | After |
|--------|-------|
| `og:image` → `https://autobrainservice.app/assets/og-image.png` | `og:image` → `https://autobrainservice.app/assets/blog/og/<slug>.png` |
| `og:image:height` → 400 | `og:image:height` → 630 |
| `article:author` → `https://autobrainservice.app/about.html` | `article:author` → `https://autobrainservice.app/about.html#nathan` |
| JSON-LD `author` → `@type: Organization, name: AutoBrain` | JSON-LD `author` → `@type: Person` (Nathan) |
| JSON-LD `image` → shared `og-image.png` | JSON-LD `image` → per-post OG image |

## OG Image Generation Workflow

### Architecture

```
Blog post slug  →  Section lookup  →  Accent color  →  Render card  →  assets/blog/og/<slug>.png
```

1. **Section extraction** — each blog post has `article:section` meta tag (e.g., `Reliability`, `Maintenance`, `Announcements`)
2. **Accent color mapping** — section maps to a brand accent color (see table below)
3. **Card rendering** — deterministic generator creates 1200×630 PNG with:
   - AutoBrain Blog header
   - Post title text
   - Section-specific accent color bar/styling
   - Brand charcoal/teal/gold palette
4. **Output** — PNG saved to `assets/blog/og/<slug>.png`

### Implementation

- Generated images are **committed to the repo** (not generated at runtime)
- 33 images created in commit `22b4d8c` (AUT-3115)
- Rendered via Pillow (Python), zero external dependencies
- Height updated from 400 to 630 for optimal LinkedIn/Facebook/Twitter rendering

### Section-to-Accent-Color Mapping

| Section | Posts | Accent Color (hex) | Notes |
|---------|-------|-------------------|-------|
| Maintenance | 4 | `#00B7FF` (teal) | Core brand primary |
| Announcements | 4 | `#007BFF` (blue) | Brand accent |
| Features | 3 | `#1A4DFF` (deep blue) | Brand secondary |
| Workshops | 2 | `#D4A53C` (gold) | Brand gold |
| Ownership Costs | 2 | `#0D9488` (teal-700) | |
| Ownership | 2 | `#0D9488` (teal-700) | |
| Integrations | 2 | `#00B7FF` (teal) | |
| Diagnostics | 2 | `#1A4DFF` (deep blue) | |
| Troubleshooting | 1 | `#EF4444` (red) | Alert/warning tone |
| Reliability | 1 | `#00B7FF` (teal) | |
| Product | 1 | `#00B7FF` (teal) | |
| Pricing | 1 | `#D4A53C` (gold) | |
| Guides | 1 | `#007BFF` (blue) | |
| Fuel & Cost Tracking | 1 | `#007BFF` (blue) | |
| Fuel & Cost | 1 | `#007BFF` (blue) | |
| Engineering | 1 | `#6366F1` (indigo) | Technical tone |
| EV & Battery | 1 | `#22C55E` (green) | EV/green theme |
| Data ownership | 1 | `#00B7FF` (teal) | |
| Car clubs | 1 | `#D4A53C` (gold) | |
| AI & Technology | 1 | `#8B5CF6` (violet) | AI/tech theme |

**Total: 33 posts across 19 sections.**

> **Note:** Exact hex values are defined in the OG generation script used during AUT-3115. The table above reflects the mapping used for the 33 generated images.

### File Locations

| Asset | Path |
|-------|------|
| Per-post OG images | `assets/blog/og/<slug>.png` (33 files) |
| Shared fallback OG image | `assets/og-image.png` |
| Blog post HTML | `blog/<slug>.html` |

### Meta Tag Pattern (per post)

```html
<meta property="og:type" content="article">
<meta property="og:site_name" content="AutoBrain">
<meta property="og:title" content="<Post Title>">
<meta property="og:description" content="<Post Description>">
<meta property="og:url" content="https://autobrainservice.app/blog/<slug>.html">
<meta property="og:image" content="https://autobrainservice.app/assets/blog/og/<slug>.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="article:published_time" content="<YYYY-MM-DD>">
<meta property="article:modified_time" content="<YYYY-MM-DD>">
<meta property="article:author" content="https://autobrainservice.app/about.html#nathan">
<meta property="article:section" content="<Section Name>">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="<Post Title>">
<meta name="twitter:description" content="<Post Description>">
<meta name="twitter:image" content="https://autobrainservice.app/assets/blog/og/<slug>.png">
```

## Person Author Bio Schema

### JSON-LD Person Schema (BlogPosting.author)

```json
{
  "@type": "Person",
  "@id": "https://autobrainservice.app/#nathan",
  "name": "Nathan",
  "jobTitle": "IT professional and car enthusiast",
  "url": "https://autobrainservice.app/about.html#nathan",
  "worksFor": {
    "@type": "Organization",
    "name": "AutoBrain",
    "@id": "https://autobrainservice.app/#org"
  },
  "sameAs": "https://www.linkedin.com/in/nathanmartina"
}
```

### Fields

| Field | Value | Purpose |
|-------|-------|---------|
| `@type` | `Person` | Schema.org type |
| `@id` | `https://autobrainservice.app/#nathan` | Unique identifier, matches `article:author` |
| `name` | `Nathan` | Display name |
| `jobTitle` | `IT professional and car enthusiast` | Professional identity |
| `url` | `https://autobrainservice.app/about.html#nathan` | Canonical author page |
| `worksFor` | Organization reference | Links to AutoBrain org |
| `sameAs` | `https://www.linkedin.com/in/nathanmartina` | Social profile for verification |

### About Page Person Schema (Reference)

The About page (`about.html`) also contains a `Person` node in its `@graph`:

```json
{
  "@type": "Person",
  "@id": "https://autobrainservice.app/#nathan",
  "name": "Nathan",
  "jobTitle": "IT professional and software developer",
  "worksFor": { "@id": "https://autobrainservice.app/#org" },
  "knowsAbout": [
    "infrastructure",
    "networking",
    "software development",
    "car maintenance",
    "vehicle restoration"
  ]
}
```

> **Note:** The blog post Person schema includes `url` and `sameAs` fields not present in the About page Person node. The `jobTitle` wording differs slightly (`car enthusiast` vs `software developer`).

## Blog Post Coverage (33 posts)

| Slug | Section | OG Image |
|------|---------|----------|
| ai-that-works-even-when-the-ai-is-down | Reliability | ✅ |
| android-app-full-release | Announcements | ✅ |
| autobrain-app-tour | Guides | ✅ |
| autobrain-for-car-clubs | Car clubs | ✅ |
| autobrain-home-assistant-integration-part-2 | Integrations | ✅ |
| autobrain-home-assistant-integration | Integrations | ✅ |
| best-car-maintenance-app-australia-2026 | Maintenance | ✅ |
| best-car-maintenance-tracker-apps | Maintenance | ✅ |
| best-mechanic-near-me-australia | Workshops | ✅ |
| car-dashboard-warning-lights-australia | Maintenance | ✅ |
| car-fuel-tracker-app-australia | Fuel & Cost Tracking | ✅ |
| car-service-cost-australia | Ownership Costs | ✅ |
| car-wont-start-causes | Troubleshooting | ✅ |
| check-engine-light-australia-obd2-codes-2026 | Diagnostics | ✅ |
| community-garage-ga | Announcements | ✅ |
| digital-car-logbook-australia | Features | ✅ |
| ev-battery-health-australia | EV & Battery | ✅ |
| free-rego-lookup-australia | Features | ✅ |
| fuel-consumption-australia-real-world | Fuel & Cost | ✅ |
| have-you-ever-repair-bill | Features | ✅ |
| issues-blog | Announcements | ✅ |
| mechanic-prices-australia-2026 | Pricing | ✅ |
| obd2-code-reader-app-australia | Diagnostics | ✅ |
| oil-change-cost-australia | Ownership Costs | ✅ |
| ownership-advisor-coming-soon | Ownership | ✅ |
| ownership-advisor-live | Ownership | ✅ |
| predictive-maintenance-car-ai-diagnostics | AI & Technology | ✅ |
| top-5-car-maintenance-trackers | Maintenance | ✅ |
| what-is-autobrain | Product | ✅ |
| what-our-obd2-adapter-will-do | Announcements | ✅ |
| why-a-simpler-stack-is-a-better-stack | Engineering | ✅ |
| workshop-management-software-australian-mechanics | Workshops | ✅ |
| your-data-your-way | Data ownership | ✅ |

## Maintenance

- **Adding new posts:** Generate OG image with section's accent color, commit to `assets/blog/og/`, update meta tags and JSON-LD in blog post HTML.
- **Section color changes:** Update the OG generation script and regenerate affected images.
- **Author updates:** Update Person schema in blog post JSON-LD and About page `@graph` simultaneously.

## Related Docs

- [Social Image Generation (LinkedIn/Facebook)](./social-image-generation.md) — runtime social card generator for posts
- [Marketing & Website Index](./index.md) — section overview