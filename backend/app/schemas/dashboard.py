"""Dashboard response shapes."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MetricCount(BaseModel):
    total: int
    new_this_week: int


class StorageMetric(BaseModel):
    bytes: int
    # Both null until a quota exists. A percentage needs a denominator, and
    # inventing one would be a fabricated statistic.
    quota_bytes: int | None = None
    percent: float | None = None


class RecentIngestion(BaseModel):
    id: uuid.UUID
    filename: str
    modality: str
    size_bytes: int
    status: str
    created_at: datetime


class ActivityDay(BaseModel):
    date: str
    count: int


class DistributionSlice(BaseModel):
    label: str
    count: int


class TopicDistribution(BaseModel):
    slices: list[DistributionSlice] = Field(default_factory=list)
    total: int = 0


class MapNode(BaseModel):
    label: str
    count: int


class MapEdge(BaseModel):
    source: str
    target: str
    weight: int


class KnowledgeMap(BaseModel):
    center: str | None = None
    nodes: list[MapNode] = Field(default_factory=list)
    edges: list[MapEdge] = Field(default_factory=list)
    # Names what the edges mean, so the graph is not read as semantic.
    basis: str = "topic_co_occurrence"


class RecollectionSource(BaseModel):
    id: uuid.UUID
    filename: str
    modality: str


class RecollectionItem(BaseModel):
    topic: str
    document_count: int
    artifacts: list[RecollectionSource] = Field(default_factory=list)


class DashboardOverview(BaseModel):
    documents: MetricCount
    fragments: MetricCount
    topics: MetricCount
    storage: StorageMetric
    recent: list[RecentIngestion] = Field(default_factory=list)
    activity: list[ActivityDay] = Field(default_factory=list)
    topic_distribution: TopicDistribution
    knowledge_map: KnowledgeMap
    recollection: list[RecollectionItem] = Field(default_factory=list)
