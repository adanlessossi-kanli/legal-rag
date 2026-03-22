# Context Engine — Agent Changes

## Agent Classification

| Agent | Classification | In Registry? | Invoked By |
|-------|---------------|:------------:|------------|
| Librarian | Fixed infrastructure | ❌ | Executor (Stage 1 — blueprint retrieval, direct calls for ingest/remove) |
| Researcher | Plannable specialist | ✅ | Executor (Stage 2 — from plan) |
| Summarizer | Plannable specialist | ✅ | Executor (Stage 2 — from plan, if Planner includes it) |
| Writer | Fixed infrastructure | ❌ | Executor (Stage 3 — always the final step) |

---

## REQ-CE-AG-001: Librarian — Namespace-Aware Search

### Current Behavior

`librarian.search` queries the `chunks` collection filtered by `user_id`/`org_id`/`document_ids`.

### New Behavior

`librarian.search` gains a `namespace` parameter to distinguish between KnowledgeStore and ContextLibrary searches:

```json
{
  "name": "librarian.search",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "minLength": 1, "maxLength": 5000 },
      "user_id": { "type": "string", "minLength": 1 },
      "namespace": {
        "type": "string",
        "enum": ["KnowledgeStore", "ContextLibrary"],
        "default": "KnowledgeStore"
      },
      "document_ids": { "type": "array", "items": { "type": "string" }, "maxItems": 50 },
      "org_id": { "type": "string" },
      "top_k": { "type": "integer", "minimum": 1, "maximum": 20, "default": 5 }
    },
    "required": ["query", "user_id"]
  }
}
```

### Search Logic Change

The `namespace` filter is added to the scope filter in `vectorstore.py`:

```python
def _build_scope_filter(user_id, document_ids, org_id, namespace="KnowledgeStore"):
    f = {"namespace": namespace}  # always filter by namespace
    if org_id:
        f["org_id"] = org_id
    elif user_id:
        f["user_id"] = user_id
    if document_ids:
        f["doc_id"] = {"$in": document_ids}
    return f
```

### ContextLibrary Search: Blueprint Retrieval

When `namespace="ContextLibrary"`, after retrieving matching vector entries, the Librarian loads the full blueprint content from the `blueprints` collection:

```python
async def _search(self, params):
    tool = "librarian.search"
    # ... existing validation ...
    namespace = params.get("namespace", "KnowledgeStore")

    if namespace not in ("KnowledgeStore", "ContextLibrary"):
        raise AgentError("VALIDATION_ERROR", "namespace must be KnowledgeStore or ContextLibrary", self.name, tool)

    chunks = await retrieve(query, user_id, document_ids, org_id, namespace=namespace)

    if namespace == "ContextLibrary" and chunks:
        blueprint_id = chunks[0]["metadata"].get("blueprint_id")
        if blueprint_id:
            blueprint = await self._load_blueprint(blueprint_id)
            return {"chunks": chunks, "blueprint": blueprint}

    return {"chunks": chunks}
```

```python
async def _load_blueprint(self, blueprint_id: str) -> dict | None:
    db = get_db()
    doc = await db.blueprints.find_one({"blueprint_id": blueprint_id})
    if not doc:
        self.logger.warning("Blueprint %s not found in blueprints collection", blueprint_id)
        return None
    return {
        "blueprint_id": doc["blueprint_id"],
        "name": doc["name"],
        "description": doc["description"],
        "content": doc["content"],
    }
```

### Backward Compatibility

- `namespace` defaults to `"KnowledgeStore"` — all existing callers (Researcher) work without changes.
- The Researcher never passes `namespace` explicitly, so it always searches KnowledgeStore.
- Only the Executor's Stage 1 passes `namespace="ContextLibrary"`.

---

## REQ-CE-AG-002: Librarian — Blueprint CRUD Tools

New MCP tools for blueprint lifecycle management. These are called by the API layer (via Orchestrator direct calls), not by the Planner.

### `librarian.create_blueprint`

```json
{
  "name": "librarian.create_blueprint",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": { "type": "string", "minLength": 1, "maxLength": 255 },
      "description": { "type": "string", "minLength": 1, "maxLength": 2000 },
      "content": { "type": "object" },
      "user_id": { "type": "string", "minLength": 1 },
      "org_id": { "type": "string" }
    },
    "required": ["name", "description", "content", "user_id"]
  }
}
```

Logic:
1. Validate inputs (name length, description length, user_id non-empty).
2. Generate `blueprint_id` = `"bp_" + uuid4().hex[:12]`.
3. Check uniqueness: `(user_id, name)` pair must not already exist. If org_id is set, check `(org_id, name)` instead.
4. Insert into `blueprints` collection with `created_at` and `updated_at` timestamps.
5. Embed the `description` text via `_embed([description])`.
6. Insert vector entry into `chunks` collection with `namespace: "ContextLibrary"`, `chunk_id: blueprint_id`, `doc_id: blueprint_id`.
7. Return `{ "blueprint_id": str }`.
8. On failure: clean up partial state (delete blueprint doc if vector insert fails, and vice versa).

### `librarian.update_blueprint`

```json
{
  "name": "librarian.update_blueprint",
  "inputSchema": {
    "type": "object",
    "properties": {
      "blueprint_id": { "type": "string", "minLength": 1 },
      "name": { "type": "string", "minLength": 1, "maxLength": 255 },
      "description": { "type": "string", "minLength": 1, "maxLength": 2000 },
      "content": { "type": "object" },
      "user_id": { "type": "string", "minLength": 1 }
    },
    "required": ["blueprint_id", "user_id"]
  }
}
```

Logic:
1. Load existing blueprint. If not found → `AgentError("NOT_FOUND", ...)`.
2. Verify ownership: `user_id` matches, or `org_id` matches and user is a member.
3. Build update dict from provided fields only (partial update).
4. Set `updated_at` timestamp.
5. If `description` changed:
   - Delete old vector entry: `chunks.delete_one({"chunk_id": blueprint_id, "namespace": "ContextLibrary"})`.
   - Re-embed new description.
   - Insert new vector entry.
6. Update `blueprints` document.
7. Return `{ "updated": true }`.

### `librarian.delete_blueprint`

```json
{
  "name": "librarian.delete_blueprint",
  "inputSchema": {
    "type": "object",
    "properties": {
      "blueprint_id": { "type": "string", "minLength": 1 },
      "user_id": { "type": "string", "minLength": 1 }
    },
    "required": ["blueprint_id", "user_id"]
  }
}
```

Logic:
1. Load existing blueprint. If not found → return `{ "deleted": true }` (idempotent).
2. Verify ownership.
3. Delete from `blueprints` collection.
4. Delete vector entry from `chunks` where `chunk_id == blueprint_id` and `namespace == "ContextLibrary"`.
5. Return `{ "deleted": true }`.

### Best Practices Applied

- **Idempotent deletes**: Deleting a non-existent blueprint succeeds silently.
- **Partial updates**: Only provided fields are updated; omitted fields are unchanged.
- **Atomic-ish operations**: On create failure, partial state is cleaned up. On update, vector re-embedding only happens if description actually changed.
- **Ownership validation**: Every mutation verifies the caller owns the blueprint.

---

## REQ-CE-AG-003: Librarian — Ingestion Namespace Tagging

The `librarian.ingest` tool tags all chunks with `namespace: "KnowledgeStore"`:

```python
async def _ingest(self, params):
    # ... existing logic ...
    for c in chunks:
        c.metadata["user_id"] = user_id
        c.metadata["namespace"] = "KnowledgeStore"
        if org_id:
            c.metadata["org_id"] = org_id
    await store_chunks(chunks)
```

The `store_chunks` function in `vectorstore.py` includes `namespace` in the MongoDB document:

```python
docs = [
    {
        "chunk_id": c.chunk_id,
        "doc_id": c.metadata.get("doc_id", ""),
        "namespace": c.metadata.get("namespace", "KnowledgeStore"),
        "user_id": c.metadata.get("user_id", ""),
        "org_id": c.metadata.get("org_id", ""),
        "text": c.text,
        "embedding": emb,
        "metadata": c.metadata,
    }
    for c, emb in zip(batch, embeddings)
]
```

---

## REQ-CE-AG-004: Researcher — Registered Specialist, No Internal Changes

### Registry Entry

```python
AgentCapability(
    name="researcher",
    description="Retrieves and synthesizes factual information, providing source citations.",
    tools=["researcher.research"],
)
```

### Internal Behavior

The Researcher is unchanged internally:
1. Rewrites follow-up queries (if history exists).
2. Calls `librarian.search` — which now defaults to `namespace: "KnowledgeStore"` (no explicit namespace passed by Researcher).
3. Summarizes long contexts via Summarizer (if threshold exceeded).

The Researcher does **not** interact with the ContextLibrary. Blueprint retrieval is handled by the Executor's fixed Stage 1.

### Why Researcher Is Plannable

The Planner decides:
- *What* topic to research (the `topic_query` it extracts from the user's goal).
- *When* to research (always first in the plan, but the Planner confirms this).
- *What document scope* to apply.

---

## REQ-CE-AG-005: Summarizer — Registered Specialist, No Internal Changes

### Registry Entry

```python
AgentCapability(
    name="summarizer",
    description="Reduces a large text to a concise summary based on an objective.",
    tools=["summarizer.summarize"],
)
```

### Internal Behavior

The Summarizer is unchanged. It condenses text focused on a specific objective using `gpt-4o-mini`.

### Why Summarizer Is Plannable

The Planner decides:
- *If* summarization is needed (based on the user's goal — e.g., "give me a brief overview" implies summarization).
- *What objective* to focus the summary on.
- *When* in the pipeline to summarize (after research, before writing).

Note: The Researcher also calls the Summarizer internally when retrieved context exceeds the threshold. This is an internal optimization, separate from the Planner's strategic use of the Summarizer.

---

## REQ-CE-AG-006: Writer — Blueprint-Aware Generation (Fixed Infrastructure)

### Classification

The Writer is **not** in the Agent Registry. It is a fixed Stage 3 component invoked directly by the Executor after all planned steps complete.

### Current Behavior

The Writer always uses a hardcoded `SYSTEM_PROMPT` for legal assistant behavior.

### New Behavior

The Writer accepts an optional `blueprint` parameter. When present, the blueprint's content augments the system prompt with style, structure, and constraint instructions.

### Updated Tool Schema

```json
{
  "name": "writer.generate",
  "inputSchema": {
    "type": "object",
    "properties": {
      "question": { "type": "string", "minLength": 1, "maxLength": 5000 },
      "chunks": { "type": "array", "items": { "type": "object" }, "minItems": 1, "maxItems": 20 },
      "blueprint": {
        "type": ["object", "null"],
        "description": "Optional semantic blueprint with style/structure instructions",
        "properties": {
          "blueprint_id": { "type": "string" },
          "name": { "type": "string" },
          "description": { "type": "string" },
          "content": { "type": "object" }
        }
      },
      "history": { "type": "array" },
      "stream": { "type": "boolean", "default": false }
    },
    "required": ["question", "chunks"]
  }
}
```

### Prompt Construction

Blueprint content uses a flexible schema with fields like `scene_goal`, `style_guide`, `structure`, `participants`, and `instruction`. The Writer maps these into the system prompt:

```python
def _build_system_prompt(self, blueprint: dict | None) -> str:
    if not blueprint or not blueprint.get("content"):
        return SYSTEM_PROMPT  # default legal assistant prompt

    content = blueprint["content"]
    parts = [SYSTEM_PROMPT]  # always include base prompt

    if content.get("scene_goal"):
        parts.append(f"\nGoal: {content['scene_goal']}")
    if content.get("style_guide"):
        parts.append(f"\nStyle guide: {content['style_guide']}")
    if content.get("structure"):
        sections = ", ".join(content["structure"])
        parts.append(f"\nStructure your response with these sections: {sections}")
    if content.get("participants"):
        roles = "; ".join(f"{p['role']}: {p['description']}" for p in content["participants"])
        parts.append(f"\nParticipants: {roles}")
    if content.get("instruction"):
        parts.append(f"\nInstruction: {content['instruction']}")

    return "\n".join(parts)
```

This approach is forward-compatible: unknown fields in `content` are silently ignored. New blueprint types can add new fields without requiring Writer changes.

### Implementation Change

```python
async def _generate(self, params: dict) -> dict:
    tool = "writer.generate"
    self._validate_required(params, ["question", "chunks"], tool)

    question = params["question"]
    chunks = params["chunks"]
    history_raw = params.get("history", [])
    stream = params.get("stream", False)
    blueprint = params.get("blueprint")  # NEW — optional

    # ... existing validation ...

    history = [ChatMessage(role=h["role"], content=h["content"]) for h in history_raw]

    # Build system prompt — blueprint-aware
    system_prompt = self._build_system_prompt(blueprint)

    try:
        if stream:
            return {"stream": generate_stream(question, chunks, history, system_prompt=system_prompt)}
        answer = await generate(question, chunks, history, system_prompt=system_prompt)
        return {"answer": answer}
    except AgentError:
        raise
    except Exception as e:
        raise AgentError("LLM_ERROR", f"Generation failed: {e}", self.name, tool, retryable=not stream) from e
```

### Changes to `rag/llm.py`

The `generate`, `generate_stream`, and `_build_messages` functions gain an optional `system_prompt` parameter:

```python
def _build_messages(question, chunks, history, system_prompt=None):
    prompt = system_prompt or SYSTEM_PROMPT
    # ... rest unchanged, using `prompt` instead of hardcoded SYSTEM_PROMPT ...

async def generate(question, chunks, history, system_prompt=None):
    messages = _build_messages(question, chunks, history, system_prompt=system_prompt)
    # ... rest unchanged ...

async def generate_stream(question, chunks, history, system_prompt=None):
    messages = _build_messages(question, chunks, history, system_prompt=system_prompt)
    # ... rest unchanged ...
```

### Fallback

If `blueprint` is `None`, empty, or has no `content`, the Writer uses the default `SYSTEM_PROMPT` — identical to current behavior.

### Best Practices Applied

- **Base prompt always included**: The blueprint augments the base legal assistant prompt, never replaces it. This ensures citation behavior and grounding are always enforced.
- **Defensive parsing**: Each blueprint content field is checked individually. Missing fields are silently skipped.
- **No injection risk**: Blueprint content fields are interpolated into a structured prompt template, not concatenated as raw user input.

---

## REQ-CE-AG-007: MCP Tool Summary (Updated)

### Infrastructure Tools (Fixed Pipeline)

| Agent | Tool | Stage | Description |
|-------|------|:-----:|-------------|
| Librarian | `librarian.search` | 1 | Namespace-aware semantic search (KnowledgeStore or ContextLibrary) |
| Librarian | `librarian.ingest` | — | Ingest document (tags with KnowledgeStore namespace) |
| Librarian | `librarian.remove` | — | Remove document chunks |
| Librarian | `librarian.create_blueprint` | — | Create blueprint + embed description in ContextLibrary |
| Librarian | `librarian.update_blueprint` | — | Update blueprint + re-embed if description changed |
| Librarian | `librarian.delete_blueprint` | — | Delete blueprint + vector entry |
| Writer | `writer.generate` | 3 | Generate answer (optionally blueprint-guided) |

### Specialist Tools (Plannable via Agent Registry)

| Agent | Tool | Stage | Description |
|-------|------|:-----:|-------------|
| Researcher | `researcher.research` | 2 | Retrieves and synthesizes factual information with source citations |
| Summarizer | `summarizer.summarize` | 2 | Reduces large text to a concise summary based on an objective |
