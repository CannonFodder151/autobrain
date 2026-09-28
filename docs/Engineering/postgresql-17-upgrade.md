# PostgreSQL 17 + pgvector Upgrade

## Current state

All three tiers (Demo, Default, Hosted) run **PostgreSQL 17** with the **pgvector** extension pre-installed:

```yaml
image: pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f
```

- **Major bump:** pg16 → pg17 (AUT-1749).
- **Digest pin** so the multi-arch manifest (amd64 dev box + arm64 Oracle VM) is immutable across every endpoint. Bump deliberately: verify release notes first.
- The `vector` extension is created by migration `g7h8i9j0k1l2`; the image ships the extension files so `CREATE EXTENSION vector` succeeds at migration time.
- In dev the port is published to `127.0.0.1:5432` only. In prod/hosted it is internal to the compose network.

## pgvector schema in use

Five tables carry `embedding vector(1536)` columns (dimension from `EMBEDDING_DIMENSION`, matching `text-embedding-3-small`), each with an HNSW cosine-similarity index:

| Table | Migration | Content embedded |
|-------|-----------|------------------|
| `diagnostics` | `g7h8i9j0k1l2` | Symptoms + AI response summary |
| `service_records` | `g7h8i9j0k1l2` | Description + notes + steps |
| `modifications` | `g7h8i9j0k1l2` | Name + notes + category |
| `receipts` | `g7h8i9j0k1l2` | Vendor + extracted line-item names |
| `social_issue_posts` | `u1v2w3x4y5z6` | Title + body (Issues Blog, AUT-627) |

`h1i2j3k4l5m6` rebuilt the indexes as **HNSW** (they were IVFFlat on older DBs, which needs list tuning that does not pay off on small per-user tables).

The `embedding` columns exist at the **database layer only** — the SQLAlchemy models do not map them. Writes go through raw SQL in `backend/app/services/search.py` (`backfill_entity_embedding`).

**Alembic head:** single head at `m3rge06`, verified by `backend/tests/test_alembic_heads.py`. Migrations run inside the backend container on boot (`alembic upgrade head` in dev/prod, `python -m app.db.bootstrap` in hosted), so a redeploy is a complete upgrade — no separate migration step.

## Non-root container

The postgres service runs with `read_only: true`, `cap_drop: [ALL]`, and `tmpfs` for `/tmp` and `/var/run/postgresql` in prod/hosted. Data lives on a named volume (`postgres-data`) mounted at `/var/lib/postgresql/data`.

## Digest pin rationale

The Oracle Cloud VM (EP5) is ARM64; the dev box and Demo/Default are x86_64. Pinning the multi-arch manifest-list digest (`pgvector/pgvector:pg17@sha256:cf134a76...`) guarantees the same bits on every architecture — a floating `:pg17` tag can resolve to different manifests per node and break the arm64 deploy. Bump deliberately: check the release notes, update the digest in all three compose files (`docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.hosted.yml`) in one PR, and run `scripts/check-compose-config.py` to validate.

## Upgrade procedure (pg16 → pg17, for future bumps)

1. Review the PostgreSQL 17 release notes for breaking changes.
2. Update the image tag + digest in all three compose files.
3. Run `docker compose config` (or `scripts/check-compose-config.py`) to validate interpolation.
4. Deploy Demo first, verify `pg_isready` and `/health` are green.
5. Promote to Default, then Hosted (AUT-107 order).
6. Verify pgvector extension is still present: `docker exec <postgres> psql -c '\dx vector'`.