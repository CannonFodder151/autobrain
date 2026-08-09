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

### 1. Sync shared Flutter lineage into `autobrain-mobile`

The mobile repo mirrors the web app's Flutter code. After web/frontend changes land
on `autobrain` `main`:

```bash
# Fresh checkout of the mobile repo (private, needs PAT)
git clone https://github.com/CannonFodder151/autobrain-mobile.git
cd autobrain-mobile
git checkout main && git pull

# Mirror the shared Flutter source from the monorepo frontend/ (lib/, assets/, pubspec.yaml)
# plus the shared changelog (single source for both apps).
rsync -a --delete \
  --exclude '.git' --exclude 'build/' --exclude 'web/' --exclude 'android/' --exclude 'ios/' \
  ../autobrain/frontend/lib ../autobrain/frontend/assets ./pubspec.yaml ../autobrain/CHANGELOG.md .
# Keep platform folders (android/, ios/) as-is; they are mobile-only.
git add -A && git commit -m "chore: sync frontend lineage + shared changelog from autobrain@<sha>"
```

> Note: `--exclude web/` keeps the mobile repo from tracking the web-only build
> folder. `android/` and `ios/` are owned by this repo and must not be overwritten
> by the monorepo copy.

### 2. Bump the mobile version

From the **monorepo** repo root (bumps `frontend/pubspec.yaml` and, with `--mobile`,
`../autobrain-mobile/pubspec.yaml`):

```bash
cd autobrain
./scripts/bump-version.sh <x.y.z> --mobile
```

Or bump directly in `autobrain-mobile/pubspec.yaml` if the monorepo checkout is not
a sibling:

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
   different AutoBrain key. The AAB must be signed with **v2+v3** (APK Signature
   Block 42 present) — Play rejects v1-only bundles.

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

Public, customer-facing — **`changelog`**:

```bash
curl -s -X POST https://n8n.nathanmartina.com/webhook/discord-report \
  -H "Content-Type: application/json" \
  -d '{"channel":"changelog","title":"AutoBrain app v1.2.3+10 released","description":"<what changed, 1-4 lines>","color":"0x2ECC71","author":"Founding Engineer","fields":[{"name":"Download","value":"https://github.com/CannonFodder151/autobrain-mobile/releases/tag/v1.2.3+10","inline":true},{"name":"Platform","value":"Android (.aab)","inline":true}]}'
```

Short staff summary — **`updates`** (color `0x3498DB`):

```bash
curl -s -X POST https://n8n.nathanmartina.com/webhook/discord-report \
  -H "Content-Type: application/json" \
  -d '{"channel":"updates","title":"Mobile .aab v1.2.3+10 released","description":"Release notes + .aab live.","color":"0x3498DB","author":"Founding Engineer","fields":[{"name":"Artifact","value":"app-release.aab","inline":true},{"name":"Notes","value":"#changelog + GitHub Releases","inline":true}]}'
```

No auth needed on the reporter webhook. Keep embeds tight: `title` ≤ 90 chars,
`description` 1–4 lines, `fields` ≤ 4.

### 6. Mirror the release into the marketing site changelog

Every release also lands on the public website: add the new version entry to
`autobrainservice-website/changelog.html` (same content as `CHANGELOG.md`), then
commit + push that repo. The site's Azure Static Web Apps deployment publishes
it automatically.

## GitHub Actions (recommended automation)

A workflow on `CannonFodder151/autobrain-mobile` (`main`) can automate steps 3–5:

1. `actions/checkout@v4`
2. `subosito/flutter-action@v2` (stable channel)
3. `flutter pub get && flutter build appbundle --release --dart-define=...`
4. Upload `build/app/outputs/bundle/release/app-release.aab` to a `softprops/action-gh-release@v2` release
5. `curl` the n8n `discord-report` webhook for `changelog` + `updates` with the release URL

## Where the `.aab` lives (Nathan's answer)

- **Change notes:** Discord **`#changelog`** on AutoBrain HQ (public) + GitHub Releases on
  `CannonFodder151/autobrain-mobile`.
- **Artifact:** `app-release.aab` attached to the matching GitHub Release
  (`https://github.com/CannonFodder151/autobrain-mobile/releases`).
- Staff summary: Discord **`#updates`**.
