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
    # Fragments only: cosine similarity to their own topic's passages, and
    # whether they resemble nothing else (drawn close around their topic) or
    # which other topic they resemble most.
    similarity: float | None = None
    orbit: bool | None = None
    affinity: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    # "co_occurrence", "named_in", "contains", or "similar_meaning" /
    # "similar_words" — a measured resemblance between texts, never a
    # verified semantic relationship.
    kind: str
    weight: int
    # Words, not a percentage: a number would read as a confidence the data
    # does not support.
    relevance: str
    # Why the edge is drawn, in a sentence, and the documents it rests on.
    # An edge that cannot say either of these should not be displayed.
    explanation: str = ""
    evidence: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    # A count of supporting documents, stated as such. Not a score.
    confidence: str = ""
    status: str = "registered"
    # False for an edge resting on a single document: real, but shown only
    # when one of its endpoints is selected.
    strong: bool = True
    # A measurement, unlike the counts above: cosine similarity of the two
    # ends' embeddings (0–1), and how far above the library's typical
    # similarity it sits (0 at typical, 1 at its strongest pair).
    similarity: float | None = None
    strength: float | None = None
    # A similarity link between topics no document carries together.
    discovered: bool = False


class SimilaritySpace(BaseModel):
    """How similarity was measured for this response, and against what yardstick."""

    provider: str
    model: str
    dimensions: int
    learned: bool
    # "meaning" for a learned model, "shared words" for the hashing embedder.
    measures: str
    typical: float | None = None
    topic_threshold: float | None = None
    ceiling: float | None = None
    vectors: int = 0
    topics_measured: int = 0


class GalaxyResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    clusters: list[str] = Field(default_factory=list)
    truncated: bool = False
    similarity: SimilaritySpace | None = None


class LensRequest(BaseModel):
    text: str = Field(min_length=2, max_length=1000)


class LensTopic(BaseModel):
    id: str
    label: str
    similarity: float
    strength: float
    above_typical: bool


class LensPassage(BaseModel):
    id: str
    artifact_id: str
    title: str
    excerpt: str
    similarity: float


class LensResponse(BaseModel):
    text: str
    topics: list[LensTopic] = Field(default_factory=list)
    passages: list[LensPassage] = Field(default_factory=list)
    placement: str
    similarity: SimilaritySpace


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
