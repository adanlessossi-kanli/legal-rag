"""Relevance feedback — users can rate answers to improve retrieval over time."""

import logging
from datetime import datetime, timezone

from app.core.database import get_db

logger = logging.getLogger(__name__)


async def submit_feedback(
    user_id: str,
    conversation_id: str,
    message_id: str,
    rating: int,
    comment: str = "",
) -> str:
    """Store user feedback on an answer. Rating: 1 (bad) to 5 (great)."""
    db = get_db()
    result = await db.feedback.insert_one({
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "rating": rating,
        "comment": comment[:500] if comment else "",
        "created_at": datetime.now(timezone.utc),
    })
    logger.info("Feedback recorded: user=%s rating=%d message=%s", user_id, rating, message_id)
    return str(result.inserted_id)


async def get_feedback_stats(user_id: str | None = None, org_id: str | None = None) -> dict:
    """Aggregate feedback statistics."""
    db = get_db()
    match: dict = {}
    if user_id:
        match["user_id"] = user_id

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "avg_rating": {"$avg": "$rating"},
            "count_1": {"$sum": {"$cond": [{"$eq": ["$rating", 1]}, 1, 0]}},
            "count_2": {"$sum": {"$cond": [{"$eq": ["$rating", 2]}, 1, 0]}},
            "count_3": {"$sum": {"$cond": [{"$eq": ["$rating", 3]}, 1, 0]}},
            "count_4": {"$sum": {"$cond": [{"$eq": ["$rating", 4]}, 1, 0]}},
            "count_5": {"$sum": {"$cond": [{"$eq": ["$rating", 5]}, 1, 0]}},
        }},
    ]

    result = {"total": 0, "avg_rating": 0.0, "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}}
    async for doc in db.feedback.aggregate(pipeline):
        result["total"] = doc["total"]
        result["avg_rating"] = round(doc["avg_rating"], 2)
        for i in range(1, 6):
            result["distribution"][i] = doc[f"count_{i}"]
    return result
