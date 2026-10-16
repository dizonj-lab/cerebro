"""Artifact API contracts.

No schema accepts an owner id: ownership always comes from the session.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.artifacts.metadata import METADATA_FIELDS

MAX_LIST_ITEMS = 30
MAX_ITEM_LENGTH = 80


def _clean_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        item = " ".join(raw.split())[:MAX_ITEM_LENGTH]
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    return out[:MAX_LIST_ITEMS]


class ArtifactMetadata(BaseModel):
    """The editable metadata surface, matching the PoC field set."""

    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    language: str | None = Field(default=None, max_length=60)
    author: str | None = Field(default=None, max_length=160)
    created_date: str | None = Field(default=None, max_length=40)
    topics: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("topics", "people", "organizations", "projects", "tags", mode="after")
    @classmethod
    def _lists(cls, v: list[str]) -> list[str]:
        return _clean_list(v)

    @field_validator("title", "description", "language", "author", "created_date", mode="after")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None


class ArtifactReviewRequest(BaseModel):
    """Human review. Approval is explicit and never defaulted."""

    metadata: ArtifactMetadata
    approve: bool = False


class ArtifactSummary(BaseModel):
    """Library row. Deliberately omits the heavy JSONB payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    modality: str
    size_bytes: int
    status: str
    sha256: str
    title: str | None = None
    created_at: datetime
    registered_at: datetime | None = None


class ArtifactDetail(ArtifactSummary):
    content_type: str | None = None
    metadata: ArtifactMetadata
    field_methods: dict = Field(default_factory=dict)
    inspection: dict = Field(default_factory=dict)
    extraction: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    integrity: dict = Field(default_factory=dict)
    # Short preview of the stored text, for the review screen.
    preview: str | None = None


class ArtifactListResponse(BaseModel):
    items: list[ArtifactSummary]
    total: int


__all__ = [
    "ArtifactMetadata", "ArtifactReviewRequest", "ArtifactSummary",
    "ArtifactDetail", "ArtifactListResponse", "METADATA_FIELDS",
]


class EnrichmentSuggestion(BaseModel):
    """Proposed metadata. Nothing here is saved until the user approves it."""

    suggestions: dict = Field(default_factory=dict)
    field_methods: dict = Field(default_factory=dict)
    # value -> the sentence in the document it was found in. Supporting
    # evidence for a human review, not a claim that the value is correct.
    evidence: dict = Field(default_factory=dict)
    # False means no model contributed — the configured one was unreachable,
    # or AI suggestions are switched off in preferences. `notes` says which.
    ai_used: bool = False
    engine: str = "none"
    model: str | None = None
    # False would mean content left the CEREBRO environment. No engine does.
    local: bool = True
    notes: list[str] = Field(default_factory=list)


MAX_BULK_FILES = 25


class BulkUploadItem(BaseModel):
    """One file's outcome. A batch reports per file; it never fails as a whole."""

    filename: str
    accepted: bool
    artifact: ArtifactDetail | None = None
    # Why this file was refused, in the same words the single upload uses.
    error: str | None = None


class BulkUploadResponse(BaseModel):
    items: list[BulkUploadItem] = Field(default_factory=list)
    accepted: int = 0
    rejected: int = 0


class BulkReviewItem(BaseModel):
    id: uuid.UUID
    metadata: ArtifactMetadata


class BulkReviewRequest(BaseModel):
    items: list[BulkReviewItem] = Field(min_length=1, max_length=MAX_BULK_FILES)
    approve: bool = True


class BulkReviewResultItem(BaseModel):
    id: uuid.UUID
    registered: bool
    artifact: ArtifactDetail | None = None
    error: str | None = None


class BulkReviewResponse(BaseModel):
    items: list[BulkReviewResultItem] = Field(default_factory=list)
    registered: int = 0
    failed: int = 0
