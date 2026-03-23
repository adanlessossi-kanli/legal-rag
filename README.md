# Legal RAG

A retrieval-augmented generation application for legal documents. Upload contracts, policies, or any legal text — then ask natural-language questions and get grounded answers with source citations.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                Frontend (Next.js)                 │
│   Chat  ·  Upload  ·  Documents  ·  Login/Register│
│                      │ REST API + SSE             │
└──────────────────────┼────────────────────────────┘
                       │
┌──────────────────────┼────────────────────────────┐
│                Backend (FastAPI)                   │
│                      │                             │
│          ┌───────────▼────────────┐                │
│          │   Multi-Agent System   │                │
│          │  Orchestrator          │                │
│          │  ├─ Researcher         │                │
│          │  ├─ Librarian          │                │
│          │  ├─ Writer             │                │
│          │  └─ Summarizer         │                │
│          └───┬───────────────┬────┘                │
│          ┌───▼───────────────▼────┐                │
│          │     RAG Pipeline       │                │
│          │ Load → Chunk → Embed → │                │
│          │ Store → Retrieve → Gen │                │
│          └───┬───────────────┬────┘                │
│          MongoDB         OpenAI                     │
└────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer       | Technology                                      |
|------------|--------------------------------------------------|
| Frontend   | Next.js 14 (App Router), TypeScript, Tailwind CSS, next-intl |
| Backend    | Python 3.12, FastAPI                              |
| Database   | MongoDB Atlas (data + vector search)               |
| Cache      | Redis (query response caching)                    |
| LLM        | OpenAI GPT-4o                                     |
| Embeddings | OpenAI text-embedding-3-small                     |
| PPTX       | python-pptx                                       |
| Monitoring | Prometheus (prometheus-client)                    |

## Getting Started

### Prerequisites

- Docker
- Node.js 18+
- Python 3.12+
- An OpenAI API key
- A MongoDB Atlas cluster for production (free tier M0 works)

### Quick Start (all services)

One command to start MongoDB, backend, and frontend:

```bash
# macOS / Linux
chmod +x start.sh
./start.sh

# Windows
start.bat
```

This will:
1. Start MongoDB and Redis via Docker Compose
2. Wait for MongoDB to be ready
3. Create the vector search index
4. Create a Python venv and install dependencies (if needed)
5. Start the backend on `http://localhost:8000`
6. Install npm dependencies (if needed)
7. Start the frontend on `http://localhost:3000`

To stop all services:

```bash
# macOS / Linux
./stop.sh

# Windows
stop.bat
```

**Prerequisite:** copy `backend/.env.example` to `backend/.env` and set your `OPENAI_API_KEY` and `JWT_SECRET` before running.

### Production Deployment (Docker)

Build and run all services in containers:

```bash
# Build and start everything
docker compose -f docker-compose.prod.yml up -d --build

# Create the vector search index (first time only)
docker compose -f docker-compose.prod.yml exec backend python ../scripts/create_vector_index.py
```

This starts MongoDB, Redis, the backend, frontend, and runs database migrations automatically via the `migrate` service. Data is persisted in Docker volumes.

To deploy to a remote environment, push images to GHCR (handled by CI/CD) and point `MONGODB_HOST`, `REDIS_URL`, and `CORS_ORIGINS` to your production infrastructure.

### Manual Setup

If you prefer to start services individually:

#### Local MongoDB (Docker)

```bash
docker compose up -d
```

This uses the [`mongodb-atlas-local`](https://hub.docker.com/r/mongodb/mongodb-atlas-local) image which supports `$vectorSearch` locally. Data is ephemeral — it resets when the container is removed.

Then create the vector search index:

```bash
python scripts/create_vector_index.py
```

To stop / reset:

```bash
docker compose down            # stop and remove container
```

#### MongoDB Atlas Vector Search Index (Production)

For production with Atlas, create the vector search index manually:

1. Go to **Atlas UI → Database → Browse Collections → legal_rag.chunks**
2. Click **Search Indexes → Create Index → JSON Editor**
3. Set the index name to `vector_index` and paste:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1536,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "user_id"
    },
    {
      "type": "filter",
      "path": "org_id"
    },
    {
      "type": "filter",
      "path": "doc_id"
    },
    {
      "type": "filter",
      "path": "namespace"
    }
  ]
}
```

#### Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # then set OPENAI_API_KEY, MONGODB_*, JWT_SECRET
uvicorn main:app --reload
```

##### Generating a JWT Secret

`JWT_SECRET` must be a long, random string. Generate one with:

```bash
# Python (works everywhere)
python -c "import secrets; print(secrets.token_urlsafe(64))"

# OpenSSL
openssl rand -base64 64

# Node.js
node -e "console.log(require('crypto').randomBytes(64).toString('base64url'))"
```

Copy the output into your `.env` file:

```
JWT_SECRET=your-generated-secret-here
```

Never commit this value to version control. Use a different secret for each environment (dev, staging, production).

Backend runs at `http://localhost:8000`.

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

### Database Migrations

Schema changes (indexes, collections) are managed via versioned migration scripts in `backend/migrations/versions/`. Each file has a timestamp prefix and an `async def up(db)` function.

```bash
# Check migration status
python backend/migrations/runner.py --status

# Apply pending migrations
python backend/migrations/runner.py
```

To create a new migration:

1. Create a file in `backend/migrations/versions/` with a timestamp prefix:
   ```
   backend/migrations/versions/20250615_120000_add_tags_index.py
   ```
2. Implement the `up(db)` function:
   ```python
   async def up(db):
       await db.documents.create_index("tags")
   ```
3. Commit the file. The CI/CD pipeline runs migrations automatically on deploy.

Applied migrations are tracked in the `_migrations` collection — each migration runs exactly once.

### Running Tests

#### Unit Tests

```bash
cd backend
pytest tests/ -v
```

All unit tests mock OpenAI calls and use an in-memory MongoDB (via `mongomock-motor`), so no external services are needed.

#### Integration Tests

Integration tests run against the real local MongoDB Docker container and exercise the full `$vectorSearch` retrieval path. They are marked with `@pytest.mark.integration` and skipped by default.

```bash
# Start MongoDB and create the vector search index first
docker compose up -d
python scripts/create_vector_index.py

# Run integration tests
pytest tests/test_integration.py -m integration -v

# Run all tests (unit + integration)
pytest tests/ -v

# Run only unit tests (skip integration)
pytest tests/ -m "not integration" -v
```

Test modules:
- `test_chunker.py` — chunk count, overlap, size limits
- `test_loader.py` — PDF, TXT, DOCX, PPTX text extraction
- `test_metadata.py` — document metadata CRUD round-trips
- `test_api.py` — validation, health checks, request ID middleware
- `test_auth.py` — register, login, refresh token rotation, JWT
- `test_chat.py` — chat responses with sources, conversation persistence
- `test_upload.py` — file upload, type/size validation, filename sanitization
- `test_documents.py` — document listing (user-scoped), delete with chunk cleanup
- `test_librarian.py` — librarian agent: search, ingest, remove tools
- `test_researcher.py` — researcher agent: query rewriting, context summarization
- `test_summarizer.py` — summarizer agent: text condensation via LLM
- `test_writer.py` — writer agent: answer generation (sync + streaming)
- `test_orchestrator.py` — orchestrator: end-to-end multi-agent query flow
- `test_agent_integration.py` — cross-agent integration scenarios
- `test_metrics.py` — Prometheus metrics endpoint, per-user cost tracking
- `test_registry.py` — agent registry: register, get, list, capabilities
- `test_planner.py` — planner: LLM plan generation, fallback, validation, parsing
- `test_executor.py` — executor: 3-stage pipeline, placeholder resolution, blueprint flow
- `test_tracer.py` — execution trace: step lifecycle, finalize, serialization
- `test_seed.py` — default blueprint seeding, idempotency
- `test_blueprints_api.py` — blueprint CRUD, auth, default protection, validation
- `test_sources.py` — source deduplication, merging, relevance ordering
- `test_integration.py` — real MongoDB `$vectorSearch` end-to-end (requires Docker)

## Configuration

All backend config is via environment variables (set in `backend/.env`):

| Variable           | Default                  | Description                |
|-------------------|--------------------------|----------------------------|
| `OPENAI_API_KEY`  | *(required)*             | OpenAI API key             |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name       |
| `LLM_MODEL`       | `gpt-4o`                 | Chat completion model      |
| `CHUNK_SIZE`      | `1000`                   | Characters per chunk       |
| `CHUNK_OVERLAP`   | `200`                    | Overlap between chunks     |
| `RETRIEVAL_TOP_K` | `5`                      | Number of chunks retrieved |
| `RETRIEVAL_MIN_SCORE` | `0.7`               | Min cosine similarity (0–1) |
| `SOURCE_TEXT_MAX_LENGTH` | `200`             | Max chars per source excerpt |
| `VECTOR_SEARCH_INDEX` | `vector_index`      | Atlas vector search index name |
| `UPLOAD_DIR`      | `./uploads`              | Uploaded files directory   |
| `CORS_ORIGINS`    | `http://localhost:3000`  | Allowed CORS origins       |
| `MONGODB_HOST`    | `localhost`              | MongoDB host (or Atlas cluster hostname) |
| `MONGODB_PORT`    | `27017`                  | MongoDB port (ignored for Atlas SRV) |
| `MONGODB_CLIENT_ID` | *(empty)*               | Atlas service account client ID |
| `MONGODB_CLIENT_SECRET` | *(empty)*           | Atlas service account client secret |
| `MONGODB_DB`      | `legal_rag`              | MongoDB database name      |
| `MONGODB_OPTIONS` | *(empty)*                | Connection string query params (e.g. `retryWrites=true&w=majority`) |
| `JWT_SECRET`      | *(required)*             | Secret for signing JWTs    |
| `JWT_ALGORITHM`   | `HS256`                  | JWT signing algorithm      |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`        | Access token TTL           |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7`           | Refresh token TTL          |
| `RATE_LIMIT_CHAT` | `20/minute`              | Chat endpoint rate limit   |
| `RATE_LIMIT_UPLOAD` | `5/minute`             | Upload endpoint rate limit |
| `MAX_HISTORY_MESSAGES` | `20`                | Max conversation turns     |
| `MAX_QUESTION_LENGTH` | `2000`               | Max question characters    |
| `OPENAI_MAX_RETRIES` | `3`                   | OpenAI retry attempts      |
| `ENABLE_QUERY_REWRITING` | `true`            | Conversation-aware rewriting |
| `LOG_FORMAT`      | `json`                   | Log format (`json` or `text`) |
| `RESEARCHER_SUMMARIZE_THRESHOLD` | `10000`  | Char threshold to trigger chunk summarization |
| `SUMMARIZER_MODEL` | `gpt-4o-mini`           | Model for summarization agent |
| `SUMMARIZER_MAX_LENGTH` | `500`              | Max summary length (chars) |
| `MAX_LOGIN_ATTEMPTS` | `5`                   | Failed logins before lockout |
| `LOCKOUT_DURATION_MINUTES` | `15`            | Account lockout duration   |
| `ENABLE_CSP`     | `true`                    | Enable Content-Security-Policy header |
| `DEFAULT_PAGE_SIZE` | `20`                   | Default pagination page size |
| `MAX_PAGE_SIZE`   | `100`                    | Maximum pagination page size |
| `INGESTION_MAX_RETRIES` | `3`                | Max ingestion queue retry attempts |
| `INGESTION_RETRY_DELAY_SECONDS` | `30`       | Delay between ingestion retries |
| `REDIS_URL`  | `redis://localhost:6379/0`  | Redis connection URL             |
| `CACHE_TTL_SECONDS` | `3600`              | Cache entry time-to-live         |
| `CACHE_ENABLED` | `true`                  | Enable/disable Redis caching     |
| `ENABLE_HYBRID_SEARCH` | `true`           | Enable keyword + vector hybrid search |
| `KEYWORD_SEARCH_LIMIT` | `10`             | Max keyword search results to merge |
| `ENABLE_RERANKING` | `true`               | Enable LLM-based reranking       |
| `RERANK_MODEL` | `gpt-4o-mini`             | Model for reranking passages     |
| `ENABLE_CONTEXT_ENGINE` | `true`          | Enable LLM-based query planning  |
| `PLANNER_MODEL` | `gpt-4o`                 | Model for plan generation        |
| `PLANNER_TIMEOUT` | `15`                   | Planner LLM timeout (seconds)    |
| `DEFAULT_NAMESPACE` | `KnowledgeStore`     | Default vector namespace         |
| `FILE_TOKEN_EXPIRY_SECONDS` | `300`   | Signed file URL TTL (5 minutes)          |

Frontend config (set in `frontend/.env.local`):

| Variable              | Default                 | Description      |
|----------------------|-------------------------|------------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL |

## API Endpoints

| Method   | Path                         | Auth | Description                          |
|----------|------------------------------|:----:|--------------------------------------|
| `GET`    | `/api/health`                | No   | Health check (`?deep=true` for deps) |
| `POST`   | `/api/auth/register`        | No   | Create a new account                 |
| `POST`   | `/api/auth/login`           | No   | Sign in and get tokens               |
| `POST`   | `/api/auth/refresh`         | No   | Refresh access token                 |
| `POST`   | `/api/auth/logout`          | Yes  | Revoke all sessions                  |
| `GET`    | `/api/auth/me`              | Yes  | Get current user info                |
| `POST`   | `/api/chat`                 | Yes  | Ask a question (`?stream=true` for SSE) |
| `POST`   | `/api/upload`               | Yes  | Upload a PDF, TXT, DOCX, or PPTX document |
| `GET`    | `/api/documents/{id}/file`  | Yes* | Serve original uploaded file (signed URL)  |
| `GET`    | `/api/documents/{id}/file-token` | Yes | Generate short-lived signed URL for file |
| `GET`    | `/api/documents`            | Yes  | List user/org documents (paginated)  |
| `GET`    | `/api/documents/{id}/status`| Yes  | Get document processing status       |
| `DELETE` | `/api/documents/{id}`       | Yes  | Delete a document and its chunks     |
| `GET`    | `/api/conversations`        | Yes  | List user's conversations (paginated) |
| `GET`    | `/api/conversations/{id}`   | Yes  | Get conversation with messages       |
| `DELETE` | `/api/conversations/{id}`   | Yes  | Delete a conversation                |
| `GET`    | `/api/metrics`              | No   | Prometheus metrics scrape endpoint   |
| `GET`    | `/api/usage`                | Yes  | Per-user OpenAI cost & token usage   |
| `POST`   | `/api/organizations`        | Yes  | Create an organization               |
| `GET`    | `/api/organizations`        | Yes  | List user's organizations            |
| `GET`    | `/api/organizations/{id}`   | Yes  | Get organization details + members   |
| `POST`   | `/api/organizations/{id}/members` | Yes | Invite a member (admin only)   |
| `DELETE` | `/api/organizations/{id}/members/{uid}` | Yes | Remove a member (admin only) |
| `POST`   | `/api/blueprints`           | Yes  | Create a blueprint                   |
| `GET`    | `/api/blueprints`           | Yes  | List blueprints (paginated)          |
| `GET`    | `/api/blueprints/{id}`      | Yes  | Get blueprint details                |
| `PUT`    | `/api/blueprints/{id}`      | Yes  | Update a blueprint                   |
| `DELETE` | `/api/blueprints/{id}`      | Yes  | Delete a blueprint                   |
| `WS`     | `/api/ws/ingestion`         | Yes* | WebSocket for ingestion notifications |

### POST /api/auth/register

```json
// Request
{ "email": "user@example.com", "password": "Secure1pass", "name": "Jane Doe" }

// Response 201
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": { "id": "...", "email": "user@example.com", "name": "Jane Doe", "created_at": "..." }
}
```

### POST /api/auth/login

```json
// Request
{ "email": "user@example.com", "password": "Secure1pass" }

// Response 200 — same shape as register
```

### POST /api/chat

```json
// Request
{
  "question": "What is the liability clause?",
  "conversation_id": "optional_id",
  "document_ids": ["doc_abc123"]  // optional — scope to specific documents
}

// Response (non-streaming)
{
  "answer": "According to Section 5.2...",
  "sources": [
    { "document": "contract.pdf", "chunk_id": "abc123", "text": "The total liability..." }
  ],
  "conversation_id": "abc123def456",
  "no_context": false
}
```

If `conversation_id` is omitted, a new conversation is created. If provided, the message is appended to that conversation and history is loaded from the database. If `document_ids` is provided, retrieval is scoped to those documents only.

Streaming (`?stream=true`) returns SSE events:
```
data: {"type": "agent_status", "agent": "planner", "status": "working"}
data: {"type": "agent_status", "agent": "researcher", "status": "working"}
data: {"type": "sources", "sources": [...]}
data: {"type": "agent_status", "agent": "writer", "status": "working"}
data: {"type": "conversation_id", "conversation_id": "abc123def456"}
data: {"type": "token", "token": "According"}
data: {"type": "token", "token": " to"}
data: {"type": "agent_status", "agent": "done", "status": "done"}
data: {"type": "done"}
```

### GET /api/usage

```json
// Request — GET /api/usage?month=2025-01 (month is optional, defaults to current)

// Response 200
{
  "month": "2025-01",
  "by_model": {
    "gpt-4o": {
      "prompt_tokens": 15000,
      "completion_tokens": 3000,
      "total_tokens": 18000,
      "estimated_cost_usd": 0.0675,
      "request_count": 12
    },
    "gpt-4o-mini": {
      "prompt_tokens": 5000,
      "completion_tokens": 1000,
      "total_tokens": 6000,
      "estimated_cost_usd": 0.00135,
      "request_count": 8
    }
  },
  "totals": {
    "prompt_tokens": 20000,
    "completion_tokens": 4000,
    "total_tokens": 24000,
    "estimated_cost_usd": 0.06885,
    "request_count": 20
  }
}
```

### POST /api/upload

Send as `multipart/form-data` with a `file` field. Accepts `.pdf`, `.txt`, `.docx`, `.pptx` (max 50MB).
Ingestion runs in the background — the response returns immediately with `status: "processing"`.

```json
// Response
{ "id": "doc_abc123", "name": "contract.pdf", "chunk_count": 0, "status": "processing" }
```

## Project Structure

```
legal-rag/
├── .github/
│   └── workflows/
│       └── ci.yml              # CI/CD: test, build, migrate, deploy
├── docker-compose.yml      # Local dev: MongoDB + Redis only
├── docker-compose.prod.yml # Production: all services containerized
├── start.sh                # One-command startup (macOS/Linux)
├── start.bat               # One-command startup (Windows)
├── stop.sh                 # Stop all services (macOS/Linux)
├── stop.bat                # Stop all services (Windows)
├── scripts/
│   └── create_vector_index.py  # Create vector search index locally
├── backend/
│   ├── Dockerfile          # Multi-stage production image
│   ├── migrations/
│   │   ├── runner.py       # Migration runner (apply/status)
│   │   └── versions/       # Versioned migration scripts
│   │       ├── 20250101_000000_initial_schema.py
│   │       └── 20250615_120000_add_context_engine.py
│   ├── app/
│   │   ├── agents/         # Multi-agent system
│   │   │   ├── base.py     #   BaseAgent, AgentError, tool registry
│   │   │   ├── orchestrator.py # Agent coordination (query, ingest, stream)
│   │   │   ├── librarian.py#   Document search, ingest, remove
│   │   │   ├── researcher.py#  Query rewriting + context retrieval
│   │   │   ├── summarizer.py#  Long-context chunk summarization
│   │   │   └── writer.py   #   Answer generation (sync + streaming)
│   │   ├── api/            # Route handlers
│   │   │   ├── auth.py     #   register, login, refresh, logout, me
│   │   │   ├── chat.py     #   chat with conversation persistence + caching
│   │   │   ├── conversations.py  # list, get, delete conversations
│   │   │   ├── documents.py#   list, status, delete, file serving (org/user-scoped)
│   │   │   ├── health.py   #   health check (incl. agent + Redis health)
│   │   │   ├── metrics.py  #   Prometheus scrape + usage endpoints
│   │   │   ├── organizations.py # org CRUD + member management
│   │   │   ├── upload.py   #   file upload (org/user-scoped)
│   │   │   ├── blueprints.py # blueprint CRUD (create, list, get, update, delete)
│   │   │   └── ws.py       #   WebSocket ingestion notifications
│   │   ├── core/           # Infrastructure
│   │   │   ├── auth.py     #   JWT auth dependency (get_current_user, get_org_id)
│   │   │   ├── cache.py    #   Redis cache (connect, get, set, invalidate)
│   │   │   ├── clients.py  #   OpenAI async client
│   │   │   ├── config.py   #   Settings from env vars
│   │   │   ├── database.py #   Motor MongoDB client + indexes
│   │   │   ├── ingestion_queue.py # Persistent ingestion queue + WebSocket notifications
│   │   │   ├── metadata.py #   Document metadata CRUD (org-aware)
│   │   │   ├── metrics.py  #   Prometheus metrics (HTTP, OpenAI, retrieval)
│   │   │   ├── notifications.py # WebSocket connection manager
│   │   │   ├── usage.py    #   Per-user OpenAI cost tracking
│   │   │   └── security.py #   Account lockout + CSP middleware
│   │   ├── engine/         # Context Engine (Plan → Execute)
│   │   │   ├── planner.py  #   LLM-based plan generation + fallback
│   │   │   ├── executor.py #   3-stage pipeline (blueprint → specialists → writer)
│   │   │   ├── tracer.py   #   Flight recorder for pipeline execution
│   │   │   ├── registry.py #   Agent capability registry (Researcher, Summarizer)
│   │   │   └── seed.py     #   Default blueprint seeding
│   │   ├── models/
│   │   │   └── schemas.py  #   Pydantic schemas (auth, chat, docs, conversations, blueprints)
│   │   └── rag/            # RAG pipeline
│   │       ├── chunker.py  #   Text splitting with offset tracking
│   │       ├── llm.py      #   OpenAI generation + query rewriting
│   │       ├── loader.py   #   PDF/TXT/DOCX/PPTX text extraction
│   │       ├── pipeline.py #   Thin facade delegating to orchestrator
│   │       ├── sources.py  #   Source deduplication + merging
│   │       └── vectorstore.py  # Hybrid search (vector + keyword + RRF + rerank)
│   ├── tests/
│   │   ├── conftest.py     #   Fixtures: mock MongoDB, auth helpers
│   │   ├── test_api.py     #   Validation, health, middleware
│   │   ├── test_auth.py    #   Register, login, JWT, refresh
│   │   ├── test_chat.py    #   Chat responses, conversations
│   │   ├── test_chunker.py #   Chunk count, overlap, size
│   │   ├── test_documents.py # List, delete (user-scoped)
│   │   ├── test_loader.py  #   PDF/TXT/DOCX loading
│   │   ├── test_metadata.py#   Metadata CRUD round-trips
│   │   ├── test_upload.py  #   Upload, validation, sanitization
│   │   ├── test_librarian.py   # Librarian agent tools
│   │   ├── test_researcher.py  # Researcher agent + query rewriting
│   │   ├── test_summarizer.py  # Summarizer agent
│   │   ├── test_writer.py      # Writer agent (sync + streaming)
│   │   ├── test_orchestrator.py# Orchestrator end-to-end flow
│   │   ├── test_agent_integration.py # Cross-agent integration
│   │   ├── test_metrics.py     # Prometheus metrics + cost tracking
│   │   ├── test_registry.py    # Agent registry: register, get, list
│   │   ├── test_planner.py     # Planner: LLM plan, fallback, validation
│   │   ├── test_executor.py    # Executor: 3-stage pipeline, placeholders
│   │   ├── test_tracer.py      # Execution trace lifecycle
│   │   ├── test_seed.py        # Default blueprint seeding
│   │   ├── test_blueprints_api.py # Blueprint CRUD endpoints
│   │   └── test_integration.py # Real MongoDB $vectorSearch (Docker)
│   ├── main.py             # FastAPI entrypoint
│   ├── pytest.ini          # Pytest configuration
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── Dockerfile          # Multi-stage Next.js standalone image
│   ├── messages/                 # Translation files (i18n)
│   │   ├── en.json               #   English (default)
│   │   ├── fr.json               #   French
│   │   ├── de.json               #   German
│   │   └── it.json               #   Italian
│   └── src/
│       ├── app/
│       │   ├── layout.tsx        # Root layout (font, global CSS)
│       │   └── [locale]/         # Locale-based routing segment
│       │       ├── layout.tsx    #   NextIntlClientProvider + AuthGuard
│       │       ├── page.tsx      #   Chat page (conversation-aware)
│       │       ├── login/page.tsx    # Login page
│       │       ├── register/page.tsx # Register page
│       │       ├── upload/page.tsx   # Upload page
│       │       └── documents/page.tsx# Documents page
│       ├── components/
│       │   ├── AgentIndicator.tsx # Active agent status with animated dot
│       │   ├── AuthGuard.tsx     # Auth redirect + sidebar layout
│       │   ├── ChatInput.tsx     # Auto-resizing textarea + send
│       │   ├── ChatMessage.tsx   # Message bubbles with grouped sources
│       │   ├── DocumentTable.tsx # Document list table
│       │   ├── ErrorBoundary.tsx # Error fallback UI
│       │   ├── FileDropzone.tsx  # Drag-and-drop upload (PDF/TXT/DOCX/PPTX)
│       │   ├── LanguageSwitcher.tsx # Locale dropdown selector
│       │   ├── LoadingIndicator.tsx # Typing dots animation
│       │   ├── Sidebar.tsx       # Nav, conversations, language switcher, user info
│       │   └── SourceViewer.tsx  # PDF viewer modal + text-excerpt mode (lazy-loaded)
│       ├── i18n/                 # Internationalization config
│       │   ├── config.ts         #   Supported locales + default
│       │   ├── navigation.ts     #   Localized Link, useRouter, usePathname
│       │   └── request.ts        #   next-intl request config (message loading)
│       ├── lib/
│       │   ├── api.ts            # API client (Bearer auth, auto-refresh)
│       │   └── auth.ts           # Token management (login, register, logout)
│       └── middleware.ts         # Locale detection + URL rewriting
└── specs/                        # Project specifications
```

## Multi-Agent System

The backend uses a multi-agent architecture where specialized agents collaborate through an orchestrator:

| Agent | Role |
|-------|------|
| Orchestrator | Coordinates the query pipeline via Context Engine (Plan → Execute), manages timeouts (90s), delegates to specialized agents |
| Researcher | Rewrites follow-up questions into standalone queries, retrieves context via Librarian, triggers Summarizer for long contexts |
| Librarian | Manages document lifecycle — search (vector retrieval, namespace-aware), ingest (load → chunk → embed → store), remove, and blueprint loading from ContextLibrary |
| Writer | Generates answers from retrieved context using GPT-4o, supports sync and streaming modes, applies blueprint styling when available |
| Summarizer | Condenses long chunks (>2000 chars) using GPT-4o-mini when total context exceeds the configurable threshold |

Agents communicate via a tool-based protocol: each agent registers named tools, and other agents invoke them through `call_tool()`. All tool calls are logged with timing and status.

### Context Engine

The query pipeline uses a two-phase Plan → Execute architecture:

1. **Plan** — The Planner uses GPT-4o to decompose the user's question into an `intent_query` (desired output style) and a `topic_query` (factual subject), then generates a step-by-step execution plan selecting from the Agent Registry (Researcher, Summarizer). Falls back to a hardcoded single-step plan if the LLM fails or `ENABLE_CONTEXT_ENGINE=false`.
2. **Execute** — The Executor runs a 3-stage pipeline:
   - **Stage 1 (Fixed):** Librarian searches the ContextLibrary namespace for a matching blueprint based on `intent_query`.
   - **Stage 2 (Planned):** Specialist agents (Researcher, Summarizer) execute the planned steps with `$$PLACEHOLDER$$` resolution for inter-step dependencies.
   - **Stage 3 (Fixed):** Writer generates the final answer, optionally styled by the blueprint's `scene_goal`, `style_guide`, `structure`, `participants`, and `instruction` fields.
3. **Trace** — Every step is recorded by the ExecutionTrace flight recorder with timing, status, and output summaries.

### Blueprints

Blueprints are semantic templates stored in the `blueprints` collection and embedded into the `ContextLibrary` vector namespace. Three default blueprints are seeded on first run:

| Blueprint | Style |
|-----------|-------|
| Suspense Narrative | Short, sharp sentences with sensory details and eerie tone |
| Technical Explanation | Formal, objective, structured (Definition → Function → Impact) |
| Casual Summary | Informal, brief, conversational |

Users can create custom blueprints via the API. The Planner's `intent_query` is used to find the best-matching blueprint via vector search.

## RAG Pipeline

1. **Load** — Extract text from PDF (PyMuPDF), TXT, DOCX (python-docx), or PPTX (python-pptx) files, preserving page/slide numbers.
2. **Chunk** — Split into ~1000-character chunks with 200-character overlap using recursive character splitting.
3. **Embed** — Generate vectors via OpenAI `text-embedding-3-small`.
4. **Store** — Persist chunks + embeddings in MongoDB Atlas (`chunks` collection).
5. **Retrieve** — Hybrid search: Researcher agent rewrites follow-up questions, then Librarian runs both Atlas Vector Search (`$vectorSearch`) and MongoDB full-text keyword search (`$text`), merges results via Reciprocal Rank Fusion (RRF), and reranks with GPT-4o-mini. Results are filtered by `org_id` or `user_id` (and optionally `document_ids`) with cosine similarity threshold. Long contexts are summarized by the Summarizer agent.
6. **Generate** — Writer agent sends question + retrieved context to GPT-4o with a system prompt that enforces citation. Supports streaming with real-time agent status events.
7. **Cache** — Non-streaming responses are cached in Redis keyed by `(user_id, question, document_ids)`. Cache is invalidated on document upload/delete via a generation counter.

## Features

- **Context Engine** — Two-phase Plan → Execute architecture. LLM-based Planner decomposes queries into intent + topic, generates execution plans from an Agent Registry. Executor runs a 3-stage pipeline (blueprint retrieval → specialist agents → writer). ExecutionTrace flight recorder logs every step with timing. Graceful fallback to single-step plan when LLM fails or feature is disabled.
- **Blueprints** — Semantic templates (ContextLibrary namespace) that style Writer output. Three defaults seeded (Suspense Narrative, Technical Explanation, Casual Summary). Full CRUD API with ownership validation and default protection. Descriptions are vector-embedded for intent-based retrieval.
- **Multi-agent system** — Orchestrator coordinates Researcher, Librarian, Writer, and Summarizer agents with tool-based communication, per-call logging, and 90-second timeout.
- **Streaming chat** — Tokens stream in real-time via SSE for instant feedback, with agent status indicators (Researching → Writing).
- **Markdown rendering** — Assistant responses render markdown (bold, lists, tables, code).
- **Source citations** — Every answer includes the document name and relevant text excerpt.
- **User authentication** — JWT-based registration, login, and session management with MongoDB. Refresh token rotation with SHA-256 hashed storage.
- **Conversation persistence** — Chat history persists server-side in MongoDB, scoped per user. Conversations are auto-created on first message and listed in the sidebar.
- **Conversation-aware retrieval** — Follow-up questions are rewritten to standalone queries for better retrieval.
- **Document management** — Upload, list, and delete documents with optimistic UI updates. Documents are scoped to the user's organization (if any) or to the individual user.
- **Document scoping** — Optionally restrict chat retrieval to specific documents via `document_ids`. Backend validates ownership — users can only scope to documents they own or that belong to their organization.
- **Background ingestion** — Persistent MongoDB-based ingestion queue with exponential backoff retries (30s → 60s → 120s, capped at 10min), dead-letter handling, scheduled retry timestamps, and crash recovery. Upload returns immediately. WebSocket notifications on completion.
- **Hybrid search + reranking** — Retrieval combines Atlas Vector Search (semantic) with MongoDB `$text` keyword search, merged via Reciprocal Rank Fusion (RRF). Results are then reranked by GPT-4o-mini for relevance. Both features degrade gracefully if unavailable.
- **Query caching** — Redis caching layer for repeated queries with generation-based invalidation on document changes. Legal teams often ask the same questions — cached responses are served instantly.
- **WebSocket ingestion notifications** — Real-time document processing status via WebSocket (`/api/ws/ingestion`), replacing client-side polling.
- **Multi-tenancy** — Organization-level data isolation. Create organizations, invite members, and share documents across the team. Vector search is scoped to `org_id` when the user belongs to an organization.
- **DOCX support** — Upload Word documents alongside PDF and TXT.
- **PPTX support** — Upload PowerPoint presentations. Extracts text from text frames, tables, and grouped shapes per slide. Speaker notes excluded (future enhancement).
- **Source viewer** — Clickable source citations open the original PDF in an in-app viewer at the relevant page with text highlighting. Sources are grouped by document with relevance scores. Signed URLs for secure file access. Non-PDF sources show text excerpts.
- **File validation** — Client-side and server-side type/size checks (PDF, TXT, DOCX, PPTX), filename sanitization, duplicate detection per user.
- **Responsive UI** — Sidebar collapses on mobile, dark mode support, accessible navigation.
- **Security** — JWT auth, bcrypt password hashing (SHA-256 pre-hash), refresh token rotation, rate limiting, input length limits, org/user-scoped data isolation, account lockout after failed logins, Content-Security-Policy headers, path traversal prevention.
- **Observability** — Structured JSON logging, request ID tracing, deep health checks (MongoDB + OpenAI + Redis + agents), per-agent tool call timing. Prometheus metrics endpoint (`/api/metrics`) for HTTP latency, OpenAI token usage, error rates, and retrieval performance.
- **Cost tracking** — Per-user OpenAI API usage recorded in MongoDB with estimated cost breakdown by model. Query via `GET /api/usage?month=YYYY-MM`.
- **Integration tests** — End-to-end `$vectorSearch` tests against the real local MongoDB Docker container (marked `@pytest.mark.integration`), covering user-scoped retrieval, org-scoped retrieval, document-scoped queries (single and multi-doc), score ordering, empty results, keyword search, and RRF merge logic.
- **Pagination** — Documents and conversations endpoints support paginated responses with configurable page size.
- **Internationalization** — Full i18n support for English, French, German, and Italian via `next-intl`. URL-based locale routing (`/fr/...`, `/de/...`, `/it/...`), language switcher in sidebar, ICU message format for pluralization, locale-aware date formatting.
- **Docker deployment** — Production Dockerfiles for backend (Python 3.12-slim) and frontend (Node 18-alpine standalone), with `docker-compose.prod.yml` for full-stack deployment. Non-root users, health checks, volume persistence.
- **CI/CD** — GitHub Actions pipeline: unit tests, integration tests, lint, Docker image build/push to GHCR, automated database migrations, deploy placeholder.
- **Database migrations** — Versioned migration scripts tracked in a `_migrations` collection. Runner supports apply and status commands. Runs automatically in CI/CD and as a Docker Compose service.

## UI Design

The frontend follows a professional design system built on CSS custom properties and Tailwind CSS.

### Design System

- **Color tokens** — Semantic variables (`--accent`, `--surface`, `--muted`, `--success`, `--danger`, `--warning`) with automatic light/dark mode switching.
- **Typography** — Geist Sans variable font with ligatures and contextual alternates enabled.
- **Shadows** — Three-tier elevation system (`--shadow-sm`, `--shadow`, `--shadow-md`) that adapts to dark mode.
- **Custom scrollbar** — Thin 6px scrollbar with themed track/thumb colors.
- **Focus rings** — Consistent 2px accent-colored outlines on all interactive elements.

### Components

| Component | Description |
|-----------|-------------|
| AgentIndicator | Shows active agent name (Researching/Writing/Summarizing) with animated ping dot and SVG icon |
| AuthGuard | Client-side auth check, redirects to `/login` if unauthenticated, renders Sidebar for protected routes |
| Sidebar | Branded logo, SVG nav icons, recent conversations list, language switcher, user name/email display, logout button, mobile overlay with backdrop blur |
| LanguageSwitcher | Locale dropdown (EN/FR/DE/IT), switches URL locale and re-renders all translated text |
| ChatMessage | User/assistant avatars, directional bubble tails, expandable source cards with document icons |
| ChatInput | Auto-resizing textarea, integrated send button, shadow elevation on focus |
| FileDropzone | Cloud-upload SVG illustration, scale animation on drag, inline error alerts |
| DocumentTable | Card-wrapped table, pill-shaped status badges with colored dots, icon-based delete actions, illustrated empty state |
| LoadingIndicator | Typing dots animation inside a styled bubble |
| ErrorBoundary | Error illustration SVG with refresh action button |

### Pages

- **Login** — Email + password form, link to register. Language switcher in top-right corner. Rendered without sidebar.
- **Register** — Name + email + password form with validation hints, link to login. Language switcher in top-right corner. Rendered without sidebar.
- **Chat** — Empty state with document + chat bubble illustration and example query chips. Messages area with avatars. "New Chat" button. Document scope selector to filter retrieval by specific documents. Agent status indicator during streaming (Researching → Writing). Conversations loaded from URL param `?c=<id>`. Disclaimer footer.
- **Upload** — Dropzone with cloud icon, animated spinner during upload, success/error alert cards.
- **Documents** — Document count subtitle, loading spinner, card-based table with hover states.

## License

MIT
