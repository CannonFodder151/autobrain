# Developer Onboarding

## 1. Get the repo

```bash
git clone git@github.com:CannonFodder151/autobrain.git
cd autobrain
```

## 2. Local stack

Requires Docker + Compose. No local Python/Flutter needed for backend/AI.

```bash
cp .env.example .env
docker compose up -d --build
```

## 3. Verify

- `curl http://localhost:8000/health` → `{"status":"ok",...}`
- `curl http://localhost:8001/health` → router status
- Open http://localhost:8000/docs

## 4. Code layout

```
backend/   FastAPI + SQLAlchemy + Celery   (app/ = package)
ai/        inference gateway + fallbacks   (app/ = package)
frontend/  Flutter web app                 (lib/ = package)
docker/    build contexts for all images
infra/     k8s, systemd, nginx
scripts/   deploy, backup, setup-server, publish-images, bump-version
tests/     backend + ai tests
docs/      markdown mirrors of the wiki
```

> **Mobile app:** the iOS/Android app lives in the separate **private** repo
> `CannonFodder151/autobrain-mobile`. This repo's `frontend/` is the Flutter
> **web** build only; the two share a common Flutter lineage but are versioned
> independently (`scripts/bump-version.sh --mobile`).

## 5. Day-to-day

- **Add an endpoint** → `backend/app/api/v1/<area>.py` + `schemas/<area>.py`, register in `api/v1/__init__.py`.
- **Add a table** → model in `backend/app/models/`, autogenerate migration.
- **Add an AI feature** → module in `ai/app/modules/` + fallback in `ai/app/fallbacks.py` + client fn in `backend/app/services/ai_client.py`.
- **Add a screen** → `frontend/lib/screens/<area>/`.

## 6. Tests

```bash
docker compose exec backend pytest
docker compose exec ai pytest
# frontend:
cd frontend && flutter test
```

## 7. Docs

Behaviour changes update BOTH the Outline wiki (AutoBrain collection) and `docs/` mirror.

## 8. Rego / market data providers

External lookups (`REGO_LOOKUP_URL`, `MARKET_DATA_URL`) are optional; see `.env.example`. Without them the app uses deterministic offline heuristics.
