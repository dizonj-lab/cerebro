"""Enrichment contract.

Enrichment proposes metadata for a human to confirm. It never establishes
it. Every suggested field carries the method that produced it, so the review
screen can say where a value came from and the artifact records it:

    document_metadata   the file itself asserts it (PDF /Info, Office core)
    keyphrase_extraction  statistical, from the document's own words
    language_detection    statistical, with a confidence margin required
    extracted_opening     a verbatim quote of the document's first sentences
    ai_suggested          a local language model proposed it

Three rules hold for every engine:

* Nothing is invented. A value that cannot be grounded in the document is
  left absent, and absent means absent — never an empty string or a guess.
* Author and creation date come only from document metadata. They are claims
  about the world that reading the content cannot establish, so no engine,
  statistical or generative, may propose them.
* Suggestions are drafts. They reach the artifact as unconfirmed and only
  become `human_confirmed` when the user approves them at review.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# Fields an engine may propose. Deliberately excludes `author` and
# `created_date` for generative engines; see the module docstring.
SUGGESTABLE = (
    "title", "description", "language", "author", "created_date",
    "topics", "people", "organizations", "projects", "tags",
)

# Only document metadata may fill these.
ASSERTION_ONLY = frozenset({"author", "created_date"})


@dataclass
class Enrichment:
    """What an engine proposes, and how it got there."""

    # field -> value. A field absent from this mapping was not established.
    suggestions: dict = field(default_factory=dict)
    # field -> method, one of the names in the module docstring.
    methods: dict = field(default_factory=dict)
    engine: str = "none"
    model: str | None = None
    ai_used: bool = False
    # False would mean content left the CEREBRO environment.
    local: bool = True
    notes: list[str] = field(default_factory=list)
    # value -> the sentence it was found in. An entity CEREBRO shows as
    # suggested can therefore be checked against the document without
    # opening it, which is what makes "review before approval" meaningful.
    evidence: dict = field(default_factory=dict)

    def merge(self, other: Enrichment) -> Enrichment:
        """Combine, keeping values already established.

        Earlier engines win. Document metadata runs first precisely so a
        language model cannot overwrite what the file itself asserts.
        """
        for name, value in other.suggestions.items():
            if name in self.suggestions:
                continue
            self.suggestions[name] = value
            self.methods[name] = other.methods.get(name, other.engine)
        self.notes.extend(other.notes)
        for value, quote in other.evidence.items():
            self.evidence.setdefault(value, quote)
        if other.ai_used:
            self.ai_used = True
            self.engine = other.engine
            self.model = other.model
            self.local = self.local and other.local
        return self

    def provenance(self) -> dict:
        return {
            "engine": self.engine,
            "model": self.model,
            "ai_used": self.ai_used,
            "local": self.local,
            "fields": sorted(self.suggestions),
            "notes": self.notes,
        }


class EnrichmentEngine(Protocol):
    name: str
    ai_used: bool
    local: bool

    def enrich(
        self, *, text: str, properties: dict, filename: str, on_progress=None
    ) -> Enrichment: ...
