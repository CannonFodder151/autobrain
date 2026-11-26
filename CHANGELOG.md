# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]

## [0.3.324] - 2026-11-26

### Added (AUT-6415)
- feat(docker): merge dongle-server + backup GUI into backend container (AUT-6415)

### Fixed (AUT-4821)
- fix(backup): `run_backup_offsite` now raises `RuntimeError` when `_push_offsite` returns `False`, so Celery reports FAIL instead of SUCCESS on a silent no-op; regression test added in `test_backup_offsite.py::test_push_failure_raises` (AUT-4821)

### Added (AUT-3857)
- feat(health-score): Vehicle Health Score deterministic-first module with rule-based fallback + 9Router enrichment; `GET /vehicles/{id}/health-score` endpoint (AUT-3857)

### Added (AUT-322)
- chore(mobile): mobile release v0.3.311+253 — `release-mobile.yml` `promote_to_production` flag now promotes the closed-testing release to Google Play production (staged rollout 10% → 50% → 100%); shared changelog entry for mobile GitHub Release (AUT-322)

## [0.3.323] - 2026-11-22

### Added (AUT-670)
- PR/CI Watchdog: failed GitHub Actions workflows now auto-create GitHub issues with failure logs, postmortem template, MTTR labels, and Paperclip execution issues to wake the assigned agent (.github/workflows/pr-ci-watchdog.yml, scripts/pr-ci-watchdog.sh, scripts/pr-ci-watchdog-notify.sh)

## [0.3.322] - 2026-11-22

### Fixed (AUT-504)
- fix(frontend): add "Petrol Prices" tile to the home screen feature grid so the petrol price map (AUT-1813) is discoverable, matching the marketing claim (PR #1145)

## [0.3.321] - 2026-11-19

### Added (AUT-594)
- demo/default compose digest pinning now tracked by update-compose-pins.py
- demo (EP2, stack 138) and default (EP2, stack 137) sync to Portainer via
  sync-compose-to-portainer.py in dockerhub-publish.yml merge-triggered workflow
- demo frontend registry drift resolved: switched from ghcr.io to Docker Hub
  cannonfodder151/autobrain-frontend:demo@sha256:db91b2b7...

### Fixed (AUT-594)
- demo/frontend registry drift (ghcr.io :hosted was never published, only
  Docker Hub :demo exists)
- update-compose-pins.py now supports Docker Hub (prefixless) registry and
  tier-specific frontend tags (:demo/:default)

