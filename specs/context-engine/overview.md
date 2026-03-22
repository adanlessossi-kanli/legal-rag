# Context Engine — Overview

## Purpose

Evolve the current multi-agent orchestrator into a **Context Engine** — a two-phase (Plan → Execute) system that separates **knowledge** (factual data from uploaded files) from **context** (semantic blueprints: structured instructions that govern how answers are styled, formatted, and structured). The engine uses an LLM-powered Planner to dynamically generate execution plans, an Executor to carry them out, and a Tracer to record every step.

## Design Principles

- **DP-CE-001: Knowledge ≠ Context** — Factual data (uploaded files) and procedural blueprints (semantic instructions) are stored in strictly separated namespaces within the same vector index. They are never mixed during retrieval.
- **DP-CE-002: Plan Before Execute** — Every user goal is first decomposed into a structured JSON plan by an LLM. No specialist agent is invoked without a plan step.
- **DP-CE-003: Intent vs. Topic** — The Planner decomposes each user goal into an `intent_query` (desired style/structure → ContextLibrary) and a `topic_query` (subject matter → KnowledgeStore).
- **DP-CE-004: Blueprint = Description + Content** — Only the blueprint's intent description is embedded. The full blueprint content (JSON) is stored separately and linked by ID. Searches match on intent; full content is loaded on retrieval.
- **DP-CE-005: Stateful Execution** — Agent outputs chain into subsequent agent inputs via `$$STEP_N_OUTPUT$$` placeholders resolved at runtime.
- **DP-CE-006: MCP Everywhere** — All inter-agent communication uses MCP (Model Context Protocol). No direct function imports between agents.
- **DP-CE-007: Observable by Default** — Every plan step, agent invocation, and dependency resolution is recorded in an ExecutionTrace with timing and status.
- **DP-CE-008: Backward Compatibility** — The REST API contract does not change. Existing frontend code works without modification. The Context Engine is an internal refactor of the orchestration layer.
- **DP-CE-009: Graceful Degradation** — If the ContextLibrary has no matching blueprint, the Writer falls back to its default system prompt (current behavior). The system never fails because a blueprint is missing.
- **DP-CE-010: Separation of Concerns** — The Agent Registry exposes only specialist agents (Researcher, Summarizer) as plannable capabilities. Infrastructure components (Librarian, Writer) are invoked directly by the Executor as fixed pipeline stages, not selected by the Planner.
- **DP-CE-011: Least Privilege Planning** — The Planner sees only what it needs to reason about. It does not see infrastructure internals (storage, generation) — only the specialist agents whose selection and ordering require strategic reasoning.
- **DP-CE-012: Idempotent Operations** — Blueprint CRUD, ingestion, and deletion are idempotent. Retrying a failed operation produces the same result as a successful first attempt.
- **DP-CE-013: Fail Fast, Recover Gracefully** — Validate inputs at every boundary (API, Planner, Executor, agent). On validation failure, reject immediately with a clear error. On runtime failure, degrade gracefully where possible.

## Constraints

- C-CE-001: All agents run in-process within the FastAPI application.
- C-CE-002: MCP is the only communication mechanism between agents.
- C-CE-003: A single MongoDB vector search index with two namespaces (`KnowledgeStore`, `ContextLibrary`) distinguished by a `namespace` field on each document.
- C-CE-004: Blueprint content is stored in a `blueprints` MongoDB collection, not in the vector index.
- C-CE-005: The Planner uses the LLM to generate execution plans. Plans are JSON arrays of steps.
- C-CE-006: The Executor resolves inter-step dependencies before invoking each agent.
- C-CE-007: The Tracer logs every step but never blocks execution.
- C-CE-008: Only Researcher and Summarizer are registered in the Agent Registry as plannable capabilities. Librarian (storage/retrieval) and Writer (generation) are fixed infrastructure invoked directly by the Executor.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                   │
│  Receives user goal, auth context, conversation history  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   CONTEXT ENGINE                         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Planner                                          │   │
│  │  ├─ Consults Agent Registry (Researcher,          │   │
│  │  │  Summarizer)                                   │   │
│  │  ├─ Sends goal + capabilities to LLM              │   │
│  │  └─ Returns structured ExecutionPlan              │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │  Executor                                         │   │
│  │  ├─ Fixed: Librarian.search(ContextLibrary)       │   │
│  │  ├─ Planned: Researcher / Summarizer (from plan)  │   │
│  │  ├─ Fixed: Writer.generate (final stage)          │   │
│  │  └─ Resolves $$STEP_N_OUTPUT$$ dependencies       │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │  Tracer                                           │   │
│  │  └─ Logs every step: timing, status, I/O summary  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
└──────────────────────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌─────────┐  ┌───────────┐  ┌──────────┐
   │ Vector DB│  │    LLM    │  │ MongoDB  │
   │(chunks)  │  │ (OpenAI)  │  │(blueprints│
   └─────────┘  └───────────┘  └──────────┘
```

## Data Model

### Two Input Sources

| Source | Description | Embedding Strategy | Namespace |
|--------|-------------|-------------------|-----------|
| Knowledge Data | Factual content from uploaded files (PDF, TXT, DOCX) | Full text chunks embedded | `KnowledgeStore` |
| Context Data | Semantic blueprints — structured instructions for style, format, structure | Only the intent description is embedded | `ContextLibrary` |

### Vector Index Namespaces

A single vector search index (`vector_index`) with a `namespace` field used as a filter:

| Namespace | Contents | Embedded Text | Linked Data |
|-----------|----------|---------------|-------------|
| `KnowledgeStore` | Factual document chunks | Chunk text | — |
| `ContextLibrary` | Blueprint intent descriptions | Description text | Full blueprint JSON (in `blueprints` collection) |

### Blueprint Storage

```
blueprints collection:
{
  "_id": ObjectId,
  "blueprint_id": str,          // unique identifier
  "name": str,                  // human-readable name
  "description": str,           // intent description (this gets embedded)
  "content": dict,              // full blueprint JSON (instructions, structure, style rules)
  "user_id": str,               // owner
  "org_id": str,                // organization scope
  "created_at": datetime,
  "updated_at": datetime
}

chunks collection (ContextLibrary entries):
{
  "chunk_id": str,              // = blueprint_id for ContextLibrary entries
  "doc_id": str,                // = blueprint_id
  "namespace": "ContextLibrary",
  "user_id": str,
  "org_id": str,
  "text": str,                  // = description (embedded text)
  "embedding": [float],
  "metadata": {
    "source": str,              // blueprint name
    "blueprint_id": str,        // link to blueprints collection
    "namespace": "ContextLibrary"
  }
}

chunks collection (KnowledgeStore entries — existing):
{
  "chunk_id": str,
  "doc_id": str,
  "namespace": "KnowledgeStore",
  "user_id": str,
  "org_id": str,
  "text": str,
  "embedding": [float],
  "metadata": { ... }
}
```

## Agent Registry — Plannable Agents Only

The Agent Registry is a runtime catalog of **specialist agents** whose selection and ordering require strategic reasoning by the Planner. Infrastructure components (Librarian, Writer) are **not** in the registry — they are fixed pipeline stages invoked directly by the Executor.

### Rationale

The Planner's job is to decide *what information to gather and how to process it*. It does not decide *where to store/retrieve data* (Librarian) or *how to render the final output* (Writer) — those are fixed infrastructure concerns:

| Component | Role | In Registry? | Why |
|-----------|------|:------------:|-----|
| **Researcher** | Retrieves and synthesizes factual information, providing source citations | ✅ Yes | The Planner decides *what* to research and *when* |
| **Summarizer** | Reduces large text to a concise summary based on an objective | ✅ Yes | The Planner decides *if* and *when* summarization is needed |
| **Librarian** | Storage and retrieval infrastructure (vector search, ingestion, deletion) | ❌ No | Fixed infrastructure — always called the same way |
| **Writer** | Final answer generation from context + blueprint | ❌ No | Fixed final stage — always the last step |

### Registry Contents

```python
{
  "researcher": {
    "description": "Retrieves and synthesizes factual information, providing source citations.",
    "tools": ["researcher.research"]
  },
  "summarizer": {
    "description": "Reduces a large text to a concise summary based on an objective.",
    "tools": ["summarizer.summarize"]
  }
}
```

## Orchestrator Architecture

The Orchestrator contains three internal modules:

| Module | Role |
|--------|------|
| **Planner** | Strategic core. Receives the user's goal, consults the Agent Registry for available specialist capabilities, sends goal + capabilities to the LLM, receives a structured JSON execution plan. |
| **Executor** | Operational manager. Executes fixed infrastructure steps (Librarian search, Writer generation) and planned specialist steps (Researcher, Summarizer) in sequence, resolving inter-step dependencies. |
| **Tracer** | Transparent recorder. Logs every step (start, end, duration, status, input/output summaries) for debugging and observability. |

## Query Flow (Context Engine)

```
User Goal
     │
     ▼
┌──────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                        │
│                                                        │
│  Phase 1: PLANNING                                     │
│  ├─ Create ExecutionTrace                              │
│  ├─ AgentRegistry.get_capabilities_description()       │
│  │   → returns Researcher + Summarizer capabilities    │
│  ├─ LLM(goal + capabilities) → ExecutionPlan           │
│  │   → intent_query, topic_query, specialist steps     │
│  │                                                     │
│  Phase 2: EXECUTION                                    │
│  ├─ FIXED: Librarian.search(intent_query,              │
│  │         namespace=ContextLibrary)                   │
│  │   → retrieve semantic blueprint (if available)      │
│  ├─ PLANNED: Execute specialist steps from plan        │
│  │   ├─ Researcher.research(topic_query, ...)          │
│  │   ├─ Summarizer.summarize(...) (if in plan)         │
│  │   └─ resolve $$STEP_N_OUTPUT$$ between steps        │
│  ├─ FIXED: Writer.generate(facts + blueprint)          │
│  │   → final answer using facts as content,            │
│  │     blueprint as structural instructions            │
│  │                                                     │
│  Phase 3: FINALIZATION                                 │
│  └─ trace.finalize() → log status + total duration     │
│     return structured output                           │
└────────────────────────────────────────────────────────┘
```

### Execution Order

The Executor follows a fixed three-stage pipeline with planned steps in the middle:

```
Stage 1 (Fixed):    Librarian → ContextLibrary search → blueprint (or null)
Stage 2 (Planned):  Specialist agents from plan (Researcher, Summarizer, etc.)
Stage 3 (Fixed):    Writer → generate answer using facts + blueprint
```

This ensures:
- Blueprint retrieval always happens first (so the Writer always has it).
- Specialist agent ordering is dynamic (Planner decides).
- Answer generation always happens last.

### Typical Plan for a Query

The Planner generates a plan for the **specialist steps only** (Stage 2). The Executor wraps it with fixed stages:

```json
{
  "intent_query": "executive summary with risk highlights",
  "topic_query": "liability clauses in the uploaded contract",
  "steps": [
    {
      "step_id": 1,
      "agent": "researcher",
      "tool": "researcher.research",
      "inputs": {
        "question": "liability clauses in the uploaded contract",
        "user_id": "$$USER_ID$$",
        "history": "$$HISTORY$$",
        "document_ids": "$$DOCUMENT_IDS$$"
      },
      "description": "Retrieve and synthesize factual context about liability clauses",
      "depends_on": []
    }
  ]
}
```

A more complex plan might include summarization:

```json
{
  "intent_query": "concise bullet-point analysis",
  "topic_query": "all termination provisions across uploaded documents",
  "steps": [
    {
      "step_id": 1,
      "agent": "researcher",
      "tool": "researcher.research",
      "inputs": {
        "question": "all termination provisions across uploaded documents",
        "user_id": "$$USER_ID$$",
        "history": "$$HISTORY$$",
        "document_ids": "$$DOCUMENT_IDS$$"
      },
      "description": "Retrieve factual context about termination provisions",
      "depends_on": []
    },
    {
      "step_id": 2,
      "agent": "summarizer",
      "tool": "summarizer.summarize",
      "inputs": {
        "text": "$$STEP_1_OUTPUT.chunks_text$$",
        "objective": "termination provisions and their conditions",
        "max_length": 800
      },
      "description": "Summarize the retrieved provisions into a concise overview",
      "depends_on": [1]
    }
  ]
}
```

### Dependency Resolution

The Executor replaces placeholders before invoking each step:

| Placeholder | Resolved To |
|-------------|-------------|
| `$$USER_ID$$` | Current user's ID from request context |
| `$$ORG_ID$$` | Current user's organization ID |
| `$$HISTORY$$` | Conversation history from request |
| `$$DOCUMENT_IDS$$` | Document scope from request |
| `$$ORIGINAL_GOAL$$` | The user's original question |
| `$$STEP_N_OUTPUT$$` | Full output of step N |
| `$$STEP_N_OUTPUT.field$$` | Specific field from step N's output |

## Impact on Existing Agents

| Agent | Changes |
|-------|---------|
| **Librarian** | Add `namespace` filter to search. Add blueprint retrieval (search ContextLibrary → load full blueprint from `blueprints` collection). Add blueprint CRUD tools. Not in Agent Registry. |
| **Researcher** | Unchanged internally. Registered in Agent Registry as a plannable specialist. |
| **Writer** | Accept optional `blueprint` parameter. When present, use blueprint as structural/style instructions instead of default system prompt. Not in Agent Registry. |
| **Summarizer** | Unchanged internally. Registered in Agent Registry as a plannable specialist. |
| **Orchestrator** | Major refactor — replace direct agent calls with Planner → Executor → Tracer pipeline. |

## What Does NOT Change

- REST API endpoints, paths, request/response schemas.
- Authentication, JWT, refresh token rotation.
- Upload API, background ingestion trigger.
- Frontend routing, pages, i18n structure.
- Existing KnowledgeStore data and vector search index structure.
- Existing test suite (all tests continue to pass with KnowledgeStore namespace default).

## New API Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/blueprints` | Yes | Create a semantic blueprint |
| `GET` | `/api/blueprints` | Yes | List user/org blueprints (paginated) |
| `GET` | `/api/blueprints/{id}` | Yes | Get blueprint details |
| `PUT` | `/api/blueprints/{id}` | Yes | Update a blueprint |
| `DELETE` | `/api/blueprints/{id}` | Yes | Delete a blueprint and its vector entry |

## New Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PLANNER_MODEL` | `gpt-4o` | LLM model for plan generation |
| `PLANNER_TIMEOUT` | `15` | Planner LLM call timeout (seconds) |
| `ENABLE_CONTEXT_ENGINE` | `true` | Feature flag — when false, use legacy direct orchestration |
| `DEFAULT_NAMESPACE` | `KnowledgeStore` | Default namespace for backward compatibility |
