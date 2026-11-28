# Health Check Runbook

## Overview
Standard health verification procedures for AutoBrain services across all environments.

## Service Health Endpoints

| Service | Endpoint | Expected Response |
|---------|----------|-------------------|
| Backend API | `GET /health` | `{"status":"ok","version":"x.y.z",...}` |
| AI Gateway | `GET /health` | `{"status":"ok","service":"ai-gateway","version":"x.y.z","router_enabled":true,"router_url":"..."}` |
| Frontend | `GET /flutter_bootstrap.js` | 200 OK, valid JS bundle |
| PostgreSQL | `pg_isready` | `accepting connections` |
| Redis | `redis-cli ping` | `PONG` |
| MinIO | `mc ready local` | `OK` |
| 9Router | `GET /api/health` | `{"ok":true}` |

## Quick Health Check (All Tiers)

### Automated (Post-Deploy Smoke Test)
```bash
# Run the standard smoke test script
./scripts/post-deploy-smoke.sh https://<domain> [EXPECTED_FRONTEND_SHA]

# Checks:
# - GET /health → 200, status:ok
# - GET /flutter_bootstrap.js → 200, SHA matches (if provided)
# - POST /api/v1/auth/signup → 201 (with display_name)
# - GET /ready → 200
```

### Manual Verification
```bash
# Backend
curl -s https://<domain>/health | jq .

# AI Gateway
curl -s https://<domain>/ai/health | jq .

# Frontend bundle
curl -sI https://<domain>/flutter_bootstrap.js | head -1

# 9Router (EP2 / hosted)
curl -s http://10.0.3.17:20128/api/health | jq .
curl -s http://9router:20128/api/health | jq .  # internal Docker DNS
```

## Environment-Specific Checks

### Development (localhost)
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8080/flutter_bootstrap.js
curl http://localhost:9001/minio/health/live
```

### Demo (https://demo.autobrainservice.app)
```bash
./scripts/post-deploy-smoke.sh https://demo.autobrainservice.app
curl https://demo.autobrainservice.app/health
```

### Default (https://default.autobrainservice.app)
```bash
./scripts/post-deploy-smoke.sh https://default.autobrainservice.app
curl https://default.autobrainservice.app/health
```

### Hosted (https://hosted.autobrainservice.app)
```bash
./scripts/post-deploy-smoke.sh https://hosted.autobrainservice.app
curl https://hosted.autobrainservice.app/health

# Verify running digests match compose
python3 scripts/sync-compose-to-portainer.py --verify-only \
  --stack autobrain-hosted --endpoint 5 --file docker-compose.hosted.yml
```

## Container Health Checks (Portainer/Docker)

### View Container Health Status
```bash
# All containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"

# Specific service
docker inspect <container_name> | jq '.[0].State.Health'
```

### Portainer Stack Verification
1. Portainer → Stacks → `<stack-name>` → Containers
2. Verify all containers show `Up (healthy)` or `Up`
3. Check logs for any error patterns

## Common Issues & Troubleshooting

### Backend `/health` Returns 503 or Fails
**Causes:**
- Database not ready (check PostgreSQL health)
- Migration failed (check logs for `alembic_failed_falling_back_to_create_all`)
- Missing required env vars (check `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`)

**Resolution:**
```bash
# Check backend logs
docker logs <backend-container> | tail -100

# Check database connectivity
docker exec <backend-container> pg_isready -h postgres -U "$POSTGRES_USER"

# Verify migrations
docker exec <backend-container> alembic current
```

### AI Gateway `/health` Shows `router_enabled: false`
**Causes:**
- `AI_ROUTER_URL` not set or set to placeholder
- 9Router unreachable
- Network/firewall blocking

**Resolution:**
```bash
# Check AI gateway logs
docker logs <ai-container> | tail -50

# Test 9Router connectivity from backend
docker exec <backend-container> curl -s http://9router:20128/api/health

# Verify AI_ROUTER_URL in env
docker exec <backend-container> env | grep AI_ROUTER
```

### Frontend Returns 502 (Bad Gateway)
**Causes:**
- Frontend container recreated with new IP (nginx proxy cache stale)
- Frontend container not healthy

**Resolution:**
```bash
# Check frontend container IP
docker inspect <frontend-container> | jq '.[0].NetworkSettings.Networks[].IPAddress'

# For hosted: verify nginx proxy manager caches correct IP
# (frontend pins ipv4_address: 172.18.0.14 in compose)

# Restart nginx proxy manager if needed
docker restart npm
```

### PostgreSQL Connection Failures
**Causes:**
- Password mismatch
- Database not initialized
- Connection pool exhausted

**Resolution:**
```bash
# Test connection
docker exec <postgres-container> pg_isready -U "$POSTGRES_USER"

# Check logs
docker logs <postgres-container> | tail -50

# Verify credentials match between postgres and backend
```

## Monitoring & Alerting

### Key Metrics to Watch
- `/health` response time (< 200ms)
- Container restart count (should be 0)
- Memory/CPU usage trends
- Disk space (especially postgres-data, minio-data volumes)

### Discord Notifications
- CI/CD failures → `#ops` / `#incidents`
- Deploy completions → `#updates`
- Runner watchdog alerts → `#incidents`

## Verification Checklist (Post-Deploy)
- [ ] Backend `/health` → 200, status:ok, correct version
- [ ] AI Gateway `/health` → 200, router_enabled: true
- [ ] Frontend `/flutter_bootstrap.js` → 200, valid JS
- [ ] Post-deploy smoke test passes
- [ ] All containers `Up (healthy)`
- [ ] No error patterns in recent logs
- [ ] Key user flows work (login, vehicle list, add service)

## Related Docs
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md)
- [Deploy Runbook](./deploy.md)
- [Post-Deploy Smoke Test](../Deployment-and-Infrastructure/deployment-guide.md#post-deploy-smoke-test-spec)
- [Monitoring](../Deployment-and-Infrastructure/monitoring.md)
