"""Search request and response shapes."""
import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)


class SearchMatch(BaseModel):
    fragment_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_filename: str
    artifact_title: str | None
    content: str
    # Page, slide, section, paragraph — whichever extraction established.
    # Missing keys mean the modality has no such notion, not a default.
    source_location: dict
    kind: str
    score: float


class SearchResponse(BaseModel):
    matches: list[SearchMatch]
    total: int
    # Named so a caller can tell which space produced these scores, and so a
    # change of provider is visible rather than silent.
    provider: str
    model: str
    dimensions: int
