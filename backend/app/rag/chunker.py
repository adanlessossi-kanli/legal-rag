import re
import uuid
import logging
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.rag.loader import DocumentPage

logger = logging.getLogger(__name__)

# Legal section patterns: "Article 1", "Section 2.3", "CLAUSE IV", "1.", "1.1", etc.
_LEGAL_SECTION_RE = re.compile(
    r"^\s*(?:"
    r"(?:article|section|clause|part|chapter|schedule|annex|exhibit|appendix)\s+[\dIVXivx]+"
    r"|\d+\.\d*\s"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


def _detect_legal_separators(text: str) -> list[str]:
    """Return separators tuned for legal documents if section headers are detected."""
    if _LEGAL_SECTION_RE.search(text):
        return [
            # Double newlines (paragraph breaks)
            "\n\n",
            # Legal section headers as split points
            "\nArticle ", "\nARTICLE ",
            "\nSection ", "\nSECTION ",
            "\nClause ", "\nCLAUSE ",
            "\nSchedule ", "\nSCHEDULE ",
            # Numbered clauses
            "\n",
            ". ",
            " ",
        ]
    return None  # Use default RecursiveCharacterTextSplitter separators


def chunk_pages(pages: list[DocumentPage], doc_id: str) -> list[Chunk]:
    all_text = "\n\n".join(p.text for p in pages)
    separators = _detect_legal_separators(all_text)

    splitter_kwargs = dict(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    if separators:
        splitter_kwargs["separators"] = separators
        logger.info("Using legal-aware separators for doc %s", doc_id)

    splitter = RecursiveCharacterTextSplitter(**splitter_kwargs)
    chunks: list[Chunk] = []
    for page in pages:
        page_num = page.metadata.get("page", 1)
        docs = splitter.create_documents([page.text], metadatas=[page.metadata])
        search_start = 0
        for doc in docs:
            text = doc.page_content
            start_char = page.text.find(text, search_start)
            if start_char == -1:
                start_char = page.text.find(text)
            end_char = start_char + len(text) if start_char >= 0 else -1
            if start_char >= 0:
                search_start = start_char + 1
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                metadata={
                    **page.metadata,
                    "doc_id": doc_id,
                    "page_start": page_num,
                    "page_end": page_num,
                    "start_char": max(start_char, 0),
                    "end_char": max(end_char, 0),
                },
            ))
    logger.info("Chunked doc %s into %d chunks", doc_id, len(chunks))
    return chunks
