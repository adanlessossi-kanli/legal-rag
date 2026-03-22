# Quality — Testing

## Backend Tests (pytest)

All unit tests mock OpenAI calls and use an in-memory MongoDB (via `mongomock-motor`), so no external services are needed. Integration tests run against the real local MongoDB Docker container.

### Unit Tests

**RAG Pipeline:**
- **test_chunker.py** — Chunk count, overlap, size limits. Verify enriched metadata: `page_start`, `page_end`, `start_char`, `end_char`. Verify `page` alias preserved. Cross-page chunk detection.
- **test_loader.py** — PDF, TXT, DOCX, PPTX text extraction. PPTX: single-slide, multi-slide, slides with tables, grouped shapes, empty slides skipped, all-slides-empty returns empty list. Verify `DocumentPage.metadata` has correct `source` and `page`.
- **test_sources.py** — Source deduplication: two chunks from same `(doc_id, page)` merge into one `Source` with union character range. Ordering preserved. Highest relevance kept.
- **test_metadata.py** — Document metadata CRUD round-trips.

**API:**
- **test_api.py** — Validation, health checks, request ID middleware. File serving: auth required, correct content-type (PDF, TXT, DOCX, PPTX), 404 for missing doc, 404 with specific message for doc-exists-but-file-missing-from-disk, 403 for unauthorized, path traversal prevention, Range header support (206), ETag / If-None-Match (304). File-token: returns signed URL, validates ownership before generating (403), URL expires after 5 minutes, invalid signature rejected, 404 for nonexistent doc.
- **test_auth.py** — Register, login, refresh token rotation, JWT validation.
- **test_chat.py** — Chat responses with sources (including `doc_id`, `page`, `relevance`), conversation persistence, source deduplication in response.
- **test_upload.py** — File upload, type/size validation (`.pptx` accepted), filename sanitization, duplicate detection.
- **test_documents.py** — Document listing (user-scoped), delete with chunk cleanup, file type filter includes `pptx`.

**Agents:**
- **test_librarian.py** — Librarian agent: search, ingest, remove tools.
- **test_researcher.py** — Researcher agent: query rewriting, context summarization.
- **test_summarizer.py** — Summarizer agent: text condensation via LLM.
- **test_writer.py** — Writer agent: answer generation (sync + streaming).
- **test_orchestrator.py** — Orchestrator: end-to-end multi-agent query flow.
- **test_agent_integration.py** — Cross-agent integration scenarios.

**Engine:**
- **test_registry.py** — Agent registry: register, get, list, capabilities.
- **test_planner.py** — Planner: LLM plan generation, fallback, validation, parsing.
- **test_executor.py** — Executor: 3-stage pipeline, placeholder resolution, blueprint flow.
- **test_tracer.py** — Execution trace: step lifecycle, finalize, serialization.
- **test_seed.py** — Default blueprint seeding, idempotency.
- **test_blueprints_api.py** — Blueprint CRUD, auth, default protection, validation.

**Infrastructure:**
- **test_metrics.py** — Prometheus metrics endpoint, per-user cost tracking.

### Integration Tests

Marked with `@pytest.mark.integration`, skipped by default. Run against the real local MongoDB Docker container.

- **test_integration.py** — Real MongoDB `$vectorSearch` end-to-end: user-scoped retrieval, org-scoped retrieval, document-scoped queries (single and multi-doc), score ordering, empty results, keyword search, RRF merge logic.

### Mocking
- Mock OpenAI calls in all unit tests (no real API calls in CI).
- Use `mongomock-motor` for in-memory MongoDB in unit tests.
- Integration tests use the real `mongodb-atlas-local` Docker image.

## Frontend Tests

- **SourceViewer** — Renders modal, loads PDF at correct page, closes on Escape/backdrop. Page navigation (prev/next/thumbnail). Text search highlights matches. Full-screen on mobile. Lazy-loaded (not in main bundle). Text-excerpt mode for PPTX/DOCX/TXT with "Slide N" label for PPTX. Shows "file unavailable" message on 404. Silently refreshes signed URL on 401/403 expiry.
- **ChatMessage** — Sources grouped by document. Each entry clickable, opens viewer with correct props. Relevance badge displayed and color-coded. Deep link hash updated on open, cleared on close. PPTX sources labeled "Slide N".
- **Upload page** — After successful upload, navigates to `/documents` via client-side routing. No navigation on failure. PPTX files accepted in dropzone. State cleaned up on unmount. Navigation timer cleared on unmount.
- **Documents page** — File type filter includes PPTX option (synced with backend regex). WebSocket updates document status in-place after navigation from upload.

## Coverage Target
- Backend: 80%+ line coverage for `rag/`, `api/`, `agents/`, and `engine/` modules.
