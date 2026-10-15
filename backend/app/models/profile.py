"""Profile and preferences — who the user is, and how CEREBRO should behave.

Kept separate from User, which stays purely the account: identity, credentials
and account metadata. Both tables use the user id as their own primary key, so
the one-to-one relationship cannot be violated and no second identity exists.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Response style for future AI features. Stored only; nothing reads it yet.
RESPONSE_STYLES = ("concise", "balanced", "detailed")
AI_PROCESSING_MODES = ("local", "cloud")
KNOWLEDGE_VISIBILITY = ("private", "shared")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    # Personal
    full_name: Mapped[str | None] = mapped_column(String(120))
    bio: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    # Professional
    role_title: Mapped[str | None] = mapped_column(String(120))
    organization: Mapped[str | None] = mapped_column(String(120))
    industry: Mapped[str | None] = mapped_column(String(120))
    years_experience: Mapped[int | None] = mapped_column(Integer)
    expertise: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list, nullable=False)

    # Interests and goals
    interests: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list, nullable=False)
    current_topics: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), default=list, nullable=False
    )
    learning_goals: Mapped[str | None] = mapped_column(Text)
    career_goals: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    response_style: Mapped[str] = mapped_column(String(20), default="balanced", nullable=False)
    ai_suggestions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recall_suggestions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Privacy is the default, not an opt-in.
    knowledge_visibility: Mapped[str] = mapped_column(
        String(20), default="private", nullable=False
    )

    # --- AI & privacy -----------------------------------------------------
    # Local is the default. Cloud requires explicit consent; nothing in CEREBRO
    # may switch this automatically.
    ai_processing_mode: Mapped[str] = mapped_column(String(10), default="local", nullable=False)
    local_provider: Mapped[str | None] = mapped_column(String(60))
    local_model: Mapped[str | None] = mapped_column(String(120))
    cloud_provider: Mapped[str | None] = mapped_column(String(60))
    cloud_model: Mapped[str | None] = mapped_column(String(120))
    # Consent is recorded, never assumed. No API credentials are stored here;
    # those belong in secret management and must never reach the frontend.
    cloud_ai_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cloud_ai_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
