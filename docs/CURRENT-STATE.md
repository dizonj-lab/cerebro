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

### Chunking and embeddings

Chunks target roughly 500 tokens with 75 of overlap, sized in characters —
2000 and 300 at the four-characters-per-token English average — because
characters are what the splitter can count exactly. Token figures are
labelled estimates everywhere they appear; the only exact counts CEREBRO has
are the ones a daemon reports after a generation. Empty chunks and duplicates
are dropped, so a slide footer repeated across 29 pages costs one vector
rather than 29. The splitter's name, version and budget are recorded on the
artifact's provenance.

Embeddings go to Ollama in one batched request (`/api/embed`) rather than one
call per chunk, which is what made registering a real document feel broken:
a 29-page PDF is roughly 90 chunks and so was roughly 90 round trips. A
daemon too old for that endpoint answers 404, and the one-at-a-time path is
still there for it.

### Local models

CEREBRO discovers what the local Ollama daemon has rather than requiring it to
be named in configuration. One client (`app/services/ollama.py`) asks the
daemon for its models and picks from what is installed: a small
instruction-following model to answer with, a purpose-built embedder to embed
with. It tries the configured URL, then `host.docker.internal`, then
localhost, because inside a container `localhost:11434` is the container.

Embeddings, enrichment and answering all default to `auto`. `off` pins the
deterministic path, which is what the test suite uses so that no test depends
on whether a daemon is running on the machine running it. There is still no
cloud path, and a failing local model never becomes one.

Ask CEREBRO answers by streaming: the sources arrive first, then the words as
the model produces them, then a summary with the daemon's own token counts. A
citation to a passage that was not retrieved is removed from the answer — a
model citing `[7]` of six passages has cited nothing — and the citations that
survive are what the response reports. With nothing retrieved, no model is
called at all and the answer is "Insufficient evidence...".

`/api/ml/status` reports what is installed, what is selected, whether the
active embedder is pretrained or the deterministic fallback, the retrieval
algorithms, and the last operations with their durations and token counts.
`/api/ml/embeddings/backfill` embeds fragments that have no vector for the
active model, which is what makes `auto` safe: a change of embedder orphans
vectors rather than deleting them, and the gap is visible and fixable instead
of showing up as search quietly returning nothing.

Reasoning models are handled: `qwen3` and `deepseek-r1` deliberate inside
`<think>` tags, which is stripped from answers, never streamed, and switched
off at the daemon where supported. Left in, it reads as the model talking to
itself and makes enrichment's JSON reply unparseable.

`make models` lists what the daemon has; `make models-pull` pulls the
preferred pair. `POST /api/ml/probe` — or **Verify inference** in Telemetry —
runs one generation and one embedding and reports what came back, because an
installed model is not necessarily a working one.

Enrichment's grounding check normalises punctuation and spacing on both
sides before testing that a suggestion appears in the document. The exact
substring test it replaced dropped "Acme, Inc." and "Maria Santos (CTO)" from
documents that plainly named both, which is why People, Organizations and
Projects came back empty. Each accepted entity now carries the sentence it
was found in, shown in the form, so a reviewer can check a proposed name
without opening the document. A suggestion the document does not contain is
still dropped and the drop still recorded.

### Telemetry

A floating window, opened from the sidebar or from the header beside Ingest,
that reports on the library while the user works in any module. It drags by its title bar, resizes from every
edge and corner down to a floor of 320x240, minimises to a pill, maximises on
a double-click, and its opacity is adjustable from 50% to 100% (85% by
default). Position, size, opacity and mode are stored, so closing and
reopening it puts it back where it was, and a viewport change moves it back
inside the screen rather than leaving it unreachable.

It is mounted in the shell rather than on a page, so navigating between
modules leaves it alone. Dragging writes to the element's transform directly
and commits to storage once on release: a render per pointer move would
re-render the telemetry sixty times a second in order to move a box. The
window is only as large as itself, with no layer behind it, so the Galaxy
underneath keeps every pointer event the window does not cover.

What it shows is read from the user's own library through the existing
endpoints — document, fragment and topic counts, bytes stored, the week's
ingestion, the most recent artifact and its status, the configured engines —
plus the round trip of its own request, which the browser can honestly
measure. **CEREBRO keeps no server-side metrics**: there are no request
rates, no CPU and no queue depths, so the window shows none. A dial reading a number nobody
measured would be worse than an absent dial.

### Timeline

`/construct/timeline` places events at the dates the documents themselves
state. "The cutover completed in March 2021" is an event in March 2021,
whoever uploaded the deck and whenever they did. Dates are found by regular
expression over the sentences of registered fragments, and every event
carries the expression that was matched and the sentence it came from, so
nothing on the timeline is unaccountable.

Precision is kept rather than flattened: a year is a year, "Q3 2024" a
quarter, "March 2021" a month, "12 Sep 2023" a day. An impossible date
degrades to the precision the text does support — "31 February 2024" is
February 2024, not a guessed day and not silence. **An upload or
registration date is never used as an event date**: that would be CEREBRO
inventing history out of its own filing.

Lanes are the library's own confirmed topics, most-used first. A topic was
approved by a human at registration, so grouping by it groups by a judgement
already made rather than one CEREBRO invented. A library that has confirmed
no topics falls back to the six named lanes, assigned on evidence — a lane word present in the sentence
or in the artifact's confirmed topics — and the matching word is shown in the
panel. Anything unmatched goes to "Other" rather than being pushed into a
lane a model guessed at. Events from overlapping chunks are deduplicated by
document, date and sentence.

A card leads with the document — its confirmed title, or the filename where
nothing was confirmed — then the date, then the sentence the event came
from. It used to lead with the sentence, which never said which document it
was, so a lane of cards read as unrelated noise.

Hovering a card gives the document's own facts, and the three dates there do
not mean the same thing, so each says where it came from. **Created** and
**Modified** are claims the file itself makes, read from PDF `/Info` or
Office core properties; a format that states neither leaves both unknown,
and the upload time is deliberately never used as a stand-in. **Registered**
is the one date CEREBRO itself knows.

The window is a pair of timestamps: zoom, pan, fit and the navigator all move
the same two numbers, and only events inside them are rendered. Dragging the
canvas moves time horizontally and scrolls the lanes vertically, from
anywhere that is not a card. Cards that would overlap are packed onto
further rows, so nothing is hidden behind anything.

The navigator's bars are **volume**, not a count of dates: their height is
pages of document, stacked and coloured by category in the lanes' own
colours. A month holding one eighty-page thesis and a month holding one
two-page memo are not the same amount of knowledge, and a bar that counted
events claimed they were. Each document counts once per month however many
dates it names, so a date-dense document cannot inflate its own size; where
a format reports no page count the floor is one page, which is presence
rather than a guess at length. The histogram covers the whole library, so
filtering the lanes does not change the shape of the knowledge behind it.

Related events say what they share — an entity, a document, a lane — and
never assert a semantic relationship, which CEREBRO has no way to establish.

Dragging the Galaxy moves it; holding shift turns it, following the pointer
around the centre. Rotation earns its place on a radial layout: turning the
map brings a cluster hidden behind a label round to the front. It is a
change of viewpoint and never of data — the layout stays the source of truth
for every relationship drawn, and labels counter-rotate so text stays
horizontal at any angle.

The Galaxy and the Timeline share a focus through the URL. Opening an event
in the Galaxy selects its subject there; a cluster offers to show itself over
time. The Galaxy also draws the entities a human confirmed — people,
organizations, projects, technologies — joined to the topics whose documents
name them, but only where an entity appears in more than one document: a name
mentioned once is a detail of that document, not a thread through the
library.

An answer from Ask CEREBRO can be mapped onto the Galaxy. "Show me on the
map" lights the topics the answer quoted, dims the ones it found but did not
use, and greys everything else; Reset returns the unmapped galaxy. The three
states are what retrieval and the citation guard established, not a judgement
about quality.
`/api/timeline/journey` follows one entity's events in order, which is the
second mode the design calls Knowledge Journey.

### Appearance

Light and dark switch from the header, in place: the control used to live only
in Settings, so changing it meant leaving the page — on the Galaxy, losing the
view the user had arranged. The button writes an explicit choice, applies it
immediately and saves it to the account in the background. "Match my system"
stays in Settings, because a two-state button cannot express three states
honestly.

### Navigation

The sidebar has two widths: 240px with labels, and a 64px rail of icons that
keep their accessible names and carry their label as a tooltip. The rail
applies from tablet width up; below that the panel is off-canvas behind the
hamburger, because a 64px drawer is not a navigation.

The Galaxy and its timeline open railed, since they want the screen. That is a
default, not an override: the moment the user picks a width it is stored and
wins on every route, Galaxy included. Nothing about the visualisation is
re-initialised when the width changes — the galaxy is one SVG `viewBox` and
the timeline a flex row, so both reflow in CSS with zoom, node positions,
selection and scroll position untouched.

### Search

`/construct/search` searches the library and the registered knowledge in one
request, in three modes: keyword (PostgreSQL full-text, no model), semantic
(local embeddings) and hybrid, which fuses the two rankings with Reciprocal
Rank Fusion and is the default. Results come back as documents, knowledge and
the confirmed topics those carry. The header box submits to it and suggests
completions of the user's own metadata as they type; ⌘K focuses it.

Relevance is stated in words, excerpts are the document's own text with the
matched terms marked by PostgreSQL, and a document awaiting review is findable
but labelled as not yet part of the user's knowledge. See `docs/SEARCH.md`.

### Ingestion

One drop zone. Dropping a single file opens the review form; dropping several
opens the table, a row each. There is no mode to choose first — the shape
follows what the user did.

A file under 1MB is read inside the upload request: extraction finishes in
well under a second and a round trip is simpler than a poll. A larger one is
answered for as soon as its bytes are stored, with status **processing**, and
read in the background. The work happens in CEREBRO rather than in the tab,
so the user can go elsewhere and find it finished; the form polls while it is
open and says that leaving is safe.

Cheap refusals still happen in the upload request, whatever the size: the
limit, the checksum, the duplicate check, and whether the bytes match the
extension. What needs the text — a PDF with no text layer — can only be found
later, so that refusal is written to the artifact as a rejection reason the
library shows, rather than raised into a request that has already answered.
`POST /api/artifacts/{id}/process` reads an artifact that is still waiting,
for the case the API restarted mid-task; it is idempotent by status, so a
review in progress cannot be clobbered.

Artifacts can be deleted, from the library, the review form or a table row,
each behind a confirmation. Deletion removes the row, the stored original,
the derived extraction object and — by database cascade — the fragments and
embeddings built from it. A deleted document must not leave retrievable
passages behind: that would be the library answering from something the user
deleted.

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

Every edge carries what is needed to justify drawing it: an explanation in a
sentence, the documents it rests on by name, a confidence stated as a count
of those documents, and its approval status. Hovering an edge shows all of
it. The kind names what was *observed* — two topics in one registered
document, or a confirmed entity named in a document about a topic — and
never what it might mean. CEREBRO cannot see that one thing *uses* or
*depends on* another, so no edge says so.

An edge resting on a single document is the weakest claim the graph makes.
It is kept, because the evidence is real, but drawn dashed and held back
until one of its endpoints is in focus — **unless no stronger edge exists**,
in which case it is drawn anyway. A young library's only evidence is still
its evidence, and hiding all of it drew an empty map and called that
restraint.

Nodes are confirmed topics and confirmed entities, and a **significance
rule** decides what may be proposed as either. A term naming the medium
rather than the subject — "PDF", "HTTPS", "document", "Models" — is set
aside when it stands alone, and kept the moment the document puts it in a
phrase that says something: "PDF Document Parsing Pipeline" survives, "PDF"
does not. Nothing is banned outright, so a library genuinely about file
formats keeps its subject. Spellings of one concept collapse to one node,
preferring the phrasing with more words; a missed merge leaves two nodes
meaning one thing, while a wrong merge invents a concept nobody wrote, and
the rule errs toward the cheaper mistake.

The rule governs *proposals*, so a library built before it still carries
terms a human confirmed. `POST /api/graph/revalidate` finds them. It reports
and changes nothing by default: those terms were approved by a person, and
deleting approved data to make a graph prettier is the kind of silent
overwrite CEREBRO must not do. `?apply=true` performs it, touching only the
concept fields, recording what it removed in the artifact's provenance, and
never deleting an artifact, a fragment, an extraction or source bytes.

Enrichment is a **background queue**, not part of the request that asks for
it. Running it inside the request caused three separate complaints at once:
the request blocked for minutes, there was nowhere to report progress to,
and navigating away aborted the fetch and threw the work away. The job now
lives on the artifact row, so it survives the page, the navigation and a
restart, and both Ingest and the Library read the same queue.

**One or two at a time, and the rest wait.** A local model is a single
daemon on one machine: asking it for twenty documents at once does not make
twenty arrive sooner, it makes all twenty slow and none reviewable early.
The queue admits one by default and a second only on evidence — a recent job
that finished quickly — and drops back to one when that stops being true.
Everything else waits visibly, with its place in the line, because "waiting"
without a number is indistinguishable from stuck. Claiming uses
`FOR UPDATE SKIP LOCKED`, so no two workers can take the same artifact.

Suggestions are **stored** when a job finishes, as unconfirmed proposals.
They used to exist only in the browser tab that asked for them. Storing them
changes nothing about trust: `field_methods` still records them as
proposals, only approval sets `human_confirmed`, and a value the user has
already typed is never overwritten from behind the page they are looking at.

Local enrichment runs under a **time budget**, not just a per-call timeout.
A long document is read in windows, and ten windows at the per-call timeout
is half an hour inside one HTTP request — which no browser waits for. The
proxy gave up first and reported the API as unreachable, which was both
wrong and unhelpful: the API was working and the model was slow. The windows
now share a budget, whatever was read when it runs low is what gets merged,
and the shortfall is stated in the notes. The proxy sets its own timeout
above that worst case and says "took too long" rather than "unreachable",
because the two need different actions.

## Performance Report

What the models and algorithms actually cost, measured rather than claimed.
`services/telemetry.py` stays a 50-entry in-memory ring for what is running
now; `operation_metrics` is the persistent row per operation that a report
needs, carrying what ran, how long it took and what it produced — never a
prompt, never a passage. Ingestion, enrichment, search and every Ask CEREBRO
question are instrumented, and a metrics write that fails is swallowed: a
lost row costs a measurement, a propagated one costs the user's upload.

**Accuracy comes from the review loop.** Every suggestion is confirmed,
edited or dropped by a human as a matter of course, which is a labelled set
produced for free — but registration used to overwrite `field_methods` with
`human_confirmed` and destroy the record of what the model proposed, so the
before-state no longer existed. A `suggested_snapshot` is now kept in
provenance at the first review, and precision, recall and F1 are computed
per field from it. Documents registered before snapshots existed are
**excluded rather than assumed correct**, and the page says how many.

Three things the report refuses to do. It prints no number where there is no
measurement, because a zero that looks like data is worse than an absence
that looks like one. It counts an Ask CEREBRO refusal and never grades it:
abstaining is correct behaviour when the library lacks the answer, and only
a human can say whether each one was right. And it labels precision as
"suggestions kept at human review" rather than correctness, since a user who
approves everything would otherwise score a model perfect.

Counts are shown beside every rate. Over a library of thirty documents a
percentage implies a population that is not there.

A person's CV is the one document that says what they *did*, in order, and
it anchors the timeline. It goes through the ordinary artifact pipeline —
same validation, extraction, storage and ownership checks — and the profile
points at it, so there is no second ingestion path and no CV-shaped hole in
the security model. Reading it is deterministic: a line under a recognised
heading carrying a date range, or a short line carrying one date. A line
with no date is not an event, because deciding whether it is a
responsibility or a page footer would be a guess.

Anchors arrive as **suggestions** and reach the Timeline only once a human
approves them; `cv_status` drives a "Setup incomplete" state that
personalises the timeline and nothing else — no other part of CEREBRO is
blocked without a CV. Each anchor keeps the CV's own line as evidence, and
`extracted` keeps what the document said beside whatever the user corrected
it to, so a correction never destroys the record of the source. "Present"
stores a **null** end date rather than today, and a year-only range keeps
`year` precision so it is never displayed as more exact than the CV was.

Re-uploading or replacing a CV matches anchors by fingerprint: a career is
updated rather than duplicated, an anchor nobody edited is refreshed, and
one somebody corrected is left as they left it.

Anchors are a **backdrop**. An artifact never takes its date from the period
it falls inside, and no document is attached to an employer for overlapping
it in time — overlapping dates are not a relationship.

Timeline dates are the date the document states, or the date it was
registered, and which one is always shown. No date is inferred. The axis has
two levels — years as milestones, months beneath — and each month states how
many artifacts fall in it rather than leaving a bar to be read. Cards preview
the document's own opening, quoted, so a card can be checked against its
source.

The workspace is one surface rather than three cards: Galaxy, details and
Timeline share a single border and divide with hairlines, with no gutters
between them. The Timeline spans the full width beneath both, takes about a
quarter of the height, and collapses to its header to give the Galaxy the
screen. The divider between them is also the resize grip.

Every month between the first and the last appears on the axis, including
empty ones — a gap in the record is itself information, and skipping quiet
months would make a sparse year look as busy as a dense one. Month ticks are
capped in width so a year holding one month does not become a single bar the
width of the screen.

The sidebar collapses to its icon rail from the header, and the choice is
remembered per browser so it does not reopen on every navigation.

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
