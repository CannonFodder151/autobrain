# CI/CD Pipeline

How code gets from a branch to running production services.

## Overview

| Pipeline | Trigger | Output |
|----------|---------|--------|
| `dockerhub-publish.yml` | push to `main` (or manual dispatch) | `cannonfodder151/autobrain-{backend,ai,frontend}:latest` + `:hosted` images on Docker Hub; CHANGELOG sync to the marketing site |
| `build-hosted.yml` | manual (`workflow_dispatch`) | `ghcr.io/cannonfodder151/autobrain-{backend,ai,frontend}:<tag>` multi-arch images |
| `arm64-runner-keepalive.yml` | every 30 min (`schedule`) | no artifacts — keeps the EP5 ARM64 runner's broker session exercised and canaries the runner |
| `sync-mobile.yml` | push to `main` touching `frontend/`, `CHANGELOG.md`, `bump-version.sh`, `sync-mobile.sh` (or manual) | `autobrain-mobile` lineage + version sync, dispatches the mobile release pipeline |
| `release-mobile.yml` *(in `autobrain-mobile`)* | manual dispatch with a `version` input | Signed `.aab` + draft GitHub Release + Discord `#changelog`/`#updates` |

All workflows run on `ubuntu-latest`. Builds are multi-arch (`linux/amd64`,
`linux/arm64`). Since AUT-987 each platform is built **natively** on its own
self-hosted runner — amd64 on the x64 dev-box runner, arm64 on the ARM hosted
server (<HOSTED_VM_IP>, Portainer EP5, `arm64`-labeled runner) — and combined
into multi-arch manifests by a `*-manifest` job. No QEMU emulation.

## 1. Docker Hub publish (`dockerhub-publish.yml`)

Runs on every push to `main`, every pull request, and manual dispatch:

1. **changelog-gate** — runs on `pull_request` events only: if the PR changed
   `backend/`, `ai/`, `frontend/`, `docker/` or `docker-compose*` files,
   `CHANGELOG.md` must have changed too; otherwise the job fails. This enforces
   the "every user-facing change ships with a changelog entry" rule (AUT-168).
   Skipped on `push`/manual dispatch — the merge process already grafts
   `[Unreleased]` entries, so a post-merge check would only misfire (AUT-451).
2. **auto-bump** — cuts a release when `[Unreleased]` has content and pushes it
   to `main`, rebasing onto the latest main and retrying up to 3 times on
   concurrent-push conflicts (AUT-451).
3. **publish** — matrix over `[amd64, arm64]`; each leg builds only its native
   platform on the matching self-hosted runner and pushes a per-arch tag
   (`autobrain-<svc>:<tag>-<arch>`). **publish-manifest** then runs
   `docker buildx imagetools create` to assemble the multi-arch manifest lists
    for `autobrain-backend`, `autobrain-ai`,
    `autobrain-frontend`, `autobrain-market-data` for both `latest` and `hosted`
   tags (plus the `default`-tier frontend). The frontend build
   is baked with `API_BASE_URL=https://hosted.autobrainservice.app/api/v1` and
   `WS_BASE_URL=wss://hosted.autobrainservice.app/ws`.
4. **sync-changelog** — copies `CHANGELOG.md` into the
   `autobrainservice-website` repo and pushes if changed.

Image tags: `latest` tracks every main merge; `hosted` is the tag the hosted
Portainer stack pulls. There is no per-release tag — releases pin by checking
the version/changelog match *before* deploy (see below).

## 2. Hosted image build (`build-hosted.yml`)

Manual workflow for one-off tags: input `tag` (default `hosted`), `platforms`,
`api_base_url`, `ws_base_url`. Pushes to GHCR, not Docker Hub. Used for ad-hoc
builds (e.g. a staging tag or a platform-limited test).

### Hosted deploy window (AUT-5172 / AUT-2409)

The hosted stack (Portainer endpoint 5, Oracle Cloud) is production, and
AUT-2409 confines hosted deploys to the nightly **03:00–04:00 AEST** window.

- `compose-pin` runs on every merge to `main`. It still bumps the
  `docker-compose.hosted.yml` digest pins and pushes the commit `[skip ci]`,
  but `scripts/sync-compose-to-portainer.py` **skips the Portainer PUT outside
  the window** (exit 0, `SKIP: …` in the log, zero API calls). A merge at any
  other hour therefore cannot recreate production containers. Pins stay bumped
  in git and the next in-window deploy applies them.
- The gate lives in the script, not the workflow, so every caller is covered —
  not just `compose-pin`. It applies to `--endpoint 5` only; other endpoints
  (e.g. EP2 `9router`) carry no window policy and stay hand-updatable.
- **Override:** `ALLOW_OUT_OF_WINDOW=true` (exported, or the `secrets.*` env
  entry on the dispatch job) permits an out-of-window deploy. Only the
  Deployment Lead sets it, and only for a board-approved deploy.
- A `workflow_dispatch` of this workflow *is* the approved deploy action — the
  job sets `ALLOW_OUT_OF_WINDOW=true` on dispatch, so the in-window 03:00
  deploy path keeps working while push-triggered merges do not redeploy.
- Proof: `scripts/test_sync_compose_to_portainer.py::TestDeployWindowGate`
  (23:00 AEST makes no API call; `ALLOW_OUT_OF_WINDOW=true` PUTs; EP2 still
  PUTs out of window) — run by the `compose-sync-script` CI job.

### Nightly hosted deploy (AUT-5186)

`build-hosted.yml` also runs on `schedule: cron "0 17 * * *"` — 17:00 UTC is
03:00 AEST (AEST is a fixed UTC+10, no DST), the start of the window. That job
(`nightly-hosted-sync`) is the automatic deploy path AUT-5172 removed from
`push`:

- It **only syncs**. It never builds: every other job in the workflow is
  gated `github.event_name != 'schedule'`, so the nightly run cannot rebuild
  images or re-cut a release. It pulls the `:hosted` manifests already on
  ghcr.io and PUTs `docker-compose.hosted.yml` to Portainer endpoint 5 with
  `pullImage=true` (the script default).
- It sets **no** `ALLOW_OUT_OF_WINDOW`, so the window gate above still
  applies. A cron that fires late or early (GitHub schedules are best-effort)
  logs `SKIP: … outside the AUT-2409 hosted deploy window` and exits 0
  without touching EP5 — a misfire skips rather than redeploys. Proof:
  `scripts/test_sync_compose_to_portainer.py::TestNightlyHostedSync`
  (`test_cron_misfire_out_of_window_skips_and_logs_no_digest`).
- The run log records what it rolled out, one line per service:
  `applied: backend -> ghcr.io/…@sha256:…`. Read the run log to audit a
  nightly deploy; no other artifact records the applied digests.
- It runs on a GitHub-hosted runner and holds its own concurrency group, so a
  slow multi-arch build on `main` cannot push the deploy past the window.
- Window is 1 hour and cron is best-effort: if the nightly run is skipped,
  the pins stay bumped in git and the next
  `workflow_dispatch` (which sets the override) applies them.

### ARM64 runner broker keepalive (AUT-5463)

`arm64` builds are the only leg of `build-hosted.yml` that has exactly one
runner: `gh-runner-autobrain-arm64`, containerised on the Oracle Cloud VM
(Portainer endpoint 5). That runner talks to the GitHub Actions broker over a
long-lived WebSocket, and EP5 container logs for 2026-09-27 → 2026-10-04 show
the failure mode that looks alarming but is not:

- 3 real broker drops in 7.09 days (**0.42/day**, one per ~57 h), all while the
  runner was **idle** (36 / 81 / 326 min after the previous job ended). The
  runner backs off ~6–15 s, retries, and reconnects — no session restart, no
  job impact.
- 59 `BrokerServer` `SocketException (125)` bursts in the same window land at
  job end: the message listener cancels its in-flight long-poll and rotates it.
  One per completed job, all 59 jobs still finished.
- 0 jobs were interrupted mid-flight (59 jobs / 624 job-minutes). The only
  session restarts in the window are GitHub's daily 03:00 UTC
  `RunnerRefreshConfigMessage`, which the runner defers until the job dispatcher
  is idle.
- `RestartCount=0` for the container across the whole window — none of the
  154 "restarts" in the AUT-3822 sweep were container restarts.

`arm64-runner-keepalive.yml` therefore runs a 5-line no-op job on
`[self-hosted, linux, ARM64]` every 30 min. It caps the idle gap below the
shortest observed drop threshold and gives the broker regular message traffic;
it is not a retry mechanism (nothing to retry — no drop has hit a running job).
The job also re-asserts `uname -m == aarch64`, the AUT-2097 canary, so a runner
replaced by a qemu-shimmed x86 host fails loudly instead of shipping
mis-labelled manifests.

## 3. Mobile sync (`sync-mobile.yml`)

On any `main` push touching shared Flutter lineage (`frontend/lib`,
`frontend/assets`, `frontend/pubspec.yaml`), `CHANGELOG.md`, or the version/sync
scripts, it:

1. checks out both repos,
2. runs `scripts/sync-mobile.sh` (mirrors `lib` + `assets` + `pubspec.yaml` +
   `CHANGELOG.md` into `autobrain-mobile`, preserves mobile-only deltas,
   bumps the mobile version to match the server `APP_VERSION`),
3. commits + pushes to `autobrain-mobile` if anything changed,
4. tags the synced commit (`v<version>`) and dispatches `release-mobile.yml`
   for that tag. A freshly pushed tag can lag GitHub's ref lookup, so the
   dispatch retries up to ~60s on HTTP 422 "No ref found" before failing
   (AUT-451).

## 4. Mobile release (`release-mobile.yml`, `autobrain-mobile` repo)

Manual release pipeline producing a signed release `.aab`. Never runs on push.
See `docs/mobile-release.md` for the full runbook. In short:

- verifies the requested `version` matches `pubspec.yaml` (`vX.Y.Z+N`),
- installs the Play upload keystore from repo secrets,
- verifies the Play-locked package identity (`com.autobrainservice.app`),
- builds `appbundle`, verifies signatures (AAB v1, upload-key SHA1 fingerprint
  match), publishes a GitHub Release with the `.aab` + top changelog entry,
- **APK build is throttled** (AUT-2619): the `.apk` (used for the apksigner
  v2/v3 scheme + upload-certificate fingerprint check, plus the alternate-store
  feeds) is only built when the mobile code (`lib/`, `assets/`) changed since
  the previous release tag **and** at least 48h have passed since the last
  APK build (tracked via a floating `apk-built` tag ref). Pure version bumps
  skip the APK; the `.aab` is never throttled.
- posts customer-facing notes to Discord `#changelog` and a staff summary to
  `#updates` via the n8n Discord Reporter (best-effort — a reporter outage never
  fails the release).

## 5. Release gates (enforced before deploy)

`scripts/check-release.sh` (called by `deploy.sh` / `publish-images.sh`):

- fails if `CHANGELOG.md` still has a non-empty `[Unreleased]` section,
- fails if `backend/app/core/config.py` `APP_VERSION` does not match the top
  changelog version.

`scripts/bump-version.sh <x.y.z> [--mobile]` is the one tool that moves a
release version everywhere in one shot (see `docs/versioning.md`).

## 2b. Rego-lookup auto-deploy (AUT-264)

`CannonFodder151/rego-lookup-api` deploys automatically on every push to `main`:

1. **Trigger** — push to `main` (or manual `workflow_dispatch`) runs
   `build.yml` in that repo.
2. **Build** — multi-arch image pushed as `ghcr.io/cannonfodder151/rego-lookup:hosted`
   (+ Docker Hub `cannonfodder151/rego-lookup-api:hosted` / `:latest`).
3. **Deploy** — a `deploy` job then calls Portainer with `PullImage: true` on
   **both** tiers (no manual step, order irrelevant here since the image is
   immutable once pushed):
   - On-prem: Portainer stack `plate-api-scraper` (EP2, `<PORTENER_HOST_IP>:8011`), stack id **<STACK_ID>**.
   - Hosted: Portainer stack `rego-lookup` (EP5, `<HOSTED_VM_IP>:8011`), stack id **<STACK_ID>** —
     port is bound to `127.0.0.1` only (loopback, AUT-316), never a public IP.

Secrets live on the `rego-lookup-api` repo: `PORTAINER_URL`, `PORTAINER_API_KEY`,
`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`. The deploy job re-applies each stack's
current compose (no drift) and treats a reverse-proxy `504` on the PUT as
"triggered" (Portainer applies server-side). See the rego-lookup-api README
*Deploy (auto — AUT-264)*.

## 6. Deploy flow

Deploys are promotion-gated — **Demo → Default → Hosted**, in that order, and a
release is only complete when the **Hosted** tier is verified last (board
directive AUT-78; see `docs/deployment-guide.md` for the full checklist).

- **Demo / Default** — `docker compose ... up -d --build` on the dev box from
  source mounts.
- **Hosted** — `./scripts/publish-images.sh hosted` builds + pushes the images,
  then the Portainer stack (endpoint 5, Oracle Cloud) is updated to pull the
  new `:hosted` tag. `sync-changelog` keeps the marketing site in step.
- DB migrations run inside the backend container on boot (Alembic `upgrade
  head`); `scripts/deploy.sh` drives remote deploys over SSH.

## 7. Where CI secrets live

GitHub Actions secrets on `CannonFodder151/autobrain`:
`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` (image publish),
`WEBSITE_SYNC_TOKEN` (marketing-site changelog), `MOBILE_SYNC_TOKEN`
(mobile sync + release dispatch). The mobile repo carries its own
`UPLOAD_KEYSTORE_BASE64`, `KEY_ALIAS`, `KEY_PASSWORD`, `KEY_STORE_PASSWORD`.

`DISCORD_REPORT_WEBHOOK` is the n8n Discord Reporter URL
(`https://n8n.nathanmartina.com/webhook/discord-report`).
Every workflow that posts through it copies the secret into a
`discord_url` local and rejects anything that is not an `http(s)://`
URL **before** curl parses it — a malformed secret would otherwise
reach curl as an *option* (`curl: option -: is unknown`) and the
alert would silently never send (AUT-5690).
`python3 scripts/check-discord-webhook-guard.py` asserts the guard
in both call sites.

> Mirror of the Outline doc *Engineering > CI/CD Pipeline*. Keep in sync when
> the pipelines change. Never store credentials in this file or in the repo.
