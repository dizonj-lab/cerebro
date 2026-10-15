"""Dashboard aggregates.

One read per panel, all scoped to the owner. Nothing here is cached: the
counts are cheap aggregate queries over indexed columns, and a cache would
add a staleness problem the dashboard does not have.

Only registered artifacts count as knowledge. An artifact awaiting review is
visible in Recent Ingestions, because the user needs to act on it, but it is
not counted as a document, a fragment or a topic — approval is the gate into
trusted knowledge and the dashboard must not blur it.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import KnowledgeFragment

RECENT_LIMIT = 5
ACTIVITY_DAYS = 14
# Enough to show structure, few enough to stay readable and cheap.
MAP_NODES = 9
DISTRIBUTION_SLICES = 5
RECOLLECTION_LIMIT = 5


def _week_ago() -> datetime:
    return datetime.now(UTC) - timedelta(days=7)


def _registered(owner_id: uuid.UUID):
    return (Artifact.owner_id == owner_id, Artifact.status == "registered")


def _topic_rows(db: Session, owner_id: uuid.UUID) -> list[tuple[list, datetime]]:
    """Topics per registered artifact, with when it was registered.

    Only the metadata column is selected, not whole rows: the topic lists are
    small, the rest of an artifact row is not.
    """
    rows = db.execute(
        select(Artifact.artifact_metadata, Artifact.registered_at).where(*_registered(owner_id))
    ).all()
    return [((meta or {}).get("topics") or [], when) for meta, when in rows]


def summary(db: Session, owner_id: uuid.UUID) -> dict:
    since = _week_ago()

    documents = db.scalar(
        select(func.count()).select_from(Artifact).where(*_registered(owner_id))
    )
    documents_new = db.scalar(
        select(func.count())
        .select_from(Artifact)
        .where(*_registered(owner_id), Artifact.registered_at >= since)
    )
    fragments = db.scalar(
        select(func.count())
        .select_from(KnowledgeFragment)
        .where(KnowledgeFragment.owner_id == owner_id)
    )
    fragments_new = db.scalar(
        select(func.count())
        .select_from(KnowledgeFragment)
        .where(KnowledgeFragment.owner_id == owner_id, KnowledgeFragment.created_at >= since)
    )
    # Storage counts every stored artifact, approved or not: the bytes are on
    # disk either way.
    storage = db.scalar(
        select(func.coalesce(func.sum(Artifact.size_bytes), 0)).where(
            Artifact.owner_id == owner_id
        )
    )

    rows = _topic_rows(db, owner_id)
    all_topics = {t for topics, _ in rows for t in topics}
    new_topics = {t for topics, when in rows if when and when >= since for t in topics}

    return {
        "documents": {"total": int(documents or 0), "new_this_week": int(documents_new or 0)},
        "fragments": {"total": int(fragments or 0), "new_this_week": int(fragments_new or 0)},
        "topics": {
            "total": len(all_topics),
            # A topic is "new" when it arrived with an artifact registered this
            # week. It may have existed before; this is not a claim that it is
            # newly discovered.
            "new_this_week": len(new_topics - (all_topics - new_topics)),
        },
        "storage": {
            "bytes": int(storage or 0),
            # No quota exists. Reporting a percentage would require inventing
            # a denominator.
            "quota_bytes": None,
            "percent": None,
        },
    }


def recent_ingestions(db: Session, owner_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(
            Artifact.id,
            Artifact.filename,
            Artifact.modality,
            Artifact.size_bytes,
            Artifact.status,
            Artifact.created_at,
        )
        .where(Artifact.owner_id == owner_id)
        .order_by(Artifact.created_at.desc())
        .limit(RECENT_LIMIT)
    ).all()
    return [
        {
            "id": r[0],
            "filename": r[1],
            "modality": r[2],
            "size_bytes": r[3],
            "status": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def activity(db: Session, owner_id: uuid.UUID, *, days: int = ACTIVITY_DAYS) -> list[dict]:
    """Uploads per day, grouped in the database rather than in Python."""
    start = (datetime.now(UTC) - timedelta(days=days - 1)).date()
    rows = db.execute(
        select(cast(Artifact.created_at, Date).label("day"), func.count())
        .where(Artifact.owner_id == owner_id, cast(Artifact.created_at, Date) >= start)
        .group_by("day")
    ).all()
    counts = {day: int(n) for day, n in rows}
    out = []
    for i in range(days):
        day = start + timedelta(days=i)
        out.append({"date": day.isoformat(), "count": counts.get(day, 0)})
    return out


def topic_distribution(db: Session, owner_id: uuid.UUID) -> dict:
    counts = Counter(t for topics, _ in _topic_rows(db, owner_id) for t in topics)
    if not counts:
        return {"slices": [], "total": 0}

    top = counts.most_common(DISTRIBUTION_SLICES)
    remainder = sum(counts.values()) - sum(n for _, n in top)
    slices = [{"label": label, "count": n} for label, n in top]
    if remainder:
        slices.append({"label": "Others", "count": remainder})
    return {"slices": slices, "total": len(counts)}


def knowledge_map(db: Session, owner_id: uuid.UUID) -> dict:
    """Topics that appear together on the same registered artifact.

    Co-occurrence is the only relationship the data actually supports. It is
    evidence from the artifacts themselves, not an inferred semantic graph,
    and the response says so.
    """
    rows = _topic_rows(db, owner_id)
    counts = Counter(t for topics, _ in rows for t in topics)
    if not counts:
        return {"center": None, "nodes": [], "edges": [], "basis": "topic_co_occurrence"}

    keep = [label for label, _ in counts.most_common(MAP_NODES)]
    rank = {label: i for i, label in enumerate(keep)}
    center = keep[0]

    pairs: Counter = Counter()
    for topics, _ in rows:
        present = sorted({t for t in topics if t in rank}, key=lambda t: rank[t])
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                pairs[(a, b)] += 1

    return {
        "center": center,
        "nodes": [{"label": label, "count": counts[label]} for label in keep],
        "edges": [{"source": a, "target": b, "weight": n} for (a, b), n in pairs.most_common(20)],
        "basis": "topic_co_occurrence",
    }


def recollection(db: Session, owner_id: uuid.UUID) -> list[dict]:
    """Topics with the documents that evidence them.

    Not a recommendation engine and not an LLM call: each entry is a topic the
    user's own approved artifacts carry, with the artifacts that carry it, so
    every suggestion can be traced to its sources.
    """
    rows = db.execute(
        select(Artifact.id, Artifact.filename, Artifact.modality, Artifact.artifact_metadata)
        .where(*_registered(owner_id))
        .order_by(Artifact.registered_at.desc())
    ).all()

    by_topic: dict[str, list[dict]] = {}
    for artifact_id, filename, modality, meta in rows:
        for topic in (meta or {}).get("topics") or []:
            by_topic.setdefault(topic, []).append(
                {"id": artifact_id, "filename": filename, "modality": modality}
            )

    ranked = sorted(by_topic.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [
        {
            "topic": topic,
            "document_count": len(artifacts),
            "artifacts": artifacts[:3],
        }
        for topic, artifacts in ranked[:RECOLLECTION_LIMIT]
    ]


def overview(db: Session, owner_id: uuid.UUID) -> dict:
    return {
        **summary(db, owner_id),
        "recent": recent_ingestions(db, owner_id),
        "activity": activity(db, owner_id),
        "topic_distribution": topic_distribution(db, owner_id),
        "knowledge_map": knowledge_map(db, owner_id),
        "recollection": recollection(db, owner_id),
    }
