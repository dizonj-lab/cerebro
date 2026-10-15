"""Artifact model — a source document the knowledge twin is built from.

Mirrors the PoC artifact contract: deterministic inspection, editable
metadata, per-stage provenance and integrity flags, all carried on the row
so a registered artifact can be audited without replaying the pipeline.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Lifecycle. AI enrichment will later sit between INSPECTED and APPROVED.
ARTIFACT_STATUSES = ("inspected", "approved", "registered", "rejected")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Ownership is the security boundary: every query filters on this.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(160))
    modality: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Content address. Unique per owner, so re-uploading the same bytes is
    # detected rather than silently duplicated.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="inspected")

    # The PoC contract, carried verbatim.
    inspection: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    field_methods: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    integrity: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_artifacts_owner_created", "owner_id", "created_at"),
        Index("uq_artifacts_owner_sha256", "owner_id", "sha256", unique=True),
    )
