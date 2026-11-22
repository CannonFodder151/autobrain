# Mobile App Split — `autobrain-mobile`

AutoBrain's mobile app (iOS/Android) lives in its own private repo:
[`CannonFodder151/autobrain-mobile`](https://github.com/CannonFodder151/autobrain-mobile).

The main `autobrain` repo keeps the **Flutter web** build only (served by the frontend Docker image via nginx).

---

## Why Separate Repos?

- **Independent release cadence.** Mobile builds (TestFlight, Play Store) don't block web deployments.
- **Build tooling isolation.** Mobile CI needs Xcode Cloud, Android SDK, and signing — all outside the web Docker pipeline.
- **Code sharing via lineage.** Both repos share the same Flutter codebase lineage; sync is done via CI when the web repo's Flutter code changes.

---

## Repositories

| Repo | Scope | CI | Build |
|------|-------|-----|-------|
| `CannonFodder151/autobrain` | Backend, web frontend, platform | GitHub Actions (Docker, pytest, security) | Docker images (backend, frontend) |
| `CannonFodder151/autobrain-mobile` | iOS/Android Flutter app | Xcode Cloud, Play Console | iOS TestFlight, Android Play Store |

---

## Version Sync

Both repos share the same release version (e.g., `0.3.270`). On release:

1. `scripts/bump-version.sh` in `autobrain` bumps `pubspec.yaml` (web) and calls `scripts/bump-version.sh --mobile` to update `autobrain-mobile`'s `pubspec.yaml`.
2. CI builds web Docker images and triggers mobile CI.
3. Store versions match the server release.

On login, the mobile app compares its installed version with the server's `GET /api/v1/auth/config` → `app_version` and prompts the user to update when behind.

---

## CI/CD Pipeline

### Web (autobrain repo)
- `.github/workflows/ci-tests.yml` — pytest, ruff, import checks
- `.github/workflows/build-hosted.yml` — Docker image builds (amd64 + arm64)
- `.github/workflows/security-scan.yml` — Trivy, pip-audit, gitleaks

### Mobile (autobrain-mobile repo)
- **iOS**: Xcode Cloud builds TestFlight; config in `azure-pipelines` or Xcode Cloud project
- **Android**: Play Console CI; versionCode managed via `scripts/bump-version.sh --mobile`

---

## Directory Structure

```
autobrain-mobile/
├── ios/                  # iOS project (Xcode)
├── android/              # Android project (Gradle)
├── lib/                  # Flutter app code
├── pubspec.yaml          # Flutter dependencies + version
├── fastlane/             # Fastlane for store uploads
└── scripts/
    └── build-and-upload.sh
```

---

## Onboarding a New Mobile Release

1. Bump version in `autobrain` repo: `scripts/bump-version.sh --mobile`
2. Commit both repos (version bump must match)
3. Trigger CI in `autobrain-mobile`
4. iOS: TestFlight review → App Store
5. Android: Play Console internal testing → closed testing → production

---

## See Also

- `docs/Engineering/mobile-release.md` — mobile release guide
- `scripts/bump-version.sh` — version bump script