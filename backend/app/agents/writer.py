from collections.abc import AsyncGenerator

from app.agents.base import AgentError, BaseAgent
from app.models.schemas import ChatMessage
from app.rag.llm import generate, generate_stream, _build_messages


class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__("writer")
        self.register_tools()

    def register_tools(self) -> None:
        @self.tool("writer.generate")
        async def gen(params: dict) -> dict:
            return await self._generate(params)

    async def _generate(self, params: dict) -> dict | AsyncGenerator[str, None]:
        tool = "writer.generate"
        self._validate_required(params, ["question", "chunks"], tool)

        question = params["question"]
        chunks = params["chunks"]
        history_raw = params.get("history", [])
        stream = params.get("stream", False)

        self._validate_string_length(question, "question", 1, 5000, tool)
        if not chunks:
            raise AgentError("VALIDATION_ERROR", "chunks must not be empty", self.name, tool)

        history = [ChatMessage(role=h["role"], content=h["content"]) for h in history_raw]

        try:
            if stream:
                return {"stream": generate_stream(question, chunks, history)}
            answer = await generate(question, chunks, history)
            return {"answer": answer}
        except AgentError:
            raise
        except Exception as e:
            raise AgentError("LLM_ERROR", f"Generation failed: {e}", self.name, tool, retryable=not stream) from e
