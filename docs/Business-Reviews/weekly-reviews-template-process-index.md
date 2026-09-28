> **Repo mirror:** a sanitised mirror of the Outline doc *Business Reviews > Weekly Reviews — Template, Process & Index*. The actual weekly review documents (one per period, e.g. `2026-W39 Weekly Review`) live in the `weekly review` Outline collection and are **not** mirrored to the public repo — this repo file carries the template, process, and reviews index only. Outline is the complete source of truth.

---

# Weekly Reviews — Template, Process & Index

**Owner:** BDM. **Cadence:** every Monday 08:00 UTC (routine `0 8 * * 1`). **Output bar:** an Outline doc in the `weekly review` folder AND a Discord embed to `bdm-review`. One without the other is not done.

---

## Reviews Index

| Period | Outline Doc | Rating | Issues Raised | Issues Fixed | Fix Rate | Downtime | Traffic/Sales | Social Posts |
|--------|-------------|--------|---------------|--------------|----------|----------|---------------|--------------|
| 2026-W39 (Sep 21–27) | [2026-W39 Weekly Review](/doc/2026-w39-weekly-review-zQ8T6YX5m5) | 5/10   | ~180         | ~95         | ~0.53   | 2 incidents (~2 min planned) | No analytics  | 0            |
| 2026-W38 (Sep 14–20) | [2026-W38 Weekly Review](/doc/2026-w38-weekly-review-6skw5L4rS7) | 4/10   | 500          | 140         | 0.28    | 10 incident issues | No analytics  | 0            |
| 2026-W34 (Aug 17–23) | [2026-W34 Weekly Review](/doc/2026-w34-weekly-review-WpC9wvwjkU) | 7/10   | —            | 942         | 0.92    | ~5h outage | No analytics  | 0            |
| 2026-W33 (Aug 10–16) | [2026-W33 Weekly Review](/doc/2026-w33-weekly-review-528VvzsAPH) | 7/10   | —            | 790         | 0.92    | ~5h outage | No analytics  | 0            |
| 2026-W32 (Aug 3–9)   | [2026-W32 Weekly Review](/doc/2026-w32-weekly-review-NwOgLqjzBQ) | 7/10   | 157          | 116         | 0.74    | 1 outage (email) | No analytics  | 0            |

> **Note:** Weekly review docs for W32–W34 live in the **AutoBrain** collection under "Weekly Review (Consolidation)". W38–W39+ live in the **weekly review** Outline collection. W35–W37 do not exist (review cadence started at W38). This index consolidates both for cross-linking. Add new rows when each review completes. Ratings/numbers marked `—` are not yet populated in the source review doc; pull them from the review doc before publishing the index.

---

## 1. When and why

The weekly business review answers, every Monday: what shipped, what broke, how many issues were raised and fixed, whether the service went down, what website traffic/sales looked like, how social engagement moved, and a rating for the period. It also adds forward-looking value: market growth options and ideas.

* **Period:** the last 7 days (Mon → Sun, UTC). Set explicit `start`/`end` timestamps from the run.
* **Trend over level:** judge the period against the previous week and a rolling baseline, never in isolation.

---

## 2. Data sources (traceability rules)

Every number must trace to a source. "Unverified" is an acceptable value; a guessed number is not.

| Metric | Source | Owner of truth |
|--------|--------|----------------|
| Issues raised / fixed / open | Paperclip `GET /api/companies/{companyId}/issues?createdAfter&createdBefore` and by status | CTO            |
| Downtime / incidents | Paperclip incident-labelled issues + `incidents` Discord history; verify with Deployment | Deployment Lead |
| Website sales + traffic | Live health checks (autobrainservice.app, demo.autobrainservice.app) + any analytics/webhook data reachable | CMO / Deployment |
| Social engagement | Social Media Manager report (posts, reach, likes/comments, follower change) | SMM            |

Known gaps are stated explicitly, not filled: if no analytics integration exists, say so and recommend one.

---

## 3. Rating (X/10)

Weighting: delivered vs committed work · issue fix rate · uptime · traffic/sales direction · engagement trend. One-line rationale required.

* **Velocity vs commitments:** issues fixed vs issues raised; a fix rate below 1.0 means the backlog is growing.
* **Reliability (error budget):** count outages, not just excuses.

---

## 4. Document structure

Name by period (e.g. `2026-W33 Weekly Review`) and save under the `weekly review` Outline folder:

1. Period + rating (X/10) + one-line rationale
2. Issues raised vs fixed (raw numbers, still-open counts)
3. Service downtime (count + total duration if known; else "unverified — check Deployment")
4. Website sales + traffic (availability, sales = orders/conversions only from a real source)
5. Social media engagement (posts, reach, likes, follower delta)
6. What shipped / what broke (top 3–5 bullets)
7. Market growth options and ideas (2–5 concrete, ICE-scored)
8. Data gaps / next actions

---

## 5. Posting

1. Publish the markdown doc to Outline under `weekly review`.
2. Post a Discord embed to `bdm-review` via the n8n reporter (channel `bdm-review`): rating, headline numbers (issues, downtime, traffic/sales, engagement), link to the Outline doc.
3. Comment on the run issue with the summary, link to the doc, key numbers, and mark it `done` with evidence.

---

## 6. Growth ideas (ICE)

For every suggested growth idea: **Impact / Confidence / Effort** (1–10 each). Ideas must be concrete (who, what, rough effort), not vague.

---

## 7. Funnel discipline

Traffic → signup → activation → sale. Identify the weakest stage each week; the review names it.
