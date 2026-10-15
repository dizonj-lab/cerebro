"""Serving an artifact's original bytes back to its owner.

The content type is derived here from the artifact's own extension, never
taken from `content_type`, which is whatever the client claimed at upload. A
client that uploaded `notes.txt` while declaring `text/html` would otherwise
have its file served back as HTML from the application's own origin, and any
script in it would run with the session's privileges.

Only types this application knows how to extract are served, which is also
the set it is willing to vouch for.
"""
from __future__ import annotations

from pathlib import Path

# extension -> (media type, render inline?)
_SERVABLE: dict[str, tuple[str, bool]] = {
    # A browser's PDF viewer is sandboxed, and opening the source document in
    # place is the point of the control.
    ".pdf": ("application/pdf", True),
    ".txt": ("text/plain; charset=utf-8", True),
    ".md": ("text/plain; charset=utf-8", True),
    ".markdown": ("text/plain; charset=utf-8", True),
    # No browser renders these, so offering a download is the honest result.
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        False,
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        False,
    ),
}

_FALLBACK = ("application/octet-stream", False)


def media_type_for(filename: str) -> tuple[str, bool]:
    return _SERVABLE.get(Path(filename).suffix.lower(), _FALLBACK)


def safe_filename(filename: str) -> str:
    """A filename safe to put in a Content-Disposition header.

    Quotes, newlines and path separators are removed: a filename is attacker
    -influenced, and a newline in a header value splits the response.
    """
    name = Path(filename).name
    cleaned = "".join(c for c in name if c.isprintable() and c not in '"\\\r\n;')
    return cleaned.strip() or "artifact"
