# Improvements — Security

## REQ-IS-001: Rate Limiting

The `/api/chat` and `/api/upload` endpoints call OpenAI on every request. Without rate limiting, a malicious or misconfigured client can exhaust API quota or DoS the service.

### Requirements
- Add per-IP rate limiting using `slowapi` (wraps `limits`).
- Limits:
  | Endpoint       | Limit              |
  |---------------|--------------------|
  | `POST /chat`  | 20 requests/minute |
  | `POST /upload`| 5 requests/minute  |
  | All others    | 60 requests/minute |
- Return `429 Too Many Requests` with `Retry-After` header when exceeded.
- Limits configurable via environment variables.

### Config
| Variable           | Default | Description                  |
|-------------------|---------|------------------------------|
| `RATE_LIMIT_CHAT` | `20/minute` | Chat endpoint rate limit |
| `RATE_LIMIT_UPLOAD` | `5/minute` | Upload endpoint rate limit |

### Implementation
- Add `slowapi` to `requirements.txt`.
- Attach `SlowAPIMiddleware` in `main.py`.
- Decorate each router with `@limiter.limit(...)`.

---

## REQ-IS-002: API Key Authentication

All endpoints are currently public. Add a lightweight API key mechanism so only authorized clients can access the service.

### Requirements
- New env var `API_KEY` (optional). When set, all `/api/*` endpoints except `/api/health` require `X-API-Key` header.
- If `API_KEY` is unset, auth is disabled (backward-compatible with v1 local usage).
- Return `401 Unauthorized` with `{"detail": "Invalid or missing API key"}` on failure.

### Implementation
- Add a FastAPI dependency (`verify_api_key`) that reads the header and compares against `settings.api_key`.
- Apply as a router-level dependency on `chat`, `upload`, and `documents` routers.
- Do not apply to `health` router.

### Config
| Variable  | Default | Description                              |
|----------|---------|------------------------------------------|
| `API_KEY` | `None`  | When set, enables API key authentication |

### Frontend Changes
- Read `NEXT_PUBLIC_API_KEY` from env.
- Include `X-API-Key` header in all `request()` calls in `lib/api.ts`.

---

## REQ-IS-003: Tighten CORS Configuration

Current config uses `allow_methods=["*"]` and `allow_headers=["*"]`, which is overly permissive.

### Requirements
- Restrict `allow_methods` to `["GET", "POST", "DELETE", "OPTIONS"]`.
- Restrict `allow_headers` to `["Content-Type", "X-API-Key"]`.
- Keep `allow_origins` configurable via `CORS_ORIGINS` env var (no change).

---

## REQ-IS-004: Streaming File Upload with Size Check

The upload endpoint currently reads the entire file into memory (`await file.read()`) before validating size. A malicious client can send a multi-GB payload and exhaust server memory.

### Requirements
- Read the uploaded file in chunks (e.g. 64KB at a time).
- Track cumulative bytes read; abort with `413` as soon as the limit is exceeded.
- Never hold more than one chunk in memory at a time during the size-check phase.

### Implementation
```python
async def _read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while chunk := await file.read(65_536):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="File exceeds 50MB limit")
        chunks.append(chunk)
    return b"".join(chunks)
```

---

## REQ-IS-005: Cap Conversation History Length

A client can send an unbounded `history` array, leading to token limit errors or excessive OpenAI costs.

### Requirements
- Add a `MAX_HISTORY_MESSAGES` setting (default: `20`).
- In the chat endpoint, truncate `history` to the last N messages before passing to the pipeline.
- If truncated, log a warning.

### Config
| Variable               | Default | Description                        |
|-----------------------|---------|------------------------------------|
| `MAX_HISTORY_MESSAGES` | `20`    | Max conversation turns sent to LLM |
