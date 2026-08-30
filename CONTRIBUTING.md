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
- Run `ruff check` and `pytest` before pushing.
- Backend + AI: `docker compose exec backend ruff check app tests && docker compose exec backend pytest`
- Frontend: `cd frontend && flutter analyze && flutter test`

## Feature parity & changelog (mandatory)

- **Build every feature for BOTH frontends at the same time** — the web app
  (`frontend/`, hosted at autobrainservice.app) and the mobile app
  (`CannonFodder151/autobrain-mobile`). They share one Flutter codebase; a
  feature is not "done" until the screen/flow exists in both.
- **The only exception is OBD2 integration** — it is **mobile-only** and must
  NOT be exposed on the website.
- **Every feature must update the shared [CHANGELOG.md](CHANGELOG.md)** under
  "Unreleased". It is the single changelog for both the hosted and mobile apps —
  no separate mobile changelog. Add the entry in the same PR that ships the
  feature, listing it once even though it lands in both apps.
- Frontend-only changes (a new screen, setting, or flow) count as features and
  need a changelog entry too.

## Code style

- **Python:** black + ruff (line length 100). Type hints required.
- **Dart/Flutter:** follow `flutter analyze` rules; prefer `const` constructors, no `print()` in widgets.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).
- No comments unless they explain *why*.

## Tests

- Backend: `tests/backend/` — run `docker compose exec backend pytest`.
- AI: `tests/ai/` — run `docker compose exec ai pytest`.
- Frontend: `frontend/test/` — run `flutter test` from the `frontend/` directory.
- QA & User Testing runs a post-push test pass for every change immediately
  after merge (Gate 2, `docs/change-validation-gate.md`).

## Documentation

Docs live in the Outline wiki and are mirrored to `docs/`. Update both when you
change behaviour. The API spec is generated from OpenAPI and stored in
`docs/api-spec.md`.

## Security

- Every change needs Security sign-off BEFORE implementation starts (Gate 1,
  `docs/change-validation-gate.md`). Security-critical changes (auth, payments,
  data access, secrets, network) get a full review, not an auto-pass.
- Never commit `.env` or secrets.
- Add new environment variables to `.env.example`.
- Secrets must be injected via env vars at runtime only.
- See [SECURITY.md](SECURITY.md) for vulnerability reporting.
