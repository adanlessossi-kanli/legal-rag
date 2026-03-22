# Project Overview

## Purpose
Legal RAG — a retrieval-augmented generation application that lets users upload legal documents, ask natural-language questions, and receive grounded answers with source citations.

## Tech Stack

| Layer       | Technology                                      |
|------------|--------------------------------------------------|
| Frontend   | Next.js 14 (App Router), TypeScript, Tailwind CSS, next-intl |
| Backend    | Python 3.12, FastAPI                              |
| Database   | MongoDB Atlas (data + vector search)               |
| Cache      | Redis (query response caching)                    |
| LLM        | OpenAI GPT-4o                                     |
| Embeddings | OpenAI text-embedding-3-small                     |
| Monitoring | Prometheus (prometheus-client)                    |

## Constraints
- C-001: All answers must include source citations (document name + page/chunk reference).
- C-002: Frontend and backend communicate via REST JSON API + SSE for streaming.
- C-003: Document processing must support PDF, TXT, DOCX, and PPTX files.
- C-004: All data is scoped per user or per organization (multi-tenancy).
- C-005: JWT-based authentication required for all protected endpoints.

## Scope
1. Upload legal documents (PDF, TXT, DOCX, PPTX).
2. Ingest and chunk documents into MongoDB Atlas vector store.
3. Ask questions via chat interface with streaming responses.
4. Receive answers with cited sources — clickable source links open the original document at the relevant page.
5. Conversation persistence (server-side, per user).
6. Multi-agent system (Orchestrator, Researcher, Librarian, Writer, Summarizer).
7. Context Engine with Plan → Execute architecture and Blueprints.
8. Hybrid search (vector + keyword) with RRF merge and LLM reranking.
9. Multi-tenancy with organization-level data isolation.
10. Internationalization (EN, FR, DE, IT).
11. Background ingestion with retry queue and WebSocket notifications.
12. Redis caching for repeated queries.
13. Per-user cost tracking and Prometheus metrics.
14. Docker deployment with CI/CD pipeline.
