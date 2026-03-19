# Architecture

## System Diagram

```
┌─────────────────────────────────────────────────┐
│                   Frontend (Next.js)             │
│  ┌───────────┐  ┌───────────┐  ┌─────────────┐  │
│  │ Chat Page │  │ Upload    │  │ Documents   │  │
│  │           │  │ Page      │  │ Page        │  │
│  └─────┬─────┘  └─────┬─────┘  └──────┬──────┘  │
│        └───────────────┼───────────────┘         │
│                        │ REST API                │
└────────────────────────┼─────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────┐
│                   Backend (FastAPI)               │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ /chat    │  │ /upload  │  │ /documents     │  │
│  └────┬─────┘  └────┬─────┘  └───────┬────────┘  │
│       │              │                │           │
│  ┌────▼─────────────▼────────────────▼────────┐  │
│  │              RAG Pipeline                   │  │
│  │  Ingest → Chunk → Embed → Store → Retrieve │  │
│  └────────┬──────────────────────┬────────────┘  │
│           │                      │                │
│    ┌──────▼──────┐       ┌───────▼───────┐       │
│    │  ChromaDB   │       │  LLM (OpenAI) │       │
│    └─────────────┘       └───────────────┘       │
└───────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component       | Responsibility                                      |
|----------------|------------------------------------------------------|
| Frontend        | UI, file upload, chat interface, document listing    |
| API Layer       | Request validation, routing, error handling          |
| RAG Pipeline    | Document processing, embedding, retrieval, generation|
| Vector DB       | Persistent storage and similarity search of chunks   |
| LLM Provider    | Answer generation given context + question           |
| File Storage    | Raw uploaded documents on local filesystem           |

## Communication

- Frontend → Backend: HTTP REST (JSON), multipart/form-data for uploads.
- Backend → ChromaDB: Python client (in-process).
- Backend → OpenAI: HTTPS API calls.

## Directory Structure

```
legal-rag/
├── frontend/          # Next.js app
│   ├── app/           # App Router pages
│   ├── components/    # Reusable UI
│   ├── lib/           # API client, utils
│   └── public/        # Static assets
├── backend/           # FastAPI app
│   ├── app/
│   │   ├── api/       # Route handlers
│   │   ├── core/      # Config, dependencies
│   │   ├── rag/       # Pipeline logic
│   │   └── models/    # Pydantic schemas
│   ├── uploads/       # Uploaded documents
│   └── main.py        # Entrypoint
└── specs/             # This spec folder
```
