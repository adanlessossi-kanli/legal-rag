"""Lightweight MongoDB migration runner.

Tracks applied migrations in a `_migrations` collection.
Each migration is a Python file in `migrations/versions/` with an `async def up(db)` function.
Files are sorted lexicographically — use a timestamp prefix (e.g. 20250101_000000_description.py).

Usage:
    python migrations/runner.py              # apply pending migrations
    python migrations/runner.py --status     # show migration status
"""

import argparse
import importlib.util
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")

VERSIONS_DIR = Path(__file__).parent / "versions"
COLLECTION = "_migrations"


def _build_uri() -> tuple[str, str]:
    """Build MongoDB URI from env vars (mirrors app.core.database logic)."""
    import os
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")

    host = os.getenv("MONGODB_HOST", "localhost")
    port = os.getenv("MONGODB_PORT", "27017")
    client_id = os.getenv("MONGODB_CLIENT_ID", "")
    client_secret = os.getenv("MONGODB_CLIENT_SECRET", "")
    db_name = os.getenv("MONGODB_DB", "legal_rag")
    options = os.getenv("MONGODB_OPTIONS", "")

    if client_id and client_secret:
        if host.endswith(".mongodb.net") or host.startswith("mongodb+srv"):
            host = host.removeprefix("mongodb+srv://")
            base = f"mongodb+srv://{client_id}:{client_secret}@{host}"
        else:
            base = f"mongodb://{client_id}:{client_secret}@{host}:{port}"
        oidc = "authMechanism=MONGODB-OIDC&authMechanismProperties=ENVIRONMENT:azure,TOKEN_RESOURCE:https://cloud.mongodb.com"
        options = f"{options}&{oidc}" if options else oidc
    else:
        base = f"mongodb://{host}:{port}"
        if not options:
            options = "directConnection=true"

    uri = f"{base}/?{options}" if options else base
    return uri, db_name


def _discover_migrations() -> list[Path]:
    if not VERSIONS_DIR.exists():
        return []
    return sorted(p for p in VERSIONS_DIR.glob("*.py") if not p.name.startswith("_"))


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def get_applied(db) -> set[str]:
    return {doc["name"] async for doc in db[COLLECTION].find({}, {"name": 1})}


async def run_migrations(db) -> int:
    applied = await get_applied(db)
    migrations = _discover_migrations()
    pending = [m for m in migrations if m.stem not in applied]

    if not pending:
        logger.info("No pending migrations")
        return 0

    count = 0
    for path in pending:
        mod = _load_module(path)
        if not hasattr(mod, "up"):
            logger.warning("Skipping %s — no up() function", path.name)
            continue

        logger.info("Applying %s ...", path.stem)
        await mod.up(db)
        await db[COLLECTION].insert_one({
            "name": path.stem,
            "applied_at": datetime.now(timezone.utc),
        })
        count += 1
        logger.info("Applied %s", path.stem)

    logger.info("Applied %d migration(s)", count)
    return count


async def show_status(db):
    applied = await get_applied(db)
    migrations = _discover_migrations()
    for m in migrations:
        status = "applied" if m.stem in applied else "pending"
        print(f"  [{status}] {m.stem}")
    if not migrations:
        print("  No migration files found")


async def main():
    parser = argparse.ArgumentParser(description="MongoDB migration runner")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    args = parser.parse_args()

    uri, db_name = _build_uri()
    client = AsyncIOMotorClient(uri)
    db = client[db_name]

    try:
        if args.status:
            await show_status(db)
        else:
            await run_migrations(db)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
