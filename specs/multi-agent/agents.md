# Multi-Agent RAG — Agent Specifications

## REQ-MA-001: Orchestrator

### Responsibility

Central coordinator. Receives requests from the API layer, delegates to specialized agents via MCP tool calls, assembles the final response, and emits status events for the frontend.

### Invariants

- The Orchestrator never calls OpenAI directly. All LLM work is delegated to agents.
- The Orchestrator is stateless. Conversation history is passed in, not stored.
- The Orchestrator enforces a 90s overall timeout per query request.
- On any agent failure, the Orchestrator logs the error with correlation ID and returns a structured error.

### Interface

```python
class Orchestrator:
    async def query(question, history, user_id, document_ids, on_status) -> (answer, sources, no_context)
    async def query_stream(question, history, user_id, document_ids, on_status) -> (token_gen, sources, no_context)
    async def ingest(file_path, original_name, doc_id, content_hash, user_id) -> int
    async def remove_document(doc_id) -> None
    async def summarize(text, objective, max_length) -> str
```

### Query Behavior

1. Validate inputs: `question` non-empty, `user_id` non-empty.
2. Emit `on_status("researcher", "working")`.
3. Call `researcher.research(question, history, user_id, document_ids)`.
4. If Researcher returns empty chunks:
   - Emit `on_status("done")`.
   - Return `(NO_CONTEXT_ANSWER, [], no_context=True)`.
5. Build `sources` list from returned chunks (truncate text to `SOURCE_TEXT_MAX_LENGTH`).
6. Emit `on_status("writer", "working")`.
7. Call `writer.generate(question, chunks, history, stream)`.
8. Streaming: forward token events, interleaving `on_status` events.
9. Non-streaming: receive complete answer string.
10. Emit `on_status("done")`.
11. Return `(answer, sources, no_context=False)`.

### Ingest Behavior

1. Call `librarian.ingest(file_path, original_name, doc_id, content_hash, user_id)`.
2. Return chunk count from Librarian response.
3. On failure: let the error propagate (API layer handles status update).

### Remove Behavior

1. Call `librarian.remove(doc_id)`.
2. On failure: log and propagate.

### Status Events

```python
@dataclass
class AgentStatus:
    agent: str    # "researcher" | "writer" | "summarizer"
    status: str   # "working" | "done"
```

The `on_status` callback is provided by the API layer and wired into the SSE stream.

### Observability

- Log each agent call: `agent={name} tool={tool} duration={ms} status={ok|error}`.
- Propagate the request's correlation ID (from `X-Request-ID` header) to all log entries.
- Log total orchestration time for each query.

---

## REQ-MA-002: Librarian Agent

### Responsibility

Owns all document storage operations: ingestion (load → chunk → embed → store), vector search retrieval, and document deletion. The single source of truth for document data.

### Invariants

- Librarian never calls other agents. It is a leaf node in the agent graph.
- Librarian makes OpenAI calls only for embeddings, never for chat completions.
- All data access is scoped by `user_id`. Librarian never returns chunks belonging to a different user.
- Ingestion is idempotent by `content_hash` — re-ingesting the same file for the same user is a no-op that returns the existing chunk count.

### MCP Tools

| Tool                | Timeout | Retryable |
|--------------------|---------|-----------|
| `librarian.search`  | 10s     | Yes (2)   |
| `librarian.ingest`  | 120s    | No        |
| `librarian.remove`  | 10s     | Yes (1)   |

### `librarian.search` — Logic

1. Validate inputs: `query` non-empty, `user_id` non-empty, `top_k` in [1, 20].
2. Embed the query via `vectorstore._embed([query])`.
3. Run `$vectorSearch` aggregation on MongoDB `chunks` collection:
   - Filter by `user_id`.
   - Optionally filter by `document_ids` (if provided).
   - Limit to `top_k` results.
4. Filter results by `settings.retrieval_min_score`.
5. Return chunks with `chunk_id`, `text`, `metadata`, `score`.
6. Log: retrieval duration, chunk count returned, min/max scores.

### `librarian.ingest` — Logic

1. Validate inputs: `file_path` exists and is within `UPLOAD_DIR`, `doc_id` non-empty, `user_id` non-empty, `content_hash` is 64 hex chars.
2. Call `save_document(doc_id, original_name, 0, "processing", content_hash, user_id)`.
3. `load_document(file_path)` → pages.
4. `chunk_pages(pages, doc_id)` → chunks.
5. Set `user_id` in each chunk's metadata.
6. `store_chunks(chunks)` → embed + insert into MongoDB.
7. `save_document(doc_id, original_name, len(chunks), "ready", content_hash, user_id)`.
8. Return `{ "chunk_count": len(chunks) }`.
9. On error: `update_status(doc_id, "error")`, log exception, re-raise as `STORAGE_ERROR`.

### `librarian.remove` — Logic

1. Validate: `doc_id` non-empty.
2. `delete_by_doc_id(doc_id)` — remove chunks from MongoDB.
3. Delete the uploaded file from disk (if exists).
4. Return `{ "deleted": true }`.
5. Idempotent: if doc_id doesn't exist, still return success (no-op).

### Implementation

Wraps existing modules without modifying them:
- `rag/loader.py` → `load_document()`
- `rag/chunker.py` → `chunk_pages()`
- `rag/vectorstore.py` → `store_chunks()`, `retrieve()`, `delete_by_doc_id()`, `_embed()`
- `core/metadata.py` → `save_document()`, `update_status()`

---

## REQ-MA-003: Researcher Agent

### Responsibility

Takes a user question and conversation history, formulates an optimal search query, retrieves relevant chunks via the Librarian, and optionally summarizes oversized context via the Summarizer.

### Invariants

- Researcher never accesses the vector store directly. All retrieval goes through `librarian.search`.
- Researcher never generates final answers. It only produces context for the Writer.
- If query rewriting fails, Researcher falls back to the original question (logs warning, does not fail).
- If summarization fails, Researcher returns unsummarized chunks (logs warning, does not fail).

### MCP Tools Exposed

| Tool                   | Timeout | Retryable |
|-----------------------|---------|-----------|
| `researcher.research`  | 30s     | No        |

### MCP Tools Called (as client)

| Tool                     | On Agent   | Required? |
|-------------------------|------------|-----------|
| `librarian.search`       | Librarian  | Yes       |
| `summarizer.summarize`   | Summarizer | No (graceful degradation) |

### `researcher.research` — Logic

1. Validate inputs: `question` non-empty, `user_id` non-empty.
2. **Query rewriting** (conditional):
   - If `history` is non-empty AND `settings.enable_query_rewriting` is true:
     - Call OpenAI (gpt-4o-mini) with `REWRITE_PROMPT` to rewrite the follow-up into a standalone question.
     - On failure: log warning, use original `question`.
   - Set `search_query` = rewritten query or original question.
3. **Retrieval**:
   - Call `librarian.search(search_query, user_id, document_ids, top_k=settings.retrieval_top_k)`.
   - If empty: return `{ "chunks": [], "rewritten_query": search_query }`.
4. **Context size check** (conditional):
   - Calculate total text length of all returned chunks.
   - If total > `settings.researcher_summarize_threshold` (default 10,000 chars):
     - For each chunk exceeding 2,000 chars individually:
       - Call `summarizer.summarize(chunk.text, objective=question, max_length=500)`.
       - Replace chunk text with summary. Preserve original `chunk_id` and `metadata`.
     - On Summarizer failure: log warning, keep original chunk text.
5. Return `{ "chunks": [...], "rewritten_query": search_query if rewritten else null }`.
6. Log: original query, rewritten query (if any), chunk count, whether summarization was triggered.

### Configuration

| Setting                          | Env Var                          | Default | Description                              |
|---------------------------------|----------------------------------|---------|------------------------------------------|
| Summarization threshold          | `RESEARCHER_SUMMARIZE_THRESHOLD` | `10000` | Total chars to trigger chunk summarization |
| Per-chunk summarization threshold | (derived)                        | `2000`  | Individual chunk size to summarize        |

---

## REQ-MA-004: Writer Agent

### Responsibility

Generates a cited answer from retrieved context chunks and conversation history. Supports both streaming and non-streaming modes. The only agent that produces user-facing answer text.

### Invariants

- Writer never retrieves documents. It only works with chunks provided to it.
- Writer always uses the legal assistant system prompt. The prompt is not configurable per-request.
- Writer uses `settings.llm_model` (gpt-4o) for generation. Never a smaller model.
- Streaming and non-streaming use the same prompt construction logic.

### MCP Tools Exposed

| Tool               | Timeout | Retryable          |
|-------------------|---------|---------------------|
| `writer.generate`  | 60s     | Yes (2) non-stream, No for stream |

### `writer.generate` — Logic

1. Validate inputs: `question` non-empty, `chunks` non-empty (at least 1).
2. Build message array:
   - System message: `SYSTEM_PROMPT` (legal assistant, cite sources, stay grounded).
   - History messages: from `history` array (role + content).
   - User message: formatted context chunks (with `[Source: name, Page N]` labels) + question.
3. Call OpenAI chat completion:
   - Model: `settings.llm_model`.
   - Temperature: 0.1.
   - Stream: based on `stream` parameter.
4. Non-streaming:
   - Return `{ "answer": response_text }`.
   - Log: duration, prompt tokens, completion tokens.
5. Streaming:
   - Yield `{ "token": chunk_text }` for each delta.
   - Yield `{ "done": true }` at end.
   - Log: duration, token count (if available from stream).

### Prompts

```
SYSTEM_PROMPT = "You are a legal assistant. Answer the user's question based ONLY on the
provided context. If the context does not contain enough information,
say so. Always cite which document and section your answer comes from."
```

---

## REQ-MA-005: Summarizer Agent

### Responsibility

Reduces large text to a concise summary focused on a specific objective. Used by the Researcher when retrieved context is too large, or called directly via the Orchestrator for on-demand summarization.

### Invariants

- Summarizer is stateless and context-free. It does not know about conversations, users, or documents.
- Summarizer uses a smaller/cheaper model (`gpt-4o-mini`) since summaries don't need the full model's capability.
- Summarizer preserves key legal terms, dates, and named entities in its output.
- Summarizer failure is never fatal to the overall query flow (graceful degradation).

### MCP Tools Exposed

| Tool                     | Timeout | Retryable |
|-------------------------|---------|-----------|
| `summarizer.summarize`   | 30s     | Yes (2)   |

### `summarizer.summarize` — Logic

1. Validate inputs: `text` non-empty, `objective` non-empty, `max_length` in [50, 5000].
2. Build prompt:
   ```
   Summarize the following text. Focus on: {objective}.
   Keep the summary under {max_length} characters.
   Preserve key legal terms, dates, and named entities.

   Text:
   {text}
   ```
3. Call OpenAI chat completion:
   - Model: `settings.summarizer_model` (default: `gpt-4o-mini`).
   - Temperature: 0.1.
   - Max tokens: `max_length // 3` (rough char-to-token ratio).
4. Return `{ "summary": response_text }`.
5. Log: input length, output length, duration.

### Configuration

| Setting            | Env Var                  | Default      | Description                  |
|-------------------|--------------------------|--------------|------------------------------|
| Summarizer model   | `SUMMARIZER_MODEL`       | `gpt-4o-mini` | Model for summarization      |
| Default max length | `SUMMARIZER_MAX_LENGTH`  | `500`        | Default max summary chars    |
