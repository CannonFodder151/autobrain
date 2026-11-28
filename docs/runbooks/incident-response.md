# Incident Response Runbook

## Overview
Standard incident classification, escalation, and resolution procedures for AutoBrain.

## Incident Severity Levels

| Severity | Label | Description | Response Time | Escalation |
|----------|-------|-------------|---------------|------------|
| SEV-1 | Critical | Production down, data loss, security breach | Immediate | CTO → CEO → Discord #incidents |
| SEV-2 | Major | Major feature broken, degraded performance | < 1 hour | CTO → Discord #incidents |
| SEV-3 | Minor | Non-critical bug, minor degradation | < 4 hours | Assigned agent → Discord #updates |
| SEV-4 | Low | Cosmetic, documentation, non-urgent | Next business day | Assigned agent |

## Incident Classification

### SEV-1 (Critical)
- Hosted site completely down (`/health` failing)
- Database unavailable or corrupted
- Security breach / data exposure
- Payment processing broken
- All users unable to authenticate

### SEV-2 (Major)
- AI features completely down (9Router + fallbacks failing)
- Single tier down (demo/default) but hosted up
- Major feature broken (e.g., vehicle creation, fuel logging)
- Backup/restore failing
- CI/CD pipeline completely blocked

### SEV-3 (Minor)
- Single AI module degraded
- Non-critical UI bug
- Intermittent performance issue
- Documentation error
- Mobile app build failure

### SEV-4 (Low)
- Typo in documentation
- Missing changelog entry
- Minor UI polish
- Non-blocking test failure

## Response Procedures

### 1. Detection & Triage
```bash
# Automated detection sources:
# - GitHub Actions failure → PR/CI Watchdog creates issue
# - Runner watchdog → Discord #incidents
# - Uptime monitor → Discord #incidents
# - User report → Discord #support / GitHub issue
# - Manual health check → discover issue
```

**First responder actions:**
1. Acknowledge in Discord #incidents with severity
2. Run health checks: `./scripts/post-deploy-smoke.sh <url>`
3. Check container status: `docker ps` / Portainer
4. Check recent deployments: `git log --oneline -10`
5. Check CI/CD status: GitHub Actions runs

### 2. Containment
**SEV-1/SEV-2:**
- If recent deploy: consider rollback (see Rollback section)
- If infrastructure: check Oracle Cloud / Portainer status
- If database: verify backups exist before any action

**SEV-3/SEV-4:**
- Create issue with `bug` label
- Assign to appropriate agent
- Document workaround if exists

### 3. Investigation
```bash
# Check logs (last 100 lines)
docker logs <container> --tail 100

# Follow logs in real-time
docker logs <container> -f

# Check specific error patterns
docker logs <container> | grep -iE "error|exception|fail|timeout"

# Database queries (if needed)
docker exec <postgres> psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT * FROM pg_stat_activity;"
```

### 4. Resolution
- Fix root cause (code, config, infrastructure)
- Test fix in dev → demo → default → hosted order
- Deploy fix following promotion policy
- Verify with smoke test

### 5. Post-Incident
- Create postmortem issue (use template: `docs/Engineering/postmortem-template.md`)
- Document: timeline, root cause, impact, resolution, prevention
- Update runbooks if new failure mode discovered
- Share learnings in Discord #updates

## Rollback Procedures

### Quick Rollback (Portainer)
1. Portainer → Stacks → `<stack>` → Update
2. Select previous image tag / digest
3. `pullImage: true`
4. Deploy
5. Verify health

### Full Rollback (Git + Rebuild)
```bash
# Revert to previous release tag
git checkout <previous-tag>
./scripts/publish-images.sh <previous-tag>
# Then update Portainer stacks
```

### Database Rollback
**Only if migration caused issue AND backup exists:**
```bash
# Stop backend
docker compose stop backend

# Restore from admin backup
docker compose exec backend python -m app.services.backup restore_backup <backup-id>

# Or from off-site backup
# Check backup instance GUI

# Start backend
docker compose up -d backend
```

## Communication

### Discord Channels
| Channel | Purpose |
|---------|---------|
| `#incidents` | SEV-1/SEV-2 active incidents, status updates |
| `#updates` | Resolution notices, deploy confirmations |
| `#ops` | CI/CD failures, runner alerts, deploy notifications |
| `#approvals` | Board approvals needed for out-of-window deploys |

### Status Update Template
```
**INCIDENT: <SEV-N> - <Brief Title>**
**Status:** Investigating / Mitigating / Resolved
**Impact:** <User-facing impact>
**Started:** <Timestamp>
**Latest:** <Current action>
**ETA:** <If known>
```

### Resolution Notice
```
**RESOLVED: <SEV-N> - <Brief Title>**
**Root Cause:** <One sentence>
**Fix:** <What was deployed/changed>
**Postmortem:** <Link to issue>
```

## Escalation Contacts

| Role | Contact | When to Escalate |
|------|---------|------------------|
| On-call Agent | Discord DM | First response |
| CTO | Discord DM | SEV-1, architectural decisions |
| CEO | Discord DM | Business impact, customer-facing SEV-1 |
| DevOps | Discord DM | Infrastructure, Portainer, Oracle Cloud |
| Security Officer | Discord DM | Security incidents |

## Runbook Maintenance
- Review quarterly
- Update after each SEV-1/SEV-2 postmortem
- Test procedures in dev environment

## Related Docs
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md#rollback)
- [Deploy Runbook](./deploy.md)
- [Backup & Restore Runbook](./backup-restore.md)
- [Health Check Runbook](./health-check.md)
- [Postmortem Template](../Engineering/postmortem-template.md)
- [Security Policy](../Security/security.md)
