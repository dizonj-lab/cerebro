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
| Branding               | COMPLETE   |

Branding: complete. The supplied artwork is in at
`frontend/public/brand/cerebro-mark.png`, cropped from the master lockup with
its white matte removed so it renders on any surface, and the logo copy
(tagline *Adaptive Knowledge and Reasoning Digital Twin*, pillars *Learn ·
Connect · Reason · Recall*) is applied throughout.

## Verification

| Dimension   | Result               |
| ----------- | -------------------- |
| Engineering | PASS                 |
| Functional  | PASS                 |
| UI/UX       | APPROVED             |
| Regression  | PASS                 |

**Engineering** — Backend: 25 pytest tests green against a real PostgreSQL 16
database. Frontend: `tsc --noEmit` clean, ESLint clean, production build clean.
Kubernetes manifests parse as valid YAML.

**Functional** — 31 Playwright end-to-end tests green in Chromium against the
running stack (Next.js + FastAPI + PostgreSQL), covering work-package TESTs 1–9.

**UI/UX** — Approved by the product owner on 18 September 2026. Also verified
programmatically: WCAG 2.1 A/AA via axe-core on all four pages, no horizontal
overflow at 375 / 768 / 1440, and no unexpected browser console errors.

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
| Kubernetes       | SCHEMA APPROVED — **not yet applied to a cluster**      |
| cerebro-worker   | NOT PRESENT (not required by this work package)     |

The stack is fully containerised: Dockerfiles for both services, Kubernetes
manifests under `k8s/` (namespace `cerebro`), a `Makefile` (`make up`), and a
`docker-compose.yml` as the simpler alternative.

The manifests render with kustomize and pass `kubeconform -strict` against the
Kubernetes 1.31 schemas (`make validate`), and the schema was approved by the
product owner on 18 September 2026.

They have still **never been applied and the images have never been built**:
this environment has no Docker daemon and no cluster. Approval covers the
design, not a runtime proving — `make up` on a machine with Docker and a
cluster remains the outstanding step.

An ingress controller is no longer required. The web pod proxies `/api` to the
API service, so `make port-forward` is a complete working deployment;
`k8s/40-ingress.yaml` is optional and only provides the `cerebro.localhost`
hostname.

## Not implemented (deliberately out of scope)

User Profile, Artifact upload/Library, MinIO, AI processing, OCR, speech,
vision, embeddings, Qdrant, Neo4j, Kafka, local LLM, RAG, Recall, Timeline,
Galaxy, What-If, Dashboard analytics. Sidebar entries for these are inert
placeholders.

## Release

Tagged `v0.1-construct` on 18 September 2026, following UI approval.

## Next work package

User Profile + Artifact Ingestion. See `docs/ROADMAP.md`.
