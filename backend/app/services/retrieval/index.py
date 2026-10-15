"""Vector search over fragment embeddings.

The index is an interface with one implementation: brute-force cosine over
PostgreSQL `float4[]` columns. pgvector is not available in the target
database, and at this scale an exact scan is both correct and fast enough.
The interface exists so an approximate index can replace it later without
changing any caller.

Two properties are not negotiable:

* every query is scoped to one owner, in the predicate rather than filtered
  afterwards, so a crafted request cannot reach another user's fragments;
* only vectors from the same provider, model and dimensions are compared. A
  cosine similarity across two embedding spaces is a number with no meaning,
  so mixing them would quietly produce nonsense rankings.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import FragmentEmbedding, KnowledgeFragment


@dataclass
class Match:
    fragment_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_filename: str
    artifact_title: str | None
    content: str
    source_location: dict
    kind: str
    score: float


class VectorIndex(Protocol):
    def search(
        self,
        db: Session,
        *,
        owner_id: uuid.UUID,
        vector: list[float],
        provider: str,
        model: str,
        dimensions: int,
        limit: int = 10,
    ) -> list[Match]: ...


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


class PostgresBruteForceIndex:
    """Exact cosine search by scanning the owner's vectors.

    Vectors are L2-normalised on write, so cosine similarity is a dot
    product and no per-query normalisation is needed.

    The scan happens in Python rather than SQL because expressing a dot
    product over `float4[]` without pgvector needs an `unnest` subquery per
    row, which is slower and considerably harder to read. The cost is that
    one owner's vectors are held in memory for the length of a query — fine
    for a personal knowledge store, and the reason this sits behind an
    interface.
    """

    def search(
        self,
        db: Session,
        *,
        owner_id: uuid.UUID,
        vector: list[float],
        provider: str,
        model: str,
        dimensions: int,
        limit: int = 10,
    ) -> list[Match]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if len(vector) != dimensions:
            raise ValueError(
                f"Query vector has {len(vector)} dimensions, expected {dimensions}."
            )

        rows = db.execute(
            select(
                KnowledgeFragment.id,
                KnowledgeFragment.artifact_id,
                Artifact.filename,
                Artifact.artifact_metadata,
                KnowledgeFragment.content,
                KnowledgeFragment.source_location,
                KnowledgeFragment.kind,
                FragmentEmbedding.vector,
            )
            .join(FragmentEmbedding, FragmentEmbedding.fragment_id == KnowledgeFragment.id)
            .join(Artifact, Artifact.id == KnowledgeFragment.artifact_id)
            .where(
                # Owner scoping is part of the predicate, not a later check.
                KnowledgeFragment.owner_id == owner_id,
                FragmentEmbedding.provider == provider,
                FragmentEmbedding.model == model,
                FragmentEmbedding.dimensions == dimensions,
            )
        ).all()

        matches = [
            match
            for match in (
                Match(
                    fragment_id=row[0],
                    artifact_id=row[1],
                    artifact_filename=row[2],
                    artifact_title=(row[3] or {}).get("title"),
                    content=row[4],
                    source_location=row[5] or {},
                    kind=row[6],
                    score=_dot(vector, list(row[7])),
                )
                for row in rows
            )
            # A zero or negative similarity is not a weak match, it is no
            # relationship at all. Returning such a fragment would present
            # an unrelated passage as evidence.
            if match.score > 0.0
        ]
        # Ties broken by content so the ordering is stable run to run.
        matches.sort(key=lambda m: (-m.score, m.content))
        return matches[:limit]


_index: VectorIndex = PostgresBruteForceIndex()


def get_index() -> VectorIndex:
    return _index
