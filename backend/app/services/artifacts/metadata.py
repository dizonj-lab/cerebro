"""Deterministic metadata extraction.

Produces metadata and per-field prefill evidence without AI inference.
Ported from poc/src/metadata.py (EXP-INGEST-003).

Every field carries how it was established. Nothing here is semantic: the
title candidate is the filename stem, not a read of the document. AI
enrichment and human confirmation are separate, later stages.
"""
from pathlib import Path

# The editable metadata surface. Order is the order shown at review.
METADATA_FIELDS = (
    "title", "description", "language", "author", "created_date",
    "topics", "people", "organizations", "projects", "tags",
)

_LIST_FIELDS = frozenset({"topics", "people", "organizations", "projects", "tags"})


def extract_text_metadata(*, filename: str, text: str, sha256: str) -> dict:
    """Deterministic metadata for a validated text artifact."""
    extracted = {field: [] if field in _LIST_FIELDS else None for field in METADATA_FIELDS}
    # The filename stem is a deterministic candidate, not a semantic title.
    extracted["title"] = Path(filename).stem

    field_methods = {field: "not_established" for field in METADATA_FIELDS}
    field_methods["title"] = "filename_stem"

    return {
        "filename": filename,
        "source": {"sha256": sha256},
        "extracted_metadata": extracted,
        "field_methods": field_methods,
        "content_facts": {
            "character_count": len(text),
            "word_count": len(text.split()),
            "line_count": len(text.splitlines()),
            "representation_type": "extracted_text",
        },
        "provenance": {
            "method": "deterministic_metadata_extraction",
            "source_representation": "extracted_text",
            "ai_used": False,
            "human_confirmed": False,
        },
        "status": "METADATA_EXTRACTED",
    }


def build_prefill_fields(metadata_result: dict) -> dict:
    """Field-level prefill records. Values stay unconfirmed until review."""
    return {
        name: {
            "value": value,
            "source": "extracted",
            "method": metadata_result["field_methods"][name],
            "user_confirmed": False,
        }
        for name, value in metadata_result["extracted_metadata"].items()
    }
