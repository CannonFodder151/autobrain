# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.

## [Unreleased]

## [0.3.326] - 2026-11-28

### Added (AUT-1031)
- feat(deps): Configure Dependabot for automated dependency updates across all ecosystems (Docker, Python, npm, pub, GitHub Actions)
- feat(deps): Add auto-merge workflow for Dependabot patch/minor PRs with passing CI

## [0.3.325] - 2026-11-27

### Security (AUT-895)
- Pin floating base image tags to immutable digests to fix trivy scan findings (GH #1050):
  - `docker/runner/Dockerfile`: pin `ghcr.io/actions/actions-runner:latest` to `sha256:6d0b2d80d80f143f77dcb676e50920100bbb547e39e883454d57f45ab8c31300`
  - `docker/frontend/Dockerfile`: pin `ghcr.io/cirruslabs/flutter:3.38.2` to `sha256:f207a06162d1335cf44e4cc8ed997d605ab41dbd88fdc70e528fb32f2c663ef0`

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

