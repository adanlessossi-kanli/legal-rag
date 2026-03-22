import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

from app.agents.base import AgentError, StatusCallback
from app.agents.librarian import LibrarianAgent
from app.agents.researcher import ResearcherAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.writer import WriterAgent
from app.core.database import get_db
from app.models.schemas import ChatMessage, Source

logger = logging.getLogger("agent.orchestrator")

# Re-exported for backward compatibility (tests import from here)
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

        # Deferred init — built on first use to avoid circular imports
        self._planner = None
        self._executor = None
        self._registry = None

    def _ensure_engine(self):
        if self._registry is not None:
            return
        from app.engine.registry import AgentRegistry, AgentCapability
        from app.engine.planner import Planner
        from app.engine.executor import Executor

        self._registry = AgentRegistry()
        self._registry.register("researcher", self._researcher, AgentCapability(
            name="researcher",
            description="Retrieves and synthesizes factual information, providing source citations.",
            tools=["researcher.research"],
        ))
        self._registry.register("summarizer", self._summarizer, AgentCapability(
            name="summarizer",
            description="Reduces a large text to a concise summary based on an objective.",
            tools=["summarizer.summarize"],
        ))
        self._planner = Planner(self._registry)
        self._executor = Executor(self._registry, self._librarian, self._writer)

    async def query(
        self,
        question: str,
        history: list[ChatMessage],
        user_id: str,
        document_ids: list[str] | None = None,
        on_status: StatusCallback | None = None,
        org_id: str | None = None,
    ) -> tuple[str, list[Source], bool]:
        async def _noop(a: str, s: str) -> None:
            pass
        status = on_status or _noop

        try:
            return await asyncio.wait_for(
                self._do_query(question, history, user_id, document_ids, status, org_id, stream=False),
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
        org_id: str | None,
        stream: bool,
    ) -> tuple[str, list[Source], bool]:
        self._ensure_engine()
        from app.engine.planner import PlanContext
        from app.engine.tracer import ExecutionTrace
        from app.engine.executor import NO_CONTEXT_ANSWER

        trace = ExecutionTrace(trace_id=uuid.uuid4().hex[:12], goal=question)

        # Phase 1: Plan
        await status("planner", "working")
        context = PlanContext(
            user_id=user_id,
            org_id=org_id,
            history=[{"role": m.role, "content": m.content} for m in history],
            document_ids=document_ids,
            stream=stream,
            has_blueprints=await self._has_blueprints(user_id, org_id),
        )
        plan = await self._planner.plan(question, context)

        # Phase 2: Execute
        result = await self._executor.execute(plan, context, status, trace)

        # Phase 3: Finalize
        trace.finalize("completed")
        await status("done", "done")

        return result.answer or NO_CONTEXT_ANSWER, result.sources or [], result.no_context

    async def query_stream(
        self,
        question: str,
        history: list[ChatMessage],
        user_id: str,
        document_ids: list[str] | None = None,
        on_status: StatusCallback | None = None,
        org_id: str | None = None,
    ) -> tuple[AsyncGenerator[str, None] | None, list[Source], bool]:
        async def _noop(a: str, s: str) -> None:
            pass
        status = on_status or _noop

        self._ensure_engine()
        from app.engine.planner import PlanContext
        from app.engine.tracer import ExecutionTrace

        trace = ExecutionTrace(trace_id=uuid.uuid4().hex[:12], goal=question)

        # Phase 1: Plan
        await status("planner", "working")
        context = PlanContext(
            user_id=user_id,
            org_id=org_id,
            history=[{"role": m.role, "content": m.content} for m in history],
            document_ids=document_ids,
            stream=True,
            has_blueprints=await self._has_blueprints(user_id, org_id),
        )
        plan = await self._planner.plan(question, context)

        # Phase 2: Execute
        result = await self._executor.execute(plan, context, status, trace)

        if result.no_context:
            trace.finalize("completed")
            await status("done", "done")
            return None, [], True

        async def _wrapped_stream() -> AsyncGenerator[str, None]:
            async for token in result.stream:
                yield token
            trace.finalize("completed")
            await status("done", "done")

        return _wrapped_stream(), result.sources or [], False

    async def ingest(
        self, file_path: str, original_name: str, doc_id: str, content_hash: str, user_id: str, org_id: str = "",
    ) -> int:
        result = await self._librarian.call_tool("librarian.ingest", {
            "file_path": file_path,
            "original_name": original_name,
            "doc_id": doc_id,
            "content_hash": content_hash,
            "user_id": user_id,
            "org_id": org_id,
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

    async def _has_blueprints(self, user_id: str, org_id: str | None) -> bool:
        db = get_db()
        query: dict = {"$or": [
            {"user_id": "system", "is_default": True},
            {"user_id": user_id},
        ]}
        if org_id:
            query["$or"].append({"org_id": org_id})
        return await db.blueprints.count_documents(query, limit=1) > 0
