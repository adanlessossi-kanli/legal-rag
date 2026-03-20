from app.agents.base import AgentError, BaseAgent
from app.agents.librarian import LibrarianAgent
from app.agents.summarizer import SummarizerAgent
from app.core.config import settings
from app.rag.llm import rewrite_query
from app.models.schemas import ChatMessage


class ResearcherAgent(BaseAgent):
    def __init__(self, librarian: LibrarianAgent, summarizer: SummarizerAgent):
        super().__init__("researcher")
        self._librarian = librarian
        self._summarizer = summarizer
        self.register_tools()

    def register_tools(self) -> None:
        @self.tool("researcher.research")
        async def research(params: dict) -> dict:
            return await self._research(params)

    async def _research(self, params: dict) -> dict:
        tool = "researcher.research"
        self._validate_required(params, ["question", "user_id"], tool)

        question = params["question"]
        user_id = params["user_id"]
        history_raw = params.get("history", [])
        document_ids = params.get("document_ids")
        org_id = params.get("org_id")

        self._validate_string_length(question, "question", 1, 5000, tool)

        # Build ChatMessage history
        history = [ChatMessage(role=h["role"], content=h["content"]) for h in history_raw]

        # Query rewriting
        rewritten_query = None
        search_query = question
        if history and settings.enable_query_rewriting:
            try:
                search_query = await rewrite_query(question, history)
                rewritten_query = search_query
                self.logger.info("Rewrote query: '%s' -> '%s'", question, search_query)
            except Exception:
                self.logger.warning("Query rewriting failed, using original question", exc_info=True)
                search_query = question

        # Retrieve via Librarian
        result = await self._librarian.call_tool("librarian.search", {
            "query": search_query,
            "user_id": user_id,
            "document_ids": document_ids,
            "top_k": settings.retrieval_top_k,
            "org_id": org_id,
        })
        chunks = result["chunks"]

        if not chunks:
            return {"chunks": [], "rewritten_query": rewritten_query}

        # Summarize long context if needed
        total_chars = sum(len(c["text"]) for c in chunks)
        if total_chars > settings.researcher_summarize_threshold:
            chunks = await self._summarize_long_chunks(chunks, question)

        return {"chunks": chunks, "rewritten_query": rewritten_query}

    async def _summarize_long_chunks(self, chunks: list[dict], question: str) -> list[dict]:
        result = []
        for chunk in chunks:
            if len(chunk["text"]) > 2000:
                try:
                    summary_result = await self._summarizer.call_tool("summarizer.summarize", {
                        "text": chunk["text"],
                        "objective": question,
                        "max_length": 500,
                    })
                    result.append({
                        **chunk,
                        "text": summary_result["summary"],
                    })
                    continue
                except Exception:
                    self.logger.warning("Chunk summarization failed, keeping original", exc_info=True)
            result.append(chunk)
        return result
