import uuid
import logging
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.rag.loader import DocumentPage

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


def chunk_pages(pages: list[DocumentPage], doc_id: str) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks: list[Chunk] = []
    for page in pages:
        splits = splitter.split_text(page.text)
        for text in splits:
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                metadata={**page.metadata, "doc_id": doc_id},
            ))
    logger.info("Chunked doc %s into %d chunks", doc_id, len(chunks))
    return chunks
