# CEREBRO — Development

## Prerequisites

PostgreSQL 16, Python 3.11+, Node 22+.

## Database

Create the role **before** the databases, and make it the owner. Order matters:
since PostgreSQL 15 the `public` schema no longer grants `CREATE` to everyone,
so a database owned by someone else makes `alembic upgrade head` fail with
`permission denied for schema public`.

```bash
psql -c "CREATE ROLE cerebro WITH LOGIN PASSWORD 'cerebro_dev_password';"
createdb -O cerebro cerebro
createdb -O cerebro cerebro_test
```

Run these as a superuser (on most installs, `sudo -u postgres <command>`).

Verify before going further:

```bash
PGPASSWORD=cerebro_dev_password psql -h localhost -U cerebro -d cerebro -c "SELECT current_user;"
```

## Backend

```bash
cd backend
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Tests (these use the real `cerebro_test` database, not a stub):

```bash
cd backend && source .venv/bin/activate && pytest -q
```

## Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

`frontend/.env.local`:

```
INTERNAL_API_BASE_URL=http://127.0.0.1:8000
```

The browser calls `/api` on the web origin and Next.js proxies it to the API, so
there is no browser-visible API URL to configure and no CORS to get wrong.

Checks: `npm run typecheck`, `npm run lint`, `npm run build`.

## End-to-end tests

Both servers must be running first. The suite drives a real browser against the
real stack.

```bash
cd frontend && npm run test:e2e
```

If the environment already provides Chromium, point Playwright at it instead of
downloading a build:

```bash
CHROMIUM_PATH=/opt/pw-browsers/chromium npm run test:e2e
```

## Containers

Two paths. Kubernetes is the primary target; compose is the quicker one.

### Kubernetes

```bash
make up          # build images, load them into the cluster, deploy, wait
make port-forward
```

Then open <http://localhost:3000>. If that port is taken, use
`make port-forward WEB_PORT=3100`. No ingress controller needed: the web pod
proxies `/api` to the API service, so a port-forward is a complete deployment.

Optional friendlier hostname, if you have ingress-nginx:

```bash
kubectl apply -f k8s/40-ingress.yaml   # already included in `make deploy`
# open http://cerebro.localhost
```

Other targets: `make status`, `make logs`, `make down`, and `make validate`
(renders the manifests and schema-checks them without a cluster).

### Docker Compose

```bash
make compose-up      # or: docker compose up --build
```

Open <http://localhost:3000>. `make compose-down` removes the database volume.

### Port already in use

3000, 8000 and 5432 are all commonly taken — OpenWebUI and other Next.js
projects sit on 3000, and a host PostgreSQL on 5432. Override per run:

```bash
make compose-up WEB_PORT=3100        # then open http://localhost:3100
make port-forward WEB_PORT=3100      # the Kubernetes equivalent
make test-e2e WEB_PORT=3100
```

Or set them once, which compose reads automatically:

```bash
cp .env.example .env                 # then edit CEREBRO_WEB_PORT etc.
```

Only the host side of the mapping changes. **No image rebuild is needed**: the
browser reaches the API through the web origin, not a hard-coded port. Verified
by running the full end-to-end suite against port 3100 with an unchanged
build — 31/31.

### Object storage

By default artifact bytes go to a Docker volume through the filesystem backend.
That needs no extra container and is the backend the test suite covers.

MinIO is opt-in:

```bash
CEREBRO_STORAGE_BACKEND=s3 docker compose --profile minio up -d --build
```

MinIO images are no longer anonymously pullable. Checked 2026-10-15:

| Reference                   | Result                          |
| --------------------------- | ------------------------------- |
| `minio/minio`               | 404 on Docker Hub — repo gone   |
| `minio/mc`                  | 404 on Docker Hub — repo gone   |
| `quay.io/minio/minio`       | 401 unauthorized                |
| `bitnami/minio`             | repo exists, **0 tags**         |
| `bitnamilegacy/minio`       | 1027 tags, newest `2025.7.23-debian-12-r5`, amd64 + arm64 |

So `CEREBRO_MINIO_IMAGE` has no default and the profile refuses to start
without one. `bitnamilegacy/minio` is the only verified-pullable option, but
Bitnami's image uses different paths and entrypoint conventions, so the service
definition needs adjusting for it — that has not been done or tested.

None of this blocks anything: the filesystem backend is the default and the
one the test suite covers. The same note applies to `k8s/15-minio.yaml`.

### Secrets

The committed manifests carry development values. Replace them before anything
shared:

```bash
kubectl -n cerebro create secret generic cerebro-api \
  --from-literal=CEREBRO_JWT_SECRET="$(openssl rand -hex 32)" \
  --from-literal=CEREBRO_DATABASE_URL="postgresql+psycopg://cerebro:<pw>@cerebro-postgres:5432/cerebro" \
  --dry-run=client -o yaml | kubectl apply -f -
```

The API refuses to start outside development unless `CEREBRO_JWT_SECRET` is at
least 32 characters and not the built-in default.

### Not verified here

The images have never been built and the manifests have never been applied: the
development container has no Docker daemon and no cluster. They are rendered and
schema-validated against Kubernetes 1.31 (`make validate`), which catches
structural errors but not runtime ones. See `docs/CURRENT-STATE.md`.
