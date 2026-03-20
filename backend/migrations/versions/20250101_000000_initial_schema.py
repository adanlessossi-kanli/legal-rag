"""Initial schema — creates all MongoDB indexes and the vector search index.

This captures the baseline schema that was previously applied at app startup in database.py.
"""


async def up(db):
    # Users
    await db.users.create_index("email", unique=True)

    # Documents
    await db.documents.create_index("doc_id", unique=True)
    await db.documents.create_index("user_id")
    await db.documents.create_index([("user_id", 1), ("content_hash", 1)], unique=True)

    # Conversations
    await db.conversations.create_index("user_id")
    await db.conversations.create_index([("user_id", 1), ("updated_at", -1)])

    # Messages
    await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])

    # Refresh tokens
    await db.refresh_tokens.create_index("token_hash", unique=True)
    await db.refresh_tokens.create_index("user_id")
    await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)

    # Chunks
    await db.chunks.create_index("doc_id")
    await db.chunks.create_index("user_id")
    await db.chunks.create_index("org_id")
    await db.chunks.create_index("chunk_id")
    await db.chunks.create_index([("text", "text")], default_language="english")

    # Usage
    await db.usage.create_index([("user_id", 1), ("month", 1)])
    await db.usage.create_index("created_at")

    # Organizations
    await db.organizations.create_index("owner_id")
    await db.org_members.create_index([("org_id", 1), ("user_id", 1)], unique=True)
    await db.org_members.create_index("user_id")

    # Ingestion queue
    await db.ingestion_queue.create_index("status")

    # Migration tracking
    await db.get_collection("_migrations").create_index("name", unique=True)
