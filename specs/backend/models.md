# Backend — Data Models

## Pydantic Schemas

### REQ-BM-001: Chat
```python
class ChatRequest(BaseModel):
    question: str                          # non-empty
    history: list[ChatMessage] = []

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class Source(BaseModel):
    document: str
    chunk_id: str
    text: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
```

### REQ-BM-002: Document
```python
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
```

### REQ-BM-003: Health
```python
class HealthResponse(BaseModel):
    status: str
```

## Internal Models (not exposed via API)

### REQ-BM-004: Document Processing
```python
class DocumentPage:
    text: str
    metadata: dict  # {"source": filename, "page": int}

class Chunk:
    chunk_id: str
    text: str
    metadata: dict  # {"doc_id": str, "source": str, "page": int}
```

## Document Metadata Store
For v1, document metadata (id, name, date, chunk_count, status) is stored in a JSON file (`uploads/metadata.json`) to avoid adding a database dependency.

```json
{
  "doc_abc123": {
    "name": "contract_2024.pdf",
    "uploaded_at": "2025-01-15T10:30:00Z",
    "chunk_count": 42,
    "status": "ready"
  }
}
```
