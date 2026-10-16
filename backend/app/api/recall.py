"""Assisted Recollection.

Retrieval-first and owner-scoped. A model, if one is configured, only ever
sees passages already retrieved from this user's registered documents.
"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

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
            history=[turn.model_dump() for turn in payload.history],
        )
    )


@router.post("/stream")
def ask_streaming(
    payload: RecallRequest, current_user: CurrentUser, db: DbSession
) -> StreamingResponse:
    """The same answer as server-sent events: sources, then words, then a summary.

    Streaming exists so the chat shows an answer forming rather than a
    spinner: a local 3B model on a laptop takes seconds, and the first words
    are useful before the last ones arrive.

    Sources are sent first, before any text. They are known the moment
    retrieval finishes, and they are the evidence — the user can check what
    the answer is being built from while it is still being written.
    """
    preferences = profiles.get_preferences(db, current_user.id)

    def events() -> object:
        for event in recall.ask_stream(
            db,
            current_user.id,
            question=payload.question,
            topic=payload.topic,
            ai_suggestions=preferences.ai_suggestions,
            history=[turn.model_dump() for turn in payload.history],
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # No buffering anywhere in between, or the stream arrives as one lump
        # and the point of streaming is lost.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
