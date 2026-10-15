"""Profile, preferences and account contracts.

No schema accepts a user id: identity always comes from the session, so a
client cannot address another user's record.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.profile import AI_PROCESSING_MODES, KNOWLEDGE_VISIBILITY, RESPONSE_STYLES

MAX_TAGS = 20
MAX_TAG_LENGTH = 60


def _clean_tags(values: list[str]) -> list[str]:
    """Trim, drop blanks, de-duplicate case-insensitively, preserve order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        tag = " ".join(raw.split())[:MAX_TAG_LENGTH]
        if not tag or tag.casefold() in seen:
            continue
        seen.add(tag.casefold())
        out.append(tag)
    return out[:MAX_TAGS]


class ProfileBase(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    role_title: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=120)
    years_experience: int | None = Field(default=None, ge=0, le=80)
    expertise: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    current_topics: list[str] = Field(default_factory=list)
    learning_goals: str | None = Field(default=None, max_length=1000)
    career_goals: str | None = Field(default=None, max_length=1000)

    @field_validator("expertise", "interests", "current_topics", mode="after")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return _clean_tags(v)

    @field_validator(
        "full_name", "bio", "location", "timezone", "role_title",
        "organization", "industry", "learning_goals", "career_goals",
        mode="after",
    )
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ProfileUpdate(ProfileBase):
    """Full replacement of the editable profile fields."""


class ProfileResponse(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    avatar_url: str | None = None
    # Derived, never stored: recomputed on every read so it cannot drift.
    completion_percent: int = 0
    completed_fields: int = 0
    total_fields: int = 0


class PreferencesUpdate(BaseModel):
    response_style: Literal[RESPONSE_STYLES] | None = None  # type: ignore[valid-type]
    ai_suggestions: bool | None = None
    recall_suggestions: bool | None = None
    knowledge_visibility: Literal[KNOWLEDGE_VISIBILITY] | None = None  # type: ignore[valid-type]

    ai_processing_mode: Literal[AI_PROCESSING_MODES] | None = None  # type: ignore[valid-type]
    local_provider: str | None = Field(default=None, max_length=60)
    local_model: str | None = Field(default=None, max_length=120)
    cloud_provider: str | None = Field(default=None, max_length=60)
    cloud_model: str | None = Field(default=None, max_length=120)
    # Consent is granted or withdrawn explicitly; the timestamp is server-set.
    cloud_ai_consent: bool | None = None


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    response_style: str
    ai_suggestions: bool
    recall_suggestions: bool
    knowledge_visibility: str
    ai_processing_mode: str
    local_provider: str | None
    local_model: str | None
    cloud_provider: str | None
    cloud_model: str | None
    cloud_ai_consent: bool
    cloud_ai_consent_at: datetime | None


class AccountResponse(BaseModel):
    """Account facts only. Never includes the password hash or any token."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    email: EmailStr
    created_at: datetime
    last_login_at: datetime | None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v
