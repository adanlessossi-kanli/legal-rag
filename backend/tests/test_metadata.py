import os
import tempfile

# Override upload dir before importing metadata
_tmp = tempfile.mkdtemp()
os.environ["UPLOAD_DIR"] = _tmp

# Force reimport with fresh DB path
import importlib
import app.core.metadata as metadata_mod

metadata_mod._DB_PATH = metadata_mod.Path(_tmp) / "test_metadata.db"
metadata_mod._init_db()


def test_save_and_get():
    metadata_mod.save_document("doc_1", "test.pdf", 10, "ready", "hash1")
    doc = metadata_mod.get_document("doc_1")
    assert doc is not None
    assert doc["name"] == "test.pdf"
    assert doc["chunk_count"] == 10
    assert doc["status"] == "ready"
    assert doc["content_hash"] == "hash1"


def test_get_all():
    metadata_mod.save_document("doc_2", "a.pdf", 5, "ready", "hash2")
    docs = metadata_mod.get_all_documents()
    ids = [d["id"] for d in docs]
    assert "doc_2" in ids


def test_delete():
    metadata_mod.save_document("doc_del", "del.pdf", 1, "ready", "hashd")
    assert metadata_mod.delete_document("doc_del") is True
    assert metadata_mod.get_document("doc_del") is None


def test_delete_nonexistent():
    assert metadata_mod.delete_document("doc_nope") is False


def test_update_status():
    metadata_mod.save_document("doc_s", "s.pdf", 1, "processing", "hashs")
    metadata_mod.update_status("doc_s", "ready")
    doc = metadata_mod.get_document("doc_s")
    assert doc["status"] == "ready"


def test_find_by_hash():
    metadata_mod.save_document("doc_h", "h.pdf", 1, "ready", "unique_hash")
    found = metadata_mod.find_by_hash("unique_hash")
    assert found is not None
    assert found["id"] == "doc_h"
    assert metadata_mod.find_by_hash("nonexistent") is None
