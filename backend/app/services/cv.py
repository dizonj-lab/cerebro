"""Reading a CV's chronology, deterministically.

A CV states its own history in a form regular expressions can read: a line
with a date range and an employer, under a heading that says what kind of
history it is. That is enough, and it is preferable to asking a model —
dates and employers are claims about the world, and the document asserting
them is the only acceptable source. Nothing here infers, completes or tidies.

What it produces are **suggestions**. Every one carries the line it came
from, so a reviewer can check it against the CV, and none reaches the
Timeline or the Galaxy until a human approves it.

Three refusals worth stating, because each is a place a tidier
implementation would quietly invent something:

* An open range ("2021 – Present") stores a **null** end date. It does not
  store today. The CV says the person is still there, not that the role
  ended this morning.
* A range giving only years stores `year` precision and 1 January. The day
  is a storage artefact; the precision column is what the UI reads, so the
  date is never displayed as more exact than the CV was.
* A line with no date is not an event. It may be a responsibility, a skill
  or a page footer, and guessing which would be fabrication.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.services.temporal import MONTHS

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
# Dashes a CV might use between two dates, en and em included.
_DASH = r"[-–—]|\bto\b|\buntil\b"
_PRESENT = re.compile(r"\b(present|current|now|to date|ongoing)\b", re.I)

# "Mar 2016", "March 2016", "03/2016", "2016"
_POINT = re.compile(
    rf"(?:(?P<month_name>{_MONTH})[a-z]*\.?\s+)?(?P<year>(?:19|20)\d{{2}})"
    rf"|(?P<num_month>0?[1-9]|1[0-2])[/.](?P<num_year>(?:19|20)\d{{2}})",
    re.I,
)
_RANGE = re.compile(
    rf"(?P<start>(?:{_MONTH})[a-z]*\.?\s+(?:19|20)\d{{2}}|(?:0?[1-9]|1[0-2])[/.](?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
    rf"\s*(?:{_DASH})\s*"
    rf"(?P<end>(?:{_MONTH})[a-z]*\.?\s+(?:19|20)\d{{2}}|(?:0?[1-9]|1[0-2])[/.](?:19|20)\d{{2}}|(?:19|20)\d{{2}}|present|current|now|ongoing|to date)",
    re.I,
)

# Headings a CV uses, mapped to the event type the lines beneath them carry.
# A heading is a line that is short and matches one of these: a sentence
# mentioning "education" in passing is not a section.
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("education", ("education", "academic", "academic background", "qualifications", "studies")),
    (
        "employment",
        ("experience", "employment", "work experience", "professional experience",
         "career", "career history", "work history", "professional background"),
    ),
    ("project", ("projects", "selected projects", "key projects", "engagements")),
    (
        "certification",
        ("certifications", "certificates", "licences", "licenses", "accreditations"),
    ),
    (
        "professional_development",
        ("training", "professional development", "courses", "memberships",
         "professional memberships", "affiliations"),
    ),
)
_MAX_HEADING_WORDS = 4
_MAX_ANCHORS = 60
# A line carrying one date rather than a range — a certification, an award, a
# milestone. Only short lines qualify: "TOGAF 9 Certified, The Open Group
# 2015" is an entry, while "Published three papers between 2019 and 2021 on
# distributed systems" is prose that happens to contain a year, and treating
# the second as an event would be inventing one.
_MAX_SINGLE_DATE_WORDS = 12


@dataclass
class Anchor:
    """One dated entry a CV states, before anyone has confirmed it."""

    event_type: str
    title: str
    organization: str | None
    start_date: str | None
    end_date: str | None
    date_precision: str
    evidence_text: str
    source_location: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Identity of this life event, stable across re-uploads of the CV.

        Type, title, employer and start date, normalised. Re-uploading a CV
        with a new line added must update the one new anchor and leave the
        rest alone, which is only possible if the others hash the same.
        """
        parts = (
            self.event_type,
            (self.title or "").strip().lower(),
            (self.organization or "").strip().lower(),
            self.start_date or "",
        )
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:40]

    def as_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "title": self.title,
            "organization": self.organization,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "date_precision": self.date_precision,
            "evidence_text": self.evidence_text,
            "source_location": self.source_location,
            "fingerprint": self.fingerprint,
        }


def _heading(line: str) -> str | None:
    """The event type this line introduces, or None if it is not a heading."""
    cleaned = re.sub(r"[^a-z\s]", " ", line.strip().lower()).strip()
    if not cleaned or len(cleaned.split()) > _MAX_HEADING_WORDS:
        return None
    for event_type, names in SECTIONS:
        if cleaned in names:
            return event_type
    return None


def _point(raw: str) -> tuple[str | None, str]:
    """One date as (ISO, precision). A year alone stays a year."""
    text = raw.strip()
    if _PRESENT.search(text):
        # The CV says "still there" — which is not a date, and must not
        # become today's.
        return None, "unknown"
    match = _POINT.search(text)
    if not match:
        return None, "unknown"
    if match.group("num_year"):
        year, month = int(match.group("num_year")), int(match.group("num_month"))
        return f"{year:04d}-{month:02d}-01", "month"
    year = int(match.group("year"))
    name = match.group("month_name")
    if name:
        month = MONTHS.get(name.lower().rstrip("."), 1)
        return f"{year:04d}-{month:02d}-01", "month"
    # January is storage, not a claim: `date_precision` is what the UI reads.
    return f"{year:04d}-01-01", "year"


def _split(line: str, dated: str = "") -> tuple[str, str | None]:
    """A CV line as (title, organization).

    CVs separate the two with a comma, a pipe, an en dash or "at". Where a
    line offers no separator the whole line is the title and the employer
    stays unknown, which is the honest reading.
    """
    body = (line.replace(dated, " ") if dated else _RANGE.sub("", line))
    body = body.strip(" \t,·|-–—")
    body = re.sub(r"\s{2,}", " ", body).strip()
    for separator in (" | ", " — ", " – ", ", ", " at ", " @ "):
        if separator in body:
            left, right = body.split(separator, 1)
            left, right = left.strip(" ,|-–—"), right.strip(" ,|-–—")
            if left and right:
                return left, right
    return body or "Untitled entry", None


def extract(text: str, *, page_of=None) -> list[Anchor]:
    """Dated entries a CV states, in document order.

    `page_of` maps a line index to a page number where extraction knew one,
    so an anchor can point back at where in the CV it was read.
    """
    anchors: list[Anchor] = []
    current = "other"
    seen: set[str] = set()

    for index, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        heading = _heading(line)
        if heading:
            current = heading
            continue

        match = _RANGE.search(line)
        if match:
            start, start_precision = _point(match.group("start"))
            end, end_precision = _point(match.group("end"))
            dated = match.group(0)
        else:
            single = _POINT.search(line)
            # No date, no event. A line may be a responsibility, a skill or a
            # page footer, and deciding which would be a guess.
            if not single or len(line.split()) > _MAX_SINGLE_DATE_WORDS:
                continue
            start, start_precision = _point(single.group(0))
            if start is None:
                continue
            # One date is a point in time, not a range ending today.
            end, end_precision = None, "unknown"
            dated = single.group(0)
        title, organization = _split(line, dated)
        # The coarser of the two: a range is only as exact as its vaguer end.
        precision = (
            "unknown"
            if start is None
            else "year"
            if "year" in (start_precision, end_precision) or end is None and start_precision == "year"
            else start_precision
        )

        anchor = Anchor(
            event_type=current,
            title=title[:300],
            organization=organization[:200] if organization else None,
            start_date=start,
            end_date=end,
            date_precision=precision,
            evidence_text=line[:500],
            source_location={"line": index + 1, **({"page": page_of(index)} if page_of else {})},
        )
        if anchor.fingerprint in seen:
            continue
        seen.add(anchor.fingerprint)
        anchors.append(anchor)
        if len(anchors) >= _MAX_ANCHORS:
            break

    return anchors
