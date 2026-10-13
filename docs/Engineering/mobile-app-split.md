# Mobile App Split: autobrain-mobile Repository

## Overview

The Flutter mobile app was originally part of the `autobrain` monorepo under `frontend/`. It has been split into a separate private repository `CannonFodder151/autobrain-mobile` to enable independent CI/CD, release management, and team ownership.

## Repository Structure

### Before Split (Monorepo)
```
autobrain/
├── frontend/           # Flutter web + mobile (shared)
│   ├── lib/
│   ├── test/
│   ├── pubspec.yaml
│   └── ...
├── backend/
├── ai/
└── ...
```

### After Split
```
autobrain/ (monorepo, public)
├── frontend/           # Flutter web only
│   ├── lib/
│   ├── test/
│   ├── pubspec.yaml    # Web dependencies only
│   └── ...
├── backend/
├── ai/
└── ...

autobrain-mobile/ (private repo)
├── lib/                # Mobile-specific code
├── test/
├── pubspec.yaml        # Mobile dependencies (geolocator, flutter_map, etc.)
├── android/
├── ios/
├── .github/workflows/  # Mobile-specific CI
└── ...
```

## Sync Workflow: `sync-mobile.yml`

The `sync-mobile.yml` workflow in the monorepo syncs changes from `autobrain/frontend/` to `autobrain-mobile`:

### Trigger
- Runs on pushes to `main` that touch `frontend/**`
- Manual dispatch via `workflow_dispatch`

### Process
1. **Checkout** both repos (monorepo + mobile via `CannonFodder151/autobrain-mobile` PAT)
2. **Copy** `frontend/lib/` → `autobrain-mobile/lib/`
3. **Copy** `frontend/test/` → `autobrain-mobile/test/` (excluding web-only tests)
4. **Preserve** mobile-specific files:
   - `pubspec.yaml` (mobile deps: `geolocator`, `flutter_map`, `latlong2`, etc.)
   - `android/` and `ios/` directories
   - Platform-specific code in `lib/platform/`
5. **Commit** and push to `autobrain-mobile` main
6. **Trigger** `mobile-release-build.yml` in mobile repo

### Critical Guards (AUT-5205)
- **Part directive check**: Ensures all `.dart` files in `lib/core/models/` are referenced in `models.dart` via `part` directives
- **Import resolution**: Verifies `flutter pub get` resolves all imports in mobile repo
- **Test collection**: Runs `flutter test --dry-run` to catch missing dependencies

### Common Sync Failures
| Failure | Cause | Fix |
|---------|-------|-----|
| `part` directive missing | New model file added to monorepo without `part` in `models.dart` | Add `part 'models/xxx.dart';` to monorepo `frontend/lib/core/models.dart` |
| Unresolved import | Mobile dep not in mobile `pubspec.yaml` | Add dependency to `autobrain-mobile/pubspec.yaml` |
| Test import error | Web-only test synced to mobile | Add to `.sync-ignore` or move to `web/` subdir |

## CI/CD Pipeline

### Monorepo (`autobrain`)
- `sync-mobile.yml` — Syncs frontend → mobile on main pushes
- `compose-checks.yml` — Validates docker-compose files
- `ci-tests.yml` — Backend/AI tests
- `dockerhub-publish.yml` — Builds and publishes backend/AI/frontend images

### Mobile Repo (`autobrain-mobile`)
- `mobile-release-build.yml` — **Release gate** (AUT-2177):
  - Runs `flutter build appbundle --release` on PRs touching `android/**`, `pubspec.yaml`, or synced frontend lineage
  - Must pass before merge (enforced by sync workflow)
  - Validates AGP/Gradle wrapper compatibility
- `flutter-test.yml` — Runs `flutter test` on every PR
- `ios-release.yml` / `android-release.yml` — Manual release workflows

### Release Build Verification (AUT-2177)
**Never merge an AGP/Gradle/Android dependency bump without verifying a release build.**

Required before merge:
1. **Local**: `flutter build appbundle --release` passes, OR
2. **CI**: `mobile-release-build.yml` green on merge commit (≤1 hour old)

PR checklist:
- [ ] `flutter build appbundle --release` passed locally OR `mobile-release-build` green on merge commit
- [ ] AGP version + Gradle wrapper version consistent (no version skew)
- [ ] AppBundle artifact produced (not just analyze pass)

## Release Process

### Versioning
- Monorepo: `pubspec.yaml` version bumped via `auto-bump.sh` on main
- Mobile: Version synced from monorepo + build number increment

### Release Steps
1. Monorepo `main` receives version bump commit
2. `sync-mobile.yml` triggers, syncs to `autobrain-mobile`
3. `mobile-release-build.yml` runs on mobile repo (validates release build)
4. Mobile Release Engineer manually triggers `ios-release.yml` / `android-release.yml`
4. Artifacts uploaded to Play Console / App Store Connect
5. Mobile Release Engineer promotes to production

### Hotfix Process
1. Create hotfix branch from `main` in monorepo
2. Apply fix, bump version
3. Merge to `main` → triggers sync → mobile release build
4. Mobile Release Engineer deploys hotfix

## Key Differences: Monorepo vs Mobile Repo

| Aspect | Monorepo (`frontend/`) | Mobile Repo (`autobrain-mobile/`) |
|--------|------------------------|-----------------------------------|
| Target | Web (Flutter web) | iOS + Android |
| `pubspec.yaml` | Web deps only | Mobile deps (`geolocator`, `flutter_map`, `latlong2`, `flutter_local_notifications`, etc.) |
| Platform dirs | None | `android/`, `ios/` |
| Entry point | `lib/main_web.dart` | `lib/main.dart` |
| CI | Part of monorepo CI | Independent mobile CI |
| Release | N/A (web auto-deploy) | Manual via Play Console / App Store |

## Adding Mobile-Only Dependencies

1. Add dependency to `autobrain-mobile/pubspec.yaml`
2. Add platform-specific code in `autobrain-mobile/lib/platform/`
3. **Do NOT** add to monorepo `frontend/pubspec.yaml` — it will cause web build failures

## Adding Shared Code

1. Add to `autobrain/frontend/lib/` (monorepo)
2. Ensure `part` directives in `models.dart` for model files
3. Run `sync-mobile.yml` (auto on main push) or manual dispatch
4. Verify `mobile-release-build.yml` passes

## Troubleshooting

### Sync Workflow Fails
1. Check `sync-mobile.yml` logs for specific error
2. Common: missing `part` directive → add to monorepo `models.dart`
3. Common: unresolved import → add dep to mobile `pubspec.yaml`

### Release Build Fails
1. Check `mobile-release-build.yml` logs
2. Common: AGP/Gradle version mismatch → align versions in `android/build.gradle` and `android/gradle/wrapper/gradle-wrapper.properties`
3. Common: Missing signing config → ensure keystore/secrets configured in mobile repo

### Test Failures After Sync
1. Run `flutter test` locally in mobile repo
2. Check for web-only tests that were synced → add to `.sync-ignore` or move

## Related Issues

- AUT-1907: Mobile release trigger
- AUT-440: Mobile release unstick
- AUT-447: CI failure spam (sync-mobile)
- AUT-2177: Release build verification gate
- AUT-5205: Sync guard (part directives)
- AUT-5584: Fuel history part directive sync issue

## See Also

- `docs/Engineering/mobile-release.md` — Mobile release process details
- `.github/workflows/sync-mobile.yml` — Sync workflow definition
- `autobrain-mobile/.github/workflows/mobile-release-build.yml` — Release build gate
- `scripts/auto-bump.sh` — Version bumping script
