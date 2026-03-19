# Quality — Non-Functional Requirements

## Performance
- REQ-QN-001: Document ingestion ≤ 30s for a 100-page PDF.
- REQ-QN-002: Chat response ≤ 10s (including LLM latency).
- REQ-QN-003: Document list loads ≤ 500ms.

## Security
- REQ-QN-004: No secrets in source code — all via environment variables.
- REQ-QN-005: File upload validates type and size server-side (not just client).
- REQ-QN-006: CORS restricted to allowed origins.
- REQ-QN-007: Uploaded filenames sanitized to prevent path traversal.

## Reliability
- REQ-QN-008: Backend returns structured error responses (never raw stack traces).
- REQ-QN-009: Failed ingestion marks document status as `error`, does not crash server.

## Observability
- REQ-QN-010: Backend logs all requests with method, path, status, duration.
- REQ-QN-011: RAG pipeline logs chunk count, retrieval time, LLM token usage.

## Accessibility
- REQ-QN-012: Frontend meets WCAG 2.1 AA — keyboard navigable, proper ARIA labels.
- REQ-QN-013: Color contrast ratios ≥ 4.5:1 for text.
