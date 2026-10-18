"""Artifact endpoints: upload, library, review, registration.

Ownership always comes from the session. No route accepts an owner id, and
every lookup is scoped to the authenticated user, so a guessed artifact id
finds nothing rather than someone else's document.
"""
import time
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.models.artifact import Artifact
from app.schemas.artifact import (
    MAX_BULK_FILES,
    ArtifactDetail,
    ArtifactListResponse,
    ArtifactMetadata,
    ArtifactReviewRequest,
    ArtifactSummary,
    BulkReviewRequest,
    BulkReviewResponse,
    BulkReviewResultItem,
    BulkUploadItem,
    BulkUploadResponse,
)
from app.services import enrichment_queue, metrics, profiles
from app.services.artifacts import service, serving
from app.services.artifacts.fragments import FragmentsUnavailable
from app.services.artifacts.registration import RegistrationRejected

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
settings = get_settings()

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")


def _summary(a: Artifact) -> ArtifactSummary:
    return ArtifactSummary(
        id=a.id, filename=a.filename, modality=a.modality, size_bytes=a.size_bytes,
        status=a.status, sha256=a.sha256, created_at=a.created_at,
        registered_at=a.registered_at,
        title=(a.artifact_metadata or {}).get("title"),
        rejection_reason=(a.inspection or {}).get("rejected_reason"),
    )


def _detail(a: Artifact, *, preview: bool = True) -> ArtifactDetail:
    return ArtifactDetail(
        **_summary(a).model_dump(),
        content_type=a.content_type,
        metadata=ArtifactMetadata(**(a.artifact_metadata or {})),
        field_methods=a.field_methods or {},
        inspection=a.inspection or {},
        extraction=a.extraction or {},
        provenance=a.provenance or {},
        integrity=a.integrity or {},
        enrichment_job=a.enrichment_job or {},
        preview=service.preview_text(a) if preview else None,
    )


@router.post("", response_model=ArtifactDetail, status_code=status.HTTP_201_CREATED)
async def upload(
    current_user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
):
    """Upload an artifact: inspect, store, draft metadata. Not yet registered.

    A small file is read during the request. A large one is stored, answered
    for immediately with status "processing", and extracted in the background
    — so a 20MB PDF neither holds the browser nor loses its work when the
    user moves to another part of CEREBRO. Either way the file is refused
    outright, in this request, if its bytes contradict its extension or it
    duplicates something already in the library.
    """
    started = time.perf_counter()
    content = await file.read()
    # Enrichment honours the user's own setting. Deterministic enrichment —
    # the document's own metadata and statistics over its text — always runs;
    # this governs whether a local language model is also asked.
    preferences = profiles.get_preferences(db, current_user.id)
    deferred = len(content) > service.INLINE_BYTES
    try:
        if deferred:
            artifact = service.store_upload(
                db,
                owner_id=current_user.id,
                filename=file.filename or "untitled",
                content=content,
                content_type=file.content_type,
                max_bytes=settings.max_upload_bytes,
            )
        else:
            artifact = service.ingest(
                db,
                owner_id=current_user.id,
                filename=file.filename or "untitled",
                content=content,
                content_type=file.content_type,
                max_bytes=settings.max_upload_bytes,
                ai_suggestions=preferences.ai_suggestions,
            )
    except service.DuplicateArtifact as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This file is already in your library as '{exc}'.",
        ) from None
    except service.ArtifactStorageUnavailable:
        db.rollback()
        # Deliberately vague: the underlying message names a server path. The
        # detail is in the API log, not in the browser.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CEREBRO could not store the file. Artifact storage is unavailable.",
        ) from None
    except service.ArtifactRejected as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    # Ingestion cost, with the units that make the duration mean something:
    # a slow read of an eighty-page scan is not the same problem as a slow
    # read of a memo.
    metrics.record(
        db,
        owner_id=current_user.id,
        kind="ingestion",
        operation="artifact.upload" + (" (deferred)" if deferred else ""),
        duration_ms=(time.perf_counter() - started) * 1000,
        model=None,
        algorithm="deterministic extraction",
        artifact_id=artifact.id,
        units={
            "bytes": len(content),
            "pages": ((artifact.extraction or {}).get("structure") or {}).get("pages"),
            "characters": (artifact.extraction or {}).get("character_count"),
            "deferred": deferred,
        },
    )
    db.commit()
    db.refresh(artifact)
    if deferred:
        # Scheduled after the commit, so the task cannot read a row that is
        # not there yet, and queued rather than awaited so the response goes
        # out now.
        background.add_task(
            service.process_later,
            artifact.id,
            current_user.id,
            preferences.ai_suggestions,
        )
    return _detail(artifact)


@router.post("/bulk", response_model=BulkUploadResponse, status_code=status.HTTP_207_MULTI_STATUS)
async def upload_many(
    current_user: CurrentUser, db: DbSession, files: Annotated[list[UploadFile], File()]
):
    """Upload several artifacts at once.

    Each file succeeds or fails on its own: one unreadable PDF in a batch of
    twenty must not cost the user the other nineteen. The response reports
    every file, so the table can show exactly which rows need attention.

    Each accepted file goes through the same `ingest` as a single upload —
    inspection, extraction, deterministic enrichment — and is left awaiting
    review. Nothing is registered here.
    """
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Up to {MAX_BULK_FILES} files at a time; {len(files)} were sent.",
        )

    preferences = profiles.get_preferences(db, current_user.id)
    items: list[BulkUploadItem] = []

    for file in files:
        filename = file.filename or "untitled"
        content = await file.read()
        try:
            artifact = service.ingest(
                db,
                owner_id=current_user.id,
                filename=filename,
                content=content,
                content_type=file.content_type,
                max_bytes=settings.max_upload_bytes,
                ai_suggestions=preferences.ai_suggestions,
            )
        except service.DuplicateArtifact as exc:
            # Rolled back individually, so the rest of the batch survives.
            db.rollback()
            items.append(
                BulkUploadItem(
                    filename=filename,
                    accepted=False,
                    error=f"This file is already in your library as '{exc}'.",
                )
            )
            continue
        except (service.ArtifactRejected, service.ArtifactStorageUnavailable) as exc:
            db.rollback()
            message = (
                "CEREBRO could not store the file. Artifact storage is unavailable."
                if isinstance(exc, service.ArtifactStorageUnavailable)
                else str(exc)
            )
            items.append(BulkUploadItem(filename=filename, accepted=False, error=message))
            continue

        db.commit()
        db.refresh(artifact)
        items.append(
            BulkUploadItem(
                filename=filename, accepted=True, artifact=_detail(artifact, preview=False)
            )
        )

    accepted = sum(1 for item in items if item.accepted)
    return BulkUploadResponse(
        items=items, accepted=accepted, rejected=len(items) - accepted
    )


@router.patch("/bulk", response_model=BulkReviewResponse)
def review_many(
    payload: BulkReviewRequest, current_user: CurrentUser, db: DbSession
) -> BulkReviewResponse:
    """Confirm metadata for several artifacts, registering each.

    Registration is the same path a single approval takes, so each artifact
    is checksum-verified and its knowledge fragments are chunked and embedded
    before it counts as knowledge. One artifact failing leaves the others
    registered.
    """
    items: list[BulkReviewResultItem] = []

    for entry in payload.items:
        artifact = service.get_for_owner(db, current_user.id, entry.id)
        if artifact is None:
            items.append(
                BulkReviewResultItem(id=entry.id, registered=False, error="Artifact not found")
            )
            continue
        try:
            reviewed = service.review(
                db, artifact, metadata=entry.metadata.model_dump(), approve=payload.approve
            )
        except (RegistrationRejected, FragmentsUnavailable, service.ArtifactRejected) as exc:
            db.rollback()
            items.append(BulkReviewResultItem(id=entry.id, registered=False, error=str(exc)))
            continue

        db.commit()
        db.refresh(reviewed)
        items.append(
            BulkReviewResultItem(
                id=entry.id,
                registered=reviewed.status == "registered",
                artifact=_detail(reviewed, preview=False),
            )
        )

    registered = sum(1 for item in items if item.registered)
    return BulkReviewResponse(
        items=items, registered=registered, failed=len(items) - registered
    )


@router.get("", response_model=ArtifactListResponse)
def library(current_user: CurrentUser, db: DbSession) -> ArtifactListResponse:
    rows, total = service.list_for_owner(db, current_user.id)
    return ArtifactListResponse(items=[_summary(a) for a in rows], total=total)


@router.get("/{artifact_id}", response_model=ArtifactDetail)
def detail(artifact_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> ArtifactDetail:
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise NOT_FOUND
    return _detail(artifact)


@router.patch("/{artifact_id}", response_model=ArtifactDetail)
def review(
    artifact_id: uuid.UUID, payload: ArtifactReviewRequest,
    current_user: CurrentUser, db: DbSession,
) -> ArtifactDetail:
    """Save reviewed metadata, and register when `approve` is true."""
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise NOT_FOUND
    try:
        artifact = service.review(
            db, artifact, metadata=payload.metadata.model_dump(), approve=payload.approve
        )
    except RegistrationRejected as exc:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Registration refused: {exc}",
        ) from None
    except FragmentsUnavailable as exc:
        # The artifact stays unregistered. Registering something that cannot
        # be retrieved would show it in the library as trusted evidence that
        # no query can reach.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Registration stopped before completing: {exc}",
        ) from None
    except service.ArtifactRejected as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    db.commit()
    db.refresh(artifact)
    return _detail(artifact)


@router.get("/{artifact_id}/content")
def content(artifact_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> Response:
    """The original uploaded bytes, for opening the source document.

    Scoped to the owner like every other artifact route, so a guessed id
    finds nothing rather than someone else's document.
    """
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise NOT_FOUND

    try:
        raw = service.original_bytes(artifact)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The stored file for this artifact is no longer available.",
        ) from None

    media_type, inline = serving.media_type_for(artifact.filename)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=raw,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{serving.safe_filename(artifact.filename)}"'
            ),
            # The media type is derived from the extension, not from what the
            # client claimed. Tell the browser not to second-guess it either.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{artifact_id}/suggest", status_code=status.HTTP_202_ACCEPTED)
def suggest(artifact_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> dict:
    """Queue this artifact for enrichment by the local model.

    Accepted, not done. Enrichment used to run inside this request, which
    blocked it for minutes, had nowhere to report progress to, and lost the
    work entirely when the user navigated away — the browser aborted the
    fetch and the model's output went with it. The job now belongs to the
    queue rather than to a request, so leaving the page is free and the
    progress is somewhere both pages can read.
    """
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise NOT_FOUND
    if artifact.status == "registered":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This artifact is already registered.",
        )

    preferences = profiles.get_preferences(db, current_user.id)
    job = enrichment_queue.enqueue(artifact, ai_suggestions=preferences.ai_suggestions)
    db.commit()
    # Started here rather than at import: a test run and a migration both
    # import the application, and neither should start threads that reach
    # for a model.
    enrichment_queue.start()
    return {"artifact_id": str(artifact_id), **job}


@router.get("/enrichment/queue")
def enrichment_status(current_user: CurrentUser, db: DbSession) -> dict:
    """What this owner has waiting or running. Polled by the Library."""
    jobs = enrichment_queue.pending(db, current_user.id)
    return {
        "jobs": jobs,
        "running": sum(1 for j in jobs if j["status"] == "running"),
        "waiting": sum(1 for j in jobs if j["status"] == "queued"),
        # Stated so the UI can explain why the rest are waiting rather than
        # looking stuck.
        "max_concurrent": enrichment_queue.MAX_WORKERS,
    }


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(artifact_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> Response:
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise NOT_FOUND
    service.delete(db, artifact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{artifact_id}/process", response_model=ArtifactDetail)
def process_now(
    artifact_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> ArtifactDetail:
    """Read an artifact that is still waiting to be read.

    For the case the background task did not finish: the API restarted while
    it was running, say. Processing is idempotent by status, so asking twice
    is harmless, and an artifact that was already read is returned unchanged.
    """
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such artifact.")

    if artifact.status == "processing":
        preferences = profiles.get_preferences(db, current_user.id)
        background.add_task(
            service.process_later, artifact.id, current_user.id, preferences.ai_suggestions
        )
    return _detail(artifact)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(artifact_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> Response:
    """Delete an artifact, the knowledge derived from it, and its stored bytes.

    Scoped to the owner, like every other route here: another user's artifact
    is not found rather than forbidden, so the endpoint cannot be used to
    discover what exists.

    This removes knowledge as well as the document. Fragments and their
    embeddings cascade, because a deleted document must not leave retrievable
    passages behind — that would be the library answering from something the
    user deleted.
    """
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such artifact.")

    service.delete_artifact(db, artifact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
