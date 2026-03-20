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
