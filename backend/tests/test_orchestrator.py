"""
REQ-MT-007: Orchestrator coordination tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call

from app.agents.base import AgentError
from app.agents.librarian import LibrarianAgent
from app.agents.researcher import ResearcherAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.writer import WriterAgent
from app.agents.orchestrator import Orchestrator, NO_CONTEXT_ANSWER


def _mock_agent(cls, name):
    agent = MagicMock(spec=cls)
    agent.name = name
    agent.call_tool = AsyncMock()
    agent.health = AsyncMock(return_value="ok")
    return agent


@pytest.fixture
def agents():
    return {
        "librarian": _mock_agent(LibrarianAgent, "librarian"),
        "researcher": _mock_agent(ResearcherAgent, "researcher"),
        "writer": _mock_agent(WriterAgent, "writer"),
        "summarizer": _mock_agent(SummarizerAgent, "summarizer"),
    }


@pytest.fixture
def orchestrator(agents):
    return Orchestrator(agents["librarian"], agents["researcher"], agents["writer"], agents["summarizer"])


def _sample_chunks():
    return [
        {"chunk_id": "c1", "text": "Liability clause text here", "metadata": {"source": "contract.pdf"}, "score": 0.9},
    ]


# --- Query ---

async def test_query_calls_researcher_then_writer(orchestrator, agents):
    agents["researcher"].call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}
    agents["writer"].call_tool.return_value = {"answer": "The answer is..."}

    answer, sources, no_context = await orchestrator.query("What is liability?", [], "user1")

    assert answer == "The answer is..."
    assert len(sources) == 1
    assert not no_context

    # Verify call order: researcher first, then writer
    agents["researcher"].call_tool.assert_called_once()
    agents["writer"].call_tool.assert_called_once()
    assert agents["researcher"].call_tool.call_args[0][0] == "researcher.research"
    assert agents["writer"].call_tool.call_args[0][0] == "writer.generate"


async def test_query_no_context_returns_fallback(orchestrator, agents):
    agents["researcher"].call_tool.return_value = {"chunks": [], "rewritten_query": None}

    answer, sources, no_context = await orchestrator.query("Unknown topic", [], "user1")

    assert answer == NO_CONTEXT_ANSWER
    assert sources == []
    assert no_context
    agents["writer"].call_tool.assert_not_called()  # Writer should NOT be called


async def test_query_builds_sources_from_chunks(orchestrator, agents):
    chunks = [
        {"chunk_id": "c1", "text": "A" * 300, "metadata": {"source": "doc1.pdf", "doc_id": "d1", "page": 1, "page_start": 1, "page_end": 1}, "score": 0.9},
        {"chunk_id": "c2", "text": "B" * 50, "metadata": {"source": "doc2.pdf", "doc_id": "d2", "page": 1, "page_start": 1, "page_end": 1}, "score": 0.8},
    ]
    agents["researcher"].call_tool.return_value = {"chunks": chunks, "rewritten_query": None}
    agents["writer"].call_tool.return_value = {"answer": "answer"}

    _, sources, _ = await orchestrator.query("test", [], "user1")

    assert len(sources) == 2
    assert sources[0].document == "doc1.pdf"
    assert sources[1].document == "doc2.pdf"
    # Source text should be truncated to SOURCE_TEXT_MAX_LENGTH
    assert len(sources[0].text) <= 200


async def test_query_stream_emits_status_events(orchestrator, agents):
    agents["researcher"].call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}

    async def mock_stream():
        yield "token1"
        yield "token2"

    agents["writer"].call_tool.return_value = {"stream": mock_stream()}

    status_events = []

    async def on_status(agent, status):
        status_events.append((agent, status))

    token_gen, sources, no_context = await orchestrator.query_stream("test", [], "user1", on_status=on_status)

    # Consume the stream
    tokens = []
    async for token in token_gen:
        tokens.append(token)

    assert ("researcher", "working") in status_events
    assert ("writer", "working") in status_events
    assert ("done", "done") in status_events
    assert tokens == ["token1", "token2"]


async def test_query_stream_forwards_tokens(orchestrator, agents):
    agents["researcher"].call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}

    async def mock_stream():
        for t in ["Hello", " ", "world"]:
            yield t

    agents["writer"].call_tool.return_value = {"stream": mock_stream()}

    token_gen, _, _ = await orchestrator.query_stream("test", [], "user1")
    tokens = [t async for t in token_gen]
    assert tokens == ["Hello", " ", "world"]


# --- Ingest ---

async def test_ingest_delegates_to_librarian(orchestrator, agents):
    agents["librarian"].call_tool.return_value = {"chunk_count": 42}

    count = await orchestrator.ingest("/path/file.pdf", "file.pdf", "doc1", "a" * 64, "user1")

    assert count == 42
    agents["librarian"].call_tool.assert_called_once_with("librarian.ingest", {
        "file_path": "/path/file.pdf",
        "original_name": "file.pdf",
        "doc_id": "doc1",
        "content_hash": "a" * 64,
        "user_id": "user1",
        "org_id": "",
    })


# --- Remove ---

async def test_remove_delegates_to_librarian(orchestrator, agents):
    agents["librarian"].call_tool.return_value = {"deleted": True}

    await orchestrator.remove_document("doc1")

    agents["librarian"].call_tool.assert_called_once_with("librarian.remove", {"doc_id": "doc1"})


# --- Summarize ---

async def test_summarize_delegates_to_summarizer(orchestrator, agents):
    agents["summarizer"].call_tool.return_value = {"summary": "Short version"}

    result = await orchestrator.summarize("Long text...", "key points", 500)

    assert result == "Short version"
    agents["summarizer"].call_tool.assert_called_once()


# --- Error handling ---

async def test_researcher_failure_returns_error(orchestrator, agents):
    agents["researcher"].call_tool.side_effect = AgentError("LLM_ERROR", "OpenAI down", "researcher", "researcher.research", retryable=True)

    with pytest.raises(AgentError) as exc_info:
        await orchestrator.query("test", [], "user1")

    assert exc_info.value.error_type == "LLM_ERROR"


async def test_writer_failure_returns_error(orchestrator, agents):
    agents["researcher"].call_tool.return_value = {"chunks": _sample_chunks(), "rewritten_query": None}
    agents["writer"].call_tool.side_effect = AgentError("LLM_ERROR", "Generation failed", "writer", "writer.generate")

    with pytest.raises(AgentError):
        await orchestrator.query("test", [], "user1")


# --- Health ---

async def test_health_check(orchestrator, agents):
    result = await orchestrator.health_check()
    assert result == {"librarian": "ok", "researcher": "ok", "writer": "ok", "summarizer": "ok"}


async def test_health_check_degraded(orchestrator, agents):
    agents["writer"].health.side_effect = Exception("down")
    result = await orchestrator.health_check()
    assert result["writer"] == "error"
    assert result["librarian"] == "ok"
