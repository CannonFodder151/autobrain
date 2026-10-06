# Mobile App Split — `autobrain-mobile` Repo Creation Guide

**Status:** COMPLETE — split executed, sync pipeline automated, iOS/Android platform dirs migrated.
**Parent issue:** AUT-3810 (Phase 1 Workstream E: Documentation)
**Executed by:** Founding Engineer (heartbeat 2026-08-08), CTO review 2026-10-06.
**Related issues:** AUT-5 (repo creation), AUT-3105 (platform dirs migration), AUT-1798 (sync pipeline), AUT-2642 (platform dirs in mobile repo).

---

## Overview

The Flutter mobile app was extracted from `frontend/` of the `CannonFodder151/autobrain` monorepo into a new **private** repository `CannonFodder151/autobrain-mobile`.

| Repo | Visibility | Purpose |
|------|------------|---------|
| `CannonFodder151/autobrain` | Public | Monorepo. `frontend/` = Flutter **web** app. Build, version bump scripts, CI for backend/AI/web. |
| `CannonFodder151/autobrain-mobile` | Private | iOS/Android app. Mirrors shared Flutter lineage from monorepo `frontend/`; owns `ios/`, `android/` platform dirs, store signing config, and release pipelines. |

**Key design decision:** Same Flutter codebase, single source of truth for shared code (`lib/`, `assets/`, `CHANGELOG.md`). Mobile repo gets incremental syncs from monorepo `main` via automated pipeline.

---

## Split Execution (Historical)

### 1. Git subtree split (preserves history)

```bash
# From autobrain repo root
git subtree split -P frontend -b mobile-split
# 39 commits of frontend/ history extracted
```

### 2. New private repo created

```bash
# Via GitHub API (requires github_pat with repo scope)
POST https://api.github.com/user/repos
{"name":"autobrain-mobile","private":true,"description":"AutoBrain mobile app (Flutter)"}
```

### 3. Push split branch as `main`

```bash
git push https://github.com/CannonFodder151/autobrain-mobile.git mobile-split:main
```

### 4. Platform directories migrated (AUT-3105)

The `ios/` and `android/` folders **moved** from `frontend/` to the mobile repo root. They no longer exist in the monorepo.

- `frontend/ios/` → `autobrain-mobile/ios/` (Xcode project, signing, `Runner.xcworkspace`)
- `frontend/android/` → `autobrain-mobile/android/` (Gradle, `build.gradle`, `MainActivity.kt`, upload keystore)

The monorepo `frontend/` now contains **only** the web build (`web/`, `lib/`, `assets/`, `pubspec.yaml`).

### 5. Mobile-only deltas identified & preserved

Files that exist **only** in `autobrain-mobile` (not in monorepo `frontend/`):

| File | Purpose |
|------|---------|
| `lib/core/version_check.dart` | App update check logic (store vs current version) |
| `lib/core/auth_state.dart` | "Update available" prompt layered on web base |
| `lib/core/config.dart` | `storeBuild` flag, IAP config (AUT-610) |
| `lib/screens/auth/login_screen.dart` | Play Store update prompt UI |
| `lib/screens/settings/license_screen.dart` | Store-native IAP license UI (AUT-610) |
| `lib/services/iap_service.dart` | Singleton `IapService` + `IapCatalog`/`IapProduct` (AUT-610) |
| `lib/services/car/car_kit_trip_monitor.dart` | Phone-path GPS types (`GpsFix`, `PositionSource`) |
| `lib/services/car/car_kit_service.dart` | Phone-path GPS position wiring (AUT-427) |
| `pubspec.yaml` dependency `package_info_plus` | Mobile-only package |

**Rule:** `sync-mobile.sh` restores these files after copying the shared base from monorepo. If the web base of any delta file changes, a human must re-merge the mobile deltas.

---

## Automated Sync Pipeline

### Trigger

`.github/workflows/sync-mobile.yml` on `autobrain` runs on every push to `main` touching:

- `frontend/lib/**`
- `frontend/assets/**`
- `frontend/pubspec.yaml`
- `CHANGELOG.md`
- `scripts/bump-version.sh`
- `scripts/sync-mobile.sh`
- `scripts/auto-fix-mobile-test-mocks.py`

Also manually dispatchable: `gh workflow run sync-mobile.yml`.

### What `scripts/sync-mobile.sh` does

```bash
./scripts/sync-mobile.sh <path-to-autobrain-mobile-checkout>
```

1. **Pre-flight guards**
   - Fails if `ios/` or `android/` missing in mobile checkout (AUT-2642).
   - Fails if `ios/` or `android/` exist in monorepo `frontend/` (platform dirs must stay in mobile repo).
   - Fails if editor backup files (`*.bak`, `*~`) found in sync paths (AUT-4919).

2. **Copy shared lineage**
   - `cp -a frontend/lib/. lib/` (verbatim)
   - `cp -a frontend/assets/. assets/`
   - `cp CHANGELOG.md CHANGELOG.md`

3. **Restore mobile-only deltas**
   - `git checkout --` the 8 delta files listed above.

4. **Auto-fix test mocks**
   - Runs `scripts/auto-fix-mobile-test-mocks.py` to align mock signatures with synced `ApiClient` changes (AUT-1939).

5. **Dependency guard**
   - Scans `lib/` for `import 'package:...'` not declared in `pubspec.lock`; fails sync if missing (AUT-455).

6. **Version bump**
   - Reads server version from `frontend/pubspec.yaml` (e.g., `0.3.5+22`).
   - Increments mobile build number: `0.3.5+22` → `0.3.5+23`.
   - Writes new version to mobile `pubspec.yaml`.

7. **Compile guard (CI)**
   - `flutter analyze --no-fatal-warnings --no-fatal-infos` must pass.
   - Self-heals `invalid_override` errors by re-running mock fix; other errors fail the sync.

8. **Commit + push**
   - Commits with message: `chore: sync frontend lineage + version to <version> from autobrain (auto)`
   - Rebases onto latest `origin/main` + retries push up to 3× (AUT-633, AUT-1099).

9. **Tag + dispatch release pipelines**
   - Creates/forces tag `v<version>` (e.g., `v0.3.5+23`).
   - Dispatches `release-mobile.yml` (Android `.aab`) and `release-ios.yml` (iOS `.ipa`).
   - Rate-limit aware (defers dispatch if GitHub API < 100 remaining).
   - Polls for tag visibility before dispatch (AUT-451, AUT-1652).

### Concurrency control

`concurrency.group: sync-mobile-${{ github.ref }}` with `cancel-in-progress: true` — only one sync per ref at a time; newest wins. Safe to cancel because every run syncs `main`'s latest lineage.

---

## Version Management

| Aspect | Monorepo (`autobrain`) | Mobile (`autobrain-mobile`) |
|--------|------------------------|----------------------------|
| **Source of truth** | `frontend/pubspec.yaml` | Mirrored + build incremented |
| **Version format** | `MAJOR.MINOR.PATCH+BUILD` | Same `MAJOR.MINOR.PATCH`, `BUILD+1` |
| **Bump command** | `scripts/bump-version.sh` (or `--mobile`) | Automatic via sync; manual: `sed -i 's/^version: .*/version: X.Y.Z+N/' pubspec.yaml` |
| **`versionCode`** | Not used (web) | The `+N` number — **must strictly increase** for Play Console; burned forever once uploaded. |

---

## Release Pipelines (in `autobrain-mobile`)

### Android: `.github/workflows/release-mobile.yml`

- **Trigger:** `workflow_dispatch` (input `version` must match `pubspec.yaml` tag `vX.Y.Z+N`).
- **Runner:** GitHub-hosted `ubuntu-latest` (Flutter + Android SDK).
- **Steps:**
  1. Checkout at version tag.
  2. Decode upload keystore from `UPLOAD_KEYSTORE_BASE64` secret → `android/upload-keystore.jks` + `android/key.properties`.
  3. Verify package identity: `namespace` + `applicationId` = `com.autobrainservice.app` (Play-locked).
  4. `flutter pub get` + `flutter build appbundle --release` with hosted API/WS URLs.
  5. Signing guard: `jarsigner -verify` (v1) + `apksigner verify` (v2+v3) against machine keystore fingerprint.
  6. Publish **published** GitHub Release (not draft) on tag with `CHANGELOG.md` section + `.aab` artifact.
  7. Upload `.aab` to Play Console **closed testing** track `alpha` via `scripts/play-upload-closed-testing.sh` (service account JSON from `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` secret).
  8. Discord embeds via n8n Reporter: `#changelog` (public, semantic version change only) + `#updates` (staff, every build).

### iOS: `.github/workflows/release-ios.yml`

- **Trigger:** `workflow_dispatch` (same version input).
- **Runner:** Self-hosted macOS (GitHub Actions macOS runner or self-hosted).
- **Steps:**
  1. Checkout at version tag.
  2. Install provisioning profile from `IOS_PROVISIONING_PROFILE_BASE64` secret (App Store profile).
  3. Install distribution certificate from `IOS_DIST_CERT_BASE64` + `IOS_DIST_CERT_PASSWORD` secrets.
  4. `flutter pub get` + `flutter build ipa --release --export-options-plist=ExportOptions.plist` (method=app-store).
  5. Create GitHub Release with `.ipa` artifact.
  6. (Future) TestFlight upload via `xcrun altool` / App Store Connect API.

### APK throttle (AUT-2619)

Release pipeline builds release `.apk` **only** when:
1. Meaningful change in `lib/` + `assets/` since previous release tag (non-empty diff).
2. ≥48 hours since last APK build (tracked by floating tag `apk-built`).

`.aab` is **never** throttled — every release produces and uploads the `.aab`.

---

## Key Files Reference

| File | Repo | Role |
|------|------|------|
| `scripts/sync-mobile.sh` | `autobrain` | Core sync logic (copies lineage, restores deltas, bumps version). |
| `scripts/auto-fix-mobile-test-mocks.py` | `autobrain` | Aligns test mock signatures after API changes in synced `lib/`. |
| `scripts/bump-version.sh` | `autobrain` | Version bump for web + mobile (`--mobile` flag). |
| `.github/workflows/sync-mobile.yml` | `autobrain` | Automated sync pipeline (runs on monorepo pushes). |
| `.github/workflows/release-mobile.yml` | `autobrain-mobile` | Android `.aab` build + GitHub Release + Play upload. |
| `.github/workflows/release-ios.yml` | `autobrain-mobile` | iOS `.ipa` build + GitHub Release. |
| `scripts/play-upload-closed-testing.sh` | `autobrain-mobile` | Play Console closed testing upload (media upload API). |
| `scripts/check-workflow-runner-isolation.sh` | `autobrain-mobile` | Validates runner isolation (AUT-4880). |

---

## Secrets Required

| Secret | Scope | Purpose |
|--------|-------|---------|
| `MOBILE_SYNC_TOKEN` | `autobrain` (GitHub Actions) | PAT with `repo` scope for `autobrain-mobile` clone/push/tag/dispatch. |
| `UPLOAD_KEYSTORE_BASE64` | `autobrain-mobile` | Base64 JKS upload keystore (machine key). |
| `KEY_STORE_PASSWORD` / `KEY_PASSWORD` / `KEY_ALIAS` | `autobrain-mobile` | Keystore credentials (`alias: autobrain`). |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | `autobrain-mobile` | Service account for Play Console upload (media API). |
| `IOS_PROVISIONING_PROFILE_BASE64` | `autobrain-mobile` | App Store provisioning profile (`.mobileprovision`). |
| `IOS_DIST_CERT_BASE64` / `IOS_DIST_CERT_PASSWORD` | `autobrain-mobile` | iOS distribution certificate (`.p12`). |

**Signer fingerprint (machine key):** SHA-1 `F3:79:19:3F:F7:28:54:BE:46:01:6E:CB:FF:43:DC:15:DF:BF:FB:4C` — CI verifies this on every build.

---

## Common Operations

### Manual sync (local)

```bash
# From autobrain checkout with sibling autobrain-mobile checkout
./scripts/sync-mobile.sh ../autobrain-mobile
cd ../autobrain-mobile
git diff  # review
git commit -am "chore: manual sync <version>"
git push origin main
```

### Manual version bump (throwaway validation build)

```bash
# In autobrain-mobile
sed -i -E 's/^version: [0-9.]+.*/version: 1.2.3+10/' pubspec.yaml
git commit -am "chore: bump mobile version to 1.2.3+10"
git push origin main
# Then trigger release-mobile.yml manually with version=v1.2.3+10
```

### Trigger mobile release manually

```bash
# From autobrain-mobile checkout
gh workflow run release-mobile.yml -f version=v0.3.5+23
gh workflow run release-ios.yml -f version=v0.3.5+23
```

### Re-merge mobile deltas after web base change

If `sync-mobile.sh` detects that a delta file's web base changed (the `git checkout --` restore will show conflicts or the file differs from expected):

1. Check `git diff lib/core/auth_state.dart` (or other delta file).
2. Manually re-apply the mobile-specific logic on top of the new web base.
3. Commit the re-merged file in `autobrain-mobile`.
4. Next sync will preserve it.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `sync-mobile.yml` fails at "Compile-guard" | `invalid_override` in test mocks | Self-heal step should fix; if not, run `python3 ../autobrain/scripts/auto-fix-mobile-test-mocks.py .` locally. |
| `sync-mobile.yml` fails at "Dependency guard" | New `package:` import in synced `lib/` not in mobile `pubspec.yaml` | Add missing dependency to mobile `pubspec.yaml` (match version from `frontend/pubspec.yaml`), `flutter pub get`, commit lockfile. |
| `release-mobile.yml` fails at signing guard | Wrong keystore in secrets | Verify `UPLOAD_KEYSTORE_BASE64` decodes to keystore with alias `autobrain` and SHA-1 `F3:79:19:3F:F7:28:54:BE:46:01:6E:CB:FF:43:DC:15:DF:BF:FB:4C`. |
| Play upload fails "authority in use" | `applicationId` != `com.autobrainservice.app` | Fix `android/app/build.gradle` namespace + applicationId + `MainActivity.kt` package. |
| Play upload fails "signed with wrong key" | Keystore fingerprint mismatch | Ensure CI uses machine keystore (not generated upload key). Verify with `apksigner verify --verbose --print-certs`. |
| iOS build fails "no provisioning profile" | `IOS_PROVISIONING_PROFILE_BASE64` missing/expired | Update secret with valid App Store profile (check ExpirationDate). |
| Sync push fails "non-fast-forward" | Concurrent sync races | Workflow retries 3× with rebase; if persistent, manually `cd autobrain-mobile && git pull --rebase origin main && git push`. |

---

## Migration Checklist (for future reference)

If repeating this split for another app:

- [ ] `git subtree split -P <subdir>` to extract history.
- [ ] Create private repo via GitHub API.
- [ ] Push split branch as `main`.
- [ ] Move platform dirs (`ios/`, `android/`) to new repo root.
- [ ] Identify mobile-only delta files (config, store UI, native plugins).
- [ ] Write sync script that copies shared base + restores deltas.
- [ ] Add pre-flight guards (platform dirs, editor backups).
- [ ] Add dependency guard (scan imports vs pubspec.lock).
- [ ] Add version bump logic (mirror + increment build).
- [ ] Add compile guard (`flutter analyze`).
- [ ] Build CI workflow with concurrency control.
- [ ] Configure secrets for signing + store upload.
- [ ] Build release pipelines (Android + iOS).
- [ ] Document ownership split (who bumps version, who releases, who owns features).

---

## Ownership Summary

| Area | Owner |
|------|-------|
| Monorepo `frontend/` (web app, shared Flutter code) | **Founding Engineer** |
| `scripts/sync-mobile.sh`, `sync-mobile.yml` | **Founding Engineer** / **CTO** |
| Mobile repo `autobrain-mobile` (platform dirs, deltas, release pipelines) | **Mobile Release Engineer** |
| Version bumps (server + mobile) | **Founding Engineer** (web), **Mobile Release Engineer** (mobile build number) |
| Android `.aab` build + Play upload | **Mobile Release Engineer** (automated) |
| iOS `.ipa` build + TestFlight | **Mobile Release Engineer** (automated) |
| Discord changelog/updates | **Mobile Release Engineer** (automated via n8n Reporter) |
| Marketing site changelog mirror | **Marketing** (manual per release) |

*Ownership split defined in Paperclip `AUT-145` (Mobile packaging issue).*