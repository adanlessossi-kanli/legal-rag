"""
Integration tests against the real local MongoDB Docker container.

These tests require:
  1. docker compose up -d
  2. python scripts/create_vector_index.py

Run with:  pytest tests/test_integration.py -m integration -v
Skip with: pytest -m "not integration"
"""

import asyncio
import math
import os
import time

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("TEST_MONGODB_URI", "mongodb://localhost:27017/?directConnection=true")
DB_NAME = "legal_rag_integration_test"
COLLECTION = "chunks"
INDEX_NAME = "vector_index"

pytestmark = pytest.mark.integration

# Applied to all async tests/fixtures in this module
_async_mark = pytest.mark.asyncio(loop_scope="module")


def _is_mongo_available() -> bool:
    from pymongo import MongoClient
    try:
        c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        c.admin.command("ping")
        c.close()
        return True
    except Exception:
        return False


skip_no_mongo = pytest.mark.skipif(
    not _is_mongo_available(),
    reason="Local MongoDB not running (docker compose up -d)",
)


@pytest.fixture(autouse=True)
def _patch_db():
    """Override conftest's _patch_db — integration tests use real MongoDB."""
    yield


@pytest.fixture(autouse=True)
def _init_orchestrator():
    """Override conftest's _init_orchestrator — not needed for integration tests."""
    yield


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db():
    client = AsyncIOMotorClient(MONGO_URI)
    database = client[DB_NAME]
    yield database
    await database.drop_collection(COLLECTION)
    client.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def setup_index(db):
    """Create the vector search index on the test database."""
    from pymongo import MongoClient
    sync_client = MongoClient(MONGO_URI)
    sync_db = sync_client[DB_NAME]
    collection = sync_db[COLLECTION]

    # Ensure collection exists
    collection.insert_one({"_init": True})
    collection.delete_one({"_init": True})

    index_def = {
        "name": INDEX_NAME,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {"type": "vector", "path": "embedding", "numDimensions": 3, "similarity": "cosine"},
                {"type": "filter", "path": "user_id"},
                {"type": "filter", "path": "org_id"},
                {"type": "filter", "path": "doc_id"},
            ],
        },
    }

    try:
        collection.create_search_index(index_def)
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise

    # Also create text index for keyword search
    try:
        collection.create_index([("text", "text")], default_language="english")
    except Exception:
        pass  # may already exist

    sync_client.close()

    # Poll until the vector index is queryable (CI runners are slower)
    coll = db[COLLECTION]
    await coll.insert_one({"_probe": True, "embedding": [0.0, 0.0, 0.1], "user_id": "_probe", "org_id": "", "doc_id": ""})
    probe_pipeline = [
        {"$vectorSearch": {"index": INDEX_NAME, "path": "embedding", "queryVector": [0.0, 0.0, 0.1], "numCandidates": 1, "limit": 1}},
    ]
    for _ in range(30):
        try:
            results = [doc async for doc in coll.aggregate(probe_pipeline)]
            if results:
                break
        except Exception:
            pass
        await asyncio.sleep(1)
    await coll.delete_many({"_probe": True})
    yield


def _fake_embedding(seed: float) -> list[float]:
    """Create a deterministic 3D unit-ish vector for testing."""
    angle = seed * 0.5
    return [math.cos(angle), math.sin(angle), 0.1]


# ---------------------------------------------------------------------------
# 1. Basic vector search — user-scoped retrieval
# ---------------------------------------------------------------------------

@skip_no_mongo
@_async_mark
async def test_vector_search_returns_similar_chunks(db, setup_index):
    """End-to-end: insert chunks with embeddings, then $vectorSearch retrieves the most similar."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    chunks = [
        {"chunk_id": "c1", "doc_id": "doc1", "user_id": "user1", "org_id": "", "text": "Liability clause", "embedding": _fake_embedding(0.0), "metadata": {"source": "contract.pdf"}},
        {"chunk_id": "c2", "doc_id": "doc1", "user_id": "user1", "org_id": "", "text": "Payment terms", "embedding": _fake_embedding(3.14), "metadata": {"source": "contract.pdf"}},
        {"chunk_id": "c3", "doc_id": "doc2", "user_id": "user1", "org_id": "", "text": "Indemnification", "embedding": _fake_embedding(0.1), "metadata": {"source": "policy.pdf"}},
        {"chunk_id": "c4", "doc_id": "doc1", "user_id": "user2", "org_id": "", "text": "Other user chunk", "embedding": _fake_embedding(0.0), "metadata": {"source": "other.pdf"}},
    ]
    await coll.insert_many(chunks)
    await asyncio.sleep(1)

    query_vec = _fake_embedding(0.05)
    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vec,
                "numCandidates": 10,
                "limit": 3,
                "filter": {"user_id": "user1"},
            }
        },
        {
            "$project": {
                "chunk_id": 1,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]

    assert len(results) > 0
    returned_ids = {r["chunk_id"] for r in results}
    assert "c4" not in returned_ids, "Should not return other user's chunks"

    if len(results) >= 2:
        assert results[0]["score"] >= results[1]["score"]


# ---------------------------------------------------------------------------
# 2. Document-scoped queries — doc_id filter
# ---------------------------------------------------------------------------

@skip_no_mongo
@_async_mark
async def test_vector_search_with_doc_id_filter(db, setup_index):
    """$vectorSearch respects doc_id filter for document-scoped queries."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    chunks = [
        {"chunk_id": "a1", "doc_id": "docA", "user_id": "u1", "org_id": "", "text": "Alpha clause", "embedding": _fake_embedding(0.0), "metadata": {"source": "alpha.pdf"}},
        {"chunk_id": "b1", "doc_id": "docB", "user_id": "u1", "org_id": "", "text": "Beta clause", "embedding": _fake_embedding(0.0), "metadata": {"source": "beta.pdf"}},
        {"chunk_id": "a2", "doc_id": "docA", "user_id": "u1", "org_id": "", "text": "Alpha section two", "embedding": _fake_embedding(0.1), "metadata": {"source": "alpha.pdf"}},
    ]
    await coll.insert_many(chunks)
    await asyncio.sleep(1)

    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": _fake_embedding(0.0),
                "numCandidates": 10,
                "limit": 5,
                "filter": {"user_id": "u1", "doc_id": {"$in": ["docA"]}},
            }
        },
        {"$project": {"chunk_id": 1, "doc_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    returned_ids = {r["chunk_id"] for r in results}
    assert "a1" in returned_ids
    assert "a2" in returned_ids
    assert "b1" not in returned_ids, "Should not return chunks from excluded documents"


@skip_no_mongo
@_async_mark
async def test_vector_search_multi_doc_filter(db, setup_index):
    """$vectorSearch with multiple doc_ids returns chunks from all specified docs."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    chunks = [
        {"chunk_id": "x1", "doc_id": "d1", "user_id": "u1", "org_id": "", "text": "Doc one", "embedding": _fake_embedding(0.0), "metadata": {}},
        {"chunk_id": "x2", "doc_id": "d2", "user_id": "u1", "org_id": "", "text": "Doc two", "embedding": _fake_embedding(0.0), "metadata": {}},
        {"chunk_id": "x3", "doc_id": "d3", "user_id": "u1", "org_id": "", "text": "Doc three", "embedding": _fake_embedding(0.0), "metadata": {}},
    ]
    await coll.insert_many(chunks)
    await asyncio.sleep(1)

    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": _fake_embedding(0.0),
                "numCandidates": 10,
                "limit": 5,
                "filter": {"user_id": "u1", "doc_id": {"$in": ["d1", "d2"]}},
            }
        },
        {"$project": {"chunk_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    returned_ids = {r["chunk_id"] for r in results}
    assert "x1" in returned_ids
    assert "x2" in returned_ids
    assert "x3" not in returned_ids


# ---------------------------------------------------------------------------
# 3. Organization-scoped retrieval — org_id filter
# ---------------------------------------------------------------------------

@skip_no_mongo
@_async_mark
async def test_vector_search_org_scoped(db, setup_index):
    """org_id filter returns all org members' chunks, not just the querying user's."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    chunks = [
        {"chunk_id": "org1", "doc_id": "d1", "user_id": "alice", "org_id": "org_abc", "text": "Alice contract", "embedding": _fake_embedding(0.0), "metadata": {"source": "alice.pdf"}},
        {"chunk_id": "org2", "doc_id": "d2", "user_id": "bob", "org_id": "org_abc", "text": "Bob contract", "embedding": _fake_embedding(0.1), "metadata": {"source": "bob.pdf"}},
        {"chunk_id": "org3", "doc_id": "d3", "user_id": "charlie", "org_id": "org_xyz", "text": "Charlie contract", "embedding": _fake_embedding(0.0), "metadata": {"source": "charlie.pdf"}},
        {"chunk_id": "org4", "doc_id": "d4", "user_id": "alice", "org_id": "", "text": "Alice personal", "embedding": _fake_embedding(0.0), "metadata": {"source": "personal.pdf"}},
    ]
    await coll.insert_many(chunks)
    await asyncio.sleep(1)

    # Query scoped to org_abc — should return alice's and bob's chunks, not charlie's or personal
    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": _fake_embedding(0.0),
                "numCandidates": 10,
                "limit": 5,
                "filter": {"org_id": "org_abc"},
            }
        },
        {"$project": {"chunk_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    returned_ids = {r["chunk_id"] for r in results}
    assert "org1" in returned_ids, "Should include alice's org chunk"
    assert "org2" in returned_ids, "Should include bob's org chunk"
    assert "org3" not in returned_ids, "Should not include other org's chunk"
    assert "org4" not in returned_ids, "Should not include personal (no org) chunk"


@skip_no_mongo
@_async_mark
async def test_vector_search_org_with_doc_filter(db, setup_index):
    """org_id + doc_id filter narrows to specific docs within the org."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    chunks = [
        {"chunk_id": "od1", "doc_id": "dA", "user_id": "u1", "org_id": "org1", "text": "Doc A", "embedding": _fake_embedding(0.0), "metadata": {}},
        {"chunk_id": "od2", "doc_id": "dB", "user_id": "u2", "org_id": "org1", "text": "Doc B", "embedding": _fake_embedding(0.0), "metadata": {}},
    ]
    await coll.insert_many(chunks)
    await asyncio.sleep(1)

    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": _fake_embedding(0.0),
                "numCandidates": 10,
                "limit": 5,
                "filter": {"org_id": "org1", "doc_id": {"$in": ["dA"]}},
            }
        },
        {"$project": {"chunk_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    returned_ids = {r["chunk_id"] for r in results}
    assert "od1" in returned_ids
    assert "od2" not in returned_ids


# ---------------------------------------------------------------------------
# 4. Score ordering
# ---------------------------------------------------------------------------

@skip_no_mongo
@_async_mark
async def test_vector_search_score_ordering(db, setup_index):
    """Results are ordered by descending similarity score."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    await coll.insert_many([
        {"chunk_id": f"s{i}", "doc_id": "d1", "user_id": "u1", "org_id": "", "text": f"chunk {i}", "embedding": _fake_embedding(i * 0.5), "metadata": {}}
        for i in range(5)
    ])
    await asyncio.sleep(1)

    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": _fake_embedding(0.0),
                "numCandidates": 20,
                "limit": 5,
            }
        },
        {"$project": {"chunk_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), "Results should be ordered by descending score"


# ---------------------------------------------------------------------------
# 5. Empty collection
# ---------------------------------------------------------------------------

@skip_no_mongo
@_async_mark
async def test_vector_search_empty_collection(db, setup_index):
    """$vectorSearch on empty collection returns no results."""
    coll = db[COLLECTION]
    await coll.delete_many({})
    await asyncio.sleep(1)

    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": _fake_embedding(0.0),
                "numCandidates": 10,
                "limit": 5,
            }
        },
        {"$project": {"chunk_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    assert results == []


# ---------------------------------------------------------------------------
# 6. Keyword search (text index)
# ---------------------------------------------------------------------------

@skip_no_mongo
@_async_mark
async def test_keyword_search_returns_matching_chunks(db, setup_index):
    """MongoDB $text search returns chunks matching keywords."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    chunks = [
        {"chunk_id": "k1", "doc_id": "d1", "user_id": "u1", "org_id": "", "text": "The liability clause limits total damages to contract value", "embedding": _fake_embedding(0.0), "metadata": {}},
        {"chunk_id": "k2", "doc_id": "d1", "user_id": "u1", "org_id": "", "text": "Payment shall be made within thirty days of invoice", "embedding": _fake_embedding(1.0), "metadata": {}},
        {"chunk_id": "k3", "doc_id": "d1", "user_id": "u1", "org_id": "", "text": "Indemnification for liability arising from negligence", "embedding": _fake_embedding(2.0), "metadata": {}},
    ]
    await coll.insert_many(chunks)

    # Text search for "liability"
    pipeline = [
        {"$match": {"user_id": "u1", "$text": {"$search": "liability"}}},
        {"$addFields": {"score": {"$meta": "textScore"}}},
        {"$sort": {"score": -1}},
        {"$limit": 5},
        {"$project": {"chunk_id": 1, "text": 1, "score": 1}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    returned_ids = {r["chunk_id"] for r in results}
    assert "k1" in returned_ids, "Should match 'liability clause'"
    assert "k3" in returned_ids, "Should match 'liability arising'"
    assert "k2" not in returned_ids, "Should not match payment terms"


@skip_no_mongo
@_async_mark
async def test_keyword_search_user_scoped(db, setup_index):
    """Keyword search respects user_id scoping."""
    coll = db[COLLECTION]
    await coll.delete_many({})

    chunks = [
        {"chunk_id": "ku1", "doc_id": "d1", "user_id": "alice", "org_id": "", "text": "Liability clause for Alice", "embedding": _fake_embedding(0.0), "metadata": {}},
        {"chunk_id": "ku2", "doc_id": "d2", "user_id": "bob", "org_id": "", "text": "Liability clause for Bob", "embedding": _fake_embedding(0.0), "metadata": {}},
    ]
    await coll.insert_many(chunks)

    pipeline = [
        {"$match": {"user_id": "alice", "$text": {"$search": "liability"}}},
        {"$project": {"chunk_id": 1}},
    ]

    results = [doc async for doc in coll.aggregate(pipeline)]
    returned_ids = {r["chunk_id"] for r in results}
    assert "ku1" in returned_ids
    assert "ku2" not in returned_ids


# ---------------------------------------------------------------------------
# 7. Hybrid merge (Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------

def test_rrf_merge_deduplicates():
    """RRF merge combines vector and keyword results without duplicates."""
    from app.rag.vectorstore import _merge_results

    vector = [
        {"chunk_id": "c1", "text": "a", "metadata": {}, "score": 0.9},
        {"chunk_id": "c2", "text": "b", "metadata": {}, "score": 0.8},
    ]
    keyword = [
        {"chunk_id": "c2", "text": "b", "metadata": {}, "score": 5.0},
        {"chunk_id": "c3", "text": "c", "metadata": {}, "score": 3.0},
    ]

    merged = _merge_results(vector, keyword, top_k=3)
    ids = [c["chunk_id"] for c in merged]

    # c2 appears in both → should have highest RRF score
    assert ids[0] == "c2", "Chunk appearing in both lists should rank first"
    assert len(ids) == len(set(ids)), "No duplicates"
    assert len(ids) == 3


def test_rrf_merge_respects_top_k():
    """RRF merge limits output to top_k."""
    from app.rag.vectorstore import _merge_results

    vector = [{"chunk_id": f"v{i}", "text": f"v{i}", "metadata": {}, "score": 0.9 - i * 0.1} for i in range(5)]
    keyword = [{"chunk_id": f"k{i}", "text": f"k{i}", "metadata": {}, "score": 5.0 - i} for i in range(5)]

    merged = _merge_results(vector, keyword, top_k=3)
    assert len(merged) == 3


def test_rrf_merge_empty_keyword():
    """RRF merge works when keyword results are empty."""
    from app.rag.vectorstore import _merge_results

    vector = [
        {"chunk_id": "c1", "text": "a", "metadata": {}, "score": 0.9},
    ]
    merged = _merge_results(vector, [], top_k=5)
    assert len(merged) == 1
    assert merged[0]["chunk_id"] == "c1"


def test_rrf_merge_empty_vector():
    """RRF merge works when vector results are empty."""
    from app.rag.vectorstore import _merge_results

    keyword = [
        {"chunk_id": "c1", "text": "a", "metadata": {}, "score": 5.0},
    ]
    merged = _merge_results([], keyword, top_k=5)
    assert len(merged) == 1


# ---------------------------------------------------------------------------
# 8. Ingestion queue retry delay
# ---------------------------------------------------------------------------

def test_retry_delay_exponential_backoff():
    """Retry delay uses exponential backoff capped at 10 minutes."""
    from app.core.ingestion_queue import _retry_delay

    d1 = _retry_delay(1)  # base * 2^0 = 30
    d2 = _retry_delay(2)  # base * 2^1 = 60
    d3 = _retry_delay(3)  # base * 2^2 = 120

    assert d1 < d2 < d3, "Delay should increase with attempts"
    assert d1 == 30  # default base
    assert _retry_delay(100) <= 600, "Should be capped at 10 minutes"


# ---------------------------------------------------------------------------
# 9. Document-scoped query validation (unit-level, no Docker needed)
# ---------------------------------------------------------------------------

def test_scope_filter_user_only():
    """Scope filter with user_id only."""
    from app.rag.vectorstore import _build_scope_filter
    f = _build_scope_filter("user1", None, None)
    assert f == {"user_id": "user1"}


def test_scope_filter_org_overrides_user():
    """When org_id is present, it takes precedence over user_id."""
    from app.rag.vectorstore import _build_scope_filter
    f = _build_scope_filter("user1", None, "org1")
    assert f == {"org_id": "org1"}
    assert "user_id" not in f


def test_scope_filter_with_doc_ids():
    """Document IDs are added to the filter."""
    from app.rag.vectorstore import _build_scope_filter
    f = _build_scope_filter("user1", ["d1", "d2"], None)
    assert f == {"user_id": "user1", "doc_id": {"$in": ["d1", "d2"]}}


def test_scope_filter_org_with_doc_ids():
    """Org + doc_ids filter."""
    from app.rag.vectorstore import _build_scope_filter
    f = _build_scope_filter("user1", ["d1"], "org1")
    assert f == {"org_id": "org1", "doc_id": {"$in": ["d1"]}}
