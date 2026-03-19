# Backend — API Endpoints

## Base URL
`http://localhost:8000`

---

## REQ-BA-001: POST `/api/chat`

Ask a question against ingested documents.

### Request
```json
{
  "question": "What is the liability clause?",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

### Response `200`
```json
{
  "answer": "According to Section 5.2, the liability is limited to...",
  "sources": [
    {
      "document": "contract_2024.pdf",
      "chunk_id": "abc123",
      "text": "The total liability shall not exceed..."
    }
  ]
}
```

### Errors
- `400`: Missing or empty `question`.
- `500`: LLM or vector DB failure.

---

## REQ-BA-002: POST `/api/upload`

Upload a document for ingestion.

### Request
- Content-Type: `multipart/form-data`
- Field: `file` (single file, `.pdf` or `.txt`, max 50MB)

### Response `200`
```json
{
  "id": "doc_abc123",
  "name": "contract_2024.pdf",
  "chunk_count": 42,
  "status": "ready"
}
```

### Errors
- `400`: Unsupported file type or empty file.
- `413`: File exceeds size limit.
- `500`: Processing failure.

---

## REQ-BA-003: GET `/api/documents`

List all ingested documents.

### Response `200`
```json
[
  {
    "id": "doc_abc123",
    "name": "contract_2024.pdf",
    "uploaded_at": "2025-01-15T10:30:00Z",
    "chunk_count": 42,
    "status": "ready"
  }
]
```

---

## REQ-BA-004: DELETE `/api/documents/{id}`

Delete a document and its chunks from the vector store.

### Response `200`
```json
{ "detail": "Document deleted" }
```

### Errors
- `404`: Document not found.

---

## REQ-BA-005: GET `/api/health`

Health check.

### Response `200`
```json
{ "status": "ok" }
```

## CORS
- Allow origin: `http://localhost:3000` (dev), configurable via env.
