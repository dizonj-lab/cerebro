"""Page furniture: lines a document repeats on most of its pages or slides.

A lecture deck prints "© 2026 National University of Singapore. All Rights Reserved" on every slide.
Left in, that one line is in every fragment: it becomes the most frequent phrase in the library, so
it is proposed as a topic and drawn as the Galaxy's biggest cluster, and it makes every fragment's
vector look alike, so Recall ranks passages by their footer as much as by their content.

The rule is about repetition within **one** document, never a vocabulary:

* a line counts when, with its page counter ignored ("…Reserved Page 3" and "…Reserved Page 4" are
  one line), it appears on at least half of the document's pages or slides, and on at least three of
  them. Only page counters are ignored: "Topic 1" and "Topic 2" stay different lines;
* on a PDF only the top and bottom few lines of a page are considered, because that is where headers
  and footers live, and a column of numbers in a table repeats too without being furniture;
* the **first** occurrence is kept and only the repeats are removed, so nothing the document says is
  lost from it altogether;
* removal never empties a document, and what was removed is reported so it can be checked.

Deterministic and local: no model, no network. Documents without pages or slides (Word, plain text)
pass through unchanged, since their headers and footers are not extracted in the first place.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import replace

from app.services.artifacts.extraction.base import Block, ExtractionResult

MIN_UNITS = 3
SHARE = 0.5
# Lines from the top and bottom of a PDF page considered as possible header or footer.
PAGE_EDGE_LINES = 3
METHOD = "repeated_line_removal"

_PAGE_COUNTER = re.compile(
    r"(page|slide|p\.)\s*\d+(\s*(of|/)\s*\d+)?"   # "Page 3", "Slide 4 of 20"
    r"|\b\d+\s*(/|of)\s*\d+\b"                   # "3/20", "3 of 20"
)
_LINE = re.compile(r"[^\n]+")


def normalise(line: str) -> str:
    """What two printings of one furniture line share: case, spacing and page counters ignored."""
    return _PAGE_COUNTER.sub("#", " ".join(line.lower().split())).strip(" .-|·•")


def repeated_lines(
    units: dict, *, min_units: int = MIN_UNITS, share: float = SHARE
) -> set[str]:
    """Normalised lines appearing in at least `share` of the units, and in at least `min_units`."""
    if len(units) < min_units:
        return set()
    counts: Counter = Counter()
    for lines in units.values():
        counts.update({k for k in (normalise(line) for line in lines) if k})
    need = max(min_units, math.ceil(share * len(units)))
    # A line with no letters at all is a page number or a table cell; repetition alone cannot
    # tell which, so it is left alone.
    return {k for k, n in counts.items() if n >= need and re.search(r"[a-z]", k)}


def _unit_of(block: Block):
    if block.location.slide is not None:
        return ("slide", block.location.slide)
    if block.location.page is not None:
        return ("page", block.location.page)
    return None


def strip(result: ExtractionResult) -> tuple[ExtractionResult, dict | None]:
    """The extraction with repeated furniture removed, and a report of what went, or None."""
    lines_by_unit: dict = {}
    order: list = []
    for b_index, block in enumerate(result.blocks):
        unit = _unit_of(block)
        if unit is None:
            return result, None
        if unit not in lines_by_unit:
            lines_by_unit[unit] = []
            order.append(unit)
        for m in _LINE.finditer(block.text):
            if m.group().strip():
                lines_by_unit[unit].append((b_index, m.start(), m.end(), m.group()))

    def considered(unit, entries):
        if unit[0] != "page":
            return entries
        return entries[:PAGE_EDGE_LINES] + entries[PAGE_EDGE_LINES:][-PAGE_EDGE_LINES:]

    candidates = repeated_lines(
        {u: [e[3] for e in considered(u, lines_by_unit[u])] for u in order}
    )
    if not candidates:
        return result, None

    removed: dict[int, list[tuple[int, int]]] = {}
    seen: dict[str, str] = {}
    count = 0
    for unit in sorted(order, key=lambda u: u[1]):
        for b_index, start, end, text in considered(unit, lines_by_unit[unit]):
            key = normalise(text)
            if key not in candidates:
                continue
            if key not in seen:
                seen[key] = text.strip()   # the first printing stays
                continue
            removed.setdefault(b_index, []).append((start, end))
            count += 1
    if not count:
        return result, None

    blocks: list[Block] = []
    for b_index, block in enumerate(result.blocks):
        cuts = removed.get(b_index)
        if not cuts:
            blocks.append(block)
            continue
        blocks.extend(_without(block, cuts))
    if not blocks:
        return result, None   # never empty a document: an artifact with no text is refused

    report = {
        "method": METHOD,
        "lines": sorted(seen.values())[:8],
        "removed": count,
        "units": len(order),
    }
    structure = {**result.structure, "blocks": len(blocks), "boilerplate": report}
    return replace(result, blocks=blocks, structure=structure), report


def _without(block: Block, cuts: list[tuple[int, int]]) -> list[Block]:
    """The block minus the cut lines, split into runs that keep exact character offsets."""
    kept: list[tuple[int, int]] = []
    cursor = 0
    for start, end in sorted(cuts):
        if start > cursor:
            kept.append((cursor, start))
        cursor = max(cursor, end)
    kept.append((cursor, len(block.text)))

    out = []
    base = block.location.char_start
    for start, end in kept:
        segment = block.text[start:end]
        lead = len(segment) - len(segment.lstrip())
        text = segment.strip()
        if not text:
            continue
        s = start + lead
        location = replace(block.location, char_start=base + s, char_end=base + s + len(text))
        out.append(Block(text=text, location=location, kind=block.kind))
    return out
