.PHONY: up down build logs test lint seed migrate deploy

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

test:
	docker compose exec backend pytest
	docker compose exec ai pytest

lint:
	docker compose exec backend ruff check app tests
	docker compose exec ai ruff check app tests

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python -m app.db.seed

deploy:
	./scripts/deploy.sh

