# Versioning Strategy

## Versioning

- API: semantic versioning in the URL (`/api/v1`). New breaking versions add
  `/api/v2` while v1 stays supported during a deprecation window.
- App: `major.minor.patch+build` from `pubspec.yaml` and CI build number.
- Docker images: tagged `latest` per env plus immutable `prod` tags on release.

## Releases

1. Feature branches → PR → CI (lint, test, docker build).
2. Merge to `main` → CD deploys production.
3. `CHANGELOG.md` maintained under "Unreleased", moved to a dated section on
   release.

## Migration rules

- DB changes use Alembic revisions; never hand-edit prod data.
- Backward-compatible API changes are additive only.
- Breaking changes require a version bump and deprecation notice.
