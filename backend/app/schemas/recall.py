"""Assisted Recollection shapes."""
from pydantic import BaseModel, Field


class RecallRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # The cluster the user has selected, used as context for the query.
    topic: str | None = Field(default=None, max_length=200)


class RecallSource(BaseModel):
    index: int
    fragment_id: str
    artifact_id: str
    filename: str
    title: str | None = None
    source_location: dict = Field(default_factory=dict)
    excerpt: str
    score: float


class RecallResponse(BaseModel):
    # Null when no model phrased an answer; the sources still stand on their own.
    answer: str | None = None
    sources: list[RecallSource] = Field(default_factory=list)
    # True when passages from the library back this response.
    grounded: bool = False
    model: str | None = None
    note: str | None = None
