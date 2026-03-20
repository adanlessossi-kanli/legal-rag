"""
REQ-MT-004: Researcher agent unit tests.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.base import AgentError
from app.agents.librarian import LibrarianAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.researcher import ResearcherAgent


@pytest.fixture
def mock_librarian():
    lib = MagicMock(spec=LibrarianAgent)
    lib.name = "librarian"
    lib.call_tool = AsyncMock()
    return lib


@pytest.fixture
def mock_summarizer():
    summ = MagicMock(spec=SummarizerAgent)
    summ.name = "summarizer"
    summ.call_tool = AsyncMock()
    return summ


@pytest.fixture
def researcher(mock_librarian, mock_summarizer):
    return ResearcherAgent(mock_librarian, mock_summarizer)


def _make_chunks(texts):
    return [
        {"chunk_id": f"c{i}", "text": t, "metadata": {"source": "doc.pdf"}, "score": 0.9}
        for i, t in enumerate(texts)
    ]


# --- Happy path ---

async def test_research_without_history(researcher, mock_librarian):
    mock_librarian.call_tool.return_value = {"chunks": _make_chunks(["text"])}

    with patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 10000
        result = await researcher.call_tool("researcher.research", {
            "question": "What is liability?",
            "user_id": "user1",
        })

    assert len(result["chunks"]) == 1
    assert result["rewritten_query"] is None  # no history → no rewrite


async def test_research_with_history_rewrites(researcher, mock_librarian):
    mock_librarian.call_tool.return_value = {"chunks": _make_chunks(["text"])}

    with patch("app.agents.researcher.rewrite_query", new_callable=AsyncMock, return_value="standalone question"), \
         patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 10000

        result = await researcher.call_tool("researcher.research", {
            "question": "What about that?",
            "history": [{"role": "user", "content": "Tell me about liability"}, {"role": "assistant", "content": "..."}],
            "user_id": "user1",
        })

    assert result["rewritten_query"] == "standalone question"


async def test_research_calls_librarian_search(researcher, mock_librarian):
    mock_librarian.call_tool.return_value = {"chunks": []}

    with patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 10000
        await researcher.call_tool("researcher.research", {
            "question": "test query",
            "user_id": "user1",
            "document_ids": ["doc1"],
        })

    mock_librarian.call_tool.assert_called_once()
    call_args = mock_librarian.call_tool.call_args
    assert call_args[0][0] == "librarian.search"
    assert call_args[0][1]["query"] == "test query"
    assert call_args[0][1]["user_id"] == "user1"


async def test_research_returns_rewritten_query(researcher, mock_librarian):
    mock_librarian.call_tool.return_value = {"chunks": _make_chunks(["text"])}

    with patch("app.agents.researcher.rewrite_query", new_callable=AsyncMock, return_value="rewritten"), \
         patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 10000

        result = await researcher.call_tool("researcher.research", {
            "question": "follow up",
            "history": [{"role": "user", "content": "first"}],
            "user_id": "user1",
        })

    assert result["rewritten_query"] == "rewritten"


# --- Summarization ---

async def test_research_summarizes_long_context(researcher, mock_librarian, mock_summarizer):
    long_text = "x" * 3000
    mock_librarian.call_tool.return_value = {"chunks": _make_chunks([long_text, long_text, long_text, long_text])}
    mock_summarizer.call_tool.return_value = {"summary": "short summary"}

    with patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 5000  # total 12000 > 5000

        result = await researcher.call_tool("researcher.research", {
            "question": "summarize this",
            "user_id": "user1",
        })

    # All chunks > 2000 chars should be summarized
    assert mock_summarizer.call_tool.call_count == 4
    for chunk in result["chunks"]:
        assert chunk["text"] == "short summary"


async def test_research_no_summarize_under_threshold(researcher, mock_librarian, mock_summarizer):
    mock_librarian.call_tool.return_value = {"chunks": _make_chunks(["short text"])}

    with patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 10000

        await researcher.call_tool("researcher.research", {
            "question": "test",
            "user_id": "user1",
        })

    mock_summarizer.call_tool.assert_not_called()


async def test_research_skips_short_chunks_in_summarization(researcher, mock_librarian, mock_summarizer):
    """Only chunks > 2000 chars are summarized individually."""
    mock_librarian.call_tool.return_value = {
        "chunks": _make_chunks(["short", "x" * 3000, "also short", "y" * 3000])
    }
    mock_summarizer.call_tool.return_value = {"summary": "summarized"}

    with patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 100  # force summarization check

        result = await researcher.call_tool("researcher.research", {
            "question": "test",
            "user_id": "user1",
        })

    # Only the 2 long chunks should be summarized
    assert mock_summarizer.call_tool.call_count == 2


# --- Fallback behavior ---

async def test_research_rewrite_failure_fallback(researcher, mock_librarian):
    mock_librarian.call_tool.return_value = {"chunks": _make_chunks(["text"])}

    with patch("app.agents.researcher.rewrite_query", new_callable=AsyncMock, side_effect=Exception("LLM down")), \
         patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 10000

        result = await researcher.call_tool("researcher.research", {
            "question": "original question",
            "history": [{"role": "user", "content": "prev"}],
            "user_id": "user1",
        })

    # Should use original question, not fail
    assert result["rewritten_query"] is None
    assert len(result["chunks"]) == 1


async def test_research_summarizer_failure_fallback(researcher, mock_librarian, mock_summarizer):
    long_text = "x" * 3000
    mock_librarian.call_tool.return_value = {"chunks": _make_chunks([long_text])}
    mock_summarizer.call_tool.side_effect = Exception("Summarizer down")

    with patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 100

        result = await researcher.call_tool("researcher.research", {
            "question": "test",
            "user_id": "user1",
        })

    # Should return original chunk text, not fail
    assert result["chunks"][0]["text"] == long_text


async def test_research_empty_results(researcher, mock_librarian):
    mock_librarian.call_tool.return_value = {"chunks": []}

    with patch("app.agents.researcher.settings") as s:
        s.enable_query_rewriting = True
        s.retrieval_top_k = 5
        s.researcher_summarize_threshold = 10000

        result = await researcher.call_tool("researcher.research", {
            "question": "nothing here",
            "user_id": "user1",
        })

    assert result["chunks"] == []


# --- Validation ---

async def test_research_validates_empty_question(researcher):
    with pytest.raises(AgentError) as exc_info:
        await researcher.call_tool("researcher.research", {
            "question": "",
            "user_id": "user1",
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"
