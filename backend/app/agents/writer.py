from collections.abc import AsyncGenerator

from app.agents.base import AgentError, BaseAgent
from app.models.schemas import ChatMessage
from app.rag.llm import SYSTEM_PROMPT, generate, generate_stream


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
        blueprint = params.get("blueprint")

        self._validate_string_length(question, "question", 1, 5000, tool)
        if not chunks:
            raise AgentError("VALIDATION_ERROR", "chunks must not be empty", self.name, tool)

        history = [ChatMessage(role=h["role"], content=h["content"]) for h in history_raw]
        system_prompt = self._build_system_prompt(blueprint)

        try:
            if stream:
                return {"stream": generate_stream(question, chunks, history, system_prompt=system_prompt)}
            answer = await generate(question, chunks, history, system_prompt=system_prompt)
            return {"answer": answer}
        except AgentError:
            raise
        except Exception as e:
            raise AgentError("LLM_ERROR", f"Generation failed: {e}", self.name, tool, retryable=not stream) from e

    def _build_system_prompt(self, blueprint: dict | None) -> str:
        if not blueprint or not blueprint.get("content"):
            return SYSTEM_PROMPT

        content = blueprint["content"]
        parts = [SYSTEM_PROMPT]

        if content.get("scene_goal"):
            parts.append(f"\nGoal: {content['scene_goal']}")
        if content.get("style_guide"):
            parts.append(f"\nStyle guide: {content['style_guide']}")
        if content.get("structure"):
            sections = ", ".join(content["structure"])
            parts.append(f"\nStructure your response with these sections: {sections}")
        if content.get("participants"):
            roles = "; ".join(f"{p['role']}: {p['description']}" for p in content["participants"])
            parts.append(f"\nParticipants: {roles}")
        if content.get("instruction"):
            parts.append(f"\nInstruction: {content['instruction']}")

        return "\n".join(parts)
