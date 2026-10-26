"""The timeline: approved knowledge placed at the dates its documents state.

Events come from registered fragments only, and every one carries the
expression that dated it and the sentence it came from. Filters are applied
server-side so the browser is never handed the whole library to sift.
"""
import time
from collections import Counter, defaultdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.services import anchors as anchor_service
from app.services import telemetry, temporal

router = APIRouter(prefix="/api/timeline", tags=["timeline"])

MAX_EVENTS = 1500
MAX_RELATED = 8


# A month in which no document reported a page count. Kept distinct from a
# month of zero pages: the bar falls back to counting documents there, rather
# than claiming the knowledge has no volume.
_EMPTY_VOLUME = {"pages": 0, "documents": 0, "by_category": {}, "basis": "document count"}


def _volume_by_month(events: list[temporal.Event]) -> dict[str, dict]:
    """How much document there is per month, and in which categories.

    Volume is pages, because a month holding one 80-page thesis and a month
    holding one two-page memo are not the same amount of knowledge, and a
    bar that counts events says they are. Each document is counted once per
    month however many events it produced — otherwise a document that
    mentions many dates would inflate its own size.
    """
    pages: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    seen: set[tuple[str, str]] = set()
    counted: dict[str, int] = Counter()

    for event in events:
        month = event.date[:7]
        key = (month, event.artifact_id)
        if key in seen:
            continue
        seen.add(key)
        counted[month] += 1
        # A document with no page count still has presence; one page is the
        # floor, not a guess at its real length.
        pages[month][event.category] += event.document.get("pages") or 1

    return {
        month: {
            "pages": sum(by_category.values()),
            "documents": counted[month],
            "by_category": dict(by_category),
            "basis": "page count where the document reports one",
        }
        for month, by_category in pages.items()
    }


def _within(event: temporal.Event, start: str | None, end: str | None) -> bool:
    if start and event.date < start:
        return False
    return not (end and event.date > end)


@router.get("")
def read(
    current_user: CurrentUser,
    db: DbSession,
    categories: Annotated[list[str], Query()] = [],  # noqa: B006 - FastAPI query list
    sources: Annotated[list[str], Query()] = [],  # noqa: B006 - FastAPI query list
    entity_type: str | None = None,
    entity: str | None = None,
    start: str | None = None,
    end: str | None = None,
    references: bool = False,
) -> dict:
    started = time.perf_counter()
    # The owner's own topics are the lanes; the six named ones are the
    # fallback for a library that has not confirmed any.
    owner_lanes = temporal.lanes_for_owner(db, current_user.id)
    everything, stats = temporal.events_for_owner(db, current_user.id, lanes=owner_lanes)
    # Cited dates ("Marr (1982)", a URL's /2021/) are left out unless asked
    # for, and the response says how many, so hiding them is never silent.
    # Range, histogram and facets follow the same choice: a 1982 citation
    # should not stretch a library of 2020s documents across forty years.
    hidden_references = 0 if references else sum(e.kind == "reference" for e in everything)
    events = everything if references else [e for e in everything if e.kind != "reference"]

    # The histogram is built from everything, so the navigator keeps showing
    # the whole range while the lanes show a filtered slice of it.
    months = Counter(event.date[:7] for event in events)
    volume = _volume_by_month(events)

    selected = [
        event
        for event in events
        if (not categories or event.category in categories)
        and (not sources or event.artifact_id in sources)
        and _within(event, start, end)
        and (
            not entity
            or any(
                entity in values
                for field, values in event.entities.items()
                if not entity_type or field == entity_type
            )
        )
    ]

    counts = Counter(event.category for event in selected)
    # Named lanes are only shown when the library has no topics of its own:
    # six empty rows of someone else's taxonomy is noise.
    names = owner_lanes or [name for name, _ in temporal.LANES]
    lanes = [{"name": name, "count": counts.get(name, 0)} for name in names]
    if counts.get(temporal.OTHER_LANE) or not names:
        lanes.append({"name": temporal.OTHER_LANE, "count": counts.get(temporal.OTHER_LANE, 0)})

    # Facets are the values actually present, so no filter is offered that
    # would select nothing.
    entity_values: dict[str, set[str]] = defaultdict(set)
    for event in events:
        for field, values in event.entities.items():
            entity_values[field].update(values)

    took_ms = round((time.perf_counter() - started) * 1000, 1)
    telemetry.record(
        "timeline.query",
        model=None,
        duration_ms=int(took_ms),
        algorithm="deterministic date parsing + server-side filtering",
        detail=f"{len(selected)} of {len(events)} events",
    )

    return {
        "events": [event.as_dict() for event in selected[:MAX_EVENTS]],
        "lanes": lanes,
        "histogram": [
            {"month": month, "count": count, **volume.get(month, _EMPTY_VOLUME)}
            for month, count in sorted(months.items())
        ],
        "range": {
            "earliest": events[0].date if events else None,
            "latest": events[-1].date if events else None,
        },
        "sources": sorted(
            {(event.artifact_id, event.filename) for event in events},
            key=lambda pair: pair[1],
        ),
        "entity_values": {field: sorted(values) for field, values in entity_values.items()},
        "lane_source": "confirmed topics" if owner_lanes else "keyword fallback",
        # The chronology the user states about themselves, from their CV.
        # Approved only: a suggestion is not a fact about someone's life, and
        # the timeline is personalised only once they have said so. These are
        # a backdrop, never a date: an artifact that states no date of its own
        # does not borrow one from the job it happens to fall inside.
        "anchors": [
            anchor_service.as_dict(a)
            for a in anchor_service.for_owner(db, current_user.id, approved_only=True)
        ],
        "extraction": {
            "method": temporal.EXTRACTION_METHOD,
            "version": temporal.EXTRACTION_VERSION,
            **stats,
        },
        "references": {
            "included": references,
            "hidden": hidden_references,
            "total": sum(e.kind == "reference" for e in everything),
        },
        "total": len(selected),
        "took_ms": took_ms,
    }


@router.get("/related")
def related(current_user: CurrentUser, db: DbSession, event: str) -> dict:
    """Events sharing an entity, a source or a lane with this one.

    Each one says why it is related. The relationship is co-occurrence of
    something both events actually carry — never an inferred semantic link,
    which CEREBRO has no way to establish and so does not claim.
    """
    events, _ = temporal.events_for_owner(
        db, current_user.id, lanes=temporal.lanes_for_owner(db, current_user.id)
    )
    by_id = {item.id: item for item in events}
    anchor = by_id.get(event)
    if anchor is None:
        raise HTTPException(status_code=404, detail="No such event.")

    anchor_entities = {(f, v) for f, values in anchor.entities.items() for v in values}

    scored: list[tuple[int, str, temporal.Event]] = []
    for other in events:
        if other.id == anchor.id:
            continue
        shared = {
            (f, v) for f, values in other.entities.items() for v in values
        } & anchor_entities
        if shared:
            field, value = sorted(shared)[0]
            scored.append((3, f"Both mention {value}", other))
        elif other.artifact_id == anchor.artifact_id:
            scored.append((2, "From the same document", other))
        elif other.category == anchor.category and anchor.category != temporal.OTHER_LANE:
            scored.append((1, f"Both in {anchor.category}", other))

    scored.sort(key=lambda row: (-row[0], abs((row[2].date > anchor.date) - 0.5), row[2].date))
    return {
        "event": anchor.as_dict(),
        "related": [
            {**other.as_dict(), "relationship": why} for _, why, other in scored[:MAX_RELATED]
        ],
    }


@router.get("/journey")
def journey(current_user: CurrentUser, db: DbSession, entity: str, field: str = "projects") -> dict:
    """One entity's events in order — the Knowledge Journey, second mode.

    The same extraction, filtered to what mentions the entity. Milestones are
    whatever the documents actually say about it, in the order they say it
    happened; nothing is added to make a story complete.
    """
    events, _ = temporal.events_for_owner(
        db, current_user.id, lanes=temporal.lanes_for_owner(db, current_user.id)
    )
    steps = [
        event
        for event in events
        # A cited year is not a step in the entity's own story.
        if event.kind != "reference" and entity in (event.entities.get(field) or [])
    ]
    return {
        "entity": entity,
        "field": field,
        "steps": [event.as_dict() for event in steps],
        "total": len(steps),
    }
