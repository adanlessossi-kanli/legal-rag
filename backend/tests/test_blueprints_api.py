"""
Context Engine: Blueprints API unit tests.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from tests.conftest import TEST_USER_ID, _get_mock_db


@pytest.fixture
def mock_embed():
    with patch("app.api.blueprints._embed", new_callable=AsyncMock, return_value=[[0.1] * 1536]) as m:
        yield m


# --- Create ---

async def test_create_blueprint(client, auth_headers, mock_embed):
    resp = client.post("/api/blueprints", json={
        "name": "Test Blueprint",
        "description": "A test blueprint for unit testing",
        "content": {"scene_goal": "test", "instruction": "do stuff"},
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Blueprint"
    assert data["blueprint_id"].startswith("bp_")
    assert data["is_default"] is False
    mock_embed.assert_called_once()


async def test_create_blueprint_unauthenticated(client):
    resp = client.post("/api/blueprints", json={
        "name": "Test", "description": "desc", "content": {},
    })
    assert resp.status_code == 401


async def test_create_blueprint_validates_empty_name(client, auth_headers):
    resp = client.post("/api/blueprints", json={
        "name": "", "description": "desc", "content": {},
    }, headers=auth_headers)
    assert resp.status_code == 422


async def test_create_blueprint_validates_long_description(client, auth_headers):
    resp = client.post("/api/blueprints", json={
        "name": "Test", "description": "x" * 2001, "content": {},
    }, headers=auth_headers)
    assert resp.status_code == 422


# --- List ---

async def test_list_blueprints_empty(client, auth_headers):
    resp = client.get("/api/blueprints", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_blueprints_includes_own(client, auth_headers, mock_embed):
    client.post("/api/blueprints", json={
        "name": "My BP", "description": "mine", "content": {"instruction": "test"},
    }, headers=auth_headers)

    resp = client.get("/api/blueprints", headers=auth_headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "My BP"
    assert data["items"][0]["content"] is None  # content omitted in list


async def test_list_blueprints_includes_defaults(client, auth_headers):
    db = _get_mock_db()
    await db.blueprints.insert_one({
        "blueprint_id": "bp_default", "name": "Default", "description": "system bp",
        "content": {}, "user_id": "system", "org_id": "", "is_default": True,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    })

    resp = client.get("/api/blueprints", headers=auth_headers)
    data = resp.json()
    assert data["total"] == 1
    names = [item["name"] for item in data["items"]]
    assert "Default" in names


async def test_list_blueprints_pagination(client, auth_headers, mock_embed):
    for i in range(3):
        client.post("/api/blueprints", json={
            "name": f"BP {i}", "description": f"desc {i}", "content": {},
        }, headers=auth_headers)

    resp = client.get("/api/blueprints?page=1&page_size=2", headers=auth_headers)
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


# --- Get ---

async def test_get_blueprint(client, auth_headers, mock_embed):
    create_resp = client.post("/api/blueprints", json={
        "name": "Detail BP", "description": "detailed", "content": {"scene_goal": "test"},
    }, headers=auth_headers)
    bp_id = create_resp.json()["blueprint_id"]

    resp = client.get(f"/api/blueprints/{bp_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["blueprint_id"] == bp_id
    assert data["content"] == {"scene_goal": "test"}


async def test_get_blueprint_not_found(client, auth_headers):
    resp = client.get("/api/blueprints/bp_nonexistent", headers=auth_headers)
    assert resp.status_code == 404


# --- Update ---

async def test_update_blueprint(client, auth_headers, mock_embed):
    create_resp = client.post("/api/blueprints", json={
        "name": "Original", "description": "original desc", "content": {"instruction": "old"},
    }, headers=auth_headers)
    bp_id = create_resp.json()["blueprint_id"]

    resp = client.put(f"/api/blueprints/{bp_id}", json={
        "name": "Updated",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


async def test_update_blueprint_re_embeds_on_description_change(client, auth_headers, mock_embed):
    create_resp = client.post("/api/blueprints", json={
        "name": "BP", "description": "original", "content": {},
    }, headers=auth_headers)
    bp_id = create_resp.json()["blueprint_id"]
    mock_embed.reset_mock()

    client.put(f"/api/blueprints/{bp_id}", json={
        "description": "new description",
    }, headers=auth_headers)

    mock_embed.assert_called_once()


async def test_update_default_blueprint_forbidden(client, auth_headers):
    db = _get_mock_db()
    await db.blueprints.insert_one({
        "blueprint_id": "bp_sys", "name": "System", "description": "system",
        "content": {}, "user_id": "system", "org_id": "", "is_default": True,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    })

    resp = client.put("/api/blueprints/bp_sys", json={"name": "Hacked"}, headers=auth_headers)
    assert resp.status_code == 403


async def test_update_other_users_blueprint_forbidden(client, auth_headers):
    db = _get_mock_db()
    await db.blueprints.insert_one({
        "blueprint_id": "bp_other", "name": "Other", "description": "other",
        "content": {}, "user_id": "other_user", "org_id": "", "is_default": False,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    })

    resp = client.put("/api/blueprints/bp_other", json={"name": "Stolen"}, headers=auth_headers)
    assert resp.status_code == 403


async def test_update_nonexistent_blueprint(client, auth_headers):
    resp = client.put("/api/blueprints/bp_ghost", json={"name": "X"}, headers=auth_headers)
    assert resp.status_code == 404


# --- Delete ---

async def test_delete_blueprint(client, auth_headers, mock_embed):
    create_resp = client.post("/api/blueprints", json={
        "name": "To Delete", "description": "delete me", "content": {},
    }, headers=auth_headers)
    bp_id = create_resp.json()["blueprint_id"]

    resp = client.delete(f"/api/blueprints/{bp_id}", headers=auth_headers)
    assert resp.status_code == 204

    get_resp = client.get(f"/api/blueprints/{bp_id}", headers=auth_headers)
    assert get_resp.status_code == 404


async def test_delete_default_blueprint_forbidden(client, auth_headers):
    db = _get_mock_db()
    await db.blueprints.insert_one({
        "blueprint_id": "bp_nodelete", "name": "Protected", "description": "no",
        "content": {}, "user_id": "system", "org_id": "", "is_default": True,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    })

    resp = client.delete("/api/blueprints/bp_nodelete", headers=auth_headers)
    assert resp.status_code == 403


async def test_delete_nonexistent_returns_404(client, auth_headers):
    resp = client.delete("/api/blueprints/bp_gone", headers=auth_headers)
    assert resp.status_code == 404


async def test_delete_other_users_blueprint_forbidden(client, auth_headers):
    db = _get_mock_db()
    await db.blueprints.insert_one({
        "blueprint_id": "bp_notmine", "name": "Not Mine", "description": "nope",
        "content": {}, "user_id": "someone_else", "org_id": "", "is_default": False,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    })

    resp = client.delete("/api/blueprints/bp_notmine", headers=auth_headers)
    assert resp.status_code == 403
