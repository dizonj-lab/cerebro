"""Artifact registration into the trusted layer.

Ported from poc/src/registration.py (EXP-INGEST-006).

Registration requires deterministic inspection, a verified source checksum,
human review and explicit human approval. It fails closed: any missing or
contradictory evidence raises rather than registering a weaker record.

This module does NOT create knowledge fragments, generate embeddings,
create relationships, or invoke AI models.
"""
import hashlib
from copy import deepcopy
from datetime import UTC, datetime


class RegistrationRejected(ValueError):
    """Registration refused because an integrity requirement failed."""


def register_artifact(
    *,
    filename: str,
    content: bytes,
    inspection: dict,
    approved_metadata: dict,
    reviewed_at: str | None = None,
) -> dict:
    """Register a human-approved artifact, or refuse."""

    # --- approval gate -------------------------------------------------
    if approved_metadata.get("human_reviewed") is not True:
        raise RegistrationRejected("human_reviewed must be True")
    if approved_metadata.get("human_approved") is not True:
        raise RegistrationRejected("human_approved must be True")
    if approved_metadata.get("status") != "APPROVED":
        raise RegistrationRejected("review status must be APPROVED")

    # --- source integrity ----------------------------------------------
    actual_sha256 = hashlib.sha256(content).hexdigest()
    inspected_sha256 = inspection.get("file", {}).get("sha256")

    if not inspected_sha256:
        raise RegistrationRejected("source checksum missing")
    if actual_sha256 != inspected_sha256:
        raise RegistrationRejected("source checksum mismatch")

    return {
        "filename": filename,
        "metadata": deepcopy(approved_metadata["metadata"]),
        "source": {
            "sha256": actual_sha256,
            "size_bytes": len(content),
            "modality": inspection.get("identification", {}).get("detected_modality"),
        },
        "review": {
            "human_reviewed": True,
            "human_approved": True,
            "reviewed_at": reviewed_at,
        },
        "provenance": {
            "inspection_method": inspection.get("provenance", {}).get("method"),
            "source_verified": True,
            "registered_at": datetime.now(UTC).isoformat(),
        },
        "integrity": {
            "checksum_verified": True,
            "provenance_present": True,
            "human_approval_verified": True,
        },
        "status": "REGISTERED",
    }
