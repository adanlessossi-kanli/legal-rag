"""
Context Engine: Executor unit tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.base import AgentError
from app.engine.executor import Executor, ExecutorResult, NO_CONTEXT_ANSWER
from app.engine.planner import ExecutionPlan, PlanContext, PlanStep
from app.engine.registry import AgentCapability, AgentRegistry
from app.engine.tracer import ExecutionTrace


def _make_registry():
    r = AgentRegistry()
    researcher = MagicMock()
    researcher.name = "researcher"
    researcher.call_tool = AsyncMock()
    summarizer = MagicMock()
    summarizer.name = "summarizer"
    summarizer.call_tool = AsyncMock()
    r.register("researcher", researcher, AgentCapability(name="researcher", description="", tools=["researcher.research"]))
    r.register("summarizer", summarizer, AgentCapability(name="summarizer", description="", tools=["summarizer.summarize"]))
    return r, researcher, summarizer


def _make_librarian():
    lib = MagicMock()
    lib.name = "librarian"
    lib.call_tool = AsyncMock()
    return lib


def _make_writer():
    w = MagicMock()
    w.name = "writer"
    w.call_tool = AsyncMock()
    return w


def _sample_chunks():
    return [
        {"chunk_id": "c1", "text": "Liability clause text", "metadata": {"source": "contract.pdf"}, "score": 0.9},
    ]


def _make_context(**overrides):
    defaults = dict(user_id="user1", org_id=None, history=[], document_ids=None, stream=False, has_blueprints=True)
    defaults.update(overrides)
    return PlanContext(**defaults)


def _make_plan(steps=None, intent_query=None, topic_query=None):
    if steps is None:
        steps = [PlanStep(step_id=1, agent="researcher", tool="researcher.research",
                          inputs={"question": "$$ORIGINAL_GOAL$$", "user_id": "$$USER_ID$$", "history": "$$HISTORY$$", "document_ids": "$$DOCUMENT_IDS$$"},
                          description="Retrieve context")]
    return ExecutionPlan(goal="What is liability?", intent_query=intent_query, topic_query=topic_query or "liability", steps=steps)


@pytest.fixture
def setup():
    registry, researcher, summarizer = _make_registry()
    librarian = _make_librarian()
    writer = _make_writer()
    executor = Executor(registry, librarian, writer)
    tracer = ExecutionTrace(trace_id="t1", goal="test")
    status_events = []

    async def on_status(agent, status):
        status_events.append((agent, status))

    return executor, librarian, writer, researcher, summarizer, tracer, on_status, status_events


# --- Stage 2 + 3: normal flow ---

async def test_execute_normal_flow(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, status_events = setup
    researcher.call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}
    writer.call_tool.return_value = {"answer": "The answer is..."}

    result = await executor.execute(_make_plan(), _make_context(), on_status, tracer)

    assert result.answer == "The answer is..."
    assert len(result.sources) == 1
    assert result.sources[0].document == "contract.pdf"
    assert not result.no_context
    assert ("researcher", "working") in status_events
    assert ("writer", "working") in status_events


# --- No context short-circuit ---

async def test_execute_no_context(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, status_events = setup
    researcher.call_tool.return_value = {"chunks": [], "rewritten_query": None}

    result = await executor.execute(_make_plan(), _make_context(), on_status, tracer)

    assert result.answer == NO_CONTEXT_ANSWER
    assert result.no_context is True
    assert result.sources == []
    writer.call_tool.assert_not_called()


# --- Stage 1: Blueprint retrieval ---

async def test_execute_with_blueprint(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, status_events = setup
    blueprint = {"blueprint_id": "bp_test", "name": "Test", "description": "desc", "content": {"scene_goal": "test"}}
    librarian.call_tool.return_value = {"chunks": [], "blueprint": blueprint}
    researcher.call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}
    writer.call_tool.return_value = {"answer": "styled answer"}

    plan = _make_plan(intent_query="formal memo")
    result = await executor.execute(plan, _make_context(), on_status, tracer)

    assert result.blueprint_used == "bp_test"
    # Verify blueprint was passed to writer
    writer_call = writer.call_tool.call_args[0][1]
    assert writer_call["blueprint"] == blueprint


async def test_execute_skips_blueprint_when_no_intent(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, status_events = setup
    researcher.call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}
    writer.call_tool.return_value = {"answer": "answer"}

    plan = _make_plan(intent_query=None)
    result = await executor.execute(plan, _make_context(), on_status, tracer)

    librarian.call_tool.assert_not_called()
    assert result.blueprint_used is None


async def test_execute_blueprint_failure_continues(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, status_events = setup
    librarian.call_tool.side_effect = Exception("ContextLibrary down")
    researcher.call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}
    writer.call_tool.return_value = {"answer": "answer without blueprint"}

    plan = _make_plan(intent_query="summary style")
    # Reset side_effect for researcher call (librarian is only called for blueprint)
    librarian.call_tool.side_effect = Exception("ContextLibrary down")

    result = await executor.execute(plan, _make_context(), on_status, tracer)

    assert result.answer == "answer without blueprint"
    assert result.blueprint_used is None


# --- Streaming ---

async def test_execute_streaming(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, status_events = setup
    researcher.call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}

    async def mock_stream():
        for t in ["Hello", " world"]:
            yield t

    writer.call_tool.return_value = {"stream": mock_stream()}

    result = await executor.execute(_make_plan(), _make_context(stream=True), on_status, tracer)

    assert result.stream is not None
    tokens = [t async for t in result.stream]
    assert tokens == ["Hello", " world"]


# --- Placeholder resolution ---

async def test_resolve_request_context_placeholders(setup):
    executor, *_ = setup
    request_context = {"USER_ID": "u1", "ORG_ID": "o1", "HISTORY": [], "DOCUMENT_IDS": None, "ORIGINAL_GOAL": "test"}
    inputs = {"user_id": "$$USER_ID$$", "org_id": "$$ORG_ID$$", "question": "$$ORIGINAL_GOAL$$"}
    resolved = executor._resolve_dependencies(inputs, {}, request_context)
    assert resolved == {"user_id": "u1", "org_id": "o1", "question": "test"}


async def test_resolve_step_output_placeholder(setup):
    executor, *_ = setup
    step_outputs = {1: {"chunks": [{"text": "data"}], "rewritten_query": None}}
    request_context = {"USER_ID": "u1", "ORG_ID": "", "HISTORY": [], "DOCUMENT_IDS": None, "ORIGINAL_GOAL": "test"}
    inputs = {"data": "$$STEP_1_OUTPUT$$"}
    resolved = executor._resolve_dependencies(inputs, step_outputs, request_context)
    assert resolved["data"] == step_outputs[1]


async def test_resolve_step_output_field_placeholder(setup):
    executor, *_ = setup
    step_outputs = {1: {"chunks": [{"text": "data"}], "rewritten_query": "rewritten"}}
    request_context = {"USER_ID": "u1", "ORG_ID": "", "HISTORY": [], "DOCUMENT_IDS": None, "ORIGINAL_GOAL": "test"}
    inputs = {"query": "$$STEP_1_OUTPUT.rewritten_query$$"}
    resolved = executor._resolve_dependencies(inputs, step_outputs, request_context)
    assert resolved["query"] == "rewritten"


async def test_resolve_unknown_placeholder_raises(setup):
    executor, *_ = setup
    with pytest.raises(AgentError) as exc_info:
        executor._resolve_placeholder("$$UNKNOWN$$", {}, {})
    assert "Unknown placeholder" in exc_info.value.message


async def test_resolve_missing_step_output_raises(setup):
    executor, *_ = setup
    with pytest.raises(AgentError) as exc_info:
        executor._resolve_placeholder("$$STEP_99_OUTPUT$$", {}, {})
    assert "no output yet" in exc_info.value.message


async def test_resolve_missing_field_raises(setup):
    executor, *_ = setup
    step_outputs = {1: {"chunks": []}}
    with pytest.raises(AgentError) as exc_info:
        executor._resolve_placeholder("$$STEP_1_OUTPUT.nonexistent$$", step_outputs, {})
    assert "no field" in exc_info.value.message


# --- Source building ---

async def test_sources_truncated(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, _ = setup
    long_chunks = [{"chunk_id": "c1", "text": "A" * 500, "metadata": {"source": "doc.pdf"}, "score": 0.9}]
    researcher.call_tool.return_value = {"chunks": long_chunks, "rewritten_query": None}
    writer.call_tool.return_value = {"answer": "answer"}

    result = await executor.execute(_make_plan(), _make_context(), on_status, tracer)
    assert len(result.sources[0].text) <= 200


# --- Agent error propagation ---

async def test_specialist_failure_propagates(setup):
    executor, librarian, writer, researcher, _, tracer, on_status, _ = setup
    researcher.call_tool.side_effect = AgentError("LLM_ERROR", "OpenAI down", "researcher", "researcher.research")

    with pytest.raises(AgentError) as exc_info:
        await executor.execute(_make_plan(), _make_context(), on_status, tracer)
    assert exc_info.value.error_type == "LLM_ERROR"
