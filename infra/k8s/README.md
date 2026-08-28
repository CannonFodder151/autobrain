# infra/k8s — quick deploy

```bash
kubectl create namespace autobrain
kubectl -n autobrain create secret generic autobrain-secrets \
  --from-literal=secret-key="$(openssl rand -hex 32)" \
  --from-literal=postgres-user=autobrain --from-literal=postgres-password="$(openssl rand -hex 24)" \
  --from-literal=minio-access-key="$(openssl rand -hex 16)" --from-literal=minio-secret-key="$(openssl rand -hex 24)" \
  --from-literal=redis-password="$(openssl rand -hex 24)"
kubectl apply -f infra/k8s/config.yaml
kubectl apply -f infra/k8s/redis.yaml -f infra/k8s/postgres.yaml -f infra/k8s/minio.yaml
sleep 30
kubectl apply -f infra/k8s/networkpolicy.yaml -f infra/k8s/ai.yaml -f infra/k8s/backend.yaml -f infra/k8s/worker.yaml -f infra/k8s/frontend.yaml
```

`redis-password` is alphanumeric so `REDIS_URL=redis://:$(REDIS_PASSWORD)@host:6379/0` needs no encoding. Re-creating `autobrain-secrets` requires restarting `autobrain-redis` (cmdline arg), `autobrain-backend`, `autobrain-worker`, `autobrain-beat`.

For GitOps use SealedSecrets or external-secrets.
