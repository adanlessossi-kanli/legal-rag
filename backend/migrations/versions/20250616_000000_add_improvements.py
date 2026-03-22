"""Add audit log, feedback, document versioning, and document search indexes."""


async def up(db):
    # Audit log
    await db.audit_log.create_index("user_id")
    await db.audit_log.create_index("org_id")
    await db.audit_log.create_index("action")
    await db.audit_log.create_index("created_at")
    await db.audit_log.create_index([("created_at", 1)], expireAfterSeconds=90 * 86400)

    # Feedback
    await db.feedback.create_index("user_id")
    await db.feedback.create_index("conversation_id")
    await db.feedback.create_index("created_at")

    # Document versions
    await db.document_versions.create_index("doc_id")
    await db.document_versions.create_index([("doc_id", 1), ("version", -1)])

    # Document search
    await db.documents.create_index("uploaded_at")
