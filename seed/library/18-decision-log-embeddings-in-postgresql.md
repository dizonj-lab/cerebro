# Decision Log: Embeddings Stay in PostgreSQL

Prepared by Joselito Dizon

_Why CEREBRO keeps vectors in PostgreSQL instead of adding a vector database, and when to revisit._

## Decision

Decided on 10 October 2026: embeddings for CEREBRO Semantic Search stay in PostgreSQL, searched by exact cosine similarity. No separate vector database is added.

## Reasons

A personal library holds thousands of fragments, not billions; exact search is fast enough and never misses.

One datastore keeps Containerised Deployment simple: one fewer service in Kubernetes and in Compose, one fewer thing to back up.

## Revisit when

A single user's library passes a few hundred thousand fragments, or query latency exceeds a second.

Switching embedding model orphans existing vectors, so any change must re-register the library.

<sub>Illustrative sample document for the CEREBRO demo library.</sub>
