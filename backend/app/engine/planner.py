"""Planner — strategic core that generates execution plans via LLM."""

import json
import logging
from dataclasses import dataclass, field

from app.core.config import settings
from app.engine.registry import AgentRegistry

logger = logging.getLogger("context_engine.planner")


@dataclass
class PlanStep:
    step_id: int
    agent: str
    tool: str
    inputs: dict
    description: str
    depends_on: list[int] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    goal: str
    intent_query: str | None = None
    topic_query: str | None = None
    steps: list[PlanStep] = field(default_factory=list)


@dataclass
class PlanContext:
    user_id: str
    org_id: str | None
    history: list[dict]
    document_ids: list[str] | None
    stream: bool
    has_blueprints: bool


PLANNING_PROMPT = """\
You are a task planner for a legal document analysis system. Given a user's goal and a list of available specialist agents, produce a JSON execution plan.

YOUR JOB:
- Analyze the user's goal and decompose it into:
  - intent_query: The desired output style or structure (e.g., "executive summary", "bullet-point comparison", "formal legal memo"). Set to null if the goal implies no specific style.
  - topic_query: The factual subject matter to research (e.g., "liability clauses", "termination provisions").
- Select which specialist agents to invoke and in what order.
- Define the inputs for each step, using $$PLACEHOLDER$$ syntax for dynamic values.

AVAILABLE PLACEHOLDERS:
- $$USER_ID$$, $$ORG_ID$$: User and organization identifiers.
- $$HISTORY$$: Conversation history.
- $$DOCUMENT_IDS$$: Document scope filter (may be null).
- $$ORIGINAL_GOAL$$: The user's original question.
- $$STEP_N_OUTPUT$$: Full output of step N.
- $$STEP_N_OUTPUT.field$$: A specific field from step N's output.

CONSTRAINTS:
- You may ONLY use the specialist agents listed below. Do not reference any other agents.
- Each step must have: step_id (int, starting at 1), agent (str), tool (str), inputs (dict), description (str), depends_on (list[int]).
- The researcher agent should almost always be included to retrieve factual context.
- The summarizer agent should only be included when the goal explicitly or implicitly requires condensing large amounts of information.

AVAILABLE SPECIALIST AGENTS:
{capabilities}

USER CONTEXT:
- Goal: {goal}
- Has blueprints: {has_blueprints}
- Has conversation history: {has_history}
- Has document scope: {has_document_ids}

Respond with ONLY a JSON object:
{{"intent_query": "string or null", "topic_query": "string", "steps": [...]}}"""


class Planner:
    def __init__(self, registry: AgentRegistry):
        self._registry = registry

    async def plan(self, goal: str, context: PlanContext) -> ExecutionPlan:
        if not settings.enable_context_engine:
            return self._fallback_plan(goal)

        try:
            return await self._llm_plan(goal, context)
        except Exception:
            logger.warning("Planner LLM failed, using fallback plan", exc_info=True)
            return self._fallback_plan(goal)

    async def _llm_plan(self, goal: str, context: PlanContext) -> ExecutionPlan:
        import asyncio
        from app.core.clients import openai_client

        capabilities = self._registry.get_capabilities_description()
        prompt = PLANNING_PROMPT.format(
            capabilities=capabilities,
            goal=goal,
            has_blueprints=context.has_blueprints,
            has_history=bool(context.history),
            has_document_ids=bool(context.document_ids),
        )

        resp = await asyncio.wait_for(
            openai_client.chat.completions.create(
                model=settings.planner_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            ),
            timeout=settings.planner_timeout,
        )

        raw = json.loads(resp.choices[0].message.content)
        plan = self._parse_plan(goal, raw)
        self._validate_plan(plan)
        logger.info(
            "Planner generated %d-step plan: intent=%s topic=%s",
            len(plan.steps), plan.intent_query, plan.topic_query,
        )
        return plan

    def _parse_plan(self, goal: str, raw: dict) -> ExecutionPlan:
        steps = []
        for s in raw.get("steps", []):
            steps.append(PlanStep(
                step_id=int(s["step_id"]),
                agent=s["agent"],
                tool=s["tool"],
                inputs=s.get("inputs", {}),
                description=s.get("description", ""),
                depends_on=s.get("depends_on", []),
            ))
        return ExecutionPlan(
            goal=goal,
            intent_query=raw.get("intent_query"),
            topic_query=raw.get("topic_query", goal),
            steps=steps,
        )

    def _validate_plan(self, plan: ExecutionPlan) -> None:
        if not plan.steps:
            raise ValueError("Plan has no steps")

        step_ids = {s.step_id for s in plan.steps}
        for step in plan.steps:
            if not self._registry.has_agent(step.agent):
                raise ValueError(f"Unknown agent in plan: {step.agent}")
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(f"Step {step.step_id} depends on non-existent step {dep}")
                if dep >= step.step_id:
                    raise ValueError(f"Step {step.step_id} has forward/circular dependency on step {dep}")

    def _fallback_plan(self, goal: str) -> ExecutionPlan:
        return ExecutionPlan(
            goal=goal,
            intent_query=None,
            topic_query=goal,
            steps=[
                PlanStep(
                    step_id=1,
                    agent="researcher",
                    tool="researcher.research",
                    inputs={
                        "question": "$$ORIGINAL_GOAL$$",
                        "user_id": "$$USER_ID$$",
                        "history": "$$HISTORY$$",
                        "document_ids": "$$DOCUMENT_IDS$$",
                    },
                    description="Retrieve factual context",
                ),
            ],
        )
