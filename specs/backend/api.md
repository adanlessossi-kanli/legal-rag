# Backend — API Endpoints

## Base URL
`http://localhost:8000`

---

## Authentication

All endpoints marked **Auth: Yes** require a `Authorization: Bearer <access_token>` header. Tokens are obtained via `/api/auth/login` or `/api/auth/register`.

---

## REQ-BA-001: POST `/api/chat`

Ask a question against ingested documents.

### Request
```json
{
  "question": "What is the liability clause?",
  "conversation_id": "optional_id",
  "document_ids": ["doc_abc123"]
}
```

### Response `200`
```json
{
  "answer": "According to Section 5.2, the liability is limited to...",
  "sources": [
    {
      "document": "contract_2024.pdf",
      "doc_id": "doc_abc123",
      "chunk_id": "abc123",
      "text": "The total liability shall not exceed...",
      "page": 3,
      "page_end": 3,
      "start_char": 150,
      "end_char": 320,
      "relevance": 0.92
    }
  ],
  "conversation_id": "abc123def456",
  "no_context": false
}
```

### Streaming (`?stream=true`)
Returns SSE events: `agent_status`, `sources`, `conversation_id`, `token`, `done`.

### Auth: Yes
### Errors
- `400`: Missing or empty `question`, exceeds max length.
- `403`: Access denied to scoped `document_ids`.
- `404`: Conversation not found.
- `429`: Rate limit exceeded.
- `500`: LLM or database failure.

---

## REQ-BA-002: POST `/api/upload`

Upload a document for ingestion. Ingestion runs in the background.

### Request
- Content-Type: `multipart/form-data`
- Field: `file` (single file, `.pdf`, `.txt`, `.docx`, or `.pptx`, max 50MB)

### Response `200`
```json
{
  "id": "doc_abc123",
  "name": "contract_2024.pdf",
  "chunk_count": 0,
  "status": "processing"
}
```

### Auth: Yes
### Errors
- `400`: Unsupported file type, empty file, or no file provided.
- `409`: Duplicate document (same content hash for this user).
- `413`: File exceeds 50MB limit.
- `429`: Rate limit exceeded.

---

## REQ-BA-003: GET `/api/documents`

List user/org documents (paginated, searchable, filterable).

### Query Parameters
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | `1` | Page number |
| `page_size` | int | `20` | Items per page (max 100) |
| `search` | string | — | Filename search (regex) |
| `status` | string | — | Filter: `processing`, `ready`, `error` |
| `file_type` | string | — | Filter: `pdf`, `txt`, `docx`, `pptx` |
| `sort_by` | string | `uploaded_at` | Sort field: `name`, `uploaded_at`, `chunk_count` |
| `sort_order` | string | `desc` | Sort direction: `asc`, `desc` |

### Response `200`
```json
{
  "items": [
    {
      "id": "doc_abc123",
      "name": "contract_2024.pdf",
      "uploaded_at": "2025-01-15T10:30:00Z",
      "chunk_count": 42,
      "status": "ready",
      "version": 1
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### Auth: Yes

---

## REQ-BA-004: DELETE `/api/documents/{doc_id}`

Delete a document, its chunks, and cached responses.

### Response `200`
```json
{ "detail": "Document deleted" }
```

### Auth: Yes
### Errors
- `404`: Document not found or not owned by user.

---

## REQ-BA-005: GET `/api/documents/{doc_id}/status`

Get document processing status.

### Auth: Yes
### Errors
- `404`: Document not found or not owned by user.

---

## REQ-BA-006: GET `/api/documents/{doc_id}/file`

Serve the original uploaded file.

- Returns the file with correct `Content-Type` (PDF, TXT, DOCX, PPTX).
- Sets `Content-Disposition: inline`.
- Supports HTTP `Range` requests (206 Partial Content).
- Supports `ETag` / `If-None-Match` (304 Not Modified).
- Auth via signed URL query params (`?sig=<token>&exp=<timestamp>`) or Bearer token.
- Returns `404` with `{"detail": "File no longer available on disk"}` if the document record exists but the file is missing from disk.

### Auth: Signed URL or Bearer
### Errors
- `403`: User doesn't own the document.
- `404`: Document not found or file missing from disk.

---

## REQ-BA-007: GET `/api/documents/{doc_id}/file-token`

Generate a short-lived signed URL for file access.

- Validates document existence and user ownership before generating the token.
- Returns a signed URL with 5-minute TTL (configurable via `FILE_TOKEN_EXPIRY_SECONDS`).

### Response `200`
```json
{ "url": "/api/documents/doc_abc123/file?sig=...&exp=..." }
```

### Auth: Yes
### Errors
- `403`: User doesn't own the document.
- `404`: Document not found.

---

## REQ-BA-008: Auth Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/auth/register` | No | Create account, returns tokens |
| `POST` | `/api/auth/login` | No | Sign in, returns tokens |
| `POST` | `/api/auth/refresh` | No | Refresh access token |
| `POST` | `/api/auth/logout` | Yes | Revoke all sessions |
| `GET` | `/api/auth/me` | Yes | Get current user info |

---

## REQ-BA-009: Conversation Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET` | `/api/conversations` | Yes | List conversations (paginated) |
| `GET` | `/api/conversations/{id}` | Yes | Get conversation with messages |
| `DELETE` | `/api/conversations/{id}` | Yes | Delete a conversation |

---

## REQ-BA-010: Organization Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/organizations` | Yes | Create an organization |
| `GET` | `/api/organizations` | Yes | List user's organizations |
| `GET` | `/api/organizations/{id}` | Yes | Get org details + members |
| `POST` | `/api/organizations/{id}/members` | Yes | Invite a member (admin only) |
| `DELETE` | `/api/organizations/{id}/members/{uid}` | Yes | Remove a member (admin only) |

---

## REQ-BA-011: Blueprint Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/blueprints` | Yes | Create a blueprint |
| `GET` | `/api/blueprints` | Yes | List blueprints (paginated) |
| `GET` | `/api/blueprints/{id}` | Yes | Get blueprint details |
| `PUT` | `/api/blueprints/{id}` | Yes | Update a blueprint |
| `DELETE` | `/api/blueprints/{id}` | Yes | Delete a blueprint |

---

## REQ-BA-012: Utility Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET` | `/api/health` | No | Health check (`?deep=true` for deps) |
| `GET` | `/api/metrics` | No | Prometheus metrics scrape endpoint |
| `GET` | `/api/usage` | Yes | Per-user OpenAI cost & token usage |
| `WS` | `/api/ws/ingestion` | Yes* | WebSocket for ingestion notifications |

---

## CORS
- Allow origin: configurable via `CORS_ORIGINS` (default: `http://localhost:3000`).
