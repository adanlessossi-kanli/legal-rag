import re
from datetime import datetime
from enum import Enum
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
    doc_id: str = ""
    chunk_id: str
    text: str
    page: int | None = None
    page_end: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    relevance: float | None = None


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
    version: int = 1


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


# --- Organizations ---

class CreateOrgRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("Name must be 1-100 characters")
        return v


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "editor", "viewer"] = "editor"


class OrgMember(BaseModel):
    user_id: str
    email: str
    name: str
    role: Literal["admin", "editor", "viewer"]


class OrgSummary(BaseModel):
    id: str
    name: str
    member_count: int


class OrgDetail(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: datetime
    members: list[OrgMember]


# --- Blueprints ---

class BlueprintCreate(BaseModel):
    name: str
    description: str
    content: dict

    @field_validator("name")
    @classmethod
    def name_length(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 255:
            raise ValueError("Name must be 1-255 characters")
        return v

    @field_validator("description")
    @classmethod
    def description_length(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 2000:
            raise ValueError("Description must be 1-2000 characters")
        return v


class BlueprintUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: dict | None = None

    @field_validator("name")
    @classmethod
    def name_length(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v or len(v) > 255:
                raise ValueError("Name must be 1-255 characters")
        return v

    @field_validator("description")
    @classmethod
    def description_length(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v or len(v) > 2000:
                raise ValueError("Description must be 1-2000 characters")
        return v


class BlueprintResponse(BaseModel):
    blueprint_id: str
    name: str
    description: str
    content: dict | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class PaginatedBlueprints(BaseModel):
    items: list[BlueprintResponse]
    total: int
    page: int
    page_size: int


# --- Audit Log ---

class AuditLogEntry(BaseModel):
    id: str
    action: str
    user_id: str
    org_id: str = ""
    resource_type: str
    resource_id: str
    detail: str = ""
    ip_address: str = ""
    created_at: datetime


class PaginatedAuditLog(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int


# --- Feedback ---

class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    rating: int
    comment: str = ""

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("Rating must be between 1 and 5")
        return v


class FeedbackResponse(BaseModel):
    id: str
    detail: str = "Feedback recorded"


# --- Document Versioning ---

class DocumentVersion(BaseModel):
    version: int
    name: str
    chunk_count: int
    uploaded_at: datetime
    content_hash: str


# --- Document Search ---

class DocumentSearchParams(BaseModel):
    query: str | None = None
    status: Literal["processing", "ready", "error"] | None = None
    file_type: str | None = None
    sort_by: Literal["name", "uploaded_at", "chunk_count"] = "uploaded_at"
    sort_order: Literal["asc", "desc"] = "desc"


# --- Export ---

class ExportFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


# --- User Roles ---

class UpdateMemberRoleRequest(BaseModel):
    role: Literal["admin", "editor", "viewer"]
