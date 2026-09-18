# CEREBRO — Current State

Last updated: 2026-09-18

## EXPERIENCE FOUNDATION

| Component              | Status     |
| ---------------------- | ---------- |
| Landing                | COMPLETE   |
| Signup                 | COMPLETE   |
| Login                  | COMPLETE   |
| Authentication API     | COMPLETE   |
| PostgreSQL Persistence | COMPLETE   |
| Protected Construct    | COMPLETE   |
| Construct Shell        | COMPLETE   |
| Branding               | PARTIAL — awaiting artwork |

Branding: the supplied logo's copy is applied throughout (tagline *Adaptive
Knowledge and Reasoning Digital Twin*, pillars *Learn · Connect · Reason ·
Recall*), and the brand components are in place. The mark image itself is still
a **placeholder** — the artwork was not available as a file to this environment.
Dropping the real file at `frontend/public/brand/cerebro-mark.svg` completes it
with no code change.

## Verification

| Dimension   | Result               |
| ----------- | -------------------- |
| Engineering | PASS                 |
| Functional  | PASS                 |
| UI/UX       | AWAITING USER REVIEW |
| Regression  | PASS                 |

**Engineering** — Backend: 25 pytest tests green against a real PostgreSQL 16
database. Frontend: `tsc --noEmit` clean, ESLint clean, production build clean.
Kubernetes manifests parse as valid YAML.

**Functional** — 31 Playwright end-to-end tests green in Chromium against the
running stack (Next.js + FastAPI + PostgreSQL), covering work-package TESTs 1–9.

**UI/UX** — Implemented to the design contract and verified programmatically
(WCAG 2.1 A/AA via axe-core on all four pages, no horizontal overflow at 375 /
768 / 1440, no unexpected browser console errors). Visual approval by the
product owner is still outstanding.

**Regression** — No prior functionality existed to regress; the repository
contained only an empty `readme.md` at the start of this work package.

## Test results

| Test                     | Result | Evidence                                              |
| ------------------------ | ------ | ----------------------------------------------------- |
| TEST 1 — Landing         | PASS   | Branding, pillars and both entry points navigate      |
| TEST 2 — Sign-up         | PASS   | Account created; row in PostgreSQL; Argon2id hash     |
| TEST 3 — Duplicate       | PASS   | 409 with a clear message; no second row written       |
| TEST 4 — Login           | PASS   | Session established; redirect to `/construct`         |
| TEST 5 — Invalid login   | PASS   | 401, identical message for unknown email              |
| TEST 6 — Protected route | PASS   | Unauthenticated `/construct` → `/login?next=/construct` |
| TEST 7 — Session         | PASS   | Survives refresh; `/login` bounces to `/construct`    |
| TEST 8 — Logout          | PASS   | Cookie cleared; protected route inaccessible          |
| TEST 9 — UI              | PASS   | axe-core clean; responsive; loading and error states  |

Database evidence at time of writing: 78 user rows, 78 Argon2id hashes,
0 plaintext passwords.

## Infrastructure

| Workload         | Status                                             |
| ---------------- | -------------------------------------------------- |
| PostgreSQL       | RUNNING (local cluster, `cerebro` + `cerebro_test`) |
| cerebro-api      | RUNNING (uvicorn, port 8000)                        |
| cerebro-web      | RUNNING (Next.js, port 3000)                        |
| Kubernetes       | **BLOCKED — not deployable from this environment**  |
| cerebro-worker   | NOT PRESENT (not required by this work package)     |

Kubernetes manifests for namespace `cerebro` exist under `k8s/` and their YAML
is valid, but they have not been applied: the development container has no
Docker daemon and no `kubectl`/cluster, so images cannot be built or deployed
here. Applying them on a machine with a local cluster is the outstanding step.

## Not implemented (deliberately out of scope)

User Profile, Artifact upload/Library, MinIO, AI processing, OCR, speech,
vision, embeddings, Qdrant, Neo4j, Kafka, local LLM, RAG, Recall, Timeline,
Galaxy, What-If, Dashboard analytics. Sidebar entries for these are inert
placeholders.

## Next work package

User Profile + Artifact Ingestion.
