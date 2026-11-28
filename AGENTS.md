## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## graphify CLI (AutoBrain dev box)

The `graphify` command is not on PATH on the shared dev box. Use the full path:

```
GRAPHIFY=/paperclip/graphify/bin/graphify
$GRAPHIFY query "auth flow"
$GRAPHIFY path "AuthState" "API"
$GRAPHIFY explain "RateLimiter"
```

`graph.json` is committed, so the graph works from any clone; only the CLI needs this path.

<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` ​→ ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` ​→ every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->

## AutoBrain Project-Specific Patterns

### Code Style
- **Python**: FastAPI, SQLAlchemy 2.0 async, Pydantic v2, type hints mandatory
- **Flutter/Dart**: null safety, Riverpod for state, material design
- **TypeScript**: not used (Flutter web)
- **SQL**: PostgreSQL 17 + pgvector, Alembic migrations

### Architecture Patterns
- **API**: REST + WebSocket, versioned at `/api/v1`
- **Auth**: JWT (access + refresh rotation), TOTP MFA (RFC 6238), passkeys (WebAuthn)
- **AI**: All inference via 9Router (OpenAI-compatible); deterministic rule-based fallbacks
- **Async**: Celery (Redis broker) for background tasks, Celery Beat for scheduling
- **Storage**: MinIO (S3-compatible) for files, PostgreSQL for relational data
- **Frontend**: Flutter web served by nginx, proxies API/WebSocket/AI same-origin

### Key Conventions
- **Environment**: All config via `.env` (from `.env.example`), never hardcoded
- **Secrets**: `*_FILE` suffix for file-based secrets (AUT-1533), Docker secrets in production
- **Database**: `alembic upgrade head` on boot; `create_all` fallback only for dev
- **Docker**: Multi-stage builds, digest-pinned base images (security)
- **Versioning**: `scripts/bump-version.sh` updates all version files + mobile pubspec

### Testing
- **Backend**: pytest, async, fixtures in `tests/conftest.py`
- **Frontend**: `flutter test` for unit/widget tests
- **Integration**: Post-deploy smoke script (`scripts/post-deploy-smoke.sh`)
- **CI**: GitHub Actions with Docker layer caching, Trivy scanning

### Deployment
- **Tiers**: Demo → Default → Hosted (mandatory promotion order)
- **Hosted**: Oracle Cloud VM, Portainer stack, GHCR images, nightly 03:00–04:00 AEST window
- **Health checks**: `/health` on all services, post-deploy smoke required
- **Rollback**: Portainer stack redeploy previous image tag

### AI Module Pattern
Each AI module follows deterministic-first pattern:
1. Rule-based fallback (always works, no external deps)
2. 9Router enrichment (if available, adds confidence/detail)
3. Response includes `model` field: `"9router"` or `"rule-based-fallback"`

### Security
- **CORS**: Same-origin only by default; explicit allowlist via `CORS_ALLOWED_ORIGINS`
- **Rate limiting**: Per-user AI limits + gateway burst caps
- **Demo accounts**: Read-only, all write endpoints + AI return 403
- **MFA**: Enforced for non-demo accounts when `MFA_ENFORCED=true`
- **Secrets**: Never in code/logs; Paperclip secrets API / Docker secrets

### Common Commands
```bash
# Development
docker compose up -d --build
docker compose logs -f backend

# Database
docker compose exec backend alembic revision --autogenerate -m "change"
docker compose exec backend alembic upgrade head

# Testing
docker compose exec backend pytest -xvs
flutter test

# Deployment
./scripts/publish-images.sh <tag>
./scripts/upgrade-instances.sh
./scripts/post-deploy-smoke.sh <url>
./scripts/prune-images.sh

# Version bump
./scripts/bump-version.sh [--mobile]
```
