# Deploy Runbook

## Overview
This runbook covers deploying AutoBrain to Demo, Default, and Hosted tiers following the mandatory promotion order: **Demo → Default → Hosted**.

## Prerequisites
- Access to Paperclip control plane
- Docker Hub credentials for Demo/Default images
- GHCR credentials for Hosted images
- Portainer access (EP2 for Demo/Default, EP5 for Hosted)

## Promotion Order (MANDATORY)
1. **Demo** — `demo.autobrainservice.app` (public, low-risk, demo account)
2. **Default** — `default.autobrainservice.app` (internal dev/default instance)
3. **Hosted** — `hosted.autobrainservice.app` (Oracle Cloud, production)

> **Never skip or reorder tiers.** A change never goes to Hosted without first passing Demo and Default.

## Deploy to Demo / Default (Docker Hub)

### 1. Build and Push Images
```bash
# From repo root
export DOCKERHUB_USERNAME=cannonfodder151
export CARTO_API_KEY=<from Paperclip secrets>
./scripts/publish-images.sh <tag>  # e.g. 0.3.327 or latest
```

### 2. Update Portainer Stacks
**Demo (Stack 73, EP2):**
- Portainer → Stacks → `autobrain-demo` → Update
- Set `pullImage: true`
- Verify `/health` returns new version

**Default (Stack 68, EP2):**
- Portainer → Stacks → `autobrain-default` → Update
- Set `pullImage: true`
- Verify `/health` returns new version

### 3. Verify
```bash
curl https://demo.autobrainservice.app/health
curl https://default.autobrainservice.app/health
./scripts/post-deploy-smoke.sh https://demo.autobrainservice.app
./scripts/post-deploy-smoke.sh https://default.autobrainservice.app
```

### 4. Prune Dangling Images
```bash
./scripts/prune-images.sh
```

---

## Deploy to Hosted (Oracle Cloud / GHCR)

### 1. Build Hosted Images
```bash
# Trigger via GitHub Actions
gh workflow run build-hosted.yml \
  -f tag=hosted \
  -f api_base_url=https://hosted.autobrainservice.app/api/v1 \
  -f ws_base_url=wss://hosted.autobrainservice.app/ws
```

### 2. Wait for Build Completion
Monitor `build-hosted.yml` workflow. It pushes multi-arch images to GHCR with `:hosted` tag and updates `docker-compose.hosted.yml` digest pins.

### 3. Sync Compose to Portainer (Stack 122, EP5)
```bash
# From repo root (after build-hosted.yml completes)
python3 scripts/sync-compose-to-portainer.py \
  --stack autobrain-hosted --endpoint 5 --file docker-compose.hosted.yml
```

### 4. Verify
```bash
# Check actual running digests match compose
python3 scripts/sync-compose-to-portainer.py --verify-only \
  --stack autobrain-hosted --endpoint 5 --file docker-compose.hosted.yml

# Health + smoke
curl https://hosted.autobrainservice.app/health
./scripts/post-deploy-smoke.sh https://hosted.autobrainservice.app
```

### 5. Prune Dangling Images
```bash
# On Oracle VM via Portainer exec or SSH
./scripts/prune-images.sh
```

---

## Hosted Deploy Window (AUT-2409 / AUT-5172)
- **Window:** 03:00–04:00 AEST (17:00–18:00 UTC)
- **Automatic:** Nightly cron runs `build-hosted.yml` → syncs compose (if in window)
- **Manual override:** `ALLOW_OUT_OF_WINDOW=true` (Deployment Lead only, board approval required)

---

## Post-Deploy Checklist
- [ ] Demo healthy (`/health`, smoke test)
- [ ] Default healthy (`/health`, smoke test)
- [ ] Hosted healthy (`/health`, smoke test)
- [ ] Feature verified on each tier (not just version banner)
- [ ] Dangling images pruned on EP2 and EP5
- [ ] Promotion order + verification noted in issue / `#updates`

---

## Rollback
```bash
# Portainer: redeploy previous stack definition / image tag
# Or if migration: keep old host running, flip DNS back
# See docs/Deployment-and-Infrastructure/server-migration.md
```

---

## Related Docs
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md)
- [CI/CD Pipeline](../Deployment-and-Infrastructure/ci-cd.md)
- [Shop Deployment](../shop-deployment.md)