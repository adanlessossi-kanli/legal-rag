# Multi-Agent RAG — MCP Protocol

## REQ-MP-001: Transport

- Protocol: MCP (Anthropic Model Context Protocol) over HTTP/SSE.
- Architecture: In-process MCP servers. Each agent runs as an MCP server within the same FastAPI process. The Orchestrator and Researcher act as MCP clients.
- No separate processes. Agents are logical MCP servers instantiated at app startup, communicating via in-memory transport.
- SDK: `mcp` Python package (PyPI), version ≥ 1.0.

## REQ-MP-002: Agent ↔ MCP Mapping

Each agent is an MCP server exposing typed tools. Clients discover tools at connection time.

| Agent       | MCP Role       | Exposes Tools                                          | Calls Tools On            |
|------------|----------------|--------------------------------------------------------|---------------------------|
| Librarian   | Server         | `librarian.search`, `librarian.ingest`, `librarian.remove` | —                         |
| Researcher  | Server + Client | `researcher.research`                                  | Librarian, Summarizer     |
| Writer      | Server         | `writer.generate`                                      | —                         |
| Summarizer  | Server         | `summarizer.summarize`                                 | —                         |
| Orchestrator| Client only    | —                                                      | Researcher, Writer, Librarian, Summarizer |

## REQ-MP-003: Tool Schemas

### `librarian.search`

Search the vector store for relevant chunks.

```json
{
  "name": "librarian.search",
  "description": "Search document chunks by semantic similarity",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "minLength": 1, "maxLength": 5000 },
      "user_id": { "type": "string", "minLength": 1 },
      "document_ids": {
        "type": "array",
        "items": { "type": "string" },
        "maxItems": 50
      },
      "top_k": { "type": "integer", "minimum": 1, "maximum": 20, "default": 5 }
    },
    "required": ["query", "user_id"],
    "additionalProperties": false
  }
}
```

Returns: `{ "chunks": [{ "chunk_id": str, "text": str, "metadata": dict, "score": float }] }`

### `librarian.ingest`

Ingest a document: load, chunk, embed, store.

```json
{
  "name": "librarian.ingest",
  "description": "Ingest a document into the vector store",
  "inputSchema": {
    "type": "object",
    "properties": {
      "file_path": { "type": "string", "minLength": 1 },
      "original_name": { "type": "string", "minLength": 1, "maxLength": 255 },
      "doc_id": { "type": "string", "minLength": 1 },
      "content_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
      "user_id": { "type": "string", "minLength": 1 }
    },
    "required": ["file_path", "original_name", "doc_id", "content_hash", "user_id"],
    "additionalProperties": false
  }
}
```

Returns: `{ "chunk_count": int }`

### `librarian.remove`

Delete a document and its chunks.

```json
{
  "name": "librarian.remove",
  "description": "Remove a document and all its chunks",
  "inputSchema": {
    "type": "object",
    "properties": {
      "doc_id": { "type": "string", "minLength": 1 }
    },
    "required": ["doc_id"],
    "additionalProperties": false
  }
}
```

Returns: `{ "deleted": true }`

### `researcher.research`

Research a question: rewrite query if needed, retrieve and rank chunks.

```json
{
  "name": "researcher.research",
  "description": "Research a question: rewrite → retrieve → rank",
  "inputSchema": {
    "type": "object",
    "properties": {
      "question": { "type": "string", "minLength": 1, "maxLength": 5000 },
      "history": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "role": { "type": "string", "enum": ["user", "assistant"] },
            "content": { "type": "string" }
          },
          "required": ["role", "content"]
        },
        "maxItems": 50
      },
      "user_id": { "type": "string", "minLength": 1 },
      "document_ids": {
        "type": "array",
        "items": { "type": "string" },
        "maxItems": 50
      }
    },
    "required": ["question", "user_id"],
    "additionalProperties": false
  }
}
```

Returns: `{ "chunks": [...], "rewritten_query": str | null }`

### `writer.generate`

Generate a cited answer from retrieved context.

```json
{
  "name": "writer.generate",
  "description": "Generate a cited answer from context chunks",
  "inputSchema": {
    "type": "object",
    "properties": {
      "question": { "type": "string", "minLength": 1, "maxLength": 5000 },
      "chunks": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "chunk_id": { "type": "string" },
            "text": { "type": "string" },
            "metadata": { "type": "object" }
          },
          "required": ["chunk_id", "text", "metadata"]
        },
        "minItems": 1,
        "maxItems": 20
      },
      "history": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "role": { "type": "string", "enum": ["user", "assistant"] },
            "content": { "type": "string" }
          },
          "required": ["role", "content"]
        },
        "maxItems": 50
      },
      "stream": { "type": "boolean", "default": false }
    },
    "required": ["question", "chunks"],
    "additionalProperties": false
  }
}
```

Returns (non-streaming): `{ "answer": str }`
Returns (streaming): SSE stream of `{ "token": str }` events, ending with `{ "done": true }`

### `summarizer.summarize`

Condense text based on an objective.

```json
{
  "name": "summarizer.summarize",
  "description": "Summarize text focused on a specific objective",
  "inputSchema": {
    "type": "object",
    "properties": {
      "text": { "type": "string", "minLength": 1, "maxLength": 50000 },
      "objective": { "type": "string", "minLength": 1, "maxLength": 500 },
      "max_length": { "type": "integer", "minimum": 50, "maximum": 5000, "default": 500 }
    },
    "required": ["text", "objective"],
    "additionalProperties": false
  }
}
```

Returns: `{ "summary": str }`

## REQ-MP-004: Input Validation

Every agent validates inputs at its MCP tool boundary before processing:

- Reject missing required fields with a descriptive `McpError`.
- Enforce `minLength`, `maxLength`, `minimum`, `maximum`, `maxItems` constraints.
- Sanitize `file_path` in `librarian.ingest` — resolve to absolute path, verify it is within the configured `UPLOAD_DIR`. Reject path traversal attempts.
- Validate `user_id` format — must be a valid ObjectId string (24 hex chars).
- Reject `additionalProperties` — unknown fields are not silently ignored.

## REQ-MP-005: Error Taxonomy

All agent errors are categorized for consistent handling:

| Error Type          | MCP Error Code | Retryable | Example                              |
|--------------------|----------------|-----------|--------------------------------------|
| `VALIDATION_ERROR`  | `InvalidParams` | No        | Missing required field, bad format   |
| `NOT_FOUND`         | `InvalidParams` | No        | Document not found for removal       |
| `LLM_ERROR`         | `InternalError` | Yes       | OpenAI API timeout, rate limit       |
| `STORAGE_ERROR`     | `InternalError` | Yes       | MongoDB connection failure           |
| `EMBEDDING_ERROR`   | `InternalError` | Yes       | Embedding API failure                |
| `INTERNAL_ERROR`    | `InternalError` | No        | Unexpected exception                 |

Error response format:

```json
{
  "error": {
    "type": "LLM_ERROR",
    "message": "OpenAI API timeout after 30s",
    "agent": "writer",
    "tool": "writer.generate",
    "retryable": true
  }
}
```

## REQ-MP-006: Timeout & Retry Policy

| Call                          | Timeout | Retries | Backoff              | Notes                          |
|------------------------------|---------|---------|----------------------|--------------------------------|
| `librarian.search`           | 10s     | 2       | Exponential (1s base) | MongoDB vector search          |
| `librarian.ingest`           | 120s    | 0       | —                    | Long-running, retried at API level |
| `librarian.remove`           | 10s     | 1       | Fixed 1s             | Idempotent                     |
| `researcher.research`        | 30s     | 0       | —                    | Composite (includes sub-calls) |
| `writer.generate`            | 60s     | 2       | Exponential (1s base) | LLM generation                 |
| `writer.generate` (stream)   | 60s     | 0       | —                    | Cannot retry mid-stream        |
| `summarizer.summarize`       | 30s     | 2       | Exponential (1s base) | LLM summarization              |

- Timeouts are per-call, not cumulative.
- The Orchestrator enforces an overall request timeout of 90s for query flows.
- Retries within agents (e.g., OpenAI retries in Writer) use the existing `tenacity` retry decorator. MCP-level retries are additional.

## REQ-MP-007: Graceful Degradation

| Failure                        | Behavior                                                    |
|-------------------------------|-------------------------------------------------------------|
| Summarizer unavailable         | Researcher skips summarization, returns full chunks          |
| Summarizer call fails          | Researcher logs warning, continues with unsummarized chunks  |
| Writer fails (non-streaming)   | Orchestrator returns error to API layer                     |
| Writer fails (streaming)       | Orchestrator emits error SSE event, closes stream           |
| Librarian search fails         | Researcher returns empty chunks, Orchestrator returns NO_CONTEXT_ANSWER |
| Librarian ingest fails         | Error propagated, document status set to "error"            |
| Query rewriting fails          | Researcher uses original question (logs warning)            |

## REQ-MP-008: Lifecycle Management

### Startup (in FastAPI lifespan)

1. Instantiate Librarian MCP server → register tools.
2. Instantiate Summarizer MCP server → register tools.
3. Instantiate Writer MCP server → register tools.
4. Instantiate Researcher MCP server → register tools → connect as client to Librarian + Summarizer.
5. Instantiate Orchestrator MCP client → connect to Researcher, Writer, Librarian, Summarizer.
6. Verify all connections with a health ping to each server.
7. Store Orchestrator reference in `app.state.orchestrator`.
8. Log startup complete with agent count and connection status.

### Shutdown

1. Close Orchestrator client connections.
2. Close Researcher client connections (to Librarian, Summarizer).
3. Shut down all MCP servers (Writer, Summarizer, Librarian, Researcher).
4. Log shutdown complete.

Order matters: clients close before servers to avoid dangling connections.

### Health Check

`GET /api/health?deep=true` extended to include agent status:

```json
{
  "status": "ok",
  "checks": {
    "mongodb": "ok",
    "openai": "ok",
    "agents": {
      "librarian": "ok",
      "researcher": "ok",
      "writer": "ok",
      "summarizer": "ok"
    }
  }
}
```

## REQ-MP-009: Security at Agent Boundaries

- Agents do not authenticate each other (in-process trust boundary). If agents are extracted to services in the future, add mTLS or token-based auth.
- `user_id` is passed explicitly to every tool that accesses user-scoped data. Agents never infer user identity.
- `file_path` in `librarian.ingest` is validated against `UPLOAD_DIR` to prevent path traversal.
- Tool inputs are validated against the JSON schema before execution. Malformed inputs are rejected, not coerced.
- Agents never log sensitive content (file contents, full question text at DEBUG level only).
