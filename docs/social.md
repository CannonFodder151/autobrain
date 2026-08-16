# Community Garage (AUT-294 / AUT-332)

Federated, privacy-preserving social layer. Every AutoBrain instance keeps its
own data (Postgres + MinIO); servers that opt in register with a central
federation hub and exchange build posts. Display identity: `<Display name> from
<Server Name>`.

**Status:** backend only. No publish until the P3 QA/security gate is green.

## Admin toggles (`/api/v1/admin/social`)

| Toggle | Off behaviour |
|---|---|
| `feature_enabled` | All `/social/*` routes return `403 "Disabled by your admin"` |
| `federation_enabled` | Feed still works, local builds only; no hub register/outbox/inbox |

Toggles persist in the singleton `social_server_config` row (seeded from env
`SOCIAL_FEATURE_ENABLED` / `SOCIAL_FEDERATION_ENABLED` on first run). The admin
API (`GET/PATCH /admin/social`, `POST /admin/social/register`,
`POST /admin/social/unregister`) flips them at runtime.

Registration needs `SOCIAL_FEDERATION_HUB_URL` on the backend (default
`https://hub.autobrainservice.app`; wired in all three compose files, AUT-532).
AutoBrain's own stacks set `SOCIAL_FEDERATION_HOSTED=true` (free bundled
license, docs R5a); self-hosted servers leave it unset/false and pay $20/yr at
join. With no hub URL the register route returns `502 hub not configured`.

## Entitlement (rev 4)

Every social route requires premium (`free_account == False`). Demo accounts
keep read-only access (curated demo feed); write routes reject the demo role.

## API

- `GET /social/feed` — published builds (local + remote, desc).
- `GET /social/my-posts` — the caller's own published builds (My Builds tab).
- `POST /social/posts` — share a vehicle as a build: `{vehicle_id, caption?,
  share_scope?, photo_ids?}`. Snapshot is built deterministically from the
  vehicle + mods (no AI). Outbox push happens when federation is on.
- `GET/DELETE /social/posts/{id}` — detail / unshare (takedown).
- `PATCH /social/posts/{id}` — edit the build's caption `{caption?}` (owner-only).
- `POST/GET /social/posts/{id}/comments`, `POST/GET /social/posts/{id}/likes`.
- `POST /social/posts/{id}/share-link` → `{token, url}`;
  `GET /social/share/{token}` resolves it.
- `POST /social/posts/{id}/report` `{reason}` — report a build (AUT-896).
  Records a `social_build_flags` row locally and pushes a hub-local `report`
  event (AUT-896) so the federation-hub operator sees it in the Reported posts
  queue. Idempotent per user per post; hub failures never fail the report.
- `POST /social/uploads` — multipart image; webp-compressed on upload
  (`app/social/media.py`), stored in MinIO, returned as a signed short-lived URL.
- `GET/POST /social/issues...` — the Issues Blog (`app/api/v1/issues.py`).
  Posts, replies and answers federate like builds (AUT-756): outbox payloads
  carry `type: "issue"` and the sync loop routes them into `social_issue_posts`
  with `origin="remote"` + the origin's signed photo URLs.
  - `GET /social/issues?mine=true` — the caller's own posts (My Issues, AUT-832).
  - `POST /social/issues/{id}/flag` — report a post; deduped per user per post.
  - `POST /social/issues/{id}/comments/{cid}/flag` — report a comment (AUT-832);
    deduped per user per comment.
- `GET /admin/issues/review` — **moderation hub (AUT-832)**: every flagged post
  and comment with reporting reason + author, newest first.
- `DELETE /admin/issues/posts/{id}` / `DELETE /admin/issues/comments/{cid}` —
  admin deletes a reported entry (cascades flags/photos).
- `POST /admin/users/{id}/social-ban` / `social-unban` — suspend a user from
  posting in Community Garage (hides/restores their posts; write routes reject
  the ban via `require_premium_write`).

## Share scope (req 11)

Per-build opt-in (`social_share_scopes`). Default minimal: photos + specs +
mods. `allow_odometer` and `allow_notes` are opt-in. Redaction is applied when
the snapshot is built/served — never stored without consent.

## Federation client (`app/social/federation.py`)

Origin-server side only, matching the hub service contract (private repo
`autobrain-federation-hub`, AUT-333):

- `POST {hub}/v1/register` `{server_name, email, public_key, hosted}` →
  `{server_id, api_key}`. `public_key` is a hex ed25519 key the client
  generates at registration; `api_key` is shown once and stored. `hosted`
  (`SOCIAL_FEDERATION_HOSTED`) marks AutoBrain-hosted servers (licensed free).
- Signed federation requests carry `X-Server-Id`, `X-Timestamp`,
  `X-Signature` (ed25519 over `<method>\n<path>\n<timestamp>\n<sha256(body)>`)
  and `X-Api-Key` — the same scheme the hub verifies (see the private repo).
- `POST {hub}/v1/outbox` build metadata + signed photo URLs; `GET {hub}/v1/inbox`
  → `{builds: [...]}` (remote builds stored as `origin="remote"` with their
  snapshot JSON; media fetched on demand). Hub write ops require a valid license.

Every hub call is resilient — failures are logged and never break the local
feed. Remote builds are never re-federated (no loops). **Zero billing code on
end servers** (rev 7); Stripe lives on the hub only.

## Tests

`backend/tests_social/test_social.py` — self-contained (own sqlite engine +
`get_db` override; no Postgres/MinIO needed): run with
`docker compose exec backend pytest tests_social`.
