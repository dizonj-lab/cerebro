"""
CEREBRO deterministic metadata extraction.

Produces metadata and prefill evidence from an extracted artifact
without AI inference.

AI enrichment belongs to a later capability.
Human confirmation belongs to the review stage.
"""

from pathlib import Path


def extract_text_metadata(extracted_artifact: dict):
    """
    Produce deterministic/extracted metadata for a text artifact.

    This deliberately avoids semantic inference.
    """

    filename = extracted_artifact["filename"]
    representation = extracted_artifact["representation"]

    if extracted_artifact["modality"] != "text":
        raise ValueError(
            "extract_text_metadata currently supports "
            "validated text artifacts only."
        )

    source_text = representation["content"]

    # Filename stem is only a deterministic title candidate.
    # It is NOT treated as a semantic document title.
    title_candidate = Path(filename).stem

    extracted_metadata = {
        "title": title_candidate,
        "author": None,
        "created_date": None,
        "language": None,
        "description": None,
        "topics": [],
        "people": [],
        "organizations": [],
        "projects": [],
        "tags": [],
    }

    field_methods = {
        "title": "filename_stem",
        "author": "not_established",
        "created_date": "not_established",
        "language": "not_established",
        "description": "not_established",
        "topics": "not_established",
        "people": "not_established",
        "organizations": "not_established",
        "projects": "not_established",
        "tags": "not_established",
    }

    return {
        "filename": filename,

        "source": {
            "sha256": extracted_artifact["source"]["sha256"],
        },

        "extracted_metadata": extracted_metadata,

        "field_methods": field_methods,

        "content_facts": {
            "character_count": len(source_text),
            "representation_type": representation["type"],
        },

        "provenance": {
            "method": "deterministic_metadata_extraction",
            "source_representation": "extracted_text",
            "ai_used": False,
            "human_confirmed": False,
        },

        "status": "METADATA_EXTRACTED",
    }


def build_prefill_fields(metadata_result: dict):
    """
    Convert extracted metadata into field-level prefill records.

    Values remain unconfirmed until human review.
    """

    fields = {}

    for field_name, value in (
        metadata_result["extracted_metadata"].items()
    ):
        fields[field_name] = {
            "value": value,
            "source": "extracted",
            "method": metadata_result["field_methods"][field_name],
            "user_confirmed": False,
        }

    return fields
