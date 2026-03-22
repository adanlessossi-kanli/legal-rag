import logging
import time
from collections.abc import AsyncGenerator
from contextvars import ContextVar

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.circuit_breaker import CircuitOpenError, openai_circuit
from app.core.clients import openai_client
from app.core.config import settings
from app.core.metrics import LLM_ERRORS, LLM_LATENCY, LLM_TOKENS
from app.models.schemas import ChatMessage

logger = logging.getLogger(__name__)

# Context var set by chat endpoint so LLM calls can record per-user usage
current_user_id: ContextVar[str] = ContextVar("current_user_id", default="")

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


def _build_messages(question: str, context_chunks: list[dict], history: list[ChatMessage], system_prompt: str | None = None) -> list[dict]:
    context = "\n\n".join(
        f"[Source: {c['metadata'].get('source', 'unknown')}, Page {c['metadata'].get('page', '?')}]\n{c['text']}"
        for c in context_chunks
    )
    messages = [{"role": "system", "content": system_prompt or SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})
    return messages


async def _track_usage(model: str, operation: str, usage) -> None:
    LLM_TOKENS.labels("prompt").inc(usage.prompt_tokens)
    LLM_TOKENS.labels("completion").inc(usage.completion_tokens)
    uid = current_user_id.get()
    if uid:
        from app.core.usage import record_usage
        try:
            await record_usage(uid, model, operation, usage.prompt_tokens, usage.completion_tokens)
        except Exception:
            logger.warning("Failed to record usage", exc_info=True)


@_retry
async def generate(question: str, context_chunks: list[dict], history: list[ChatMessage], system_prompt: str | None = None) -> str:
    messages = _build_messages(question, context_chunks, history, system_prompt=system_prompt)

    start = time.time()
    try:
        async with openai_circuit:
            resp = await openai_client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=0.1,
            )
    except CircuitOpenError:
        LLM_ERRORS.labels("generate").inc()
        raise
    except Exception:
        LLM_ERRORS.labels("generate").inc()
        raise
    elapsed = time.time() - start
    LLM_LATENCY.labels("generate").observe(elapsed)
    usage = resp.usage
    logger.info("LLM took %.2fs, tokens: prompt=%d completion=%d", elapsed, usage.prompt_tokens, usage.completion_tokens)
    await _track_usage(settings.llm_model, "generate", usage)

    return resp.choices[0].message.content


@_retry
async def generate_stream(question: str, context_chunks: list[dict], history: list[ChatMessage], system_prompt: str | None = None) -> AsyncGenerator[str, None]:
    messages = _build_messages(question, context_chunks, history, system_prompt=system_prompt)

    stream = await openai_client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.1,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
        if hasattr(chunk, "usage") and chunk.usage and hasattr(chunk.usage, "prompt_tokens") and isinstance(chunk.usage.prompt_tokens, int):
            await _track_usage(settings.llm_model, "generate_stream", chunk.usage)


@_retry
async def rewrite_query(question: str, history: list[ChatMessage]) -> str:
    history_text = "\n".join(f"{m.role}: {m.content}" for m in history)
    start = time.time()
    try:
        async with openai_circuit:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": REWRITE_PROMPT},
                    {"role": "user", "content": f"History:\n{history_text}\n\nFollow-up question: {question}\n\nStandalone question:"},
                ],
                temperature=0,
                max_tokens=256,
            )
    except CircuitOpenError:
        LLM_ERRORS.labels("rewrite").inc()
        raise
    except Exception:
        LLM_ERRORS.labels("rewrite").inc()
        raise
    LLM_LATENCY.labels("rewrite").observe(time.time() - start)
    if resp.usage:
        LLM_TOKENS.labels("prompt").inc(resp.usage.prompt_tokens)
        LLM_TOKENS.labels("completion").inc(resp.usage.completion_tokens)
        await _track_usage("gpt-4o-mini", "rewrite", resp.usage)
    rewritten = resp.choices[0].message.content.strip()
    logger.info("Rewrote query: '%s' -> '%s'", question, rewritten)
    return rewritten
