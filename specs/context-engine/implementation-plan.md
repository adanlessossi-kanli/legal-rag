# Context Engine — Implementation Plan

## Phase 1: Foundation (Namespace + Config)

Add the `namespace` field to the data layer and configuration. No behavioral changes — all defaults preserve current behavior.

### Files to Modify
- `backend/app/core/config.py` — add `planner_model`, `planner_timeout`, `enable_context_engine`, `default_namespace`
- `backend/app/rag/vectorstore.py` — add `namespace` parameter to `_build_scope_filter`, `_vector_search`, `_keyword_search`, `retrieve`, `store_chunks`
- `scripts/create_vector_index.py` — add `namespace` filter field to vector index definition

### Files to Create
- `backend/migrations/versions/YYYYMMDD_HHMMSS_add_context_engine.py` — migration: set `namespace: "KnowledgeStore"` on existing chunks, create `blueprints` indexes, seed default blueprints
- `backend/app/engine/__init__.py`
- `backend/app/engine/seed.py` — default blueprint definitions + idempotent seed function

### Validation
- All existing tests pass (namespace defaults to `KnowledgeStore`).
- Migration runs against local MongoDB without errors.
- Default blueprints seeded (3 blueprints in `blueprints` collection, 3 vector entries in `chunks` with `namespace: ContextLibrary`).
- Re-running migration is safe (idempotent seed).
- Vector index recreated with `namespace` filter field.

---

## Phase 2: Blueprint Storage + Librarian CRUD

Add the `blueprints` collection, Librarian blueprint tools, and the blueprint API.

### Files to Create
- `backend/app/api/blueprints.py` — CRUD endpoints for blueprints
- `backend/tests/test_blueprints.py` — blueprint API tests
- `backend/tests/test_namespaces.py` — namespace isolation tests

### Files to Modify
- `backend/app/models/schemas.py` — add `BlueprintCreate`, `BlueprintUpdate`, `BlueprintResponse` (flexible `content: dict`)
- `backend/app/agents/librarian.py` — add `namespace` to `_search`, add `_load_blueprint`, add `create_blueprint`, `update_blueprint`, `delete_blueprint` tools (with `is_default` protection), tag ingested chunks with `namespace: "KnowledgeStore"`
- `backend/main.py` — register blueprint routes

### Validation
- Blueprint CRUD works via API (create, read, update, delete).
- `librarian.search` with `namespace=ContextLibrary` returns blueprint entries (including defaults).
- `librarian.search` with `namespace=KnowledgeStore` (or default) returns only document chunks.
- Default blueprints cannot be updated or deleted via API (403).
- Namespace isolation confirmed: blueprints never appear in KnowledgeStore searches and vice versa.

---

## Phase 3: Context Engine Core (Registry, Planner, Executor, Tracer)

Build the engine modules. No integration with the Orchestrator yet — tested in isolation.

### Files to Create
- `backend/app/engine/registry.py` — `AgentRegistry`, `AgentCapability` (registers Researcher + Summarizer only)
- `backend/app/engine/planner.py` — `Planner`, `PlanContext`, `ExecutionPlan`, `PlanStep`, planning prompt, fallback plan
- `backend/app/engine/executor.py` — `Executor`, `ExecutorResult`, dependency resolution, three-stage pipeline (Librarian → planned steps → Writer)
- `backend/app/engine/tracer.py` — `ExecutionTrace`, `TraceEntry`
- `backend/tests/test_agent_registry.py`
- `backend/tests/test_planner.py`
- `backend/tests/test_executor.py`
- `backend/tests/test_tracer.py`

### Validation
- Agent Registry registers only Researcher and Summarizer; rejects unknown agents.
- Planner generates valid plans from mocked LLM responses; falls back on failure.
- Executor resolves `$$STEP_N_OUTPUT$$` dependencies correctly.
- Executor runs three-stage pipeline: Stage 1 (Librarian) → Stage 2 (planned) → Stage 3 (Writer).
- Executor short-circuits when Researcher returns no chunks.
- Tracer records all steps with timing and status.

---

## Phase 4: Orchestrator Refactor + Writer Blueprint Support

Wire the engine into the Orchestrator and add blueprint-aware generation to the Writer.

### Files to Modify
- `backend/app/agents/orchestrator.py` — refactor to use Planner → Executor → Tracer internally; keep public interface identical
- `backend/app/agents/writer.py` — accept optional `blueprint` parameter, add `_build_system_prompt` method
- `backend/app/rag/llm.py` — add optional `system_prompt` parameter to `generate`, `generate_stream`, `_build_messages`
- `backend/main.py` — initialize `AgentRegistry`, `Planner`, `Executor`, wire into Orchestrator at startup

### Files to Create
- `backend/tests/test_writer_blueprint.py` — Writer blueprint prompt construction tests

### Files to Modify (tests)
- `backend/tests/test_orchestrator.py` — add Context Engine flow tests alongside existing tests

### Validation
- All existing tests pass without modification.
- Chat flow works end-to-end with and without blueprints.
- Feature flag `ENABLE_CONTEXT_ENGINE=false` produces identical behavior to pre-refactor.
- Streaming works through the full pipeline.
- Blueprint content shapes the Writer's system prompt.

---

## Phase 5: Integration Testing + Documentation

End-to-end tests with real MongoDB and full pipeline validation.

### Files to Create
- `backend/tests/test_context_engine_integration.py` — full end-to-end tests with real MongoDB (`@pytest.mark.integration`)

### Files to Modify
- `README.md` — document Context Engine, blueprints, new config variables, new API endpoints
- `backend/.env.example` — add new environment variables

### Validation
- Upload document + create blueprint → query → answer follows blueprint style.
- Namespace isolation confirmed with real `$vectorSearch`.
- Trace output logged correctly with timing.
- Blueprint CRUD roundtrip works end-to-end.
- All existing tests still pass.

---

## File Structure (New/Modified)

```
backend/
├── app/
│   ├── engine/                          # NEW — Context Engine core
│   │   ├── __init__.py
│   │   ├── seed.py                      # Default blueprint definitions + seed function
│   │   ├── registry.py                  # AgentRegistry (Researcher + Summarizer)
│   │   ├── planner.py                   # Planner, PlanContext, ExecutionPlan
│   │   ├── executor.py                  # Executor, ExecutorResult, 3-stage pipeline
│   │   └── tracer.py                    # ExecutionTrace, TraceEntry
│   ├── agents/
│   │   ├── orchestrator.py              # MODIFIED — uses Planner/Executor/Tracer
│   │   ├── librarian.py                 # MODIFIED — namespace + blueprint CRUD
│   │   └── writer.py                    # MODIFIED — blueprint-aware prompts
│   ├── api/
│   │   └── blueprints.py                # NEW — blueprint CRUD endpoints
│   ├── core/
│   │   └── config.py                    # MODIFIED — new settings
│   ├── models/
│   │   └── schemas.py                   # MODIFIED — blueprint schemas
│   └── rag/
│       ├── vectorstore.py               # MODIFIED — namespace filter
│       └── llm.py                       # MODIFIED — optional system_prompt param
├── migrations/
│   └── versions/
│       └── YYYYMMDD_add_context_engine.py  # NEW
├── tests/
│   ├── test_agent_registry.py           # NEW
│   ├── test_planner.py                  # NEW
│   ├── test_executor.py                 # NEW
│   ├── test_tracer.py                   # NEW
│   ├── test_blueprints.py              # NEW
│   ├── test_namespaces.py              # NEW
│   ├── test_writer_blueprint.py        # NEW
│   ├── test_context_engine_integration.py  # NEW
│   ├── test_orchestrator.py             # MODIFIED — add context engine tests
│   └── test_writer.py                   # MODIFIED — verify backward compat
└── scripts/
    └── create_vector_index.py           # MODIFIED — add namespace filter
```

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| Planner LLM produces invalid plans | Medium | Low | Hardcoded fallback plan; plan validation before execution; feature flag |
| Planner adds latency to every query | Medium | Medium | Feature flag to disable; 15s timeout; fallback plan on timeout |
| Namespace migration breaks existing data | Low | High | Migration is additive (sets default); all queries default to KnowledgeStore; run migration in staging first |
| Blueprint search returns irrelevant match | Medium | Low | Cosine similarity threshold applies; Writer falls back to default prompt if no blueprint; only top-1 match used |
| Breaking existing tests | Low | High | All changes are additive; defaults preserve current behavior; feature flag for instant rollback |
| Writer prompt injection via blueprint content | Low | Medium | Blueprint fields are interpolated into structured template, not raw-concatenated; base legal prompt always included |
| Circular dependencies in plan | Low | Low | Topological sort validation in Planner; rejected plans fall back to default |

---

## Best Practices Checklist

- [x] **Feature flag** (`ENABLE_CONTEXT_ENGINE`) for gradual rollout and instant rollback
- [x] **Backward compatibility** — all defaults preserve current behavior; public API unchanged
- [x] **Separation of concerns** — Planner plans, Executor executes, Tracer traces; infrastructure (Librarian, Writer) separated from plannable specialists (Researcher, Summarizer)
- [x] **Graceful degradation** — blueprint retrieval failure is non-fatal; Planner failure falls back to hardcoded plan; Summarizer failure in Researcher is non-fatal
- [x] **Fail-fast validation** — plan validation rejects invalid agents, circular deps, empty steps before execution
- [x] **Idempotent operations** — blueprint delete is idempotent; chunk namespace migration is idempotent
- [x] **Observability** — ExecutionTrace logs every step with timing, status, and correlation ID
- [x] **Security** — blueprint ownership verified on every mutation; no prompt injection via structured template interpolation
- [x] **Testability** — each module (Registry, Planner, Executor, Tracer) is independently testable with mocks
- [x] **Phased rollout** — 5 phases, each independently deployable and testable
