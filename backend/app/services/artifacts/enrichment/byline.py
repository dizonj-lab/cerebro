"""The author a document prints on its own first page.

Author has always come from the file's metadata and nowhere else, on the
grounds that it is a claim about the world which reading the content cannot
establish. That reasoning holds for prose. It fails for the documents people
actually have: a lecture deck exported to PDF carries no `/Author`, and
prints "Dr Zhu Fangming" on slide one. Refusing to read it left the field
blank while the answer sat in the first thing anyone sees.

So the rule is widened by exactly one case, and no further. A byline is a short line
near the top of the document that **says it is a byline** — either carrying
an honorific like Dr or Prof, or introduced by "Presented by", "Author:" and
the like — and is otherwise a name and nothing else. It is taken verbatim.

The explicit signal is the whole point. A bare capitalised line was tried
first and matched "Quarterly Revenue Review", because a title in title case
has exactly the shape of a name. Without a signal the two cannot be told
apart, and guessing wrong puts a document's subject in its author field. That is still the document asserting
its own authorship — the same kind of claim as `/Author`, printed instead of
embedded — rather than anything inferred from the body, and it carries its
own method (`extracted_byline`) so the review screen can say where it came
from and a reviewer can disagree.

What is deliberately not here: no model may propose an author, nothing is
read from the body of the document, and a line that merely contains a name
is not a byline. A sentence about a person is evidence that they are
mentioned, never that they wrote it.
"""
from __future__ import annotations

import re

# How far in a byline may appear. A name below this is in the content.
MAX_LINES = 12
MAX_WORDS = 6

# "Presented by", "Author:", "Lecturer —". The label is dropped, the name
# kept.
_INTRO = re.compile(
    r"^\s*(presented\s+by|prepared\s+by|author|authors|by|lecturer|presenter|speaker|"
    r"instructor|facilitator)\s*[:\-–—]?\s*",
    re.I,
)
# Honorifics a name may carry. Kept, because "Dr" is part of how the
# document names the person.
_TITLE = r"(?:Dr|Prof|Professor|Mr|Mrs|Ms|Miss|Sir|Dame|Ir|Eng)\.?"
_NAME_WORD = r"[A-Z][A-Za-z'’\-]+"
# Two to four capitalised words, optionally after an honorific. Initials are
# allowed because people write "J. V. Dizon".
_NAME = re.compile(
    rf"^(?:{_TITLE}\s+)?(?:(?:{_NAME_WORD}|[A-Z]\.)\s+){{1,3}}(?:{_NAME_WORD})$"
)
# Lines that look like names but are not.
_NOT_A_NAME = re.compile(
    r"\b(university|college|institute|school|faculty|department|ltd|limited|inc|"
    r"corporation|company|systems?|solutions?|technolog|present(ation|s)?|"
    r"introduction|overview|agenda|contents|copyright|all rights reserved|"
    r"confidential|chapter|lecture|module|session|day\s*\d)\b",
    re.I,
)


_HONORIFIC = re.compile(rf"^{_TITLE}\s+", re.I)


def find(text: str) -> tuple[str, str] | None:
    """A byline as (name, the line it was printed on), or None.

    Returns the line too, so the review screen can show the evidence rather
    than asking the reviewer to take the value on trust.
    """
    for raw in text.splitlines()[:MAX_LINES]:
        line = " ".join(raw.split())
        if not line or len(line.split()) > MAX_WORDS:
            continue

        introduced = bool(_INTRO.match(line))
        candidate = _INTRO.sub("", line).strip(" .,:;–—-")
        if not candidate:
            continue
        # A heading shouted in capitals is not a byline, however much it
        # resembles one: "PATTERN RECOGNITION AND MACHINE" matched before
        # this check existed.
        words = candidate.split()
        if len(words) > 1 and all(w.isupper() for w in words if w.isalpha()):
            continue
        if not introduced and not _HONORIFIC.match(candidate):
            # No signal that this line claims authorship. A title in title
            # case has the same shape as a name, and the two are not
            # separable without one.
            continue
        if _NOT_A_NAME.search(candidate):
            # An organisation, a section heading or a copyright line. Any of
            # them can match the shape of a name.
            continue
        if _NAME.match(candidate):
            return candidate, line
    return None
