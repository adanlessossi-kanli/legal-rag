"""
Auth tests: JWT tokens, password hashing, register/login flows.
REQ-QN-004: No secrets in source code (JWT_SECRET from env).
"""
import pytest

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from tests.conftest import TEST_USER_ID


def test_password_hash_roundtrip():
    hashed = hash_password("MySecure1")
    assert verify_password("MySecure1", hashed)
    assert not verify_password("WrongPass1", hashed)


def test_access_token_creation():
    token = create_access_token(str(TEST_USER_ID))
    assert isinstance(token, str) and len(token) > 20


def test_refresh_token_creation():
    token, jti = create_refresh_token(str(TEST_USER_ID))
    assert isinstance(token, str) and len(token) > 20
    assert isinstance(jti, str) and len(jti) > 0


def test_hash_token_deterministic():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("xyz")


def test_register(client):
    resp = client.post("/api/auth/register", json={
        "email": "new@example.com",
        "password": "Secure1pass",
        "name": "New User",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "new@example.com"


def test_register_duplicate(client):
    client.post("/api/auth/register", json={
        "email": "dup@example.com", "password": "Secure1pass", "name": "Dup",
    })
    resp = client.post("/api/auth/register", json={
        "email": "dup@example.com", "password": "Secure1pass", "name": "Dup",
    })
    assert resp.status_code == 409


def test_register_weak_password(client):
    resp = client.post("/api/auth/register", json={
        "email": "weak@example.com", "password": "short", "name": "Weak",
    })
    assert resp.status_code == 422


def test_login(client, test_user):
    resp = client.post("/api/auth/login", json={
        "email": "test@example.com", "password": "Test1234",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client, test_user):
    resp = client.post("/api/auth/login", json={
        "email": "test@example.com", "password": "WrongPass1",
    })
    assert resp.status_code == 401


def test_me_endpoint(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


def test_refresh_token_flow(client):
    # Register to get tokens
    resp = client.post("/api/auth/register", json={
        "email": "refresh@example.com", "password": "Secure1pass", "name": "Refresh",
    })
    refresh = resp.json()["refresh_token"]

    # Use refresh token
    resp2 = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()

    # Old refresh token should be revoked
    resp3 = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp3.status_code == 401
