# Improvements — Operational

## REQ-IO-001: Root `.gitignore`

The project has no root `.gitignore`. Build artifacts, secrets, and data directories will be committed accidentally.

### Requirements
- Add a `.gitignore` at the project root covering:

```gitignore
# Python
__pycache__/
*.pyc
venv/
.env

# Data
backend/chroma_data/
backend/uploads/

# Node
node_modules/
.next/
frontend/.env.local

# IDE
.vscode/
.idea/
*.swp
```

---

## REQ-IO-002: Deep Health Check

The `/api/health` endpoint returns `"ok"` without verifying that dependencies are functional. A misconfigured OpenAI key or corrupt ChromaDB will only surface on the first real request.

### Requirements
- Add an optional `?deep=true` query parameter to `GET /api/health`.
- When `deep=true`, verify:
  | Check          | Method                                          | Failure message            |
  |---------------|--------------------------------------------------|----------------------------|
  | ChromaDB      | Call `_collection.count()` — must not throw      | `"chromadb_unavailable"`   |
  | OpenAI API    | Call `openai.models.list()` with a short timeout  | `"openai_unavailable"`     |
- Response shape:

### Shallow (default)
```json
{ "status": "ok" }
```

### Deep (`?deep=true`) — all healthy
```json
{
  "status": "ok",
  "checks": {
    "chromadb": "ok",
    "openai": "ok"
  }
}
```

### Deep — partial failure
```json
{
  "status": "degraded",
  "checks": {
    "chromadb": "ok",
    "openai": "openai_unavailable"
  }
}
```

### Schema Change
```python
class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] | None = None
```

---

## REQ-IO-003: Request Validation — History Length

Covered by REQ-IS-005 (Security). Cross-reference only — no duplicate implementation.
