# Quality — Testing

## Backend Tests (pytest)

### Unit Tests
- REQ-QT-001: Chunking produces correct chunk count and overlap.
- REQ-QT-002: Metadata JSON read/write round-trips correctly.
- REQ-QT-003: Chat request validation rejects empty questions.
- REQ-QT-004: File type validation rejects unsupported extensions.

### Integration Tests
- REQ-QT-005: Upload endpoint ingests a PDF and returns correct response.
- REQ-QT-006: Chat endpoint returns answer with sources for a known document.
- REQ-QT-007: Delete endpoint removes document and its chunks.

### Mocking
- Mock OpenAI calls in all tests (no real API calls in CI).
- Use a temporary ChromaDB instance per test session.

## Frontend Tests (future)
- Component tests with React Testing Library.
- E2E tests with Playwright.

## Coverage Target
- Backend: 80%+ line coverage for `rag/` and `api/` modules.
