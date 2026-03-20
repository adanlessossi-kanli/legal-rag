from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.agents.base import AgentError, BaseAgent
from app.core.clients import openai_client
from app.core.config import settings

SUMMARIZE_PROMPT = (
    "Summarize the following text. Focus on: {objective}.\n"
    "Keep the summary under {max_length} characters.\n"
    "Preserve key legal terms, dates, and named entities.\n\n"
    "Text:\n{text}"
)

_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
)


class SummarizerAgent(BaseAgent):
    def __init__(self):
        super().__init__("summarizer")
        self.register_tools()

    def register_tools(self) -> None:
        @self.tool("summarizer.summarize")
        async def summarize(params: dict) -> dict:
            return await self._summarize(params)

    async def _summarize(self, params: dict) -> dict:
        tool = "summarizer.summarize"
        self._validate_required(params, ["text", "objective"], tool)

        text = params["text"]
        objective = params["objective"]
        max_length = params.get("max_length", settings.summarizer_max_length)

        self._validate_string_length(text, "text", 1, 50000, tool)
        self._validate_string_length(objective, "objective", 1, 500, tool)
        self._validate_int_range(max_length, "max_length", 50, 5000, tool)

        prompt = SUMMARIZE_PROMPT.format(text=text, objective=objective, max_length=max_length)

        try:
            resp = await self._call_llm(prompt, max_length)
            summary = resp.choices[0].message.content.strip()
            self.logger.info(
                "Summarized %d chars -> %d chars", len(text), len(summary),
            )
            return {"summary": summary}
        except AgentError:
            raise
        except Exception as e:
            raise AgentError("LLM_ERROR", f"Summarization failed: {e}", self.name, tool, retryable=True) from e

    @_retry
    async def _call_llm(self, prompt: str, max_length: int):
        return await openai_client.chat.completions.create(
            model=settings.summarizer_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max(max_length // 3, 100),
        )
