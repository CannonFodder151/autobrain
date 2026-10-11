# Mobile App Split — `autobrain-mobile` Repo Creation

The Flutter mobile app currently lives in `frontend/` of the main `autobrain` monorepo. This document describes the plan to split it into a dedicated private repository `autobrain-mobile`.

## Rationale

| Factor | Current (monorepo) | After Split |
|--------|-------------------|-------------|
| **CI/CD** | Mobile builds run on every backend/frontend change | Independent mobile pipeline |
| **Build time** | Flutter web + mobile + backend all in one pipeline | Mobile-only pipeline (~5 min vs 15 min) |
| **Deploy** | Tied to monorepo release | Independent mobile releases |
| **Team** | All engineers touch mobile code | Dedicated mobile team |
| **Dependencies** | Shared `pubspec.yaml` with web | Mobile-specific dependencies |
| **Security** | Mobile code in public repo | Private repo (proprietary features) |

## Repository Structure

### New: `autobrain-mobile` (private)

```
autobrain-mobile/
├── .github/
│   └── workflows/
│       ├── ci.yml              # flutter test, analyze, build
│       ├── release.yml         # build + deploy to Play Store / TestFlight
│       └── dependency-review.yml
├── lib/
│   ├── main.dart
│   ├── app.dart
│   ├── core/                   # Shared with web via git submodule or package
│   │   ├── api/                # API client (generated from OpenAPI)
│   │   ├── models/             # Data models
│   │   ├── services/           # Storage, auth, notifications
│   │   └── utils/
│   ├── features/               # Feature modules
│   │   ├── garage/
│   │   ├── fuel/
│   │   ├── diagnostics/
│   │   ├── advisor/
│   │   └── social/
│   └── shared/                 # Widgets, theme, routing
├── test/
├── integration_test/
├── android/
├── ios/
├── pubspec.yaml
├── melos.yaml                  # If using melos for monorepo-style packages
└── README.md
```

### Existing: `autobrain` (public)

```
autobrain/
├── frontend/                   # Flutter WEB only
│   ├── lib/
│   │   ├── main.dart           # Web entry point
│   │   └── web/                # Web-specific code
│   ├── web/
│   └── pubspec.yaml            # Web dependencies only
├── backend/
├── ai/
└── ...
```

## Shared Code Strategy

### Option A: Git Submodule (recommended)

```bash
# In autobrain-mobile:
git submodule add https://github.com/CannonFodder151/autobrain-shared.git lib/core

# In autobrain (frontend):
git submodule add https://github.com/CannonFodder151/autobrain-shared.git lib/core
```

Create `autobrain-shared` repo with:
- `lib/core/api/` — generated API client
- `lib/core/models/` — shared data models
- `lib/core/services/` — storage, auth, notifications
- `lib/core/utils/` — common utilities

### Option B: Dart Package (pub.dev or Git dependency)

```yaml
# pubspec.yaml
dependencies:
  autobrain_core:
    git:
      url: https://github.com/CannonFodder151/autobrain-core.git
      ref: main
```

Publish `autobrain_core` as a private package on pub.dev or use Git dependency.

### Option C: Copy + Sync (simplest, short-term)

Copy shared files to both repos, use a sync script or GitHub Action to keep in sync.

## Migration Steps

### Phase 1: Prepare (Week 1)

1. [ ] Create `autobrain-mobile` private repo on GitHub
2. [ ] Create `autobrain-shared` repo (or decide on package strategy)
3. [ ] Set up CI/CD for mobile repo (flutter test, analyze, build)
4. [ ] Configure code signing (iOS certificates, Android keystore)
5. [ ] Set up Fastlane for Play Store / TestFlight deployment

### Phase 2: Extract Mobile Code (Week 2)

1. [ ] Copy `frontend/lib` → `autobrain-mobile/lib`
2. [ ] Remove web-specific code from mobile (`web/`, `index.html`, web plugins)
3. [ ] Update `pubspec.yaml` — remove web-only dependencies (`flutter_web_plugins`, `universal_html`, etc.)
4. [ ] Add mobile-only dependencies (`camera`, `geolocator`, `local_auth`, `flutter_local_notifications`, etc.)
5. [ ] Configure `android/` and `ios/` folders (copy from frontend, update bundle IDs, signing)
6. [ ] Update imports to use shared package/submodule

### Phase 3: Clean Up Monorepo (Week 3)

1. [ ] Remove mobile-specific code from `frontend/` (keep only web)
2. [ ] Update `frontend/pubspec.yaml` — web-only dependencies
3. [ ] Update monorepo CI to skip mobile build
4. [ ] Update `docker-compose.yml` — frontend image builds web only
5. [ ] Update deployment scripts for hosted/demo stacks

### Phase 4: Validate & Deploy (Week 4)

1. [ ] Run full mobile test suite
2. [ ] Build and test on device (iOS + Android)
3. [ ] Deploy to TestFlight / Internal Play Store track
4. [ ] Run integration tests against hosted backend
5. [ ] Update documentation

## CI/CD Pipeline (autobrain-mobile)

### `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter analyze
  
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter test --coverage
      - uses: codecov/codecov-action@v3

  build-android:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter build apk --release
      - uses: actions/upload-artifact@v4
        with:
          name: app-release.apk
          path: build/app/outputs/flutter-apk/app-release.apk

  build-ios:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter build ios --release --no-codesign
      - uses: actions/upload-artifact@v4
        with:
          name: app-release.ipa
          path: build/ios/ipa/*.ipa
```

### `.github/workflows/release.yml`

```yaml
name: Release
on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Version (e.g. 1.2.0)'
        required: true
      track:
        description: 'Release track'
        type: choice
        options: [internal, alpha, beta, production]
        default: internal

jobs:
  release-android:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter build appbundle --release
      - uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJson: ${{ secrets.GOOGLE_PLAY_SERVICE_ACCOUNT }}
          packageName: com.autobrainservice.app
          releaseFiles: build/app/outputs/bundle/release/app-release.aab
          track: ${{ github.event.inputs.track }}
          versionCode: ${{ github.run_number }}

  release-ios:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter build ios --release
      - uses: apple-actions/upload-testflight-build@v1
        with:
          app-path: build/ios/ipa/*.ipa
          api-key: ${{ secrets.APP_STORE_CONNECT_API_KEY }}
          api-issuer: ${{ secrets.APP_STORE_CONNECT_ISSUER_ID }}
```

## Configuration & Secrets

### Required Secrets (GitHub Actions)

| Secret | Description |
|--------|-------------|
| `GOOGLE_PLAY_SERVICE_ACCOUNT` | Service account JSON for Play Console |
| `APP_STORE_CONNECT_API_KEY` | App Store Connect API key (p8) |
| `APP_STORE_CONNECT_ISSUER_ID` | App Store Connect issuer ID |
| `APP_STORE_CONNECT_KEY_ID` | App Store Connect key ID |
| `FLUTTER_KEYSTORE_BASE64` | Android keystore (base64 encoded) |
| `FLUTTER_KEYSTORE_PASSWORD` | Keystore password |
| `FLUTTER_KEY_PASSWORD` | Key password |
| `FLUTTER_KEY_ALIAS` | Key alias |

### Environment-Specific Config

```dart
// lib/core/config/env.dart
class EnvConfig {
  static const String apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const String appBaseUrl = String.fromEnvironment('APP_BASE_URL');
  static const bool enableAnalytics = bool.fromEnvironment('ENABLE_ANALYTICS');
  static const String sentryDsn = String.fromEnvironment('SENTRY_DSN');
}
```

Build with:
```bash
flutter build apk --release \
  --dart-define=API_BASE_URL=https://hosted.autobrainservice.app \
  --dart-define=APP_BASE_URL=https://autobrainservice.app \
  --dart-define=ENABLE_ANALYTICS=true \
  --dart-define=SENTRY_DSN=$SENTRY_DSN
```

## Flutter Version Management

Pin Flutter version in both repos:

```yaml
# .github/workflows/ci.yml
- uses: subosito/flutter-action@v2
  with:
    flutter-version: '3.24.3'
    channel: 'stable'
```

Also create `.fvmrc` in each repo for local development:
```json
{"version": "3.24.3"}
```

## Rollback Plan

If issues arise after split:

1. Revert monorepo CI to build mobile
2. Copy mobile code back to `frontend/lib`
3. Mobile repo stays as backup/archive
4. Re-evaluate split strategy

## Timeline & Ownership

| Phase | Duration | Owner |
|-------|----------|-------|
| Prepare | 1 week | CTO + Mobile Lead |
| Extract | 2 weeks | Mobile Lead + 1 engineer |
| Cleanup | 1 week | CTO + Frontend Lead |
| Validate | 1 week | QA + Mobile Lead |
| **Total** | **5 weeks** | |

## Related Issues

- `AUT-XXXX` — Create `autobrain-mobile` repo
- `AUT-XXXX` — Extract mobile code from monorepo
- `AUT-XXXX` — Set up mobile CI/CD (Fastlane, code signing)
- `AUT-XXXX` — Create `autobrain-shared` package
- `AUT-XXXX` — Update monorepo CI to skip mobile
- `AUT-XXXX` — Update deployment for web-only frontend