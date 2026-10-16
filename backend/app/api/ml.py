"""What CEREBRO's AI and ML actually consists of, right now.

One endpoint behind GOD MODE and the AI settings. It reports what is
installed, what is selected, what ran, and where coverage is incomplete —
measured, never asserted. Everything here is about this deployment, not
about the user's documents, so no document content passes through it.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.fragment import FragmentEmbedding, KnowledgeFragment
from app.services import ollama, telemetry
from app.services.embeddings import get_embedding_provider

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/status")
def status(current_user: CurrentUser, db: DbSession) -> dict:
    found = ollama.discover()
    provider = get_embedding_provider()

    # Coverage is counted against the *active* provider, model and width,
    # because that is what retrieval filters on: a fragment embedded under a
    # different model is not retrievable now, however many vectors exist.
    total = db.scalar(
        select(func.count()).select_from(KnowledgeFragment).where(
            KnowledgeFragment.owner_id == current_user.id
        )
    )
    embedded = db.scalar(
        select(func.count())
        .select_from(KnowledgeFragment)
        .join(FragmentEmbedding, FragmentEmbedding.fragment_id == KnowledgeFragment.id)
        .where(
            KnowledgeFragment.owner_id == current_user.id,
            FragmentEmbedding.provider == provider.name,
            FragmentEmbedding.model == provider.model,
            FragmentEmbedding.dimensions == provider.dimensions,
        )
    )

    return {
        "ollama": {
            "reachable": found.reachable,
            "base_url": found.base_url,
            "models": found.models,
            "answering_model": found.chat_model(),
            "embedding_model": found.embedding_model(),
            "error": found.error,
        },
        "embeddings": {
            "provider": provider.name,
            "model": provider.model,
            "dimensions": provider.dimensions,
            # A hashing vector is a deterministic projection, not a learned
            # representation. Saying so is the point of this field.
            "pretrained": provider.name != "hashing",
            "fragments": total or 0,
            "embedded": embedded or 0,
            "missing": max((total or 0) - (embedded or 0), 0),
        },
        "retrieval": {
            "vector_index": "exact cosine scan over float4[] (no pgvector)",
            "keyword_index": "postgresql full-text, GIN",
            "fusion": "reciprocal rank fusion, k=60",
        },
        "operations": telemetry.recent(),
    }


@router.post("/embeddings/backfill")
def backfill(current_user: CurrentUser, db: DbSession, limit: int = 500) -> dict:
    """Embed this owner's fragments that have no vector for the active model.

    Needed because the embedder can change — a daemon that was not running
    when a document was registered, or a deliberate switch to a better model.
    Vectors are per provider, model and width, so the old ones are left
    alone rather than deleted: if the user switches back, they are still
    there and still correct.
    """
    from app.services.artifacts.fragments import (
        FragmentsUnavailable,
        backfill_embeddings,
    )

    try:
        result = backfill_embeddings(db, current_user.id, limit=limit)
    except FragmentsUnavailable as exc:
        # The embedder is unavailable. Nothing is written, and nothing is
        # embedded by a different provider to paper over it.
        db.rollback()
        raise HTTPException(
            status_code=503, detail=str(exc)
        ) from None
    db.commit()
    return result
