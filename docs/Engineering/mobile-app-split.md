# Mobile App Split — `autobrain-mobile` Repo Creation Guide

## Overview

This document describes the extraction of the Flutter mobile app from the monorepo `frontend/` into the private repo `CannonFodder151/autobrain-mobile`. The split was mandated by **ADR-003** (2026-08) to enable independent release cadence, tighter secret isolation, and separate CI/CD for the mobile store builds.

**Source of truth for this split:** ADR-003 in `docs/Company/decisions-adr.md`

---

## Decision Context (ADR-003)

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-08 |
| **Deciders** | CEO, CTO |
| **Context** | Flutter app mixed mobile + web targets in `frontend/`. Mobile has different release cadence, secret handling, and audience. |
| **Decision** | Split mobile app into private repo `CannonFodder151/autobrain-mobile`. `frontend/` retains web app. |
| **Consequences** | Tighter secret isolation, independent CI/CD, requires extraction PR + Mobile Engineer hire. |

---

## Repository Structure

| Repo | Purpose | Visibility |
|------|---------|------------|
| `CannonFodder151/autobrain` | Monorepo. `frontend/` = Flutter **web** app. `scripts/bump-version.sh` lives here. | Public |
| `CannonFodder151/autobrain-mobile` | Private. Same Flutter codebase for **iOS/Android**. Same release version as server (`bump-version.sh --mobile`). | Private |

---

## What Was Extracted

### Platform Directories (Mobile-Only)

These directories **live only in `autobrain-mobile`** and are never synced from the monorepo:

```
autobrain-mobile/
├── android/          # Android Gradle project, signing config, store metadata
├── ios/              # Xcode project, Info.plist, provisioning profiles
├── web/              # Empty (web build handled by monorepo)
```

**Rule:** The sync script (`scripts/sync-mobile.sh`) fails loudly if `ios/` or `android/` ever appear in `frontend/` again (AUT-2642).

### Mobile-Only Source Files (Preserved During Sync)

These files exist in `autobrain-mobile/lib/` with mobile-specific logic. The sync script restores them after copying the shared base from `frontend/lib/`:

| File | Purpose |
|------|---------|
| `lib/core/version_check.dart` | Mobile-only version check logic |
| `lib/core/auth_state.dart` | "Update available" prompt layered on web base |
| `lib/core/config.dart` | `storeBuild` flag, store-native IAP config (AUT-610) |
| `lib/screens/auth/login_screen.dart` | Play Store update prompt |
| `lib/screens/settings/license_screen.dart` | Store-native IAP UI (AUT-610) |
| `lib/services/iap_service.dart` | Singleton `IapService` + `IapCatalog`/`IapProduct` (AUT-610) |
| `lib/services/car/car_kit_trip_monitor.dart` | Phone-path GPS types (`GpsFix`, `PositionSource`) |
| `lib/services/car/car_kit_service.dart` | Phone-path GPS position wiring (AUT-427) |

**Dependency:** `package_info_plus` in `pubspec.yaml` (mobile-only)

---

## Sync Mechanism

### Automated Sync (`.github/workflows/sync-mobile.yml`)

Triggered on every push to `main` in the monorepo touching:
- `frontend/lib/**`
- `frontend/assets/**`
- `frontend/pubspec.yaml`
- `CHANGELOG.md`
- `scripts/bump-version.sh`

**What it does:**
1. Checks out `autobrain-mobile` (private repo) with a PAT
2. Runs `scripts/sync-mobile.sh <mobile-checkout-path>`
3. Commits + pushes to `autobrain-mobile` `main` if anything changed
4. Tags the synced commit (`v<version>`)
5. Dispatches `release-mobile.yml` in `autobrain-mobile`

### Sync Script (`scripts/sync-mobile.sh`)

```bash
./scripts/sync-mobile.sh <path-to-autobrain-mobile-checkout>
```

**Operations:**
1. **Pre-flight checks** — verifies `ios/` and `android/` exist in mobile, don't exist in frontend
2. **Editor backup guard** — fails on `*.bak` / `*~` files in sync paths (AUT-4919)
3. **Copy shared lineage** — `cp -a frontend/lib/. lib/`, `cp -a frontend/assets/. assets/`, `cp CHANGELOG.md`
4. **Restore mobile-only deltas** — `git checkout --` the 8 preserved files
5. **Part-directive guard** — validates `lib/core/models.dart` part directives resolve (AUT-5205)
6. **API compatibility guard** — runs `auto-fix-mobile-test-mocks.py` to align mock classes
7. **Dependency guard** — fails if `lib/` imports packages missing from mobile `pubspec.yaml`
8. **Version bump** — sets mobile `pubspec.yaml` version to match server `APP_VERSION` with incremented build number

---

## Version Management

### Single Version Source

- **One semver** `x.y.z` for both web and mobile
- Managed by `scripts/bump-version.sh <x.y.z> [--mobile]`
- Promotes `[Unreleased]` → `[V]` in `CHANGELOG.md` (see `docs/versioning.md`)

### Version Code (Build Number)

- `pubspec.yaml` format: `version: <x.y.z>+<build>`
- `versionCode` = number after `+` (strictly increasing, burned on Play Console)
- Mobile build number auto-incremented by `sync-mobile.sh` on each sync
- Manual bump: `bump-version.sh --mobile` or edit `pubspec.yaml` directly

---

## Release Pipeline (`autobrain-mobile/.github/workflows/release-mobile.yml`)

### Trigger

- `workflow_dispatch` with `version` input (must match `pubspec.yaml` tag `v<X.Y.Z>+<build>`)
- Automatically dispatched by `sync-mobile.yml` after successful sync

### Steps

1. **Checkout** → Flutter SDK (stable) → Android SDK (API 33+)
2. **Decode keystore** from Actions secrets (`UPLOAD_KEYSTORE_BASE64`, `KEY_STORE_PASSWORD`, `KEY_PASSWORD`, `KEY_ALIAS`)
3. **Verify package identity** — `namespace` + `applicationId` = `com.autobrainservice.app`, `MainActivity.kt` package matches
4. **Build** — `flutter pub get` → `flutter build appbundle --release` with `--dart-define=API_BASE_URL=https://hosted.autobrainservice.app/api/v1` + `WS_BASE_URL`
5. **Signing guard** — `jarsigner -verify` (v1) + `apksigner verify` (v2+v3) with machine upload key fingerprint
6. **Publish GitHub Release** — tag `v<X.Y.Z>+<build>`, body from `CHANGELOG.md`, `app-release.aab` attached (published, not draft)
7. **Play Console closed testing upload** — `scripts/play-upload-closed-testing.sh` uploads to track `alpha` (existing track with testers), commits edit (submits for review)
8. **Discord notifications** — `#changelog` (public, on semantic version change) + `#updates` (staff, every build)

### APK Build Throttle (AUT-2619)

Release `.apk` built **only** when:
1. Meaningful change in `lib/` + `assets/` since last release tag
2. ≥48 hours since last APK build (tracked via floating tag `apk-built`)

The `.aab` (Play artifact) is **never throttled**.

---

## Play Console Configuration

| Setting | Value |
|---------|-------|
| Package name | `com.autobrainservice.app` |
| Closed testing track | `alpha` (custom name, has tester audience) |
| Upload key SHA1 | `F3:79:19:3F:F7:28:54:BE:46:01:6E:CB:FF:43:DC:15:DF:BF:FB:4C` |
| Upload key SHA256 | `A0:F6:2F:A4:55:D7:8D:BA:11:7F:E8:6E:CE:39:93:39:87:84:EE:38:D2:CC:59:F5:C9:37:00:40:BA:2A:78:5C` |
| Key alias | `autobrain` |

**Critical:** `android/app/build.gradle` must have both `namespace` and `applicationId` = `com.autobrainservice.app`. Mismatch = #1 upload rejection cause.

---

## BLE Permissions (AUT-936)

Required for Dongle WiFi provisioning over BLE (`flutter_blue_plus: 1.32.8`):

| Platform | Permission |
|----------|------------|
| iOS | `NSBluetoothAlwaysUsageDescription` in `ios/Runner/Info.plist` (required, crashes without) |
| Android 12+ | `BLUETOOTH_SCAN` (`usesPermissionFlags="neverForLocation"`), `BLUETOOTH_CONNECT` |
| Android 11- | `ACCESS_FINE_LOCATION` covers scan |

**Pin:** `flutter_blue_plus: 1.32.8` — 2.x is paid commercial license.

---

## Store-Native IAP (AUT-610)

Mobile app sells same licences via Apple App Store / Google Play:

| Product ID Pattern | Example |
|--------------------|---------|
| `com.autobrainservice.app.{enthusiast,garage}.{monthly,yearly}` | `com.autobrainservice.app.enthusiast.monthly` |

**Backend catalogue:** `GET /billing/iap/catalog` (public) → `{enabled, products}`

**Mobile-only IAP files:** `lib/services/iap_service.dart`, `lib/screens/settings/license_screen.dart`, `lib/core/config.dart` (`storeBuild` flag)

---

## Change Notes Delivery

| Channel | Content | Trigger |
|---------|---------|---------|
| Discord `#changelog` (public) | Summarized notes + GitHub Release link | Semantic version change only (`0.3.6` → `0.3.7`) |
| GitHub Releases (`autobrain-mobile`) | Full changelog section + `.aab` artifact | Every release (automated) |
| Discord `#updates` (staff) | Short build summary | Every build |

**Shared changelog:** `CHANGELOG.md` in monorepo covers **both** hosted (web) and mobile apps. No separate mobile changelog.

---

## Creating the Repo (One-Time Setup)

### 1. Create Private Repo

```bash
gh repo create CannonFodder151/autobrain-mobile --private --description "AutoBrain mobile app (iOS/Android)"
```

### 2. Initial Extraction

```bash
# In monorepo checkout
cd /path/to/autobrain
./scripts/sync-mobile.sh ../autobrain-mobile
# Review, commit, push in ../autobrain-mobile
```

### 3. Configure Mobile Repo Secrets

Required GitHub Actions secrets in `autobrain-mobile`:

| Secret | Source |
|--------|--------|
| `UPLOAD_KEYSTORE_BASE64` | `base64 -w0 android/upload-keystore.jks` |
| `KEY_STORE_PASSWORD` | Keystore password |
| `KEY_PASSWORD` | Key password |
| `KEY_ALIAS` | `autobrain` |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Service account with Play Console access |
| `GH_PAT` | PAT with write access to `CannonFodder151/autobrain-mobile` |

### 4. Configure Monorepo Secrets

Required for `sync-mobile.yml`:

| Secret | Purpose |
|--------|---------|
| `MOBILE_SYNC_PAT` | PAT with write access to `CannonFodder151/autobrain-mobile` |

### 5. Enable Workflows

- `sync-mobile.yml` in monorepo (runs on `main` pushes)
- `release-mobile.yml` in `autobrain-mobile` (manual dispatch + auto-dispatch from sync)

---

## Operational Notes

### Sync Failure Recovery

If `sync-mobile.sh` fails:
1. Fix the reported issue (missing mobile deltas, part directives, dependencies)
2. Re-run manually: `./scripts/sync-mobile.sh ../autobrain-mobile`
3. Commit + push in mobile repo
4. Re-dispatch `release-mobile.yml` if needed

### Common Failure Modes

| Error | Cause | Fix |
|-------|-------|-----|
| `lib/core/$p is a part of lib/core/models.dart but missing` | New `models/*.dart` not declared in `lib/core/models.dart` | Add `part 'models/foo.dart';` in BOTH repos |
| `lib/ imports packages missing from pubspec.yaml` | New `package:` import in synced code | Add dep to mobile `pubspec.yaml` (match frontend version), `flutter pub get`, commit lockfile |
| `android/` or `ios/` missing in mobile | Platform dirs not migrated | Run initial extraction again, ensure dirs exist |
| Editor backup files found | `*.bak` / `*~` in sync paths | Delete them, re-run |

### Version Drift

If mobile version drifts from server:
- **Auto-corrected** on next sync (build number increments)
- **Manual fix:** `bump-version.sh --mobile` in monorepo, then sync

### Adding New Mobile-Only Files

1. Add file to `autobrain-mobile/lib/`
2. Add to preserved list in `scripts/sync-mobile.sh` (lines 73-78)
3. Commit mobile repo
4. Next sync will preserve it

---

## References

- **ADR-003** — `docs/Company/decisions-adr.md`
- **Mobile Release Runbook** — `docs/Engineering/mobile-release.md`
- **Sync Script** — `scripts/sync-mobile.sh`
- **Versioning** — `docs/versioning.md`
- **CI/CD** — `docs/Deployment-and-Infrastructure/ci-cd.md`
- **Developer Onboarding** — `docs/Engineering/developer-onboarding.md`

---

## Ownership

| Role | Responsibility |
|------|----------------|
| **Mobile Release Engineer** | Mobile packaging, releases, version bumps, CI/CD, Discord notes |
| **Founding Engineer** | Mobile feature code only (Flutter `frontend/` + mirrored mobile repo) |
| **Deployment** | Backend/containers/CI for hosted services (API endpoints mobile targets) |
| **Documentation Manager** | Keep this doc and `mobile-release.md` in sync with process changes |

*Document created per Phase 1 Improvement Plan (AUT-XXXX) — `mobile-app-split.md` was listed as missing.*