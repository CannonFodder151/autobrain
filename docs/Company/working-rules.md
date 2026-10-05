# Working Rules & Team Conventions

## General Principles

1. **Deterministic first, AI fallback** — Every AI function must have a deterministic path. AI is a fallback, not the primary logic.
2. **Cost consciousness** — Route all AI through 9Router. Track token spend. Prefer cheaper models for simple tasks.
3. **Modularity** — Small, focused modules. Clear boundaries between backend, AI gateway, frontend, mobile.
4. **Documentation as code** — Update Outline + GitHub mirror in the same change. No stale docs.
5. **Security by default** — No secrets in public repos. Per-instance secrets in Outline only. Least privilege for agents.

## Git & PR Workflow

- **Branching** — All changes on branches off `main`. Never push directly to `main`.
- **PRs** — Open PR for every change. Squash-merge after QA + Security + OCR approval, using the AUT-2230 gate script (AUT-5561). Never arm GitHub auto-merge: `allow_auto_merge` is `false` on this repo, and the gate enforces QA **and** Security at the exact head, which a one-approval auto-merge cannot.
  ```bash
  node .agents/skills/pr-gardening/scripts/merge-gated.mjs \
    --repo CannonFodder151/autobrain --pr NUMBER --origin AUT-NNN
  ```
- **Never leave approved PRs open** — Once the gate reports both roles clean, merge immediately.
- **Deploy after merge** — Deploy to all servers (dev box + AutoBrain-Hosted) after merge.
- **Post-deploy QA mandatory** — Every deployment requires QA verification (AUT-3624). Deployment not complete until QA signs off.

## Issue & Task Management

- **All work through Paperclip issues** — Check out task, do work, record products, post summary, close issue.
- **Batch decomposition** — When an issue lists multiple discrete items, immediately decompose into child issues (one per item) before starting.
- **Follow-up rule** — Every identified problem/TODO/next step becomes a child issue (parentId = current issue) before finishing run.
- **No hallucinated issue IDs** — Must call Paperclip API, verify 201 response, use returned identifier.

## Agent Conventions

- **Model routing** — CEO uses `9router/CEO`, all others use `9router/Employee`. All calls via 9Router at `http://10.0.3.17:20128/v1`.
- **Budgets** — Respect agent budgets. Propose hires via Paperclip when needed.
- **Communication** — Discord is the main status/approval portal. Use n8n Discord Reporter for embeds. Channels: `status`, `approvals`, `updates`, `roadmap`, `incidents`, `ops`, `testing`, `support`, `changelog`.
- **Nathan approvals** — Only for genuine board decisions (budget, hires, contracts, major architecture, policy). NOT for PRs.

## Code Standards

- **Lazy senior developer** — Stdlib/native first. Shortest diff. Deletion over addition. Boring over clever.
- **No unrequested abstractions** — No interface with one implementation, no factory for one product.
- **Error handling** — Prevent data loss. Validate at trust boundaries.
- **Testing** — Non-trivial logic leaves one runnable check (assert-based self-check or small test file).

## Environment Discipline

| Environment | Host | Portainer Endpoint | Purpose |
|-------------|------|-------------------|---------|
| Dev | 10.0.3.39 | 6 (PaperClip-AutoBrain-Dev-Box) | Dev box, Paperclip control plane |
| Demo | 10.0.3.17 | 2 (Portainer-Host) | Demo stack |
| Default | 10.0.3.17 | 2 (Portainer-Host) | Default stack |
| Hosted (Prod) | 152.69.188.133 | 5 (AutoBrain-Hosted) | ARM Oracle VM, production, HA |

- 9Router for AI: `http://10.0.3.17:20128/v1` (on Default host)
- Demo/Default use different compose files on same Portainer endpoint
- Hosted has own API, rego-lookup, 9Router instance

## Secrets Management

- **Paperclip secrets** — All credentials (GitHub PAT, Portainer API key, Discord tokens, Outline token, n8n key, 9Router keys, Oracle VM IP, Docker Hub creds, SSH creds)
- **Never print tokens** — Use env vars or secret references
- **Git clone** — Use `GITHUB_TOKEN` env (gh credential helper). Never embed token in URL.
- **Scratch clones** — `rm -rf` when done. Never keep in `/tmp`.

## Discord Reporting Format

Always use embeds via n8n Discord Reporter:
```bash
curl -s -X POST https://n8n.nathanmartina.com/webhook/discord-report \
  -H "Content-Type: application/json" \
  -d '{"channel":"status","title":"...","description":"...","color":"0x57F287","author":"Role","fields":[{"name":"...","value":"...","inline":true}]}'
```

Colors: status green `0x57F287`/amber `0xFEE75C`/down `0xED4245`; approvals `0x5865F2`; updates `0x3498DB`; roadmap `0x9B59B6`; incidents `0xED4245`/`0xE67E22`; ops `0x95A5A6`; changelog `0x2ECC71`.

## Documentation Policy (Recap)

- Update Outline (internal) + GitHub `docs/` mirror (public) in same change
- Outline = source of truth, includes per-instance secrets
- Public mirror = sanitised (no secrets, internal endpoints, board-sensitive notes)
- One topic per page. Deterministic over AI. Working index required.

## Deployment Rules

- Reference `docker-compose.hosted.yml` and `docker-compose.prod.yml` for stack definitions
- Portainer endpoints: 5=Hosted (Oracle), 6=Dev Box, 2=Demo/Default
- Cloudflare DNS changes → Discord for Nathan to apply (no API key stored)
- Post-deploy QA issue created by deploying agent → assigned to QA & User Testing

## Incident Response

- Deployment team owns triage
- Post to `#incidents` (private) with embed
- Hotfix or rollback if QA finds regressions
- Resolution posted to `#incidents` and `#updates`

## Weekly Cadence

- **Monday** — CEO posts roadmap digest to `#roadmap`
- **Ongoing** — Status updates to `#status` on phase completion, notable changes, incidents
- **Weekly** — Budget/spend review by CEO
- **Per deploy** — QA smoke tests (login, core features, API health)