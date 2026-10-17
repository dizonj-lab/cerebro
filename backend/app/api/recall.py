"""Assisted Recollection.

Retrieval-first and owner-scoped. A model, if one is configured, only ever
sees passages already retrieved from this user's registered documents.
"""
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.schemas.recall import RecallRequest, RecallResponse
from app.services import metrics, profiles, recall

router = APIRouter(prefix="/api/recall", tags=["recall"])


@router.post("", response_model=RecallResponse)
def ask(payload: RecallRequest, current_user: CurrentUser, db: DbSession) -> RecallResponse:
    preferences = profiles.get_preferences(db, current_user.id)
    started = time.perf_counter()
    result = recall.ask(
        db,
        current_user.id,
        question=payload.question,
        topic=payload.topic,
        ai_suggestions=preferences.ai_suggestions,
        history=[turn.model_dump() for turn in payload.history],
    )

    # What the question cost, end to end — retrieval included, not just the
    # model's share. The user waits for the whole thing, so that is what the
    # report has to show.
    inner = result.get("telemetry") or {}
    abstained = bool(result.get("abstained"))
    metrics.record(
        db,
        owner_id=current_user.id,
        kind="recall",
        operation="recall.ask",
        duration_ms=(time.perf_counter() - started) * 1000,
        model=result.get("model"),
        algorithm="hybrid retrieval (RRF) + local generation" if result.get("model")
        else "hybrid retrieval (RRF), passages only",
        prompt_tokens=inner.get("prompt_tokens"),
        completion_tokens=inner.get("completion_tokens"),
        units={
            "passages": inner.get("passages") or len(result.get("sources") or []),
            "citations": len(result.get("cited") or []),
            # Separated because they mean different things: an honest refusal
            # is correct behaviour, and averaging it with an answer hides both.
            "abstained": abstained,
            "answered": not abstained,
            "grounded": bool(result.get("grounded")),
            "model_ms": inner.get("duration_ms"),
        },
    )
    db.commit()
    return RecallResponse(**result)


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
