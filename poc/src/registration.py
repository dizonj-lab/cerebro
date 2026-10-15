"""
CEREBRO artifact registration capability.

Registers an approved artifact into the trusted artifact layer.

Registration requires:
- deterministic source inspection,
- source checksum,
- human review,
- explicit human approval.

This module does NOT:
- create knowledge fragments,
- generate embeddings,
- create relationships,
- invoke AI models.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib


def register_artifact(
    artifact_id: str,
    *,
    filename: str,
    content: bytes,
    inspection: dict,
    approved_metadata: dict,
):
    """
    Register a human-approved artifact.

    Fails closed if integrity requirements are not satisfied.
    """

    # -----------------------------------------------------
    # Approval gate
    # -----------------------------------------------------

    if approved_metadata.get("human_reviewed") is not True:
        raise ValueError(
            "Artifact registration rejected: "
            "human_reviewed must be True."
        )

    if approved_metadata.get("human_approved") is not True:
        raise ValueError(
            "Artifact registration rejected: "
            "human_approved must be True."
        )

    if approved_metadata.get("status") != "APPROVED":
        raise ValueError(
            "Artifact registration rejected: "
            "review status must be APPROVED."
        )

    # -----------------------------------------------------
    # Source integrity
    # -----------------------------------------------------

    actual_sha256 = hashlib.sha256(content).hexdigest()

    inspected_sha256 = (
        inspection
        .get("file", {})
        .get("sha256")
    )

    if not inspected_sha256:
        raise ValueError(
            "Artifact registration rejected: "
            "source checksum missing."
        )

    if actual_sha256 != inspected_sha256:
        raise ValueError(
            "Artifact registration rejected: "
            "source checksum mismatch."
        )

    # -----------------------------------------------------
    # Registration
    # -----------------------------------------------------

    registered_at = (
        datetime.now(timezone.utc).isoformat()
    )

    return {
        "artifact_id": artifact_id,

        "filename": filename,

        "metadata": deepcopy(
            approved_metadata["metadata"]
        ),

        "source": {
            "sha256": actual_sha256,
            "size_bytes": len(content),
            "modality": (
                inspection
                .get("identification", {})
                .get("detected_modality")
            ),
        },

        "review": {
            "human_reviewed": True,
            "human_approved": True,
            "reviewed_at": (
                approved_metadata.get("reviewed_at")
            ),
        },

        "provenance": {
            "inspection_method": (
                inspection
                .get("provenance", {})
                .get("method")
            ),

            "source_verified": True,

            "registered_at": registered_at,
        },

        "integrity": {
            "checksum_verified": True,
            "provenance_present": True,
            "human_approval_verified": True,
        },

        "status": "REGISTERED",
    }
