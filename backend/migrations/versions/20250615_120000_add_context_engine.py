"""Add Context Engine: namespace field on chunks, blueprints collection, seed defaults."""


async def up(db):
    # 1. Tag existing chunks with KnowledgeStore namespace
    result = await db.chunks.update_many(
        {"namespace": {"$exists": False}},
        {"$set": {"namespace": "KnowledgeStore"}},
    )
    if result.modified_count:
        print(f"  Tagged {result.modified_count} existing chunks with namespace=KnowledgeStore")

    # 2. Create blueprints collection indexes
    await db.blueprints.create_index("blueprint_id", unique=True)
    await db.blueprints.create_index("user_id")
    await db.blueprints.create_index("org_id")
    await db.blueprints.create_index("is_default")
    print("  Created blueprints indexes")

    # 3. Namespace index on chunks
    await db.chunks.create_index("namespace")
    print("  Created namespace index on chunks")

    # 4. Seed default blueprints
    from app.engine.seed import seed_default_blueprints
    seeded = await seed_default_blueprints(db)
    print(f"  Seeded {seeded} default blueprints")
