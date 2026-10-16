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
| Knowledge fragments + embeddings       | COMPLETE |
| Search API                             | COMPLETE |
| Search UI                              | NOT STARTED (needs a work package) |
| Metadata enrichment (deterministic)    | COMPLETE |
| Metadata enrichment (local LLM)        | COMPLETE — untested against a live Ollama |
| Open the original document             | COMPLETE |
| Light / dark appearance                | COMPLETE |
| Dashboard                              | COMPLETE — against the approved reference |
| Knowledge Galaxy (P0)                  | COMPLETE |
| Knowledge Timeline                     | COMPLETE |
| Assisted Recollection chat (P2)        | COMPLETE — grounded, local model optional |
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

Registering an artifact chunks its extracted text into knowledge fragments,
embeds each one, and makes it searchable: USER -> ARTIFACT -> KNOWLEDGE
FRAGMENT -> SOURCE LOCATION. Approval is the only gate into retrieval, so an
unapproved artifact can never be searched. The step is idempotent by content
hash, so a retry adds what is missing and duplicates nothing.

Embeddings are `float4[]` columns with brute-force cosine behind a
`VectorIndex` interface; pgvector is not available in the target PostgreSQL.
Vectors are L2-normalised on write, so similarity is a dot product.

Two providers, both local. `hashing` is the default: deterministic, offline,
384 dimensions, and what the tests use — it is a hashing trick over words, so
it finds lexical overlap, not meaning, and is not presented as semantic
search. `ollama` (nomic-embed-text) is a learned model on the user's own
machine, opt-in via `CEREBRO_EMBEDDING_PROVIDER=ollama`. **There is no cloud
provider**, and a failing local provider does not fall back to one: it refuses
registration and says why, because a different provider writes a different
vector space and a cloud one would send content the user never consented to
send. Provider, model and dimensions are stored with every vector and search
filters on all three, so vectors from two spaces are never compared.

A fragment scoring zero or below is not returned. An unrelated passage
offered as a weak match is an unrelated passage offered as evidence.

The search API is done; there is no search UI yet. The sidebar Search entry
stays inert until a work package covers it.

### Bulk ingestion

`/construct/ingest` offers one document or several. A batch uploads up to 25
files in one request and lands as a table, a row per file, with title, topics
and tags editable in place and prefilled by the same enrichment a single
upload runs.

A batch is a set of independent files. One unreadable PDF costs the user that
file and nothing else: the response reports every file, refusals are named in
the same words a single upload uses, and the rest of the batch is accepted.

Rows can be enriched by the local model, singly or all at once, from the
same endpoint the single form uses. A batch runs **one row at a time**: a
model on a laptop takes tens of seconds each, and parallel requests would
only queue inside Ollama while making progress impossible to follow.

**There is no bulk shortcut past review.** Registering a row — one at a time
or the whole table — runs the identical approval path: checksum
re-verification, then chunking and embedding, with `field_methods` marked
`human_confirmed`. Rows left alone stay drafts and reach neither search nor
the Galaxy. The end-to-end test registers a batch and then searches for it,
because that is the proof the pipeline ran rather than a status being set.

### Metadata enrichment

The review form arrives filled in, from three kinds of evidence in descending
order of authority:

1. **What the document asserts about itself** — PDF `/Info`, Office core
   properties. Method `document_metadata`.
2. **A local language model**, if one is configured and the user asks for it.
   Method `ai_suggested`.
3. **Statistics over the document's own words** — keyphrases for topics and
   tags, language detection, and a verbatim quote of the opening as a
   description. Methods `keyphrase_extraction`, `language_detection`,
   `extracted_opening`.

The order is load-bearing: a model can never overwrite what the file itself
asserts, and the statistical fallbacks only fill what is still empty.

Four rules constrain it:

* **People, organizations and projects come only from a model.** Telling a
  person from a company needs knowledge of the world, not word counts, so the
  statistical engine never proposes them — and the model's suggestions are
  dropped unless the document contains them verbatim. An invented person is
  the worst thing enrichment could produce.
* **`author` and `created_date` come only from document metadata.** They are
  claims about the world that reading the text cannot establish, so no
  engine — statistical or generative — may propose them.
* **A model's topics and tags are checked against the document** and dropped
  unless they appear in it verbatim. The number dropped is recorded.
* **Nothing is padded.** A document with no recurring subject matter gets no
  topics, and an unclear language is left blank. A list filled out to look
  thorough is fabrication.
* **Recurrence is the evidence, and names lead the tags.** A term must repeat
  before it can be a topic or a tag, and words the document capitalises are
  preferred — frequency alone surfaced words like "driven" and "represents",
  which are true of the text and useless as tags.
* **Suggestions are drafts.** Each field shows how it was arrived at, and
  only approval marks it `human_confirmed`.

`provenance.ai_enrichment` stays `null` unless a model actually contributed,
so the field keeps meaning "AI touched this". Deterministic enrichment is
recorded separately under `provenance.enrichment`.

The local model is **a button on the review screen, not part of upload**: a
model on a laptop takes tens of seconds and an upload must not hang on it. It
honours the AI suggestions toggle in Settings, and says so plainly when it is
switched off, unconfigured or unreachable. There is no cloud engine, and a
failing local engine falls back to deterministic enrichment rather than to
anything remote.

**Untested against a live Ollama.** The engine's response handling, grounding
guard and unreachable path are covered by tests, but no Ollama daemon was
reachable from the environment this was built in. See `docs/DEVELOPMENT.md`
for setup, including why the base URL inside a container cannot be
`localhost`.

### Opening the original

The Library and the review screen both link to the uploaded file. The media
type is derived from the artifact's extension, never from the `content_type`
the client supplied at upload — otherwise a file uploaded as `text/html`
would be served back as HTML from the application's own origin. PDFs and text
open inline; Office documents download, since no browser renders them.
Filenames are sanitised before going into a `Content-Disposition` header.

### Appearance

Light, dark, or follow the operating system, chosen in Settings and stored on
the account so it follows the user between machines. The browser keeps a copy
so the first paint is correct rather than flashing the wrong theme.

Components never ask which theme is active: the design tokens re-point, and
the components keep using the tokens. `--color-accent-ink` was added for text
placed on the accent, because the dark theme's accent is light and white on it
would fail contrast.

Every dark pair was checked against WCAG AA on all four surfaces — the lowest
is `ink-subtle` on `surface-subtle` at 5.54:1, against a 4.5:1 requirement —
and axe-core runs over the dark theme in the end-to-end suite. A dark palette
that fails contrast is worse than none: it looks considered and is not.

### Dashboard

Built to the approved reference at `docs/design/cerebro-dashboard-reference.png`,
in both themes. One `GET /api/dashboard` call fills every panel, so the page
does not fan out on load, and nothing on it calls a language model.

Only registered artifacts count as knowledge. An artifact awaiting review
appears in Recent Ingestions, because the user has to act on it, but it is not
counted as a document, a fragment or a topic.

Three gaps are shown as such rather than filled with invented data:

* **Projects do not exist.** The Personal/Project selector offers Project and
  disables it, instead of relabelling personal data.
* **No storage quota exists.** Storage shows bytes used and says "No quota
  set"; a percentage would need a denominator we would have to invent.
* **Notifications have no backend.** The bell renders as unavailable and never
  carries a badge, which would be a fabricated count.

The Knowledge Map draws topics joined by the documents that carry both. That
is co-occurrence, the only relationship the data supports, and the caption
says so — it is not a semantic graph. Assisted Recollection is the same
evidence: the user's own topics with the documents behind them, not generated
recommendations. Search and Galaxy have no routes yet, so those controls stay
placeholders per CLAUDE.md.

Charts are inline SVG. The project has no charting library, and a donut and a
bar strip do not justify adding one that would then need theming and bundling.

### Knowledge Galaxy and Timeline

`/construct/galaxy`, built to the approved reference. Clusters are topics a
human confirmed on registered artifacts; opening one fetches its fragments,
each resolving to artifact, fragment and source location. Details are fetched
per node and cached, so the whole graph is never loaded.

**No edge is a verified semantic relationship, and none is presented as one.**
Cluster edges are co-occurrence — a registered document carries both topics —
and the panel says exactly that for every relationship. Relevance is words
("Highly Related", "Related", "Potential Connection"), never a percentage
posing as certainty. People appear only where a human confirmed them; none are
inferred.

Timeline dates are the date the document states, or the date it was
registered, and which one is always shown. No date is inferred. The axis has
two levels — years as milestones, months beneath — and each month states how
many artifacts fall in it rather than leaving a bar to be read. Cards preview
the document's own opening, quoted, so a card can be checked against its
source.

Galaxy and Timeline share one column, so the Timeline is as wide as the
Galaxy and both grow when the details panel collapses; the panel is a column
beside them rather than above the Timeline.

Rendered as SVG: the node count is capped server-side at a couple of dozen,
which SVG handles comfortably while keeping nodes focusable and hoverable
without custom hit-testing. The layout is a deterministic radial arrangement,
not a force simulation, so there is no animation loop behind the view. If the
caps are raised past a few hundred nodes, `GalaxyCanvas` is the piece to
replace — `layout.ts` is already separate for that.

Nothing on the screen calls a language model, including on hover.

Known gaps: the Assisted Recollection chat (P2) is not built — no chat or RAG
service exists yet. Search, Timeline, Collections, Tags and Agents in the
sidebar still have no routes.

## Verification

| Dimension   | Result               |
| ----------- | -------------------- |
| Engineering | PASS                 |
| Functional  | PASS                 |
| UI/UX       | APPROVED             |
| Regression  | PASS                 |

**Engineering** — Backend: 184 pytest tests green against a real PostgreSQL 16
database. Frontend: `tsc --noEmit` clean, ESLint clean, production build clean.
Kubernetes manifests parse as valid YAML.

**Functional** — 58 Playwright end-to-end tests green in Chromium against the
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
