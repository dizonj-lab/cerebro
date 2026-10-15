"""Artifact endpoints: upload, library, review, registration.

Ownership always comes from the session. No route accepts an owner id, and
every lookup is scoped to the authenticated user, so a guessed artifact id
finds nothing rather than someone else's document.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.models.artifact import Artifact
from app.schemas.artifact import (
    ArtifactDetail,
    ArtifactListResponse,
    ArtifactMetadata,
    ArtifactReviewRequest,
    ArtifactSummary,
)
from app.services.artifacts import service
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
    )


def _detail(a: Artifact, *, preview: bool = True) -> ArtifactDetail:
    return ArtifactDetail(
        **_summary(a).model_dump(),
        content_type=a.content_type,
        metadata=ArtifactMetadata(**(a.artifact_metadata or {})),
        field_methods=a.field_methods or {},
        inspection=a.inspection or {},
        provenance=a.provenance or {},
        integrity=a.integrity or {},
        preview=service.preview_text(a) if preview else None,
    )


@router.post("", response_model=ArtifactDetail, status_code=status.HTTP_201_CREATED)
async def upload(
    current_user: CurrentUser, db: DbSession, file: Annotated[UploadFile, File()]
):
    """Upload an artifact: inspect, store, draft metadata. Not yet registered."""
    content = await file.read()
    try:
        artifact = service.ingest(
            db,
            owner_id=current_user.id,
            filename=file.filename or "untitled",
            content=content,
            content_type=file.content_type,
            max_bytes=settings.max_upload_bytes,
        )
    except service.DuplicateArtifact as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This file is already in your library as '{exc}'.",
        ) from None
    except service.ArtifactRejected as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    db.commit()
    db.refresh(artifact)
    return _detail(artifact)


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
    except service.ArtifactRejected as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    db.commit()
    db.refresh(artifact)
    return _detail(artifact)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(artifact_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> Response:
    artifact = service.get_for_owner(db, current_user.id, artifact_id)
    if artifact is None:
        raise NOT_FOUND
    service.delete(db, artifact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
