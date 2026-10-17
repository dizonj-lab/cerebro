"""Which proposed concepts are worth being knowledge, and which are furniture.

A document is written in a medium, carried by a protocol and saved in a
format, and it names all three while being about none of them. Frequency
cannot tell the difference: "PDF" recurs in a PDF about anything, and a
capitalised acronym looks exactly like a proper noun to a statistical
extractor. That is how "PDF" and "HTTPS" became prominent nodes in the
Galaxy, sitting at the same weight as the subjects the documents are
actually about.

The rule here is about **context, not vocabulary**. A generic word is
rejected when it stands alone, and kept the moment the document puts it in a
phrase that says something:

    PDF                           rejected — names the format
    PDF Document Parsing          kept     — names a subject
    HTTPS                         rejected — names the transport
    Secure API Communication      kept     — names a practice

So nothing is banned outright. A library genuinely about file formats keeps
its subject, because such a document discusses "PDF extraction" and "PDF
structure" rather than merely being a PDF.

Three properties this deliberately has:

* **Deterministic and free.** It runs on the merged suggestions, before any
  human sees them, and costs no model call.
* **Non-destructive.** It filters what is *proposed*. The document's text,
  its fragments and its extraction are untouched, and so is anything a human
  already confirmed — revalidating that is a separate, explicit act.
* **Reversible in principle.** What it drops is recorded in the enrichment
  notes rather than silently discarded, so a filter that is too aggressive
  can be seen to be too aggressive.
"""
from __future__ import annotations

import re

# Terms naming the medium, the format, the protocol or the furniture of a
# document. Rejected as standalone concepts; kept inside a phrase.
GENERIC = frozenset("""
pdf pdfs docx doc docs document documents file files folder attachment
ppt pptx slide slides deck presentation presentations spreadsheet xlsx csv
txt text markdown md rtf odt page pages paragraph paragraphs section sections
chapter heading headings appendix annex figure figures table tables
image images photo photos screenshot diagram chart charts
http https url urls uri link links website web site webpage internet online
email mail inbox message messages
html xml json yaml sql api apis http2 tcp ip dns ssl tls ssh ftp
software hardware system systems platform platforms tool tools application
applications app apps service services server servers client database
technology technologies solution solutions product products project projects
process processes method methods approach approaches framework frameworks
model models data information knowledge content detail details item items
user users customer customers people person team teams company organisation
organization business companies group groups member members
report reports summary overview introduction conclusion abstract
version draft final copy copyright reserved rights trademark confidential
january february march april may june july august september october november
december monday tuesday wednesday thursday friday saturday sunday
figure1 note notes reference references bibliography glossary index contents
click download upload print save open close view read write search
number total amount value values result results type types kind form
""".split())

_PUNCTUATION = re.compile(r"[^\w\s]+")


def _singular(word: str) -> str:
    """A naive plural stripped, and only where it cannot destroy the word.

    Deliberately simple: "ies" becomes "y", and an "s" is dropped from a word
    long enough to survive it. An "es" rule was tried and removed — it cannot
    tell "classes" from "databases" without a dictionary, and it turned
    "slides" into "slid". A missed merge leaves two nodes that mean one
    thing; a wrong merge invents a concept nobody wrote. The first is the
    cheaper mistake, so the rule errs that way.
    """
    if word.endswith("ies") and len(word) > 4:
        return f"{word[:-3]}y"
    if word.endswith("ss") or len(word) <= 3:
        return word
    return word[:-1] if word.endswith("s") else word


def canonical(term: str) -> str:
    """The form two spellings of one concept share.

    Case, surrounding punctuation and a trailing plural are presentation, not
    meaning: "Models", "models" and "model" are one concept and must not
    become three nodes. Only a naive plural is stripped, and only from a word
    long enough that stripping cannot destroy it — this is deduplication, not
    stemming, and a wrong merge is worse than a missed one.
    """
    cleaned = _PUNCTUATION.sub(" ", term).strip().lower()
    words = cleaned.split()
    if not words:
        return ""
    # "ies" -> "y" so "technologies" meets "technology".
    return " ".join(_singular(word) for word in words)


def is_generic(term: str) -> bool:
    """True when the term names the medium rather than the subject.

    A single generic word is furniture. A phrase is furniture only if every
    word in it is — "document" alone says nothing, "document parsing
    pipeline" says something, and the difference is the context the document
    supplied.
    """
    words = canonical(term).split()
    if not words:
        return True
    return all(word in GENERIC for word in words)


def filter_concepts(values: list[str]) -> tuple[list[str], list[str]]:
    """Split proposals into what is worth confirming and what is not.

    Returns (kept, rejected). Order is preserved, and where two proposals
    are the same concept only one survives: the one naming it in more words,
    since that is the more specific statement, and otherwise the one seen
    first. Length in characters is not the test — "rag pipelines" is not a
    better name than "RAG Pipeline" for being a character longer.
    """
    kept: list[str] = []
    rejected: list[str] = []
    by_key: dict[str, int] = {}

    for raw in values:
        if not isinstance(raw, str):
            continue
        term = " ".join(raw.split())
        if not term:
            continue
        if is_generic(term):
            rejected.append(term)
            continue
        key = canonical(term)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = len(kept)
            kept.append(term)
        elif len(term.split()) > len(kept[existing].split()):
            # Same concept, stated more specifically. The fuller phrase takes
            # the place, and the one it replaces is recorded as the duplicate
            # it is rather than vanishing.
            rejected.append(kept[existing])
            kept[existing] = term
        else:
            rejected.append(term)

    return kept, rejected
