"""Unified search over the owner's library and registered knowledge.

Only fragments of registered artifacts exist, so an unapproved artifact can
never appear as knowledge. Documents match at any status, and carry that
status with them. Every query is scoped to the authenticated user: the owner
comes from the session, never from the request.
"""
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.search import (
    SearchMatch,
    SearchRequest,
    SearchResponse,
    SuggestionsResponse,
)
from app.services import search as search_service
from app.services.embeddings import get_embedding_provider

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def search(payload: SearchRequest, current_user: CurrentUser, db: DbSession) -> SearchResponse:
    result = search_service.search(
        db,
        current_user.id,
        query=payload.query,
        mode=payload.mode,
        scope=payload.scope,
        filters=search_service.Filters(**payload.filters.model_dump()),
        limit=payload.limit,
    )

    # The provider is reported even for a keyword-only query, so a caller can
    # always tell which space any scores it does receive came from.
    provider = get_embedding_provider()
    matches = [
        SearchMatch(
            fragment_id=item["fragment_id"],
            artifact_id=item["artifact_id"],
            artifact_filename=item["filename"],
            artifact_title=item["title"],
            content=item["content"],
            source_location=item["source_location"],
            kind="chunk",
            score=item["score"],
        )
        for item in result["knowledge"]
    ]

    return SearchResponse(
        **result,
        matches=matches,
        total=len(matches),
        provider=provider.name,
        model=provider.model,
        dimensions=provider.dimensions,
    )


@router.get("/suggestions", response_model=SuggestionsResponse)
def suggestions(
    current_user: CurrentUser,
    db: DbSession,
    q: str = Query(default="", max_length=200),
) -> SuggestionsResponse:
    return SuggestionsResponse(
        prefix=q, suggestions=search_service.suggestions(db, current_user.id, q)
    )
