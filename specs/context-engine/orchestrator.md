# Context Engine — Orchestrator (Planner, Executor, Tracer)

## REQ-CE-ORC-001: Orchestrator Refactor

The Orchestrator is refactored from a direct agent-caller into a three-module engine with a fixed-stage pipeline:

```
┌──────────────────────────────────────────────────────┐
│                    Orchestrator                        │
│                                                        │
│  ┌──────────┐   ┌──────────────┐   ┌────────┐        │
│  │  Planner  │   │   Executor   │   │ Tracer │        │
│  └────┬─────┘   └──────┬───────┘   └───┬────┘        │
│       │                 │               │              │
│       │  Agent Registry │               │              │
│       │  (Researcher,   │               │              │
│       │   Summarizer)   │               │              │
│       └──────┬──────────┘               │              │
│              │                          │              │
│  ┌───────────▼──────────────────────────▼───────────┐ │
│  │              Execution Pipeline                    │ │
│  │                                                    │ │
│  │  Stage 1 (Fixed):  Librarian → ContextLibrary     │ │
│  │  Stage 2 (Planned): Researcher / Summarizer       │ │
│  │  Stage 3 (Fixed):  Writer → generate answer       │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Interface (unchanged public API)

```python
class Orchestrator:
    def __init__(
        self,
        planner: Planner,
        executor: Executor,
        agent_registry: AgentRegistry,
        librarian: LibrarianAgent,
        researcher: ResearcherAgent,
        writer: WriterAgent,
        summarizer: SummarizerAgent,
    ): ...

    # Public API — signatures unchanged from current implementation
    async def query(question, history, user_id, document_ids, on_status, org_id) -> (answer, sources, no_context)
    async def query_stream(question, history, user_id, document_ids, on_status, org_id) -> (token_gen, sources, no_context)
    async def ingest(file_path, original_name, doc_id, content_hash, user_id, org_id) -> int
    async def remove_document(doc_id) -> None
    async def summarize(text, objective, max_length) -> str
    async def health_check() -> dict
```

---

## REQ-CE-ORC-002: Agent Registry

The Agent Registry is a runtime catalog of **plannable specialist agents only**. Infrastructure components (Librarian, Writer) are not registered — they are fixed pipeline stages.

### Interface

```python
@dataclass
class AgentCapability:
    name: str               # agent name
    description: str        # what this agent does (shown to Planner LLM)
    tools: list[str]        # MCP tool names

class AgentRegistry:
    def register(self, name: str, agent: BaseAgent, capability: AgentCapability) -> None
    def get_handler(self, agent_name: str) -> BaseAgent
    def get_capabilities_description(self) -> str   # formatted for LLM prompt
    def list_agents(self) -> list[AgentCapability]
    def has_agent(self, name: str) -> bool
```

### Registration (at startup)

```python
registry = AgentRegistry()

registry.register("researcher", researcher, AgentCapability(
    name="researcher",
    description="Retrieves and synthesizes factual information, providing source citations.",
    tools=["researcher.research"],
))

registry.register("summarizer", summarizer, AgentCapability(
    name="summarizer",
    description="Reduces a large text to a concise summary based on an objective.",
    tools=["summarizer.summarize"],
))
```

### `get_capabilities_description()` Output

Returns a formatted string for the Planner's LLM prompt:

```
Available specialist agents:

1. researcher
   Description: Retrieves and synthesizes factual information, providing source citations.
   Tools: researcher.research

2. summarizer
   Description: Reduces a large text to a concise summary based on an objective.
   Tools: summarizer.summarize
```

### Why Only Two Agents?

| Component | Plannable? | Reason |
|-----------|:----------:|--------|
| Researcher | ✅ | The Planner decides *what topic to research* and *when* |
| Summarizer | ✅ | The Planner decides *if* summarization is needed and *what objective* to focus on |
| Librarian | ❌ | Fixed infrastructure — blueprint retrieval (Stage 1) and factual storage are deterministic, not strategic |
| Writer | ❌ | Fixed final stage — always the last step, always receives facts + blueprint |

### Validation

- `get_handler(name)` raises `AgentError("VALIDATION_ERROR", f"Unknown agent: {name}")` if the agent is not registered.
- `register` raises `ValueError` if an agent with the same name is already registered (fail-fast at startup).

---

## REQ-CE-ORC-003: Planner

### Responsibility

The Planner is the strategic core. It receives the user's goal, consults the Agent Registry for available specialist capabilities, and uses an LLM to generate a structured execution plan for the specialist steps (Stage 2 of the pipeline).

The Planner does **not** plan Stage 1 (blueprint retrieval) or Stage 3 (answer generation) — those are fixed.

### Interface

```python
class Planner:
    def __init__(self, registry: AgentRegistry): ...

    async def plan(self, goal: str, context: PlanContext) -> ExecutionPlan
```

### `PlanContext`

```python
@dataclass
class PlanContext:
    user_id: str
    org_id: str | None
    history: list[dict]
    document_ids: list[str] | None
    stream: bool
    has_blueprints: bool          # whether user/org has any blueprints in ContextLibrary
```

### `ExecutionPlan`

```python
@dataclass
class PlanStep:
    step_id: int
    agent: str                    # must exist in Agent Registry
    tool: str                     # MCP tool name on that agent
    inputs: dict                  # tool parameters (may contain $$PLACEHOLDERS$$)
    description: str              # human-readable step description
    depends_on: list[int] = []    # step_ids this step depends on

@dataclass
class ExecutionPlan:
    goal: str                     # original user goal
    intent_query: str | None      # extracted intent (for ContextLibrary)
    topic_query: str | None       # extracted topic (for KnowledgeStore)
    steps: list[PlanStep]         # specialist steps only (Stage 2)
```

### Planning Logic

1. Get capabilities via `registry.get_capabilities_description()`.
2. Build the planning prompt (see below).
3. Call LLM (`settings.planner_model`, temperature=0, `response_format={"type": "json_object"}`).
4. Parse the JSON response into an `ExecutionPlan`.
5. **Validate the plan:**
   - All referenced agents exist in the registry.
   - All `depends_on` references point to valid `step_id` values.
   - No circular dependencies (topological sort check).
   - At least one step exists.
   - `intent_query` and `topic_query` are non-empty strings (or null for intent_query).
6. Return the validated plan.
7. On any failure (LLM error, parse error, validation error): log warning, return fallback plan.

### Planning Prompt

```
You are a task planner for a legal document analysis system. Given a user's goal and a list of available specialist agents, produce a JSON execution plan.

YOUR JOB:
- Analyze the user's goal and decompose it into:
  - intent_query: The desired output style or structure (e.g., "executive summary", "bullet-point comparison", "formal legal memo"). Set to null if the goal implies no specific style.
  - topic_query: The factual subject matter to research (e.g., "liability clauses", "termination provisions").
- Select which specialist agents to invoke and in what order.
- Define the inputs for each step, using $$PLACEHOLDER$$ syntax for dynamic values.

AVAILABLE PLACEHOLDERS:
- $$USER_ID$$, $$ORG_ID$$: User and organization identifiers.
- $$HISTORY$$: Conversation history.
- $$DOCUMENT_IDS$$: Document scope filter (may be null).
- $$ORIGINAL_GOAL$$: The user's original question.
- $$STEP_N_OUTPUT$$: Full output of step N.
- $$STEP_N_OUTPUT.field$$: A specific field from step N's output.

CONSTRAINTS:
- You may ONLY use the specialist agents listed below. Do not reference any other agents.
- Each step must have: step_id (int, starting at 1), agent (str), tool (str), inputs (dict), description (str), depends_on (list[int]).
- The researcher agent should almost always be included to retrieve factual context.
- The summarizer agent should only be included when the goal explicitly or implicitly requires condensing large amounts of information.

AVAILABLE SPECIALIST AGENTS:
{capabilities}

USER CONTEXT:
- Goal: {goal}
- Has blueprints: {has_blueprints}
- Has conversation history: {has_history}
- Has document scope: {has_document_ids}

Respond with ONLY a JSON object:
{{
  "intent_query": "string or null",
  "topic_query": "string",
  "steps": [...]
}}
```

### Fallback Plan

If the LLM fails to produce a valid plan, or if `settings.enable_context_engine` is `false`, the Planner returns a hardcoded fallback plan:

```json
{
  "intent_query": null,
  "topic_query": "<original question>",
  "steps": [
    {
      "step_id": 1,
      "agent": "researcher",
      "tool": "researcher.research",
      "inputs": {
        "question": "$$ORIGINAL_GOAL$$",
        "user_id": "$$USER_ID$$",
        "history": "$$HISTORY$$",
        "document_ids": "$$DOCUMENT_IDS$$"
      },
      "description": "Retrieve factual context",
      "depends_on": []
    }
  ]
}
```

This fallback mirrors the current system behavior: research only, no blueprint, Writer uses default prompt.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PLANNER_MODEL` | `gpt-4o` | LLM for plan generation |
| `PLANNER_TIMEOUT` | `15` | Timeout in seconds |
| `ENABLE_CONTEXT_ENGINE` | `true` | Feature flag |

---

## REQ-CE-ORC-004: Executor

### Responsibility

The Executor carries out the full three-stage pipeline:

1. **Stage 1 (Fixed):** Librarian searches ContextLibrary for a matching blueprint.
2. **Stage 2 (Planned):** Specialist agents from the plan are invoked in order, with dependency resolution.
3. **Stage 3 (Fixed):** Writer generates the final answer using retrieved facts + blueprint.

### Interface

```python
class Executor:
    def __init__(
        self,
        registry: AgentRegistry,
        librarian: LibrarianAgent,
        writer: WriterAgent,
    ): ...

    async def execute(
        self,
        plan: ExecutionPlan,
        context: PlanContext,
        on_status: StatusCallback,
        tracer: ExecutionTrace,
    ) -> ExecutorResult
```

### `ExecutorResult`

```python
@dataclass
class ExecutorResult:
    answer: str | None                    # final answer (non-streaming)
    stream: AsyncGenerator[str, None] | None  # token stream (streaming)
    sources: list[Source]
    no_context: bool
    blueprint_used: str | None            # blueprint_id if one was applied
```

### Execution Logic

```python
async def execute(self, plan, context, on_status, tracer):
    step_outputs = {}
    request_context = {
        "USER_ID": context.user_id,
        "ORG_ID": context.org_id or "",
        "HISTORY": context.history,
        "DOCUMENT_IDS": context.document_ids,
        "ORIGINAL_GOAL": plan.goal,
    }

    # ── Stage 1 (Fixed): Blueprint retrieval ──
    blueprint = None
    if plan.intent_query and context.has_blueprints:
        tracer.log_step_start(PlanStep(0, "librarian", "librarian.search", {}, "Blueprint retrieval"))
        await on_status("librarian", "working")
        try:
            result = await self._librarian.call_tool("librarian.search", {
                "query": plan.intent_query,
                "user_id": context.user_id,
                "org_id": context.org_id,
                "namespace": "ContextLibrary",
                "top_k": 1,
            })
            blueprint = result.get("blueprint")
            tracer.log_step_complete(0, f"blueprint={'found' if blueprint else 'none'}")
        except Exception as e:
            # Graceful degradation: no blueprint is not fatal
            tracer.log_step_failed(0, str(e))
            logger.warning("Blueprint retrieval failed, continuing without blueprint", exc_info=True)

    # ── Stage 2 (Planned): Specialist agents ──
    for step in plan.steps:
        tracer.log_step_start(step)
        await on_status(step.agent, "working")

        resolved_inputs = self._resolve_dependencies(
            step.inputs, step_outputs, request_context
        )

        agent = self._registry.get_handler(step.agent)

        try:
            result = await agent.call_tool(step.tool, resolved_inputs)
            step_outputs[step.step_id] = result
            tracer.log_step_complete(step.step_id, _summarize(result))
        except Exception as e:
            tracer.log_step_failed(step.step_id, str(e))
            raise

    # ── Short-circuit: no factual context ──
    researcher_output = self._find_researcher_output(step_outputs, plan)
    chunks = researcher_output.get("chunks", []) if researcher_output else []

    if not chunks:
        return ExecutorResult(
            answer=NO_CONTEXT_ANSWER, stream=None,
            sources=[], no_context=True, blueprint_used=None,
        )

    sources = self._build_sources(chunks)

    # ── Stage 3 (Fixed): Writer generation ──
    await on_status("writer", "working")
    writer_inputs = {
        "question": plan.goal,
        "chunks": chunks,
        "history": context.history,
        "stream": context.stream,
    }
    if blueprint:
        writer_inputs["blueprint"] = blueprint

    tracer.log_step_start(PlanStep(-1, "writer", "writer.generate", {}, "Answer generation"))
    writer_result = await self._writer.call_tool("writer.generate", writer_inputs)
    tracer.log_step_complete(-1, "generation complete")

    if context.stream:
        return ExecutorResult(
            answer=None, stream=writer_result["stream"],
            sources=sources, no_context=False,
            blueprint_used=blueprint["blueprint_id"] if blueprint else None,
        )

    return ExecutorResult(
        answer=writer_result["answer"], stream=None,
        sources=sources, no_context=False,
        blueprint_used=blueprint["blueprint_id"] if blueprint else None,
    )
```

### Dependency Resolution

```python
def _resolve_dependencies(self, inputs: dict, step_outputs: dict, request_context: dict) -> dict:
    resolved = {}
    for key, value in inputs.items():
        if isinstance(value, str) and value.startswith("$$") and value.endswith("$$"):
            resolved[key] = self._resolve_placeholder(value, step_outputs, request_context)
        else:
            resolved[key] = value
    return resolved

def _resolve_placeholder(self, placeholder: str, step_outputs: dict, request_context: dict) -> Any:
    inner = placeholder[2:-2]  # strip $$

    # Request context placeholders
    if inner in request_context:
        return request_context[inner]

    # Step output placeholders: STEP_N_OUTPUT or STEP_N_OUTPUT.field
    match = re.match(r"STEP_(\d+)_OUTPUT(?:\.(.+))?", inner)
    if match:
        step_id = int(match.group(1))
        field = match.group(2)
        if step_id not in step_outputs:
            raise AgentError("VALIDATION_ERROR", f"Step {step_id} has no output yet", "executor", "resolve")
        output = step_outputs[step_id]
        if field:
            return output[field]
        return output

    raise AgentError("VALIDATION_ERROR", f"Unknown placeholder: {placeholder}", "executor", "resolve")
```

### Best Practices Applied

- **Fail-fast validation**: Placeholders referencing non-existent steps raise immediately, not silently return None.
- **Graceful degradation**: Blueprint retrieval failure (Stage 1) logs a warning and continues without a blueprint.
- **Short-circuit**: If Researcher returns no chunks, Writer is never called — avoids wasting an LLM call.
- **Single responsibility**: The Executor only executes. It does not plan, log, or build API responses.

---

## REQ-CE-ORC-005: Tracer

### Responsibility

The Tracer is the flight recorder. It logs every step for debugging and observability. It never blocks execution.

### Interface

```python
class ExecutionTrace:
    def __init__(self, trace_id: str, goal: str): ...

    def log_step_start(self, step: PlanStep) -> None
    def log_step_complete(self, step_id: int, output_summary: str) -> None
    def log_step_failed(self, step_id: int, error: str) -> None
    def log_step_skipped(self, step_id: int, reason: str) -> None
    def finalize(self, status: str = "completed") -> None
    def to_dict(self) -> dict

    @property
    def entries(self) -> list[TraceEntry]
    @property
    def total_duration_ms(self) -> float | None
```

### `TraceEntry`

```python
@dataclass
class TraceEntry:
    step_id: int
    agent: str
    tool: str
    status: str                       # "started" | "completed" | "failed" | "skipped"
    started_at: float                 # time.time()
    completed_at: float | None = None
    duration_ms: float | None = None
    input_summary: str = ""           # truncated, no sensitive data
    output_summary: str | None = None # truncated to 200 chars
    error: str | None = None
```

### Behavior

- `log_step_start`: Records `started_at`, agent, tool. Logs at INFO level.
- `log_step_complete`: Records `completed_at`, `duration_ms`, `output_summary` (truncated to 200 chars). Logs at INFO level.
- `log_step_failed`: Records error message. Logs at ERROR level.
- `log_step_skipped`: Records reason (e.g., "short-circuited: no context"). Logs at INFO level.
- `finalize`: Records final `status` ("completed" | "failed"), `completed_at`, `total_duration_ms`. Logs at INFO level with full trace summary.
- All logging uses structured format consistent with the existing `LOG_FORMAT` setting.

### Logging Format

```
context_engine trace_id=abc123 step=0 agent=librarian tool=librarian.search status=completed duration_ms=245.3
context_engine trace_id=abc123 step=1 agent=researcher tool=researcher.research status=completed duration_ms=1203.7
context_engine trace_id=abc123 step=-1 agent=writer tool=writer.generate status=completed duration_ms=3421.1
context_engine trace_id=abc123 status=completed total_duration_ms=4870.1 steps=3
```

Step ID conventions:
- `0` = Stage 1 (blueprint retrieval)
- `1..N` = Stage 2 (planned specialist steps)
- `-1` = Stage 3 (writer generation)

### Trace Storage

Traces are logged but **not persisted to MongoDB** by default. A future enhancement can add trace persistence for analytics. The `to_dict()` method enables serialization if needed.

### Best Practices Applied

- **Non-blocking**: Tracer methods never raise exceptions. Logging failures are swallowed with a stderr fallback.
- **No sensitive data**: `input_summary` and `output_summary` are truncated and never contain full question text, user data, or document content.
- **Correlation**: `trace_id` is the request's `X-Request-ID` header value, enabling end-to-end tracing.

---

## REQ-CE-ORC-006: Query Flow (Full)

### Non-Streaming

```python
async def query(self, question, history, user_id, document_ids, on_status, org_id):
    status = on_status or _noop

    try:
        return await asyncio.wait_for(
            self._do_query(question, history, user_id, document_ids, status, org_id, stream=False),
            timeout=OVERALL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise AgentError("INTERNAL_ERROR", "Query timed out", "orchestrator", "query")

async def _do_query(self, question, history, user_id, document_ids, status, org_id, stream):
    trace = ExecutionTrace(trace_id=_get_request_id(), goal=question)

    # Phase 1: Plan
    await status("planner", "working")
    context = PlanContext(
        user_id=user_id,
        org_id=org_id,
        history=[{"role": m.role, "content": m.content} for m in history],
        document_ids=document_ids,
        stream=stream,
        has_blueprints=await self._has_blueprints(user_id, org_id),
    )
    plan = await self._planner.plan(question, context)

    # Phase 2: Execute
    result = await self._executor.execute(plan, context, status, trace)

    # Phase 3: Finalize
    trace.finalize("completed")
    await status("done", "done")

    return result.answer or NO_CONTEXT_ANSWER, result.sources, result.no_context
```

### Streaming

Same flow, but `stream=True`. The Executor returns an `ExecutorResult` with a `stream` generator. The Orchestrator wraps it:

```python
async def query_stream(self, question, history, user_id, document_ids, on_status, org_id):
    # ... same planning + execution ...
    result = await self._executor.execute(plan, context, status, trace)

    if result.no_context:
        await status("done", "done")
        return None, [], True

    async def _wrapped_stream():
        async for token in result.stream:
            yield token
        trace.finalize("completed")
        await status("done", "done")

    return _wrapped_stream(), result.sources, False
```

---

## REQ-CE-ORC-007: Ingest / Remove / Summarize

These operations bypass the Planner (no strategic reasoning needed) and call agents directly:

- `ingest` → `librarian.ingest` (direct MCP call)
- `remove_document` → `librarian.remove` (direct MCP call)
- `summarize` → `summarizer.summarize` (direct MCP call)

The Tracer still logs these calls for consistency, using a simplified single-step trace.

---

## REQ-CE-ORC-008: Feature Flag

When `ENABLE_CONTEXT_ENGINE` is `false`:
- The Planner returns the hardcoded fallback plan (no LLM call, no `intent_query`).
- Stage 1 (blueprint retrieval) is skipped entirely.
- Stage 2 runs the fallback plan (Researcher only).
- Stage 3 runs the Writer with default system prompt.
- Behavior is identical to the current system.

This allows gradual rollout and instant rollback.

---

## REQ-CE-ORC-009: `_has_blueprints` Check

Before planning, the Orchestrator checks if the user/org has any blueprints:

```python
async def _has_blueprints(self, user_id: str, org_id: str | None) -> bool:
    db = get_db()
    query = {"org_id": org_id} if org_id else {"user_id": user_id}
    count = await db.blueprints.count_documents(query, limit=1)
    return count > 0
```

This is a fast `limit=1` count — not a full collection scan. If no blueprints exist, the Planner knows not to generate an `intent_query`, and Stage 1 is skipped.
