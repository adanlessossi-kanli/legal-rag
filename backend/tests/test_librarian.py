"""
REQ-MT-003: Librarian agent unit tests.
"""
import os
import tempfile

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.base import AgentError
from app.agents.librarian import LibrarianAgent


@pytest.fixture
def librarian():
    return LibrarianAgent()


@pytest.fixture
def upload_dir():
    d = tempfile.mkdtemp()
    with patch("app.agents.librarian.settings") as mock_settings:
        mock_settings.upload_dir = d
        mock_settings.retrieval_top_k = 5
        mock_settings.retrieval_min_score = 0.7
        yield d, mock_settings


# --- Search ---

async def test_search_returns_chunks(librarian):
    mock_chunks = [
        {"chunk_id": "c1", "text": "Liability clause", "metadata": {"source": "contract.pdf"}, "score": 0.9},
    ]
    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=mock_chunks):
        result = await librarian.call_tool("librarian.search", {
            "query": "liability", "user_id": "user123",
        })
    assert len(result["chunks"]) == 1
    assert result["chunks"][0]["chunk_id"] == "c1"


async def test_search_filters_by_user(librarian):
    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=[]) as mock_ret:
        await librarian.call_tool("librarian.search", {
            "query": "test", "user_id": "user_abc",
        })
    mock_ret.assert_called_once()
    assert mock_ret.call_args[0][1] == "user_abc"


async def test_search_filters_by_document_ids(librarian):
    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=[]) as mock_ret:
        await librarian.call_tool("librarian.search", {
            "query": "test", "user_id": "user1", "document_ids": ["doc1", "doc2"],
        })
    assert mock_ret.call_args[0][2] == ["doc1", "doc2"]


async def test_search_empty_results(librarian):
    with patch("app.agents.librarian.retrieve", new_callable=AsyncMock, return_value=[]):
        result = await librarian.call_tool("librarian.search", {
            "query": "nonexistent", "user_id": "user1",
        })
    assert result["chunks"] == []


async def test_search_validates_empty_query(librarian):
    with pytest.raises(AgentError) as exc_info:
        await librarian.call_tool("librarian.search", {"query": "", "user_id": "user1"})
    assert exc_info.value.error_type == "VALIDATION_ERROR"


async def test_search_validates_missing_user_id(librarian):
    with pytest.raises(AgentError) as exc_info:
        await librarian.call_tool("librarian.search", {"query": "test"})
    assert exc_info.value.error_type == "VALIDATION_ERROR"


async def test_search_validates_top_k_bounds(librarian):
    with pytest.raises(AgentError) as exc_info:
        await librarian.call_tool("librarian.search", {
            "query": "test", "user_id": "user1", "top_k": 100,
        })
    assert exc_info.value.error_type == "VALIDATION_ERROR"


# --- Ingest ---

async def test_ingest_full_pipeline():
    librarian = LibrarianAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test file inside the upload dir
        test_file = os.path.join(tmpdir, "doc_abc_test.txt")
        with open(test_file, "w") as f:
            f.write("Legal contract text for testing.")

        with patch("app.agents.librarian.settings") as mock_settings, \
             patch("app.agents.librarian.save_document", new_callable=AsyncMock) as mock_save, \
             patch("app.agents.librarian.load_document") as mock_load, \
             patch("app.agents.librarian.chunk_pages") as mock_chunk, \
             patch("app.agents.librarian.store_chunks", new_callable=AsyncMock):

            mock_settings.upload_dir = tmpdir
            mock_load.return_value = [MagicMock(text="text", metadata={"source": "test.txt"})]
            mock_chunk.return_value = [MagicMock(text="chunk", metadata={}, chunk_id="c1")]

            result = await librarian.call_tool("librarian.ingest", {
                "file_path": test_file,
                "original_name": "test.txt",
                "doc_id": "doc_abc",
                "content_hash": "a" * 64,
                "user_id": "user1",
            })

        assert result["chunk_count"] == 1
        assert mock_save.call_count == 2  # processing + ready


async def test_ingest_error_sets_status():
    librarian = LibrarianAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "doc_err_test.txt")
        with open(test_file, "w") as f:
            f.write("text")

        with patch("app.agents.librarian.settings") as mock_settings, \
             patch("app.agents.librarian.save_document", new_callable=AsyncMock), \
             patch("app.agents.librarian.update_status", new_callable=AsyncMock) as mock_status, \
             patch("app.agents.librarian.load_document", side_effect=Exception("parse error")):

            mock_settings.upload_dir = tmpdir

            with pytest.raises(AgentError) as exc_info:
                await librarian.call_tool("librarian.ingest", {
                    "file_path": test_file,
                    "original_name": "test.txt",
                    "doc_id": "doc_err",
                    "content_hash": "b" * 64,
                    "user_id": "user1",
                })

        assert exc_info.value.error_type == "STORAGE_ERROR"
        mock_status.assert_called_once_with("doc_err", "error")


async def test_ingest_validates_path_traversal():
    librarian = LibrarianAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("app.agents.librarian.settings") as mock_settings:
            mock_settings.upload_dir = tmpdir

            with pytest.raises(AgentError) as exc_info:
                await librarian.call_tool("librarian.ingest", {
                    "file_path": "/etc/passwd",
                    "original_name": "test.txt",
                    "doc_id": "doc1",
                    "content_hash": "c" * 64,
                    "user_id": "user1",
                })
    assert "upload directory" in exc_info.value.message


async def test_ingest_validates_content_hash(librarian):
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("data")
        with patch("app.agents.librarian.settings") as mock_settings:
            mock_settings.upload_dir = tmpdir
            with pytest.raises(AgentError) as exc_info:
                await librarian.call_tool("librarian.ingest", {
                    "file_path": test_file,
                    "original_name": "test.txt",
                    "doc_id": "doc1",
                    "content_hash": "not-a-hash",
                    "user_id": "user1",
                })
    assert "content_hash" in exc_info.value.message


# --- Remove ---

async def test_remove_deletes_chunks_and_file():
    librarian = LibrarianAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "doc_rm_test.txt")
        with open(test_file, "w") as f:
            f.write("data")

        with patch("app.agents.librarian.settings") as mock_settings, \
             patch("app.agents.librarian.delete_by_doc_id", new_callable=AsyncMock) as mock_del:
            mock_settings.upload_dir = tmpdir

            result = await librarian.call_tool("librarian.remove", {"doc_id": "doc_rm"})

        assert result["deleted"] is True
        mock_del.assert_called_once_with("doc_rm")
        assert not os.path.exists(test_file)


async def test_remove_idempotent(librarian):
    with patch("app.agents.librarian.delete_by_doc_id", new_callable=AsyncMock), \
         patch("app.agents.librarian.settings") as mock_settings:
        mock_settings.upload_dir = tempfile.mkdtemp()
        result = await librarian.call_tool("librarian.remove", {"doc_id": "nonexistent"})
    assert result["deleted"] is True
