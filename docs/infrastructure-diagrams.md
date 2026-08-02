# Infrastructure Diagrams

## Network topology (production)

```
                 Internet
                    │ :80 (HTTPS via LB/TLS)
                    ▼
              ┌───────────┐
              │   nginx   │
              └─┬──────┬──┘
                │      │
        ┌───────┘      └───────┐
        ▼                      ▼
   /api /ws                /ai
   backend:8000          ai:8001
        │
   ┌────┼────────────┐
   ▼    ▼            ▼
postgres redis     minio
 (5432)  (6379)     (9000)
        │ (broker)
        ▼
   celery worker
   celery beat
```

## Container image graph

```
docker/backend/Dockerfile ──► autobrain-backend   (API + migrations)
docker/ai/Dockerfile      ──► autobrain-ai        (inference gateway)
docker/worker/Dockerfile  ──► autobrain-worker    (celery worker + beat)
docker/frontend/Dockerfile──► autobrain-frontend  (Flutter web → nginx)
```

## K8s deployment graph

```
ingress ──► autobrain-backend:8000 (2 replicas)
         ──► autobrain-ai:8001
         ──► autobrain-frontend:80
autobrain-backend ──► autobrain-postgres / autobrain-redis / autobrain-minio
autobrain-worker, autobrain-beat ──► autobrain-redis, autobrain-postgres
```
