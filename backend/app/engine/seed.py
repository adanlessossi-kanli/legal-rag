"""Default seed blueprints for the ContextLibrary."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_BLUEPRINTS = [
    {
        "blueprint_id": "blueprint_suspense_narrative",
        "name": "Suspense Narrative",
        "description": (
            "A precise Semantic Blueprint designed to generate suspenseful and tense "
            "narratives, suitable for children's stories. Focuses on atmosphere, "
            "perceived threats, and emotional impact. Ideal for creative writing."
        ),
        "content": {
            "scene_goal": "Increase tension and create suspense.",
            "style_guide": (
                "Use short, sharp sentences. Focus on sensory details (sounds, shadows). "
                "Maintain a slightly eerie but age-appropriate tone."
            ),
            "participants": [
                {"role": "Agent", "description": "The protagonist experiencing the events."},
                {"role": "Source_of_Threat", "description": "The underlying danger or mystery."},
            ],
            "instruction": (
                "Rewrite the provided facts into a narrative adhering strictly "
                "to the scene_goal and style_guide."
            ),
        },
    },
    {
        "blueprint_id": "blueprint_technical_explanation",
        "name": "Technical Explanation",
        "description": (
            "A Semantic Blueprint designed for technical explanation or analysis. "
            "This blueprint focuses on clarity, objectivity, and structure. Ideal for "
            "breaking down complex processes, explaining mechanisms, or summarizing "
            "scientific findings."
        ),
        "content": {
            "scene_goal": "Explain the mechanism or findings clearly and concisely.",
            "style_guide": (
                "Maintain an objective and formal tone. Use precise terminology. "
                "Prioritize factual accuracy and clarity over narrative flair."
            ),
            "structure": ["Definition", "Function/Operation", "Key Findings/Impact"],
            "instruction": (
                "Organize the provided facts into the defined structure, "
                "adhering to the style_guide."
            ),
        },
    },
    {
        "blueprint_id": "blueprint_casual_summary",
        "name": "Casual Summary",
        "description": (
            "A goal-oriented context for creating a casual, easy-to-read summary. "
            "Focuses on brevity and accessibility, explaining concepts simply."
        ),
        "content": {
            "scene_goal": "Summarize information quickly and casually.",
            "style_guide": (
                "Use informal language. Keep it brief and engaging. "
                "Imagine explaining it to a friend."
            ),
            "instruction": "Summarize the provided facts using the casual style guide.",
        },
    },
]


async def seed_default_blueprints(db) -> int:
    """Insert default blueprints and their vector entries. Idempotent."""
    from app.rag.vectorstore import _embed

    now = datetime.now(timezone.utc)
    seeded = 0

    for bp in DEFAULT_BLUEPRINTS:
        exists = await db.blueprints.find_one({"blueprint_id": bp["blueprint_id"]})
        if exists:
            continue

        await db.blueprints.insert_one({
            "blueprint_id": bp["blueprint_id"],
            "name": bp["name"],
            "description": bp["description"],
            "content": bp["content"],
            "user_id": "system",
            "org_id": "",
            "is_default": True,
            "created_at": now,
            "updated_at": now,
        })

        embedding = (await _embed([bp["description"]]))[0]
        await db.chunks.insert_one({
            "chunk_id": bp["blueprint_id"],
            "doc_id": bp["blueprint_id"],
            "namespace": "ContextLibrary",
            "user_id": "system",
            "org_id": "",
            "text": bp["description"],
            "embedding": embedding,
            "metadata": {
                "source": bp["name"],
                "blueprint_id": bp["blueprint_id"],
                "namespace": "ContextLibrary",
            },
        })
        seeded += 1
        logger.info("Seeded default blueprint: %s", bp["blueprint_id"])

    if seeded:
        logger.info("Seeded %d default blueprints", seeded)
    return seeded
