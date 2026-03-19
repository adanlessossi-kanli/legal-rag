# Improvements — Backend Reliability

## REQ-IR-001: Replace JSON Metadata Store with SQLite

The current metadata store (`uploads/metadata.json`) has no file locking. Concurrent uploads or deletes cause race conditions and data loss.

### Requirements
- Replace `metadata.json` with a SQLite database (`uploads/metadata.db`).
- Schema:
  ```sql
  CREATE TABLE documents (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL,
      uploaded_at TEXT NOT NULL,
      chunk_count INTEGER NOT NULL DEFAULT 0,
      status      TEXT NOT NULL DEFAULT 'processing'
  );
  ```
- All existing functions in `core/metadata.py` (`save_document`, `get_all_documents`, `get_document`, `delete_document`, `update_status`) retain the same signatures.
- Use Python's built-in `sqlite3` module — no new dependencies.
- SQLite handles concurrent access safely via its internal locking.

### Migration
- On first startup, if `metadata.json` exists and `metadata.db` does not, auto-migrate entries from JSON to SQLite, then rename JSON to `metadata.json.bak`.

---

## REQ-IR-002: Async OpenAI Calls

Synchronous OpenAI calls inside async FastAPI endpoints block the event loop, degrading throughput under concurrent requests.

### Requirements
- Replace `OpenAI` client with `AsyncOpenAI` in both `rag/vectorstore.py` and `rag/llm.py`.
- Convert `_embed()`, `store_chunks()`, `retrieve()`, and `generate()` to `async` functions.
- Update `pipeline.py` functions (`ingest`, `query`) to be `async`.
- Update route handlers to `await` pipeline calls.

### Affected Files
| File                  | Change                                    |
|----------------------|-------------------------------------------|
| `rag/vectorstore.py` | `OpenAI` → `AsyncOpenAI`, async `_embed`  |
| `rag/llm.py`         | `OpenAI` → `AsyncOpenAI`, async `generate`|
| `rag/pipeline.py`    | `async def ingest()`, `async def query()` |
| `api/chat.py`        | `await query(...)`                        |
| `api/upload.py`      | `await ingest(...)`                       |

---

## REQ-IR-003: OpenAI Retry Logic

Transient OpenAI failures (rate limits, timeouts, server errors) currently surface as 500s to the user.

### Requirements
- Add retry with exponential backoff for all OpenAI API calls (embeddings and chat completions).
- Retry on: `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError` (status 500/502/503).
- Max retries: 3. Initial delay: 1s. Backoff multiplier: 2.
- Use `tenacity` library.

### Config
| Variable              | Default | Description          |
|----------------------|---------|----------------------|
| `OPENAI_MAX_RETRIES` | `3`     | Max retry attempts   |

### Implementation
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
)
async def _embed(texts: list[str]) -> list[list[float]]:
    ...
```

---

## REQ-IR-004: Shared OpenAI Client Singleton

Two separate `OpenAI` client instances exist — one in `vectorstore.py` and one in `llm.py`. This wastes connections and makes configuration inconsistent.

### Requirements
- Create `core/clients.py` exposing a single `AsyncOpenAI` instance.
- Both `vectorstore.py` and `llm.py` import from `core/clients.py`.
- Client is initialized once at module load using `settings.openai_api_key`.

### New File: `core/clients.py`
```python
from openai import AsyncOpenAI
from app.core.config import settings

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
```

---

## REQ-IR-005: Fix Upload File Rename Race Condition

The upload endpoint saves the file with a temp ID, runs ingestion, then renames to use the doc_id. If the rename fails, metadata and filesystem are inconsistent.

### Requirements
- Generate `doc_id` before saving the file to disk.
- Save directly as `{doc_id}_{safe_name}` — no temp file, no rename step.
- Pass the final path to `ingest()`.

### Implementation
```python
doc_id = f"doc_{uuid.uuid4().hex[:12]}"
safe_name = _sanitize_filename(file.filename)
file_path = upload_dir / f"{doc_id}_{safe_name}"
file_path.write_bytes(content)
# ingest receives doc_id directly instead of generating its own
chunk_count = ingest(str(file_path), file.filename, doc_id)
```

### Pipeline Change
- `ingest()` signature changes from `(file_path, original_name)` to `(file_path, original_name, doc_id)`.
- Remove `uuid` generation inside `ingest()`.
