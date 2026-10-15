"""Artifact pipeline orchestration: upload, review, register.

Sequences the ported PoC capabilities and persists the result. Owns no
inspection or registration logic of its own — those stay in their modules
so the contract the PoC validated is the one the application enforces.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.storage import get_object_store
from app.models.artifact import Artifact
from app.services.artifacts.inspection import inspect_artifact
from app.services.artifacts.metadata import extract_text_metadata
from app.services.artifacts.registration import RegistrationRejected, register_artifact

PREVIEW_CHARS = 1200


class ArtifactRejected(ValueError):
    """Upload refused before anything was stored."""


class DuplicateArtifact(ValueError):
    """These exact bytes are already in this owner's library."""


def _storage_key(owner_id: uuid.UUID, artifact_id: uuid.UUID, filename: str) -> str:
    # Owner-prefixed and server-generated. The client's filename never
    # reaches the key, so it cannot influence where bytes land.
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    safe = "".join(c for c in suffix if c.isalnum())[:8] or "bin"
    return f"{owner_id}/{artifact_id}.{safe}"


def ingest(
    db: Session, *, owner_id: uuid.UUID, filename: str, content: bytes,
    content_type: str | None, max_bytes: int,
) -> Artifact:
    """Inspect, store and draft metadata for an uploaded artifact.

    Stops short of registration: the artifact is INSPECTED and awaits human
    review. Nothing is stored until inspection has accepted the bytes.
    """
    if not content:
        raise ArtifactRejected("The file is empty.")
    if len(content) > max_bytes:
        raise ArtifactRejected(
            f"The file is larger than the {max_bytes // (1024 * 1024)}MB limit."
        )

    inspection = inspect_artifact(filename, content)
    modality = inspection["identification"]["detected_modality"]

    # This phase handles text only. Other modalities need extraction
    # capabilities (OCR, transcription) that belong to a later phase.
    if modality != "text":
        raise ArtifactRejected(
            f"Only text artifacts are supported in this phase; detected '{modality}'."
        )

    sha256 = inspection["file"]["sha256"]
    existing = db.scalar(
        select(Artifact).where(Artifact.owner_id == owner_id, Artifact.sha256 == sha256)
    )
    if existing is not None:
        raise DuplicateArtifact(existing.filename)

    # Safe: inspection has already confirmed valid UTF-8 for text modality.
    text = content.decode("utf-8")
    md = extract_text_metadata(filename=filename, text=text, sha256=sha256)

    artifact_id = uuid.uuid4()
    key = _storage_key(owner_id, artifact_id, filename)
    uri = get_object_store().put(key, content)

    artifact = Artifact(
        id=artifact_id,
        owner_id=owner_id,
        filename=filename,
        content_type=content_type,
        modality=modality,
        size_bytes=len(content),
        sha256=sha256,
        storage_key=key,
        storage_uri=uri,
        status="inspected",
        inspection=inspection,
        artifact_metadata=md["extracted_metadata"],
        field_methods=md["field_methods"],
        provenance={
            "inspection": md["provenance"]["method"],
            "extraction": "deterministic_metadata_extraction",
            "ai_enrichment": None,
            "human_review": None,
            "registration": None,
            "content_facts": md["content_facts"],
        },
        integrity={
            "human_reviewed": False,
            "human_approved": False,
            "source_verified": False,
        },
    )
    db.add(artifact)
    db.flush()
    return artifact


def list_for_owner(db: Session, owner_id: uuid.UUID) -> tuple[list[Artifact], int]:
    rows = db.scalars(
        select(Artifact)
        .where(Artifact.owner_id == owner_id)
        .order_by(Artifact.created_at.desc())
    ).all()
    total = db.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.owner_id == owner_id)
    )
    return list(rows), int(total or 0)


def get_for_owner(db: Session, owner_id: uuid.UUID, artifact_id: uuid.UUID) -> Artifact | None:
    """Fetch scoped to the owner.

    The owner is part of the predicate rather than checked afterwards, so a
    guessed id simply finds nothing.
    """
    return db.scalar(
        select(Artifact).where(Artifact.id == artifact_id, Artifact.owner_id == owner_id)
    )


def review(db: Session, artifact: Artifact, *, metadata: dict, approve: bool) -> Artifact:
    """Save reviewed metadata, and register when the human approves.

    Registration re-reads the stored bytes and re-verifies the checksum, so
    approval alone cannot register an artifact whose content has drifted.
    """
    if artifact.status == "registered":
        raise ArtifactRejected("This artifact is already registered.")

    artifact.artifact_metadata = metadata
    # Build a new dict rather than mutating in place. A JSONB column is not
    # change-tracked, and mutating before reassigning makes SQLAlchemy compare
    # the object with itself and conclude nothing changed — the update is then
    # silently dropped.
    artifact.field_methods = {
        **(artifact.field_methods or {}),
        **{field: "human_confirmed" for field in metadata},
    }

    reviewed_at = datetime.now(UTC).isoformat()
    artifact.integrity = {**artifact.integrity, "human_reviewed": True}
    artifact.provenance = {**artifact.provenance, "human_review": reviewed_at}

    if not approve:
        artifact.status = "inspected"
        db.flush()
        return artifact

    content = get_object_store().get(artifact.storage_key)

    try:
        registered = register_artifact(
            filename=artifact.filename,
            content=content,
            inspection=artifact.inspection,
            approved_metadata={
                "metadata": metadata,
                "human_reviewed": True,
                "human_approved": True,
                "status": "APPROVED",
            },
            reviewed_at=reviewed_at,
        )
    except RegistrationRejected:
        # Fail closed: leave the artifact unregistered and let it surface.
        artifact.status = "inspected"
        db.flush()
        raise

    artifact.status = "registered"
    artifact.registered_at = datetime.now(UTC)
    artifact.provenance = {**artifact.provenance, "registration": registered["provenance"]}
    artifact.integrity = {
        **artifact.integrity,
        "human_approved": True,
        "source_verified": True,
        **registered["integrity"],
    }
    db.flush()
    return artifact


def preview_text(artifact: Artifact) -> str | None:
    """First characters of the stored text, for the review screen."""
    if artifact.modality != "text":
        return None
    try:
        raw = get_object_store().get(artifact.storage_key)
    except FileNotFoundError:
        return None
    return raw.decode("utf-8", errors="replace")[:PREVIEW_CHARS]


def delete(db: Session, artifact: Artifact) -> None:
    get_object_store().delete(artifact.storage_key)
    db.delete(artifact)
    db.flush()
