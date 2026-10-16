"""Search request and response shapes.

The response keeps the flat `matches` list the first semantic endpoint
returned, and adds the grouped view the search page needs. One request, one
set of results, three groupings of it.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    """Filters the stored metadata can actually answer.

    There is no confidence or collection filter here on purpose: neither
    exists in the data, and a control that silently matches nothing is worse
    than its absence.
    """

    modalities: list[str] = Field(default_factory=list, max_length=12)
    statuses: list[str] = Field(default_factory=list, max_length=6)
    topics: list[str] = Field(default_factory=list, max_length=24)
    tags: list[str] = Field(default_factory=list, max_length=24)
    people: list[str] = Field(default_factory=list, max_length=24)
    organizations: list[str] = Field(default_factory=list, max_length=24)
    projects: list[str] = Field(default_factory=list, max_length=24)
    uploaded_from: date | None = None
    uploaded_to: date | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)
    # Hybrid is the default because neither retrieval alone is reliable: a
    # keyword query misses paraphrase, a semantic one misses an exact
    # identifier.
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    scope: Literal["all", "library", "knowledge"] = "all"
    filters: SearchFilters = Field(default_factory=SearchFilters)


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


class KnowledgeHit(BaseModel):
    fragment_id: uuid.UUID
    artifact_id: uuid.UUID
    filename: str
    title: str | None
    content: str
    # The passage around the match, with the matched terms marked. Only the
    # keyword retrieval can produce one; a semantic hit gets a plain opening
    # excerpt instead.
    excerpt: str
    source_location: dict
    topics: list[str] = Field(default_factory=list)
    score: float
    # Which retrievals found it, so a user can see why it is here.
    matched_by: list[str] = Field(default_factory=list)
    # Words, never a percentage: a fused rank is not a confidence.
    relevance: str


class DocumentHit(BaseModel):
    artifact_id: uuid.UUID
    filename: str
    modality: str
    # Carried so an artifact still awaiting review is never read as
    # established knowledge.
    status: str
    created_at: datetime
    title: str | None
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    score: float
    relevance: str


class ConceptHit(BaseModel):
    label: str
    count: int


class SearchResponse(BaseModel):
    query: str
    mode: str
    scope: str
    documents: list[DocumentHit]
    knowledge: list[KnowledgeHit]
    concepts: list[ConceptHit]
    total_documents: int
    total_knowledge: int
    took_ms: float
    # Set when half the hybrid was unavailable, so a shortened result set is
    # never passed off as the whole answer.
    note: str | None = None
    matches: list[SearchMatch]
    total: int
    # Named so a caller can tell which space produced these scores, and so a
    # change of provider is visible rather than silent.
    provider: str
    model: str
    dimensions: int


class SuggestionsResponse(BaseModel):
    prefix: str
    suggestions: list[str]
