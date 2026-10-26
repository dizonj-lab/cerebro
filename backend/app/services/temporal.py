"""Temporal knowledge: events the documents themselves date.

The old timeline placed one event per artifact, dated by the document's own
metadata or by when it was registered. That answers "when did this arrive",
not "when did this happen". This reads the dates *inside* registered
knowledge: "the cutover completed in March 2021" is an event in March 2021,
whoever uploaded the deck and whenever they did it.

Three rules shape the whole module:

* **Only dates the text states.** Every event carries the expression that was
  matched and the sentence it came from. Nothing is inferred, and an upload
  or registration date is never substituted for a date a document does not
  give — that would be CEREBRO inventing history from its own filing.
* **Deterministic parsing first.** Regular expressions over sentences, with
  the method recorded. A language model is not needed to see "March 2021",
  and using one here would make the result unrepeatable and unexplainable.
* **A cited date is not an event.** "Marr (1982)" and "Springer, 2006" are
  when someone else's work appeared, not something that happened in this
  document, and a URL's /2021/12/31/ is a path. Such dates are kept but
  marked `kind: "reference"` with the reason, so the timeline can hide them
  by default and still show them on request — nothing is silently dropped.
* **Precision is kept.** "2024" is a year, "Q3 2024" a quarter, "March 2021"
  a month, "12 Sep 2023" a day. They are not all silently turned into the
  first of some month.
"""
from __future__ import annotations

import hashlib
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import KnowledgeFragment
from app.services import telemetry

EXTRACTION_METHOD = "deterministic_date_parsing"
EXTRACTION_VERSION = 2

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))

# Ordered: the most specific expression wins where two overlap, so
# "12 September 2023" is a day rather than the month "September 2023".
PATTERNS: list[tuple[str, str]] = [
    ("iso", r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    ("dmy", rf"\b(\d{{1,2}})\s+({_MONTH_NAMES})\.?,?\s+(\d{{4}})\b"),
    ("mdy", rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b"),
    ("month_year", rf"\b({_MONTH_NAMES})\.?\s+(\d{{4}})\b"),
    ("quarter", r"\b[Qq]([1-4])\s*(?:of\s*)?(\d{4})\b"),
    ("fiscal_year", r"\b(?:FY|fiscal year)\s*(\d{4})\b"),
    # "2020a" is how a reference list tells two 2020 papers apart.
    ("year", r"\b(19\d{2}|20\d{2})(?:\b|(?=[a-c]\b))"),
]
_COMPILED = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in PATTERNS]

# A full stop followed by a comma, a bracket, a digit or a lowercase word does
# not end a sentence: "Smith et al., 2019" and "Marr et al. (1982)" stay whole,
# so the citation around the year is still visible to the rules below.
_SENTENCE = re.compile(r"(?:[^.!?\n]|\.(?=\s*[a-z(,;\d]))+(?:[.!?]|\n|$)")

# What marks a date as a reference rather than an event. Each rule looks only
# at the text around the match, so the reason can be stated.
#
# Links and copyright lines apply at any precision. The citation rules apply
# to bare years only: citations are dated by year, while "the cutover (March
# 2021)" is an event however it is punctuated.
_LINK_TOKEN = re.compile(r"/|https?:|www\.|\.(?:com|org|net|edu|gov|io|ai|sg)\b", re.IGNORECASE)
_COPYRIGHT = re.compile(r"©|\(c\)|\bcopyright\b|\ball rights reserved\b", re.IGNORECASE)
_REFERENCE_LINE = re.compile(
    r"^\s*(?:\[\d+\]|references?\b|bibliography\b|sources?\s*:|cited\b|further reading\b)",
    re.IGNORECASE,
)
_CITATION_MARKER = re.compile(
    r"\bet al\b|\bdoi\b|\barxiv\b|\bisbn\b|\bpp\.|\bvol\.|\bproceedings\b|\bjournal\b"
    r"|\buniversity press\b|\bpublish(?:ed|er|ing)\b|\bspringer\b|\belsevier\b|\bieee\b|\bacm\b"
    r"|\bwiley\b|\bo['’]reilly\b|\bneurips\b|\bicml\b|\biclr\b|\bcvpr\b|\biccv\b|\beccv\b"
    r"|\baaai\b",
    re.IGNORECASE,
)
# "(1982)", "(Ghosh, 2020)", "(Smith et al., 2019; Jones, 2020a)"
_OPENS_CITATION = re.compile(r"\(\s*$|\([^()]*[,;]\s*$")
_CLOSES_CITATION = re.compile(r"^[a-z]?\s*[),;]")
# "Ghosh, 2020" or "Springer, 2006" closing a sentence or a line.
_NAME_COMMA = re.compile(r"[A-Z][\w'’\-]+(?:\s+et\s+al\.?)?,\s*$")
_ENDS_CLAUSE = re.compile(r"^\s*[).;,]?\s*$")


def _reference_basis(sentence: str, start: int, end: int, precision: str) -> str | None:
    """Why the date at sentence[start:end] is a reference, or None for an event."""
    token_start = sentence.rfind(" ", 0, start) + 1
    token_end = sentence.find(" ", end)
    token = sentence[token_start : token_end if token_end != -1 else len(sentence)]
    if _LINK_TOKEN.search(token):
        return "link"
    if _COPYRIGHT.search(sentence[max(0, start - 40) : start]):
        return "copyright"
    if precision != "year":
        return None
    before, after = sentence[:start], sentence[end:]
    if _OPENS_CITATION.search(before) and _CLOSES_CITATION.match(after):
        return "citation"
    if _NAME_COMMA.search(before) and _ENDS_CLAUSE.match(after):
        return "citation"
    if _REFERENCE_LINE.match(sentence):
        return "reference list"
    if _CITATION_MARKER.search(sentence):
        return "citation"
    return None

# Two ways to put an event in a lane, and neither of them guesses.
#
# The library's own topics come first: a topic was confirmed by a human at
# registration, so grouping by it is grouping by a judgement that was
# already made. Lanes are the owner's most-used topics, which means the
# timeline is organised the way their library is rather than the way a
# generic taxonomy assumes it should be.
#
# The six named lanes below are the fallback, used when a document carries
# no confirmed topic. A lane is assigned only when the evidence contains one
# of its words, so the panel can show what matched. The alternative — asking
# a model to classify — would put a document in "Governance" with nothing to
# point at.
LANES: list[tuple[str, tuple[str, ...]]] = [
    ("Strategy", ("strategy", "strategic", "vision", "roadmap", "mission", "objective")),
    (
        "Architecture",
        ("architecture", "architectural", "design pattern", "blueprint", "reference model"),
    ),
    (
        "Governance",
        ("governance", "policy", "compliance", "risk", "audit", "regulation", "standard"),
    ),
    (
        "Technology",
        ("technology", "platform", "infrastructure", "cloud", "system", "software", "model"),
    ),
    (
        "Projects",
        ("project", "programme", "program", "initiative", "milestone", "delivery", "rollout"),
    ),
    (
        "People",
        ("team", "hire", "appointed", "leadership", "reorganisation", "reorganization", "staff"),
    ),
]
OTHER_LANE = "Other"
LANE_NAMES = [name for name, _ in LANES] + [OTHER_LANE]

ENTITY_FIELDS = ("people", "organizations", "projects", "technologies")
MAX_TITLE_CHARS = 90
MAX_EVIDENCE_CHARS = 320


@dataclass
class Event:
    id: str
    artifact_id: str
    fragment_id: str
    title: str
    description: str | None
    category: str
    category_basis: str | None
    event_type: str
    date: str
    end_date: str | None
    precision: str
    expression: str
    evidence: str
    kind: str
    reference_basis: str | None
    source_location: dict
    filename: str
    author: str | None
    # What the document itself says about its own size and dates, plus where
    # each value came from. Never inferred: a date the file does not assert
    # stays null rather than being filled in with the upload time, which
    # records when CEREBRO received the file and not when anyone wrote it.
    document: dict = field(default_factory=dict)
    entities: dict = field(default_factory=dict)
    extraction_method: str = f"{EXTRACTION_METHOD} v{EXTRACTION_VERSION}"
    approval_status: str = "registered"

    def as_dict(self) -> dict:
        return {**self.__dict__}


def _normalise(kind: str, match: re.Match) -> tuple[str, str] | None:
    """A matched expression as (ISO date, precision), or None if impossible."""
    try:
        if kind == "iso":
            year, month, day = (int(g) for g in match.groups())
            return date(year, month, day).isoformat(), "day"
        if kind == "dmy":
            day, name, year = match.group(1), match.group(2).lower().rstrip("."), match.group(3)
            return date(int(year), MONTHS[name], int(day)).isoformat(), "day"
        if kind == "mdy":
            name, day, year = match.group(1).lower().rstrip("."), match.group(2), match.group(3)
            return date(int(year), MONTHS[name], int(day)).isoformat(), "day"
        if kind == "month_year":
            name, year = match.group(1).lower().rstrip("."), match.group(2)
            return date(int(year), MONTHS[name], 1).isoformat(), "month"
        if kind == "quarter":
            quarter, year = int(match.group(1)), int(match.group(2))
            return date(year, (quarter - 1) * 3 + 1, 1).isoformat(), "quarter"
        if kind in ("year", "fiscal_year"):
            return date(int(match.group(1)), 1, 1).isoformat(), "year"
    except (ValueError, KeyError):
        # A real string that is not a real date — "31 February 2024", or a
        # four-digit number that is not a year in context.
        return None
    return None


def _expressions(sentence: str) -> list[tuple[str, str, str, int, int]]:
    """Every date expression in a sentence, most specific first, no overlaps."""
    found: list[tuple[str, str, str, int, int]] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in _COMPILED:
        for match in pattern.finditer(sentence):
            start, end = match.span()
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            normalised = _normalise(kind, match)
            if normalised is None:
                continue
            iso, precision = normalised
            taken.append((start, end))
            found.append((iso, precision, match.group(0), start, end))
    return found


def _lane(
    text: str, topics: list[str], *, preferred: list[str] | None = None
) -> tuple[str, str | None]:
    """Which lane, and what put it there.

    A confirmed topic wins: it is the owner's own classification, approved
    at registration. Only a document without one falls through to the
    keyword lanes.
    """
    if preferred:
        for topic in topics:
            for lane in preferred:
                if topic.lower() == lane.lower():
                    return lane, f"topic: {topic}"

    haystack = f"{text} {' '.join(topics)}".lower()
    for name, words in LANES:
        for word in words:
            if word in haystack:
                return name, word
    return OTHER_LANE, None


def _title(sentence: str) -> str:
    """The document's own words, trimmed — never a generated summary."""
    clean = " ".join(sentence.split())
    if len(clean) <= MAX_TITLE_CHARS:
        return clean
    cut = clean[:MAX_TITLE_CHARS].rsplit(" ", 1)[0]
    return f"{cut}…"


def _event_type(sentence: str) -> str:
    """A coarse label from the words present, or a plain statement."""
    lowered = sentence.lower()
    for label, words in (
        (
            "decision",
            ("approved", "decided", "agreed", "signed off", "authorised", "authorized"),
        ),
        (
            "milestone",
            ("completed", "delivered", "launched", "went live", "cutover", "released"),
        ),
        ("plan", ("will", "planned", "scheduled", "roadmap", "target")),
        ("change", ("migrated", "replaced", "upgraded", "restructure", "appointed")),
    ):
        if any(word in lowered for word in words):
            return label
    return "statement"


def extract_from_text(
    text: str,
    *,
    topics: list[str] | None = None,
    entities: dict | None = None,
    lanes: list[str] | None = None,
) -> list[dict]:
    """Every dated statement in a passage, as plain dictionaries.

    Pure and side-effect free, which is what makes it testable against a
    sentence rather than against a database.
    """
    topics = topics or []
    entities = entities or {}
    out: list[dict] = []

    for match in _SENTENCE.finditer(text):
        sentence = match.group().strip()
        if not sentence:
            continue
        expressions = _expressions(sentence)
        if not expressions:
            continue

        # One event per sentence, dated by its first expression that is not
        # a reference; a second such date becomes the range's end rather
        # than a separate event, which is what "from March to June" means.
        # "In 2021 we adopted Marr (1982)" is a 2021 event. A sentence whose
        # dates are all references is one reference, dated by the first.
        bases = [_reference_basis(sentence, s, e, p) for _, p, _, s, e in expressions]
        dated = [x for x, basis in zip(expressions, bases, strict=True) if basis is None]
        kind = "event" if dated else "reference"
        reference_basis = None if dated else bases[0]
        dated = dated or expressions
        iso, precision, expression, _, _ = dated[0]
        end = dated[1][0] if len(dated) > 1 and dated[1][0] > iso else None
        lane, basis = _lane(sentence, topics, preferred=lanes)

        mentioned = {
            field_name: [
                value
                for value in (entities.get(field_name) or [])
                if isinstance(value, str) and value.lower() in sentence.lower()
            ]
            for field_name in ENTITY_FIELDS
        }

        out.append(
            {
                "title": _title(sentence),
                "description": None,
                "category": lane,
                "category_basis": basis,
                "event_type": _event_type(sentence),
                "date": iso,
                "end_date": end,
                "precision": precision,
                "expression": expression,
                "kind": kind,
                "reference_basis": reference_basis,
                "evidence": " ".join(sentence.split())[:MAX_EVIDENCE_CHARS],
                "entities": {k: v for k, v in mentioned.items() if v},
            }
        )
    return out


def lanes_for_owner(db: Session, owner_id: uuid.UUID, *, limit: int = 6) -> list[str]:
    """The owner's most-used confirmed topics, which become their lanes.

    Counted over registered artifacts only, because an unregistered one
    carries topics nobody has approved yet. A library with no topics at all
    gets the six named lanes instead, so the timeline is never empty of
    structure.
    """
    rows = db.execute(
        select(Artifact.artifact_metadata).where(
            Artifact.owner_id == owner_id, Artifact.status == "registered"
        )
    ).all()

    counts: Counter[str] = Counter()
    for (meta,) in rows:
        for topic in (meta or {}).get("topics") or []:
            if isinstance(topic, str) and topic.strip():
                counts[topic.strip()] += 1

    return [topic for topic, _ in counts.most_common(limit)]


def _document_facts(extraction: dict | None, registered: object, meta: dict) -> dict:
    """Size and dates as the document asserts them, plus CEREBRO's own record.

    `title` is what a human confirmed at review, or the filename when they
    confirmed nothing — the card leads with it because a sentence lifted out
    of the middle of a document does not say which document it is.

    `pages` is a count extraction made, not a claim read out of the text.
    `created` and `modified` come only from the file's own metadata — PDF
    /Info, Office core properties — so both are frequently null, and null is
    the honest answer. `registered` is the one date CEREBRO itself knows.
    """
    extraction = extraction or {}
    structure = extraction.get("structure") or {}
    properties = extraction.get("properties") or {}

    title = meta.get("title") if isinstance(meta.get("title"), str) else None
    pages = structure.get("pages") or structure.get("slides")
    return {
        "title": (title or "").strip() or None,
        "title_basis": "confirmed metadata" if (title or "").strip() else None,
        "pages": pages if isinstance(pages, int) and pages > 0 else None,
        "blocks": extraction.get("block_count"),
        "characters": extraction.get("character_count"),
        "created": properties.get("created_date"),
        "modified": properties.get("modified_date"),
        "registered": registered.isoformat() if hasattr(registered, "isoformat") else None,
        # Said plainly, because the three dates do not mean the same thing.
        "created_basis": "document metadata" if properties.get("created_date") else None,
        "modified_basis": "document metadata" if properties.get("modified_date") else None,
        "registered_basis": "CEREBRO record",
    }


def events_for_owner(
    db: Session, owner_id: uuid.UUID, *, lanes: list[str] | None = None
) -> tuple[list[Event], dict]:
    """Dated events from this owner's registered knowledge, plus what it cost.

    Only registered fragments are read, so nothing awaiting review can place
    an event on the timeline.
    """
    started = time.perf_counter()
    rows = db.execute(
        select(
            KnowledgeFragment.id,
            KnowledgeFragment.artifact_id,
            KnowledgeFragment.content,
            KnowledgeFragment.source_location,
            Artifact.filename,
            Artifact.artifact_metadata,
            Artifact.extraction,
            Artifact.registered_at,
            Artifact.created_at,
        )
        .join(Artifact, Artifact.id == KnowledgeFragment.artifact_id)
        .where(
            KnowledgeFragment.owner_id == owner_id,
            Artifact.status == "registered",
        )
        .order_by(KnowledgeFragment.artifact_id, KnowledgeFragment.ordinal)
    ).all()

    events: list[Event] = []
    seen: set[str] = set()
    duplicates = 0
    scanned = 0

    for (
        fragment_id,
        artifact_id,
        content,
        location,
        filename,
        meta,
        extraction,
        registered_at,
        uploaded_at,
    ) in rows:
        scanned += 1
        meta = meta or {}
        facts = _document_facts(extraction, registered_at or uploaded_at, meta)
        topics = [t for t in (meta.get("topics") or []) if isinstance(t, str)]
        found = extract_from_text(
            content,
            topics=topics,
            entities={f: meta.get(f) or [] for f in ENTITY_FIELDS},
            lanes=lanes,
        )
        for item in found:
            # Chunks overlap by design, so the same sentence is read twice.
            # The same statement on the same date is one event.
            key = hashlib.sha256(
                f"{artifact_id}|{item['date']}|{item['evidence'].lower()}".encode()
            ).hexdigest()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            events.append(
                Event(
                    id=f"event:{key[:16]}",
                    artifact_id=str(artifact_id),
                    fragment_id=str(fragment_id),
                    source_location=location or {},
                    filename=filename,
                    author=meta.get("author"),
                    document=facts,
                    **item,
                )
            )

    events.sort(key=lambda e: (e.date, e.title))
    stats = {
        "fragments_scanned": scanned,
        "events": len(events),
        "duplicates_dropped": duplicates,
        "unknown_dates": 0,
        "took_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    telemetry.record(
        "timeline.extract",
        model=None,
        duration_ms=int(stats["took_ms"]),
        algorithm=f"{EXTRACTION_METHOD} v{EXTRACTION_VERSION}",
        detail=(
            f"{scanned} fragments, {len(events)} events, "
            f"{duplicates} duplicates dropped"
        ),
    )
    return events, stats
