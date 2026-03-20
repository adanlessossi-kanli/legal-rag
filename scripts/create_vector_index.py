"""Create the Atlas Vector Search index on a local mongodb-atlas-local container.

Usage:
    python scripts/create_vector_index.py

Requires: pymongo (installed with the backend dependencies).
"""

import sys
from pymongo import MongoClient
from pymongo.errors import OperationFailure

MONGODB_URI = "mongodb://localhost:27017/?directConnection=true"
DB_NAME = "legal_rag"
COLLECTION = "chunks"
INDEX_NAME = "vector_index"

INDEX_DEFINITION = {
    "name": INDEX_NAME,
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": 1536,
                "similarity": "cosine",
            },
            {
                "type": "filter",
                "path": "user_id",
            },
            {
                "type": "filter",
                "path": "org_id",
            },
            {
                "type": "filter",
                "path": "doc_id",
            },
        ],
    },
}


def main():
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION]

    # Ensure the collection exists (insert + delete a dummy doc)
    collection.insert_one({"_init": True})
    collection.delete_one({"_init": True})

    try:
        collection.create_search_index(INDEX_DEFINITION)
        print(f"OK: Vector search index '{INDEX_NAME}' created on {DB_NAME}.{COLLECTION}")
    except OperationFailure as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print(f"OK: Vector search index '{INDEX_NAME}' already exists")
        else:
            print(f"FAILED: {e}", file=sys.stderr)
            sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
