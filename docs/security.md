# Security Considerations

## Authentication & sessions

- Passwords hashed with bcrypt (`passlib`), pinned `bcrypt==4.0.1` for compatibility.
- JWT access tokens (30-minute default; configurable) + refresh tokens (30 days).
- Access and refresh tokens carry a `ver` claim = the user's `token_version` at
  issue time. Bumping `token_version` (logout, password change) instantly revokes
  every outstanding token. Old tokens without a `ver` claim still validate
  (they decode as version 0), so the rollout is backwards compatible.
- Refresh tokens rotate on every `/auth/refresh`: the used token's `jti` is
  denylisted, so a replayed/stolen token is rejected.
- All `/api/v1/*` routes except auth require a bearer token.

## Multi-factor authentication (MFA)

- TOTP (RFC 6238) via `pyotp`; setup returns a secret + QR (data URL).
- Login with MFA enabled returns `{mfa_required, mfa_token}`; the full session is only issued after `/auth/mfa/verify` with a valid 6-digit code.
- MFA tokens are short-lived (5 min) and type-flagged; they cannot be exchanged for access tokens alone.

## Roles & provisioning

- Three roles: `admin`, `user` and `demo` (demo accounts are seeded and
  read-only; only `admin`/`user` are admin-creatable).
- **Admin-only provisioning** — `/auth/register` and `/admin/users` require the
  admin role (403 otherwise; anonymous → 401). Self-service **free signup**
  (`/auth/signup`) is enabled on the hosted instance only
  (`SELF_SIGNUP_ENABLED=true`), otherwise signup 403s.
- The bootstrap admin is created from `ADMIN_EMAIL` / `ADMIN_INITIAL_PASSWORD` on first boot; rotate after first login.
- Deleting the last admin or your own account is blocked.

## Environment & secrets

- `.env` never committed (`.gitignore`). Template at `.env.example` has
  placeholder values only.
- `SECRET_KEY` must be a long random string in production.
- Kubernetes secrets (`infra/k8s/config.yaml`) contain placeholders only —
  replace at install, never commit real values.

## Git operations (credential-safe cloning)

The GitHub `github_pat` (classic PAT, full access) is injected as the env var
`GITHUB_TOKEN` (or fetched via the Paperclip secrets API). It is used ONLY for
agent-side `gh` API operations (PR/release automation) — the deployed server
runtime makes NO authenticated GitHub calls and holds no token (AUT-461).

Private-repo CLONES use **SSH read-only deploy keys**, not a PAT (AUT-461):
- Read-only deploy keys (`agent-deploy-key-readonly`) are registered on
  `autobrain-mobile`, `autobrainservice-website`, `rego-lookup-api`.
- Per-repo keypairs live in `~/.ssh/autobrain_{mobile,website,rego}_deploy`;
  `~/.ssh/config` maps alias hosts (`github-ab-mobile`, `github-ab-website`,
  `github-ab-rego`) to github.com with `IdentitiesOnly yes`.
- `git config --global url.…insteadOf` rewrites the plain HTTPS URLs of the
  three private repos to those SSH aliases, so cloning with the plain HTTPS URL
  still works and needs no token.
- Public repos (e.g. `autobrain`) clone over plain HTTPS without any auth.

All git operations MUST follow this procedure:

- **Clone with the plain HTTPS URL only** — never embed the token:
  `git clone https://github.com/CannonFodder151/<repo>.git`. Private repos are
  transparently routed to SSH deploy keys via the `insteadOf` rewrite above.
- `gh` API operations authenticate via the injected `GITHUB_TOKEN` env
  (gh credential helper) — the token never appears in any URL.
- **Never** use `https://<user>:<token>@github.com/...` — git persists the
  remote URL (token included) into `<repo>/.git/config`, leaking the secret to
  disk (see [AUT-323](/AUT/issues/AUT-323)).
- Purge scratch clones with `rm -rf` when done; never leave clones in `/tmp`.

**Recovery (if a token already leaked into a clone):**

1. Replace every credential-bearing URL/remote value with the plain HTTPS URL:
   `git remote set-url origin https://github.com/CannonFodder151/<repo>.git`.
   This includes `[branch "..."]` blocks whose `remote` line holds a full URL.
2. Expire reflogs so the token is not persisted under `.git/logs`:
   `git reflog expire --expire=now --all`.
3. Regression-check all workspace clones — this must return nothing:
   `grep -rnE '@github\.com' /paperclip/instances/default/workspaces/*/*/.git/config /paperclip/instances/default/projects/*/*/*/.git/config`
4. If the leaked token was still live at exposure time, rotate it (exposed-on-disk
   equals compromised); see [AUT-474](/AUT/issues/AUT-474).

## AI router

- `AI_ROUTER_API_KEY` (optional) is sent as a bearer token to the router.
- Router payloads never include credentials or raw receipt images by default
  (the OCR module receives file metadata/preview, not secrets).

## AI gateway auth

- The AI gateway's `/v1/*` endpoints require the shared `AI_GATEWAY_API_KEY`
  (Bearer token, same value the backend sends via `ai_client.py`). This **fails
  closed** — with the key unset the gateway returns 401 on `/v1/*` unless an
  explicit dev opt-out is set (`AI_ENV=development` or
  `AI_GATEWAY_AUTH_DISABLED=1`).
- Hosted and prod compose refuse to start without it
  (`${AI_GATEWAY_API_KEY:?...}`). Set the same strong random value for the
  backend and `ai` services (Portainer stack env on the hosted instance).

## Network

- Prod runs behind nginx; only :80 exposed. Internal services are not
  published.
- CORS is locked to configured origins in production (empty = same-origin).
- Hosted instance enforces MFA, rate-limits auth endpoints (`LOGIN_MAX_ATTEMPTS=5`, `LOGIN_WINDOW_SECONDS=10800`), and runs behind a Cloudflare-reverse-proxied domain.

### Hosted host: Portainer agent exposure (AUT-472)

The Portainer agent on the Oracle VM (`152.69.188.133:9001`) must never be
reachable from the public internet (full Docker control = container escape /
secrets exfiltration). It is restricted by source at the host firewall:

- Allowed source for `tcp/9001`: the Portainer server egress IP
  `122.199.30.128/32` (dev box / Portainer-Host network). Everything else is
  dropped.
- Enforced by the `fw-keeper` container (image `autobrain-fw-keeper:1`,
  `network_mode: host`, `privileged`, `restart: unless-stopped`) on the hosted
  host. It re-applies the rules every 60s at boot/restart because Ubuntu Core's
  `/etc` is read-only (no iptables-persistent). The container's `cmd` is the
  canonical rule source; the image has no other purpose.
- Rules applied: `iptables -I INPUT 1 -p tcp --dport 9001 ! -s 122.199.30.128 -j DROP`
  (docker-proxy/local socket path) and
  `iptables -I DOCKER-USER 1 -p tcp --dport 9001 ! -s 122.199.30.128 -j DROP`
  (DNAT forward path).
- Verification (2026-08-13, AUT-472): 25/25 external check-host.net nodes
  timed out on `:9001`; Portainer EP5 management still works from the allowed
  source; `GET /ping` answers `204` only from the allowlisted IP.
- Defense-in-depth pending: OCI security list rule to restrict `tcp/9001`
  ingress to `122.199.30.128/32` at the VCN level (needs OCI console access).
- If the Portainer server egress IP ever changes, update the source in the
  `fw-keeper` container command and re-apply.

## Data protection

- Receipts/photos stored in MinIO; keys are random per upload.
- Consider S3 server-side encryption in production.
- Backups contain PII — encrypt backup artifacts at rest.

## Vulnerability reporting

See [SECURITY.md](../../SECURITY.md) for the reporting policy.

## Hardening checklist

- [ ] Rotate all default credentials (postgres, minio, SECRET_KEY).
- [ ] Set a real `AI_ROUTER_URL` and key in prod.
- [ ] Set a real `AI_GATEWAY_API_KEY` (same value for backend + ai services).
- [ ] Restrict CORS origins.
- [ ] Enable HTTPS (TLS termination on nginx or a load balancer).
- [ ] Restrict SSH (key-only auth).
- [x] Restrict Portainer agent (`tcp/9001`) to Portainer server IP via `fw-keeper` (AUT-472).
- [ ] Backups encrypted + off-site.
