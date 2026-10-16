"""Artifact pipeline orchestration: upload, review, register.

Sequences the ported PoC capabilities and persists the result. Owns no
inspection or registration logic of its own — those stay in their modules
so the contract the PoC validated is the one the application enforces.
"""
import json
import logging
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.storage import get_object_store
from app.models.artifact import Artifact
from app.services.artifacts.enrichment import enrich
from app.services.artifacts.extraction import (
    SUPPORTED_EXTENSIONS,
    ExtractionFailed,
    ExtractionResult,
    adapter_for,
)
from app.services.artifacts.fragments import build_for_artifact
from app.services.artifacts.inspection import inspect_artifact
from app.services.artifacts.metadata import extract_text_metadata
from app.services.artifacts.registration import RegistrationRejected, register_artifact

logger = logging.getLogger(__name__)

PREVIEW_CHARS = 1200


class ArtifactRejected(ValueError):
    """Upload refused before anything was stored."""


class ArtifactStorageUnavailable(RuntimeError):
    """The bytes could not be written to the object store.

    Distinct from a rejection: nothing is wrong with the artifact. Raised so
    the API can say the store is the problem rather than returning a bare 500,
    which reaches the browser as plain text and renders as a generic error.
    """


class DuplicateArtifact(ValueError):
    """These exact bytes are already in this owner's library."""


def _storage_key(owner_id: uuid.UUID, artifact_id: uuid.UUID, filename: str) -> str:
    # Owner-prefixed and server-generated. The client's filename never
    # reaches the key, so it cannot influence where bytes land.
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    safe = "".join(c for c in suffix if c.isalnum())[:8] or "bin"
    return f"{owner_id}/{artifact_id}.{safe}"


def _extraction_key(storage_key: str) -> str:
    """Key of the derived extraction result beside the original bytes."""
    return f"{storage_key}.extraction.json"


def _select_adapter(filename: str, inspection: dict):
    """Pick the extraction adapter, refusing anything the bytes contradict."""
    adapter = adapter_for(filename)
    if adapter is None:
        raise ArtifactRejected(
            "CEREBRO cannot read this file type yet. Supported: "
            f"{', '.join(SUPPORTED_EXTENSIONS)}. Images and audio need OCR and "
            "transcription, which arrive in a later phase."
        )

    detected = inspection["identification"]["detected_modality"]
    if detected not in adapter.signature_modalities:
        # The extension claims one thing and the bytes show another. Trust the
        # bytes: extracting on the strength of a filename is how a renamed
        # file gets treated as a document.
        raise ArtifactRejected(
            f"The contents of this file do not match its name: it is named like "
            f"{adapter.modality} but its bytes look like '{detected}'."
        )
    return adapter


def _extraction_summary(result: ExtractionResult, *, adapter, key: str) -> dict:
    return {**result.as_dict(), "modality": adapter.modality, "object_key": key}


def extracted_document(artifact: Artifact) -> ExtractionResult | None:
    """Read back the stored extraction, or None if it is not retrievable."""
    key = (artifact.extraction or {}).get("object_key")
    if not key:
        return None
    try:
        raw = get_object_store().get(key)
    except FileNotFoundError:
        return None
    try:
        return ExtractionResult.from_document(json.loads(raw.decode("utf-8")))
    except (ValueError, KeyError):
        return None


# Below this size, extraction runs inside the upload request: it finishes in
# well under a second and a round trip is simpler than a poll. Above it, the
# request returns as soon as the bytes are safely stored and extraction
# continues in the background, so a 20MB PDF does not hold the browser — and
# does not lose its work if the user navigates away, because the work is
# happening on the server rather than in the tab.
INLINE_BYTES = 1024 * 1024


def store_upload(
    db: Session, *, owner_id: uuid.UUID, filename: str, content: bytes,
    content_type: str | None, max_bytes: int,
) -> Artifact:
    """Accept and store the bytes, leaving extraction for `process`.

    Everything cheap and everything that can refuse the file happens here —
    the size limit, the checksum, the duplicate check, and whether the bytes
    match the extension — so a file that will never be accepted is rejected
    in the request that uploaded it rather than minutes later.
    """
    if not content:
        raise ArtifactRejected("The file is empty.")
    if len(content) > max_bytes:
        raise ArtifactRejected(
            f"The file is larger than the {max_bytes // (1024 * 1024)}MB limit."
        )

    inspection = inspect_artifact(filename, content)
    # Refuses when the bytes contradict the extension, before anything is
    # stored: the filename is a claim and the bytes are the evidence.
    adapter = _select_adapter(filename, inspection)

    sha256 = inspection["file"]["sha256"]
    existing = db.scalar(
        select(Artifact).where(Artifact.owner_id == owner_id, Artifact.sha256 == sha256)
    )
    if existing is not None:
        raise DuplicateArtifact(existing.filename)

    artifact_id = uuid.uuid4()
    key = _storage_key(owner_id, artifact_id, filename)
    try:
        uri = get_object_store().put(key, content)
    except OSError as exc:
        logger.exception("Artifact storage write failed for key %s", key)
        raise ArtifactStorageUnavailable(str(exc)) from None

    artifact = Artifact(
        id=artifact_id,
        owner_id=owner_id,
        filename=filename,
        content_type=content_type,
        modality=adapter.modality,
        size_bytes=len(content),
        sha256=sha256,
        storage_key=key,
        storage_uri=uri,
        # Stored but not yet read. The status is honest about that: no
        # metadata has been proposed and no text exists yet.
        status="processing",
        inspection=inspection,
        artifact_metadata={},
        field_methods={},
        extraction={},
        provenance={"inspection": inspection.get("method", "deterministic_inspection")},
        integrity={
            "human_reviewed": False,
            "human_approved": False,
            "source_verified": False,
        },
    )
    db.add(artifact)
    db.flush()
    return artifact


def process(
    db: Session,
    artifact: Artifact,
    *,
    ai_suggestions: bool = True,
    record_failure: bool = False,
) -> Artifact:
    """Extract the text and draft metadata for a stored artifact.

    Separated from storage so it can run in the background for a large file.
    Idempotent by status: an artifact that has already been read is returned
    untouched, so a retry cannot overwrite a review in progress.

    `record_failure` decides where a refusal goes. Inline it is raised, so
    the upload request answers 400 and nothing is kept — a document with no
    retrievable text must not enter the library. In the background the
    request has already returned, so the reason is written to the artifact
    instead: that is the only place left to tell the user.
    """
    if artifact.status != "processing":
        return artifact

    content = original_bytes(artifact)
    adapter = _select_adapter(artifact.filename, artifact.inspection)

    try:
        extracted = adapter.extract(content, filename=artifact.filename)
    except ExtractionFailed as exc:
        if not record_failure:
            raise ArtifactRejected(str(exc)) from None
        artifact.status = "rejected"
        artifact.inspection = {**artifact.inspection, "rejected_reason": str(exc)}
        db.flush()
        return artifact

    md = extract_text_metadata(
        filename=artifact.filename, text=extracted.text, sha256=artifact.sha256
    )

    # Deliberately deterministic here. Asking a local language model takes
    # tens of seconds, and it is asked from the review screen, when the user
    # asks for it.
    suggested = enrich(
        text=extracted.text,
        properties=extracted.properties,
        filename=artifact.filename,
        ai_suggestions=ai_suggestions,
        use_llm=False,
    )

    try:
        # Blocks keep their page or slide, so a chunk built from them later
        # can still point back at where in the document it came from.
        get_object_store().put(
            _extraction_key(artifact.storage_key),
            json.dumps(extracted.as_document(), ensure_ascii=False).encode("utf-8"),
        )
    except OSError as exc:
        logger.exception("Extraction write failed for key %s", artifact.storage_key)
        raise ArtifactStorageUnavailable(str(exc)) from None

    artifact.artifact_metadata = {**md["extracted_metadata"], **suggested.suggestions}
    artifact.field_methods = {**md["field_methods"], **suggested.methods}
    artifact.extraction = _extraction_summary(
        extracted, adapter=adapter, key=_extraction_key(artifact.storage_key)
    )
    artifact.provenance = {
        **artifact.provenance,
        "inspection": md["provenance"]["method"],
        # Deterministic enrichment is recorded here; `ai_enrichment` stays
        # null unless a language model actually contributed, so the field
        # keeps meaning "AI touched this".
        "enrichment": suggested.provenance(),
        "ai_enrichment": suggested.provenance() if suggested.ai_used else None,
        "extraction": "deterministic_metadata_extraction",
        "text_extraction": {
            "method": "deterministic_extraction",
            "adapter": type(adapter).__name__,
            "ai_used": False,
        },
        "human_review": None,
        "registration": None,
        "content_facts": md["content_facts"],
    }
    artifact.status = "inspected"
    db.flush()
    return artifact


def process_later(artifact_id: uuid.UUID, owner_id: uuid.UUID, ai_suggestions: bool) -> None:
    """Run `process` in its own session, after the response has gone out.

    Its own session because the request's is closed by then. Failures are
    written to the artifact rather than logged and forgotten: an artifact
    stuck at "processing" with no explanation is the worst outcome here.
    """
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        artifact = get_for_owner(db, owner_id, artifact_id)
        if artifact is None:
            return
        try:
            process(db, artifact, ai_suggestions=ai_suggestions, record_failure=True)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - nothing else can report this
            logger.exception("Background processing failed for artifact %s", artifact_id)
            db.rollback()
            artifact = get_for_owner(db, owner_id, artifact_id)
            if artifact is not None and artifact.status == "processing":
                artifact.status = "rejected"
                artifact.inspection = {
                    **artifact.inspection,
                    "rejected_reason": f"Processing failed: {exc}",
                }
                db.commit()


def delete_artifact(db: Session, artifact: Artifact) -> None:
    """Remove an artifact, its knowledge and its stored bytes.

    The database cascades fragments and their embeddings, so deleting the row
    removes the knowledge derived from it — a deleted document must not leave
    retrievable passages behind.

    The objects go too: the original and the derived extraction. Storage
    failures are logged and swallowed deliberately, because the row is gone
    either way and an orphaned object is a cleanup problem, not a reason to
    tell the user their deletion failed.
    """
    store = get_object_store()
    for key in (artifact.storage_key, _extraction_key(artifact.storage_key)):
        try:
            store.delete(key)
        except OSError:
            logger.exception("Could not delete object %s", key)

    db.delete(artifact)
    db.flush()


def ingest(
    db: Session, *, owner_id: uuid.UUID, filename: str, content: bytes,
    content_type: str | None, max_bytes: int, ai_suggestions: bool = True,
) -> Artifact:
    """Store and read an artifact in one go.

    Stops short of registration: the artifact ends up INSPECTED and awaits
    human review. One code path with the deferred route — the only difference
    there is when `process` runs.
    """
    artifact = store_upload(
        db,
        owner_id=owner_id,
        filename=filename,
        content=content,
        content_type=content_type,
        max_bytes=max_bytes,
    )
    return process(db, artifact, ai_suggestions=ai_suggestions)


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

    # Approval is the gate into retrieval: fragments are built here and
    # nowhere else, so an unapproved artifact can never be searched. Building
    # them in this transaction means a failure rolls the registration back
    # rather than leaving a registered artifact no query can reach.
    build_for_artifact(db, artifact, document=extracted_document(artifact))
    db.flush()
    return artifact


def original_bytes(artifact: Artifact) -> bytes:
    """The artifact's stored bytes, exactly as uploaded."""
    return get_object_store().get(artifact.storage_key)


def preview_text(artifact: Artifact) -> str | None:
    """First characters of the extracted text, for the review screen.

    The extracted text, not the raw bytes: a PDF's bytes are not readable,
    and the extracted text is what the rest of the pipeline will work from,
    so it is also what the human should be reviewing.
    """
    document = extracted_document(artifact)
    if document is None:
        # Artifacts registered before extraction was wired in have no derived
        # object. Their bytes were text, so they can be read directly.
        if artifact.modality != "text":
            return None
        try:
            raw = get_object_store().get(artifact.storage_key)
        except FileNotFoundError:
            return None
        return raw.decode("utf-8", errors="replace")[:PREVIEW_CHARS]
    return document.text[:PREVIEW_CHARS]


def delete(db: Session, artifact: Artifact) -> None:
    store = get_object_store()
    key = (artifact.extraction or {}).get("object_key")
    if key:
        # Derived data, so a missing object is not a failure worth surfacing.
        with suppress(FileNotFoundError):
            store.delete(key)
    store.delete(artifact.storage_key)
    db.delete(artifact)
    db.flush()


def suggest_with_model(db: Session, artifact: Artifact, *, ai_suggestions: bool) -> dict:
    """Ask the configured local model to propose metadata for this artifact.

    Returns the suggestions and how each was arrived at, without saving them.
    The user sees them in the form and decides; nothing becomes part of the
    artifact until they approve it at review.
    """
    if artifact.status == "registered":
        raise ArtifactRejected("This artifact is already registered.")

    document = extracted_document(artifact)
    if document is None:
        raise ArtifactRejected("The extracted text for this artifact could not be read.")

    result = enrich(
        text=document.text,
        properties=document.properties,
        filename=artifact.filename,
        ai_suggestions=ai_suggestions,
        use_llm=True,
    )
    # Record that a model was consulted, even though the suggestions are not
    # saved: the attempt is part of the artifact's history.
    if result.ai_used:
        artifact.provenance = {**artifact.provenance, "ai_enrichment": result.provenance()}
        db.flush()
    return {
        "suggestions": result.suggestions,
        "field_methods": result.methods,
        # The quote each suggested entity was found in, so the reviewer can
        # check it without opening the document.
        "evidence": result.evidence,
        "ai_used": result.ai_used,
        "engine": result.engine,
        "model": result.model,
        "local": result.local,
        "notes": result.notes,
    }
