"""
Loader tests: PDF, TXT, DOCX text extraction.
"""
import tempfile
from pathlib import Path

import pytest

from app.rag.loader import DocumentPage, load_document


def test_load_txt():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
        f.write("Hello legal world.")
        f.flush()
        pages = load_document(f.name)

    assert len(pages) == 1
    assert pages[0].text == "Hello legal world."
    assert pages[0].metadata["page"] == 1
    Path(f.name).unlink()


def test_load_txt_empty():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
        f.write("")
        f.flush()
        pages = load_document(f.name)

    assert len(pages) == 1
    Path(f.name).unlink()


def test_load_unsupported():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"a,b,c")
        f.flush()
        with pytest.raises(ValueError, match="Unsupported file type"):
            load_document(f.name)
    Path(f.name).unlink()


def test_load_docx():
    from docx import Document

    doc = Document()
    doc.add_paragraph("Legal clause one.")
    doc.add_paragraph("Legal clause two.")

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        doc.save(f.name)
        pages = load_document(f.name)

    assert len(pages) >= 1
    full_text = " ".join(p.text for p in pages)
    assert "Legal clause one." in full_text
    assert "Legal clause two." in full_text
    Path(f.name).unlink()
