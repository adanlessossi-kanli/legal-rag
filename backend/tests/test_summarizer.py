"""
REQ-MT-006: Summarizer agent unit tests.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.base import AgentError
from app.agents.summarizer import SummarizerAgent


@pytest.fixture
def summarizer():
    return SummarizerAgent()


def _mock_completion(text):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


# --- Happy path ---

async def test_summarize_returns_summary(summarizer):
    with patch.object(summarizer, "_call_llm", new_callable=AsyncMock, return_value=_mock_completion("Short summary")):
        result = await summarizer.call_tool("summarizer.summarize", {
            "text": "A very long legal document text that needs summarization...",
            "objective": "key liability terms",
        })
    assert result["summary"] == "Short summary"


async def test_summarize_prompt_includes_objective(summarizer):
    with patch.object(summarizer, "_call_llm", new_callable=AsyncMock, return_value=_mock_completion("summary")) as mock_llm:
        await summarizer.call_tool("summarizer.summarize", {
            "text": "Some text",
            "objective": "payment terms",
            "max_length": 300,
        })
    prompt = mock_llm.call_args[0][0]
    assert "payment terms" in prompt


async def test_summarize_prompt_includes_max_length(summarizer):
    with patch.object(summarizer, "_call_llm", new_callable=AsyncMock, return_value=_mock_completion("summary")) as mock_llm:
        await summarizer.call_tool("summarizer.summarize", {
            "text": "Some text",
            "objective": "test",
            "max_length": 750,
        })
    prompt = mock_llm.call_args[0][0]
    assert "750" in prompt


async def test_summarize_uses_configured_model(summarizer):
    with patch("app.agents.summarizer.openai_client") as mock_client, \
         patch("app.agents.summarizer.settings") as mock_settings:
        mock_settings.summarizer_model = "gpt-4o-mini"
        mock_settings.summarizer_max_length = 500
        mock_client.chat.completions.create = AsyncMock(return_value=_mock_completion("summary"))

        await summarizer.call_tool("summarizer.summarize", {
            "text": "Some text",
            "objective": "test",
        })

    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "gpt-4o-mini"


# --- Validation ---

async def test_summarize_validates_empty_text(summarizer):
    with pytest.raises(AgentError) as exc_info:
        await summarizer.call_tool("summarizer.summarize", {
            "text": "",
            "objective": "test",
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"


async def test_summarize_validates_empty_objective(summarizer):
    with pytest.raises(AgentError) as exc_info:
        await summarizer.call_tool("summarizer.summarize", {
            "text": "Some text",
            "objective": "",
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"


async def test_summarize_validates_max_length_too_small(summarizer):
    with pytest.raises(AgentError) as exc_info:
        await summarizer.call_tool("summarizer.summarize", {
            "text": "Some text",
            "objective": "test",
            "max_length": 10,
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"


async def test_summarize_validates_max_length_too_large(summarizer):
    with pytest.raises(AgentError) as exc_info:
        await summarizer.call_tool("summarizer.summarize", {
            "text": "Some text",
            "objective": "test",
            "max_length": 10000,
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"
