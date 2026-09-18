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
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
INTERNAL_API_BASE_URL=http://127.0.0.1:8000
```

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

## Use `localhost`, not `127.0.0.1`

They are different cookie hosts and different CORS origins. Mixing them makes
sign-in fail with a CORS error and no session cookie. The API's allowed origin
is `http://localhost:3000` by default (`CEREBRO_CORS_ORIGINS`).

## Kubernetes

```bash
docker build -t cerebro-api:0.1.0 backend
docker build -t cerebro-web:0.1.0 frontend
kubectl apply -k k8s/
```

Set a real JWT secret before anything shared:

```bash
kubectl -n cerebro create secret generic cerebro-api \
  --from-literal=CEREBRO_JWT_SECRET="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

The manifests have not been applied from the development container — it has no
Docker daemon and no cluster. See `docs/CURRENT-STATE.md`.
