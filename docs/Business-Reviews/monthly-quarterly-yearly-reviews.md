# Monthly / Quarterly / Yearly Reviews


> **Repo mirror:** a sanitised mirror of the Outline doc *Business Reviews > Monthly / Quarterly / Yearly Reviews*. The actual monthly/quarterly/yearly review documents live in the `weekly review` Outline collection and are **not** mirrored to the public repo — this repo file carries the cadence, templates, and reviews index only. Outline is the complete source of truth.

**Owner:** BDM. **Cadence:** monthly (1st 09:00 UTC), quarterly (1st of Jan/Apr/Jul/Oct 09:00 UTC), yearly (1 Jan 10:00 UTC). Saved in the `weekly review` Outline folder, named by period (`2026-06 Monthly Review`, `2026-Q2 Quarterly Review`, `2025 Yearly Review`).

> Mirror of this file lives in the repo at `docs/Business-Reviews/monthly-quarterly-yearly-reviews.md`. Outline is the source of truth; update both in the same change.


---

## Purpose

Longer-window business reviews. Same evidence rules as the weekly review, wider lens: trend over level, velocity vs commitments, reliability, funnel discipline, engagement trajectory, market signals.

A monthly review aggregates 4–5 weekly reviews. A quarterly aggregates 3 months. A yearly aggregates 12 months and is the input to the next annual plan. Each wider review **rolls up the constituent weekly ratings** and calls out where the trend broke — the wider reviews exist to catch what weekly granularity misses.


---

## Periods and cadences

| Review | Period | Cron | Start ASAP | Document name |
|--------|--------|------|------------|---------------|
| Monthly | last calendar month | `0 9 1 * *` | one full month from first run | `YYYY-MM Monthly Review` |
| Quarterly | last 3 calendar months | `0 9 1 1,4,7,10 *` | one full quarter from first run | `YYYY-QN Quarterly Review` |
| Yearly | last 12 months | `0 10 1 1 *` | one full year from first run | `YYYY Yearly Review` |

Each run creates a review issue assigned to the BDM; the review is completed in the normal heartbeat flow. **The rule:** start ASAP, then each cadence runs one full period after the last run — a cadence never double-counts a period already covered.

### Quarter boundaries

| Quarter | Months | Review doc |
|---------|--------|------------|
| Q1      | Jan, Feb, Mar | `YYYY-Q1 Quarterly Review` |
| Q2      | Apr, May, Jun | `YYYY-Q2 Quarterly Review` |
| Q3      | Jul, Aug, Sep | `YYYY-Q3 Quarterly Review` |
| Q4      | Oct, Nov, Dec | `YYYY-Q4 Quarterly Review` |


---

## Reviews Index

| Period | Type | Doc | Rating |
|--------|------|-----|--------|
| *(none yet — first monthly runs after the first full month from the ASAP start)* |      |     |        |


---

## Shared 8-section structure

All three cadences use the same 8 sections, with period-wide scope:


1. Period + rating (X/10) + one-line rationale
2. Issues raised vs fixed (raw numbers + still-open counts + per-week trend line)
3. Service downtime / incidents (count + total duration if known + per-week trend)
4. Website sales + traffic
5. Social media engagement
6. What shipped / what broke (top 3–5)
7. Market growth options and ideas (2–5, ICE-scored)
8. Data gaps / next actions

The only cadence-specific difference is **section 2 and 3 get a per-week breakdown table** rather than a single row, because the trend is the point of the wider review.


---

## Rating (X/10)

Weighting: delivered vs committed work · issue fix rate · uptime · traffic/sales direction · engagement trend. Judged against the prior period and a rolling baseline, not in isolation.

For a wider review the rating is **not** the mean of the constituent weekly ratings. It is scored on the aggregated period, and the weekly ratings are cited as evidence. A quarter where four weeks rated 6 and one week rated 2 after a multi-day outage is not a 5 — the outage is the story.

### Rating bands

| Score | Meaning |
|-------|---------|
| 8–10  | Delivering ahead of commitments, fix rate > 1.0, no unplanned downtime, traffic/sales growing |
| 6–7   | Delivering on commitments, fix rate \~1.0, minor incidents, flat-to-growing traffic |
| 4–5   | Mixed — fix rate below 1.0, recurring incidents, or flat traffic. Most weeks here. |
| 1–3   | Not delivering, backlog growing fast, repeated outages, or a major launch missed |


---

## Data sources

Same traceable sources as the weekly review — Paperclip issue queries, Deployment-verified incident facts, live site health checks + any analytics, SMM engagement report. Gaps are named, not filled.

| Metric | Query / source | Owner of truth |
|--------|----------------|----------------|
| Issues raised in period | `GET /api/companies/{companyId}/issues?createdAfter={start}&createdBefore={end}` | CTO            |
| Issues fixed in period | same list filtered `status=done` + `updatedAt` in period | CTO            |
| Incidents / downtime | incident-labelled issues + `incidents` Discord channel; confirm duration with Deployment Lead | Deployment Lead |
| Traffic / sales | analytics if it exists; otherwise state the gap | CMO / Deployment |
| Social engagement | SMM report     | SMM            |

> ponytail: the "fixed in period" number is approximated by `status=done` on issues created in the period. When the API can filter by `updatedAt` between start/end, prefer that — it catches issues raised earlier and fixed this period. Until that filter exists, say "issues created in period that reached done" in the doc, not "issues fixed in period".


---

## Posting


1. Publish markdown to Outline under `weekly review`, named by period.
2. Post Discord embed to `bdm-review` (rating + headline numbers + doc link).
3. Comment on the run issue with summary + link + key numbers; mark `done` with evidence.


---

## Templates

### Monthly review template

```md
# YYYY-MM Monthly Review

**Period:** YYYY-MM-01 00:00 UTC → YYYY-MM-{last day} 23:59 UTC
**Rating:** X/10 — <one-line rationale>
**Roll-up:** constituent weekly reviews: [Wnn](link), [Wnn](link), [Wnn](link), [Wnn](link)

## Issues Raised vs Fixed

| Metric | Month | Prior month | Trend |
|--------|-------|-------------|-------|
| Issues created (raised) | N | N | +/- |
| Issues moved to `done` (fixed) | N | N | +/- |
| Fix rate | N.NN | N.NN | +/- |
| Still open at period end | N | N | +/- |
| Backlog growth | +N | +N | |

**Per-week breakdown:**

| Week | Raised | Fixed | Fix rate | Still open |
|------|--------|-------|----------|------------|
| Wnn | N | N | N.NN | N |
| Wnn | N | N | N.NN | N |
| Wnn | N | N | N.NN | N |
| Wnn | N | N | N.NN | N |

**Fix rate analysis:** <is the backlog growing or draining? what drove the movement — a launch wave, a fix wave, or a new intake source?>

## Service Downtime / Incidents

**Incident issues raised this month:** N
**Total downtime duration:** <known duration, or "unverified — check Deployment Lead">

| Week | Incidents | Total downtime | Worst incident |
|------|-----------|----------------|---------------|
| Wnn | N | N | AUT-XXXX |
| Wnn | N | N | — |
| Wnn | N | N | — |
| Wnn | N | N | — |

**Website availability (spot check at review time):**

* `autobrainservice.app` → 200 OK
* `demo.autobrainservice.app` → 200 OK
* `shop.autobrainservice.app` → 200 OK

## Website Sales + Traffic

| Metric | Month | Prior month | Trend |
|--------|-------|-------------|-------|
| Visitors / sessions | N | N | |
| Signups | N | N | |
| Activations (first AI feature used) | N | N | |
| Paid conversions | N | N | |
| Revenue | $N | $N | |

**Gap:** <if no analytics integration exists, say so plainly and recommend one — do not fill the table with estimates>

**Weakest funnel stage:** traffic → signup → activation → sale. <name the one stage and why>

## Social Media Engagement

| Platform | Posts | Impressions | Likes | Comments | Shares | Follower Δ |
|----------|-------|-------------|-------|----------|--------|------------|
| Facebook | N | N | N | N | N | N |
| LinkedIn | N | N | N | N | N | N |
| X / Twitter | N | N | N | N | N | N |
| Instagram | N | N | N | N | N | N |

**Engagement rate:** N% (interactions / impressions)
**Month-over-month:** +/- N%
**Best-performing post:** <link, and what made it work — hook, format, timing>

## What Shipped (Top 3–5)

1. **<feature>** — `AUT-XXXX` (<date>)
2. **<feature>** — `AUT-XXXX` (<date>)
3. **<feature>** — `AUT-XXXX` (<date>)

## What Broke / Blocked (Top 3–5)

1. **<thing>** — `AUT-XXXX` (<impact>)
2. **<thing>** — `AUT-XXXX` (<impact>)

## Market Growth Options & Ideas (ICE Prioritised)

| Idea | Impact | Confidence | Effort | Score | Owner | Next Step |
|------|--------|------------|--------|-------|-------|-----------|
| **<idea>** | N | N | N | **N** | @agent | <action> |

## Data Gaps / Next Actions

| Gap | Owner | Action | Due |
|-----|-------|--------|-----|
| <gap> | [@Agent] | <action> | <date> |
```

### Quarterly review template

```md
# YYYY-QN Quarterly Review

**Period:** YYYY-MM-01 00:00 UTC → YYYY-MM-30 23:59 UTC (Q N, three months)
**Rating:** X/10 — <one-line rationale>
**Roll-up:** 12–13 constituent weekly reviews; 3 monthly reviews linked below
**Prior quarter:** [YYYY-Q(N-1)](link) — rating X/10

## Quarter at a Glance

| Metric | Q N | Q N-1 | Change |
|--------|-----|-------|--------|
| Issues raised | N | N | |
| Issues fixed | N | N | |
| Fix rate | N.NN | N.NN | |
| Incidents | N | N | |
| Total downtime | N min | N min | |
| Paid subscribers | N | N | |
| Monthly recurring revenue | $N | $N | |
| Social follower Δ | N | N | |

## Monthly Trend (the point of a quarterly review)

| Month | Raised | Fixed | Fix rate | Incidents | Traffic | Posts | Follower Δ |
|-------|--------|-------|----------|-----------|---------|-------|------------|
| Month 1 | N | N | N.NN | N | N | N | N |
| Month 2 | N | N | N.NN | N | N | N | N |
| Month 3 | N | N | N.NN | N | N | N | N |

**Where the trend broke:** <name the month or week where the line changed and why — this paragraph is the reason the quarterly exists>

## Issues Raised vs Fixed

<monthly tables for each of the 3 months, then the quarter total and the backlog growth>

## Service Downtime / Incidents

<quarter totals, worst-incident table, and the standing error-budget read: planned maintenance vs unplanned outage minutes>

## Website Sales + Traffic

<quarter totals + monthly trend + funnel stage analysis + weakest stage>

## Social Media Engagement

<quarter totals per platform + monthly trend + best post of the quarter>

## What Shipped (Top 3–5 for the quarter)

1. **<major launch or capability>** — `AUT-XXXX`
2. **<major launch or capability>** — `AUT-XXXX`
3. **<major launch or capability>** — `AUT-XXXX`

## What Broke / Blocked (Top 3–5 for the quarter)

1. **<recurring failure class>** — `AUT-XXXX` (<how many times this hit us in the quarter>)
2. **<recurring failure class>** — `AUT-XXXX`

## Market Growth Options & Ideas (ICE Prioritised)

| Idea | Impact | Confidence | Effort | Score | Owner | Next Step |
|------|--------|------------|--------|-------|-------|-----------|
| **<idea>** | N | N | N | **N** | @agent | <action> |

**Carried forward from last quarter:** <list any idea that was scored high last quarter and still has no owner or no movement — carrying an unscored idea is the failure mode this section exists to prevent>

## Quarter Priorities for Next Quarter

| Priority | Why (evidence from this quarter) | Owner | Measurable target |
|----------|-------------------------------|-------|-------------------|
| 1. <priority> | <evidence> | @agent | <target> |

## Data Gaps / Next Actions

| Gap | Owner | Action | Due |
|-----|-------|--------|-----|
| <gap> | [@Agent] | <action> | <date> |
```

### Yearly review template

```md
# YYYY Yearly Review

**Period:** YYYY-01-01 00:00 UTC → YYYY-12-31 23:59 UTC
**Rating:** X/10 — <one-line rationale>
**Roll-up:** ~52 weekly reviews, 12 monthly reviews, 4 quarterly reviews
**Prior year:** YYYY-1 — rating X/10

## The Year in One Paragraph

<three to five sentences: what the business actually did this year, what changed, what it earned, and whether it is better or worse than last year. No hedging. This is the paragraph a board member reads first.>

## Year at a Glance

| Metric | YYYY | YYYY-1 | Change |
|--------|------|--------|--------|
| Issues raised | N | N | |
| Issues fixed | N | N | |
| Fix rate | N.NN | N.NN | |
| Incidents | N | N | |
| Total unplanned downtime | N min | N min | |
| Availability | N.NN% | N.NN% | |
| Website visitors | N | N | |
| Signups | N | N | |
| Paid subscribers (year end) | N | N | |
| Monthly recurring revenue (year end) | $N | $N | |
| Social posts | N | N | |
| Social followers (year end) | N | N | |

## Quarterly Trend

| Quarter | Rating | Fix rate | Incidents | Downtime | MRR | Follower Δ |
|---------|--------|----------|-----------|----------|-----|------------|
| Q1 | N/10 | N.NN | N | N min | $N | N |
| Q2 | N/10 | N.NN | N | N min | $N | N |
| Q3 | N/10 | N.NN | N | N min | $N | N |
| Q4 | N/10 | N.NN | N | N min | $N | N |

**Where the year turned:** <name the month or quarter where the trajectory changed and what caused it>

## Issues Raised vs Fixed

<quarterly roll-up tables; year totals; the backlog growth curve. If the fix rate ended the year above 1.0, that is the headline. If it ended below, the backlog is the headline.>

## Service Downtime / Incidents

<year totals; the ten worst incidents of the year with duration and customer impact; planned vs unplanned split; availability percentage>

## Website Sales + Traffic

<year totals; monthly revenue trend; funnel conversion rates year-over-year; the weakest funnel stage; the cohort that converts best>

## Social Media Engagement

<year totals per platform; best and worst quarters; the top 3 posts of the year and what they had in common; follower growth curve>

## What Shipped (Top 3–5 for the year)

1. **<capability that changed the product>** — `AUT-XXXX`
2. **<capability>** — `AUT-XXXX`
3. **<capability>** — `AUT-XXXX`

## What Broke / Blocked (Top 3–5 for the year)

1. **<recurring failure class that cost the most>** — <how many times, total cost>
2. **<recurring failure class>** — <how many times, total cost>

## Market Growth Options & Ideas (ICE Prioritised)

| Idea | Impact | Confidence | Effort | Score | Owner | Next Step |
|------|--------|------------|--------|-------|-------|-----------|
| **<idea>** | N | N | N | **N** | @agent | <action> |

**Carried forward from last year and still not done:** <this is the most important table in the document. A high-scoring idea with no movement for four quarters is a planning failure, not a market failure.>

## Next Year Plan

| Priority | Why (evidence from this year) | Owner | Measurable target |
|----------|-------------------------------|-------|-------------------|
| 1. <priority> | <evidence> | @agent | <target> |
| 2. <priority> | <evidence> | @agent | <target> |
| 3. <priority> | <evidence> | @agent | <target> |

## Data Gaps / Next Actions

| Gap | Owner | Action | Due |
|-----|-------|--------|-----|
| <gap> | [@Agent] | <action> | <date> |
```


---

## Escalation / handoff

* Bugs / engineering → route via Paperclip issues to CTO org (BDM does not fix or deploy).
* Marketing campaigns / public posts → CMO / Social Media Manager.
* Spend / budget → CFO.
* Board sign-off → `approvals` Discord channel via n8n reporter + Paperclip issue.
* Growth ideas need CMO sign-off; use ICE (Impact / Confidence / Effort) for every suggestion.