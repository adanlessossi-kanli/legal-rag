# Legal RAG

A retrieval-augmented generation application for legal documents. Upload contracts, policies, or any legal text — then ask natural-language questions and get grounded answers with source citations.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                Frontend (Next.js)                 │
│   Chat Page  ·  Upload Page  ·  Documents Page    │
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
│          ChromaDB          OpenAI                   │
└────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer       | Technology                                  |
|------------|----------------------------------------------|
| Frontend   | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Backend    | Python 3.12, FastAPI                          |
| Vector DB  | ChromaDB (persistent, local)                  |
| LLM        | OpenAI GPT-4o                                 |
| Embeddings | OpenAI text-embedding-3-small                 |

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.12+
- An OpenAI API key

### Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # then set OPENAI_API_KEY
uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`.

### Frontend

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
| `RETRIEVAL_MIN_SCORE` | `1.5`               | Max L2 distance threshold  |
| `SOURCE_TEXT_MAX_LENGTH` | `200`             | Max chars per source excerpt |
| `CHROMA_PERSIST_DIR` | `./chroma_data`       | ChromaDB storage path      |
| `UPLOAD_DIR`      | `./uploads`              | Uploaded files directory   |
| `CORS_ORIGINS`    | `http://localhost:3000`  | Allowed CORS origins       |
| `API_KEY`         | *(empty)*                | API key (empty = disabled) |
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
| `NEXT_PUBLIC_API_KEY` | *(empty)*               | API key header   |

## API Endpoints

| Method   | Path                    | Description                          |
|----------|------------------------|--------------------------------------|
| `GET`    | `/api/health`          | Health check (`?deep=true` for deps) |
| `POST`   | `/api/chat`            | Ask a question (`?stream=true` for SSE) |
| `POST`   | `/api/upload`          | Upload a PDF, TXT, or DOCX document |
| `GET`    | `/api/documents`       | List all ingested documents          |
| `DELETE` | `/api/documents/{id}`  | Delete a document and its chunks     |

### POST /api/chat

```json
// Request
{ "question": "What is the liability clause?", "history": [] }

// Response (non-streaming)
{
  "answer": "According to Section 5.2...",
  "sources": [
    { "document": "contract.pdf", "chunk_id": "abc123", "text": "The total liability..." }
  ]
}
```

Streaming (`?stream=true`) returns SSE events:
```
data: {"type": "sources", "sources": [...]}
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
├── backend/
│   ├── app/
│   │   ├── api/            # Route handlers (chat, upload, documents, health)
│   │   ├── core/           # Config, auth, metadata store, OpenAI client
│   │   ├── models/         # Pydantic schemas
│   │   └── rag/            # Pipeline (loader, chunker, vectorstore, llm)
│   ├── tests/              # Unit and integration tests
│   ├── main.py             # FastAPI entrypoint
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── app/            # Next.js pages (chat, upload, documents)
│       ├── components/     # UI components (Sidebar, ChatMessage, etc.)
│       └── lib/            # API client
└── specs/                  # Project specifications
```

## RAG Pipeline

1. **Load** — Extract text from PDF (PyMuPDF), TXT, or DOCX (python-docx) files, preserving page numbers.
2. **Chunk** — Split into ~1000-character chunks with 200-character overlap using recursive character splitting.
3. **Embed** — Generate vectors via OpenAI `text-embedding-3-small`.
4. **Store** — Persist chunks + embeddings in ChromaDB.
5. **Retrieve** — On query, embed the question and fetch top-5 similar chunks (filtered by relevance threshold).
6. **Generate** — Send question + retrieved context to GPT-4o with a system prompt that enforces citation. Supports streaming.

## Features

- **Streaming chat** — Tokens stream in real-time via SSE for instant feedback.
- **Markdown rendering** — Assistant responses render markdown (bold, lists, tables, code).
- **Source citations** — Every answer includes the document name and relevant text excerpt.
- **Conversation persistence** — Chat history persists across page refreshes via localStorage.
- **Conversation-aware retrieval** — Follow-up questions are rewritten to standalone queries for better retrieval.
- **Document management** — Upload, list, and delete documents with optimistic UI updates.
- **Background ingestion** — Large documents are processed asynchronously; upload returns immediately.
- **DOCX support** — Upload Word documents alongside PDF and TXT.
- **File validation** — Client-side and server-side type/size checks, filename sanitization, duplicate detection.
- **Responsive UI** — Sidebar collapses on mobile, dark mode support, accessible navigation.
- **Security** — API key auth, rate limiting, timing-safe key comparison, input length limits.
- **Observability** — Structured JSON logging, request ID tracing, deep health checks.

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
| Sidebar | Branded logo, SVG nav icons with active accent tinting, status indicator footer, mobile overlay with backdrop blur |
| ChatMessage | User/assistant avatars, directional bubble tails, expandable source cards with document icons |
| ChatInput | Auto-resizing textarea, integrated send button, shadow elevation on focus |
| FileDropzone | Cloud-upload SVG illustration, scale animation on drag, inline error alerts |
| DocumentTable | Card-wrapped table, pill-shaped status badges with colored dots, icon-based delete actions, illustrated empty state |
| LoadingIndicator | Typing dots animation inside a styled bubble |
| ErrorBoundary | Error illustration SVG with refresh action button |

### Pages

- **Chat** — Empty state with document + chat bubble illustration and example query chips. Messages area with avatars. Disclaimer footer.
- **Upload** — Dropzone with cloud icon, animated spinner during upload, success/error alert cards.
- **Documents** — Document count subtitle, loading spinner, card-based table with hover states.

## License

MIT
