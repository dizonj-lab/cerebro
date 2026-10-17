"""Timeline anchors: persisting, reprocessing and approving a CV's chronology.

The hard requirement here is that reprocessing a CV must not duplicate a
person's career, and must not undo their corrections. Both fall out of one
decision: an anchor is identified by its `fingerprint`, so the same life
event found again is the same row. On a reprocess a row that nobody has
edited is refreshed, and a row someone has edited is left exactly as they
left it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.anchor import TimelineAnchor
from app.services import cv as cv_reader

EDITABLE = ("event_type", "title", "organization", "description", "start_date", "end_date",
            "date_precision")


def for_owner(
    db: Session, owner_id: uuid.UUID, *, approved_only: bool = False
) -> list[TimelineAnchor]:
    """This owner's anchors, earliest first. Undated ones come last."""
    query = select(TimelineAnchor).where(TimelineAnchor.owner_id == owner_id)
    if approved_only:
        query = query.where(TimelineAnchor.approval_status == "approved")
    rows = list(db.execute(query).scalars())
    return sorted(rows, key=lambda a: (a.start_date is None, a.start_date or "", a.title))


def ingest(
    db: Session, owner_id: uuid.UUID, *, artifact_id: uuid.UUID, text: str
) -> dict:
    """Read a CV and record what it says, without disturbing what was corrected.

    Returns counts rather than rows: the caller re-reads through `for_owner`,
    which applies the ordering.
    """
    found = cv_reader.extract(text)
    existing = {
        row.fingerprint: row
        for row in db.execute(
            select(TimelineAnchor).where(TimelineAnchor.owner_id == owner_id)
        ).scalars()
    }

    added = refreshed = preserved = 0
    for anchor in found:
        row = existing.get(anchor.fingerprint)
        payload = anchor.as_dict()
        if row is None:
            db.add(
                TimelineAnchor(
                    owner_id=owner_id,
                    source_artifact_id=artifact_id,
                    fingerprint=anchor.fingerprint,
                    provenance_type="cv_extraction",
                    approval_status="suggested",
                    # What the CV said, kept whole and never rewritten by a
                    # later correction.
                    extracted=payload,
                    **{k: payload[k] for k in (
                        "event_type", "title", "organization", "start_date",
                        "end_date", "date_precision", "evidence_text", "source_location",
                    )},
                )
            )
            added += 1
            continue

        if row.user_edited:
            # Someone corrected this. A reprocess records what the document
            # now says and changes nothing they decided.
            row.extracted = payload
            preserved += 1
            continue

        row.source_artifact_id = artifact_id
        row.extracted = payload
        for field in ("event_type", "title", "organization", "start_date", "end_date",
                      "date_precision", "evidence_text", "source_location"):
            setattr(row, field, payload[field])
        refreshed += 1

    db.flush()
    return {
        "found": len(found),
        "added": added,
        "refreshed": refreshed,
        "preserved_user_edits": preserved,
    }


def update(
    db: Session, owner_id: uuid.UUID, anchor_id: uuid.UUID, changes: dict
) -> TimelineAnchor | None:
    """Apply a user's correction. Ownership is checked, never assumed."""
    row = db.get(TimelineAnchor, anchor_id)
    if row is None or row.owner_id != owner_id:
        return None

    for field in EDITABLE:
        if field in changes:
            setattr(row, field, changes[field])
            # Marked here rather than inferred later: this is the flag that
            # protects the correction from the next reprocess.
            row.user_edited = True
    if "approval_status" in changes:
        row.approval_status = changes["approval_status"]
    db.flush()
    return row


def add_manual(db: Session, owner_id: uuid.UUID, values: dict) -> TimelineAnchor:
    """An event the CV missed. Approved on arrival: the user asserted it."""
    anchor = cv_reader.Anchor(
        event_type=values.get("event_type") or "other",
        title=values["title"],
        organization=values.get("organization"),
        start_date=values.get("start_date"),
        end_date=values.get("end_date"),
        date_precision=values.get("date_precision") or "unknown",
        evidence_text=None,
        source_location={},
    )
    row = TimelineAnchor(
        owner_id=owner_id,
        source_artifact_id=None,
        fingerprint=anchor.fingerprint,
        provenance_type="user_entered",
        approval_status="approved",
        user_edited=True,
        extracted={},
        event_type=anchor.event_type,
        title=anchor.title,
        organization=anchor.organization,
        description=values.get("description"),
        start_date=anchor.start_date,
        end_date=anchor.end_date,
        date_precision=anchor.date_precision,
        evidence_text=None,
        source_location={},
    )
    db.add(row)
    db.flush()
    return row


def approve_all(db: Session, owner_id: uuid.UUID) -> int:
    """Approve every suggestion still outstanding. Rejections stay rejected."""
    rows = [
        row
        for row in db.execute(
            select(TimelineAnchor).where(
                TimelineAnchor.owner_id == owner_id,
                TimelineAnchor.approval_status == "suggested",
            )
        ).scalars()
    ]
    for row in rows:
        row.approval_status = "approved"
    db.flush()
    return len(rows)


def as_dict(anchor: TimelineAnchor) -> dict:
    return {
        "id": str(anchor.id),
        "event_type": anchor.event_type,
        "title": anchor.title,
        "organization": anchor.organization,
        "description": anchor.description,
        "start_date": anchor.start_date,
        "end_date": anchor.end_date,
        "date_precision": anchor.date_precision,
        "source_artifact_id": (
            str(anchor.source_artifact_id) if anchor.source_artifact_id else None
        ),
        "source_location": anchor.source_location or {},
        "evidence_text": anchor.evidence_text,
        # What the CV said before anyone corrected it, so a reviewer can see
        # both and the correction is never mistaken for the source.
        "extracted": anchor.extracted or {},
        "provenance_type": anchor.provenance_type,
        "approval_status": anchor.approval_status,
        "user_edited": anchor.user_edited,
    }
