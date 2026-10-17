"""What each AI/ML operation actually cost, kept so it can be analysed later.

`services/telemetry.py` holds a 50-entry in-memory ring buffer: enough to
show what is running right now, useless for a report. Measuring a model's
performance means comparing yesterday with today, and that needs rows.

This is deliberately a metrics table and not a second copy of the knowledge.
It records what ran, how long it took and what it produced — never a prompt,
never a passage, never document text. The one identifier it carries is the
artifact an operation was about, so a slow ingestion can be traced to the
file that caused it.

Owner-scoped like everything else: one person's costs are not another's to
read.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The stages a report groups by.
KINDS = ("ingestion", "enrichment", "embedding", "search", "recall", "extraction")


class OperationMetric(Base):
    __tablename__ = "operation_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL")
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    # The model where one ran, or null where the work was deterministic —
    # which is itself worth reporting, since most of CEREBRO is.
    model: Mapped[str | None] = mapped_column(String(120))
    # "cosine (brute force)", "reciprocal rank fusion", "keyphrase
    # statistics": what did the work when no model did.
    algorithm: Mapped[str | None] = mapped_column(String(120))
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    # Counts that make a duration meaningful: bytes and pages for an
    # ingestion, fragments and vectors for an embedding, hits for a search.
    units: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_metrics_owner_at", "owner_id", "at"),)
