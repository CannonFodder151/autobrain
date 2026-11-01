# GitHub-based dev pipeline (AUT-137)

Owner: DevOps Engineer (infra). CTO owns promotion decisions + Discord content.
Mobile Release Engineer owns mobile parity.

## Repos (all changes land here, never local-only)

- Web/backend monorepo: https://github.com/CannonFodder151/autobrain
- Mobile app: https://github.com/CannonFodder151/autobrain-mobile
- Federation hub: https://github.com/CannonFodder151/autobrain-federation-hub (private)

All changes: feature branch -> PR -> merge to `main`. No local-only work.

## Tiers

| Tier | Host | Compose | DB |
|---|---|---|---|
| demo | demo.autobrainservice.app | docker-compose.demo.yml | demo Postgres |
| Default (staging) | default.autobrainservice.app | docker-compose.default.yml | default Postgres |
| hosted | hosted.autobrainservice.app | docker-compose.hosted.yml | hosted Postgres |

Promotion order: demo -> Default -> hosted. Enforced by `scripts/upgrade-instances.sh`,
which health-gates every tier and refuses to promote on an unhealthy tier.
Nothing reaches hosted without passing the prior tier.

## Env config

Per-tier env injected at runtime via Portainer stack env + `.env.example`. No
hardcoded values in code; secrets via Paperclip/GitHub secrets. See
`docs/Deployment-and-Infrastructure/deployment-guide.md`.

## Testing gate

- `ci-tests.yml` runs on every PR (backend paths): health_demo gate + full
  pytest + collect-only + alembic migration chain. Fails block merge + notify
  Discord `#updates`.
- `workflow-yaml` job validates all workflow YAML parses.
- `release-scripts`, `compose-sync-script`, `base-image-pins` stdlib self-checks.
- Smoke per tier via `/health` (upgrade script polls up to 600s).

## Discord notifications (via n8n `https://n8n.nathanmartina.com/webhook/discord-report`)

- PR created: `pr-created-notify.yml` -> `#updates`
- Tests failed: `ci-tests.yml` `Notify Discord on failure` -> `#updates`
- Deployed to demo / promoted to Default / promoted to hosted:
  `deploy-instances.yml` `Report status to Discord` -> `#status`
- Rollback: manual report via same webhook.

## Rollback plan per tier

- Demo: re-run `deploy-instances.yml` with prior image tag or Portainer rollback.
  Health-gate before promoting.
- Default: same; DB migrations are forward-only — restore from pre-deploy
  backup if a migration breaks.
- Hosted: same + 03:00-04:00 AEST window. Pre-deploy DB snapshot mandatory.
  Rollback = redeploy prior image + restore snapshot if schema changed.

## Mobile parity

- `sync-mobile.yml` mirrors `frontend/lib` + assets + `CHANGELOG.md` into
  `autobrain-mobile` on push to `main`.
- Flutter analyze gate before commit.
- Mobile release follows the same demo -> Default -> hosted via `release-mobile.yml`.
- Track parity via the checklist in `docs/Engineering/parity-checklist-template.md`.
