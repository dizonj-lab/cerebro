# CEREBRO — Installation

**CEREBRO** is an Adaptive Knowledge and Reasoning Digital Twin: it turns
personal knowledge and experiences into a connected, private, searchable
store — Learn · Connect · Reason · Recall.

This document takes a clean machine to a running CEREBRO. There are three
ways to install it; **Docker Compose is the recommended one** and the only
one that needs nothing but Docker.

| Path | When to use it | Needs |
| ---- | -------------- | ----- |
| [Docker Compose](#1-docker-compose-recommended) | Evaluating, demonstrating, marking | Docker Desktop |
| [From source](#2-from-source) | Developing, debugging | PostgreSQL 16, Python 3.11+, Node 22+ |
| [Kubernetes](#3-kubernetes) | The deployment target | A cluster, `kubectl` |

---

## 1. Docker Compose (recommended)

### Prerequisites

Docker Desktop, running. Nothing else — PostgreSQL, the API, the web app and
the database migrations all come up in containers.

### Install

```bash
git clone -b cerebro-mvp https://github.com/dizonj-lab/cerebro.git
cd cerebro
make compose-up WEB_PORT=3100
```

> **The branch matters.** The current project is on `cerebro-mvp`. Cloning
> without `-b cerebro-mvp` gets the default branch, which is far behind.

That one command builds both images, starts PostgreSQL, runs the database
migrations, waits for them to finish, then starts the API and the web app.

Open **http://localhost:3100** and create an account.

> **Why `WEB_PORT=3100` and not 3000?** Port 3000 is the default but is
> commonly taken. Any port works. If you prefer not to retype it, put
> `CEREBRO_WEB_PORT=3100` in a `.env` file at the repository root — Compose
> reads it on its own, and you then just run `make compose-up`. See
> `.env.example` for the variables that file accepts.

### Verify

```bash
docker compose ps
```

Expect `cerebro-api-1` **(healthy)**, `cerebro-web-1` **Up**, and
`cerebro-postgres-1` **(healthy)**. The `migrate` container is *absent* by
design: it runs the migrations, exits, and the API waits for it to have
completed successfully before starting.

Then sign in and open **http://localhost:3100/api/ml/status**. That endpoint
reports what the running build actually is — which models it can see, how
many of your fragments are embedded, and the token budget in force:

```json
"budget": {
  "context_limit": 512,
  "payload_limit": 502,
  "chunk_target_tokens": 350,
  "chunk_overlap_tokens": 50
}
```

`payload_limit` is the quickest way to confirm the image is current. It is
smaller than `context_limit` on purpose — see
[Why two limits](#why-two-limits) below.

### Stop

```bash
make compose-down     # stops everything and removes the database volume
make compose-logs     # tail the logs
```

`compose-down` **deletes your data** along with the volume. To stop without
losing anything, use `docker compose stop`.

---

## 2. From source

For development, where you want a reloading API and the Next.js dev server.

### Prerequisites

PostgreSQL 16, Python 3.11+, Node 22+.

### Database

Create the role **before** the databases, and make it the owner — the order
matters. Since PostgreSQL 15 the `public` schema no longer grants `CREATE`
to everyone, so a database owned by someone else will fail to migrate:

```bash
psql -d postgres -c "CREATE ROLE cerebro LOGIN PASSWORD 'cerebro_dev_password';"
psql -d postgres -c "CREATE DATABASE cerebro OWNER cerebro;"
psql -d postgres -c "CREATE DATABASE cerebro_test OWNER cerebro;"
```

`cerebro_test` is only needed if you intend to run the backend tests.

### Backend

```bash
make backend-venv                      # creates backend/.venv and installs deps
cd backend
.venv/bin/alembic upgrade head         # apply migrations
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Frontend

In a second terminal:

```bash
make frontend-deps                     # installs deps and the test browser
cd frontend
npm run dev
```

The app is on **http://localhost:3000**.

> The browser only ever talks to the **web origin**. `/api` is proxied to the
> backend by a route handler, so the session cookie stays first-party and no
> CORS is involved. Do not point the browser at port 8000 directly.

### Full details

`docs/DEVELOPMENT.md` covers object storage, secrets, the Ollama setup and
the things that are deliberately not verified locally.

---

## 3. Kubernetes

The primary deployment target. Namespace `cerebro`, manifests in `k8s/`.

```bash
make validate     # render and schema-check the manifests (no cluster needed)
make up           # build, load, deploy, wait
make urls         # how to reach it
make status       # workload status
make down         # delete everything, including the database volume
```

Without an ingress controller:

```bash
make port-forward WEB_PORT=3100
```

---

## First run, end to end

From a running CEREBRO to an answer drawn from your own documents. Each step
says what to expect, so a step that goes wrong is obvious at the time rather
than three steps later.

### 1. Create an account

Open **http://localhost:3100** and sign up. The session is a JWT in an
httpOnly cookie, so it is not readable from JavaScript by design — there is
no token to copy and no client-side token store.

You land on the Dashboard at `/construct`. It is empty, and says so.

> If login ever fails, note that CEREBRO returns **one** message for both an
> unknown email and a wrong password. That is deliberate anti-enumeration
> behaviour, not a vague error.

### 2. Add a document

**Ingest** in the sidebar, or `/construct/ingest`. Drop one or more PDFs,
Word documents, PowerPoints or text files onto the drop zone. Several at once
is fine — they arrive as a table of rows rather than one form.

CEREBRO inspects each file as it arrives: it reads the bytes, extracts the
text, and drafts metadata from what the document itself provides. Two
refusals are deliberate and will show here if they apply:

- **The bytes contradict the extension.** The filename is a claim; the bytes
  are the evidence.
- **A PDF has no text layer.** An artifact with no retrievable content must
  not enter the library. Scanned pages need OCR first.

### 3. Review it

Each row opens a **Review artifact** form: title, author, dates, topics,
tags, and so on. Every field shows where its value came from — the
document's own metadata, a byline the document prints, the filename, or
nothing at all.

With a local model running, **Suggest with local AI** fills what it can and
marks those fields as AI-suggested. Two rules hold regardless:

- **Enrichment proposes, it never establishes.** Nothing a model suggests is
  treated as fact until you approve it.
- `created_date` may come **only** from the document's own metadata, and
  `author` only from that or from a byline the document prints on its first
  page. No model may invent either. A name in the body is not an author —
  being mentioned is not evidence of having written it.

Edit anything you disagree with. Unknown stays unknown; there is no
placeholder invented to fill a gap.

### 4. Approve it

Approving is what **registers** the document. Until then it is a draft and is
invisible to search, the galaxy and recollection.

On approval CEREBRO re-verifies the stored bytes against their checksum,
splits the text into fragments that each stay inside the embedding model's
budget, embeds them, and records the provenance of the whole operation —
which splitter, which version, which budget, which model.

The row shows **Registered**. If it instead reports that registration stopped
before completing, nothing was half-written: the document stays unregistered,
no fragments are left behind, and you can retry without re-uploading.

### 5. Find it again

**Library** (`/construct/library`) lists what you have registered.

**Search** (`/construct/search`) is the real test. Three modes:

| Mode | What it does |
| ---- | ------------ |
| Keyword | PostgreSQL full-text, GIN index |
| Semantic | Exact cosine over the stored vectors |
| Hybrid | Both, fused by reciprocal rank (k=60) |

Semantic search only returns anything if your fragments were embedded by the
model currently in use — see [Why search can go
quiet](#why-search-can-go-quiet) below.

### 6. Ask it a question

**Assisted Recollection** sits beside the search results, and also on the
Dashboard and the Galaxy. Ask in plain language: *"what did the proposal say
about retention?"*

The answer is drawn only from your registered documents and cites them with
`[1]`, `[2]` markers that map to the passages listed beneath. If the
documents do not answer the question, it says so and tells you what they are
about instead — it will not answer from the model's general knowledge, however
confident the model is.

This needs a local answering model. Without one you still get the passages,
which stand on their own; there is no cloud fallback.

### 7. See the shape of it

- **Galaxy** (`/construct/galaxy`) — documents and the concepts connecting
  them, draggable and rotatable. Edges carry their evidence: click one and it
  names the documents it rests on. CEREBRO draws co-occurrence and never
  claims an inferred semantic relationship.
- **Timeline** (`/construct/timeline`) — documents across time, sized by page
  count and coloured by category.
- **Performance** (`/construct/performance`) — what each operation actually
  cost, measured rather than estimated.

Collections, Tags and Agents in the sidebar are placeholders for later work
and are deliberately inert.

### 8. Check the machinery

`/api/ml/status` (signed in) is the single place that reports what the system
is really doing: which models it can see, how many of your fragments are
embedded under the model in use, how many are missing, and the token budget
in force. It is the first thing to read when something behaves unexpectedly.

---

## Local AI (optional)

CEREBRO works without any AI model installed. With [Ollama](https://ollama.com)
running it will additionally suggest metadata, answer questions over your
library, and produce learned embeddings for semantic search.

```bash
make models          # show what CEREBRO can see, and what it would use
make models-pull     # pull the models it prefers
```

The defaults are **qwen3** for answering and enrichment, and
**mxbai-embed-large** (1024 dimensions) for embeddings.

### Inside a container, `localhost` is the container

This is the single most common setup mistake. `localhost:11434` inside the API
container is the *container*, not your machine. Compose therefore points
CEREBRO at `host.docker.internal:11434`, with `extra_hosts: host-gateway` for
Linux parity. If registration reports *"Could not reach Ollama"*, that is a
reachability problem and not a model problem — `docs/DEVELOPMENT.md` has the
details, including how to connect to an Ollama you already run elsewhere.

### There is no cloud AI

By design. If a local model fails, CEREBRO falls back to deterministic
enrichment — never to a remote service. No document is sent to an external AI
provider.

---

## Running the tests

```bash
make test-unit        # no database needed (extraction, chunking, token budget)
make test-backend     # every backend test; needs PostgreSQL on :5432
make test-e2e         # Playwright; both servers must be up
```

Tests run against a real PostgreSQL and a real browser — there are no mocks
for either.

Run the end-to-end suite against the **Compose containers**, not a locally
started `next start`. The two genuinely differ: upload is the only multipart
request and the only write to a mounted volume, and it was once broken in
containers while green locally.

---

## Configuration

Every setting has a working default for local use. `.env.example` lists the
variables and is the source of truth; the ones worth knowing:

| Variable | Purpose |
| -------- | ------- |
| `CEREBRO_WEB_PORT` | Port the web app is published on (default 3000) |
| `CEREBRO_DATABASE_URL` | PostgreSQL connection string |
| `CEREBRO_JWT_SECRET` | Session signing key. **Required outside development**, 32+ characters — the API refuses to start without it |
| `CEREBRO_OLLAMA_BASE_URL` | Where to reach Ollama (`host.docker.internal:11434` in containers) |
| `CEREBRO_EMBEDDING_PROVIDER` | `auto` (default), `ollama`, or `hashing` |
| `INTERNAL_API_BASE_URL` | The proxy and server-render target, read at **runtime** |

Two traps worth stating plainly:

- `NEXT_PUBLIC_API_BASE_URL` is inlined at **build** time and must stay empty
  for containers. Setting it in a Deployment does nothing.
- Never proxy `/api` with Next's `rewrites()`. Rewrite destinations resolve at
  build time and get baked into the standalone server bundle, so a container
  ignores its runtime environment and proxies to the wrong host. This shipped
  once and broke signup in Docker; `npm run check:runtime-config` now fails
  the image build if it returns.

The embedding model, vector width, context limit, chunk size and overlap are
also editable per user in **Settings → Embedding**, with no restart.

---

## Why two limits

An embedding model's context has to hold the model's own special tokens
(`[CLS] … [SEP]`) as well as your text, so the text's share — the
**payload limit** — is smaller than the context. Measuring a chunk against
the context instead let a chunk sized at exactly the context through, and the
daemon refused it as *"input length exceeds the context length"*.

So chunks are cut to `payload_limit` (502 for a 512-token model), the check
sits immediately before every request to the daemon, and an input that is
somehow still oversized is **split and recombined** rather than truncated or
dropped. `/api/ml/status` reports both numbers.

---

## Troubleshooting

**`localhost refused to connect`** — the web container is on a different port
than you are asking for. `docker compose ps` shows the real mapping. If you
started Compose directly rather than through `make`, `CEREBRO_WEB_PORT` may
not have been passed, so the app came up on 3000.

**Upload fails with "Something went wrong"** — a volume mounted over a path
absent from the image is created owned by root, while the API runs as uid
10001, so writes fail with a `PermissionError`. The image creates and chowns
the directory itself; if you have changed the Dockerfile or the volume, check
that. FastAPI returns plain text for an unhandled exception, which is why the
browser shows only that sentence.

**An upload is refused** — two refusals are deliberate: when the bytes
contradict the file extension (the filename is a claim, the bytes are the
evidence), and when a PDF has no text layer (an artifact with no retrievable
content must not enter the library).

**"Registration stopped before completing: Could not reach Ollama"** — a
reachability problem, not a model problem. Inside a container `localhost` is
the container; see [Local AI](#local-ai-optional). Registration without a
local model works fine — this only appears once one is configured.

**The answer shows the model thinking** ("We are given a question…", "Key
rules:…") — an old image. Reasoning models deliberate in prose when their
`<think>` tags are turned off; CEREBRO strips that at the daemon boundary.
Rebuild to pick it up.

**Login does not say which field was wrong** — deliberate. One message covers
unknown-email and wrong-password alike; it is anti-enumeration behaviour with
a test asserting it.

### Why search can go quiet

**Semantic search returns nothing after changing the embedding model** —
expected, and recoverable. Provider, model and width travel with every vector
and search matches on all three, so documents embedded under the old model
drop out of semantic search until they are embedded under the new one. They
remain in your library and remain findable by keyword; nothing is lost.

`/api/ml/status` reports how many fragments are missing a vector for the
model currently in use, and `POST /api/ml/embeddings/backfill` embeds them
without re-uploading or re-approving anything.

The same applies the first time you install a local model: documents
registered while no model was running were embedded by the deterministic
fallback, and need the same backfill to become semantically searchable.

---

## Documentation

| File | Contents |
| ---- | -------- |
| `docs/DEVELOPMENT.md` | Full development setup, storage, secrets, Ollama |
| `docs/ARCHITECTURE.md` | How the pieces fit together |
| `docs/API-CONTRACT.md` | Every endpoint, and the rules each enforces |
| `docs/DATA-MODEL.md` | Tables and relationships |
| `docs/SEARCH.md` | Keyword, semantic and hybrid retrieval |
| `docs/DECISIONS.md` | Choices made, and what would justify revisiting them |
| `CLAUDE.md` | Conventions and the traps that cost a debugging cycle |
