# Improvements — RAG Pipeline

## REQ-IP-001: Duplicate Document Detection

Uploading the same document twice creates duplicate chunks in ChromaDB, polluting retrieval results with redundant content.

### Requirements
- Before ingestion, compute a SHA-256 hash of the uploaded file content.
- Store the hash in the document metadata (SQLite `documents` table — add `content_hash TEXT` column).
- On upload, check if a document with the same hash already exists.
- If duplicate found, return `409 Conflict` with `{"detail": "Document already uploaded", "existing_id": "<id>"}`.

### Schema Change
```sql
ALTER TABLE documents ADD COLUMN content_hash TEXT;
```

### API Change
- `POST /api/upload` returns `409` for duplicates.

### New Response `409`
```json
{
  "detail": "Document already uploaded",
  "existing_id": "doc_abc123"
}
```

---

## REQ-IP-002: Relevance Threshold on Retrieval

The top-K chunks are always returned regardless of similarity score. Irrelevant chunks degrade answer quality.

### Requirements
- Add a `RETRIEVAL_MIN_SCORE` setting (default: `0.3`).
- After ChromaDB query, filter out chunks whose distance exceeds the threshold.
- If all chunks are filtered out, return an empty context and let the LLM respond with "I don't have enough information."
- Include `distances` in the ChromaDB query `include` parameter.

### Config
| Variable               | Default | Description                              |
|-----------------------|---------|------------------------------------------|
| `RETRIEVAL_MIN_SCORE` | `1.5`   | Max L2 distance to consider relevant |

### Implementation
```python
results = _collection.query(
    query_embeddings=[q_embedding],
    n_results=settings.retrieval_top_k,
    include=["documents", "metadatas", "distances"],
)
chunks = []
for cid, doc, meta, dist in zip(
    results["ids"][0], results["documents"][0],
    results["metadatas"][0], results["distances"][0]
):
    if dist <= settings.retrieval_min_score:
        chunks.append({"chunk_id": cid, "text": doc, "metadata": meta})
```

---

## REQ-IP-003: Configurable Source Text Length

Source text in chat responses is hardcoded to 200 characters. Users may need more or less context.

### Requirements
- Add a `SOURCE_TEXT_MAX_LENGTH` setting (default: `200`).
- Use this setting when truncating source text in `pipeline.py`.

### Config
| Variable                  | Default | Description                          |
|--------------------------|---------|--------------------------------------|
| `SOURCE_TEXT_MAX_LENGTH`  | `200`   | Max characters per source text excerpt |

---

## REQ-IP-004: Conversation-Aware Query Rewriting

In multi-turn conversations, follow-up questions like "What about section 3?" lack standalone context. Embedding them directly yields poor retrieval results.

### Requirements
- Before embedding the question for retrieval, rewrite it using the LLM to be self-contained.
- Use a lightweight prompt that takes the last N history messages + current question and outputs a standalone query.
- Only rewrite when `history` is non-empty.
- Use the rewritten query for embedding/retrieval, but show the original question in the UI.

### Rewrite Prompt
```
Given the conversation history and a follow-up question, rewrite the
follow-up question to be a standalone question that captures the full
context. Return ONLY the rewritten question, nothing else.

History:
{history}

Follow-up question: {question}

Standalone question:
```

### Config
| Variable                    | Default | Description                          |
|----------------------------|---------|--------------------------------------|
| `ENABLE_QUERY_REWRITING`   | `true`  | Enable/disable conversation-aware rewriting |

### Implementation
- Add `rewrite_query()` function in `rag/llm.py`.
- Call from `pipeline.query()` before `retrieve()` when history is present and feature is enabled.
- Use `gpt-4o-mini` for rewriting (cheaper, fast enough for this task).
