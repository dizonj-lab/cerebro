"""Turning a registered artifact into searchable knowledge fragments.

Only a registered artifact gets fragments. Registration means a human
reviewed the metadata, approved it, and the stored bytes re-verified against
their checksum — so nothing unapproved can reach retrieval.

The step is idempotent by content hash: re-registering an artifact, or
re-running after a partial failure, adds what is missing and leaves what is
already there alone.
"""
from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import FragmentEmbedding, KnowledgeFragment
from app.services import telemetry
from app.services.artifacts.chunking import chunk_blocks
from app.services.embeddings import EmbeddingFailed, get_embedding_provider


class FragmentsUnavailable(RuntimeError):
    """Fragments could not be built for a registered artifact."""


def build_for_artifact(db: Session, artifact: Artifact, *, document) -> int:
    """Create missing fragments and their vectors. Returns how many were added.

    Raises rather than registering an artifact that cannot be retrieved. A
    registered artifact that is silently unsearchable is worse than a
    refusal: the library would show it as trusted evidence that no query can
    ever reach.
    """
    if artifact.status != "registered":
        raise FragmentsUnavailable(
            "Fragments are only built for registered artifacts; "
            f"this one is '{artifact.status}'."
        )
    if document is None:
        raise FragmentsUnavailable(
            "The extracted text for this artifact could not be read, so no "
            "fragments can be built from it."
        )

    chunks = chunk_blocks(document.blocks)
    if not chunks:
        raise FragmentsUnavailable("Extraction produced no text to build fragments from.")

    existing = set(
        db.scalars(
            select(KnowledgeFragment.content_sha256).where(
                KnowledgeFragment.artifact_id == artifact.id
            )
        ).all()
    )
    pending = [c for c in chunks if c.content_sha256 not in existing]
    if not pending:
        return 0

    provider = get_embedding_provider()
    try:
        vectors = provider.embed([c.content for c in pending])
    except EmbeddingFailed as exc:
        # Deliberately not falling back to another provider: a different
        # provider writes a different vector space, and a cloud one would
        # send content the user did not consent to send.
        raise FragmentsUnavailable(str(exc)) from None

    if len(vectors) != len(pending):
        raise FragmentsUnavailable(
            f"The embedding provider returned {len(vectors)} vectors for "
            f"{len(pending)} fragments."
        )

    # Fragments are inserted and flushed before their embeddings. There is no
    # ORM relationship between the two to order the inserts, so without this
    # the embedding can reach the database first and violate its foreign key.
    fragment_ids = []
    for chunk in pending:
        fragment_id = uuid.uuid4()
        fragment_ids.append(fragment_id)
        db.add(
            KnowledgeFragment(
                id=fragment_id,
                owner_id=artifact.owner_id,
                artifact_id=artifact.id,
                ordinal=chunk.ordinal,
                content=chunk.content,
                content_sha256=chunk.content_sha256,
                source_location=chunk.source_location,
                kind=chunk.kind,
            )
        )
    db.flush()

    for fragment_id, vector in zip(fragment_ids, vectors, strict=True):
        db.add(
            FragmentEmbedding(
                fragment_id=fragment_id,
                owner_id=artifact.owner_id,
                provider=provider.name,
                model=provider.model,
                dimensions=provider.dimensions,
                vector=list(vector),
            )
        )
    db.flush()
    return len(pending)


def count_for_artifact(db: Session, artifact_id: uuid.UUID) -> int:
    return len(
        db.scalars(
            select(KnowledgeFragment.id).where(KnowledgeFragment.artifact_id == artifact_id)
        ).all()
    )


def backfill_embeddings(db: Session, owner_id: uuid.UUID, *, limit: int = 500) -> dict:
    """Embed this owner's fragments that have no vector for the active model.

    Retrieval filters on provider, model and width together, so a fragment
    embedded under a different model is not retrievable now — however many
    vectors it has. That happens for two ordinary reasons: the daemon was not
    running when the document was registered, or the user moved to a better
    embedder. Either way the fix is the same, and it is not a migration: the
    old vectors are left in place, so switching back needs no re-embedding.

    Fragments are only ever created for registered artifacts, so nothing here
    can pull unapproved content into retrieval.
    """
    provider = get_embedding_provider()

    has_vector = (
        select(FragmentEmbedding.fragment_id)
        .where(
            FragmentEmbedding.fragment_id == KnowledgeFragment.id,
            FragmentEmbedding.provider == provider.name,
            FragmentEmbedding.model == provider.model,
            FragmentEmbedding.dimensions == provider.dimensions,
        )
        .exists()
    )
    missing = db.execute(
        select(KnowledgeFragment.id, KnowledgeFragment.content)
        .where(KnowledgeFragment.owner_id == owner_id, ~has_vector)
        .order_by(KnowledgeFragment.ordinal)
        .limit(limit)
    ).all()

    if not missing:
        return {
            "provider": provider.name,
            "model": provider.model,
            "dimensions": provider.dimensions,
            "embedded": 0,
            "remaining": 0,
        }

    started = time.perf_counter()
    try:
        vectors = provider.embed([content for _, content in missing])
    except EmbeddingFailed as exc:
        # No fallback provider, for the same reason as registration: a
        # different provider writes a different space.
        raise FragmentsUnavailable(str(exc)) from None

    for (fragment_id, _), vector in zip(missing, vectors, strict=True):
        db.add(
            FragmentEmbedding(
                fragment_id=fragment_id,
                owner_id=owner_id,
                provider=provider.name,
                model=provider.model,
                dimensions=provider.dimensions,
                vector=list(vector),
            )
        )
    db.flush()

    telemetry.record(
        "embeddings.backfill",
        model=f"{provider.name}/{provider.model}",
        duration_ms=int((time.perf_counter() - started) * 1000),
        algorithm=f"{provider.dimensions}-dimensional embedding",
        detail=f"{len(missing)} fragments",
    )

    remaining = db.scalar(
        select(func.count())
        .select_from(KnowledgeFragment)
        .where(KnowledgeFragment.owner_id == owner_id, ~has_vector)
    )
    return {
        "provider": provider.name,
        "model": provider.model,
        "dimensions": provider.dimensions,
        "embedded": len(missing),
        "remaining": remaining or 0,
    }
