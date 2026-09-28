from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.tagging import normalize_tag


class DocumentOut(BaseModel):
    id: int
    original_filename: str
    status: str
    chunk_count: int
    tags: list[str] = Field(default_factory=list)
    shared: bool = False
    can_delete: bool = True
    owner_username: str | None = None
    created_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    tag: str | None = Field(default=None, max_length=32)

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str | None) -> str | None:
        return normalize_tag(value)


class SourceOut(BaseModel):
    document_id: int
    filename: str
    chunk: int
    excerpt: str
    score: float | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    history_id: int | None = None
    feedback_rating: Literal["helpful", "not_helpful"] | None = None


class QueryHistoryOut(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[SourceOut]
    feedback_rating: Literal["helpful", "not_helpful"] | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AdminQueryHistoryOut(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[SourceOut]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FeedbackRequest(BaseModel):
    rating: Literal["helpful", "not_helpful"]


class FeedbackOut(BaseModel):
    rating: Literal["helpful", "not_helpful"]
