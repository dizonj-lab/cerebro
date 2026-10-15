"""Assisted Recollection.

Retrieval-first and owner-scoped. A model, if one is configured, only ever
sees passages already retrieved from this user's registered documents.
"""
from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.recall import RecallRequest, RecallResponse
from app.services import profiles, recall

router = APIRouter(prefix="/api/recall", tags=["recall"])


@router.post("", response_model=RecallResponse)
def ask(payload: RecallRequest, current_user: CurrentUser, db: DbSession) -> RecallResponse:
    preferences = profiles.get_preferences(db, current_user.id)
    return RecallResponse(
        **recall.ask(
            db,
            current_user.id,
            question=payload.question,
            topic=payload.topic,
            ai_suggestions=preferences.ai_suggestions,
        )
    )
