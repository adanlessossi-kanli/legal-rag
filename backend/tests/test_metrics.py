"""
Tests for Prometheus metrics endpoint and per-user cost tracking.
"""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


# --- Metrics endpoint ---

def test_metrics_endpoint_returns_prometheus_format(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "http_request" in body or "python_info" in body


# --- Usage tracking ---

async def test_record_usage_stores_in_db():
    from app.core.usage import record_usage, get_user_usage

    await record_usage("user123", "gpt-4o", "generate", 500, 100)
    await record_usage("user123", "gpt-4o-mini", "rewrite", 200, 50)

    result = await get_user_usage("user123")
    assert result["totals"]["request_count"] == 2
    assert result["totals"]["prompt_tokens"] == 700
    assert result["totals"]["completion_tokens"] == 150
    assert result["totals"]["estimated_cost_usd"] > 0
    assert "gpt-4o" in result["by_model"]


async def test_get_usage_filters_by_month():
    from app.core.usage import record_usage, get_user_usage

    await record_usage("user456", "gpt-4o", "generate", 100, 50)

    result = await get_user_usage("user456", "2020-01")
    assert result["totals"]["request_count"] == 0


async def test_usage_cost_estimation():
    from app.core.usage import _estimate_cost

    # gpt-4o: $2.50/1M prompt, $10.00/1M completion
    cost = _estimate_cost("gpt-4o", 1_000_000, 1_000_000)
    assert abs(cost - 12.50) < 0.01

    # Unknown model returns 0
    assert _estimate_cost("unknown-model", 1000, 1000) == 0.0


def test_usage_endpoint_requires_auth(client):
    resp = client.get("/api/usage")
    assert resp.status_code == 401


def test_usage_endpoint_returns_data(client, auth_headers):
    resp = client.get("/api/usage", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "totals" in data
    assert "month" in data


def test_usage_endpoint_validates_month_format(client, auth_headers):
    resp = client.get("/api/usage?month=invalid", headers=auth_headers)
    assert resp.status_code == 422
