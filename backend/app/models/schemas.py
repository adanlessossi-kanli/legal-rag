import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, field_validator

from app.core.config import settings


# --- Auth ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain a lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain a digit")
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("Name must be 1-100 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo | None = None


# --- Chat ---

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    document_ids: list[str] | None = None
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
    conversation_id: str | None = None
    no_context: bool = False


# --- Documents ---

class DocumentInfo(BaseModel):
    id: str
    name: str
    uploaded_at: datetime
    chunk_count: int
    status: Literal["processing", "ready", "error"]


class PaginatedDocuments(BaseModel):
    items: list[DocumentInfo]
    total: int
    page: int
    page_size: int


class UploadResponse(BaseModel):
    id: str
    name: str
    chunk_count: int
    status: Literal["processing", "ready", "error"]


class DeleteResponse(BaseModel):
    detail: str


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    checks: dict[str, Any] | None = None


# --- Conversations ---

class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime


class PaginatedConversations(BaseModel):
    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int


class MessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = []
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[MessageOut]
