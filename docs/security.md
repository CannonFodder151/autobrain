# Security Considerations

**Scope:** `backend/`, `ai/`, `frontend/`, hosted instance. **Last reviewed:** 2026-08-10 (AUT-181). Internal full copy (Secrets Policy, Incident Runbooks) lives in the team wiki (Outline) — this file is the sanitised public mirror.

## Authentication & sessions

- Passwords hashed with bcrypt (`passlib`, pinned `bcrypt==4.0.1` for compatibility).
- JWT access tokens (7-day default; configurable) + refresh tokens (30 days).
- Tokens are type-flagged and validated on use (`access`, `refresh`, `mfa`, `password_reset`, `invite`); a token only grants what its type allows.
- Password-reset tokens are short-lived (30 min); invite tokens 7 days.
- All `/api/v1/*` routes except auth require a bearer token; demo accounts are read-only; demo/free accounts are blocked from AI features.

## Brute-force protection

- Per-IP failed-login tracking with lockout: `LOGIN_MAX_ATTEMPTS=5` per `LOGIN_WINDOW_SECONDS` (3 h) → HTTP 429.
- Applied to login, MFA verify, and MFA setup completion.
- Known limitation: the failure tracker is in-memory — resets on restart and is per-instance only.

## Multi-factor authentication (MFA)

- TOTP (RFC 6238) via `pyotp`; setup returns a secret + QR (data URL).
- Login with MFA enabled returns `{mfa_required, mfa_token}`; the full session is only issued after `/auth/mfa/verify` with a valid 6-digit code.
- MFA tokens are short-lived (5 min) and type-flagged.
- `MFA_ENFORCED=true` forces MFA setup for all non-demo accounts (set on hosted/production).
- Security alerts are emailed on MFA enable/disable.

## Roles & provisioning

- Roles: `admin`, `user`, plus a read-only `demo` account.
- **No self signup by default** — account creation requires the admin role (403 otherwise; anonymous → 401). Hosted may enable `SELF_SIGNUP_ENABLED` for free-tier registration.
- The bootstrap admin is created from `ADMIN_EMAIL` / `ADMIN_INITIAL_PASSWORD` on first boot; rotate after first login.
- Deleting the last admin or your own account is blocked.
- Optional machine-to-machine admin API (`ADMIN_API_KEY`) via `X-Admin-API-Key` header; disabled when the key is unset; rotate regularly when enabled.

## Environment & secrets

- `.env` never committed (`.gitignore`). Template at `.env.example` has placeholder values only.
- `SECRET_KEY` must be a long random string, unique per environment, in every deployment.
- Kubernetes secrets and Compose env in this repo hold placeholders only — replace at install, never commit real values.

## AI router

- `AI_ROUTER_API_KEY` (optional) is sent as a bearer token to the router.
- Router payloads never include credentials or raw receipt images by default (the OCR module receives text, not secrets).
- Every AI module falls back to deterministic rule-based logic when the router is unreachable or errors — the app never depends on the router for availability.
- AI responses are parsed against strict JSON schemas and presented as advice, not authoritative fact.

## Network

- Production publishes only the frontend port (`:80`); internal services are not published and are reachable only on the private network.
- CORS is locked to same-origin in production (empty allowlist = same-origin); dev uses `*`.
- Hosted instance enforces MFA, rate-limits auth endpoints, and runs behind a TLS-terminating reverse proxy.

## Data protection

- Receipts/photos stored in MinIO; keys are random per upload; bucket is private by default.
- Backups contain PII — encrypt backup artifacts at rest and store off-site.
- Payments are handled via Stripe; the app never stores card numbers.
- Consider S3 server-side encryption in production.

## Dependency & supply-chain

- Python dependencies pinned in `requirements.txt`.
- Known gap: automated dependency scanning (Dependabot/Snyk) is not yet wired up — dependency review is manual at release.

## Logging & monitoring

- Authentication/authorisation failures and privilege changes are logged.
- Never log passwords, tokens, or PII.

## Vulnerability reporting

See [SECURITY.md](../../SECURITY.md) for the reporting policy (report to `security@nathanmartina.com`; do not open public issues).

## Hardening checklist

- [ ] Rotate all default credentials (postgres, minio, `SECRET_KEY`, `ADMIN_INITIAL_PASSWORD`).
- [ ] Set a real `AI_ROUTER_URL` and key in prod.
- [ ] Set `MFA_ENFORCED=true` on hosted/production.
- [ ] Restrict CORS origins (same-origin in production).
- [ ] Enable HTTPS (TLS termination at the edge).
- [ ] Restrict SSH (key-only auth).
- [ ] Encrypt backups at rest + off-site.
- [ ] Set and rotate `ADMIN_API_KEY` when enabled.
- [ ] Confirm `SECRET_KEY` is unique per environment.
- [ ] Wire up automated dependency scanning.
- [ ] Run container images as a non-root user.
