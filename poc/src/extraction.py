"""
CEREBRO deterministic content extraction.

Transforms an inspected artifact into a provenance-aware
representation suitable for downstream CEREBRO processing.

No AI inference.
No metadata enrichment.
No artifact registration.
No knowledge construction.
"""


def extract_text_artifact(
    filename: str,
    content: bytes,
    inspection: dict
):
    """
    Extract UTF-8 text from an artifact already validated as text.
    """

    detected_modality = (
        inspection
        .get("identification", {})
        .get("detected_modality")
    )

    if detected_modality != "text":
        raise ValueError(
            "extract_text_artifact requires "
            f"detected_modality='text', got {detected_modality!r}"
        )

    if not inspection.get(
        "content_validation", {}
    ).get("is_text", False):
        raise ValueError(
            "Artifact did not pass deterministic text validation."
        )

    source_text = content.decode("utf-8")

    return {
        "filename": filename,

        "modality": "text",

        "representation": {
            "type": "text",
            "content": source_text,
            "character_count": len(source_text),
        },

        "source": {
            "sha256": inspection["file"]["sha256"],
            "size_bytes": inspection["file"]["size_bytes"],
        },

        "provenance": {
            "method": "utf8_text_extraction",
            "source_representation": "original_artifact",
            "ai_used": False,
            "human_confirmed": False,
        },

        "status": "EXTRACTED",
    }
