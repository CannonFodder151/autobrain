# Infrastructure Diagrams

## Network topology (Hosted — Oracle Cloud)

```mermaid
graph TD
    CF[Cloudflare DNS\n:443 HTTPS] --> NPM[Nginx Proxy Manager\n:443]
    NPM --> FE[Frontend\n127.0.0.1:8086 → :8080]
    FE -->|/api/* /ws/*| BE[Backend\n:8000]
    FE -->|/ai/*| AI[AI Gateway\n:8001]
    BE --> PG[(PostgreSQL + pgvector\n:5432)]
    BE --> RD[(Redis\n:6379)]
    BE --> MN[(MinIO\n:9000)]
    BE -->|Celery worker+beat\nin-container| RD
    AI -->|market-data\n:8000| RD
    AI -->|market-data\n:8000| PG
    AI --> RTR[9Router\n:20128]
    BE --> RTR
    BE --> DS[Dongle Server\n:8000]
    BE --> HUB[Federation Hub\n:8000]
    BE -->|/api/v1/admin-api/backup| BA[Backup Agent]
    BA --> AB[AutoBrain Backup\n:8080]
    subgraph Oracle_VM[Oracle Cloud VM 152.69.188.133]
        NPM
        FE
        BE
        AI
        PG
        RD
        MN
        DS
        HUB
        BA
        AB
        RTR
        GH[GitHub Actions\nARM64 Runner]
    end
    FW[fw-keeper\nHost Firewall] -.->|:20128 allow\n122.199.30.128/32\n+ 172.18.0.0/16| RTR
    FW -.->|:9001 allow\n122.199.30.128/32| PA[Portainer Agent\n:9001]
```

## Hosted stack services (docker-compose.hosted.yml)

```mermaid
graph LR
    subgraph Stack[autobrain-hosted stack]
        PG[postgres\npgvector/pgvector:pg17]
        RD[redis\nredis:7.2.5-alpine]
        MN[minio\nminio/minio]
        BE[backend\nautobrain-backend:hosted]
        AI[ai\nautobrain-ai:hosted]
        DS[dongle-server\nautobrain-dongle-server:hosted]
        FE[frontend\nautobrain-frontend:hosted]
        HUB[hub\nautobrain-federation-hub:hosted]
        GR[gh-runner\nactions/actions-runner:latest]
        RTR[9router\ndecolua/9router:0.5.55]
        AB[autobrain-backup\nautobrain-backup:hosted]
        BA[backup-agent\nautobrain-backup-agent:hosted]
    end
    PG -.->|volume| PGV[postgres-data]
    RD -.->|volume| RDV[redis-data]
    MN -.->|volume| MNV[minio-data]
    HUB -.->|volume| HV[hub-data]
    RTR -.->|external volume| RTV[9router-data]
    AB -.->|bind| ABC[/data/autobrain-backup/config]
    AB -.->|bind| ABD[/data/autobrain-backup/data]
    BA -.->|bind| BAD[/data/autobrain-backup/agent-data]
    GR -.->|bind| DOCK[/var/run/docker.sock]
    GR -.->|bind| SEC[/run/secrets]
    BE -.->|bind| SEC
    AI -.->|bind| SEC
    DS -.->|bind| SEC
    PG -.->|bind| SEC
    RD -.->|bind| SEC
    MN -.->|bind| SEC
    FE -.->|static IP| NET[172.18.0.14]
    BE -.->|static IP| NET2[172.18.0.15]
```

## Container image graph

```mermaid
graph LR
    BF[docker/backend/Dockerfile] --> AB[ghcr.io/.../autobrain-backend:hosted]
    AF[docker/ai/Dockerfile] --> AAI[ghcr.io/.../autobrain-ai:hosted]
    FF[docker/frontend/Dockerfile] --> AFE[ghcr.io/.../autobrain-frontend:hosted]
    DF[docker/dongle-server/Dockerfile] --> ADS[ghcr.io/.../autobrain-dongle-server:hosted]
    HF[autobrain-federation-hub repo] --> AHB[ghcr.io/.../autobrain-federation-hub:hosted]
    BUF[autobrain-backup repo] --> ABU[ghcr.io/.../autobrain-backup:hosted]
    BAF[autobrain-backup-agent repo] --> ABA[ghcr.io/.../autobrain-backup-agent:hosted]
```

## Dev box topology (Portainer EP6, 10.0.3.39)

```mermaid
graph TD
    Dev[Dev Access] --> FE2[Frontend\n:8080]
    FE2 -->|/api/* /ws/*| BE2[Backend\n:8000]
    FE2 -->|/ai/*| AI2[AI Gateway\n:8001]
    BE2 --> PG2[(PostgreSQL + pgvector)]
    BE2 --> RD2[(Redis)]
    BE2 --> MN2[(MinIO)]
    AI2 --> RTR2[9Router\n10.0.3.17:20128]
    BE2 --> RTR2
```

## Key architectural notes

- **All app containers run non-root**: `read_only: true`, `cap_drop: [ALL]`, `tmpfs` mounts (AUT-1533/CIS hardening).
- **Secret-file pattern (AUT-1533)**: Secrets live in `/data/autobrain/secrets` on host, bind-mounted read-only at `/run/secrets`. `docker/lib-load-secrets.sh` exports `FOO_FILE` → `FOO` at container start. Values never appear in `docker inspect` or `/proc/*/environ`.
- **Unified backend**: API (`:8000`) + Celery worker+beat run in one container (AUT-3153). No separate `worker` service.
- **Stack-local 9Router**: Oracle VM runs its own 9Router instance (`decolua/9router:0.5.55`), published `0.0.0.0:20128` but firewalled to dev egress IP + docker subnet. The corporate 9Router at `10.0.3.17:20128` is NOT reachable from Oracle Cloud.
- **Static IPs**: Frontend `172.18.0.14`, Backend `172.18.0.15` pinned in compose to keep Nginx Proxy Manager's cached IP valid across recreates (AUT-372).
- **External volumes**: `9router-data` is external (preserves provider/API-key config); `postgres-data`, `redis-data`, `minio-data`, `hub-data` are compose-managed.
- **Backup stack**: `autobrain-backup` (web GUI) + `backup-agent` (hourly poller) run as part of the hosted stack.

---

**Related docs:** [`deployment-guide.md`](./deployment-guide.md) | [`ci-cd.md`](./ci-cd.md) | [`server-migration.md`](./server-migration.md) | [`backup-strategy.md`](./backup-strategy.md) | [`monitoring.md`](./monitoring.md) | [`autobrain-deploy-trigger.md`](./autobrain-deploy-trigger.md) | [`security.md`](../Security/security.md)

**Graft usage:** This repo is indexed with Graft (trailhq/Graft). Run `graft map` to orient, `graft ask "<task>"` to find code, `graft grep "<regex>"` for exhaustive search, `graft callers <symbol>` for call graphs, `graft blast --base origin/main` for diff blast radius. See `AGENTS.md` for agent integration.