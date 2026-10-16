"""Galaxy and Timeline shapes."""
from datetime import datetime

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    # "cluster" (a confirmed topic) or "fragment" (a knowledge fragment).
    type: str
    category: str
    document_count: int = 0
    fragment_count: int = 0
    relationship_count: int = 0
    provenance: str = "registered"
    # Present on fragments only: where this knowledge actually came from.
    source_artifact_id: str | None = None
    source_fragment_id: str | None = None
    source_location: dict | None = None
    source_filename: str | None = None
    source_title: str | None = None
    excerpt: str | None = None
    kind: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    # "co_occurrence" or "contains". Never a verified semantic relationship.
    kind: str
    weight: int
    # Words, not a percentage: a number would read as a confidence the data
    # does not support.
    relevance: str


class GalaxyResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    clusters: list[str] = Field(default_factory=list)
    truncated: bool = False


class RelatedNode(BaseModel):
    id: str
    label: str
    relevance: str
    explanation: str
    source_location: dict | None = None


class SourceDocument(BaseModel):
    artifact_id: str
    filename: str
    title: str | None = None
    source_location: dict | None = None
    excerpt: str | None = None


class RelatedPerson(BaseModel):
    name: str
    documents: list[str] = Field(default_factory=list)


class NodeDetails(BaseModel):
    id: str
    label: str
    type: str
    category: str
    description: str | None = None
    provenance: str = "registered"
    fragment_count: int = 0
    document_count: int = 0
    created_at: datetime | None = None
    source_artifact_id: str | None = None
    source_fragment_id: str | None = None
    source_location: dict | None = None
    related: list[RelatedNode] = Field(default_factory=list)
    documents: list[SourceDocument] = Field(default_factory=list)
    people: list[RelatedPerson] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    id: str
    artifact_id: str
    title: str
    filename: str
    date: str
    # "document_metadata" when the document states it, "registered_at"
    # otherwise. Never inferred.
    basis: str
    category: str
    topics: list[str] = Field(default_factory=list)
    description: str | None = None
    # The opening of the document itself, quoted. Null when it has no
    # fragments yet.
    preview: str | None = None
    modality: str


class TimelineResponse(BaseModel):
    events: list[TimelineEvent] = Field(default_factory=list)
