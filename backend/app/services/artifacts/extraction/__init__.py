"""Extraction adapters, selected by file extension.

Adding a modality means adding an adapter and registering it here; nothing
else in the pipeline changes. Image and audio adapters land in a later phase.
"""
from pathlib import Path

from app.services.artifacts.extraction.base import (
    Block,
    ExtractionAdapter,
    ExtractionFailed,
    ExtractionResult,
    SourceLocation,
)
from app.services.artifacts.extraction.office import DocxAdapter, PptxAdapter
from app.services.artifacts.extraction.pdf import PdfAdapter
from app.services.artifacts.extraction.plain_text import PlainTextAdapter

_ADAPTERS: tuple[ExtractionAdapter, ...] = (
    PlainTextAdapter(), PdfAdapter(), DocxAdapter(), PptxAdapter(),
)

SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(
    sorted({ext for a in _ADAPTERS for ext in a.extensions})
)


def adapter_for(filename: str) -> ExtractionAdapter | None:
    suffix = Path(filename).suffix.lower()
    for adapter in _ADAPTERS:
        if suffix in adapter.extensions:
            return adapter
    return None


def extract(content: bytes, *, filename: str) -> ExtractionResult:
    """Extract an artifact, or raise ExtractionFailed naming why."""
    adapter = adapter_for(filename)
    if adapter is None:
        raise ExtractionFailed(
            f"No extractor for this file type. Supported: {', '.join(SUPPORTED_EXTENSIONS)}."
        )
    return adapter.extract(content, filename=filename)


__all__ = [
    "Block", "ExtractionFailed", "ExtractionResult", "SourceLocation",
    "adapter_for", "extract", "SUPPORTED_EXTENSIONS",
]
