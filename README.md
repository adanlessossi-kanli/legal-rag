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
| LLM        | OpenAI GPT-4o                                     |
| Embeddings | OpenAI text-embedding-3-small                     |

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
1. Start MongoDB via Docker Compose
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

### Running Tests

```bash
cd backend
pytest tests/ -v
```

All tests mock OpenAI calls and use an in-memory MongoDB (via `mongomock-motor`), so no external services are needed.

Test modules:
- `test_chunker.py` — chunk count, overlap, size limits
- `test_loader.py` — PDF, TXT, DOCX text extraction
- `test_metadata.py` — document metadata CRUD round-trips
- `test_api.py` — validation, health checks, request ID middleware
- `test_auth.py` — register, login, refresh token rotation, JWT
- `test_chat.py` — chat responses with sources, conversation persistence
- `test_upload.py` — file upload, type/size validation, filename sanitization
- `test_documents.py` — document listing (user-scoped), delete with chunk cleanup

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
| `POST`   | `/api/upload`               | Yes  | Upload a PDF, TXT, or DOCX document |
| `GET`    | `/api/documents`            | Yes  | List user's ingested documents       |
| `DELETE` | `/api/documents/{id}`       | Yes  | Delete a document and its chunks     |
| `GET`    | `/api/conversations`        | Yes  | List user's conversations            |
| `GET`    | `/api/conversations/{id}`   | Yes  | Get conversation with messages       |
| `DELETE` | `/api/conversations/{id}`   | Yes  | Delete a conversation                |

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
{ "question": "What is the liability clause?", "conversation_id": "optional_id" }

// Response (non-streaming)
{
  "answer": "According to Section 5.2...",
  "sources": [
    { "document": "contract.pdf", "chunk_id": "abc123", "text": "The total liability..." }
  ],
  "conversation_id": "abc123def456"
}
```

If `conversation_id` is omitted, a new conversation is created. If provided, the message is appended to that conversation and history is loaded from the database.

Streaming (`?stream=true`) returns SSE events:
```
data: {"type": "sources", "sources": [...]}
data: {"type": "conversation_id", "conversation_id": "abc123def456"}
data: {"type": "token", "token": "According"}
data: {"type": "token", "token": " to"}
data: {"type": "done"}
```

### POST /api/upload

Send as `multipart/form-data` with a `file` field. Accepts `.pdf`, `.txt`, `.docx` (max 50MB).
Ingestion runs in the background — the response returns immediately with `status: "processing"`.

```json
// Response
{ "id": "doc_abc123", "name": "contract.pdf", "chunk_count": 0, "status": "processing" }
```

## Project Structure

```
legal-rag/
├── docker-compose.yml      # Local MongoDB with Atlas Vector Search
├── start.sh                # One-command startup (macOS/Linux)
├── start.bat               # One-command startup (Windows)
├── stop.sh                 # Stop all services (macOS/Linux)
├── stop.bat                # Stop all services (Windows)
├── scripts/
│   └── create_vector_index.py  # Create vector search index locally
├── backend/
│   ├── app/
│   │   ├── api/            # Route handlers
│   │   │   ├── auth.py     #   register, login, refresh, logout, me
│   │   │   ├── chat.py     #   chat with conversation persistence
│   │   │   ├── conversations.py  # list, get, delete conversations
│   │   │   ├── documents.py#   list, delete documents (user-scoped)
│   │   │   ├── health.py   #   health check
│   │   │   └── upload.py   #   file upload (user-scoped)
│   │   ├── core/           # Infrastructure
│   │   │   ├── auth.py     #   JWT auth dependency (get_current_user)
│   │   │   ├── clients.py  #   OpenAI async client
│   │   │   ├── config.py   #   Settings from env vars
│   │   │   ├── database.py #   Motor MongoDB client + indexes
│   │   │   └── metadata.py #   Document metadata CRUD (MongoDB)
│   │   ├── models/
│   │   │   └── schemas.py  #   Pydantic schemas (auth, chat, docs, conversations)
│   │   └── rag/            # RAG pipeline
│   │       ├── chunker.py  #   Text splitting
│   │       ├── llm.py      #   OpenAI generation + query rewriting
│   │       ├── loader.py   #   PDF/TXT/DOCX text extraction
│   │       ├── pipeline.py #   Orchestration (ingest, query, remove)
│   │       └── vectorstore.py  # MongoDB Atlas Vector Search
│   ├── tests/
│   │   ├── conftest.py     #   Fixtures: mock MongoDB, auth helpers
│   │   ├── test_api.py     #   Validation, health, middleware
│   │   ├── test_auth.py    #   Register, login, JWT, refresh
│   │   ├── test_chat.py    #   Chat responses, conversations
│   │   ├── test_chunker.py #   Chunk count, overlap, size
│   │   ├── test_documents.py # List, delete (user-scoped)
│   │   ├── test_loader.py  #   PDF/TXT/DOCX loading
│   │   ├── test_metadata.py#   Metadata CRUD round-trips
│   │   └── test_upload.py  #   Upload, validation, sanitization
│   ├── main.py             # FastAPI entrypoint
│   ├── pytest.ini          # Pytest configuration
│   ├── requirements.txt
│   └── .env.example
├── frontend/
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
│       │   ├── AuthGuard.tsx     # Auth redirect + sidebar layout
│       │   ├── ChatInput.tsx     # Auto-resizing textarea + send
│       │   ├── ChatMessage.tsx   # Message bubbles with sources
│       │   ├── DocumentTable.tsx # Document list table
│       │   ├── ErrorBoundary.tsx # Error fallback UI
│       │   ├── FileDropzone.tsx  # Drag-and-drop upload
│       │   ├── LanguageSwitcher.tsx # Locale dropdown selector
│       │   ├── LoadingIndicator.tsx # Typing dots animation
│       │   └── Sidebar.tsx       # Nav, conversations, language switcher, user info
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

## RAG Pipeline

1. **Load** — Extract text from PDF (PyMuPDF), TXT, or DOCX (python-docx) files, preserving page numbers.
2. **Chunk** — Split into ~1000-character chunks with 200-character overlap using recursive character splitting.
3. **Embed** — Generate vectors via OpenAI `text-embedding-3-small`.
4. **Store** — Persist chunks + embeddings in MongoDB Atlas (`chunks` collection).
5. **Retrieve** — On query, embed the question and fetch top-5 similar chunks via Atlas Vector Search (`$vectorSearch` aggregation), filtered by `user_id` and cosine similarity threshold.
6. **Generate** — Send question + retrieved context to GPT-4o with a system prompt that enforces citation. Supports streaming.

## Features

- **Streaming chat** — Tokens stream in real-time via SSE for instant feedback.
- **Markdown rendering** — Assistant responses render markdown (bold, lists, tables, code).
- **Source citations** — Every answer includes the document name and relevant text excerpt.
- **User authentication** — JWT-based registration, login, and session management with MongoDB. Refresh token rotation with SHA-256 hashed storage.
- **Conversation persistence** — Chat history persists server-side in MongoDB, scoped per user. Conversations are auto-created on first message and listed in the sidebar.
- **Conversation-aware retrieval** — Follow-up questions are rewritten to standalone queries for better retrieval.
- **Document management** — Upload, list, and delete documents with optimistic UI updates. All documents are user-scoped.
- **Background ingestion** — Large documents are processed asynchronously; upload returns immediately.
- **DOCX support** — Upload Word documents alongside PDF and TXT.
- **File validation** — Client-side and server-side type/size checks, filename sanitization, duplicate detection per user.
- **Responsive UI** — Sidebar collapses on mobile, dark mode support, accessible navigation.
- **Security** — JWT auth, bcrypt password hashing (SHA-256 pre-hash), refresh token rotation, rate limiting, input length limits, user-scoped data isolation.
- **Observability** — Structured JSON logging, request ID tracing, deep health checks (MongoDB + OpenAI).
- **Internationalization** — Full i18n support for English, French, German, and Italian via `next-intl`. URL-based locale routing (`/fr/...`, `/de/...`, `/it/...`), language switcher in sidebar, ICU message format for pluralization, locale-aware date formatting.

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
- **Chat** — Empty state with document + chat bubble illustration and example query chips. Messages area with avatars. "New Chat" button. Conversations loaded from URL param `?c=<id>`. Disclaimer footer.
- **Upload** — Dropzone with cloud icon, animated spinner during upload, success/error alert cards.
- **Documents** — Document count subtitle, loading spinner, card-based table with hover states.

## License

MIT
