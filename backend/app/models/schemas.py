from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.core.config import settings


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        if len(v) > settings.max_question_length:
            raise ValueError(f"question must not exceed {settings.max_question_length} characters")
        return v


class Source(BaseModel):
    document: str
    chunk_id: str
    text: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class DocumentInfo(BaseModel):
    id: str
    name: str
    uploaded_at: datetime
    chunk_count: int
    status: Literal["processing", "ready", "error"]


class UploadResponse(BaseModel):
    id: str
    name: str
    chunk_count: int
    status: Literal["processing", "ready", "error"]


class DeleteResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] | None = None
