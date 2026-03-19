from app.rag.chunker import Chunk, chunk_pages
from app.rag.loader import DocumentPage


def test_chunk_pages_basic():
    pages = [DocumentPage(text="Hello world. " * 200, metadata={"source": "test.txt", "page": 1})]
    chunks = chunk_pages(pages, "doc_test")
    assert len(chunks) > 1
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(c.metadata["doc_id"] == "doc_test" for c in chunks)
    assert all(c.metadata["source"] == "test.txt" for c in chunks)


def test_chunk_pages_empty():
    chunks = chunk_pages([], "doc_empty")
    assert chunks == []


def test_chunk_pages_short_text():
    pages = [DocumentPage(text="Short text.", metadata={"source": "s.txt", "page": 1})]
    chunks = chunk_pages(pages, "doc_short")
    assert len(chunks) == 1
    assert chunks[0].text == "Short text."


def test_chunk_ids_unique():
    pages = [DocumentPage(text="Word " * 500, metadata={"source": "t.txt", "page": 1})]
    chunks = chunk_pages(pages, "doc_u")
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
