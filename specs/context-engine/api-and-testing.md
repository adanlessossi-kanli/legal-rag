# Context Engine — API & Testing

## REQ-CE-API-001: Blueprint API Endpoints

### POST /api/blueprints

Create a semantic blueprint. The description is embedded into the ContextLibrary namespace.

```json
// Request
{
  "name": "Executive Summary",
  "description": "Generate a concise executive summary of legal findings with key risks highlighted",
  "content": {
    "style": "executive-summary",
    "structure": ["overview", "key_findings", "risk_assessment", "recommendations"],
    "constraints": ["max 800 words", "cite all sources", "highlight risks in bold"],
    "tone": "professional",
    "format": "markdown"
  }
}

// Response 201
{
  "blueprint_id": "bp_a1b2c3d4e5f6",
  "name": "Executive Summary",
  "description": "Generate a concise executive summary of legal findings with key risks highlighted",
  "content": { ... },
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

Validation:
- `name`: required, 1–255 chars, unique per user (or per org if org-scoped).
- `description`: required, 1–2000 chars.
- `content`: required, must be a valid JSON object.
- Duplicate `(user_id, name)` → 409 Conflict.

### GET /api/blueprints

List blueprints (paginated, scoped to user/org).

```json
// Response 200
{
  "blueprints": [
    {
      "blueprint_id": "bp_a1b2c3d4e5f6",
      "name": "Executive Summary",
      "description": "Generate a concise executive summary...",
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20
}
```

Query params: `page` (default 1), `page_size` (default 20, max 100).
Scoping: returns user's own blueprints + org blueprints (if user belongs to an org).
Note: `content` is omitted from list responses to reduce payload size.

### GET /api/blueprints/{id}

Get full blueprint details including `content`.

```json
// Response 200
{
  "blueprint_id": "bp_a1b2c3d4e5f6",
  "name": "Executive Summary",
  "description": "Generate a concise executive summary...",
  "content": { ... },
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

404 if not found or not accessible by the current user.

### PUT /api/blueprints/{id}

Partial update. Only provided fields are modified.

```json
// Request (partial)
{
  "description": "Updated intent description",
  "content": { "style": "bullet-points" }
}

// Response 200
{
  "blueprint_id": "bp_a1b2c3d4e5f6",
  "name": "Executive Summary",
  "description": "Updated intent description",
  "content": { "style": "bullet-points" },
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T11:00:00Z"
}
```

If `description` changes, the vector entry in ContextLibrary is re-embedded.
403 if not the owner or org admin.

### DELETE /api/blueprints/{id}

Delete a blueprint and its vector entry. Idempotent — 204 even if already deleted.

### Authorization

- All endpoints require JWT authentication.
- Blueprints are scoped: user sees own blueprints + org blueprints (if member).
- Only the creator or org admin can update/delete.
- Rate limiting: same as document endpoints.

---

## REQ-CE-API-002: Chat Endpoint — No Changes

The `POST /api/chat` endpoint is unchanged. The Context Engine operates internally:
- The Planner decides whether to extract an `intent_query` based on whether the user/org has blueprints.
- Blueprint selection is automatic (semantic match on intent via ContextLibrary search).
- No new request parameters needed.

Future enhancement: allow explicit `blueprint_id` in the chat request to force a specific blueprint.

---

## REQ-CE-API-003: SSE Events — New Agent Status

Streaming responses gain a new `planner` status event:

```
data: {"type": "agent_status", "agent": "planner", "status": "working"}
data: {"type": "agent_status", "agent": "librarian", "status": "working"}
data: {"type": "agent_status", "agent": "researcher", "status": "working"}
data: {"type": "sources", "sources": [...]}
data: {"type": "agent_status", "agent": "writer", "status": "working"}
data: {"type": "conversation_id", "conversation_id": "abc123"}
data: {"type": "token", "token": "According"}
data: {"type": "agent_status", "agent": "done", "status": "done"}
data: {"type": "done"}
```

The `planner` and `librarian` statuses are new. Frontend can display "Planning..." → "Loading blueprint..." → "Researching..." → "Writing...".

When `ENABLE_CONTEXT_ENGINE` is false, the `planner` and `librarian` events are not emitted (backward compatible).

---

## REQ-CE-API-004: Health Check — Extended

`GET /api/health?deep=true` includes Context Engine status:

```json
{
  "status": "ok",
  "checks": {
    "mongodb": "ok",
    "openai": "ok",
    "redis": "ok",
    "agents": {
      "librarian": "ok",
      "researcher": "ok",
      "writer": "ok",
      "summarizer": "ok"
    },
    "context_engine": {
      "enabled": true,
      "planner": "ok",
      "registry_agents": ["researcher", "summarizer"]
    }
  }
}
```

---

## REQ-CE-TEST-001: Unit Tests

### Agent Registry Tests (`test_agent_registry.py`)

| Test | Description |
|------|-------------|
| `test_register_and_get_handler` | Register Researcher, retrieve by name |
| `test_register_duplicate_raises` | Registering same name twice raises ValueError |
| `test_get_handler_unknown_raises` | Unknown agent name raises AgentError |
| `test_get_capabilities_description` | Returns formatted string with Researcher + Summarizer only |
| `test_list_agents` | Returns exactly 2 capabilities |
| `test_has_agent` | Returns True for registered, False for unregistered |

### Planner Tests (`test_planner.py`)

| Test | Description |
|------|-------------|
| `test_plan_basic_query` | Goal → plan with researcher step, intent_query, topic_query |
| `test_plan_with_blueprints` | `has_blueprints=True` → plan includes non-null `intent_query` |
| `test_plan_without_blueprints` | `has_blueprints=False` → `intent_query` is null |
| `test_plan_with_summarization` | Goal implying condensation → plan includes summarizer step |
| `test_plan_researcher_only` | Simple factual question → plan with researcher step only |
| `test_plan_fallback_on_llm_failure` | LLM error → returns hardcoded fallback plan |
| `test_plan_fallback_on_parse_error` | LLM returns invalid JSON → fallback plan |
| `test_plan_validation_rejects_unknown_agent` | Plan referencing "writer" (not in registry) is rejected → fallback |
| `test_plan_validation_rejects_circular_deps` | Circular `depends_on` → fallback |
| `test_plan_validation_rejects_empty_steps` | Empty steps array → fallback |
| `test_plan_feature_flag_disabled` | `ENABLE_CONTEXT_ENGINE=false` → always returns fallback, no LLM call |
| `test_plan_respects_timeout` | LLM call exceeding `PLANNER_TIMEOUT` → fallback |

### Executor Tests (`test_executor.py`)

| Test | Description |
|------|-------------|
| `test_execute_full_pipeline_with_blueprint` | Stage 1 finds blueprint → Stage 2 researcher → Stage 3 writer with blueprint |
| `test_execute_full_pipeline_without_blueprint` | No blueprints → Stage 1 skipped → Stage 2 → Stage 3 with default prompt |
| `test_execute_blueprint_retrieval_failure_degrades` | Stage 1 fails → continues without blueprint (graceful degradation) |
| `test_execute_no_blueprints_skips_stage1` | `has_blueprints=False` → Stage 1 not executed |
| `test_execute_no_intent_query_skips_stage1` | `intent_query=None` → Stage 1 not executed |
| `test_dependency_resolution_step_output` | `$$STEP_1_OUTPUT$$` resolves to step 1's full output |
| `test_dependency_resolution_nested_field` | `$$STEP_1_OUTPUT.chunks$$` resolves to the `chunks` field |
| `test_dependency_resolution_request_context` | `$$USER_ID$$`, `$$HISTORY$$` resolve correctly |
| `test_dependency_resolution_unknown_placeholder` | `$$UNKNOWN$$` raises AgentError |
| `test_dependency_resolution_missing_step` | `$$STEP_99_OUTPUT$$` raises AgentError |
| `test_short_circuit_no_context` | Researcher returns empty chunks → Writer not called, returns NO_CONTEXT_ANSWER |
| `test_step_failure_propagates` | Agent error in planned step → execution stops, trace records failure |
| `test_streaming_execution` | `stream=True` → Writer returns generator, wrapped correctly |
| `test_status_callbacks_emitted` | All stages emit correct on_status calls in order |

### Tracer Tests (`test_tracer.py`)

| Test | Description |
|------|-------------|
| `test_trace_records_all_steps` | All steps logged with timing |
| `test_trace_step_start_records_time` | `log_step_start` sets `started_at` |
| `test_trace_step_complete_records_duration` | `log_step_complete` calculates `duration_ms` |
| `test_trace_step_failed_records_error` | `log_step_failed` stores error message |
| `test_trace_step_skipped_records_reason` | `log_step_skipped` stores reason |
| `test_trace_finalize_completed` | `finalize("completed")` sets status and total duration |
| `test_trace_finalize_failed` | `finalize("failed")` records error status |
| `test_trace_to_dict` | Serializes correctly |
| `test_trace_output_summary_truncated` | Output summaries truncated to 200 chars |

### Blueprint Tests (`test_blueprints.py`)

| Test | Description |
|------|-------------|
| `test_create_blueprint` | Creates blueprint + vector entry in ContextLibrary |
| `test_create_blueprint_duplicate_name` | Same user + name → 409 Conflict |
| `test_create_blueprint_validates_name_length` | Name > 255 chars → 422 |
| `test_create_blueprint_validates_description_length` | Description > 2000 chars → 422 |
| `test_get_blueprint` | Returns full content |
| `test_get_blueprint_not_found` | Unknown ID → 404 |
| `test_get_blueprint_wrong_user` | Other user's blueprint → 404 |
| `test_update_blueprint_description` | Re-embeds vector entry |
| `test_update_blueprint_content_only` | No re-embedding (description unchanged) |
| `test_update_blueprint_partial` | Only provided fields updated |
| `test_update_blueprint_wrong_user` | Other user's blueprint → 403 |
| `test_update_default_blueprint_forbidden` | Default blueprint (`is_default=true`) → 403 |
| `test_delete_blueprint` | Removes blueprint + vector entry |
| `test_delete_blueprint_idempotent` | Deleting non-existent → 204 |
| `test_delete_default_blueprint_forbidden` | Default blueprint → 403 |
| `test_list_blueprints_user_scoped` | Returns user's blueprints |
| `test_list_blueprints_org_scoped` | Returns org blueprints for members |
| `test_list_blueprints_includes_defaults` | Default blueprints visible to all users |
| `test_list_blueprints_pagination` | Page/page_size params work |
| `test_list_blueprints_omits_content` | List response does not include `content` field |

### Default Blueprint Seed Tests (`test_seed.py`)

| Test | Description |
|------|-------------|
| `test_seed_inserts_three_defaults` | Seed function creates 3 blueprints + 3 vector entries |
| `test_seed_idempotent` | Running seed twice does not duplicate blueprints |
| `test_seed_blueprints_have_system_user` | All defaults have `user_id="system"` |
| `test_seed_blueprints_are_default` | All defaults have `is_default=True` |
| `test_seed_vector_entries_in_context_library` | Vector entries have `namespace="ContextLibrary"` |
| `test_seed_descriptions_are_embedded` | Vector entries have non-empty `embedding` arrays |

### Namespace Tests (`test_namespaces.py`)

| Test | Description |
|------|-------------|
| `test_search_knowledge_store_only` | `namespace=KnowledgeStore` returns only factual chunks |
| `test_search_context_library_only` | `namespace=ContextLibrary` returns only blueprint entries |
| `test_search_default_namespace` | No namespace param → defaults to KnowledgeStore |
| `test_search_invalid_namespace` | Invalid namespace value → validation error |
| `test_search_context_library_includes_defaults` | ContextLibrary search returns default blueprints for any user |
| `test_search_context_library_user_and_defaults` | ContextLibrary search returns both user blueprints and defaults |
| `test_ingest_tags_knowledge_store` | New ingested chunks have `namespace=KnowledgeStore` |
| `test_blueprint_create_tags_context_library` | New blueprint vector entry has `namespace=ContextLibrary` |
| `test_migration_tags_existing_chunks` | Existing chunks without namespace get `KnowledgeStore` |

### Writer Blueprint Tests (`test_writer_blueprint.py`)

| Test | Description |
|------|-------------|
| `test_generate_with_full_blueprint` | All blueprint fields (scene_goal, style_guide, structure, participants, instruction) shape the system prompt |
| `test_generate_with_partial_blueprint` | Blueprint with only `scene_goal` → only goal appended |
| `test_generate_with_suspense_blueprint` | Suspense narrative blueprint produces correct prompt structure |
| `test_generate_with_technical_blueprint` | Technical explanation blueprint includes structure sections |
| `test_generate_with_casual_blueprint` | Casual summary blueprint applies informal style |
| `test_generate_without_blueprint` | No blueprint → default system prompt (backward compat) |
| `test_generate_with_null_blueprint` | `blueprint=None` → default system prompt |
| `test_generate_with_empty_content` | `blueprint.content={}` → default system prompt |
| `test_base_prompt_always_included` | Blueprint augments but never replaces base legal prompt |
| `test_streaming_with_blueprint` | Blueprint applied in streaming mode too |

### Orchestrator Tests (`test_orchestrator.py` — updated)

| Test | Description |
|------|-------------|
| `test_query_full_flow_with_context_engine` | Plan → Execute → Finalize produces correct answer |
| `test_query_full_flow_feature_flag_disabled` | Fallback plan → same behavior as before |
| `test_query_with_blueprint_applied` | Blueprint found → Writer receives it |
| `test_query_without_blueprint` | No blueprints → Writer uses default prompt |
| `test_query_timeout` | Overall 90s timeout still enforced |
| `test_query_stream_with_context_engine` | Streaming works through the pipeline |
| `test_ingest_bypasses_planner` | Ingest calls Librarian directly |
| `test_remove_bypasses_planner` | Remove calls Librarian directly |
| `test_has_blueprints_check` | Returns True/False correctly |

---

## REQ-CE-TEST-002: Integration Tests

### Context Engine Integration (`test_context_engine_integration.py`)

Requires Docker (real MongoDB with `$vectorSearch`). Marked with `@pytest.mark.integration`.

| Test | Description |
|------|-------------|
| `test_full_query_with_default_blueprint` | Query matching a default blueprint → answer follows that blueprint's style |
| `test_full_query_with_user_blueprint` | Upload doc + create user blueprint → query → answer follows user blueprint |
| `test_full_query_without_matching_blueprint` | Query with no intent match → default system prompt |
| `test_blueprint_namespace_isolation` | Blueprint vectors don't appear in KnowledgeStore searches |
| `test_knowledge_namespace_isolation` | Document chunks don't appear in ContextLibrary searches |
| `test_plan_execute_trace_roundtrip` | Full plan → execute → trace with all steps logged |
| `test_blueprint_crud_roundtrip` | Create → read → update → delete blueprint |
| `test_blueprint_re_embedding_on_update` | Update description → old vector gone, new vector searchable |

---

## REQ-CE-TEST-003: Backward Compatibility Tests

| Test | Description |
|------|-------------|
| `test_existing_chat_flow_unchanged` | Current chat flow works identically with Context Engine enabled |
| `test_feature_flag_disabled_identical_behavior` | `ENABLE_CONTEXT_ENGINE=false` → identical to pre-Context Engine |
| `test_existing_tests_pass` | All existing test modules pass without modification |
| `test_researcher_default_namespace` | Researcher searches KnowledgeStore without explicit namespace |
| `test_writer_no_blueprint_default_prompt` | Writer without blueprint uses exact same prompt as before |
