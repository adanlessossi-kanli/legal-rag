# Multi-Agent RAG — Non-Functional Requirements

## REQ-MN-001: Performance

| Metric                                | Target    | Notes                                      |
|--------------------------------------|-----------|--------------------------------------------|
| Query latency (non-streaming)         | ≤ 15s     | Includes all agent calls + LLM generation  |
| Query latency overhead vs. monolithic | ≤ 200ms   | MCP in-process overhead only               |
| Ingestion latency (100-page PDF)      | ≤ 35s     | Same as before + minimal MCP overhead      |
| Agent status event delivery           | ≤ 50ms    | From Orchestrator emit to SSE write        |
| Startup time (agent initialization)   | ≤ 2s      | All agents registered and connected        |

The multi-agent architecture must not introduce perceptible latency compared to the monolithic pipeline. In-process MCP transport avoids network overhead.

## REQ-MN-002: Observability

### Structured Logging

Every agent tool call produces a structured log entry:

```json
{
  "level": "info",
  "agent": "researcher",
  "tool": "researcher.research",
  "duration_ms": 1250,
  "status": "ok",
  "request_id": "req-abc123",
  "user_id": "user-xyz",
  "extra": {
    "chunks_returned": 5,
    "rewritten": true
  }
}
```

Required fields: `agent`, `tool`, `duration_ms`, `status`, `request_id`.

### Correlation ID

- The `X-Request-ID` header (set by existing middleware) propagates through all agent calls.
- Every log entry within a request includes the same `request_id`.
- Enables tracing a single user query across Orchestrator → Researcher → Librarian → Writer.

### Agent-Level Metrics (logged, not exported)

| Metric                          | Logged By    |
|--------------------------------|--------------|
| Tool call count per agent       | Each agent   |
| Tool call duration (p50, p95)   | Each agent   |
| Error count per agent per tool  | Each agent   |
| Chunks retrieved per query      | Librarian    |
| Query rewrite count             | Researcher   |
| Summarization trigger count     | Researcher   |
| LLM token usage per call        | Writer, Summarizer |

Metrics are logged as structured JSON. External metrics export (Prometheus, CloudWatch) is out of scope for this iteration.

### Health Check

`GET /api/health?deep=true` includes agent connectivity:

```json
{
  "status": "ok",
  "checks": {
    "mongodb": "ok",
    "openai": "ok",
    "agents": {
      "librarian": "ok",
      "researcher": "ok",
      "writer": "ok",
      "summarizer": "ok"
    }
  }
}
```

An agent reports `"error"` if its MCP server is unreachable or fails a ping.

## REQ-MN-003: Security

- **Input validation at every boundary.** Each agent validates its own inputs (see REQ-MP-004). The Orchestrator does not assume agents will validate.
- **Path traversal prevention.** `librarian.ingest` resolves `file_path` to absolute and verifies it starts with `settings.upload_dir`.
- **User scoping.** `user_id` is passed explicitly to every tool that accesses user data. Agents never infer or cache user identity.
- **No credential passing.** OpenAI API keys and MongoDB credentials are accessed via `settings` singleton, never passed through MCP tool parameters.
- **Sensitive data logging.** Agents log metadata (durations, counts, IDs) but never log full question text, document content, or LLM responses at INFO level. Full content is logged at DEBUG level only.
- **In-process trust.** Agents trust each other within the process boundary. If extracted to services, add mTLS or token auth at the MCP transport layer.

## REQ-MN-004: Reliability

### Graceful Degradation

See REQ-MP-007 in `mcp-protocol.md` for the full degradation matrix. Key principle: non-critical agent failures (Summarizer, query rewriting) degrade quality but don't fail the request.

### Timeout Hierarchy

```
API request timeout (90s)
  └── Orchestrator overall timeout (90s)
        ├── researcher.research (30s)
        │     ├── query rewrite LLM call (10s)
        │     ├── librarian.search (10s)
        │     └── summarizer.summarize (30s, optional)
        └── writer.generate (60s)
```

Inner timeouts are always shorter than outer timeouts to prevent cascading.

### Error Propagation

1. Agent tool raises `McpError` with typed error (see REQ-MP-005).
2. Orchestrator catches, logs with correlation ID, and either:
   - Degrades gracefully (Summarizer, rewrite failures), or
   - Returns structured error to API layer (Researcher, Writer failures).
3. API layer converts to HTTP error response (existing pattern).

### Idempotency

- `librarian.ingest`: Idempotent by `content_hash` + `user_id`. Re-ingesting the same file returns existing chunk count.
- `librarian.remove`: Idempotent. Removing a non-existent document is a no-op.
- `researcher.research`: Not idempotent (LLM calls may vary). Acceptable — queries are not retried at the API level.

## REQ-MN-005: Scalability Considerations (Future)

These are out of scope for this iteration but the architecture supports them:

- **Agent extraction.** Any agent can be moved to a separate service by changing the MCP transport from in-memory to HTTP/SSE over the network. No protocol changes needed.
- **Horizontal scaling.** Multiple Writer instances behind a load balancer for high-throughput generation.
- **Agent versioning.** MCP tool schemas are versioned. New tool versions can coexist with old ones during migration.
- **Queue-based ingestion.** `librarian.ingest` can be fronted by a task queue (Celery, SQS) for async processing at scale.
