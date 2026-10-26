"""How alike two parts of the library are, measured from their embeddings.

The Galaxy's other edges are observations about documents: two topics carried
by one file, an entity named in one. This module adds the one thing those
cannot see — that passages about two topics *say similar things* even when no
document carries both. It is a measurement, so it is stated as one: a cosine
similarity between L2-normalised vectors, written as a percentage, with the
model that produced the vectors named beside it.

Three rules:

* **One space at a time.** Only vectors from the owner's current provider,
  model and width are read, exactly as search does. A similarity across two
  embedding spaces is a number with no meaning.
* **Relative, not absolute.** What counts as "similar" depends on the model
  and on the library: a learned model puts unrelated text near 0.3, the
  hashing embedder near 0.05. So the yardstick is this library's own
  *typical* similarity between two of its topics, recomputed on every
  request. A line is drawn only where something is more alike than that,
  and its strength is how far above it sits. New documents move the
  yardstick, which is the point.
* **Similar is not related.** Two passages about audio and speech being 71%
  alike is a fact about their vectors; it does not establish that one topic
  uses, causes or depends on the other, and nothing here says so.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from statistics import fmean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fragment import FragmentEmbedding, KnowledgeFragment
from app.services import ingest_settings
from app.services.embeddings import provider_for

# Topic pairs this far above typical are drawn on the opening view; capped so
# meaning-based lines never outnumber the documented ones.
TOPIC_EDGE_SIGMAS = 1.0
MAX_TOPIC_EDGES = 12
# A passage links to at most this many other topics, strongest first.
MAX_AFFINITIES = 3
# Strength runs from "just above typical" (0) to this far above it (1).
MIN_STRENGTH_SPAN = 0.05
# The lens: how many passages it names as nearest to the text it was given.
LENS_PASSAGES = 3


@dataclass
class Space:
    """The embedding space every similarity in one response was measured in."""

    provider: str
    model: str
    dimensions: int
    # A learned model compares meaning; the hashing embedder compares words.
    learned: bool

    @property
    def measures(self) -> str:
        return "meaning" if self.learned else "shared words"

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "dimensions": self.dimensions,
            "learned": self.learned,
            "measures": self.measures,
        }


@dataclass
class Library:
    """One owner's vectors, grouped by the topics their documents carry."""

    space: Space
    # fragment id -> (artifact id, vector)
    vectors: dict[uuid.UUID, tuple[uuid.UUID, list[float]]] = field(default_factory=dict)
    # topic -> normalised mean of its passages' vectors
    centroids: dict[str, list[float]] = field(default_factory=dict)
    # The yardstick: mean and spread of similarity between two of the topics.
    typical: float | None = None
    spread: float = 0.0
    # Highest topic-to-topic similarity, the top of the strength scale.
    ceiling: float | None = None


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _normalised(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


def _mean(vectors: list[list[float]]) -> list[float]:
    total = [0.0] * len(vectors[0])
    for vector in vectors:
        for i, x in enumerate(vector):
            total[i] += x
    return [x / len(vectors) for x in total]


def space_for(db: Session, owner_id: uuid.UUID) -> Space:
    provider = provider_for(ingest_settings.for_user(db, owner_id))
    return Space(
        provider=provider.name,
        model=provider.model,
        dimensions=provider.dimensions,
        learned=provider.name != "hashing",
    )


def library(
    db: Session, owner_id: uuid.UUID, topics_by_artifact: dict[uuid.UUID, list[str]]
) -> Library:
    """Centroids for the given topics, and the library's typical similarity.

    `topics_by_artifact` is the registered artifacts and their confirmed
    topics, so nothing unapproved shapes a centroid.
    """
    space = space_for(db, owner_id)
    found = Library(space=space)
    rows = db.execute(
        select(
            FragmentEmbedding.fragment_id, KnowledgeFragment.artifact_id, FragmentEmbedding.vector
        )
        .join(KnowledgeFragment, KnowledgeFragment.id == FragmentEmbedding.fragment_id)
        .where(
            FragmentEmbedding.owner_id == owner_id,
            FragmentEmbedding.provider == space.provider,
            FragmentEmbedding.model == space.model,
            FragmentEmbedding.dimensions == space.dimensions,
            KnowledgeFragment.artifact_id.in_(list(topics_by_artifact)),
        )
    ).all()

    grouped: dict[str, list[list[float]]] = {}
    for fragment_id, artifact_id, vector in rows:
        found.vectors[fragment_id] = (artifact_id, list(vector))
        for topic in topics_by_artifact.get(artifact_id, []):
            grouped.setdefault(topic, []).append(list(vector))

    found.centroids = {topic: _normalised(_mean(vs)) for topic, vs in grouped.items() if vs}

    pairs = [
        _dot(found.centroids[a], found.centroids[b])
        for i, a in enumerate(sorted(found.centroids))
        for b in sorted(found.centroids)[i + 1 :]
    ]
    if pairs:
        found.typical = fmean(pairs)
        found.spread = pstdev(pairs) if len(pairs) > 1 else 0.0
        found.ceiling = max(pairs)
    return found


def strength(similarity: float, lib: Library) -> float:
    """0 at the library's typical similarity, 1 at (or beyond) its strongest pair."""
    if lib.typical is None:
        return 0.0
    span = max((lib.ceiling or lib.typical) - lib.typical, MIN_STRENGTH_SPAN)
    return round(min(1.0, max(0.0, (similarity - lib.typical) / span)), 3)


def strength_word(value: float) -> str:
    if value >= 0.66:
        return "Strong similarity"
    if value >= 0.33:
        return "Moderate similarity"
    return "Weak similarity"


def percent(similarity: float) -> int:
    return round(similarity * 100)


def summary(lib: Library) -> dict:
    """What the legend says about how similarity was measured here."""
    return {
        **lib.space.describe(),
        "typical": None if lib.typical is None else round(lib.typical, 4),
        "topic_threshold": (
            None if lib.typical is None else round(lib.typical + TOPIC_EDGE_SIGMAS * lib.spread, 4)
        ),
        "ceiling": None if lib.ceiling is None else round(lib.ceiling, 4),
        "vectors": len(lib.vectors),
        "topics_measured": len(lib.centroids),
    }


def topic_pairs(lib: Library) -> list[tuple[str, str, float]]:
    """Topic pairs notably more alike than two of this library's topics usually are."""
    if lib.typical is None:
        return []
    threshold = lib.typical + TOPIC_EDGE_SIGMAS * lib.spread
    names = sorted(lib.centroids)
    found = [
        (a, b, _dot(lib.centroids[a], lib.centroids[b]))
        for i, a in enumerate(names)
        for b in names[i + 1 :]
    ]
    kept = [pair for pair in found if pair[2] > threshold]
    kept.sort(key=lambda pair: -pair[2])
    return kept[:MAX_TOPIC_EDGES]


def affinities(
    lib: Library, fragment_id: uuid.UUID, own_topic: str
) -> tuple[float | None, list[tuple[str, float]]]:
    """How well a passage fits its own topic, and which others it resembles.

    Another topic is listed only where the passage is more alike to it than
    two of the library's topics typically are to each other — "a little
    similarity" — strongest first. An empty list means the passage resembles
    nothing outside its own topic, which is where it is then drawn.
    """
    entry = lib.vectors.get(fragment_id)
    if entry is None or lib.typical is None:
        return None, []
    vector = entry[1]
    own = lib.centroids.get(own_topic)
    fit = _dot(vector, own) if own else None
    others = [
        (topic, _dot(vector, centroid))
        for topic, centroid in lib.centroids.items()
        if topic != own_topic
    ]
    above = sorted((pair for pair in others if pair[1] > lib.typical), key=lambda pair: -pair[1])
    return fit, above[:MAX_AFFINITIES]


def lens(
    lib: Library, vector: list[float]
) -> tuple[list[tuple[str, float]], list[tuple[uuid.UUID, float]]]:
    """Where a piece of text would sit: its similarity to every topic, and the nearest passages."""
    topics = sorted(
        ((topic, _dot(vector, centroid)) for topic, centroid in lib.centroids.items()),
        key=lambda pair: -pair[1],
    )
    passages = sorted(
        ((fragment_id, _dot(vector, v)) for fragment_id, (_, v) in lib.vectors.items()),
        key=lambda pair: -pair[1],
    )[:LENS_PASSAGES]
    return topics, passages
