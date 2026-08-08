.PHONY: up down build logs test lint seed migrate deploy

# Start the dev stack with hot reload
up:
	docker compose up -d --build

# Stop and remove the dev stack
down:
	docker compose down

# Build all images without starting
build:
	docker compose build

# Tail all service logs
logs:
	docker compose logs -f

# Run backend + AI tests
test:
	docker compose exec backend pytest
	docker compose exec ai pytest

# Lint backend + AI code
lint:
	docker compose exec backend ruff check app tests
	docker compose exec ai ruff check app tests

# Run Alembic migrations
migrate:
	docker compose exec backend alembic upgrade head

# Seed demo data
seed:
	docker compose exec backend python -m app.db.seed

# Deploy to production via SSH
deploy:
	./scripts/deploy.sh

