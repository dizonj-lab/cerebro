"""Deterministic enrichment: no model, no network, same answer every time.

This is the engine that is always available, and the one the test suite
asserts against. It draws on three kinds of evidence, in descending order of
authority:

1. what the document itself asserts (PDF /Info, Office core properties);
2. statistics over the document's own words (keyphrases, language);
3. a verbatim quote of its opening, as a description.

None of it is generative, so none of it can invent. A field it cannot ground
is left out.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from app.services.artifacts.enrichment import byline
from app.services.artifacts.enrichment.significance import is_placeholder_title
from app.services.artifacts.enrichment.base import Enrichment
from app.services.artifacts.enrichment.keyphrases import extract as extract_keyphrases

DESCRIPTION_CHARS = 320

# Function words are the cheapest reliable language signal. This is a
# heuristic, not a trained classifier, so it must clear a margin before
# claiming anything — see _detect_language.
_LANGUAGE_MARKERS = {
    "en": "the of and to in that is was it for as with his he be not by but",
    "es": "de la que el en los se del las por un con no una su para es",
    "fr": "de la le et les des en un une du que qui dans pour pas sur",
    "de": "der die und in den von zu das mit sich des auf für ist nicht",
    "pt": "de que não os uma para com uma por mais das dos ao como",
    "it": "di che non per una sono con sul alla come più nella anche",
    "nl": "de het een van en in dat is op te zijn met voor niet aan",
}
_MARKERS = {code: frozenset(words.split()) for code, words in _LANGUAGE_MARKERS.items()}

_MIN_LANGUAGE_WORDS = 20
_LANGUAGE_MARGIN = 1.5

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-zÀ-ɏ']+")


def _detect_language(text: str) -> str | None:
    """A two-letter code, or None when the evidence is not clear enough.

    Returns None rather than a best guess: a wrongly asserted language is a
    fabricated fact, and an unset language is simply unknown.
    """
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) < _MIN_LANGUAGE_WORDS:
        return None

    counts = Counter(words)
    hits = {
        code: sum(counts[w] for w in markers) / len(words)
        for code, markers in _MARKERS.items()
    }
    ranked = sorted(hits.items(), key=lambda pair: -pair[1])
    best, best_rate = ranked[0]
    runner_up_rate = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_rate < 0.02:
        # Barely any function words matched: a word list, a table of numbers,
        # or a language this heuristic does not cover.
        return None
    if runner_up_rate > 0 and best_rate / runner_up_rate < _LANGUAGE_MARGIN:
        # Two languages scored too alike to call. Latin languages share
        # enough short words that this happens on small samples.
        return None
    return best


def _opening(text: str) -> str | None:
    """The document's first sentences, verbatim.

    A quote, not a summary. It is labelled `extracted_opening` so nobody
    mistakes it for one — summarising needs a language model, and inventing a
    summary without one would be fabrication.
    """
    cleaned = " ".join(text.split())
    if len(cleaned) < 40:
        return None
    if len(cleaned) <= DESCRIPTION_CHARS:
        return cleaned

    out = ""
    for sentence in _SENTENCE_END.split(cleaned):
        if not sentence:
            continue
        candidate = f"{out} {sentence}".strip()
        if len(candidate) > DESCRIPTION_CHARS:
            break
        out = candidate
    if out:
        return out
    # One very long opening sentence: cut at a word boundary and mark it.
    return cleaned[:DESCRIPTION_CHARS].rsplit(" ", 1)[0] + "…"


def _keywords_from_properties(raw: str) -> list[str]:
    """A document's own keyword field, however it chose to delimit them."""
    parts = re.split(r"[,;|]", raw)
    return [p.strip() for p in parts if p.strip()][:12]


class DeterministicEnricher:
    name = "deterministic"
    ai_used = False
    local = True

    def enrich(
        self, *, text: str, properties: dict, filename: str, on_progress=None
    ) -> Enrichment:
        """Both phases together. Used directly in tests and when no model runs."""
        return self.from_properties(properties=properties).merge(
            self.from_statistics(text=text, properties=properties, filename=filename)
        )

    def from_properties(self, *, properties: dict) -> Enrichment:
        """Phase one: only what the document asserts about itself.

        Separated from the statistical phase so a language model can be
        offered the fields the document left blank, while never being able to
        overwrite the ones it filled in.
        """
        suggestions: dict = {}
        methods: dict = {}

        def propose(field: str, value, method: str) -> None:
            if value in (None, "", [], {}):
                return
            suggestions[field] = value
            methods[field] = method

        # The document's own title, unless the authoring tool wrote it. A
        # deck exported from PowerPoint carries "PowerPoint Presentation" in
        # /Title, and the rule that document metadata outranks everything
        # then puts that on the review screen as the document's name. It
        # says which program made the file, not what the file is about, so
        # it is left out and a better candidate is allowed through.
        title = properties.get("title")
        if title and not is_placeholder_title(title):
            propose("title", title, "document_metadata")

        # Author and creation date come from here and nowhere else.
        propose("author", properties.get("author"), "document_metadata")
        propose("created_date", properties.get("created_date"), "document_metadata")

        if properties.get("keywords"):
            propose("tags", _keywords_from_properties(properties["keywords"]), "document_metadata")

        # A subject line is the document's own one-line description.
        propose("description", properties.get("subject"), "document_metadata")

        return Enrichment(
            suggestions=suggestions, methods=methods, engine=self.name, ai_used=False, local=True
        )

    def from_statistics(self, *, text: str, properties: dict, filename: str) -> Enrichment:
        """Phase two: statistics over the document's own words."""
        suggestions: dict = {}
        methods: dict = {}
        document_tags = (
            _keywords_from_properties(properties["keywords"])
            if properties.get("keywords")
            else []
        )
        # The line a byline was printed on, shown at review so the value can
        # be checked rather than taken on trust.
        byline_evidence: dict = {}

        def propose(field: str, value, method: str) -> None:
            if value in (None, "", [], {}):
                return
            suggestions[field] = value
            methods[field] = method

        # The author a document prints on its own first page, where its
        # metadata carries none. Still the document asserting its own
        # authorship — printed rather than embedded — so it is the same kind
        # of claim as /Author and carries its own method, never a model's.
        if not properties.get("author"):
            found = byline.find(text)
            if found:
                name, evidence = found
                propose("author", name, "extracted_byline")
                byline_evidence[name] = evidence

        topics, tags = extract_keyphrases(text)
        propose("topics", topics, "keyphrase_extraction")
        if document_tags and tags:
            # The document's own keywords lead; the text's own words follow,
            # without duplicating them.
            seen = {t.lower() for t in document_tags}
            merged = document_tags + [t for t in tags if t.lower() not in seen]
            propose("tags", merged[:12], "document_metadata+keyphrase_extraction")
        else:
            propose("tags", tags, "keyphrase_extraction")

        propose("language", _detect_language(text), "language_detection")
        # A verbatim quote of the opening, offered only where nothing with
        # more authority has filled the description.
        propose("description", _opening(text), "extracted_opening")

        # Deliberately never proposed: people, organizations and projects.
        # Naming them needs entity recognition this engine does not have, and
        # a frequent capitalised word is not a person.
        notes = []
        if not topics:
            notes.append("Too little recurring text to establish topics.")
        if Path(filename).suffix.lower() == ".pdf" and not properties:
            notes.append("The PDF carries no metadata of its own.")

        return Enrichment(
            suggestions=suggestions,
            methods=methods,
            engine=self.name,
            model=None,
            ai_used=False,
            local=True,
            notes=notes,
            evidence=byline_evidence,
        )
