"""Knowledge fragments and their embeddings.

A fragment is a chunk of an artifact's extracted text with the location it
came from, so anything retrieved can be traced back to a page or slide of a
source document: USER -> ARTIFACT -> KNOWLEDGE FRAGMENT -> SOURCE LOCATION.

Fragments exist only for artifacts the user has approved and registered.
Nothing unapproved reaches retrieval.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    REAL,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeFragment(Base):
    __tablename__ = "knowledge_fragments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Denormalised from the artifact so every retrieval query can filter on
    # the owner without a join. Ownership is the security boundary.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Content address of the chunk. Unique per artifact, so re-registering an
    # artifact re-uses its fragments instead of duplicating them.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Page, slide, section, paragraph and character span, as extraction found
    # them. Absent keys mean the modality does not have that notion — never a
    # fabricated default.
    source_location: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="body")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("artifact_id", "content_sha256", name="uq_fragments_artifact_content"),
        Index("ix_fragments_owner", "owner_id"),
        Index("ix_fragments_artifact_ordinal", "artifact_id", "ordinal"),
    )


class FragmentEmbedding(Base):
    """A fragment's vector, with the provider that produced it.

    Stored as a float4[] rather than a pgvector column: pgvector is not
    available in the target PostgreSQL, and brute-force cosine over arrays is
    adequate at this scale. The `VectorIndex` interface exists so this can be
    replaced without touching callers.

    Provider, model and dimensions are recorded because vectors from
    different spaces must never be compared. Search filters on all three.
    """

    __tablename__ = "fragment_embeddings"

    fragment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_fragments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    # L2-normalised on write, so cosine similarity is a dot product.
    vector: Mapped[list[float]] = mapped_column(ARRAY(REAL), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_embeddings_owner_space", "owner_id", "provider", "model", "dimensions"),
    )
