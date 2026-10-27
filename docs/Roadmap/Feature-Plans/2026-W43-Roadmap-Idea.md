# Roadmap Idea — 2026-W43

## Idea: Shareable public build-sheet link (Community Garage seed)

**Who:** AutoBrain owners with a documented modification build (mods tracker + photos already captured in-app).

**What:** Add a "Share build" action on a vehicle's modifications tab that mints a read-only public URL (e.g. `autobrainservice.app/b/<slug>`) rendering the build sheet — vehicle, mod list with cost + impact summaries, and gallery photos. No login required to view; owner controls visibility (public/unlisted/private) and can revoke. This reuses the existing modifications tracker + build-sheet export data; only a public render route + slug + visibility flag are new.

**Why now:** Community Garage is listed as deferred/future in ROADMAP.md, but a shareable build sheet is the smallest shippable slice that (a) validates demand for public sharing before building full garage/leaderboards, (b) creates an acquisition loop (every shared link is a product demo), and (c) monetizes via the existing hosted tier (unlisted/private + custom slug as Pro).

**Rough effort:** S — backend: visibility flag + slug + public GET endpoint + OG meta; frontend: share button + public route; ~1 sprint. No new infra.

**ICE:** Impact 8 / Confidence 7 / Effort 3 (low) → prioritize.

**Data gaps:** none — grounded in shipped mods tracker + build-sheet export.
