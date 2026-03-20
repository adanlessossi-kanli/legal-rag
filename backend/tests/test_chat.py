"""
REQ-QT-006: Chat endpoint returns answer with sources for a known document.
"""
import pytest
from unittest.mock import patch, AsyncMock

from app.models.schemas import Source


def test_chat_returns_answer_with_sources(client, auth_headers):
    """Mock the RAG pipeline and verify the chat response shape."""
    mock_sources = [
        Source(document="contract.pdf", chunk_id="c1", text="Liability clause text"),
    ]
    with patch("app.api.chat.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = ("The liability clause states...", mock_sources, False)
        resp = client.post(
            "/api/chat",
            json={"question": "What is the liability clause?"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["document"] == "contract.pdf"
    assert "conversation_id" in data


def test_chat_creates_conversation(client, auth_headers):
    """First message should create a new conversation."""
    with patch("app.api.chat.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = ("Answer", [], False)
        resp = client.post(
            "/api/chat",
            json={"question": "Hello"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    cid = resp.json()["conversation_id"]
    assert cid is not None and len(cid) > 0


def test_chat_continues_conversation(client, auth_headers):
    """Providing conversation_id should append to existing conversation."""
    with patch("app.api.chat.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = ("First answer", [], False)
        resp1 = client.post(
            "/api/chat",
            json={"question": "First question"},
            headers=auth_headers,
        )
    cid = resp1.json()["conversation_id"]

    with patch("app.api.chat.query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = ("Follow-up answer", [], False)
        resp2 = client.post(
            "/api/chat",
            json={"question": "Follow-up", "conversation_id": cid},
            headers=auth_headers,
        )

    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == cid


def test_chat_requires_auth(client):
    resp = client.post("/api/chat", json={"question": "hello"})
    assert resp.status_code == 401
