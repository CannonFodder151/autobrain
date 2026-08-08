# Contributing to AutoBrain

Thanks for contributing! Please read the [developer onboarding guide](docs/developer-onboarding.md) first.

## Getting started

1. Fork the repo.
2. Clone: `git clone git@github.com:CannonFodder151/autobrain.git`
3. Copy `.env.example` → `.env` and fill values.
4. `docker compose up --build` and verify http://localhost:8000/docs.

## Branching & PRs

- Branch from `main`: `git checkout -b feat/my-feature`.
- Keep PRs small and focused.
- Every PR must update the [CHANGELOG.md](CHANGELOG.md) under "Unreleased".
- Run `ruff check` and `pytest` before pushing.
- Backend + AI: `docker compose exec backend ruff check app tests && docker compose exec backend pytest`
- Frontend: `cd frontend && flutter analyze && flutter test`

## Code style

- **Python:** black + ruff (line length 100). Type hints required.
- **Dart/Flutter:** follow `flutter analyze` rules; prefer `const` constructors, no `print()` in widgets.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).
- No comments unless they explain *why*.

## Tests

- Backend: `tests/backend/` — run `docker compose exec backend pytest`.
- AI: `tests/ai/` — run `docker compose exec ai pytest`.
- Frontend: `frontend/test/` — run `flutter test` from the `frontend/` directory.

## Documentation

Docs live in the Outline wiki and are mirrored to `docs/`. Update both when you
change behaviour. The API spec is generated from OpenAPI and stored in
`docs/api-spec.md`.

## Security

- Never commit `.env` or secrets.
- Add new environment variables to `.env.example`.
- Secrets must be injected via env vars at runtime only.
- See [SECURITY.md](SECURITY.md) for vulnerability reporting.
