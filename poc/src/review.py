"""
CEREBRO human review capability.

AI-generated metadata remains a suggestion until explicitly
reviewed and approved by a human.

This module does NOT:
- register artifacts,
- create knowledge fragments,
- promote candidate relationships,
- invoke AI models.
"""

from copy import deepcopy
from datetime import datetime, timezone


def prepare_review(ai_prefill: dict):
    """
    Create a reviewable copy of AI-suggested metadata.
    """

    reviewed_prefill = deepcopy(ai_prefill)

    for field_name, field in reviewed_prefill.items():
        field["original_ai_value"] = deepcopy(
            field.get("value")
        )

        field["final_value"] = None
        field["action"] = "pending"
        field["user_confirmed"] = False
        field["status"] = "pending_review"

    return reviewed_prefill


def review_field(
    reviewed_prefill: dict,
    field_name: str,
    final_value,
):
    """
    Apply explicit human review to one metadata field.
    """

    if field_name not in reviewed_prefill:
        raise KeyError(
            f"Unknown review field: {field_name}"
        )

    field = reviewed_prefill[field_name]

    original_value = field.get("original_ai_value")

    if final_value == original_value:
        action = "accepted"
    else:
        action = "edited"

    field["final_value"] = deepcopy(final_value)
    field["action"] = action
    field["user_confirmed"] = True
    field["status"] = "confirmed"

    return reviewed_prefill


def finalize_review(reviewed_prefill: dict):
    """
    Finalize review only when every field has received
    explicit human confirmation.
    """

    unconfirmed = [
        field_name
        for field_name, field in reviewed_prefill.items()
        if field.get("user_confirmed") is not True
    ]

    if unconfirmed:
        raise ValueError(
            "Cannot finalize review. "
            f"Unconfirmed fields: {unconfirmed}"
        )

    final_metadata = {
        field_name: deepcopy(field["final_value"])
        for field_name, field in reviewed_prefill.items()
    }

    return {
        "metadata": final_metadata,

        "review": deepcopy(reviewed_prefill),

        "human_reviewed": True,
        "human_approved": True,

        "reviewed_at": (
            datetime.now(timezone.utc).isoformat()
        ),

        "status": "APPROVED",
    }
