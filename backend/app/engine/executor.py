"""Executor — operational manager that runs the three-stage pipeline."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.engine.planner import ExecutionPlan, PlanContext, PlanStep
from app.engine.registry import AgentRegistry
from app.engine.tracer import ExecutionTrace
from app.models.schemas import Source

if TYPE_CHECKING:
    from app.agents.base import StatusCallback

logger = logging.getLogger("context_engine.executor")

NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in your uploaded documents to answer this question. "
    "Try uploading more documents or rephrasing your question."
)

_STEP_OUTPUT_RE = re.compile(r"^STEP_(\d+)_OUTPUT(?:\.(.+))?$")


@dataclass
class ExecutorResult:
    answer: str | None = None
    stream: AsyncGenerator[str, None] | None = None
    sources: list[Source] | None = None
    no_context: bool = False
    blueprint_used: str | None = None


class Executor:
    def __init__(self, registry: AgentRegistry, librarian: Any, writer: Any):
        self._registry = registry
        self._librarian = librarian
        self._writer = writer

    async def execute(
        self,
        plan: ExecutionPlan,
        context: PlanContext,
        on_status: Any,
        tracer: ExecutionTrace,
    ) -> ExecutorResult:
        step_outputs: dict[int, dict] = {}
        request_context = {
            "USER_ID": context.user_id,
            "ORG_ID": context.org_id or "",
            "HISTORY": context.history,
            "DOCUMENT_IDS": context.document_ids,
            "ORIGINAL_GOAL": plan.goal,
        }

        # ── Stage 1 (Fixed): Blueprint retrieval ──
        blueprint = None
        if plan.intent_query and context.has_blueprints:
            tracer.log_step_start(0, "librarian", "librarian.search")
            await on_status("librarian", "working")
            try:
                result = await self._librarian.call_tool("librarian.search", {
                    "query": plan.intent_query,
                    "user_id": context.user_id,
                    "org_id": context.org_id,
                    "namespace": "ContextLibrary",
                    "top_k": 1,
                })
                blueprint = result.get("blueprint")
                tracer.log_step_complete(0, f"blueprint={'found: ' + blueprint['blueprint_id'] if blueprint else 'none'}")
            except Exception as e:
                tracer.log_step_failed(0, str(e))
                logger.warning("Blueprint retrieval failed, continuing without blueprint", exc_info=True)
        elif not plan.intent_query:
            tracer.log_step_skipped(0, "no intent_query in plan")

        # ── Stage 2 (Planned): Specialist agents ──
        for step in plan.steps:
            tracer.log_step_start(step.step_id, step.agent, step.tool)
            await on_status(step.agent, "working")

            resolved_inputs = self._resolve_dependencies(step.inputs, step_outputs, request_context)
            resolved_inputs = self._ensure_required_inputs(step, resolved_inputs, request_context, plan)
            agent = self._registry.get_handler(step.agent)

            try:
                result = await agent.call_tool(step.tool, resolved_inputs)
                step_outputs[step.step_id] = result
                tracer.log_step_complete(step.step_id, _summarize(result))
            except Exception as e:
                tracer.log_step_failed(step.step_id, str(e))
                raise

        # ── Short-circuit: no factual context ──
        researcher_output = self._find_researcher_output(step_outputs, plan)
        chunks = researcher_output.get("chunks", []) if researcher_output else []

        if not chunks:
            tracer.log_step_skipped(-1, "short-circuited: no context")
            return ExecutorResult(answer=NO_CONTEXT_ANSWER, sources=[], no_context=True)

        sources = self._build_sources(chunks)

        # ── Stage 3 (Fixed): Writer generation ──
        tracer.log_step_start(-1, "writer", "writer.generate")
        await on_status("writer", "working")

        writer_inputs: dict = {
            "question": plan.goal,
            "chunks": chunks,
            "history": context.history,
            "stream": context.stream,
        }
        if blueprint:
            writer_inputs["blueprint"] = blueprint

        writer_result = await self._writer.call_tool("writer.generate", writer_inputs)
        tracer.log_step_complete(-1, "generation complete")

        bp_id = blueprint["blueprint_id"] if blueprint else None

        if context.stream:
            return ExecutorResult(stream=writer_result["stream"], sources=sources, blueprint_used=bp_id)

        return ExecutorResult(answer=writer_result["answer"], sources=sources, blueprint_used=bp_id)

    def _resolve_dependencies(self, inputs: dict, step_outputs: dict, request_context: dict) -> dict:
        resolved = {}
        for key, value in inputs.items():
            if isinstance(value, str) and value.startswith("$$") and value.endswith("$$"):
                resolved[key] = self._resolve_placeholder(value, step_outputs, request_context)
            else:
                resolved[key] = value
        return resolved

    def _ensure_required_inputs(self, step: PlanStep, inputs: dict, request_context: dict, plan: ExecutionPlan) -> dict:
        """Guarantee required fields for known tools, regardless of LLM plan quality."""
        if step.tool == "researcher.research":
            inputs.setdefault("question", request_context["ORIGINAL_GOAL"])
            inputs.setdefault("user_id", request_context["USER_ID"])
            inputs.setdefault("history", request_context["HISTORY"])
            inputs.setdefault("document_ids", request_context["DOCUMENT_IDS"])
            inputs.setdefault("org_id", request_context["ORG_ID"] or None)
        elif step.tool == "summarizer.summarize":
            inputs.setdefault("objective", request_context["ORIGINAL_GOAL"])
        return inputs

    def _resolve_placeholder(self, placeholder: str, step_outputs: dict, request_context: dict):
        from app.agents.base import AgentError

        inner = placeholder[2:-2]

        if inner in request_context:
            return request_context[inner]

        match = _STEP_OUTPUT_RE.match(inner)
        if match:
            step_id = int(match.group(1))
            field_name = match.group(2)
            if step_id not in step_outputs:
                raise AgentError("VALIDATION_ERROR", f"Step {step_id} has no output yet", "executor", "resolve")
            output = step_outputs[step_id]
            if field_name:
                if field_name not in output:
                    raise AgentError("VALIDATION_ERROR", f"Step {step_id} output has no field '{field_name}'", "executor", "resolve")
                return output[field_name]
            return output

        raise AgentError("VALIDATION_ERROR", f"Unknown placeholder: {placeholder}", "executor", "resolve")

    def _find_researcher_output(self, step_outputs: dict, plan: ExecutionPlan) -> dict | None:
        for step in plan.steps:
            if step.tool == "researcher.research" and step.step_id in step_outputs:
                return step_outputs[step.step_id]
        return None

    def _build_sources(self, chunks: list[dict]) -> list[Source]:
        from app.rag.sources import deduplicate_sources
        sources = [
            Source(
                document=c["metadata"].get("source", "unknown"),
                doc_id=c["metadata"].get("doc_id", ""),
                chunk_id=c["chunk_id"],
                text=c["text"][:settings.source_text_max_length],
                page=c["metadata"].get("page_start") or c["metadata"].get("page"),
                page_end=c["metadata"].get("page_end"),
                start_char=c["metadata"].get("start_char"),
                end_char=c["metadata"].get("end_char"),
                relevance=c.get("score"),
            )
            for c in chunks
        ]
        return deduplicate_sources(sources)


def _summarize(result: dict) -> str:
    if "answer" in result:
        return f"answer={len(result['answer'])} chars"
    if "chunks" in result:
        return f"chunks={len(result['chunks'])}"
    if "summary" in result:
        return f"summary={len(result['summary'])} chars"
    return str(list(result.keys()))
