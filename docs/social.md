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

## Entitlement (rev 4)

Every social route requires premium (`free_account == False`). Demo accounts
keep read-only access (curated demo feed); write routes reject the demo role.

## API

- `GET /social/feed` — published builds (local + remote, desc).
- `POST /social/posts` — share a vehicle as a build: `{vehicle_id, caption?,
  share_scope?, photo_ids?}`. Snapshot is built deterministically from the
  vehicle + mods (no AI). Outbox push happens when federation is on.
- `GET/DELETE /social/posts/{id}` — detail / unshare (takedown).
- `POST/GET /social/posts/{id}/comments`, `POST/GET /social/posts/{id}/likes`.
- `POST /social/posts/{id}/share-link` → `{token, url}`;
  `GET /social/share/{token}` resolves it.
- `POST /social/uploads` — multipart image; webp-compressed on upload
  (`app/social/media.py`), stored in MinIO, returned as a signed short-lived URL.

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
