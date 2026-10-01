This document is the consolidation landing page for the weekly review cadence.

**The canonical weekly review template, process, and reviews index live at:** [Weekly Reviews — Template, Process & Index](./weekly-reviews-template-process-index.md)

**Actual review documents (one per period) live in the** `**weekly review**` **Outline collection:**

| Period | Doc |
|--------|-----|
| 2026-W39 (Sep 21–27) | [2026-W39 Weekly Review](/doc/2026-w39-weekly-review-zQ8T6YX5m5) |
| 2026-W38 (Sep 14–20) | [2026-W38 Weekly Review](/doc/2026-w38-weekly-review-6skw5L4rS7) |

**Earlier reviews (W32–W34) live in the AutoBrain collection:**

| Period | Doc |
|--------|-----|
| 2026-W34 (Aug 17–23) | [2026-W34 Weekly Review](/doc/2026-w34-weekly-review-WpC9wvwjkU) |
| 2026-W33 (Aug 10–16) | [2026-W33 Weekly Review](/doc/2026-w33-weekly-review-528VvzsAPH) |
| 2026-W32 (Aug 3–9)   | [2026-W32 Weekly Review](/doc/2026-w32-weekly-review-NwOgLqjzBQ) |

## Why this page exists

This page previously held a single weekly review. It has been consolidated into the template/index document above, so that:

* the **template and process** are in one place (never duplicated across reviews),
* the **reviews index** (period → doc → headline numbers) is in one place,
* each **actual review** stays a standalone document in the `weekly review` Outline collection, named by period.

## Cadence

Every Monday 08:00 UTC (routine `0 8 * * 1`). Each run creates a review issue assigned to the BDM; the review is completed in the normal heartbeat flow.

## Output bar

A weekly review is not done until **both** of these exist:

1. A markdown doc in Outline under `weekly review`, named by period (e.g. `2026-W33 Weekly Review`).
2. A Discord embed posted to `bdm-review` via the n8n reporter, carrying the rating, the headline numbers, and a link to the Outline doc.

## Repo mirror note

> This file mirrors the Outline doc *Business Reviews > Weekly Review (Consolidation)*. Outline is the source of truth; keep this file in sync when the process changes.
