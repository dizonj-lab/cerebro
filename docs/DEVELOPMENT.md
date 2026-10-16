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

## Local AI with Ollama

Both AI features run on your own machine through Ollama. There is no cloud
option in CEREBRO, and a local engine that fails is never replaced by one that
would send your documents elsewhere.

```bash
ollama pull llama3.2          # metadata suggestions
ollama pull nomic-embed-text  # embeddings for search
```

Then create a `.env` beside `docker-compose.yml`:

```bash
CEREBRO_ENRICHMENT_LLM=ollama
CEREBRO_OLLAMA_ENRICHMENT_MODEL=llama3.2   # or whatever `ollama list` shows
CEREBRO_EMBEDDING_PROVIDER=ollama
```

and restart: `make compose-up WEB_PORT=3100`.

### Why the base URL is not localhost

Inside the API container, `localhost` is the container — not your Mac. A
default of `http://localhost:11434` would look configured and reach nothing.
The compose file therefore defaults to `http://host.docker.internal:11434`,
and declares

```yaml
extra_hosts:
  - host.docker.internal:host-gateway
```

so the same name works on Linux, where Docker does not provide it. Running
the API directly with `uvicorn` instead needs no override: `localhost` is
then correct.

### What each setting changes

`CEREBRO_ENRICHMENT_LLM=ollama` adds a **Suggest with local AI** button to the
review screen. It is a button rather than something that runs on upload
because a model on a laptop takes tens of seconds, and an upload must not
hang on it. Deterministic enrichment — the document's own metadata plus
statistics over its text — runs on upload regardless.

The button respects the **AI suggestions** toggle in Settings. Turned off, the
model is not asked and the screen says so.

`CEREBRO_EMBEDDING_PROVIDER=ollama` switches search from lexical matching to a
learned model. **Artifacts registered under the previous provider will stop
being found**: vectors from two providers are different spaces and are never
compared, so anything already registered has to be registered again under the
new one. That is deliberate — comparing across spaces would return confident
nonsense.

### Checking it works

```bash
curl -s http://localhost:11434/api/tags | python3 -m json.tool   # from your Mac
docker compose exec api python -c "import urllib.request; \
  print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags').status)"
```

The second command is the one that matters: it asks from inside the container,
which is where CEREBRO will be asking from.


## Connecting to an Ollama you already run

CEREBRO never starts a daemon and never pulls a model. It asks whatever
daemon it can reach what is installed, and uses that.

If Ollama runs **on the host** (`ollama serve`, or a container that publishes
`11434`), the compose defaults already work: the API reaches
`host.docker.internal:11434`, and `extra_hosts: host-gateway` makes that name
resolve on Linux too. Inside the API container `localhost:11434` is the API
container — that is the mistake this avoids.

If the Ollama container **does not publish its port**, put it on this
project's network and address it by container name:

```bash
docker network connect cerebro_default cerebro-ollama
CEREBRO_OLLAMA_BASE_URL=http://cerebro-ollama:11434 docker compose up -d api
```

Check what CEREBRO can see, from the API's point of view rather than yours:

```bash
docker compose exec api python -c "from app.services.ollama import discover; print(discover(force=True))"
```

Then verify the models actually run, which is not the same as being listed —
a daemon will list a model it cannot load:

```bash
curl -s -X POST localhost:3100/api/ml/probe -b cookies.txt | python3 -m json.tool
```

or press **Verify inference** in GOD MODE, which does the same thing and
shows the model's own words with the latency.

### Two things to expect on first connection

**Reasoning models.** `qwen3` and `deepseek-r1` wrap their deliberation in
`<think>` tags. CEREBRO strips those from answers, never streams them, and
asks the daemon not to produce them (`think: false`). Without that, the
deliberation appears in the chat and makes a JSON reply from enrichment
unparseable.

**A change of embedder orphans vectors.** Provider, model and width travel
with every vector and retrieval filters on all three, so moving from the
384-dimensional hashing fallback to `mxbai-embed-large` (1024) leaves
existing fragments unretrievable until they are re-embedded. That is visible
rather than silent: GOD MODE and `/api/ml/status` report how many fragments
lack a vector for the active model, and **Backfill embeddings** fixes it. The
old vectors are kept, so switching back needs no re-embedding.
