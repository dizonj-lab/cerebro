"""The document's own metadata.

What the file itself asserts — PDF `/Info`, Office core properties — as
opposed to anything inferred from its text. This is the only acceptable
source for author and creation date: both are claims about the world that no
amount of reading the content can establish, so a value absent here stays
absent rather than being guessed.

Blank and whitespace-only values are dropped. An empty string in a PDF's
/Author field means the field was never filled in, not that the author is "".
"""
from __future__ import annotations

from datetime import datetime

# Keys other code may rely on. Anything else a format offers is ignored.
KNOWN = ("title", "author", "subject", "keywords", "created_date")


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pdf_date(raw: object) -> str | None:
    """PDF dates look like D:20240115103000+00'00'. Return an ISO date."""
    text = _clean(raw)
    if text is None:
        return None
    digits = text[2:] if text.startswith("D:") else text
    digits = "".join(c for c in digits[:8] if c.isdigit())
    if len(digits) != 8:
        return None
    try:
        return datetime.strptime(digits, "%Y%m%d").date().isoformat()
    except ValueError:
        # An unparseable date is left out. A wrong date is worse than none.
        return None


def from_pdf(reader) -> dict:
    try:
        info = reader.metadata
    except Exception:  # noqa: BLE001 - malformed metadata must not fail extraction
        return {}
    if not info:
        return {}

    found = {
        "title": _clean(info.get("/Title")),
        "author": _clean(info.get("/Author")),
        "subject": _clean(info.get("/Subject")),
        "keywords": _clean(info.get("/Keywords")),
        "created_date": _pdf_date(info.get("/CreationDate")),
    }
    return {k: v for k, v in found.items() if v is not None}


def from_office(core) -> dict:
    """Word and PowerPoint share the same core properties object."""
    if core is None:
        return {}
    created = getattr(core, "created", None)
    found = {
        "title": _clean(getattr(core, "title", None)),
        "author": _clean(getattr(core, "author", None)),
        "subject": _clean(getattr(core, "subject", None)),
        "keywords": _clean(getattr(core, "keywords", None)),
        "created_date": created.date().isoformat() if isinstance(created, datetime) else None,
    }
    return {k: v for k, v in found.items() if v is not None}
