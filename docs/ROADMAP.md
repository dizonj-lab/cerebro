# CEREBRO — Roadmap

Where the system is, and what remains. The C4 model in
`architecture/structurizr/workspace.dsl` carries the same status as tags, so the
diagrams show built elements solid and planned ones pale.

## Legend

| Status      | Meaning                                       |
| ----------- | --------------------------------------------- |
| **Built**   | Implemented, tested, committed                |
| **Partial** | Present but incomplete or unverified          |
| **Planned** | Not started                                   |

## Built

### Experience Foundation (work package 1)

| Item                    | Evidence                                            |
| ----------------------- | --------------------------------------------------- |
| Landing page            | Branding, tagline, four pillars, both entry points  |
| Sign-up                 | Client and server validation, duplicate rejection    |
| Login                   | Loading and error states, anti-enumeration messaging |
| The Construct shell     | Header, user menu, sidebar, welcome workspace        |
| Authentication API      | `/signup`, `/login`, `/me`, `/logout`, `/health`     |
| PostgreSQL persistence  | `users` table, UUID keys, Alembic migration          |
| Argon2id hashing        | No plaintext stored or logged                        |
| Session                 | JWT in an httpOnly `SameSite=Lax` cookie             |
| Protected routes        | Proxy pre-check plus authoritative server validation |
| Design system           | Tokens → primitives → components → pages             |
| Test suites             | 25 backend (real PostgreSQL) + 31 E2E (real browser) |

### Containerisation

| Item                     | Evidence                                          |
| ------------------------ | ------------------------------------------------- |
| Images                   | Dockerfiles for both services, non-root, standalone |
| Kubernetes manifests     | Namespace `cerebro`; schema-validated against 1.31 |
| One-command workflow     | `make up`, `make down`, `make validate`            |
| Docker Compose           | `make compose-up` as the simpler alternative       |
| Same-origin proxy        | No CORS, cookie always first-party, ingress optional |
| Branding                 | Supplied mark in use; logo copy applied product-wide |

## Partial

| Item             | What is missing                                                |
| ---------------- | -------------------------------------------------------------- |
| Kubernetes       | Schema approved and passing `kubeconform -strict`, but never applied and the images never built — no Docker daemon or cluster in the development environment. Approval covers the design, not a runtime proving. |

## Planned

Ordered so each package depends only on the ones above it.

| # | Work package                | Adds                                                        |
| - | --------------------------- | ----------------------------------------------------------- |
| 2 | User Profile + Ingestion    | Profile page; artifact upload; object store (MinIO); `artifacts` table; Library view |
| 3 | Processing pipeline         | `cerebro-worker`; event bus (Kafka); OCR, speech transcription, vision |
| 4 | Semantic search             | Embeddings; vector store (Qdrant); Search view              |
| 5 | Knowledge graph             | Entity and relationship extraction; graph store (Neo4j); Connect |
| 6 | Reasoning                   | Local LLM (Ollama); RAG; Recall view                        |
| 7 | Visualisation               | Timeline; Galaxy                                            |
| 8 | Exploration and analytics   | What-If; Dashboard                                          |

Sidebar entries for packages 2–8 exist in The Construct today as inert
placeholders, so the shape of the product is visible without the functionality.

## Immediate next steps

1. Run `make up` on a machine with Docker and a cluster; report anything that
   fails at runtime. This is the only unproven part of the stack.
2. Begin work package 2 — User Profile and Artifact Ingestion.

Completed: brand artwork supplied and in use; Kubernetes schema approved; UI
approved; `v0.1-construct` tagged.
