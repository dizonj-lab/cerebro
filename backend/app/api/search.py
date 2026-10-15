"""Search over the owner's registered knowledge.

Only fragments of registered artifacts exist, so an unapproved artifact can
never appear in results. Every query is scoped to the authenticated user:
the owner comes from the session, never from the request.
"""
from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.search import SearchMatch, SearchRequest, SearchResponse
from app.services.embeddings import EmbeddingFailed, get_embedding_provider
from app.services.retrieval import get_index

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def search(payload: SearchRequest, current_user: CurrentUser, db: DbSession) -> SearchResponse:
    provider = get_embedding_provider()
    try:
        vector = provider.embed([payload.query])[0]
    except EmbeddingFailed as exc:
        # The query cannot be embedded, so there is nothing to compare. Say
        # so rather than returning an empty result set, which would read as
        # "nothing matches".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None

    matches = get_index().search(
        db,
        owner_id=current_user.id,
        vector=vector,
        provider=provider.name,
        model=provider.model,
        dimensions=provider.dimensions,
        limit=payload.limit,
    )

    return SearchResponse(
        matches=[SearchMatch(**m.__dict__) for m in matches],
        total=len(matches),
        provider=provider.name,
        model=provider.model,
        dimensions=provider.dimensions,
    )
