# Changelog (Engineering)

How the AutoBrain changelog works, who maintains it, and how it reaches every
surface. This is the *process* document; the actual entries live in
`CHANGELOG.md` at the repo root.

## One shared changelog

`CHANGELOG.md` is the **single changelog for both the hosted (web) app and the
mobile app**. There is no separate mobile changelog. Format follows
[Keep a Changelog](https://keepachangelog.com/); the current release is always
the top section.

## Rules

- **Every user-facing change adds an entry** under `[Unreleased]` in the *same
  change* that ships it — frontend-only changes count too (see `CONTRIBUTING.md`
  for the dual-frontend parity + changelog rules).
- The CI **changelog gate** (`.github/workflows/dockerhub-publish.yml`) fails a
  `main` push that changes `backend/`, `ai/`, `frontend/`, `docker/` or the
  compose files without a matching `CHANGELOG.md` change.
- `scripts/check-release.sh` fails a release if `[Unreleased]` is still
  non-empty, or if the backend `APP_VERSION` doesn't match the top changelog
  version.
- Version numbers are a single semver `x.y.z` moved everywhere by
  `scripts/bump-version.sh <x.y.z> [--mobile]`, which promotes `[Unreleased]`
  to a dated `[V]` section (see `docs/versioning.md`).

## Distribution

| Surface | How it gets the changelog |
|---------|---------------------------|
| Repo | `CHANGELOG.md` (this repo) |
| Marketing site | `sync-changelog` job in `dockerhub-publish.yml` copies `CHANGELOG.md` into `autobrainservice-website`; the site renders `changelog.html` |
| Mobile app + releases | `sync-mobile.yml` syncs `CHANGELOG.md` into `autobrain-mobile`; `release-mobile.yml` publishes the top entry as the GitHub Release body |
| Discord `#changelog` (public) | n8n Discord Reporter embed posted by the release pipelines (hosted releases and mobile releases) |
| Discord `#updates` (staff) | short staff summary embed on each release |

## Writing style

Keep entries concrete and user-visible: what the user can now do, or what was
broken and is now fixed. Attribute large work to its ticket (e.g. `AUT-115`).
Sensitive details (sample plates, internal IPs/hostnames, hosting specifics)
never appear in changelog entries.

> Mirror of the Outline doc *Engineering > Changelog*. Outline is the source of
> truth; keep this file in sync when the process changes.
