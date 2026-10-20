# CEREBRO

**An Adaptive Knowledge and Reasoning Digital Twin.**
Learn · Connect · Reason · Recall

People accumulate knowledge well over a lifetime and recall its details
badly. CEREBRO is built for the second half of that problem: it takes the
documents you have already read — lecture decks, papers, proposals, notes —
and makes them answerable, so that *"which artifact discussed this, and
where?"* has an answer with a citation rather than an afternoon of searching.

It is a personal, local store. Documents stay in the CEREBRO environment, no
AI provider is contacted unless you run one yourself, and nothing enters
retrieval without you approving it.

---

## Getting started

**[INSTALL.md](INSTALL.md)** takes a clean machine to a working CEREBRO and
then walks it end to end — account, upload, review, approve, search, ask.

The short version, with Docker Desktop running:

```bash
git clone -b cerebro-mvp https://github.com/dizonj-lab/cerebro.git
cd cerebro
make compose-up WEB_PORT=3100
```

Then open **http://localhost:3100**.

---

## What it does

```
upload → inspect → extract → review → APPROVE → chunk → embed → retrieve → answer
                                         ↑
                             nothing passes without this
```

- **Ingest** PDF, Word, PowerPoint, Markdown and plain text. Extraction is
  deterministic — `pypdf`, `python-docx`, `python-pptx`, no AI and no network
  — and every block keeps the page or slide it came from.
- **Review** the drafted metadata. Every field shows where its value came
  from: the document's own metadata, a byline it prints, the filename, or
  nothing at all.
- **Approve** to register. This re-verifies the stored bytes against their
  checksum, splits the text into fragments, embeds them, and records the
  provenance of the whole operation.
- **Search** by keyword (PostgreSQL full-text), semantically (exact cosine
  over stored vectors), or both fused by reciprocal rank.
- **Ask** in plain language. Answers are drawn only from your registered
  documents and cite them.
- **See** the library as a galaxy of documents and the concepts connecting
  them, or as a timeline.

## Principles it holds to

These are enforced in code and asserted by tests, not aspirations:

- **Enrichment proposes; it never establishes.** Every field carries its
  method, and only your approval marks anything confirmed.
- **Approval is the only gate into retrieval.** An unapproved artifact can
  never be searched or cited.
- **Unknown stays unknown.** No value is invented to fill a gap. A model's
  suggested topics are dropped unless they appear in the document verbatim,
  and a name in the body is never treated as an author.
- **There is no cloud AI.** A failing local model falls back to deterministic
  enrichment, never to a remote service.
- **Co-occurrence is not a claim.** The galaxy draws documents that share
  concepts; it never asserts an inferred semantic relationship.

## Built with

| Layer | Stack |
| ----- | ----- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind v4 |
| Backend | FastAPI, SQLAlchemy 2, Alembic, Python 3.11 |
| Database | PostgreSQL 16 — full-text search and vectors, no extra datastore |
| Local AI | Ollama (optional): qwen3 for answering, mxbai-embed-large for embeddings |
| Deployment | Kubernetes (namespace `cerebro`), or Docker Compose |

The browser only ever calls the web origin; `/api` is proxied to the backend
so the session cookie stays first-party. React never touches PostgreSQL.

## Tests

```bash
make test-unit        # no database needed
make test-backend     # every backend test; needs PostgreSQL
make test-e2e         # Playwright; both servers must be up
```

Tests run against a real PostgreSQL and a real browser. There are no mocks
for either.

## Documentation

| File | Contents |
| ---- | -------- |
| [INSTALL.md](INSTALL.md) | Installation, and a first run end to end |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pieces fit together |
| [docs/API-CONTRACT.md](docs/API-CONTRACT.md) | Every endpoint and the rules it enforces |
| [docs/DATA-MODEL.md](docs/DATA-MODEL.md) | Tables and relationships |
| [docs/SEARCH.md](docs/SEARCH.md) | Keyword, semantic and hybrid retrieval |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Choices made, and what would justify revisiting them |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development setup, storage, secrets, Ollama |
| [CLAUDE.md](CLAUDE.md) | Conventions, and the traps that cost a debugging cycle |
