"""
REQ-MT-005: Writer agent unit tests.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.base import AgentError
from app.agents.writer import WriterAgent


@pytest.fixture
def writer():
    return WriterAgent()


def _sample_chunks():
    return [
        {"chunk_id": "c1", "text": "The liability shall not exceed...", "metadata": {"source": "contract.pdf", "page": 5}},
    ]


# --- Happy path ---

async def test_generate_returns_answer(writer):
    with patch("app.agents.writer.generate", new_callable=AsyncMock, return_value="The answer is..."):
        result = await writer.call_tool("writer.generate", {
            "question": "What is the liability?",
            "chunks": _sample_chunks(),
        })
    assert result["answer"] == "The answer is..."


async def test_generate_includes_history(writer):
    with patch("app.agents.writer.generate", new_callable=AsyncMock, return_value="answer") as mock_gen:
        await writer.call_tool("writer.generate", {
            "question": "Follow up",
            "chunks": _sample_chunks(),
            "history": [{"role": "user", "content": "first"}, {"role": "assistant", "content": "reply"}],
        })
    # Verify history was passed to generate
    call_history = mock_gen.call_args[0][2]
    assert len(call_history) == 2
    assert call_history[0].role == "user"


async def test_generate_uses_system_prompt(writer):
    """Verify the writer delegates to generate which uses SYSTEM_PROMPT."""
    with patch("app.agents.writer.generate", new_callable=AsyncMock, return_value="answer") as mock_gen:
        await writer.call_tool("writer.generate", {
            "question": "test",
            "chunks": _sample_chunks(),
        })
    mock_gen.assert_called_once()


# --- Streaming ---

async def test_generate_stream_yields_tokens(writer):
    async def mock_stream(*args, **kwargs):
        for token in ["Hello", " world", "!"]:
            yield token

    with patch("app.agents.writer.generate_stream", side_effect=mock_stream):
        result = await writer.call_tool("writer.generate", {
            "question": "test",
            "chunks": _sample_chunks(),
            "stream": True,
        })

    assert "stream" in result
    tokens = []
    async for token in result["stream"]:
        tokens.append(token)
    assert tokens == ["Hello", " world", "!"]


# --- Validation ---

async def test_generate_validates_empty_chunks(writer):
    with pytest.raises(AgentError) as exc_info:
        await writer.call_tool("writer.generate", {
            "question": "test",
            "chunks": [],
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"
    assert "chunks" in exc_info.value.message


async def test_generate_validates_empty_question(writer):
    with pytest.raises(AgentError) as exc_info:
        await writer.call_tool("writer.generate", {
            "question": "",
            "chunks": _sample_chunks(),
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"


# --- Blueprint-aware system prompt ---

def test_build_system_prompt_no_blueprint(writer):
    from app.rag.llm import SYSTEM_PROMPT
    assert writer._build_system_prompt(None) == SYSTEM_PROMPT
    assert writer._build_system_prompt({}) == SYSTEM_PROMPT
    assert writer._build_system_prompt({"content": None}) == SYSTEM_PROMPT


def test_build_system_prompt_with_scene_goal(writer):
    bp = {"content": {"scene_goal": "Increase tension"}}
    prompt = writer._build_system_prompt(bp)
    assert "Increase tension" in prompt
    assert "Goal:" in prompt


def test_build_system_prompt_with_style_guide(writer):
    bp = {"content": {"style_guide": "Use short sentences"}}
    prompt = writer._build_system_prompt(bp)
    assert "Use short sentences" in prompt
    assert "Style guide:" in prompt


def test_build_system_prompt_with_structure(writer):
    bp = {"content": {"structure": ["Definition", "Impact"]}}
    prompt = writer._build_system_prompt(bp)
    assert "Definition, Impact" in prompt


def test_build_system_prompt_with_participants(writer):
    bp = {"content": {"participants": [
        {"role": "Agent", "description": "The protagonist"},
        {"role": "Threat", "description": "The danger"},
    ]}}
    prompt = writer._build_system_prompt(bp)
    assert "Agent: The protagonist" in prompt
    assert "Threat: The danger" in prompt


def test_build_system_prompt_with_instruction(writer):
    bp = {"content": {"instruction": "Rewrite the facts"}}
    prompt = writer._build_system_prompt(bp)
    assert "Rewrite the facts" in prompt


def test_build_system_prompt_full_blueprint(writer):
    from app.rag.llm import SYSTEM_PROMPT
    bp = {"content": {
        "scene_goal": "Explain clearly",
        "style_guide": "Formal tone",
        "structure": ["Intro", "Body", "Conclusion"],
        "participants": [{"role": "Expert", "description": "Domain specialist"}],
        "instruction": "Follow the structure",
    }}
    prompt = writer._build_system_prompt(bp)
    assert prompt.startswith(SYSTEM_PROMPT)
    assert "Explain clearly" in prompt
    assert "Formal tone" in prompt
    assert "Intro, Body, Conclusion" in prompt
    assert "Expert: Domain specialist" in prompt
    assert "Follow the structure" in prompt


async def test_generate_with_blueprint_passes_custom_prompt(writer):
    bp = {"content": {"scene_goal": "Be concise", "instruction": "Summarize"}}
    with patch("app.agents.writer.generate", new_callable=AsyncMock, return_value="answer") as mock_gen:
        await writer.call_tool("writer.generate", {
            "question": "test",
            "chunks": _sample_chunks(),
            "blueprint": bp,
        })
    call_kwargs = mock_gen.call_args[1]
    assert "Be concise" in call_kwargs["system_prompt"]
    assert "Summarize" in call_kwargs["system_prompt"]
