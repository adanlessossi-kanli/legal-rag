import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def _build_uri() -> str:
    client_id = settings.mongodb_client_id
    client_secret = settings.mongodb_client_secret
    host = settings.mongodb_host
    port = settings.mongodb_port
    options = settings.mongodb_options

    if client_id and client_secret:
        # Atlas service account OIDC auth
        if host.endswith(".mongodb.net") or host.startswith("mongodb+srv"):
            host = host.removeprefix("mongodb+srv://")
            base = f"mongodb+srv://{client_id}:{client_secret}@{host}"
        else:
            base = f"mongodb://{client_id}:{client_secret}@{host}:{port}"
        oidc_params = "authMechanism=MONGODB-OIDC&authMechanismProperties=ENVIRONMENT:azure,TOKEN_RESOURCE:https://cloud.mongodb.com"
        options = f"{options}&{oidc_params}" if options else oidc_params
    else:
        base = f"mongodb://{host}:{port}"
        # Local atlas-local container uses a replica set with internal hostname
        if not options:
            options = "directConnection=true"

    return f"{base}/?{options}" if options else base


async def connect_db() -> None:
    global _client, _db
    uri = _build_uri()
    _client = AsyncIOMotorClient(uri)
    _db = _client[settings.mongodb_db]

    # Create indexes
    await _db.users.create_index("email", unique=True)
    await _db.documents.create_index("doc_id", unique=True)
    await _db.documents.create_index("user_id")
    await _db.documents.create_index([("user_id", 1), ("content_hash", 1)], unique=True)
    await _db.conversations.create_index("user_id")
    await _db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
    await _db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await _db.refresh_tokens.create_index("token_hash", unique=True)
    await _db.refresh_tokens.create_index("user_id")
    await _db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
    await _db.chunks.create_index("doc_id")
    await _db.chunks.create_index("user_id")
    await _db.chunks.create_index("org_id")
    await _db.chunks.create_index("chunk_id")
    # Text index for hybrid keyword search
    await _db.chunks.create_index([("text", "text")], default_language="english")
    await _db.usage.create_index([("user_id", 1), ("month", 1)])
    await _db.usage.create_index("created_at")
    await _db.organizations.create_index("owner_id")
    await _db.org_members.create_index([("org_id", 1), ("user_id", 1)], unique=True)
    await _db.org_members.create_index("user_id")

    # Blueprints (Context Engine)
    await _db.blueprints.create_index("blueprint_id", unique=True)
    await _db.blueprints.create_index("user_id")
    await _db.blueprints.create_index("org_id")
    await _db.blueprints.create_index("is_default")
    await _db.chunks.create_index("namespace")

    # Audit log
    await _db.audit_log.create_index("user_id")
    await _db.audit_log.create_index("org_id")
    await _db.audit_log.create_index("action")
    await _db.audit_log.create_index("created_at")
    await _db.audit_log.create_index([("created_at", 1)], expireAfterSeconds=90 * 86400)  # 90 days

    # Feedback
    await _db.feedback.create_index("user_id")
    await _db.feedback.create_index("conversation_id")
    await _db.feedback.create_index("created_at")

    # Document versions
    await _db.document_versions.create_index("doc_id")
    await _db.document_versions.create_index([("doc_id", 1), ("version", -1)])

    # Document search: text index on name
    await _db.documents.create_index([("name", "text")])
    await _db.documents.create_index("uploaded_at")

    logger.info("Connected to MongoDB at %s", settings.mongodb_host)
    logger.info(
        "NOTE: You must create an Atlas Vector Search index named '%s' on the "
        "'chunks' collection. See README for instructions.",
        settings.vector_search_index,
    )


async def close_db() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
    logger.info("Disconnected from MongoDB")


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return _db
