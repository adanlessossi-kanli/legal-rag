"""
Context Engine: Planner unit tests.
"""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.planner import ExecutionPlan, PlanContext, PlanStep, Planner
from app.engine.registry import AgentCapability, AgentRegistry


@pytest.fixture
def registry():
    r = AgentRegistry()
    r.register("researcher", MagicMock(), AgentCapability(
        name="researcher", description="Retrieves info", tools=["researcher.research"],
    ))
    r.register("summarizer", MagicMock(), AgentCapability(
        name="summarizer", description="Summarizes text", tools=["summarizer.summarize"],
    ))
    return r


@pytest.fixture
def planner(registry):
    return Planner(registry)


@pytest.fixture
def context():
    return PlanContext(
        user_id="user1", org_id=None, history=[], document_ids=None,
        stream=False, has_blueprints=True,
    )


def _mock_llm_response(plan_dict: dict):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps(plan_dict)
    return resp


# --- fallback plan ---

async def test_fallback_when_engine_disabled(planner, context):
    with patch("app.engine.planner.settings") as s:
        s.enable_context_engine = False
        plan = await planner.plan("test question", context)

    assert len(plan.steps) == 1
    assert plan.steps[0].agent == "researcher"
    assert plan.intent_query is None
    assert plan.topic_query == "test question"


async def test_fallback_on_llm_failure(planner, context):
    with patch("app.engine.planner.settings") as s, \
         patch("app.core.clients.openai_client") as mock_client:
        s.enable_context_engine = True
        s.planner_model = "gpt-4o"
        s.planner_timeout = 5
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))
        plan = await planner.plan("test question", context)

    assert len(plan.steps) == 1
    assert plan.steps[0].agent == "researcher"


# --- LLM plan ---

async def test_llm_plan_success(planner, context):
    plan_dict = {
        "intent_query": "executive summary",
        "topic_query": "liability clauses",
        "steps": [
            {"step_id": 1, "agent": "researcher", "tool": "researcher.research",
             "inputs": {"question": "$$ORIGINAL_GOAL$$"}, "description": "Retrieve context"},
        ],
    }
    with patch("app.engine.planner.settings") as s, \
         patch("app.core.clients.openai_client") as mock_client:
        s.enable_context_engine = True
        s.planner_model = "gpt-4o"
        s.planner_timeout = 15
        mock_client.chat.completions.create = AsyncMock(return_value=_mock_llm_response(plan_dict))
        plan = await planner.plan("What are the liability clauses?", context)

    assert plan.intent_query == "executive summary"
    assert plan.topic_query == "liability clauses"
    assert len(plan.steps) == 1
    assert plan.steps[0].agent == "researcher"


async def test_llm_plan_multi_step(planner, context):
    plan_dict = {
        "intent_query": None,
        "topic_query": "liability",
        "steps": [
            {"step_id": 1, "agent": "researcher", "tool": "researcher.research",
             "inputs": {"question": "$$ORIGINAL_GOAL$$"}, "description": "Retrieve"},
            {"step_id": 2, "agent": "summarizer", "tool": "summarizer.summarize",
             "inputs": {"text": "$$STEP_1_OUTPUT$$"}, "description": "Summarize",
             "depends_on": [1]},
        ],
    }
    with patch("app.engine.planner.settings") as s, \
         patch("app.core.clients.openai_client") as mock_client:
        s.enable_context_engine = True
        s.planner_model = "gpt-4o"
        s.planner_timeout = 15
        mock_client.chat.completions.create = AsyncMock(return_value=_mock_llm_response(plan_dict))
        plan = await planner.plan("Summarize liability", context)

    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == [1]


# --- validation ---

def test_validate_empty_steps(planner):
    plan = ExecutionPlan(goal="test", steps=[])
    with pytest.raises(ValueError, match="no steps"):
        planner._validate_plan(plan)


def test_validate_unknown_agent(planner):
    plan = ExecutionPlan(goal="test", steps=[
        PlanStep(step_id=1, agent="ghost", tool="ghost.do", inputs={}, description=""),
    ])
    with pytest.raises(ValueError, match="Unknown agent"):
        planner._validate_plan(plan)


def test_validate_forward_dependency(planner):
    plan = ExecutionPlan(goal="test", steps=[
        PlanStep(step_id=1, agent="researcher", tool="researcher.research", inputs={}, description="", depends_on=[2]),
        PlanStep(step_id=2, agent="summarizer", tool="summarizer.summarize", inputs={}, description=""),
    ])
    with pytest.raises(ValueError, match="forward/circular dependency"):
        planner._validate_plan(plan)


def test_validate_nonexistent_dependency(planner):
    plan = ExecutionPlan(goal="test", steps=[
        PlanStep(step_id=1, agent="researcher", tool="researcher.research", inputs={}, description="", depends_on=[99]),
    ])
    with pytest.raises(ValueError, match="non-existent step"):
        planner._validate_plan(plan)


def test_validate_valid_plan(planner):
    plan = ExecutionPlan(goal="test", steps=[
        PlanStep(step_id=1, agent="researcher", tool="researcher.research", inputs={}, description=""),
        PlanStep(step_id=2, agent="summarizer", tool="summarizer.summarize", inputs={}, description="", depends_on=[1]),
    ])
    planner._validate_plan(plan)  # should not raise


# --- parse ---

def test_parse_plan_basic(planner):
    raw = {
        "intent_query": "summary",
        "topic_query": "liability",
        "steps": [
            {"step_id": 1, "agent": "researcher", "tool": "researcher.research",
             "inputs": {"q": "test"}, "description": "desc", "depends_on": []},
        ],
    }
    plan = planner._parse_plan("goal", raw)
    assert plan.goal == "goal"
    assert plan.intent_query == "summary"
    assert plan.topic_query == "liability"
    assert len(plan.steps) == 1


def test_parse_plan_defaults(planner):
    raw = {"steps": [{"step_id": 1, "agent": "researcher", "tool": "researcher.research"}]}
    plan = planner._parse_plan("goal", raw)
    assert plan.intent_query is None
    assert plan.topic_query == "goal"
    assert plan.steps[0].inputs == {}
    assert plan.steps[0].depends_on == []
