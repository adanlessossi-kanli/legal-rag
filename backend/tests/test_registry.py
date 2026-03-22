"""
Context Engine: AgentRegistry unit tests.
"""
import pytest

from app.agents.base import AgentError
from app.engine.registry import AgentCapability, AgentRegistry


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def populated_registry(registry):
    from unittest.mock import MagicMock
    agent_a = MagicMock()
    agent_b = MagicMock()
    registry.register("researcher", agent_a, AgentCapability(
        name="researcher", description="Retrieves info", tools=["researcher.research"],
    ))
    registry.register("summarizer", agent_b, AgentCapability(
        name="summarizer", description="Summarizes text", tools=["summarizer.summarize"],
    ))
    return registry, agent_a, agent_b


# --- register ---

def test_register_agent(registry):
    from unittest.mock import MagicMock
    agent = MagicMock()
    registry.register("test", agent, AgentCapability(name="test", description="desc", tools=["t.do"]))
    assert registry.has_agent("test")


def test_register_duplicate_raises(populated_registry):
    registry, agent_a, _ = populated_registry
    from unittest.mock import MagicMock
    with pytest.raises(ValueError, match="already registered"):
        registry.register("researcher", MagicMock(), AgentCapability(name="researcher", description="dup"))


# --- get_handler ---

def test_get_handler_returns_agent(populated_registry):
    registry, agent_a, _ = populated_registry
    assert registry.get_handler("researcher") is agent_a


def test_get_handler_unknown_raises(registry):
    with pytest.raises(AgentError) as exc_info:
        registry.get_handler("nonexistent")
    assert exc_info.value.error_type == "VALIDATION_ERROR"
    assert "Unknown agent" in exc_info.value.message


# --- has_agent ---

def test_has_agent_true(populated_registry):
    registry, _, _ = populated_registry
    assert registry.has_agent("researcher") is True


def test_has_agent_false(registry):
    assert registry.has_agent("ghost") is False


# --- list_agents ---

def test_list_agents_empty(registry):
    assert registry.list_agents() == []


def test_list_agents_returns_capabilities(populated_registry):
    registry, _, _ = populated_registry
    caps = registry.list_agents()
    assert len(caps) == 2
    names = {c.name for c in caps}
    assert names == {"researcher", "summarizer"}


# --- get_capabilities_description ---

def test_capabilities_description_format(populated_registry):
    registry, _, _ = populated_registry
    desc = registry.get_capabilities_description()
    assert "researcher" in desc
    assert "summarizer" in desc
    assert "researcher.research" in desc
    assert "Retrieves info" in desc
