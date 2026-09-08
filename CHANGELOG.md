# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]

### Security
- pin transitive floor versions for three known-CVE packages
  (`idna>=3.15`, `pycryptodome>=3.19.1`, `pygments>=2.20`) across
  `backend/requirements.txt`, `ai/requirements.txt`, and
  `market-data/requirements.txt`. The CVEs in question (PYSEC-2026-215 /
  GHSA-65pc-fj4g-8rjx, PYSEC-2026-1811 / GHSA-j225-cvw7-qrx7,
  PYSEC-2023-117 / GHSA-mrwq-x4v8-fh7p, PYSEC-2026-2987 /
  GHSA-5239-wwwm-4pmq) only affect unpinned transitives; current local
  resolution was already safe (idna 3.18, pycryptodome 3.23, pygments 2.20)
  but the floors make the build reproducible across environments and stop
  image builds from silently picking up a vulnerable version if an
  upstream constraint drifts (AUT-1189).
- bump `pypdf` 6.15.0 -> 6.16.1 (backend + ai) to close three CVEs that
  the new resolved-tree pip-audit gate surfaces: CVE-2026-84309
  (GHSA-jp53-mhqp-8xcg, infinite loop via `TreeObject.insert_child`),
  CVE-2026-84310 (GHSA-23w6-3w8w-8484, long runtime / memory via
  document outlines), CVE-2026-84311 (GHSA-763m-79hh-57f2, long runtime
  / memory via XForm-heavy page text extraction). Pre-existing direct
  pin; needed to land the resolved-tree gate without an immediate
  self-failure (AUT-1189).
- `security-pr-gate.yml` now runs a *resolved-tree* pip-audit pass
  (`pip-audit-resolved`, dispatched to the vm2 runner so it can build a
  throwaway venv) in addition to the existing direct-deps pass. Catches
  transitive CVE drift in PRs, not just on the weekly `security-scan.yml`
  schedule. Direct-deps pass now also covers market-data and dedupes
  cross-tree pin conflicts (backend/ai vs market-data pin different
  pydantic / fastapi majors) so a floor-pin and an exact-pin can coexist
  in one PR gate (AUT-1189).

## [0.3.256] - 2026-09-08

### Added (AUT-1872)
- feat(deploy): upgrade script + hardened hosted compose. `scripts/upgrade-instances.sh` redeploys Portainer stacks tier-by-tier (Demo → Default → Hosted) with explicit image pulls and health gates. `docker-compose.hosted.yml` drops dead `dongle-server` + duplicate `hub`, uses `:-` defaults for `POSTGRES_USER`/`POSTGRES_DB` and `DONGLE_SERVER_URL` so Portainer redeploys survive empty-stack env. PR #375.

## [0.3.255] - 2026-09-08

### Fixed (AUT-2042)
- fix(backend): add error handling to vehicles list endpoint. `GET /vehicles` now wraps `list_user_vehicles` in try/except and returns a clean 500 ("Could not load vehicles") instead of leaking raw DB errors to the client. PR #383.
