# Backend — Data Models

## Pydantic Schemas

### REQ-BM-001: Chat
```python
class ChatRequest(BaseModel):
    question: str                                    # non-empty, max 2000 chars
    conversation_id: str | None = None               # existing conversation or None for new
    document_ids: list[str] | None = None            # optional scope to specific documents
    history: list[ChatMessage] = []

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class Source(BaseModel):
    document: str                                    # original filename
    doc_id: str                                      # parent document ID
    chunk_id: str                                    # unique chunk identifier
    text: str                                        # excerpt (max SOURCE_TEXT_MAX_LENGTH)
    page: int | None = None                          # 1-based page/slide number
    page_end: int | None = None                      # end page for cross-page chunks
    start_char: int | None = None                    # char offset within start page
    end_char: int | None = None                      # char offset within end page
    relevance: float | None = None                   # cosine similarity score (0–1)

class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    conversation_id: str | None = None
    no_context: bool = False
```

### REQ-BM-002: Document
```python
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
```

### REQ-BM-003: Auth
```python
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str                                    # min 8 chars, upper + lower + digit
    name: str                                        # 1-100 chars

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
```

### REQ-BM-004: Health
```python
class HealthResponse(BaseModel):
    status: str
    checks: dict[str, Any] | None = None             # deep health check results
```

### REQ-BM-005: Conversations
```python
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
```

### REQ-BM-006: Organizations
```python
class CreateOrgRequest(BaseModel):
    name: str                                        # 1-100 chars

class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "editor", "viewer"] = "editor"

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
```

### REQ-BM-007: Blueprints
```python
class BlueprintCreate(BaseModel):
    name: str                                        # 1-255 chars
    description: str                                 # 1-2000 chars
    content: dict

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
```

## Internal Models (not exposed via API)

### REQ-BM-008: Document Processing
```python
@dataclass
class DocumentPage:
    text: str
    metadata: dict                                   # {"source": filename, "page": int}

@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict                                   # {"doc_id", "source", "page", "page_start",
                                                     #  "page_end", "start_char", "end_char"}
```

## Document Metadata Store
Document metadata is stored in MongoDB (`documents` collection), scoped by `user_id` and optionally `org_id`. Supports search, filtering, sorting, and pagination.

## Supported File Types
| Extension | MIME Type | Loader |
|-----------|-----------|--------|
| `.pdf` | `application/pdf` | PyMuPDF (fitz) |
| `.txt` | `text/plain` | UTF-8 read |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | python-docx |
| `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | python-pptx |
