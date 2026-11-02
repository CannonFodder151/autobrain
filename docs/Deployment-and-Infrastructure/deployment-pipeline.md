# Deployment Pipeline (Demo → Default → Hosted)

This document describes the full AutoBrain deployment pipeline: branch strategy, PR workflow, tier promotion, testing gates, rollback. It is kept in sync with `.github/workflows/*` and references [AUT-137](../../docs/Testing-and-QA/qa-run-logs.md#L67).

## Branch strategy

- **Default branch:** `main`. All production-ready code lands here.
- **Feature branches:** Branch from `main` (`git checkout -b feat/<name>` or `fix/<name>` or `docs/<name>`). Follow [Conventional Commits](https://www.conventionalcommits.org/).
- **No direct commits to `main`.** All changes go through PRs (see below).
- **Mobile sync:** Changes to shared Flutter lineage (`frontend/lib`, `frontend/assets`, `frontend/pubspec.yaml`) or `CHANGELOG.md`/version scripts trigger `sync-mobile.yml` to sync to `CannonFodder151/autobrain-mobile` and dispatch the mobile release pipeline.

## PR workflow

1. **Create branch** from `main`.
2. **Implement** changes; keep PRs small and focused.
3. **Changelog:** Update `CHANGELOG.md` under `[Unreleased]` for any user-facing change (backend/ai/frontend/docker-compose affects require changelog on PR per `dockerhub-publish.yml` changelog-gate; merges already graft entries).
4. **Tests/lint:** Run relevant checks locally (see [CONTRIBUTING.md](../../CONTRIBUTING.md)).
5. **Open PR** to `main`. Fill PR description (use template in [PR_BODY.md](../../PR_BODY.md) style).
6. **CI gates:** `ci-tests.yml` (backend pytest), `compose-checks.yml` (compose structural checks), `dockerhub-publish.yml` changelog-gate (on PR), `code-review.yml` (OCR review for source changes), security gates as applicable.
7. **Review:** Code review required before merge.
8. **Merge:** Merge to `main` after approval and green CI. The `auto-bump` job in `dockerhub-publish.yml` may cut a release if `[Unreleased]` has content.
9. **Post-merge:** `dockerhub-publish.yml` publishes multi-arch images to Docker Hub (`:latest`, `:hosted`) and syncs changelog to marketing site. `deploy-instances.yml` (workflow_run) emits a deploy signal to n8n which wakes agents (AUT-1907 Mobile Release Engineer, AUT-1908 Deployment Engineer).

## Tier promotion (mandatory order)

Promotion order is **Demo → Default → Hosted**. Never skip or reorder. See [deployment-guide.md](./deployment-guide.md) for full details.

| Tier | URL | Host/Endpoint | Images | Notes |
|------|-----|---------------|--------|-------|
| Demo | `demo.autobrainservice.app` | Portainer-Host (EP2) stack `autobrain-demo` (id 73) | `cannonfodder151/autobrain-*:latest` (frontend `:demo`) | Public demo, low-risk. Promoted first. |
| Default | `default.autobrainservice.app` | Portainer-Host (EP2) stack `autobrain` (id 68) | Digest-pinned via `docker-compose.default.yml` | Internal/default instance. Promoted after Demo healthy. |
| Hosted | `hosted.autobrainservice.app` | Oracle Cloud VM (EP5) stack `autobrain-hosted` (id 83) | `ghcr.io/cannonfodder151/autobrain-*:hosted` | Production. Promoted last; gated by time window and approvals. |

## Testing gates

All gates must pass before promoting to next tier. A failed gate blocks promotion.

### Pre-deploy / release gates
- [ ] **Code gate:** All features/PRs for release merged to `main` first.
- [ ] **Changelog gate:** `CHANGELOG.md` updated under `[Unreleased]` (enforced on PR for code changes).
- [ ] **CI gates:** `ci-tests.yml`, `compose-checks.yml` green; security/review gates as applicable.
- [ ] **Release checks:** `scripts/check-release.sh` passes (no non-empty `[Unreleased]`, `APP_VERSION` matches top changelog version).
- [ ] **Images published:** `dockerhub-publish.yml` or `build-hosted.yml` completed successfully with correct tags/digests.

### Per-tier gates (Demo/Default/Hosted)
- [ ] **Deploy:** Update stack via Portainer API with `pullImage=true` (preserve env/volumes). Use `scripts/upgrade-instances.sh` or `deploy-instances.yml` workflow.
- [ ] **Startup/health:** `GET /health` returns 200 with expected version/status.
- [ ] **Key flows:** Exercise critical flows for the release (not just version banner).
- [ ] **Feature verification:** Verify new feature actually present on the tier.
- [ ] **Post-deploy smoke:** Run `scripts/post-deploy-smoke.sh <BASE_URL> [EXPECTED_FRONTEND_SHA]` (checks `/health`, `/flutter_bootstrap.js`, `POST /api/v1/auth/signup`, `/ready`). See [deployment-guide.md](./deployment-guide.md#post-deploy-smoke-test-spec) for contract details.
- [ ] **Prune:** Run `scripts/prune-images.sh` on EP2 and EP5 (dangling-only; never `prune -a`). EP2 has personal services — prune cautiously (AUT-4502).
- [ ] **Notify:** Post promotion/update to Discord `#updates` (or `#changelog` for customer-facing) with issue IDs/links.

### Hosted-specific gates
- [ ] **Deploy window:** Hosted deploys only during **03:00–04:00 AEST** (AUT-2409/AUT-5172). Push-triggered redeploys are skipped outside window; use `workflow_dispatch` with override only with board approval.
- [ ] **Image source:** Use `ghcr.io/cannonfodder151/autobrain-*:hosted` built by `build-hosted.yml` (or approved override). Never build locally for hosted.
- [ ] **Window gate enforcement:** `scripts/sync-compose-to-portainer.py` enforces window for EP5; override via `ALLOW_OUT_OF_WINDOW=true` only with approval.
- [ ] **Nightly sync:** `build-hosted.yml` schedule (`cron "0 8 * * *"`) runs nightly sync only (no rebuild) during window.

## Rollback

### Immediate rollback (stack/image)
1. **Identify last known good:** Use previous image tag/digest from deployment log or git history.
2. **Redeploy previous version:** Update Portainer stack to previous images (preserve env/volumes). For Hosted, respect deploy window/approval.
3. **Verify:** Run health checks and smoke tests on rolled-back tier.
4. **Notify:** Post incident/update to Discord `#incidents`/`#updates` with details and actions taken.

### Database rollback
- **Migrations:** Prefer forward-fix. If migration must be rolled back, use Alembic downgrade carefully. See [deployment-guide.md](./deployment-guide.md#migrations).
- **Create-all fallback:** Never rely on `create_all` fallback; if it occurs, treat as broken deploy (see migration warnings).
- **Stamping:** Never use `alembic stamp` to mask missing columns — use `alembic upgrade head` first.

### Full rollback procedure
```bash
# Example: rollback hosted stack to previous compose/images
# 1. Revert docker-compose.hosted.yml to previous version
git checkout <last-good-sha> -- docker-compose.hosted.yml
# 2. Sync to Portainer (respect window/approval)
python3 scripts/sync-compose-to-portainer.py --stack autobrain-hosted --endpoint 5 --file docker-compose.hosted.yml
# 3. Verify
curl -s https://hosted.autobrainservice.app/health
./scripts/post-deploy-smoke.sh https://hosted.autobrainservice.app
```

## Automation references

- **Workflows:** `.github/workflows/dockerhub-publish.yml`, `build-hosted.yml`, `deploy-instances.yml`, `ci-tests.yml`, `compose-checks.yml`, `arm64-runner-keepalive.yml`, `sync-mobile.yml`
- **Scripts:** `scripts/upgrade-instances.sh`, `scripts/sync-compose-to-portainer.py`, `scripts/prune-images.sh`, `scripts/post-deploy-smoke.sh`, `scripts/check-release.sh`, `scripts/bump-version.sh`
- **Related issues:** AUT-137 (embedding backfill), AUT-78 (promotion order), AUT-107 (health gating), AUT-2409/AUT-5172 (hosted window), AUT-1847 (deployment ownership), AUT-1905/AUT-1907/AUT-1908 (agent triggering)
