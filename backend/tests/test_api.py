import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_shallow():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_deep():
    resp = client.get("/api/health?deep=true")
    assert resp.status_code == 200
    data = resp.json()
    assert "checks" in data
    assert "chromadb" in data["checks"]


def test_chat_empty_question():
    resp = client.post("/api/chat", json={"question": "", "history": []})
    assert resp.status_code == 422


def test_chat_question_too_long():
    resp = client.post("/api/chat", json={"question": "x" * 3000, "history": []})
    assert resp.status_code == 422


def test_upload_no_file():
    resp = client.post("/api/upload")
    assert resp.status_code == 422


def test_upload_unsupported_type():
    resp = client.post("/api/upload", files={"file": ("test.csv", b"a,b,c", "text/csv")})
    assert resp.status_code == 400


def test_upload_empty_file():
    resp = client.post("/api/upload", files={"file": ("test.txt", b"", "text/plain")})
    assert resp.status_code == 400


def test_documents_list():
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_delete_nonexistent():
    resp = client.delete("/api/documents/doc_nonexistent")
    assert resp.status_code == 404


def test_request_id_header():
    resp = client.get("/api/health")
    assert "X-Request-ID" in resp.headers


def test_request_id_propagated():
    resp = client.get("/api/health", headers={"X-Request-ID": "test-123"})
    assert resp.headers["X-Request-ID"] == "test-123"
