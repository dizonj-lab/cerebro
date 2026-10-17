"""The CV: a person's own chronology, and the anchor for their timeline.

The CV goes through the ordinary artifact pipeline — same validation, same
extraction, same storage, same ownership checks — and the profile points at
it. There is no second ingestion path for CVs, and no CV-shaped hole in the
security model: every route here resolves the owner from the session and
never from the request.

What is different is what happens next. Where an ordinary document yields
fragments, a CV also yields **anchors**: the dated entries it states about
its author. Those arrive as suggestions and reach the Timeline only once a
human has read them.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.models.artifact import Artifact
from app.services import anchors as anchor_service
from app.services import profiles
from app.services.artifacts import service

router = APIRouter(prefix="/api/cv", tags=["cv"])

# A CV is a few pages. The cap is well under the library's own limit, and is
# about catching a wrong file rather than saving disk.
MAX_CV_BYTES = 10 * 1024 * 1024
ACCEPTED = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
ACCEPTED_SUFFIXES = (".pdf", ".docx")


def _text_of(artifact: Artifact) -> str:
    document = service.extracted_document(artifact)
    return document.text if document else ""


def _state(db, owner_id: uuid.UUID) -> dict:
    profile = profiles.get_profile(db, owner_id)
    rows = anchor_service.for_owner(db, owner_id)
    artifact = (
        db.get(Artifact, profile.cv_artifact_id) if profile.cv_artifact_id else None
    )
    return {
        "status": profile.cv_status,
        "filename": artifact.filename if artifact else None,
        "uploaded_at": artifact.created_at.isoformat() if artifact else None,
        "artifact_id": str(artifact.id) if artifact else None,
        "anchors": [anchor_service.as_dict(a) for a in rows],
        "suggested": sum(1 for a in rows if a.approval_status == "suggested"),
        "approved": sum(1 for a in rows if a.approval_status == "approved"),
    }


@router.get("")
def read(current_user: CurrentUser, db: DbSession) -> dict:
    """The CV's state and its anchors. Only ever this user's."""
    return _state(db, current_user.id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    current_user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
) -> dict:
    """Upload or replace the CV, then read its chronology.

    Replacing is the same call: the new CV becomes the profile's CV and its
    anchors are matched to the existing ones by fingerprint, so a career is
    updated rather than duplicated and a correction already made is kept.
    """
    content = await file.read()
    name = file.filename or "cv.pdf"
    if not name.lower().endswith(ACCEPTED_SUFFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A CV must be a PDF or a Word document (.docx).",
        )
    if len(content) > MAX_CV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="A CV may be up to 10 MB.",
        )

    preferences = profiles.get_preferences(db, current_user.id)
    try:
        artifact = service.ingest(
            db,
            owner_id=current_user.id,
            filename=name,
            content=content,
            content_type=file.content_type,
            max_bytes=get_settings().max_upload_bytes,
            # The user's own AI setting is honoured here exactly as it is for
            # any other document. A CV is the most sensitive thing in the
            # library, so it is certainly not an exception to it.
            ai_suggestions=preferences.ai_suggestions,
        )
    except service.DuplicateArtifact:
        db.rollback()
        # The same bytes are already in the library. Point the profile at
        # them rather than refusing: re-uploading the same CV is a reasonable
        # thing to do, and it must not be an error.
        existing = service.find_by_checksum(db, owner_id=current_user.id, content=content)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This file is already in your library.",
            ) from None
        artifact = existing
    except service.ArtifactRejected as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    text = _text_of(artifact)
    if not text.strip():
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be read from this CV, so no dates could be found in it.",
        )

    result = anchor_service.ingest(
        db, current_user.id, artifact_id=artifact.id, text=text
    )
    profile = profiles.get_profile(db, current_user.id)
    profile.cv_artifact_id = artifact.id
    # Found, not yet confirmed. The timeline stays unpersonalised until a
    # human has read these.
    profile.cv_status = "needs_review" if result["found"] else "none"
    db.commit()

    return {**_state(db, current_user.id), "extraction": result}


@router.patch("/anchors/{anchor_id}")
def correct(
    current_user: CurrentUser, db: DbSession, anchor_id: uuid.UUID, changes: dict
) -> dict:
    """Edit, approve or reject one anchor."""
    row = anchor_service.update(db, current_user.id, anchor_id, changes)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such anchor.")
    db.commit()
    return anchor_service.as_dict(row)


@router.post("/anchors", status_code=status.HTTP_201_CREATED)
def add(current_user: CurrentUser, db: DbSession, values: dict) -> dict:
    """Add an event the CV did not state. The user asserts it, so it is approved."""
    if not (values.get("title") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="An event needs a title."
        )
    row = anchor_service.add_manual(db, current_user.id, values)
    db.commit()
    return anchor_service.as_dict(row)


@router.post("/approve")
def approve(current_user: CurrentUser, db: DbSession) -> dict:
    """Approve the outstanding suggestions and personalise the timeline."""
    approved = anchor_service.approve_all(db, current_user.id)
    profile = profiles.get_profile(db, current_user.id)
    rows = anchor_service.for_owner(db, current_user.id, approved_only=True)
    profile.cv_status = "approved" if rows else profile.cv_status
    db.commit()
    return {**_state(db, current_user.id), "newly_approved": approved}
