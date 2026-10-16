# CEREBRO — Search

How a query becomes results. Only what exists today is described here.

## Flow

```
Header search box (debounced suggestions, ⌘K)
   │  submit → /construct/search?q=…
   ▼
SearchView (client)  ── POST /api/search { query, mode, scope, filters, limit }
   │
   ▼
app/api/search.py  →  app/services/search.py
   │
   ├── keyword   PostgreSQL full-text
   │              to_tsvector('english', content) @@ plainto_tsquery(…)
   │              ts_rank for ordering, ts_headline for the excerpt
   │              GIN index: ix_knowledge_fragments_fts
   │
   ├── semantic  get_embedding_provider().embed(query)
   │              → VectorIndex.search (brute-force cosine over float4[])
   │
   └── hybrid    Reciprocal Rank Fusion of the two rankings
                  score(d) = Σ 1 / (60 + rank_r(d))
   │
   ▼
Three groupings of one retrieval:
   documents   artifacts whose own metadata matched (any status)
   knowledge   fragments of registered artifacts only
   concepts    the confirmed topics those results carry
```

Suggestions are a separate, cheap call: `GET /api/search/suggestions?q=` returns
completions of the user's own confirmed titles, topics, tags, people,
organizations and projects. It touches no model.

## Modes

| Mode | Retrieval | Model used | Finds |
| ---- | --------- | ---------- | ----- |
| Keyword | PostgreSQL full-text | none | exact terms, identifiers, names |
| Semantic | local embeddings | local embedder | paraphrase, related wording |
| Hybrid (default) | both, fused by RRF | local embedder | either |

Hybrid is the default because neither half is reliable alone: a keyword query
misses a paraphrase, a semantic query misses an exact identifier.

RRF fuses **positions**, not scores. A `ts_rank` and a cosine similarity are
not on the same scale, so combining the numbers directly would make the hybrid
whichever retrieval happens to produce larger values. `k = 60` is the value
from the original paper and needs no per-corpus tuning.

A quoted query (`"retention schedule"`) becomes a phrase query
(`phraseto_tsquery`), so word order matters.

## What results claim

* **Relevance is words** — "Highly Related", "Related", "Potential
  Connection". A fused rank is not a confidence, and a percentage would read
  as one.
* **Excerpts are the document's own text.** `ts_headline` marks the matched
  terms with `<mark>`; nothing else is inserted. A semantic hit, which has no
  marked passage, shows its opening instead.
* **Source locations are only those extraction established.** A modality with
  no pages has no page, and the citation omits it rather than guessing.
* **Documents carry their status.** An artifact awaiting review is findable —
  it is the user's document — but it is labelled as not yet part of their
  knowledge, and contributes no fragments. Unapproved content never enters
  retrieval as knowledge.
* **Concepts are confirmed topics**, read from the artifacts in the result
  set. Nothing is inferred from the query.

## Access control

Owner scoping is a predicate in every query — keyword, semantic and
suggestions alike — never a filter applied to results afterwards. The owner
comes from the session cookie; no request field names a user. Cross-user
leakage is covered by tests for both search and suggestions.

Search history is stored in the browser's `localStorage`, per browser. There
is no server-side saved search, because that would be a new stored object
with its own sharing and retention questions.

## Filters

Filters cover metadata that is actually stored: document type (modality),
ingestion status, confirmed topics, tags, upload date range. Topic facets come
from the user's own confirmed topics, and document types from the modalities
present in their library, so no option is offered that nothing could match.

There is deliberately **no confidence filter and no collection filter**: 
CEREBRO stores neither, and a control that silently matches everything or
nothing is worse than its absence.

## Why no new infrastructure

PostgreSQL's own full-text search, with a GIN index, serves keyword retrieval
at this scale. Adding Elasticsearch would mean a second datastore to deploy,
secure and keep consistent with the artifacts table, for a capability the
existing database already has.

Two known limits, recorded rather than worked around:

* **No pgvector.** Semantic retrieval is an exact brute-force cosine scan of
  the owner's vectors, behind the `VectorIndex` interface so an approximate
  index can replace it without changing a caller.
* **No index on the artifact side.** Its searchable text concatenates the
  filename with JSONB metadata, and both `concat_ws` and a JSONB-to-text cast
  are `STABLE` rather than `IMMUTABLE`, so PostgreSQL refuses the expression
  in an index — a generated column hits the same rule. That table holds one
  row per document rather than one per chunk, so the scan is cheap; the
  fragment index is where the cost was.
