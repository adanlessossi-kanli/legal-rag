import logging
import time
from collections.abc import AsyncGenerator

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.clients import openai_client
from app.core.config import settings
from app.models.schemas import ChatMessage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a legal assistant. Answer the user's question based ONLY on the "
    "provided context. If the context does not contain enough information, "
    "say so. Always cite which document and section your answer comes from."
)

REWRITE_PROMPT = (
    "Given the conversation history and a follow-up question, rewrite the "
    "follow-up question to be a standalone question that captures the full "
    "context. Return ONLY the rewritten question, nothing else."
)

_retry = retry(
    stop=stop_after_attempt(settings.openai_max_retries),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
)


def _build_messages(question: str, context_chunks: list[dict], history: list[ChatMessage]) -> list[dict]:
    context = "\n\n".join(
        f"[Source: {c['metadata'].get('source', 'unknown')}, Page {c['metadata'].get('page', '?')}]\n{c['text']}"
        for c in context_chunks
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})
    return messages


@_retry
async def generate(question: str, context_chunks: list[dict], history: list[ChatMessage]) -> str:
    messages = _build_messages(question, context_chunks, history)

    start = time.time()
    resp = await openai_client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.1,
    )
    elapsed = time.time() - start
    usage = resp.usage
    logger.info("LLM took %.2fs, tokens: prompt=%d completion=%d", elapsed, usage.prompt_tokens, usage.completion_tokens)

    return resp.choices[0].message.content


@_retry
async def generate_stream(question: str, context_chunks: list[dict], history: list[ChatMessage]) -> AsyncGenerator[str, None]:
    messages = _build_messages(question, context_chunks, history)

    stream = await openai_client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.1,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


@_retry
async def rewrite_query(question: str, history: list[ChatMessage]) -> str:
    history_text = "\n".join(f"{m.role}: {m.content}" for m in history)
    resp = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": REWRITE_PROMPT},
            {"role": "user", "content": f"History:\n{history_text}\n\nFollow-up question: {question}\n\nStandalone question:"},
        ],
        temperature=0,
        max_tokens=256,
    )
    rewritten = resp.choices[0].message.content.strip()
    logger.info("Rewrote query: '%s' -> '%s'", question, rewritten)
    return rewritten
