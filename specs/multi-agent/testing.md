# Multi-Agent RAG — Testing

## REQ-MT-001: Strategy

Three levels of testing, each with clear mock boundaries:

| Level       | Scope                          | Mocks                                    | Transport     |
|------------|--------------------------------|------------------------------------------|---------------|
| Unit        | Single agent, single tool      | OpenAI, MongoDB, other agents            | Direct call   |
| Integration | Multiple agents wired together | OpenAI, MongoDB                          | In-memory MCP |
| API         | Full HTTP request/response     | OpenAI, MongoDB                          | HTTP (TestClient) |

All tests mock OpenAI calls and use `mongomock-motor` (same as existing tests). No real API calls or network in CI.

## REQ-MT-002: New Test Files

```
backend/tests/
├── test_librarian.py           # Librarian agent unit tests
├── test_researcher.py          # Researcher agent unit tests
├── test_writer.py              # Writer agent unit tests
├── test_summarizer.py          # Summarizer agent unit tests
├── test_orchestrator.py        # Orchestrator coordination tests
└── test_agent_integration.py   # End-to-end multi-agent flow tests
```

## REQ-MT-003: Unit Tests — Librarian

| ID         | Test                                  | Type     | Description                                              |
|-----------|--------------------------------------|----------|----------------------------------------------------------|
| MT-LIB-01 | `test_search_returns_chunks`          | Happy    | Returns chunks matching query with scores                |
| MT-LIB-02 | `test_search_filters_by_user_id`      | Happy    | Only returns chunks belonging to the specified user      |
| MT-LIB-03 | `test_search_filters_by_document_ids` | Happy    | Scopes search to specified document IDs                  |
| MT-LIB-04 | `test_search_respects_min_score`      | Happy    | Filters out chunks below `retrieval_min_score`           |
| MT-LIB-05 | `test_search_empty_results`           | Edge     | Returns empty list when no chunks match                  |
| MT-LIB-06 | `test_search_validates_empty_query`   | Negative | Rejects empty query string with `VALIDATION_ERROR`       |
| MT-LIB-07 | `test_search_validates_top_k_bounds`  | Negative | Rejects `top_k` < 1 or > 20                             |
| MT-LIB-08 | `test_ingest_full_pipeline`           | Happy    | Ingests file, verifies chunks stored with correct metadata |
| MT-LIB-09 | `test_ingest_sets_user_id_on_chunks`  | Happy    | Every chunk has `user_id` in metadata                    |
| MT-LIB-10 | `test_ingest_error_sets_status`       | Negative | On failure, document status set to "error"               |
| MT-LIB-11 | `test_ingest_validates_file_path`     | Negative | Rejects path outside `UPLOAD_DIR` (path traversal)       |
| MT-LIB-12 | `test_ingest_validates_content_hash`  | Negative | Rejects malformed content hash                           |
| MT-LIB-13 | `test_remove_deletes_chunks_and_file` | Happy    | Removes chunks from DB and file from disk                |
| MT-LIB-14 | `test_remove_idempotent`              | Edge     | Removing non-existent doc_id succeeds (no-op)            |

## REQ-MT-004: Unit Tests — Researcher

| ID         | Test                                    | Type     | Description                                            |
|-----------|----------------------------------------|----------|--------------------------------------------------------|
| MT-RES-01 | `test_research_without_history`         | Happy    | Passes question directly to Librarian (no rewrite)     |
| MT-RES-02 | `test_research_with_history_rewrites`   | Happy    | Rewrites query when history is present                 |
| MT-RES-03 | `test_research_calls_librarian_search`  | Happy    | Verifies Librarian.search called with correct args     |
| MT-RES-04 | `test_research_returns_rewritten_query` | Happy    | Returns the rewritten query in the result              |
| MT-RES-05 | `test_research_summarizes_long_context` | Happy    | Triggers Summarizer when total chars exceed threshold  |
| MT-RES-06 | `test_research_skips_short_chunks`      | Edge     | Only summarizes individual chunks > 2000 chars         |
| MT-RES-07 | `test_research_no_summarize_under_threshold` | Edge | Skips Summarizer when total chars under threshold      |
| MT-RES-08 | `test_research_rewrite_failure_fallback`| Negative | Uses original question when rewriting fails            |
| MT-RES-09 | `test_research_summarizer_failure_fallback` | Negative | Returns unsummarized chunks when Summarizer fails  |
| MT-RES-10 | `test_research_empty_results`           | Edge     | Returns empty chunks when Librarian finds nothing      |
| MT-RES-11 | `test_research_validates_empty_question`| Negative | Rejects empty question with `VALIDATION_ERROR`         |

## REQ-MT-005: Unit Tests — Writer

| ID         | Test                                | Type     | Description                                          |
|-----------|-------------------------------------|----------|------------------------------------------------------|
| MT-WRI-01 | `test_generate_returns_answer`       | Happy    | Non-streaming generation returns answer string       |
| MT-WRI-02 | `test_generate_includes_context`     | Happy    | LLM prompt includes chunk text with source labels    |
| MT-WRI-03 | `test_generate_uses_system_prompt`   | Happy    | System prompt matches legal assistant prompt         |
| MT-WRI-04 | `test_generate_includes_history`     | Happy    | Conversation history included in LLM messages        |
| MT-WRI-05 | `test_generate_stream_yields_tokens` | Happy    | Streaming mode yields token events ending with done  |
| MT-WRI-06 | `test_generate_validates_empty_chunks` | Negative | Rejects empty chunks array with `VALIDATION_ERROR` |
| MT-WRI-07 | `test_generate_validates_empty_question` | Negative | Rejects empty question with `VALIDATION_ERROR`   |

## REQ-MT-006: Unit Tests — Summarizer

| ID         | Test                                  | Type     | Description                                        |
|-----------|---------------------------------------|----------|----------------------------------------------------|
| MT-SUM-01 | `test_summarize_returns_summary`       | Happy    | Returns a summary string                           |
| MT-SUM-02 | `test_summarize_prompt_includes_objective` | Happy | Prompt contains the objective text                 |
| MT-SUM-03 | `test_summarize_prompt_includes_max_length` | Happy | Prompt contains the max length constraint          |
| MT-SUM-04 | `test_summarize_uses_configured_model` | Happy    | Uses `settings.summarizer_model`                   |
| MT-SUM-05 | `test_summarize_validates_empty_text`  | Negative | Rejects empty text with `VALIDATION_ERROR`         |
| MT-SUM-06 | `test_summarize_validates_max_length_bounds` | Negative | Rejects `max_length` < 50 or > 5000          |

## REQ-MT-007: Orchestrator Tests

| ID         | Test                                      | Type     | Description                                        |
|-----------|------------------------------------------|----------|----------------------------------------------------|
| MT-ORC-01 | `test_query_calls_researcher_then_writer`  | Happy    | Verifies correct agent call order                  |
| MT-ORC-02 | `test_query_no_context_returns_fallback`   | Edge     | Empty chunks → NO_CONTEXT_ANSWER, no Writer call   |
| MT-ORC-03 | `test_query_builds_sources_from_chunks`    | Happy    | Sources list built correctly with truncated text   |
| MT-ORC-04 | `test_query_stream_emits_status_events`    | Happy    | Status callbacks: researcher→working, writer→working, done |
| MT-ORC-05 | `test_query_stream_forwards_tokens`        | Happy    | Token events from Writer forwarded correctly       |
| MT-ORC-06 | `test_ingest_delegates_to_librarian`       | Happy    | Ingest call forwarded to Librarian                 |
| MT-ORC-07 | `test_remove_delegates_to_librarian`       | Happy    | Remove call forwarded to Librarian                 |
| MT-ORC-08 | `test_summarize_delegates_to_summarizer`   | Happy    | Summarize call forwarded to Summarizer             |
| MT-ORC-09 | `test_researcher_failure_returns_error`    | Negative | Researcher error produces structured error         |
| MT-ORC-10 | `test_writer_failure_returns_error`        | Negative | Writer error produces structured error             |
| MT-ORC-11 | `test_overall_timeout_enforced`            | Negative | Query exceeding 90s is cancelled                   |

## REQ-MT-008: Integration Tests

| ID         | Test                                        | Type        | Description                                      |
|-----------|---------------------------------------------|-------------|--------------------------------------------------|
| MT-INT-01 | `test_full_query_flow`                       | Integration | Question → Researcher → Librarian → Writer → answer |
| MT-INT-02 | `test_full_query_with_summarization`         | Integration | Long context triggers Summarizer in the flow     |
| MT-INT-03 | `test_full_ingest_flow`                      | Integration | File → Librarian → chunks stored in mock DB      |
| MT-INT-04 | `test_stream_full_flow_event_order`          | Integration | SSE events emitted in correct order              |
| MT-INT-05 | `test_no_context_flow`                       | Integration | No matching chunks → NO_CONTEXT_ANSWER           |
| MT-INT-06 | `test_graceful_degradation_summarizer_down`  | Integration | Summarizer failure → query still succeeds        |
| MT-INT-07 | `test_graceful_degradation_rewrite_fails`    | Integration | Rewrite failure → original question used         |

## REQ-MT-009: Existing Test Impact

| Test File            | Impact  | Reason                                                    |
|---------------------|---------|-----------------------------------------------------------|
| `test_chat.py`       | None    | Tests API layer, which still calls `pipeline.query()`     |
| `test_upload.py`     | None    | Upload API unchanged                                      |
| `test_chunker.py`    | None    | Chunker module unchanged                                  |
| `test_loader.py`     | None    | Loader module unchanged                                   |
| `test_metadata.py`   | None    | Metadata module unchanged                                 |
| `test_api.py`        | None    | Health/validation unchanged (deep check additive)         |
| `test_auth.py`       | None    | Auth unchanged                                            |
| `test_documents.py`  | None    | Documents API unchanged                                   |

All existing tests must continue to pass without modification.

## REQ-MT-010: Fixtures

### `conftest.py` additions

```python
@pytest.fixture
def mock_openai_embed():
    """Mock OpenAI embeddings.create → returns deterministic vectors."""

@pytest.fixture
def mock_openai_chat():
    """Mock OpenAI chat.completions.create → returns canned response."""

@pytest.fixture
def librarian_agent(mock_db, mock_openai_embed):
    """Librarian MCP server with mocked MongoDB and OpenAI embeddings."""

@pytest.fixture
def summarizer_agent(mock_openai_chat):
    """Summarizer MCP server with mocked OpenAI chat."""

@pytest.fixture
def writer_agent(mock_openai_chat):
    """Writer MCP server with mocked OpenAI chat."""

@pytest.fixture
def researcher_agent(librarian_agent, summarizer_agent, mock_openai_chat):
    """Researcher MCP server connected to mocked Librarian and Summarizer."""

@pytest.fixture
def orchestrator(researcher_agent, writer_agent, librarian_agent, summarizer_agent):
    """Fully wired Orchestrator with all mocked agents."""
```

## REQ-MT-011: Coverage Targets

| Module           | Target  |
|-----------------|---------|
| `agents/`        | ≥ 90%   |
| `rag/` (existing)| ≥ 80%   |
| `api/` (existing)| ≥ 80%   |

Agent code is new and fully under our control — higher coverage target is appropriate.

## REQ-MT-012: Running Tests

```bash
cd backend

# All tests (existing + new)
pytest tests/ -v

# Agent tests only
pytest tests/test_librarian.py tests/test_researcher.py tests/test_writer.py tests/test_summarizer.py tests/test_orchestrator.py -v

# Integration tests only
pytest tests/test_agent_integration.py -v

# With coverage
pytest tests/ --cov=app/agents --cov-report=term-missing
```
