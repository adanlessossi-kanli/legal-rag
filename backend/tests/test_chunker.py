"""
REQ-QT-001: Chunking produces correct chunk count and overlap.
"""
from app.core.config import settings
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
    assert chunk_pages([], "doc_empty") == []


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


def test_chunk_size_respects_config():
    """Each chunk should not exceed chunk_size (with some tolerance for splitter)."""
    pages = [DocumentPage(text="A" * 5000, metadata={"source": "big.txt", "page": 1})]
    chunks = chunk_pages(pages, "doc_big")
    for c in chunks:
        assert len(c.text) <= settings.chunk_size + 50  # small tolerance


def test_chunk_overlap_exists():
    """Consecutive chunks should share overlapping text."""
    text = "word " * 600  # enough to produce multiple chunks
    pages = [DocumentPage(text=text, metadata={"source": "o.txt", "page": 1})]
    chunks = chunk_pages(pages, "doc_overlap")
    assert len(chunks) >= 2
    # Check that the end of chunk N overlaps with the start of chunk N+1
    for i in range(len(chunks) - 1):
        tail = chunks[i].text[-settings.chunk_overlap:]
        head = chunks[i + 1].text[:settings.chunk_overlap]
        # At least some substring should be shared
        overlap = set(tail.split()) & set(head.split())
        assert len(overlap) > 0, f"No overlap between chunk {i} and {i+1}"


def test_chunk_preserves_page_metadata():
    pages = [
        DocumentPage(text="Page one. " * 200, metadata={"source": "multi.pdf", "page": 1}),
        DocumentPage(text="Page two. " * 200, metadata={"source": "multi.pdf", "page": 2}),
    ]
    chunks = chunk_pages(pages, "doc_multi")
    page_numbers = {c.metadata["page"] for c in chunks}
    assert 1 in page_numbers
    assert 2 in page_numbers
