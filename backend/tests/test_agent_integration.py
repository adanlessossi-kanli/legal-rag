"""
REQ-MT-008: End-to-end multi-agent integration tests.
All agents wired together with mocked OpenAI and MongoDB.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.librarian import LibrarianAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.researcher import ResearcherAgent
from app.agents.writer import WriterAgent
from app.agents.orchestrator import Orchestrator, NO_CONTEXT_ANSWER


def _mock_completion(text):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    return resp


def _mock_embedding():
    return [[0.1] * 1536]


@pytest.fixture
def mock_openai_all():
    """Patch OpenAI client for all agent modules."""
    with patch("app.rag.llm.openai_client") as llm_client, \
         patch("app.rag.vectorstore.openai_client") as vs_client, \
         patch("app.agents.summarizer.openai_client") as sum_client:

        # LLM generate
        llm_client.chat.completions.create = AsyncMock(return_value=_mock_completion("Generated answer"))
        # Embeddings
        embed_resp = MagicMock()
        embed_resp.data = [MagicMock(embedding=[0.1] * 1536)]
        vs_client.embeddings.create = AsyncMock(return_value=embed_resp)
        # Summarizer
        sum_client.chat.completions.create = AsyncMock(return_value=_mock_completion("Summary text"))

        yield {"llm": llm_client, "vs": vs_client, "sum": sum_client}


@pytest.fixture
def mock_retrieve():
    """Mock the vectorstore retrieve to return sample chunks."""
    chunks = [
        {"chunk_id": "c1", "text": "The total liability shall not exceed the contract value.", "metadata": {"source": "contract.pdf", "page": 5}},
        {"chunk_id": "c2", "text": "Payment terms are net 30 days.", "metadata": {"source": "contract.pdf", "page": 8}},
    ]
    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=chunks) as mock:
        yield mock, chunks


@pytest.fixture
def wired_orchestrator(mock_openai_all):
    """Create a fully wired orchestrator with real agent instances."""
    librarian = LibrarianAgent()
    summarizer = SummarizerAgent()
    writer = WriterAgent()
    researcher = ResearcherAgent(librarian, summarizer)
    return Orchestrator(librarian, researcher, writer, summarizer)


# --- Full query flow ---

async def test_full_query_flow(wired_orchestrator, mock_retrieve):
    answer, sources, no_context = await wired_orchestrator.query(
        "What is the liability clause?", [], "user1",
    )

    assert answer == "Generated answer"
    assert len(sources) == 2
    assert sources[0].document == "contract.pdf"
    assert not no_context


async def test_no_context_flow(wired_orchestrator, mock_openai_all):
    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=[]):
        answer, sources, no_context = await wired_orchestrator.query(
            "Something not in documents", [], "user1",
        )

    assert answer == NO_CONTEXT_ANSWER
    assert sources == []
    assert no_context


# --- Streaming ---

async def test_stream_full_flow_event_order(wired_orchestrator, mock_retrieve, mock_openai_all):
    # Make the LLM stream tokens
    async def mock_stream_create(**kwargs):
        if kwargs.get("stream"):
            async def gen():
                for text in ["Token1", " Token2"]:
                    chunk = MagicMock()
                    chunk.choices = [MagicMock()]
                    chunk.choices[0].delta = MagicMock(content=text)
                    yield chunk
            return gen()
        return _mock_completion("answer")

    mock_openai_all["llm"].chat.completions.create = AsyncMock(side_effect=mock_stream_create)

    status_events = []

    async def on_status(agent, status):
        status_events.append((agent, status))

    token_gen, sources, no_context = await wired_orchestrator.query_stream(
        "What is liability?", [], "user1", on_status=on_status,
    )

    assert not no_context
    assert len(sources) == 2

    tokens = [t async for t in token_gen]
    assert tokens == ["Token1", " Token2"]

    # Verify status event order
    assert status_events[0] == ("researcher", "working")
    assert status_events[1] == ("writer", "working")
    assert status_events[-1] == ("done", "done")


# --- Summarization in flow ---

async def test_full_query_with_summarization(mock_openai_all):
    long_text = "x" * 3000
    long_chunks = [
        {"chunk_id": f"c{i}", "text": long_text, "metadata": {"source": "big.pdf", "page": i}, "score": 0.9}
        for i in range(4)
    ]

    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=long_chunks), \
         patch("app.agents.researcher.settings") as r_settings:
        r_settings.enable_query_rewriting = False
        r_settings.retrieval_top_k = 5
        r_settings.researcher_summarize_threshold = 5000  # 12000 > 5000 triggers summarization

        librarian = LibrarianAgent()
        summarizer = SummarizerAgent()
        writer = WriterAgent()
        researcher = ResearcherAgent(librarian, summarizer)
        orch = Orchestrator(librarian, researcher, writer, summarizer)

        answer, sources, no_context = await orch.query("Summarize liability", [], "user1")

    assert answer == "Generated answer"
    assert len(sources) == 4
    # Summarizer should have been called for each long chunk
    assert mock_openai_all["sum"].chat.completions.create.call_count == 4


# --- Graceful degradation ---

async def test_graceful_degradation_summarizer_down(mock_openai_all):
    long_text = "x" * 3000
    long_chunks = [
        {"chunk_id": "c1", "text": long_text, "metadata": {"source": "doc.pdf", "page": 1}, "score": 0.9},
    ]

    mock_openai_all["sum"].chat.completions.create = AsyncMock(side_effect=Exception("Summarizer down"))

    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=long_chunks), \
         patch("app.agents.researcher.settings") as r_settings:
        r_settings.enable_query_rewriting = False
        r_settings.retrieval_top_k = 5
        r_settings.researcher_summarize_threshold = 100

        librarian = LibrarianAgent()
        summarizer = SummarizerAgent()
        writer = WriterAgent()
        researcher = ResearcherAgent(librarian, summarizer)
        orch = Orchestrator(librarian, researcher, writer, summarizer)

        # Should NOT raise — graceful degradation
        answer, sources, no_context = await orch.query("test", [], "user1")

    assert answer == "Generated answer"
    assert not no_context


async def test_graceful_degradation_rewrite_fails(mock_openai_all, mock_retrieve):
    with patch("app.agents.researcher.rewrite_query", new_callable=AsyncMock, side_effect=Exception("LLM down")):
        librarian = LibrarianAgent()
        summarizer = SummarizerAgent()
        writer = WriterAgent()
        researcher = ResearcherAgent(librarian, summarizer)
        orch = Orchestrator(librarian, researcher, writer, summarizer)

        answer, sources, no_context = await orch.query(
            "follow up question",
            [MagicMock(role="user", content="prev")],
            "user1",
        )

    # Should succeed with original question
    assert answer == "Generated answer"
