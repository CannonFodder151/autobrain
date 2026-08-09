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
- Marketing site — mirror the new release into
  `autobrainservice-website/changelog.html` (the script reminds you).

Anything that reports a version (FastAPI `version=`, `/health`, admin banner,
public config) must come from `APP_VERSION` — never a hardcoded literal.

## Versioning details

- API: semantic versioning in the URL (`/api/v1`). New breaking versions add
  `/api/v2` while v1 stays supported during a deprecation window.
- Docker images: tagged `latest` per env plus immutable `prod`/`hosted` tags on release.
- Mobile update prompt: on login the app compares its installed version with
  `GET /api/v1/auth/config` → `app_version` and prompts to update when behind.

## Releases

1. Feature branches → PR → review.
2. `./scripts/bump-version.sh <x.y.z> [--mobile]` then commit.
3. Merge to `main` → build + deploy via `scripts/deploy.sh`.
4. Mirror the release into `autobrainservice-website/changelog.html`.

## Migration rules

- DB changes use Alembic revisions; never hand-edit prod data.
- Backward-compatible API changes are additive only.
- Breaking changes require a version bump and deprecation notice.
