"""The knowledge graph behind the Galaxy.

Built from what the data actually supports, which is less than a knowledge
graph proper:

* **Topic nodes** are clusters — a topic a user confirmed on a registered
  artifact. They are not entities in a store; there is no graph database.
* **Fragment nodes** are knowledge fragments, each resolving to its artifact,
  its fragment id and the source location it was extracted from.
* **Topic–topic edges** are co-occurrence: a registered artifact carries both.
* **Topic–fragment edges** are containment: the fragment came from an
  artifact carrying that topic.

No edge here is a verified semantic relationship, and none is presented as
one. Every edge carries `kind` and `relevance` so the interface can say what
it is looking at.

Only registered artifacts contribute. Nothing unapproved reaches the Galaxy.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import KnowledgeFragment

# Progressive disclosure: the Galaxy opens on the clusters, and fragments
# arrive when a cluster is expanded. These caps are what keep an SVG scene
# interactive rather than a thousand-node soup.
MAX_CLUSTERS = 12
MAX_FRAGMENTS_PER_CLUSTER = 12
MAX_EDGES = 80
# Entities drawn alongside the topics. Capped for the same reason as
# clusters: past a dozen or so, a graph stops being readable.
MAX_ENTITIES = 14
# The confirmed entity fields. Concepts and tags are deliberately absent —
# they describe a document rather than naming something in the world.
ENTITY_FIELDS = ("people", "organizations", "projects", "technologies")

# Co-occurrence counts, turned into words rather than a bare percentage. A
# number would read as a confidence the data does not support.
RELEVANCE = ("Potential Connection", "Related", "Highly Related")


def _relevance(weight: int) -> str:
    if weight >= 3:
        return RELEVANCE[2]
    if weight == 2:
        return RELEVANCE[1]
    return RELEVANCE[0]


@dataclass
class _Registered:
    id: uuid.UUID
    filename: str
    title: str | None
    topics: list[str]
    metadata: dict


def _registered_artifacts(db: Session, owner_id: uuid.UUID) -> list[_Registered]:
    rows = db.execute(
        select(Artifact.id, Artifact.filename, Artifact.artifact_metadata).where(
            Artifact.owner_id == owner_id, Artifact.status == "registered"
        )
    ).all()
    out = []
    for artifact_id, filename, meta in rows:
        meta = meta or {}
        out.append(
            _Registered(
                id=artifact_id,
                filename=filename,
                title=meta.get("title"),
                topics=[t for t in (meta.get("topics") or []) if isinstance(t, str)],
                metadata=meta,
            )
        )
    return out


def galaxy(db: Session, owner_id: uuid.UUID) -> dict:
    """The cluster-level view: topics, and how often they share a document."""
    artifacts = _registered_artifacts(db, owner_id)
    if not artifacts:
        return {"nodes": [], "edges": [], "clusters": [], "truncated": False}

    counts = Counter(t for a in artifacts for t in a.topics)
    if not counts:
        return {"nodes": [], "edges": [], "clusters": [], "truncated": False}

    keep = [label for label, _ in counts.most_common(MAX_CLUSTERS)]
    keep_set = set(keep)

    # Fragment counts per topic, so a cluster can show its weight without
    # loading the fragments themselves.
    fragment_counts = dict(
        db.execute(
            select(KnowledgeFragment.artifact_id, func.count())
            .where(KnowledgeFragment.owner_id == owner_id)
            .group_by(KnowledgeFragment.artifact_id)
        ).all()
    )

    per_topic_fragments: Counter = Counter()
    per_topic_documents: Counter = Counter()
    for artifact in artifacts:
        for topic in artifact.topics:
            if topic in keep_set:
                per_topic_documents[topic] += 1
                per_topic_fragments[topic] += int(fragment_counts.get(artifact.id, 0))

    pairs: Counter = Counter()
    for artifact in artifacts:
        present = sorted({t for t in artifact.topics if t in keep_set})
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                pairs[(a, b)] += 1

    # Entities the documents name — people, organizations, projects and
    # technologies a human confirmed at registration. An entity that appears
    # in two topics is a real link between them, and a more interesting one
    # than two topics merely sharing a file. It is still co-occurrence:
    # CEREBRO says what they share, never what the relationship means.
    entity_nodes, entity_edges = _entity_graph(artifacts, keep_set)

    nodes = [
        {
            "id": f"topic:{label}",
            "label": label,
            "type": "cluster",
            "category": label,
            "document_count": per_topic_documents[label],
            "fragment_count": per_topic_fragments[label],
            "relationship_count": sum(
                1 for (a, b) in pairs if a == label or b == label
            ),
            # A cluster is a confirmed topic on registered artifacts; it has
            # no single source location of its own.
            "provenance": "registered",
        }
        for label in keep
    ]

    edges = [
        {
            "id": f"topic:{a}|topic:{b}",
            "source": f"topic:{a}",
            "target": f"topic:{b}",
            "kind": "co_occurrence",
            "weight": weight,
            "relevance": _relevance(weight),
        }
        for (a, b), weight in pairs.most_common(MAX_EDGES)
    ]

    return {
        "nodes": nodes + entity_nodes,
        "edges": edges + entity_edges,
        "clusters": keep,
        "truncated": len(counts) > len(keep),
    }


def _entity_graph(
    artifacts: list[_Registered], topics: set[str]
) -> tuple[list[dict], list[dict]]:
    """Confirmed entities, and the topics whose documents name them.

    Only entities appearing in more than one document are kept: a name
    mentioned once is a detail of that document, not a thread through the
    library, and drawing every one of them would bury the graph.
    """
    mentions: dict[tuple[str, str], set[uuid.UUID]] = defaultdict(set)
    links: Counter = Counter()

    for artifact in artifacts:
        present = {t for t in artifact.topics if t in topics}
        for field in ENTITY_FIELDS:
            for value in artifact.metadata.get(field) or []:
                if not isinstance(value, str) or not value.strip():
                    continue
                key = (field, value.strip())
                mentions[key].add(artifact.id)
                for topic in present:
                    links[(key, topic)] += 1

    shared = {
        key: documents for key, documents in mentions.items() if len(documents) > 1
    }
    ranked = sorted(shared.items(), key=lambda row: (-len(row[1]), row[0][1]))[:MAX_ENTITIES]

    nodes = [
        {
            "id": f"{field}:{value}",
            "label": value,
            "type": "entity",
            "category": field,
            "document_count": len(documents),
            "fragment_count": 0,
            "relationship_count": sum(1 for (key, _), _ in links.items() if key == (field, value)),
            "provenance": "human_confirmed",
        }
        for (field, value), documents in ranked
    ]

    keep_keys = {key for key, _ in ranked}
    edges = [
        {
            "id": f"{field}:{value}|topic:{topic}",
            "source": f"{field}:{value}",
            "target": f"topic:{topic}",
            "kind": "named_in",
            "weight": weight,
            "relevance": _relevance(weight),
        }
        for ((field, value), topic), weight in links.most_common()
        if (field, value) in keep_keys
    ][:MAX_EDGES]

    return nodes, edges


def expand(db: Session, owner_id: uuid.UUID, topic: str) -> dict:
    """Fragments inside one cluster, with their provenance.

    Fetched when a cluster is expanded rather than up front: the whole graph
    is never loaded.
    """
    artifacts = [a for a in _registered_artifacts(db, owner_id) if topic in a.topics]
    if not artifacts:
        return {"nodes": [], "edges": []}

    by_artifact = {a.id: a for a in artifacts}
    rows = db.execute(
        select(
            KnowledgeFragment.id,
            KnowledgeFragment.artifact_id,
            KnowledgeFragment.content,
            KnowledgeFragment.source_location,
            KnowledgeFragment.kind,
            KnowledgeFragment.ordinal,
        )
        .where(
            KnowledgeFragment.owner_id == owner_id,
            KnowledgeFragment.artifact_id.in_(list(by_artifact)),
        )
        .order_by(KnowledgeFragment.ordinal)
        .limit(MAX_FRAGMENTS_PER_CLUSTER)
    ).all()

    nodes = []
    edges = []
    for fragment_id, artifact_id, content, location, kind, _ordinal in rows:
        artifact = by_artifact[artifact_id]
        nodes.append(
            {
                "id": f"fragment:{fragment_id}",
                "label": _summarise(content),
                "type": "fragment",
                "category": topic,
                "document_count": 1,
                "fragment_count": 1,
                "relationship_count": 1,
                "provenance": "registered",
                "source_artifact_id": str(artifact_id),
                "source_fragment_id": str(fragment_id),
                "source_location": location or {},
                "source_filename": artifact.filename,
                "source_title": artifact.title,
                "excerpt": content[:240],
                "kind": kind,
            }
        )
        edges.append(
            {
                "id": f"topic:{topic}|fragment:{fragment_id}",
                "source": f"topic:{topic}",
                "target": f"fragment:{fragment_id}",
                # Containment, not similarity: the fragment came from a
                # document the user confirmed carries this topic.
                "kind": "contains",
                "weight": 3,
                "relevance": "Highly Related",
            }
        )
    return {"nodes": nodes, "edges": edges}


def node_details(db: Session, owner_id: uuid.UUID, node_id: str) -> dict | None:
    """Everything the details panel shows, resolved on demand."""
    if node_id.startswith("topic:"):
        return _topic_details(db, owner_id, node_id[len("topic:") :])
    if node_id.startswith("fragment:"):
        try:
            fragment_uuid = uuid.UUID(node_id[len("fragment:") :])
        except ValueError:
            return None
        return _fragment_details(db, owner_id, fragment_uuid)
    return None


def _topic_details(db: Session, owner_id: uuid.UUID, topic: str) -> dict | None:
    artifacts = _registered_artifacts(db, owner_id)
    carrying = [a for a in artifacts if topic in a.topics]
    if not carrying:
        return None

    pairs: Counter = Counter()
    for artifact in artifacts:
        if topic not in artifact.topics:
            continue
        for other in artifact.topics:
            if other != topic:
                pairs[other] += 1

    # People and organizations only where a human confirmed them on a
    # registered artifact. Nothing is inferred, and nothing is invented.
    people: dict[str, list[str]] = defaultdict(list)
    for artifact in carrying:
        for person in artifact.metadata.get("people") or []:
            people[person].append(artifact.filename)

    fragment_total = db.scalar(
        select(func.count())
        .select_from(KnowledgeFragment)
        .where(
            KnowledgeFragment.owner_id == owner_id,
            KnowledgeFragment.artifact_id.in_([a.id for a in carrying]),
        )
    )

    return {
        "id": f"topic:{topic}",
        "label": topic,
        "type": "cluster",
        "category": topic,
        "description": (
            f"A topic confirmed on {len(carrying)} registered "
            f"document{'s' if len(carrying) != 1 else ''}."
        ),
        "provenance": "registered",
        "fragment_count": int(fragment_total or 0),
        "document_count": len(carrying),
        "related": [
            {
                "id": f"topic:{label}",
                "label": label,
                "relevance": _relevance(weight),
                # Says what the link is, so similarity is never read as a
                # verified semantic relationship.
                "explanation": (
                    f"Appears together on {weight} registered "
                    f"document{'s' if weight != 1 else ''}."
                ),
            }
            for label, weight in pairs.most_common(8)
        ],
        "documents": [
            {
                "artifact_id": str(a.id),
                "filename": a.filename,
                "title": a.title,
                "source_location": None,
                "excerpt": None,
            }
            for a in carrying[:10]
        ],
        "people": [
            {"name": name, "documents": sorted(set(files))} for name, files in people.items()
        ],
        "source_location": None,
    }


def _fragment_details(db: Session, owner_id: uuid.UUID, fragment_id: uuid.UUID) -> dict | None:
    row = db.execute(
        select(
            KnowledgeFragment.id,
            KnowledgeFragment.content,
            KnowledgeFragment.source_location,
            KnowledgeFragment.created_at,
            Artifact.id,
            Artifact.filename,
            Artifact.artifact_metadata,
        )
        .join(Artifact, Artifact.id == KnowledgeFragment.artifact_id)
        .where(KnowledgeFragment.id == fragment_id, KnowledgeFragment.owner_id == owner_id)
    ).first()
    if row is None:
        return None

    (_fid, content, location, created_at, artifact_id, filename, meta) = row
    meta = meta or {}
    topics = [t for t in (meta.get("topics") or []) if isinstance(t, str)]

    # Siblings from the same document: the only "related" a fragment has
    # without a similarity search, and honest about why they are related.
    siblings = db.execute(
        select(KnowledgeFragment.id, KnowledgeFragment.content, KnowledgeFragment.source_location)
        .where(
            KnowledgeFragment.artifact_id == artifact_id,
            KnowledgeFragment.id != fragment_id,
            KnowledgeFragment.owner_id == owner_id,
        )
        .limit(6)
    ).all()

    return {
        "id": f"fragment:{fragment_id}",
        "label": _summarise(content),
        "type": "fragment",
        "category": topics[0] if topics else "Knowledge",
        "description": content[:400],
        "provenance": "registered",
        "fragment_count": 1,
        "document_count": 1,
        "created_at": created_at,
        "source_artifact_id": str(artifact_id),
        "source_fragment_id": str(fragment_id),
        "source_location": location or {},
        "related": [
            {
                "id": f"fragment:{sid}",
                "label": _summarise(text),
                "relevance": "Related",
                "explanation": "From the same document.",
                "source_location": loc or {},
            }
            for sid, text, loc in siblings
        ],
        "documents": [
            {
                "artifact_id": str(artifact_id),
                "filename": filename,
                "title": meta.get("title"),
                "source_location": location or {},
                "excerpt": content[:240],
            }
        ],
        "people": [
            {"name": name, "documents": [filename]}
            for name in (meta.get("people") or [])
        ],
    }


def timeline(db: Session, owner_id: uuid.UUID) -> dict:
    """Registered artifacts placed in time, with the basis for each date.

    A date is only ever the one the document states or the one it was
    registered on. Nothing is inferred: an artifact with neither would be
    omitted rather than given a plausible date.
    """
    rows = db.execute(
        select(
            Artifact.id,
            Artifact.filename,
            Artifact.modality,
            Artifact.artifact_metadata,
            Artifact.registered_at,
        )
        .where(Artifact.owner_id == owner_id, Artifact.status == "registered")
        .order_by(Artifact.registered_at)
    ).all()

    # One query for the opening fragment of every artifact, so each card can
    # show what the document actually says rather than only its name. The
    # first chunk is the document's own opening — a quote, not a summary.
    # DISTINCT ON takes the lowest ordinal per artifact. Chunk ordinals start
    # at 1, not 0, so filtering on a fixed value silently found nothing.
    previews = dict(
        db.execute(
            select(KnowledgeFragment.artifact_id, KnowledgeFragment.content)
            .where(KnowledgeFragment.owner_id == owner_id)
            .distinct(KnowledgeFragment.artifact_id)
            .order_by(KnowledgeFragment.artifact_id, KnowledgeFragment.ordinal)
        ).all()
    )

    events = []
    for artifact_id, filename, modality, meta, registered_at in rows:
        meta = meta or {}
        stated = meta.get("created_date")
        date = stated if isinstance(stated, str) and stated else None
        basis = "document_metadata" if date else "registered_at"
        if not date:
            date = registered_at.date().isoformat() if registered_at else None
        if not date:
            continue
        topics = [t for t in (meta.get("topics") or []) if isinstance(t, str)]
        events.append(
            {
                "id": f"artifact:{artifact_id}",
                "artifact_id": str(artifact_id),
                "title": meta.get("title") or filename,
                "filename": filename,
                "date": date,
                "basis": basis,
                "category": topics[0] if topics else "Knowledge",
                "topics": topics,
                "description": (meta.get("description") or "")[:160] or None,
                # Verbatim from the document, so the card is a preview of the
                # real thing rather than a generated blurb.
                "preview": " ".join((previews.get(artifact_id) or "").split())[:280] or None,
                "modality": modality,
            }
        )

    return {"events": events}


def _summarise(content: str) -> str:
    """A fragment's label: its first clause, not a generated summary."""
    text = " ".join(content.split())
    if len(text) <= 60:
        return text
    cut = text[:60].rsplit(" ", 1)[0]
    return f"{cut}…"
