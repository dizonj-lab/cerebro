"""Timeline anchors: the chronology a person states about themselves.

An artifact's timeline comes from what documents say. This is the other
half — the career and education a CV asserts — and it is a different kind of
claim, so it gets its own table rather than being forced into the artifact
events.

Three properties the schema enforces rather than hopes for:

* **Suggested until approved.** An anchor arrives as `suggested` and only a
  human moves it to `approved`. Nothing unapproved reaches the Galaxy or the
  Timeline.
* **The original survives correction.** `extracted` keeps what the CV
  actually said; the editable columns hold what the user confirmed. A
  reprocess may refresh the former and must never overwrite the latter.
* **Unknown stays unknown.** Both dates are nullable and `date_precision`
  records how much the CV actually gave. A missing end date means the CV did
  not state one — never "today".

`fingerprint` is what makes re-uploading a CV idempotent: it identifies the
same life event across reprocessing, so a replaced CV updates its anchors
instead of duplicating them.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EVENT_TYPES = (
    "education",
    "employment",
    "project",
    "certification",
    "professional_development",
    "personal_milestone",
    "other",
)
APPROVAL_STATUSES = ("suggested", "approved", "rejected")
# How much of a date the source actually gave. Never widened by guessing.
DATE_PRECISIONS = ("day", "month", "year", "unknown")


class TimelineAnchor(Base):
    __tablename__ = "timeline_anchors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The CV this came from. Null for an anchor the user added by hand, which
    # is a first-class way to have one.
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL")
    )

    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    # ISO dates, or null where the CV stated none.
    start_date: Mapped[str | None] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10))
    date_precision: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")

    source_location: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # The CV's own words that produced this. An anchor with no evidence is an
    # anchor that cannot be checked.
    evidence_text: Mapped[str | None] = mapped_column(Text)
    # What extraction read, kept whole, so a user's correction never destroys
    # the record of what the document actually said.
    extracted: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # "cv_extraction" or "user_entered". Never inferred from anything else.
    provenance_type: Mapped[str] = mapped_column(String(32), nullable=False, default="cv_extraction")
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested")
    # True once a human has edited it: a reprocess refreshes untouched
    # anchors and leaves corrected ones alone.
    user_edited: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Stable identity for one life event across re-uploads of the CV.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # One anchor per life event per owner — this is what stops a
        # re-uploaded CV producing a second copy of every job.
        UniqueConstraint("owner_id", "fingerprint", name="uq_anchor_owner_fingerprint"),
        Index("ix_anchors_owner_start", "owner_id", "start_date"),
    )
