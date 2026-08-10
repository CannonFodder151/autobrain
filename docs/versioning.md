# Versioning Strategy

## One version, one changelog

AutoBrain uses **a single version number** (semver `x.y.z`) for every release.
The `CHANGELOG.md` is the reference; `scripts/bump-version.sh <x.y.z>` is the
one tool that moves the number everywhere in one shot:

- `backend/app/core/config.py` → `APP_VERSION` (source of truth at runtime;
  shown in admin settings, returned by `GET /health` and public
  `GET /api/v1/auth/config` → `app_version`).
- `backend/app/main.py` — reads `settings.APP_VERSION` (never hardcoded).
- `ai/app/main.py` — reads `APP_VERSION` env (default bumped by the script).
- `frontend/pubspec.yaml` — `x.y.z+<build>` (build number increments).
- `autobrain-mobile/pubspec.yaml` — bumped in the same release with `--mobile`
  so the store version always matches the server release.
- `CHANGELOG.md` — promotes `[Unreleased]` to a dated `[V]` section.
- Marketing site — `CHANGELOG.md` is synced to
  `autobrainservice-website` and `changelog.html` regenerated automatically by
  the Docker Hub publish workflow on every `main` push (no manual step).

Anything that reports a version (FastAPI `version=`, `/health`, admin banner,
public config) must come from `APP_VERSION` — never a hardcoded literal.

## Versioning details

- API: semantic versioning in the URL (`/api/v1`). New breaking versions add
  `/api/v2` while v1 stays supported during a deprecation window.
- Docker images: tagged `latest` per env plus immutable `prod`/`hosted` tags on release.
- Mobile update prompt: on login the app compares its installed version with
  `GET /api/v1/auth/config` → `app_version` and prompts to update when behind.

## Releases

1. Feature branches → PR → review. Add changelog entries under `[Unreleased]`.
2. Merge to `main` — `scripts/auto-bump.sh` (AUT-240) automatically cuts the
   next patch release (bumps `APP_VERSION`, `pubspec.yaml`, promotes
   `[Unreleased]` to a dated section, commits) whenever unreleased changes
   exist, then CI publishes images. No manual bump step needed for patch
   releases. Cut minor/major explicitly with
   `./scripts/bump-version.sh <x.y.z> [--mobile]` when warranted.
3. `scripts/check-release.sh` gates deploys on the changelog/`APP_VERSION`
   matching (run by `deploy.sh` / `publish-images.sh`).
4. `changelog.html` on the marketing site regenerates automatically from
   `CHANGELOG.md` on the `main` push (AUT-119/AUT-168).

A CI changelog gate on `main` (AUT-168) fails the Docker Hub publish if any
`backend/`, `ai/`, `frontend/`, `docker/` or compose file changes without a
matching `CHANGELOG.md` entry — so the changelog and the website always track
shipped code.

## Migration rules

- DB changes use Alembic revisions; never hand-edit prod data.
- Backward-compatible API changes are additive only.
- Breaking changes require a version bump and deprecation notice.
