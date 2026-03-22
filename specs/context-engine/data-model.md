# Context Engine — Data Model

## REQ-CE-DM-001: Namespace Separation

All vectors in the `chunks` collection are tagged with a `namespace` field:

| Namespace | Value | Description |
|-----------|-------|-------------|
| KnowledgeStore | `"KnowledgeStore"` | Factual document chunks from uploaded files |
| ContextLibrary | `"ContextLibrary"` | Blueprint intent descriptions |

### Migration

Existing chunks (uploaded documents) receive `namespace: "KnowledgeStore"` via a database migration. All new chunks are tagged at ingestion time.

### Vector Search Index Update

The `vector_index` must add `namespace` as a filter field:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1536,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "user_id"
    },
    {
      "type": "filter",
      "path": "org_id"
    },
    {
      "type": "filter",
      "path": "doc_id"
    },
    {
      "type": "filter",
      "path": "namespace"
    }
  ]
}
```

## REQ-CE-DM-002: Blueprint Schema

### `blueprints` Collection

Blueprints use a flexible content schema. The `description` field captures the blueprint's intent (this is what gets embedded for semantic search). The `content` field stores the full blueprint as a JSON object — its internal structure varies by blueprint type.

```python
{
  "_id": ObjectId,
  "blueprint_id": str,        # unique identifier (e.g. "blueprint_suspense_narrative")
  "name": str,                # human-readable name, max 255 chars
  "description": str,         # intent description — THIS is what gets embedded
  "content": {                # full blueprint — structured instructions (flexible schema)
    "scene_goal": str,        # the goal of the output
    "style_guide": str,       # style and tone instructions
    "structure": [str],       # optional: ordered sections for the output
    "participants": [dict],   # optional: roles involved in the output
    "instruction": str,       # the core instruction for the Writer
    ...                       # extensible — any additional fields
  },
  "user_id": str,             # owner ("system" for default blueprints)
  "org_id": str,              # organization scope (empty if global/personal)
  "is_default": bool,         # true for system-provided seed blueprints
  "created_at": datetime,
  "updated_at": datetime
}
```

### Indexes on `blueprints`

```python
async def up(db):
    await db.blueprints.create_index("blueprint_id", unique=True)
    await db.blueprints.create_index("user_id")
    await db.blueprints.create_index("org_id")
    await db.blueprints.create_index("is_default")
```

### Pydantic Schemas

```python
class BlueprintCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    content: dict                     # flexible JSON — validated at application level

class BlueprintUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, min_length=1, max_length=2000)
    content: dict | None = None

class BlueprintResponse(BaseModel):
    blueprint_id: str
    name: str
    description: str
    content: dict
    is_default: bool = False
    created_at: str
    updated_at: str
```

## REQ-CE-DM-003: ContextLibrary Vector Entry

When a blueprint is created or updated, its description is embedded and stored in the `chunks` collection with `namespace: "ContextLibrary"`:

```python
{
  "chunk_id": blueprint_id,           # same as blueprint_id
  "doc_id": blueprint_id,             # same as blueprint_id
  "namespace": "ContextLibrary",
  "user_id": user_id,
  "org_id": org_id,
  "text": description,                # the intent description
  "embedding": [float],               # embedding of description
  "metadata": {
    "source": name,
    "blueprint_id": blueprint_id,
    "namespace": "ContextLibrary"
  }
}
```

On blueprint update: delete old vector entry, insert new one (re-embed the updated description).
On blueprint delete: delete the vector entry and the blueprint document.

## REQ-CE-DM-004: KnowledgeStore Chunk Entry (Updated)

Existing chunk schema gains the `namespace` field:

```python
{
  "chunk_id": str,
  "doc_id": str,
  "namespace": "KnowledgeStore",      # NEW — added to all existing and new chunks
  "user_id": str,
  "org_id": str,
  "text": str,
  "embedding": [float],
  "metadata": {
    "source": str,
    "doc_id": str,
    "page": int,
    "namespace": "KnowledgeStore"     # also in metadata for convenience
  }
}
```

## REQ-CE-DM-005: Execution Plan Schema

The Planner produces and the Executor consumes this structure. Plan steps reference only **plannable specialist agents** (Researcher, Summarizer) — never infrastructure components (Librarian, Writer).

```python
class PlanStep(BaseModel):
    step_id: int
    agent: str                        # must exist in Agent Registry (researcher | summarizer)
    tool: str                         # MCP tool name on that agent
    inputs: dict                      # tool parameters (may contain $$PLACEHOLDERS$$)
    description: str                  # human-readable step description
    depends_on: list[int] = []        # step_ids this step depends on

class ExecutionPlan(BaseModel):
    goal: str                         # original user goal
    intent_query: str | None = None   # extracted intent (for ContextLibrary — used by Executor Stage 1)
    topic_query: str | None = None    # extracted topic (for KnowledgeStore — used in specialist steps)
    steps: list[PlanStep]             # specialist steps only (Executor Stage 2)
```

## REQ-CE-DM-006: Execution Trace Schema

```python
class TraceEntry(BaseModel):
    step_id: int
    agent: str
    tool: str
    status: str                       # "started" | "completed" | "failed" | "skipped"
    started_at: float                 # time.time()
    completed_at: float | None = None
    duration_ms: float | None = None
    input_summary: str                # truncated input for logging (no sensitive data)
    output_summary: str | None = None # truncated output
    error: str | None = None

class ExecutionTrace(BaseModel):
    trace_id: str                     # correlation ID from request
    goal: str
    plan: ExecutionPlan
    entries: list[TraceEntry] = []
    status: str = "running"           # "running" | "completed" | "failed"
    started_at: float
    completed_at: float | None = None
    total_duration_ms: float | None = None

    def log_step_start(self, step: PlanStep) -> None: ...
    def log_step_complete(self, step_id: int, output_summary: str) -> None: ...
    def log_step_failed(self, step_id: int, error: str) -> None: ...
    def finalize(self, status: str) -> None: ...
```

## REQ-CE-DM-007: Default Seed Blueprints

The system ships with three default blueprints that are inserted into the ContextLibrary on first startup (via migration). These are available to all users and demonstrate the blueprint system's capabilities.

Default blueprints have `user_id: "system"`, `org_id: ""`, and `is_default: true`. They are globally visible to all users during ContextLibrary searches.

### Seed Data

```python
import json

DEFAULT_BLUEPRINTS = [
    {
        "blueprint_id": "blueprint_suspense_narrative",
        "name": "Suspense Narrative",
        "description": (
            "A precise Semantic Blueprint designed to generate suspenseful and tense "
            "narratives, suitable for children's stories. Focuses on atmosphere, "
            "perceived threats, and emotional impact. Ideal for creative writing."
        ),
        "content": {
            "scene_goal": "Increase tension and create suspense.",
            "style_guide": (
                "Use short, sharp sentences. Focus on sensory details (sounds, shadows). "
                "Maintain a slightly eerie but age-appropriate tone."
            ),
            "participants": [
                {"role": "Agent", "description": "The protagonist experiencing the events."},
                {"role": "Source_of_Threat", "description": "The underlying danger or mystery."},
            ],
            "instruction": (
                "Rewrite the provided facts into a narrative adhering strictly "
                "to the scene_goal and style_guide."
            ),
        },
    },
    {
        "blueprint_id": "blueprint_technical_explanation",
        "name": "Technical Explanation",
        "description": (
            "A Semantic Blueprint designed for technical explanation or analysis. "
            "This blueprint focuses on clarity, objectivity, and structure. Ideal for "
            "breaking down complex processes, explaining mechanisms, or summarizing "
            "scientific findings."
        ),
        "content": {
            "scene_goal": "Explain the mechanism or findings clearly and concisely.",
            "style_guide": (
                "Maintain an objective and formal tone. Use precise terminology. "
                "Prioritize factual accuracy and clarity over narrative flair."
            ),
            "structure": ["Definition", "Function/Operation", "Key Findings/Impact"],
            "instruction": (
                "Organize the provided facts into the defined structure, "
                "adhering to the style_guide."
            ),
        },
    },
    {
        "blueprint_id": "blueprint_casual_summary",
        "name": "Casual Summary",
        "description": (
            "A goal-oriented context for creating a casual, easy-to-read summary. "
            "Focuses on brevity and accessibility, explaining concepts simply."
        ),
        "content": {
            "scene_goal": "Summarize information quickly and casually.",
            "style_guide": (
                "Use informal language. Keep it brief and engaging. "
                "Imagine explaining it to a friend."
            ),
            "instruction": "Summarize the provided facts using the casual style guide.",
        },
    },
]
```

### Visibility Rules

Default blueprints are visible to all users during ContextLibrary searches. The scope filter for ContextLibrary searches is extended:

```python
def _build_scope_filter(user_id, document_ids, org_id, namespace="KnowledgeStore"):
    f = {"namespace": namespace}
    if namespace == "ContextLibrary":
        # Include default blueprints (user_id="system") alongside user/org blueprints
        scope_conditions = [{"user_id": "system"}]  # always include defaults
        if org_id:
            scope_conditions.append({"org_id": org_id})
        if user_id:
            scope_conditions.append({"user_id": user_id})
        f["$or"] = scope_conditions
    else:
        if org_id:
            f["org_id"] = org_id
        elif user_id:
            f["user_id"] = user_id
    if document_ids:
        f["doc_id"] = {"$in": document_ids}
    return f
```

### Protection

- Default blueprints (`is_default: true`) cannot be updated or deleted via the API.
- The `PUT /api/blueprints/{id}` and `DELETE /api/blueprints/{id}` endpoints return 403 for default blueprints.

---

## REQ-CE-DM-008: Database Migration

Migration file: `backend/migrations/versions/YYYYMMDD_HHMMSS_add_context_engine.py`

The migration performs three operations:
1. Tag existing chunks with `namespace: "KnowledgeStore"`.
2. Create `blueprints` collection indexes.
3. Seed the default blueprints and their ContextLibrary vector entries.

```python
from datetime import datetime, timezone

async def up(db):
    # 1. Add namespace field to all existing chunks
    await db.chunks.update_many(
        {"namespace": {"$exists": False}},
        {"$set": {"namespace": "KnowledgeStore"}}
    )

    # 2. Create blueprints collection indexes
    await db.blueprints.create_index("blueprint_id", unique=True)
    await db.blueprints.create_index("user_id")
    await db.blueprints.create_index("org_id")
    await db.blueprints.create_index("is_default")

    # 3. Seed default blueprints (idempotent — skip if already exist)
    from app.engine.seed import seed_default_blueprints
    await seed_default_blueprints(db)
```

### Seed Function

`backend/app/engine/seed.py`:

```python
from datetime import datetime, timezone
from app.rag.vectorstore import _embed

DEFAULT_BLUEPRINTS = [...]  # as defined above

async def seed_default_blueprints(db):
    """Insert default blueprints and their vector entries. Idempotent."""
    now = datetime.now(timezone.utc)

    for bp in DEFAULT_BLUEPRINTS:
        # Skip if already seeded
        exists = await db.blueprints.find_one({"blueprint_id": bp["blueprint_id"]})
        if exists:
            continue

        # Insert blueprint document
        await db.blueprints.insert_one({
            "blueprint_id": bp["blueprint_id"],
            "name": bp["name"],
            "description": bp["description"],
            "content": bp["content"],
            "user_id": "system",
            "org_id": "",
            "is_default": True,
            "created_at": now,
            "updated_at": now,
        })

        # Embed description and insert vector entry
        embedding = (await _embed([bp["description"]]))[0]
        await db.chunks.insert_one({
            "chunk_id": bp["blueprint_id"],
            "doc_id": bp["blueprint_id"],
            "namespace": "ContextLibrary",
            "user_id": "system",
            "org_id": "",
            "text": bp["description"],
            "embedding": embedding,
            "metadata": {
                "source": bp["name"],
                "blueprint_id": bp["blueprint_id"],
                "namespace": "ContextLibrary",
            },
        })
```

### Idempotency

The seed function checks for existing `blueprint_id` before inserting. Running the migration multiple times is safe — already-seeded blueprints are skipped.

### `_has_blueprints` Update

Since default blueprints exist for all users, the Orchestrator's `_has_blueprints` check should always return `true` when defaults are seeded:

```python
async def _has_blueprints(self, user_id: str, org_id: str | None) -> bool:
    db = get_db()
    # Check for user/org blueprints OR default blueprints
    query = {"$or": [
        {"user_id": "system", "is_default": True},
        {"user_id": user_id},
    ]}
    if org_id:
        query["$or"].append({"org_id": org_id})
    return await db.blueprints.count_documents(query, limit=1) > 0
```

Note: The vector search index must be manually updated (or recreated via `scripts/create_vector_index.py`) to include the `namespace` filter field.
