# Multi-Agent RAG System — Overview

## Purpose

Replace the monolithic RAG pipeline (`app/rag/pipeline.py`) with a Multi-Agent System (MAS) where four specialized agents communicate via Anthropic's Model Context Protocol (MCP) over HTTP/SSE transport. A central Orchestrator coordinates all agent interactions.

## Design Principles

- **DP-001: Single Responsibility** — Each agent owns exactly one domain. No agent directly accesses another agent's internal state or dependencies.
- **DP-002: Protocol-First** — All inter-agent communication goes through MCP tool calls. No direct function imports between agents.
- **DP-003: Graceful Degradation** — If a non-critical agent fails (e.g., Summarizer), the pipeline continues with reduced functionality rather than failing entirely.
- **DP-004: Observability by Default** — Every agent call is logged with agent name, tool name, duration, and outcome. Traces propagate a correlation ID from the original API request.
- **DP-005: Backward Compatibility** — The REST API contract (endpoints, request/response shapes) does not change. Existing frontend code works without modification (agent status UI is additive).
- **DP-006: Extractability** — Agents are in-process today but the MCP boundary means any agent can be extracted to a separate service without protocol changes.

## Constraints

- C-MA-001: All agents run in-process within the FastAPI application. No separate processes or containers.
- C-MA-002: MCP is the only communication mechanism between agents. No shared mutable state.
- C-MA-003: Each agent validates its own inputs at the MCP tool boundary. Never trust caller data.
- C-MA-004: LLM calls (OpenAI) are made only by Researcher (query rewriting), Writer (generation), and Summarizer (summarization). Librarian makes embedding calls only.
- C-MA-005: Conversation history remains managed at the API layer. Agents are stateless across requests.

## Agents

| Agent        | Domain                  | MCP Role | LLM Calls        |
|-------------|-------------------------|----------|-------------------|
| Orchestrator | Coordination            | Client   | None              |
| Librarian    | Storage & retrieval     | Server   | Embeddings only   |
| Researcher   | Query analysis & search | Server + Client | Query rewriting |
| Writer       | Answer generation       | Server   | Chat completion   |
| Summarizer   | Text condensation       | Server   | Chat completion   |

## Query Flow

```
User Question
     │
     ▼
┌─────────────┐
│ Orchestrator │  ← receives (question, history, user_id, document_ids)
└──────┬──────┘
       │ 1. emit status("researcher", "working")
       │ 2. call researcher.research(question, history, user_id, document_ids)
       ▼
┌─────────────┐
│ Researcher   │
│              │── 2a. rewrite query (if history exists) [LLM: gpt-4o-mini]
│              │── 2b. call librarian.search(query, user_id, document_ids)
│              │── 2c. (optional) call summarizer.summarize(long_chunks)
└──────┬──────┘
       │ return { chunks, rewritten_query }
       ▼
┌─────────────┐
│ Orchestrator │
│              │── 3. if no chunks → return NO_CONTEXT_ANSWER (short-circuit)
│              │── 4. build sources from chunks
│              │── 5. emit status("writer", "working")
│              │── 6. call writer.generate(question, chunks, history)
└──────┬──────┘
       ▼
┌─────────────┐
│   Writer     │── 7. build prompt, call LLM, stream tokens [LLM: gpt-4o]
└──────┬──────┘
       │ return answer (streamed or complete)
       ▼
┌─────────────┐
│ Orchestrator │── 8. emit status("done")
└──────┬──────┘     9. return (answer, sources, no_context=False)
       ▼
   API Response
```

## Ingestion Flow

```
Upload API
     │
     ▼
┌─────────────┐
│ Orchestrator │── call librarian.ingest(file_path, doc_id, user_id)
└──────┬──────┘
       ▼
┌─────────────┐
│  Librarian   │── load → chunk → embed → store
└─────────────┘
```

## Summarization Flow (on-demand)

```
Researcher (or Orchestrator)
     │
     │ call summarizer.summarize(text, objective)
     ▼
┌─────────────┐
│ Summarizer   │── condense text per objective [LLM: gpt-4o-mini]
└──────┬──────┘
       │ return summary
       ▼
   Caller receives summary
```

## Impact Matrix

| Component                  | Before                          | After                                      | Breaking? |
|---------------------------|---------------------------------|--------------------------------------------|-----------|
| `app/rag/pipeline.py`     | Monolithic ingest/query/remove  | Thin wrapper delegating to Orchestrator     | No        |
| `app/rag/llm.py`          | Direct OpenAI calls             | Wrapped inside Writer + Summarizer agents   | No        |
| `app/rag/vectorstore.py`  | Direct MongoDB calls            | Wrapped inside Librarian agent              | No        |
| `app/rag/chunker.py`      | Called by pipeline               | Called by Librarian agent                   | No        |
| `app/rag/loader.py`       | Called by pipeline               | Called by Librarian agent                   | No        |
| `app/api/chat.py`         | Calls pipeline.query directly   | Calls pipeline.query → Orchestrator         | No        |
| Frontend SSE events       | `sources`, `token`, `done`      | + `agent_status` event type (additive)      | No        |
| Frontend ChatMessage      | No agent info                   | + AgentIndicator component (additive)       | No        |

## What Does NOT Change

- REST API endpoints, paths, request/response schemas.
- Authentication, JWT, refresh token rotation.
- MongoDB schema, collections, vector search index.
- Upload API, background ingestion trigger.
- Frontend routing, pages, i18n structure.
- Existing test suite (all tests continue to pass).
