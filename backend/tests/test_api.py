"""
REQ-QT-003: Chat request validation rejects empty questions.
REQ-QT-004: File type validation rejects unsupported extensions.
REQ-QN-008: Backend returns structured error responses.
REQ-QN-010: Backend logs requests with method, path, status, duration.
"""
import pytest


def test_health_shallow(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_deep(client):
    resp = client.get("/api/health?deep=true")
    assert resp.status_code == 200
    data = resp.json()
    assert "checks" in data


# REQ-QT-003
def test_chat_empty_question(client, auth_headers):
    resp = client.post("/api/chat", json={"question": ""}, headers=auth_headers)
    assert resp.status_code == 422


def test_chat_question_too_long(client, auth_headers):
    resp = client.post("/api/chat", json={"question": "x" * 3000}, headers=auth_headers)
    assert resp.status_code == 422


# REQ-QT-004
def test_upload_no_file(client, auth_headers):
    resp = client.post("/api/upload", headers=auth_headers)
    assert resp.status_code == 422


def test_upload_unsupported_type(client, auth_headers):
    resp = client.post("/api/upload", files={"file": ("test.csv", b"a,b,c", "text/csv")}, headers=auth_headers)
    assert resp.status_code == 400


def test_upload_empty_file(client, auth_headers):
    resp = client.post("/api/upload", files={"file": ("test.txt", b"", "text/plain")}, headers=auth_headers)
    assert resp.status_code == 400


# REQ-QN-008: structured error (never raw stack traces)
def test_structured_error_on_unauth(client):
    resp = client.post("/api/chat", json={"question": "hello"})
    assert resp.status_code == 401
    data = resp.json()
    assert "detail" in data


# Request ID middleware
def test_request_id_header(client):
    resp = client.get("/api/health")
    assert "X-Request-ID" in resp.headers


def test_request_id_propagated(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "test-123"})
    assert resp.headers["X-Request-ID"] == "test-123"
