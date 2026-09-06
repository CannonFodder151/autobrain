# Documentation Policy

## Purpose

This policy defines how AutoBrain documentation is maintained across the Outline wiki and the public repository `docs/` mirror.

## Scope

- **Outline** — internal-only source of truth. Contains all documents, including per-instance secrets and API keys managed by the Deployment team.
- **GitHub `docs/` mirror** — public sanitised mirror. Mirrors Outline structure and content except for internal-only items (secrets, per-instance keys, board-sensitive notes).

## Rules

1. **Update together.** When an agent ships a feature, changes behaviour, updates config, or deploys an instance, the matching Outline doc and the `docs/` mirror must be updated in the same change.
2. **Outline is internal-only.** Nothing customer-facing or public goes there. The Deployment team stores per-instance API keys and secrets in Outline. Do not copy Outline-only content into the public repo.
3. **Public repo docs are sanitised.** Remove per-instance secrets, API keys, internal deployment endpoints, and board-sensitive notes before mirroring to GitHub.
4. **Deterministic over AI.** Docs describe real, verified state. Do not invent behaviour or write aspirational content.
5. **One topic per page.** Keep pages short and focused. Use consistent naming and a working index.

## Enforcement

The Documentation Manager audits for drift (missing docs, stale content, misplaced secrets, public leakage, missing mirrors) and raises issues to the owning department.
