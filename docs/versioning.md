# Versioning Strategy

## Versioning

- API: semantic versioning in the URL (`/api/v1`). New breaking versions add
  `/api/v2` while v1 stays supported during a deprecation window.
- Backend app: `APP_VERSION` in `.env` (shown in admin settings, checked against GitHub latest release).
- Web frontend: `pubspec.yaml` version — kept in sync with `APP_VERSION` via `scripts/bump-version.sh`.
- Mobile app: separate `pubspec.yaml` in `autobrain-mobile` repo (independent versioning).
- Docker images: tagged `latest` per env plus immutable `prod`/`hosted` tags on release.

## Releases

1. Feature branches → PR → review.
2. Merge to `main` → build + deploy via `scripts/deploy.sh`.
3. `CHANGELOG.md` maintained under "Unreleased", moved to a dated section on
   release.

## Migration rules

- DB changes use Alembic revisions; never hand-edit prod data.
- Backward-compatible API changes are additive only.
- Breaking changes require a version bump and deprecation notice.
