"""Assisted Recollection shapes."""
from pydantic import BaseModel, Field


class RecallTurn(BaseModel):
    """One earlier exchange, for understanding a follow-up question."""

    question: str = Field(max_length=1000)
    answer: str = Field(max_length=4000)


class RecallRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # The cluster the user has selected, used as context for the query.
    topic: str | None = Field(default=None, max_length=200)
    # What was said before, so "what about the other one?" is answerable.
    # Context for reading the question, never a source of facts: retrieval
    # still runs fresh against the library every time.
    history: list[RecallTurn] = Field(default_factory=list, max_length=10)


class RecallSource(BaseModel):
    index: int
    fragment_id: str
    artifact_id: str
    filename: str
    title: str | None = None
    source_location: dict = Field(default_factory=dict)
    excerpt: str
    score: float
    # Confirmed topics of the source document, so a client can map an answer
    # onto the knowledge graph without a second request.
    topics: list[str] = Field(default_factory=list)


class RecallTelemetry(BaseModel):
    """What actually ran, so an answer can be audited rather than trusted."""

    model: str
    duration_ms: int | None = None
    # Counted by the daemon itself, not estimated here.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    passages: int
    top_score: float


class RecallResponse(BaseModel):
    # Null when no model phrased an answer; the sources still stand on their own.
    answer: str | None = None
    sources: list[RecallSource] = Field(default_factory=list)
    # True when passages from the library back this response.
    grounded: bool = False
    model: str | None = None
    note: str | None = None
    # Which passages the answer actually cited, after invalid citations were
    # removed. A model citing [7] of six passages cites nothing.
    cited: list[int] = Field(default_factory=list)
    # True when the model said the passages do not answer the question.
    abstained: bool = False
    telemetry: RecallTelemetry | None = None
