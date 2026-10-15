# CEREBRO — Current State

Last updated: 2026-10-15 (Phase 3 — Multimodal Ingestion, increment 1)

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

## PHASE 1.5 — PROFILE, PREFERENCES, ACCOUNT

| Component                | Status   |
| ------------------------ | -------- |
| User Profile             | COMPLETE |
| Edit Profile             | COMPLETE |
| User Preferences         | COMPLETE |
| Account settings         | COMPLETE |
| Dashboard integration    | COMPLETE |
| Profile completion       | COMPLETE |
| AI & Privacy settings    | COMPLETE (configuration only — no LLM calls) |

## PHASE 2 — ARTIFACT INGESTION

| Component                   | Status   |
| --------------------------- | -------- |
| Upload + deterministic inspection | COMPLETE |
| Object storage (filesystem) | COMPLETE |
| Object storage (MinIO / S3) | OPT-IN — image reference unresolved |
| Deterministic metadata extraction | COMPLETE |
| Human review + approval gate | COMPLETE |
| Registration with checksum re-verification | COMPLETE |
| Library view                | COMPLETE |

The capability modules are ported from the knowledge pipeline PoC
(`poc/src/`, experiments EXP-INGEST-001..006), so artifacts registered by the
application satisfy the contract the PoC benchmark validated. The port was
checked against the PoC's own benchmark artifact: it reproduces the recorded
SHA-256 of `ART-0001` exactly.

No AI in this phase: `provenance.ai_enrichment` is `null` on every artifact.

## PHASE 3 — MULTIMODAL INGESTION

| Component                              | Status   |
| -------------------------------------- | -------- |
| Extraction adapters (PDF, DOCX, PPTX, text) | COMPLETE |
| Block-level source locations           | COMPLETE |
| Chunking                               | COMPLETE (not yet consumed) |
| Extraction wired into upload           | COMPLETE |
| Knowledge fragments + embeddings       | NOT STARTED |
| Semantic search                        | NOT STARTED |
| AI enrichment                          | NOT STARTED |
| Images / OCR / audio                   | DEFERRED (P2) |

PDF, Word, PowerPoint, plain text and Markdown are uploadable. Extraction is
deterministic — `pypdf`, `python-docx`, `python-pptx`, no AI and no network —
and every block keeps the page, slide or section it came from, so a chunk
built from it later can still point back at the source.

Two refusals are deliberate. A PDF with no text layer is rejected rather than
registered empty: an artifact with no retrievable content is worse than no
artifact, and OCR is a later phase. And a file whose bytes contradict its
extension is rejected, so renaming an image to `.pdf` does not get it treated
as a document.

The extracted blocks are a derived object in the object store, beside the
original bytes and keyed `<storage_key>.extraction.json`. The artifact row
carries only a summary, so a library query does not drag megabytes of
document text with it. The original bytes are stored verbatim, so
registration still re-verifies the checksum against the source rather than
against anything derived.

Images, OCR and audio remain deferred.

## Verification

| Dimension   | Result               |
| ----------- | -------------------- |
| Engineering | PASS                 |
| Functional  | PASS                 |
| UI/UX       | APPROVED             |
| Regression  | PASS                 |

**Engineering** — Backend: 97 pytest tests green against a real PostgreSQL 16
database. Frontend: `tsc --noEmit` clean, ESLint clean, production build clean.
Kubernetes manifests parse as valid YAML.

**Functional** — 49 Playwright end-to-end tests green in Chromium against the
running stack (Next.js + FastAPI + PostgreSQL), covering Phase 1 TESTs 1–9 and
the Phase 1.5 profile, preferences, consent and isolation cases.

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

Database evidence at time of writing: 318 user rows, all Argon2id hashed,
0 plaintext passwords. The Phase 1.5 migration applied over that existing data
without loss.

## Infrastructure

| Workload         | Status                                             |
| ---------------- | -------------------------------------------------- |
| PostgreSQL       | RUNNING (local cluster, `cerebro` + `cerebro_test`) |
| cerebro-api      | RUNNING (uvicorn, port 8000)                        |
| cerebro-web      | RUNNING (Next.js, port 3000)                        |
| Docker Compose   | **VERIFIED** — running on the product owner's machine, 2026-10-15 |
| Kubernetes       | SCHEMA APPROVED — **not yet applied to a cluster**      |
| cerebro-worker   | NOT PRESENT (not required by this work package)     |

The stack is fully containerised: Dockerfiles for both services, Kubernetes
manifests under `k8s/` (namespace `cerebro`), a `Makefile` (`make up`), and a
`docker-compose.yml` as the simpler alternative.

The manifests render with kustomize and pass `kubeconform -strict` against the
Kubernetes 1.31 schemas (`make validate`), and the schema was approved by the
product owner on 18 September 2026.

**Docker Compose runs, with one defect found and fixed.** On 2026-10-15 the
product owner built the images and ran the four-service stack (`postgres`,
`migrate`, `api`, `web`) on macOS with `make compose-up WEB_PORT=3100`.
Sign-up, sign-in and the profile pages worked; **artifact upload did not**, and
had never worked in a container.

The API image did not create `/data/artifacts`, so Docker created the mount
point for the `artifact-data` volume owned by root. The API runs as uid 10001
and could not create the per-owner directory inside it. The resulting
`PermissionError` was unhandled, and FastAPI answers an unhandled exception
with *plain text*, which the web client cannot parse as JSON — so the browser
showed only "Something went wrong."

The image now creates the directory and chowns it, and a storage failure is
reported as a 503 naming storage rather than as a bare 500. Both the
permission mechanism and the 503 are covered by tests.

Running the suite against containers also exposed a race in the e2e logout
helper: it returned on the button click without waiting for the logout request
to finish, so the next navigation could still carry a valid cookie. Fast enough
to pass against a local server, slow enough to fail against containers. It was
a test defect, not a hole in the app — the server redirects correctly for a
missing, empty or invalid cookie — and it was confirmed by delaying the logout
response and reproducing the failure deliberately.

The lesson is recorded because it is the fourth time something was declared
done on schema or local evidence and failed in a container: **the end-to-end
suite had only ever run against a locally started web server, never against
the compose containers.** Upload is the only multipart request in the app, and
the only one that writes to a volume.

**Kubernetes is still unproven.** The manifests render with kustomize and pass
`kubeconform -strict` against the Kubernetes 1.31 schemas (`make validate`),
and the schema was approved on 18 September 2026 — but they have never been
applied to a cluster. Approval covers the design, not a runtime proving;
`make up` on a machine with a cluster remains the outstanding step.

Artifact bytes use the filesystem object store, written to a Docker volume.
MinIO is opt-in and currently has no pullable public image — see
`docs/DEVELOPMENT.md`.

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
