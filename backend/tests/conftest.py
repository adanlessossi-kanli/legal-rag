import os
import tempfile

import pytest

# Set required env vars before any app imports
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp())
os.environ.setdefault("LOG_FORMAT", "text")

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.core.auth import create_access_token, hash_password


# --- MongoDB mock ---

_mock_client = AsyncMongoMockClient()
_mock_db = _mock_client["test_legal_rag"]


def _get_mock_db():
    return _mock_db


@pytest.fixture(autouse=True)
async def _patch_db():
    """Patch get_db globally and clear collections between tests."""
    with patch("app.core.database.get_db", _get_mock_db), \
         patch("app.core.database._db", _mock_db):
        yield
    # Clean up all collections after each test
    for name in await _mock_db.list_collection_names():
        await _mock_db[name].delete_many({})


# --- Test user helpers ---

TEST_USER_ID = ObjectId()
TEST_USER = {
    "_id": TEST_USER_ID,
    "email": "test@example.com",
    "password_hash": hash_password("Test1234"),
    "name": "Test User",
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
}


@pytest.fixture
async def test_user():
    """Insert a test user into the mock DB and return it."""
    await _mock_db.users.insert_one({**TEST_USER})
    return TEST_USER


@pytest.fixture
def auth_headers(test_user):
    """Return Authorization headers with a valid access token."""
    token = create_access_token(str(TEST_USER_ID))
    return {"Authorization": f"Bearer {token}"}


# --- FastAPI test client ---

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# --- OpenAI mock ---

@pytest.fixture
def mock_openai():
    """Patch the OpenAI client with an AsyncMock."""
    with patch("app.core.clients.openai_client") as m:
        yield m
