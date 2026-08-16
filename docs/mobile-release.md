# Mobile Release Runbook (`.aab`)

Run this whenever frontend/app changes ship so AutoBrain's Android app is updated,
a release `.aab` is produced, and Nathan knows where the change notes live.

## Ownership

**Mobile Release Engineer** owns mobile packaging + releases end to end:

- version bumps (`scripts/bump-version.sh --mobile`) + `versionCode` rules
- Flutter lineage sync from the monorepo `frontend/` into `autobrain-mobile`
- `.aab` / `.apk` builds + machine-keystore signing
- GitHub Releases on `autobrain-mobile`
- Play Console **closed testing** upload (automated: `scripts/play-upload-closed-testing.sh`, track `testing`)
- Discord `#changelog` / `#updates` notes
- `docs/mobile-release.md` + the release workflow

**Founding Engineer** owns mobile **feature code** only (Flutter `frontend/` in the
monorepo and the mirrored mobile repo); hands off release-ready code. No version
bumps, no releases.

**Deployment** owns infra / containers / CI for backend + hosted services,
including the hosted API endpoints the app targets
(`https://hosted.autobrainservice.app/…`). It does **not** own mobile builds.

Ownership split defined by the CTO in the Mobile packaging issue (Paperclip
`AUT-145`).

**Canonical home for `.aab` change notes:**
- **`CHANGELOG.md` in the `autobrain` monorepo is the single shared changelog for BOTH the hosted (web) app and the mobile app.** Mobile has no changelog of its own — GitHub Releases here use the shared changelog, so its contents are mirrored into this repo on every sync.
- Discord **`#changelog`** on AutoBrain HQ (public, customer-facing) — link +
  summarized notes, posted **only when a new semantic version ships**
  (`0.3.6` → `0.3.7`), not per-build.
- **GitHub Releases** on `CannonFodder151/autobrain-mobile` — the `.aab` artifact + full notes from the shared changelog.
- A short staff summary also posts to Discord **`#updates`** on every build.

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
  **dispatches the mobile release pipeline** (which **publishes** the release
  automatically — no draft backlog, see step 7 below) automatically.

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

### 3c. (Optional) Build a release `.apk` for sideload/test

`.aab` is the Play artifact; the `.apk` is optional and for sideloading/testing only:

```bash
cd autobrain-mobile
flutter build apk --release \
  --dart-define=API_BASE_URL=https://hosted.autobrainservice.app/api/v1 \
  --dart-define=WS_BASE_URL=wss://hosted.autobrainservice.app/ws
```

Artifact: `build/app/outputs/flutter-apk/app-release.apk`. Same version/versionCode
rules as the `.aab`.

### 4. Create a GitHub Release and attach the `.aab`

The CI pipeline (step 7 below) does this automatically and **publishes** the
release — drafts are no longer used. Manual fallback (tag = version, e.g. `v1.2.3+10`):

```bash
# Create the release (tag = version, e.g. v1.2.3+10)
curl -s -X POST https://api.github.com/repos/CannonFodder151/autobrain-mobile/releases \
  -H "Authorization: Bearer <PAT>" \
  -d '{"tag_name":"v1.2.3+10","name":"v1.2.3+10","body":"<release notes>","draft":false}'
# Upload the artifact (from the release response `upload_url`)
curl -s -X POST "<upload_url>?name=app-release.aab" \
  -H "Authorization: Bearer <PAT>" -H "Content-Type: application/octet-stream" \
  --data-binary @build/app/outputs/bundle/release/app-release.aab
```

### 4b. Play Console closed testing upload (automated)

After the GitHub Release, the release pipeline automatically uploads the freshly
built `.aab` to the **Play Console closed testing** track. No manual upload.

- Track: `testing` (a closed testing track; closed testing tracks have **custom
  names**, there is no fixed API default — resolved live via the AndroidPublisher
  Tracks API on first use).
- Runner script: `scripts/play-upload-closed-testing.sh` in `autobrain-mobile`
  (`bash scripts/play-upload-closed-testing.sh <app-release.aab> [track-id]`).
  Requires the `bash`/`curl`/`jq`/`openssl` tools (present on runner images) and
  the service-account JSON via `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (GitHub Actions
  secret `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`; never commit or print it).
- It: talks to the `/upload/` media host for `bundles.upload` (the regular API
  host hangs on that copy), assigns the release (`status: completed`) to the
  track, then **commits the edit — which is what "submits for review" to Google
  Play**. It re-checks the track via the Tracks API and fails if the new
  versionCode is not visible.
- **Closed testing requires a tester audience.** Play refuses a `completed`
  ("live to testers") release on a closed testing track that has **no tester
  group** ("Release in track targeting no countries"). Until a tester group is
  configured in Play Console, the script commits the release as a **draft**
  (still uploaded + versionCode-visible on the track, ready to roll out from the
  Play Console) and logs a warning. Once testers are added, the same pipeline
  commits directly as `completed` with no code change. When the run falls back
  to draft, the pipeline also posts an embed to Discord **`#approvals`** asking
  Nathan to do the one-time track setup (play.google.com/console →
  `com.autobrainservice.app` → Testing → Closed testing → the `testing` track →
  add testers + country availability, restOfWorld on).
- Production is never touched — a promo to production is a separate, human-gated
  action in Play Console.

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
7. Publishes a **published** GitHub Release (`softprops/action-gh-release@v2`
   with `draft: false`) on tag `v<X.Y.Z>+<build>` with that version's
   `CHANGELOG.md` section as the body and `app-release.aab` attached. The release
   is **fully published by the workflow** — it does not stall as a draft.
8. **Play closed-testing upload** (was the manual "Play Console upload checklist
   (Nathan)" step): `scripts/play-upload-closed-testing.sh` uploads the built
   `.aab` to the Play Console closed testing track `testing` and commits the edit
   (submits for review). See step 4b for the tester-audience/draft fallback.
9. Posts the release embeds to Discord via the internal reporter webhook (see
   the Outline "Discord reporter" doc): `changelog` (public, `0x2ECC71`) and
   `updates` (staff, `0x3498DB`). Payloads are built with `jq`
   (changelog text contains quotes that break inline JSON) and are best-effort
   (`|| true` so a transient reporter outage never fails a release).
   The `changelog` embed only fires when the semantic version iterates
   (e.g. `0.3.6` → `0.3.7`) — build-only bumps of the same version skip it —
   and carries a summarized changelog (top bullets of the version's section).

Run it from the repo Actions tab (or `gh workflow run release-mobile.yml -f
version=v<X.Y.Z>+<build>`).

## Where the `.aab` lives (Nathan's answer)

- **Change notes:** Discord **`#changelog`** on AutoBrain HQ (public) + GitHub Releases on
  `CannonFodder151/autobrain-mobile`.
- **Artifact:** `app-release.aab` attached to the matching GitHub Release
  (`https://github.com/CannonFodder151/autobrain-mobile/releases`), then uploaded
  **automatically** to the Play Console **closed testing** track
  (play.google.com/console, `com.autobrainservice.app` → closed testing).
- Staff summary: Discord **`#updates`**.
