import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD) — configurable via settings
PRICING = {
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "text-embedding-3-small": {"prompt": 0.02, "completion": 0.0},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prices = PRICING.get(model, {"prompt": 0.0, "completion": 0.0})
    return (prompt_tokens * prices["prompt"] + completion_tokens * prices["completion"]) / 1_000_000


async def record_usage(
    user_id: str,
    model: str,
    operation: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    cost = _estimate_cost(model, prompt_tokens, completion_tokens)
    db = get_db()
    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")

    await db.usage.insert_one({
        "user_id": user_id,
        "model": model,
        "operation": operation,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": cost,
        "month": month_key,
        "created_at": now,
    })


async def get_user_usage(user_id: str, month: str | None = None) -> dict:
    db = get_db()
    match_filter: dict = {"user_id": user_id}
    if month:
        match_filter["month"] = month
    else:
        match_filter["month"] = datetime.now(timezone.utc).strftime("%Y-%m")

    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$model",
            "prompt_tokens": {"$sum": "$prompt_tokens"},
            "completion_tokens": {"$sum": "$completion_tokens"},
            "total_tokens": {"$sum": "$total_tokens"},
            "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
            "request_count": {"$sum": 1},
        }},
    ]

    by_model = {}
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0, "request_count": 0}

    async for doc in db.usage.aggregate(pipeline):
        model = doc["_id"]
        by_model[model] = {
            "prompt_tokens": doc["prompt_tokens"],
            "completion_tokens": doc["completion_tokens"],
            "total_tokens": doc["total_tokens"],
            "estimated_cost_usd": round(doc["estimated_cost_usd"], 6),
            "request_count": doc["request_count"],
        }
        for k in totals:
            totals[k] += doc[k]

    totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 6)
    return {"month": match_filter["month"], "by_model": by_model, "totals": totals}
