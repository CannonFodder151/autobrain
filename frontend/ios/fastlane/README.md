# AutoBrain iOS release pipeline

This directory configures the two Fastlane lanes for the AutoBrain iOS app and
the metadata / screenshot assets that ship with the App Store release.

## Lanes

| Lane | What it does |
| ---- | ------------ |
| `fastlane ios tests`    | Runs `flutter analyze` + `flutter test` before packaging. |
| `fastlane ios beta`     | Builds a TestFlight build, uploads to the internal QA group, tags the commit. |
| `fastlane ios release`  | Uploads a production build + App Store metadata, optionally submits for review. |
| `fastlane ios metadata` | Re-uploads only the App Store metadata (no binary). |
| `fastlane ios screenshots` | Re-frames and uploads the localized App Store screenshots. |
| `fastlane ios certs`    | Refreshes the app-store certificates and provisioning profiles via `match`. |

All lanes require the App Store Connect API key in the environment:

| Variable | Source | Purpose |
| -------- | ------ | ------- |
| `APPLE_KEY_ID`         | `apple-store-api-key` Paperclip secret | App Store Connect API key id |
| `APPLE_ISSUER_ID`      | `apple-store-api-key` Paperclip secret | App Store Connect issuer id |
| `APPLE_KEY_PATH`       | `apple-store-api-key` Paperclip secret | Local path to the `.p8` token file |
| `APPLE_TEAM_ID`        | `apple-store-api-key` Paperclip secret | Apple developer team id |
| `APPLE_ITC_TEAM_ID`    | `apple-store-api-key` Paperclip secret | App Store Connect team id |
| `APPLE_ID`             | `apple-store-api-key` Paperclip secret | Apple id for Appfile defaults |
| `MATCH_S3_ACCESS_KEY` / `MATCH_S3_SECRET_ACCESS_KEY` | `apple-store-api-key` Paperclip secret | Read-only access to the cert S3 bucket |
| `GITHUB_TOKEN`         | existing `github_pat` secret | Tag + release asset publication |
| `SLACK_RELEASE_WEBHOOK_URL` | optional | Notification on lane failure |

## Certificates and profiles

`fastlane match` is configured in `Matchfile` to read from the
`autobrain-ios-certificates` s3 bucket and the
`CannonFodder151/autobrain-certificates` git repo. CI runs in readonly mode;
only the `certs` lane mutates the bucket.

| Type | Profile | App identifier |
| ---- | ------- | -------------- |
| appstore | `match AppStore com.autobrain.autobrain` | `com.autobrain.autobrain` |

## App Store metadata

`metadata/` mirrors the structure `deliver` expects: one folder per locale,
with `name.txt`, `subtitle.txt`, `description.txt`, `keywords.txt`,
`marketing_url.txt`, `privacy_url.txt`, `support_url.txt`, and
`release_notes.txt`. `en-US/` is populated now; other locales inherit the same
wording until a translator pass runs.

Screenshots live in `screenshots/<locale>/<device>/`. Run
`fastlane ios screenshots` to re-frame the source PNGs and push them to App
Store Connect.

## How a release runs

```bash
export APPLE_KEY_ID="..."
export APPLE_ISSUER_ID="..."
export APPLE_KEY_PATH="$RUN_TMPDIR/AuthKey_$APPLE_KEY_ID.p8"
export APPLE_TEAM_ID="..."
bundle exec fastlane ios beta --bump patch
bundle exec fastlane ios release --bump minor --submit
```
