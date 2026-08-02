# Security Considerations

## Authentication & sessions

- Passwords hashed with bcrypt (`passlib`).
- JWT access tokens (15-min default; configurable) + refresh tokens (30 days).
- Refresh tokens are validated for type; invalid tokens are rejected.
- All `/api/v1/*` routes except auth require a bearer token.

## Environment & secrets

- `.env` never committed (`.gitignore`). Template at `.env.example` has
  placeholder values only.
- `SECRET_KEY` must be a long random string in production.
- Kubernetes secrets (`infra/k8s/config.yaml`) contain placeholders only —
  replace at install, never commit real values.

## AI router

- `AI_ROUTER_API_KEY` (optional) is sent as a bearer token to the router.
- Router payloads never include credentials or raw receipt images by default
  (the OCR module receives file metadata/preview, not secrets).

## Network

- Prod runs behind nginx; only :80 exposed. Internal services are not
  published.
- CORS is locked to configured origins in production (empty = same-origin).

## Data protection

- Receipts/photos stored in MinIO; keys are random per upload.
- Consider S3 server-side encryption in production.
- Backups contain PII — encrypt backup artifacts at rest.

## Hardening checklist

- [ ] Rotate all default credentials (postgres, minio, SECRET_KEY).
- [ ] Set a real `AI_ROUTER_URL` and key in prod.
- [ ] Restrict CORS origins.
- [ ] Enable HTTPS (TLS termination on nginx or a load balancer).
- [ ] Restrict SSH (key-only auth).
- [ ] Backups encrypted + off-site.
