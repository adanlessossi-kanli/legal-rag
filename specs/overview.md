# Project Overview

## Purpose
Legal RAG — a retrieval-augmented generation application that lets users upload legal documents, ask natural-language questions, and receive grounded answers with source citations.

## Tech Stack

| Layer        | Technology                          |
|-------------|--------------------------------------|
| Frontend    | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Backend     | Python 3.12, FastAPI                 |
| Vector DB   | ChromaDB (local, swappable)          |
| LLM         | OpenAI GPT-4o (via API)             |
| Embeddings  | OpenAI text-embedding-3-small       |
| Storage     | Local filesystem (uploads/)          |
| Auth        | None (v1), JWT (v2)                  |

## Constraints
- C-001: All answers must include source citations (document name + page/chunk reference).
- C-002: Backend must be stateless — all state lives in the vector DB or filesystem.
- C-003: Frontend and backend communicate via REST JSON API.
- C-004: The system must work fully offline once models are swapped to local alternatives.
- C-005: Document processing must support PDF and plain text files.

## MVP Scope
1. Upload legal documents (PDF, TXT).
2. Ingest and chunk documents into vector store.
3. Ask questions via chat interface.
4. Receive answers with cited sources.
5. View conversation history (session-scoped).

## Out of Scope (v1)
- Multi-user / authentication
- Document versioning
- Fine-tuned models
- Deployment automation
