import pytest
from fastapi import HTTPException

from app.core.auth import verify_api_key
from app.core.config import settings


@pytest.mark.asyncio
async def test_auth_disabled_when_no_key():
    original = settings.api_key
    settings.api_key = ""
    try:
        await verify_api_key(None)  # Should not raise
        await verify_api_key("anything")  # Should not raise
    finally:
        settings.api_key = original


@pytest.mark.asyncio
async def test_auth_rejects_wrong_key():
    original = settings.api_key
    settings.api_key = "correct-key"
    try:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key("wrong-key")
        assert exc_info.value.status_code == 401
    finally:
        settings.api_key = original


@pytest.mark.asyncio
async def test_auth_rejects_missing_key():
    original = settings.api_key
    settings.api_key = "correct-key"
    try:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(None)
        assert exc_info.value.status_code == 401
    finally:
        settings.api_key = original


@pytest.mark.asyncio
async def test_auth_accepts_correct_key():
    original = settings.api_key
    settings.api_key = "correct-key"
    try:
        await verify_api_key("correct-key")  # Should not raise
    finally:
        settings.api_key = original
