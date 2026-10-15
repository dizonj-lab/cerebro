"""Extraction adapter protocol.

An adapter turns artifact bytes into ordered blocks of text, each carrying
the location it came from. Adapters are deterministic: no AI, no inference,
no network. An adapter that cannot read its input says so rather than
guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SourceLocation:
    """Where a block came from in the original artifact.

    Fields are optional because they mean different things per modality: a
    PDF has pages, a deck has slides, a document has sections. Character
    offsets are always relative to the block's own text.
    """

    page: int | None = None
    slide: int | None = None
    section: str | None = None
    paragraph: int | None = None
    char_start: int = 0
    char_end: int = 0

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Block:
    """A contiguous run of extracted text with its origin."""

    text: str
    location: SourceLocation
    # "paragraph" | "heading" | "table" | "notes" | "body"
    kind: str = "body"

    def as_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind, "location": self.location.as_dict()}

    @classmethod
    def from_dict(cls, raw: dict) -> Block:
        return cls(
            text=raw["text"],
            kind=raw.get("kind", "body"),
            location=SourceLocation(**raw.get("location", {})),
        )


@dataclass
class ExtractionResult:
    blocks: list[Block] = field(default_factory=list)
    # Deterministic facts about the document's shape.
    structure: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)

    def as_dict(self) -> dict:
        return {
            "block_count": len(self.blocks),
            "character_count": len(self.text),
            "structure": self.structure,
            "errors": self.errors,
            "method": "deterministic_extraction",
            "ai_used": False,
        }

    def as_document(self) -> dict:
        """The full result, blocks included — for storage, not for a row.

        `as_dict` is the summary that goes on the artifact; this is what gets
        written to the object store and read back to chunk.
        """
        return {**self.as_dict(), "blocks": [b.as_dict() for b in self.blocks]}

    @classmethod
    def from_document(cls, raw: dict) -> ExtractionResult:
        return cls(
            blocks=[Block.from_dict(b) for b in raw.get("blocks", [])],
            structure=raw.get("structure", {}),
            errors=raw.get("errors", []),
        )


class ExtractionFailed(ValueError):
    """The adapter could not read this artifact."""


class ExtractionAdapter(Protocol):
    """Implemented once per modality."""

    modality: str
    extensions: tuple[str, ...]
    # What `inspect_artifact` should have detected from the bytes for this
    # extension. The filename is a claim; these are the evidence that backs
    # it, so a .exe renamed to .pdf is refused instead of extracted.
    signature_modalities: tuple[str, ...]

    def extract(self, content: bytes, *, filename: str) -> ExtractionResult: ...
