import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)


@dataclass
class DocumentPage:
    text: str
    metadata: dict = field(default_factory=dict)


def load_document(file_path: str) -> list[DocumentPage]:
    path = Path(file_path)
    ext = path.suffix.lower()
    name = path.name

    if ext == ".pdf":
        return _load_pdf(path, name)
    if ext == ".txt":
        return _load_txt(path, name)
    if ext == ".docx":
        return _load_docx(path, name)
    if ext == ".pptx":
        return _load_pptx(path, name)
    raise ValueError(f"Unsupported file type: {ext}")


def _load_pdf(path: Path, name: str) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append(DocumentPage(text=text, metadata={"source": name, "page": i + 1}))
    logger.info("Loaded PDF %s: %d pages", name, len(pages))
    return pages


def _load_txt(path: Path, name: str) -> list[DocumentPage]:
    text = path.read_text(encoding="utf-8")
    logger.info("Loaded TXT %s: %d chars", name, len(text))
    return [DocumentPage(text=text, metadata={"source": name, "page": 1})]


def _load_docx(path: Path, name: str) -> list[DocumentPage]:
    from docx import Document

    doc = Document(str(path))
    pages: list[DocumentPage] = []
    current_text: list[str] = []
    page_num = 1

    for para in doc.paragraphs:
        # DOCX doesn't have native page breaks in all cases;
        # treat section/page-break runs as page separators
        has_break = any(
            run._element.xml.find("w:br") != -1 and 'w:type="page"' in run._element.xml
            for run in para.runs
        )
        if has_break and current_text:
            pages.append(DocumentPage(
                text="\n".join(current_text),
                metadata={"source": name, "page": page_num},
            ))
            current_text = []
            page_num += 1

        if para.text.strip():
            current_text.append(para.text)

    if current_text:
        pages.append(DocumentPage(
            text="\n".join(current_text),
            metadata={"source": name, "page": page_num},
        ))

    logger.info("Loaded DOCX %s: %d pages", name, len(pages))
    return pages


def _extract_slide_texts(shapes) -> list[str]:
    texts = []
    for shape in shapes:
        if shape.has_text_frame:
            texts.append(shape.text_frame.text)
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    texts.append(cell.text)
        if hasattr(shape, "shapes"):
            texts.extend(_extract_slide_texts(shape.shapes))
    return texts


def _load_pptx(path: Path, name: str) -> list[DocumentPage]:
    from pptx import Presentation

    prs = Presentation(str(path))
    pages: list[DocumentPage] = []
    for i, slide in enumerate(prs.slides):
        texts = _extract_slide_texts(slide.shapes)
        text = "\n".join(t for t in texts if t.strip())
        if text.strip():
            pages.append(DocumentPage(text=text, metadata={"source": name, "page": i + 1}))
    logger.info("Loaded PPTX %s: %d slides", name, len(pages))
    return pages
