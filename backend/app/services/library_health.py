"""Library health: why the Galaxy and Recall look the way they do, measured from the owner's
registered knowledge.

Read-only. Nothing here writes, re-embeds or re-labels; it reports what the existing tables already
hold, so the owner can see where noise comes from before changing anything:

* **Topics.** The Galaxy draws a topic's links only when two or more registered documents share it.
  Topics confirmed on a single document, generic terms ("PDF", "system") and several spellings of
  one concept are what turn a galaxy into islands.
* **Embeddings.** A fragment is only retrievable by the model the owner's queries are embedded with.
  Vectors written under another provider, model or width are invisible to Recall and Search.
* **Stated links.** A document that names another registered document in its own text makes a claim
  CEREBRO can quote: "this proof of concept implements the CEREBRO Solution Architecture". Each
  candidate carries the sentence and its location. Nothing is inferred beyond the words used.
* **Similar documents.** Documents whose averaged fragment vectors are each other's nearest
  neighbours. An observation with a score, never a relationship.
"""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import FragmentEmbedding, KnowledgeFragment
from app.services import ingest_settings
from app.services.artifacts.enrichment.significance import canonical, is_generic
from app.services.graph import MAX_CLUSTERS, STRONG_EDGE_WEIGHT

# A title shorter than this is too likely to occur by accident ("Notes", "Plan") to count as a
# mention.
MIN_TITLE_WORDS = 3
# Similar documents: each must be among the other's nearest few, which removes most incidental
# likeness.
NEIGHBOURS = 3

# The verb near a mention, read as the relationship the document states. Order matters: the first
# pattern found in the sentence wins, and anything else is recorded as a plain mention rather than
# guessed at.
RELATIONS: list[tuple[str, str]] = [
    ("supersedes", r"\b(supersedes?|replaces?|replaced)\b"),
    ("implements", r"\b(implements?|implemented)\b"),
    ("extends", r"\b(extends?|extended|builds? on|built on)\b"),
    ("evaluates", r"\b(evaluates?|evaluated|measured against|benchmarks?)\b"),
    ("responds to", r"\b(responds? to|in response to)\b"),
    ("cites", r"\b(cites?|cited|according to|as described in|see)\b"),
    ("applies", r"\b(applies|applied|follows|following|uses|reuses)\b"),
    ("deploys", r"\b(deploys?|deployed|hosts?|hosted)\b"),
]
_COMPILED_RELATIONS = [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in RELATIONS]
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


_DATE = re.compile(
    r"^(\d{1,2}\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?(\s+\d{1,2})?,?(\s+\d{4})?$|^\d{4}$|^q[1-4]\s*\d{4}$",
    re.IGNORECASE,
)
ENTITY_FIELDS = ("people", "organizations", "projects", "technologies")


def suspect_reason(topic: str, entities: set[str]) -> tuple[str, str] | None:
    """(severity, reason) when a confirmed topic is unlikely to be a subject, else None. Reported,
    never acted on.

    "noise" is decidable from the term itself: a date, a broken word, a name in the wrong field.
    "check" is a lone plain word, which is sometimes a real subject ("Provenance") and sometimes
    filler ("Answer"); telling them apart needs the owner, so it is only listed for them.
    """
    t = " ".join(topic.split())
    if _DATE.match(t):
        return "noise", "a date, not a subject (the Timeline already reads dates)"
    if t.endswith("-") or t.startswith("-") or not re.search(r"[A-Za-z]{2}", t):
        return "noise", "a broken fragment of a word"
    if canonical(t) in entities:
        return "noise", "a name; it belongs under people, organisations, projects or technologies"
    words = t.split()
    if (
        len(words) == 1
        and t[:1].isupper()
        and t[1:].islower()
        and not any(ch.isdigit() for ch in t)
    ):
        return "check", "a single word; keep it only if it names a subject"
    return None


@dataclass
class _Doc:
    id: uuid.UUID
    filename: str
    title: str
    topics: list[str]
    entities: tuple[str, ...] = ()


def _registered(db: Session, owner_id: uuid.UUID) -> list[_Doc]:
    rows = db.execute(
        select(Artifact.id, Artifact.filename, Artifact.artifact_metadata).where(
            Artifact.owner_id == owner_id, Artifact.status == "registered"
        )
    ).all()
    out = []
    for artifact_id, filename, meta in rows:
        meta = meta or {}
        topics = [t for t in (meta.get("topics") or []) if isinstance(t, str) and t.strip()]
        entities = tuple(
            v for f in ENTITY_FIELDS for v in (meta.get(f) or []) if isinstance(v, str)
        )
        out.append(_Doc(artifact_id, filename, meta.get("title") or filename, topics, entities))
    return out


# ---------------------------------------------------------------- topics


def topic_health(db: Session, owner_id: uuid.UUID) -> dict:
    """How the confirmed topics are distributed, and what the Galaxy would draw from them today."""
    docs = _registered(db, owner_id)
    per_key: dict[str, set[uuid.UUID]] = defaultdict(set)
    spellings: dict[str, Counter] = defaultdict(Counter)
    for doc in docs:
        for topic in doc.topics:
            key = canonical(topic)
            per_key[key].add(doc.id)
            spellings[key][topic] += 1

    topics = [
        {
            "topic": spellings[key].most_common(1)[0][0],
            "documents": len(ids),
            "spellings": sorted(spellings[key]),
            "generic": is_generic(key),
        }
        for key, ids in per_key.items()
    ]
    topics.sort(key=lambda t: (-t["documents"], t["topic"].lower()))
    # Names confirmed anywhere in the library, plus the people and projects that sit in topics by
    # mistake: a topic that is also confirmed as an entity on any document is a name, wherever it
    # appears.
    entities = {canonical(v) for d in docs for v in d.entities}
    for t in topics:
        t["suspect"] = (
            ("noise", "a generic term naming the medium")
            if t["generic"]
            else suspect_reason(t["topic"], entities)
        )

    # What graph.galaxy does today: the most frequent raw labels, and pairs that share documents.
    raw = Counter(t for doc in docs for t in doc.topics)
    shown = [label for label, _ in raw.most_common(MAX_CLUSTERS)]
    shown_set = set(shown)
    pairs: Counter = Counter()
    for doc in docs:
        present = sorted({t for t in doc.topics if t in shown_set})
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                pairs[(a, b)] += 1

    return {
        "documents": len(docs),
        "documents_without_topics": sorted(d.title for d in docs if not d.topics),
        "distinct_topics": len(topics),
        "single_document_topics": sum(t["documents"] == 1 for t in topics),
        "generic_topics": [t["topic"] for t in topics if t["generic"]],
        "suspect_topics": [
            {
                "topic": t["topic"],
                "documents": t["documents"],
                "severity": t["suspect"][0],
                "reason": t["suspect"][1],
            }
            for t in topics
            if t["suspect"]
        ],
        "variant_spellings": [t for t in topics if len(t["spellings"]) > 1],
        "topics": topics,
        "galaxy_now": {
            "clusters": shown,
            "clusters_on_one_document": [t for t in shown if raw[t] == 1],
            "edges": len(pairs),
            "recurring_edges": sum(1 for n in pairs.values() if n >= STRONG_EDGE_WEIGHT),
        },
    }


# ---------------------------------------------------------------- embeddings


def _active_space(db: Session, owner_id: uuid.UUID) -> tuple[str, str, int] | None:
    """The provider, model and width the owner's queries are embedded with right now."""
    from app.services.embeddings import provider_for

    try:
        provider = provider_for(ingest_settings.for_user(db, owner_id))
    except Exception:  # an unreachable daemon is a finding, not a crash
        return None
    return provider.name, provider.model, provider.dimensions


def embedding_health(db: Session, owner_id: uuid.UUID) -> dict:
    """Which embedding spaces the fragments are in, and how many today's queries cannot see."""
    total = (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeFragment)
            .where(KnowledgeFragment.owner_id == owner_id)
        )
        or 0
    )
    spaces = db.execute(
        select(
            FragmentEmbedding.provider,
            FragmentEmbedding.model,
            FragmentEmbedding.dimensions,
            func.count(),
        )
        .where(FragmentEmbedding.owner_id == owner_id)
        .group_by(FragmentEmbedding.provider, FragmentEmbedding.model, FragmentEmbedding.dimensions)
    ).all()
    active = _active_space(db, owner_id)
    in_active = next((n for p, m, d, n in spaces if (p, m, d) == active), 0)

    docs_missing: list[str] = []
    if active:
        covered = set(
            db.scalars(
                select(KnowledgeFragment.artifact_id)
                .join(FragmentEmbedding, FragmentEmbedding.fragment_id == KnowledgeFragment.id)
                .where(
                    KnowledgeFragment.owner_id == owner_id,
                    FragmentEmbedding.provider == active[0],
                    FragmentEmbedding.model == active[1],
                    FragmentEmbedding.dimensions == active[2],
                )
                .distinct()
            )
        )
        docs_missing = sorted(d.title for d in _registered(db, owner_id) if d.id not in covered)

    return {
        "active": {"provider": active[0], "model": active[1], "dimensions": active[2]}
        if active
        else None,
        "fragments": total,
        "fragments_searchable": in_active,
        "fragments_invisible": total - in_active,
        "documents_not_searchable": docs_missing,
        "spaces": [
            {"provider": p, "model": m, "dimensions": d, "fragments": n} for p, m, d, n in spaces
        ],
    }


# ---------------------------------------------------------------- stated links


def _needles(doc: _Doc) -> list[str]:
    """Ways another document might name this one: its title, the subject half of a "Kind: Subject"
        title, and the title without a parenthetical. The kind half ("Lecture 3", "Group 7 Meeting
        Minutes") is not used: it names a series, and
    matching it links every document of that series to every other.
    """
    candidates = [doc.title, re.sub(r"\s*\([^)]*\)", "", doc.title)]
    if ":" in doc.title:
        candidates.append(doc.title.split(":", 1)[1].strip())
    stem = re.sub(r"\.[a-z0-9]+$", "", doc.filename, flags=re.IGNORECASE)
    candidates.append(re.sub(r"[-_]+", " ", re.sub(r"^\d+[-_ ]*", "", stem)))
    out = []
    for c in candidates:
        c = " ".join(c.split())
        if (
            len(c.split()) >= MIN_TITLE_WORDS
            and not is_generic(c)
            and c.lower() not in (o.lower() for o in out)
        ):
            out.append(c)
    return out


def _relation(sentence: str) -> str:
    for label, pattern in _COMPILED_RELATIONS:
        if pattern.search(sentence):
            return label
    return "mentions"


def stated_links(db: Session, owner_id: uuid.UUID) -> list[dict]:
    """Registered documents that name another registered document, with the sentence that does."""
    docs = _registered(db, owner_id)
    by_id = {d.id: d for d in docs}
    # A phrase that names more than one document identifies none of them.
    needles = {d.id: _needles(d) for d in docs}
    seen = Counter(n.lower() for ns in needles.values() for n in ns)
    patterns = {
        d_id: re.compile("|".join(rf"\b{re.escape(n)}\b" for n in unique), re.IGNORECASE)
        for d_id, ns in needles.items()
        if (unique := [n for n in ns if seen[n.lower()] == 1])
    }
    if not patterns:
        return []

    fragments = db.execute(
        select(
            KnowledgeFragment.id,
            KnowledgeFragment.artifact_id,
            KnowledgeFragment.content,
            KnowledgeFragment.source_location,
        )
        .join(Artifact, Artifact.id == KnowledgeFragment.artifact_id)
        .where(KnowledgeFragment.owner_id == owner_id, Artifact.status == "registered")
        .order_by(KnowledgeFragment.artifact_id, KnowledgeFragment.ordinal)
    ).all()

    found: dict[tuple[uuid.UUID, uuid.UUID], dict] = {}
    for fragment_id, source_id, content, location in fragments:
        for sentence in _SENTENCE.findall(content or ""):
            # A document's own title line is not a reference to anything.
            if sentence.strip().rstrip(".").lower() == by_id[source_id].title.lower():
                continue
            for target_id, pattern in patterns.items():
                if target_id == source_id or not pattern.search(sentence):
                    continue
                key = (source_id, target_id)
                if key in found:
                    found[key]["mentions"] += 1
                    continue
                found[key] = {
                    "source": by_id[source_id].title,
                    "target": by_id[target_id].title,
                    "relation": _relation(sentence),
                    "evidence": " ".join(sentence.split()),
                    "location": {
                        k: v
                        for k, v in (location or {}).items()
                        if k in ("page", "slide", "section", "paragraph")
                    },
                    "fragment_id": str(fragment_id),
                    "mentions": 1,
                }
    return sorted(found.values(), key=lambda link: (link["source"], link["target"]))


# ---------------------------------------------------------------- similar documents


def similar_documents(db: Session, owner_id: uuid.UUID, neighbours: int = NEIGHBOURS) -> list[dict]:
    """Documents that are each other's nearest neighbours by averaged fragment vector, in the active
    space.

    Mutual nearest neighbours rather than a global threshold, because cosine values mean different
    things in different embedding spaces; a fixed cut-off tuned for one model is noise for another.
    """
    active = _active_space(db, owner_id)
    if not active:
        return []
    rows = db.execute(
        select(KnowledgeFragment.artifact_id, FragmentEmbedding.vector)
        .join(FragmentEmbedding, FragmentEmbedding.fragment_id == KnowledgeFragment.id)
        .join(Artifact, Artifact.id == KnowledgeFragment.artifact_id)
        .where(
            KnowledgeFragment.owner_id == owner_id,
            Artifact.status == "registered",
            FragmentEmbedding.provider == active[0],
            FragmentEmbedding.model == active[1],
            FragmentEmbedding.dimensions == active[2],
        )
    ).all()
    sums: dict[uuid.UUID, list[float]] = {}
    for artifact_id, vector in rows:
        acc = sums.setdefault(artifact_id, [0.0] * len(vector))
        for i, x in enumerate(vector):
            acc[i] += x
    centroids = {}
    for artifact_id, acc in sums.items():
        norm = math.sqrt(sum(x * x for x in acc)) or 1.0
        centroids[artifact_id] = [x / norm for x in acc]

    ids = list(centroids)
    score = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            score[(a, b)] = score[(b, a)] = sum(
                x * y for x, y in zip(centroids[a], centroids[b], strict=False)
            )
    nearest = {
        a: {
            b for b in sorted((b for b in ids if b != a), key=lambda b: -score[(a, b)])[:neighbours]
        }
        for a in ids
    }

    docs = {d.id: d for d in _registered(db, owner_id)}
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if b in nearest[a] and a in nearest[b]:
                shared = sorted(
                    {canonical(t) for t in docs[a].topics} & {canonical(t) for t in docs[b].topics}
                )
                pairs.append(
                    {
                        "a": docs[a].title,
                        "b": docs[b].title,
                        "score": round(score[(a, b)], 3),
                        "shared_topics": shared,
                    }
                )
    return sorted(pairs, key=lambda p: -p["score"])


# ---------------------------------------------------------------- the whole report


def report(db: Session, owner_id: uuid.UUID) -> dict:
    return {
        "topics": topic_health(db, owner_id),
        "embeddings": embedding_health(db, owner_id),
        "stated_links": stated_links(db, owner_id),
        "similar_documents": similar_documents(db, owner_id),
    }
