"""
REQ-QT-005: Upload endpoint ingests a file and returns correct response.
REQ-QN-005: File upload validates type and size server-side.
REQ-QN-007: Uploaded filenames sanitized to prevent path traversal.
"""
import pytest
from unittest.mock import patch, AsyncMock

from app.api.upload import _sanitize_filename


def test_upload_txt_returns_processing(client, auth_headers):
    """Upload a valid TXT file and verify the response shape."""
    with patch("app.rag.pipeline.ingest", new_callable=AsyncMock) as mock_ingest:
        mock_ingest.return_value = 3
        resp = client.post(
            "/api/upload",
            files={"file": ("contract.txt", b"This is a legal contract.", "text/plain")},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "contract.txt"
    assert data["status"] == "processing"
    assert data["chunk_count"] == 0
    assert "id" in data


def test_upload_rejects_unsupported_extension(client, auth_headers):
    resp = client.post(
        "/api/upload",
        files={"file": ("data.xlsx", b"binary", "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


def test_upload_rejects_empty_file(client, auth_headers):
    resp = client.post(
        "/api/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# REQ-QN-007: filename sanitization
def test_sanitize_filename_removes_path_traversal():
    assert ".." not in _sanitize_filename("../../etc/passwd")
    assert "/" not in _sanitize_filename("path/to/file.pdf")
    safe = _sanitize_filename("my file (1).pdf")
    assert " " not in safe  # spaces replaced


def test_sanitize_filename_preserves_extension():
    assert _sanitize_filename("contract.pdf").endswith(".pdf")


def test_upload_requires_auth(client):
    resp = client.post("/api/upload", files={"file": ("test.txt", b"data", "text/plain")})
    assert resp.status_code == 401
