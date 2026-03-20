import asyncio
import logging
from collections.abc import AsyncGenerator

from app.agents.base import AgentError, StatusCallback
from app.agents.librarian import LibrarianAgent
from app.agents.researcher import ResearcherAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.writer import WriterAgent
from app.core.config import settings
from app.models.schemas import ChatMessage, Source

logger = logging.getLogger("agent.orchestrator")

NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in your uploaded documents to answer this question. "
    "Try uploading more documents or rephrasing your question."
)

OVERALL_TIMEOUT = 90


class Orchestrator:
    def __init__(
        self,
        librarian: LibrarianAgent,
        researcher: ResearcherAgent,
        writer: WriterAgent,
        summarizer: SummarizerAgent,
    ):
        self._librarian = librarian
        self._researcher = researcher
        self._writer = writer
        self._summarizer = summarizer

    async def query(
        self,
        question: str,
        history: list[ChatMessage],
        user_id: str,
        document_ids: list[str] | None = None,
        on_status: StatusCallback | None = None,
    ) -> tuple[str, list[Source], bool]:
        async def _noop(a: str, s: str) -> None:
            pass
        status = on_status or _noop

        try:
            return await asyncio.wait_for(
                self._do_query(question, history, user_id, document_ids, status),
                timeout=OVERALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("Query timed out after %ds", OVERALL_TIMEOUT)
            raise AgentError("INTERNAL_ERROR", "Query timed out", "orchestrator", "query")

    async def _do_query(
        self,
        question: str,
        history: list[ChatMessage],
        user_id: str,
        document_ids: list[str] | None,
        status: StatusCallback,
    ) -> tuple[str, list[Source], bool]:
        # Research phase
        await status("researcher", "working")
        history_dicts = [{"role": m.role, "content": m.content} for m in history]
        research_result = await self._researcher.call_tool("researcher.research", {
            "question": question,
            "history": history_dicts,
            "user_id": user_id,
            "document_ids": document_ids,
        })

        chunks = research_result["chunks"]
        if not chunks:
            await status("done", "done")
            return NO_CONTEXT_ANSWER, [], True

        sources = self._build_sources(chunks)

        # Generation phase
        await status("writer", "working")
        writer_result = await self._writer.call_tool("writer.generate", {
            "question": question,
            "chunks": chunks,
            "history": history_dicts,
            "stream": False,
        })

        await status("done", "done")
        return writer_result["answer"], sources, False

    async def query_stream(
        self,
        question: str,
        history: list[ChatMessage],
        user_id: str,
        document_ids: list[str] | None = None,
        on_status: StatusCallback | None = None,
    ) -> tuple[AsyncGenerator[str, None] | None, list[Source], bool]:
        async def _noop(a: str, s: str) -> None:
            pass
        status = on_status or _noop

        # Research phase
        await status("researcher", "working")
        history_dicts = [{"role": m.role, "content": m.content} for m in history]
        research_result = await self._researcher.call_tool("researcher.research", {
            "question": question,
            "history": history_dicts,
            "user_id": user_id,
            "document_ids": document_ids,
        })

        chunks = research_result["chunks"]
        if not chunks:
            await status("done", "done")
            return None, [], True

        sources = self._build_sources(chunks)

        # Generation phase (streaming)
        await status("writer", "working")
        writer_result = await self._writer.call_tool("writer.generate", {
            "question": question,
            "chunks": chunks,
            "history": history_dicts,
            "stream": True,
        })

        token_gen = writer_result["stream"]

        async def _wrapped_stream() -> AsyncGenerator[str, None]:
            async for token in token_gen:
                yield token
            await status("done", "done")

        return _wrapped_stream(), sources, False

    async def ingest(
        self, file_path: str, original_name: str, doc_id: str, content_hash: str, user_id: str,
    ) -> int:
        result = await self._librarian.call_tool("librarian.ingest", {
            "file_path": file_path,
            "original_name": original_name,
            "doc_id": doc_id,
            "content_hash": content_hash,
            "user_id": user_id,
        })
        return result["chunk_count"]

    async def remove_document(self, doc_id: str) -> None:
        await self._librarian.call_tool("librarian.remove", {"doc_id": doc_id})

    async def summarize(self, text: str, objective: str, max_length: int = 500) -> str:
        result = await self._summarizer.call_tool("summarizer.summarize", {
            "text": text,
            "objective": objective,
            "max_length": max_length,
        })
        return result["summary"]

    async def health_check(self) -> dict[str, str]:
        agents = {
            "librarian": self._librarian,
            "researcher": self._researcher,
            "writer": self._writer,
            "summarizer": self._summarizer,
        }
        result = {}
        for name, agent in agents.items():
            try:
                result[name] = await agent.health()
            except Exception:
                result[name] = "error"
        return result

    async def shutdown(self) -> None:
        logger.info("Orchestrator shutting down")

    def _build_sources(self, chunks: list[dict]) -> list[Source]:
        return [
            Source(
                document=c["metadata"].get("source", "unknown"),
                chunk_id=c["chunk_id"],
                text=c["text"][: settings.source_text_max_length],
            )
            for c in chunks
        ]
