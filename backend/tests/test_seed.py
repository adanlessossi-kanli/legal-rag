"""
Context Engine: Seed default blueprints unit tests.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.conftest import _get_mock_db
from app.engine.seed import DEFAULT_BLUEPRINTS, seed_default_blueprints


# --- DEFAULT_BLUEPRINTS structure ---

def test_default_blueprints_count():
    assert len(DEFAULT_BLUEPRINTS) == 3


def test_default_blueprints_have_required_fields():
    for bp in DEFAULT_BLUEPRINTS:
        assert "blueprint_id" in bp
        assert "name" in bp
        assert "description" in bp
        assert "content" in bp
        assert bp["blueprint_id"].startswith("blueprint_")


def test_default_blueprint_ids():
    ids = {bp["blueprint_id"] for bp in DEFAULT_BLUEPRINTS}
    assert ids == {"blueprint_suspense_narrative", "blueprint_technical_explanation", "blueprint_casual_summary"}


def test_default_blueprints_content_has_instruction():
    for bp in DEFAULT_BLUEPRINTS:
        assert "instruction" in bp["content"]
        assert "scene_goal" in bp["content"]
        assert "style_guide" in bp["content"]


# --- seed_default_blueprints ---

async def test_seed_inserts_all_blueprints():
    db = _get_mock_db()

    with patch("app.rag.vectorstore._embed", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        count = await seed_default_blueprints(db)

    assert count == 3
    assert await db.blueprints.count_documents({}) == 3
    assert await db.chunks.count_documents({"namespace": "ContextLibrary"}) == 3


async def test_seed_is_idempotent():
    db = _get_mock_db()

    with patch("app.rag.vectorstore._embed", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        first = await seed_default_blueprints(db)
        second = await seed_default_blueprints(db)

    assert first == 3
    assert second == 0
    assert await db.blueprints.count_documents({}) == 3


async def test_seed_sets_system_user():
    db = _get_mock_db()

    with patch("app.rag.vectorstore._embed", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        await seed_default_blueprints(db)

    async for doc in db.blueprints.find():
        assert doc["user_id"] == "system"
        assert doc["is_default"] is True
        assert doc["org_id"] == ""


async def test_seed_embeds_descriptions():
    db = _get_mock_db()

    with patch("app.rag.vectorstore._embed", new_callable=AsyncMock, return_value=[[0.1] * 1536]) as mock_embed:
        await seed_default_blueprints(db)

    assert mock_embed.call_count == 3
    async for chunk in db.chunks.find({"namespace": "ContextLibrary"}):
        assert chunk["user_id"] == "system"
        assert "blueprint_id" in chunk["metadata"]
        assert chunk["namespace"] == "ContextLibrary"
