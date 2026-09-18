# CEREBRO on Kubernetes

Namespace `cerebro`. Three workloads: `cerebro-web`, `cerebro-api`, PostgreSQL.

## Quick start

```bash
make up            # build images, load them into the cluster, deploy, wait
make port-forward  # http://localhost:3000
```

That is a complete, working deployment — sign-in included. **No ingress
controller is required:** the web pod proxies `/api` to the API service
(`frontend/next.config.ts`), so the browser only ever sees one origin.

## What gets created

| Resource                      | Notes                                          |
| ----------------------------- | ---------------------------------------------- |
| `StatefulSet/cerebro-postgres`| PostgreSQL 16, 5Gi PVC, headless Service       |
| `Deployment/cerebro-api`      | FastAPI; init container runs `alembic upgrade head` before traffic |
| `Deployment/cerebro-web`      | Next.js standalone server                      |
| `Ingress/cerebro`             | **Optional** — only for `http://cerebro.localhost` |
| Two `Secret`s, one `ConfigMap`| Development values; replace before sharing     |

## Images

Both are built locally and referenced with `imagePullPolicy: IfNotPresent`, so
nothing is pulled from a registry. How a locally built image reaches the cluster
depends on the distribution, which `scripts/k8s-load-images.sh` handles:

| Distribution              | Behaviour                      |
| ------------------------- | ------------------------------ |
| Docker Desktop, Rancher   | Shares the daemon — nothing to do |
| kind                      | `kind load docker-image`       |
| minikube                  | `minikube image load`          |

`ImagePullBackOff` almost always means the cluster cannot see the local image.

## Optional ingress

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/cloud/deploy.yaml
# then open http://cerebro.localhost
```

Browsers resolve `*.localhost` to loopback, so no `/etc/hosts` entry is needed.

## Migrations

An init container on `cerebro-api` runs `alembic upgrade head` before the API
serves traffic. It is idempotent, so restarts are safe. This is correct at
`replicas: 1`; running more than one replica should move it to a `Job` so two
pods cannot migrate concurrently.

## Secrets

`cerebro-postgres` holds the database credentials, `cerebro-api` holds
`CEREBRO_JWT_SECRET` and `CEREBRO_DATABASE_URL`. Both carry development values
in git. Replace them before any shared deployment — see `docs/DEVELOPMENT.md`.
The API will not start outside development with a default or short JWT secret.

## Validation

```bash
make validate   # renders with kustomize, schema-checks against Kubernetes 1.31
```

## Status

These manifests are **rendered and schema-validated but never applied**: the
environment they were written in has no Docker daemon and no cluster. Structural
errors are ruled out; runtime behaviour is not. Report anything that fails on a
real cluster.
