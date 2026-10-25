"""Title case for suggested titles, so every document is named in one consistent style.

Standard title case: every word capitalised except short joining words ("and", "of", "from", "to"),
which stay lower case unless they open or close the title or follow a colon. Each part of a
hyphenated word is capitalised ("Real-Time").

Spellings that carry meaning are kept: an acronym ("LSTM"), a word with inner capitals or digits
("PostgreSQL", "GPT-4", "iPhone"). A title set entirely in capitals hides which words are
acronyms, so there a word stays in capitals only when the document's own running text writes it
that way, when it has no vowels and so cannot be read as a word ("RNN", "CNN"), or when it is a
two-letter word that is not an ordinary English one ("AI", "ML", but not "IS" or "OF").

Only the case changes. No word is added, dropped or reordered.
"""

from __future__ import annotations

import re

SMALL_WORDS = frozenset(
    "a an and as at but by en for from if in into nor of off on onto or over per so than the "
    "to up upon via vs with yet".split()
)
# Two-letter words that are words, not acronyms, when a title is set in capitals.
COMMON_TWO_LETTER = frozenset("am be do go he hi is it me my no oh ok ox so us we".split())
_TOKEN = re.compile(r"\S+")
_EDGE = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.UNICODE)


def _acronyms(text: str) -> set[str]:
    """Words written in capitals inside lines that are not themselves all capitals."""
    found: set[str] = set()
    for line in text.splitlines():
        if not re.search(r"[a-z]", line):
            continue
        found.update(re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", line))
    return found


def _is_meaningful_spelling(word: str) -> bool:
    """Inner capitals or digits, as in PostgreSQL, iPhone, GPT-4: kept exactly."""
    return bool(re.search(r"\d", word)) or bool(re.search(r"[a-z][A-Z]|^[a-z]+[A-Z]", word))


def _cap(part: str) -> str:
    return part[:1].upper() + part[1:].lower() if part else part


def title_case(title: str, text: str = "") -> str:
    words = _TOKEN.findall(" ".join(title.split()))
    if not words:
        return title
    shouting = not re.search(r"[a-z]", title)
    acronyms = _acronyms(text) if shouting else set()

    out = []
    after_colon = False
    for i, raw in enumerate(words):
        lead, core, trail = _EDGE.match(raw).groups()
        first_or_last = i == 0 or i == len(words) - 1
        parts = core.split("-")
        cased = []
        for k, part in enumerate(parts):
            bare = part.lower()
            if not part:
                cased.append(part)
            elif _is_meaningful_spelling(part):
                cased.append(part)
            elif shouting:
                two_letter_acronym = len(part) == 2 and bare not in COMMON_TWO_LETTER | SMALL_WORDS
                no_vowels = len(part) > 1 and not re.search(r"[AEIOUY]", part)
                if part in acronyms or two_letter_acronym or no_vowels:
                    cased.append(part)
                elif bare in SMALL_WORDS and not (first_or_last or after_colon) and len(parts) == 1:
                    cased.append(bare)
                else:
                    cased.append(_cap(part))
            elif part.isupper() and len(part) > 1:
                cased.append(part)  # an acronym in a mixed-case title
            elif bare in SMALL_WORDS and not (first_or_last or after_colon) and len(parts) == 1:
                cased.append(bare)
            elif part[:1].isupper():
                cased.append(part)  # already capitalised as the document wrote it
            else:
                cased.append(_cap(part) if k == 0 or len(part) > 1 else part)
        out.append(f"{lead}{'-'.join(cased)}{trail}")
        after_colon = trail.endswith(":")
    return " ".join(out)
