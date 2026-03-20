# Multi-Agent RAG — Backend Implementation

## REQ-BI-001: Directory Structure

```
backend/app/
├── agents/                       # NEW — Multi-agent system
│   ├── __init__.py               #   Package init, exports create_orchestrator()
│   ├── base.py                   #   Base MCP server class + shared utilities
│   ├── orchestrator.py           #   Orchestrator (MCP client, coordination)
│   ├── librarian.py              #   Librarian agent (storage & retrieval)
│   ├── researcher.py             #   Researcher agent (query analysis)
│   ├── writer.py                 #   Writer agent (answer generation)
│   └── summarizer.py             #   Summarizer agent (text condensation)
├── rag/                          # EXISTING — kept as implementation modules
│   ├── chunker.py                #   (unchanged)
│   ├── llm.py                    #   (unchanged)
│   ├── loader.py                 #   (unchanged)
│   ├── pipeline.py               #   MODIFIED — thin delegation layer
│   └── vectorstore.py            #   (unchanged)
├── api/
│   ├── chat.py                   #   MODIFIED — agent_status SSE event
│   └── health.py                 #   MODIFIED — agent health in deep check
├── core/
│   └── config.py                 #   MODIFIED — new settings
└── main.py                       #   MODIFIED — agent lifecycle in lifespan
```

## REQ-BI-002: Base Agent (`agents/base.py`)

Shared base class and utilities for all agent MCP servers.

```python
class BaseAgent:
    name: str
    server: McpServer
    logger: logging.Logger

    def __init__(self, name: str):
        self.name = name
        self.server = McpServer(name)
        self.logger = logging.getLogger(f"agent.{name}")

    def register_tools(self) -> None:
        """Override to register MCP tools on self.server."""
        raise NotImplementedError

    def _validate_required(self, params: dict, fields: list[str]) -> None:
        """Raise McpError(InvalidParams) if any required field is missing or empty."""
        ...

    def _validate_string_length(self, value: str, name: str, min_len: int, max_len: int) -> None:
        """Raise McpError(InvalidParams) if string length is out of bounds."""
        ...

    def _log_call(self, tool: str, duration_ms: float, status: str, **extra) -> None:
        """Structured log entry for a tool call."""
        self.logger.info("tool_call", extra={
            "agent": self.name, "tool": tool,
            "duration_ms": duration_ms, "status": status, **extra
        })
```

## REQ-BI-003: Agent Implementations

### `agents/librarian.py`

- Extends `BaseAgent`.
- Registers 3 tools: `librarian.search`, `librarian.ingest`, `librarian.remove`.
- Imports from: `rag/loader.py`, `rag/chunker.py`, `rag/vectorstore.py`, `core/metadata.py`.
- No imports from other agents.
- Validates `file_path` is within `settings.upload_dir` (path traversal prevention).

### `agents/researcher.py`

- Extends `BaseAgent`.
- Registers 1 tool: `researcher.research`.
- Holds MCP client sessions to Librarian and Summarizer.
- Imports `rewrite_query` from `rag/llm.py` (for query rewriting).
- Graceful degradation: catches Summarizer failures, logs warning, continues.

### `agents/writer.py`

- Extends `BaseAgent`.
- Registers 1 tool: `writer.generate`.
- Imports `generate`, `generate_stream`, `_build_messages` from `rag/llm.py`.
- No imports from other agents.

### `agents/summarizer.py`

- Extends `BaseAgent`.
- Registers 1 tool: `summarizer.summarize`.
- Makes its own OpenAI call with a summarization-specific prompt.
- Uses `settings.summarizer_model` (gpt-4o-mini).
- No imports from other agents or `rag/` modules.

### `agents/orchestrator.py`

- MCP client only (not a server).
- Holds client sessions to all 4 agent servers.
- Exposes `query()`, `query_stream()`, `ingest()`, `remove_document()`, `summarize()`.
- Accepts `on_status` callback for SSE agent status events.
- Enforces 90s overall timeout per query.
- Exports `create_orchestrator()` factory function for use in lifespan.

## REQ-BI-004: Modified Files

### `rag/pipeline.py`

Replace direct logic with delegation. The module becomes a thin adapter so that `api/chat.py` and `api/upload.py` don't need import changes.

```python
from app.agents import get_orchestrator

async def query(question, history, user_id, document_ids):
    return await get_orchestrator().query(question, history, user_id, document_ids)

async def query_stream(question, history, user_id, document_ids):
    return await get_orchestrator().query_stream(question, history, user_id, document_ids)

async def ingest(file_path, original_name, doc_id, content_hash, user_id):
    return await get_orchestrator().ingest(file_path, original_name, doc_id, content_hash, user_id)

async def remove_document(doc_id):
    return await get_orchestrator().remove_document(doc_id)

# compute_hash remains here (no agent involvement)
def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
```

The `get_orchestrator()` helper retrieves the instance from FastAPI app state. Raises `RuntimeError` if called before startup.

### `core/config.py`

Add new settings:

```python
# Multi-agent
researcher_summarize_threshold: int = 10000
summarizer_model: str = "gpt-4o-mini"
summarizer_max_length: int = 500
```

### `api/chat.py`

Add `agent_status` SSE event in the streaming response:

```python
# In _stream_response(), wire on_status callback:
async def on_status(agent: str, status: str):
    nonlocal status_queue
    await status_queue.put({"type": "agent_status", "agent": agent, "status": status})

# In event_stream(), emit status events:
yield f"data: {json.dumps({'type': 'agent_status', 'agent': name, 'status': status})}\n\n"
```

For non-streaming responses, `on_status` is a no-op (status events are SSE-only).

### `api/health.py`

Extend deep health check to include agent status:

```python
# In deep health check:
checks["agents"] = await orchestrator.health_check()
# Returns: {"librarian": "ok", "researcher": "ok", "writer": "ok", "summarizer": "ok"}
```

### `main.py`

Add agent lifecycle in the lifespan context manager:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup (DB, indexes) ...

    from app.agents import create_orchestrator
    app.state.orchestrator = await create_orchestrator()
    logger.info("Multi-agent system started", extra={"agents": 4})

    yield

    # ... existing shutdown ...
    await app.state.orchestrator.shutdown()
    logger.info("Multi-agent system stopped")
```

## REQ-BI-005: Dependencies

Add to `requirements.txt`:

```
mcp>=1.0
```

No other new dependencies. The `mcp` package provides server, client, and transport modules.

## REQ-BI-006: Configuration

| Variable                         | Default        | Description                                  |
|---------------------------------|----------------|----------------------------------------------|
| `RESEARCHER_SUMMARIZE_THRESHOLD` | `10000`        | Total char threshold to trigger chunk summarization |
| `SUMMARIZER_MODEL`               | `gpt-4o-mini`  | Model for summarization calls                |
| `SUMMARIZER_MAX_LENGTH`          | `500`          | Default max summary length (chars)           |

All existing settings remain unchanged.

## REQ-BI-007: Startup Sequence

1. FastAPI lifespan begins.
2. Existing startup: MongoDB connection, index creation.
3. `create_orchestrator()` is called:
   a. Instantiate Librarian server → register tools.
   b. Instantiate Summarizer server → register tools.
   c. Instantiate Writer server → register tools.
   d. Instantiate Researcher server → register tools → connect as client to Librarian + Summarizer.
   e. Instantiate Orchestrator client → connect to Researcher, Writer, Librarian, Summarizer.
   f. Health-ping each server to verify connectivity.
4. Store Orchestrator in `app.state.orchestrator`.
5. Log: "Multi-agent system started" with agent count.

### Shutdown Sequence

1. Close Orchestrator client connections.
2. Close Researcher client connections (to Librarian, Summarizer).
3. Shut down MCP servers: Writer, Summarizer, Researcher, Librarian.
4. Existing shutdown: MongoDB disconnect.

Clients close before servers to prevent dangling connections.

## REQ-BI-008: Migration Path

The migration is non-breaking because:

1. `pipeline.py` retains the same public API (`query`, `query_stream`, `ingest`, `remove_document`, `compute_hash`).
2. `api/chat.py` continues to import from `pipeline.py` — no import changes.
3. `api/upload.py` continues to import from `pipeline.py` — no import changes.
4. The `agent_status` SSE event is additive — old frontends ignore unknown event types.
5. All existing tests pass because they test the API layer, which delegates through the same `pipeline.py` interface.

### Rollback

If the multi-agent system needs to be disabled:
1. Revert `pipeline.py` to direct implementation (restore from git).
2. Remove `agents/` directory.
3. Remove agent settings from `config.py`.
4. No database or frontend changes needed.
