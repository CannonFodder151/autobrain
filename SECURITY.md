# Security Policy

## Reporting a vulnerability

Do **not** open a public issue. Email `security@nathanmartina.com` with details. You will receive a response within 48 hours and a timeline for resolution.

## Supported versions

Only the latest release (`main` branch) receives security patches. The hosted instance is kept current by the Deployment team.

## Hardening checklist (deployers)

- [ ] Rotate all default credentials (postgres, minio, `SECRET_KEY`, `ADMIN_INITIAL_PASSWORD`)
- [ ] Set a real `AI_ROUTER_URL` and `AI_ROUTER_API_KEY`
- [ ] Restrict CORS origins (`CORS_ORIGINS` in production)
- [ ] Enable HTTPS (TLS termination on nginx or load balancer)
- [ ] Restrict SSH to key-only authentication
- [ ] Encrypt backup artifacts at rest and store off-site
- [ ] Set `MFA_ENFORCED=true` on hosted/production instances
- [ ] Rotate `ADMIN_API_KEY` regularly if enabled
- [ ] Run `docker compose` as non-root user
- [ ] Pin Docker base image digests in CI/production

## Architecture security notes

- Passwords: bcrypt (`passlib`, `bcrypt==4.0.1`)
- Sessions: JWT access (30min) + refresh (30d); refresh tokens rotate on use
  (denylisted `jti`) and are revoked by logout/password change via `token_version`
- MFA: TOTP (RFC 6238); MFA tokens are short-lived (5min) and scoped
- No self-signup by default — admin-provisioned accounts only
- `.env` never committed; secrets injected via env vars at runtime
- AI router payloads exclude credentials and raw receipt images
- MinIO object keys are random per upload; bucket is private by default
- Rate limiting on auth endpoints (`LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS`)
- Admin backup/restore is admin-authenticated; restore wipes the database

## Dependency policy

- Dependabot/Snyk scans are not currently automated — manual review on release
- Python dependencies pinned in `requirements.txt`
- Base images updated on each release build
