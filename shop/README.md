# AutoBrain Shop — Multi-Tenant Workshop Management

Backend service for multi-tenant workshop management with subscription tiers, per-workshop user management, and AI-powered features.

## Architecture

- **FastAPI** — async REST API
- **PostgreSQL + pgvector** — primary datastore with vector search
- **Redis** — Celery broker + rate limiting
- **MinIO** — object storage for assets
- **Alembic** — async database migrations
- **9Router** — AI gateway for all AI calls

## Multi-Tenant Data Model

- **Workshop** (tenant): name, slug, email, address, subscription tier (starter/professional/enterprise), Stripe integration
- **WorkshopUser**: per-workshop users with roles (owner/manager/tech/admin), MFA support, token versioning for revocation
- **SubscriptionTier**: STARTER, PROFESSIONAL, ENTERPRISE — controls max users, max vehicles, AI access

## Quick Start

```bash
# From autobrain repo root
cp .env.shop.example .env
# Edit .env with real values
docker compose -f docker-compose.shop.yml up --build
```

Services:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Development

```bash
# Run migrations
cd shop
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Run tests
pytest shop/tests/
```

## Environment Variables

See `.env.shop.example` for all required variables. Key ones:

| Variable | Description |
|----------|-------------|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Database credentials |
| `REDIS_PASSWORD` | Redis auth (required) |
| `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | MinIO credentials |
| `SECRET_KEY` | JWT signing key (generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`) |
| `AI_ROUTER_URL`, `AI_GATEWAY_API_KEY` | 9Router AI gateway |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Billing (hosted) |

## Image Publishing

Private images only — push to `ghcr.io/cannonfodder151/autobrain-shop-*`:

```bash
docker build -f docker/shop/Dockerfile -t ghcr.io/cannonfodder151/autobrain-shop:latest .
docker push ghcr.io/cannonfodder151/autobrain-shop:latest
```

## API Endpoints

### Auth
- `POST /api/v1/auth/login` — email/password + optional TOTP
- `POST /api/v1/auth/refresh` — refresh access token
- `POST /api/v1/auth/mfa/setup` — initiate MFA setup (QR code)
- `POST /api/v1/auth/mfa/verify` — verify TOTP, enable MFA
- `POST /api/v1/auth/mfa/disable` — verify TOTP, disable MFA
- `GET /api/v1/auth/me` — current user

### Workshops
- `POST /api/v1/workshops` — create workshop (creates owner user)
- `GET /api/v1/workshops` — list workshops (admin)
- `GET /api/v1/workshops/{id}` — get workshop
- `PATCH /api/v1/workshops/{id}` — update workshop (owner/admin)
- `DELETE /api/v1/workshops/{id}` — delete workshop (owner only)
- `POST /api/v1/workshops/{id}/users` — add user (owner/admin)
- `GET /api/v1/workshops/{id}/users` — list users
- `PATCH /api/v1/workshops/{id}/users/{user_id}` — update user (owner/admin)
- `DELETE /api/v1/workshops/{id}/users/{user_id}` — remove user (owner/admin)

## Role Permissions

| Role | Workshop CRUD | User Management | Settings |
|------|---------------|-----------------|----------|
| Owner | Full | Full | Full |
| Admin | Full | Full | Full |
| Manager | Read/Update | Create/Read/Update | Read |
| Tech | Read | Read | Read |

## Deployment

Production deployment uses `docker-compose.prod.shop.yml` (to be created) with the same image published to GHCR. All secrets injected via `.env` or secret files (`*_FILE` pattern per AUT-1533).