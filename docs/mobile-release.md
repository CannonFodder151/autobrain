# Mobile Release Runbook (`.aab`)

Run this whenever frontend/app changes ship so AutoBrain's Android app is updated,
a release `.aab` is produced, and Nathan knows where the change notes live.

**Canonical home for `.aab` change notes:**
- **`CHANGELOG.md` in the `autobrain` monorepo is the single shared changelog for BOTH the hosted (web) app and the mobile app.** Mobile has no changelog of its own — GitHub Releases here use the shared changelog, so its contents are mirrored into this repo on every sync.
- Discord **`#changelog`** on AutoBrain HQ (public, customer-facing) — link + notes.
- **GitHub Releases** on `CannonFodder151/autobrain-mobile` — the `.aab` artifact + full notes from the shared changelog.
- A short staff summary also posts to Discord **`#updates`**.

## Repos

| Repo | Purpose |
|------|---------|
| `CannonFodder151/autobrain` | Monorepo. `frontend/` = Flutter **web** app. `scripts/bump-version.sh` lives here. |
| `CannonFodder151/autobrain-mobile` | Private. The same Flutter codebase for **iOS/Android**. Same release version as the server (`bump-version.sh --mobile`). |

## Prerequisites (build runner)

The `.aab` **cannot** be built from the Paperclip dev box (no Flutter SDK / Android SDK
installed). Build on a machine with:

- Flutter SDK (stable channel), `flutter doctor` clean for Android toolchain
- Android SDK with `build-tools` + `platforms` (API 33+)
- Git + a PAT with access to `CannonFodder151/autobrain-mobile` (private)
- Network access to `pub.dev` (first `flutter pub get`)

Recommended runner: a GitHub Actions `ubuntu-latest` job (see checklist below) or a
local machine with the above.

## Steps

### 1. Sync shared Flutter lineage into `autobrain-mobile` (automatic)

The mobile repo mirrors the web app's Flutter code. **This is now automated**:
`.github/workflows/sync-mobile.yml` on `autobrain` `main` runs
`scripts/sync-mobile.sh` on every push touching `frontend/lib`, `frontend/assets`,
`frontend/pubspec.yaml`, `CHANGELOG.md` or `scripts/bump-version.sh`. It:

- mirrors `frontend/lib`, `frontend/assets`, `pubspec.yaml` and the shared
  `CHANGELOG.md` into `autobrain-mobile` (single source for both apps),
- bumps the mobile version to match the server `APP_VERSION` (build number
  incremented), commits + pushes to `autobrain-mobile` `main`, then
  **dispatches the mobile release pipeline** (draft release) automatically.

`scripts/sync-mobile.sh` **preserves mobile-only deltas** and will not silently
drop them:
- `lib/core/version_check.dart` (mobile-only file)
- `lib/core/auth_state.dart` + `lib/screens/auth/login_screen.dart` — the
  "update available" prompt logic layered on the web base
- `package_info_plus` pubspec dependency

> If the shared (web) base of `auth_state.dart` / `login_screen.dart` changes,
> the web copy would drop those mobile deltas, so `sync-mobile.sh` restores the
> mobile versions and a human must re-merge the deltas on top. Platform folders
> (`android/`, `ios/`, `web/`) are never touched.

Manual fallback (monorepo checkout with a sibling mobile repo, or explicit path):

```bash
./scripts/sync-mobile.sh ../autobrain-mobile
# review, then commit + push inside autobrain-mobile
```

### 2. Bump the mobile version

**Automatic**: `sync-mobile.yml` bumps it to match the server `APP_VERSION`
(with an incremented build number) and dispatches the release. Manual bump
(e.g. a throwaway validation build) — `bump-version.sh --mobile` from the
monorepo, or directly:

```bash
# pubspec.yaml version: <major>.<minor>.<patch>+<build>
sed -i -E 's/^version: [0-9.]+.*/version: 1.2.3+10/' pubspec.yaml
```

> **versionCode is the number after `+`** and must be **strictly higher** than any
> version ever uploaded to Play Console. Once a version code is used on Play it is
> burned forever — you cannot reuse it. When in doubt, `+1` the previous build
> number. `flutter build` turns `<x.y.z>+<N>` into `versionName=<x.y.z>`,
> `versionCode=<N>` automatically; do **not** hardcode versionCode in
> `android/app/build.gradle` (it reads `local.properties` from pubspec).

### 3. Build the release `.aab`

```bash
cd autobrain-mobile
flutter pub get
flutter build appbundle --release \
  --dart-define=API_BASE_URL=https://hosted.autobrainservice.app/api/v1 \
  --dart-define=WS_BASE_URL=wss://hosted.autobrainservice.app/ws
```

Artifact: `build/app/outputs/bundle/release/app-release.aab`

### 3b. Android package name & signing (must-match checklist)

Play Console is locked to package **`com.autobrainservice.app`**. Before uploading,
verify these in `autobrain-mobile` — a mismatch is the #1 cause of upload rejection:

1. `android/app/build.gradle` → `namespace` and `applicationId` must be
   **`com.autobrainservice.app`** (both, together). Do NOT use `com.autobrain.app`.
2. `MainActivity.kt` package must match the namespace:
   `android/app/src/main/kotlin/com/autobrainservice/app/MainActivity.kt`.
3. The androidx-startup content-provider authority is auto-derived from the
   `applicationId` (`<appId>.androidx-startup`). Keeping `applicationId` =
   `com.autobrainservice.app` avoids the "authority in use by other developers"
   rejection. Never add a hardcoded `androidx-startup` provider with the old appId.
4. Sign with the **machine keystore** (`key.properties` in `android/`), not a
   different AutoBrain key. The machine upload key is the certificate Play has
   registered — **signer SHA1 must be
   `F3:79:19:3F:F7:28:54:BE:46:01:6E:CB:FF:43:DC:15:DF:BF:FB:4C`**
   (SHA256 `A0:F6:2F:A4:55:D7:8D:BA:11:7F:E8:6E:CE:39:93:39:87:84:EE:38:D2:CC:59:F5:C9:37:00:40:BA:2A:78:5C`,
   alias `autobrain`). Any other fingerprint — e.g. the generated keystore that
   was briefly wired into CI (alias `upload`, `35:90:61:…`) — is rejected by
   Play with "signed with the wrong key". AGP signs the `.aab` with the JAR
   (v1) signature; Play re-signs the derived APKs with the upload key using
   **v2+v3**, which is what Play actually requires. Verify after the build:
   `jarsigner -verify <aab>` for the v1 (JAR) signature, plus
   `apksigner verify --verbose --print-certs` on a **same-`signingConfig`
   release APK** — it must report v2 and v3 and the machine-key SHA-1 digest
   (`f379193f…`). The release `signingConfig` in `android/app/build.gradle`
   enables v1+v2+v3 explicitly
   (`enableV1Signing`/`enableV2Signing`/`enableV3Signing`). CI enforces this
   too: `release-mobile.yml` aborts the build when the signer fingerprint
   does not match, so a wrong keystore in the `UPLOAD_KEYSTORE_BASE64` /
   `KEY_ALIAS` / `KEY_PASSWORD` / `KEY_STORE_PASSWORD` secrets can never ship.

Commit and push any of these changes to `autobrain-mobile` **before** building.

### 4. Create a GitHub Release and attach the `.aab`

```bash
# Create the release (tag = version, e.g. v1.2.3+10)
curl -s -X POST https://api.github.com/repos/CannonFodder151/autobrain-mobile/releases \
  -H "Authorization: Bearer <PAT>" \
  -d '{"tag_name":"v1.2.3+10","name":"v1.2.3+10","body":"<release notes>","draft":true}'
# Upload the artifact (from the release response `upload_url`)
curl -s -X POST "<upload_url>?name=app-release.aab" \
  -H "Authorization: Bearer <PAT>" -H "Content-Type: application/octet-stream" \
  --data-binary @build/app/outputs/bundle/release/app-release.aab
# Publish the release
```

### 5. Post change notes to Discord (via n8n Reporter)

Internal runbook — the reporter webhook URL and exact embed payloads live in
the Outline wiki (AutoBrain collection, "Discord reporter" doc), not in this
public repo. Payloads target the public **`changelog`** channel and the staff
**`updates`** channel. Keep embeds tight: `title` ≤ 90 chars, `description` 1–4
lines, `fields` ≤ 4.

### 6. Mirror the release into the marketing site changelog

Every release also lands on the public website: add the new version entry to
`autobrainservice-website/changelog.html` (same content as `CHANGELOG.md`), then
commit + push that repo. The site's Azure Static Web Apps deployment publishes
it automatically.

## GitHub Actions (shipped)

Automated pipeline now lives at `CannonFodder151/autobrain-mobile`
`.github/workflows/release-mobile.yml` (steps 3–5, plus version/identity guards):

1. Trigger: `workflow_dispatch` only — input `version` must equal the
   `pubspec.yaml` version tag (`v<X.Y.Z>+<build>`, e.g. `v0.3.5+22`); the job
   fails if they mismatch. `sync-mobile.yml` dispatches it automatically on a
   frontend version bump; otherwise bump with `sync-mobile.sh` first.
2. `actions/checkout@v4` → `subosito/flutter-action@v2` (stable) →
   `android-actions/setup-android@v3`.
3. Decodes `android/upload-keystore.jks` + writes `android/key.properties` from
   Actions secrets (`UPLOAD_KEYSTORE_BASE64`, `KEY_STORE_PASSWORD`,
   `KEY_PASSWORD`, `KEY_ALIAS`). Keystore files are gitignored — never commit.
4. Verifies Play-locked package identity: `namespace` + `applicationId` =
   `com.autobrainservice.app` and the `MainActivity.kt` package statement.
5. `flutter pub get` + `flutter build appbundle --release --dart-define=...`
   (hosted API/WS URLs), then builds the release APK with the same config.
6. Signing guard: `jarsigner -verify` the `.aab` (v1) and `apksigner verify`
   the APK for v2+v3 (Play-required), with the upload certificate.
7. Publishes a **draft** GitHub Release (`softprops/action-gh-release@v2`) on
   tag `v<X.Y.Z>+<build>` with the shared `CHANGELOG.md` top entry as the body
   and `app-release.aab` attached. Publish the draft when the CEO/CTO approves.
8. Posts the release embeds to Discord via the internal reporter webhook (see
   the Outline "Discord reporter" doc): `changelog` (public, `0x2ECC71`) and
   `updates` (staff, `0x3498DB`). Payloads are built with `jq`
   (changelog text contains quotes that break inline JSON) and are best-effort
   (`|| true` so a transient reporter outage never fails a release).

Run it from the repo Actions tab (or `gh workflow run release-mobile.yml -f
version=v<X.Y.Z>+<build>`).

## Where the `.aab` lives (Nathan's answer)

- **Change notes:** Discord **`#changelog`** on AutoBrain HQ (public) + GitHub Releases on
  `CannonFodder151/autobrain-mobile`.
- **Artifact:** `app-release.aab` attached to the matching GitHub Release
  (`https://github.com/CannonFodder151/autobrain-mobile/releases`).
- Staff summary: Discord **`#updates`**.
