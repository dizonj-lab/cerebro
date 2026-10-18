"""Unified search: keyword, semantic, and the hybrid of the two.

Three retrievals over the same owner-scoped data:

* **Keyword** is PostgreSQL full-text search — `to_tsvector`/`plainto_tsquery`
  with `ts_rank`. No extension and no second datastore: Postgres already does
  this, and adding Elasticsearch for it would be infrastructure without a
  reason. A quoted query becomes a phrase query.
* **Semantic** reuses the existing embedding provider and `VectorIndex`.
* **Hybrid** fuses the two with Reciprocal Rank Fusion, which needs no tuned
  weights and no reranking model — it combines positions, not scores, so two
  retrievals with incomparable scales can still be merged honestly.

Everything here obeys the same two rules as the rest of CEREBRO: results are
scoped to the authenticated owner in the query predicate, and **only
registered artifacts and their fragments are searchable**. Something awaiting
review is never returned as knowledge.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Date, String, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import KnowledgeFragment
from app.services import ingest_settings
from app.services.embeddings import EmbeddingFailed, provider_for
from app.services.retrieval import get_index

MODES = ("keyword", "semantic", "hybrid")
SCOPES = ("all", "library", "knowledge")

# RRF's only parameter. 60 is the value from the original paper and needs no
# per-corpus tuning, which is the point of using it.
RRF_K = 60
CANDIDATES = 50


@dataclass
class Filters:
    """Only filters the indexed metadata can actually answer.

    There is deliberately no confidence filter and no collection filter:
    neither exists in the data, and offering them would mean inventing the
    values behind them.
    """

    modalities: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    uploaded_from: date | None = None
    uploaded_to: date | None = None

    def any(self) -> bool:
        return any(
            [
                self.modalities, self.statuses, self.topics, self.tags,
                self.people, self.organizations, self.projects,
                self.uploaded_from, self.uploaded_to,
            ]
        )


def _tsquery(query: str):
    """A phrase query for a quoted string, otherwise a plain one."""
    stripped = query.strip()
    if len(stripped) > 1 and stripped.startswith('"') and stripped.endswith('"'):
        return func.phraseto_tsquery("english", stripped[1:-1])
    return func.plainto_tsquery("english", stripped)


def _artifact_conditions(owner_id: uuid.UUID, filters: Filters, *, registered_only: bool):
    conditions = [Artifact.owner_id == owner_id]
    if registered_only:
        conditions.append(Artifact.status == "registered")
    elif filters.statuses:
        conditions.append(Artifact.status.in_(filters.statuses))

    if filters.modalities:
        conditions.append(Artifact.modality.in_(filters.modalities))
    if filters.uploaded_from:
        conditions.append(cast(Artifact.created_at, Date) >= filters.uploaded_from)
    if filters.uploaded_to:
        conditions.append(cast(Artifact.created_at, Date) <= filters.uploaded_to)

    # JSONB list membership, so a topic filter matches the confirmed topics
    # on the artifact rather than a substring of its text.
    for values, key in (
        (filters.topics, "topics"),
        (filters.tags, "tags"),
        (filters.people, "people"),
        (filters.organizations, "organizations"),
        (filters.projects, "projects"),
    ):
        if values:
            # JSONB containment, so a filter matches a list member exactly
            # rather than a substring of the serialised list.
            conditions.append(
                or_(*[Artifact.artifact_metadata[key].contains([v]) for v in values])
            )
    return conditions


def _metadata_text():
    """The artifact's own searchable text: filename plus confirmed metadata."""
    return func.concat_ws(
        literal(" "),
        Artifact.filename,
        Artifact.artifact_metadata["title"].astext,
        Artifact.artifact_metadata["description"].astext,
        cast(Artifact.artifact_metadata["topics"], String),
        cast(Artifact.artifact_metadata["tags"], String),
        cast(Artifact.artifact_metadata["people"], String),
        cast(Artifact.artifact_metadata["organizations"], String),
        cast(Artifact.artifact_metadata["projects"], String),
    )


def _keyword_fragments(db: Session, owner_id, query: str, filters: Filters) -> list[dict]:
    tsquery = _tsquery(query)
    document = func.to_tsvector("english", KnowledgeFragment.content)
    rows = db.execute(
        select(
            KnowledgeFragment.id,
            KnowledgeFragment.artifact_id,
            KnowledgeFragment.content,
            KnowledgeFragment.source_location,
            KnowledgeFragment.kind,
            Artifact.filename,
            Artifact.artifact_metadata,
            func.ts_rank(document, tsquery).label("rank"),
            # Postgres picks the passage around the match and marks it, so the
            # excerpt shown is the part that actually matched.
            func.ts_headline(
                "english",
                KnowledgeFragment.content,
                tsquery,
                literal("StartSel=<mark>,StopSel=</mark>,MaxWords=38,MinWords=12"),
            ).label("headline"),
        )
        .join(Artifact, Artifact.id == KnowledgeFragment.artifact_id)
        .where(
            KnowledgeFragment.owner_id == owner_id,
            document.op("@@")(tsquery),
            *_artifact_conditions(owner_id, filters, registered_only=True),
        )
        .order_by(func.ts_rank(document, tsquery).desc())
        .limit(CANDIDATES)
    ).all()

    return [
        {
            "fragment_id": str(r[0]),
            "artifact_id": str(r[1]),
            "content": r[2],
            "source_location": r[3] or {},
            "kind": r[4],
            "filename": r[5],
            "title": (r[6] or {}).get("title"),
            "topics": (r[6] or {}).get("topics") or [],
            "score": float(r[7]),
            "excerpt": r[8],
        }
        for r in rows
    ]


def _keyword_documents(db: Session, owner_id, query: str, filters: Filters) -> list[dict]:
    """Artifacts whose own metadata matches, independent of their content."""
    tsquery = _tsquery(query)
    document = func.to_tsvector("english", _metadata_text())
    rows = db.execute(
        select(
            Artifact.id,
            Artifact.filename,
            Artifact.modality,
            Artifact.status,
            Artifact.created_at,
            Artifact.artifact_metadata,
            func.ts_rank(document, tsquery).label("rank"),
        )
        .where(
            document.op("@@")(tsquery),
            # Documents are searchable at any status: an artifact awaiting
            # review is still the user's, and they may be looking for it. Its
            # status travels with it so it is never mistaken for knowledge.
            *_artifact_conditions(owner_id, filters, registered_only=False),
        )
        .order_by(func.ts_rank(document, tsquery).desc())
        .limit(CANDIDATES)
    ).all()

    return [
        {
            "artifact_id": str(r[0]),
            "filename": r[1],
            "modality": r[2],
            "status": r[3],
            "created_at": r[4],
            "title": (r[5] or {}).get("title"),
            "topics": (r[5] or {}).get("topics") or [],
            "tags": (r[5] or {}).get("tags") or [],
            "score": float(r[6]),
        }
        for r in rows
    ]


def _semantic_fragments(db: Session, owner_id, query: str, filters: Filters) -> list[dict]:
    provider = provider_for(ingest_settings.for_user(db, owner_id))
    vector = provider.embed([query])[0]
    matches = get_index().search(
        db,
        owner_id=owner_id,
        vector=vector,
        provider=provider.name,
        model=provider.model,
        dimensions=provider.dimensions,
        limit=CANDIDATES,
    )
    if not matches:
        return []

    # Filters are applied after retrieval here, because the vector index
    # ranks before it knows about metadata. The candidate list is capped, so
    # this stays a small in-memory pass rather than a scan.
    allowed = None
    if filters.any():
        allowed = {
            str(a)
            for (a,) in db.execute(
                select(Artifact.id).where(
                    *_artifact_conditions(owner_id, filters, registered_only=True)
                )
            ).all()
        }

    out = []
    for match in matches:
        artifact_id = str(match.artifact_id)
        if allowed is not None and artifact_id not in allowed:
            continue
        out.append(
            {
                "fragment_id": str(match.fragment_id),
                "artifact_id": artifact_id,
                "content": match.content,
                "source_location": match.source_location,
                "kind": match.kind,
                "filename": match.artifact_filename,
                "title": match.artifact_title,
                "topics": [],
                "score": match.score,
                "excerpt": match.content[:280],
            }
        )
    return out


def _fuse(keyword: list[dict], semantic: list[dict], key: str) -> list[dict]:
    """Reciprocal Rank Fusion over two ranked lists.

    Positions are fused, not scores: a cosine similarity and a ts_rank are
    not on the same scale, and pretending otherwise is how a hybrid search
    quietly becomes whichever retrieval happens to produce bigger numbers.
    """
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, dict] = {}
    found_in: dict[str, set[str]] = defaultdict(set)

    for name, ranked in (("keyword", keyword), ("semantic", semantic)):
        for rank, item in enumerate(ranked, start=1):
            identifier = item[key]
            scores[identifier] += 1.0 / (RRF_K + rank)
            found_in[identifier].add(name)
            # Keep the keyword copy when there is one: it carries the
            # highlighted excerpt.
            if identifier not in best or name == "keyword":
                best[identifier] = item

    fused = []
    for identifier, score in sorted(scores.items(), key=lambda kv: -kv[1]):
        item = dict(best[identifier])
        item["score"] = round(score, 6)
        item["matched_by"] = sorted(found_in[identifier])
        fused.append(item)
    return fused


def _relevance(position: int, total: int) -> str:
    """Words, not a percentage: a fused rank is not a confidence."""
    if total <= 1 or position == 0:
        return "Highly Related"
    if position < max(2, total // 3):
        return "Related"
    return "Potential Connection"


def search(
    db: Session,
    owner_id: uuid.UUID,
    *,
    query: str,
    mode: str = "hybrid",
    scope: str = "all",
    filters: Filters | None = None,
    limit: int = 20,
) -> dict:
    started = time.perf_counter()
    filters = filters or Filters()
    keyword_fragments: list[dict] = []
    semantic_fragments: list[dict] = []
    documents: list[dict] = []
    note: str | None = None

    wants_knowledge = scope in ("all", "knowledge")
    wants_library = scope in ("all", "library")

    if mode in ("keyword", "hybrid"):
        if wants_knowledge:
            keyword_fragments = _keyword_fragments(db, owner_id, query, filters)
        if wants_library:
            documents = _keyword_documents(db, owner_id, query, filters)

    if mode in ("semantic", "hybrid") and wants_knowledge:
        try:
            semantic_fragments = _semantic_fragments(db, owner_id, query, filters)
        except EmbeddingFailed as exc:
            # Keyword results still stand; say why the other half is missing
            # rather than returning a quietly halved result set.
            note = str(exc)

    knowledge = (
        _fuse(keyword_fragments, semantic_fragments, "fragment_id")
        if mode == "hybrid"
        else [
            {**item, "matched_by": [mode]}
            for item in (keyword_fragments if mode == "keyword" else semantic_fragments)
        ]
    )
    knowledge = knowledge[:limit]
    for position, item in enumerate(knowledge):
        item["relevance"] = _relevance(position, len(knowledge))

    # Topics are read from the owning artifact rather than carried on the
    # fragment: the fragment has no metadata of its own, and a topic shown
    # next to a result must be one a human confirmed on the document.
    missing = [i["artifact_id"] for i in knowledge if not i.get("topics")]
    if missing:
        topics = {
            str(a): (m or {}).get("topics") or []
            for a, m in db.execute(
                select(Artifact.id, Artifact.artifact_metadata).where(
                    Artifact.owner_id == owner_id, Artifact.id.in_([uuid.UUID(m) for m in missing])
                )
            ).all()
        }
        for item in knowledge:
            if not item.get("topics"):
                item["topics"] = topics.get(item["artifact_id"], [])

    documents = documents[:limit]
    for position, item in enumerate(documents):
        item["relevance"] = _relevance(position, len(documents))

    # Concepts are the topics carried by the matching knowledge: a third
    # grouping drawn from the results themselves, not a separate search.
    concept_counts: dict[str, int] = defaultdict(int)
    for item in knowledge:
        for topic in item.get("topics") or []:
            concept_counts[topic] += 1
    for item in documents:
        for topic in item.get("topics") or []:
            concept_counts[topic] += 1
    concepts = [
        {"label": label, "count": count}
        for label, count in sorted(concept_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    ]

    return {
        "query": query,
        "mode": mode,
        "scope": scope,
        "documents": documents,
        "knowledge": knowledge,
        "concepts": concepts,
        "total_documents": len(documents),
        "total_knowledge": len(knowledge),
        "took_ms": round((time.perf_counter() - started) * 1000, 1),
        "note": note,
    }


def suggestions(db: Session, owner_id: uuid.UUID, prefix: str, *, limit: int = 8) -> list[str]:
    """Topics and titles the user already has that begin with what they typed.

    Drawn from their own confirmed metadata, so a suggestion is always
    something they can actually find.
    """
    stripped = prefix.strip().lower()
    if not stripped:
        return []

    rows = db.execute(
        select(Artifact.artifact_metadata, Artifact.filename).where(
            Artifact.owner_id == owner_id, Artifact.status == "registered"
        )
    ).all()

    candidates: set[str] = set()
    for meta, filename in rows:
        meta = meta or {}
        for value in [meta.get("title"), filename]:
            if isinstance(value, str) and value:
                candidates.add(value)
        for key in ("topics", "tags", "people", "organizations", "projects"):
            for value in meta.get(key) or []:
                if isinstance(value, str):
                    candidates.add(value)

    matches = sorted(
        (c for c in candidates if stripped in c.lower()),
        key=lambda c: (not c.lower().startswith(stripped), len(c), c),
    )
    return matches[:limit]
