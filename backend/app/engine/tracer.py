"""Execution Tracer — flight recorder for Context Engine pipeline."""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("context_engine.tracer")


@dataclass
class TraceEntry:
    step_id: int
    agent: str
    tool: str
    status: str = "started"
    started_at: float = 0.0
    completed_at: float | None = None
    duration_ms: float | None = None
    output_summary: str | None = None
    error: str | None = None


@dataclass
class ExecutionTrace:
    trace_id: str
    goal: str
    entries: list[TraceEntry] = field(default_factory=list)
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    total_duration_ms: float | None = None

    def log_step_start(self, step_id: int, agent: str, tool: str) -> None:
        entry = TraceEntry(step_id=step_id, agent=agent, tool=tool, started_at=time.time())
        self.entries.append(entry)
        logger.info(
            "context_engine trace_id=%s step=%s agent=%s tool=%s status=started",
            self.trace_id, step_id, agent, tool,
        )

    def log_step_complete(self, step_id: int, output_summary: str = "") -> None:
        entry = self._find_entry(step_id)
        if not entry:
            return
        now = time.time()
        entry.status = "completed"
        entry.completed_at = now
        entry.duration_ms = (now - entry.started_at) * 1000
        entry.output_summary = output_summary[:200] if output_summary else ""
        logger.info(
            "context_engine trace_id=%s step=%s agent=%s tool=%s status=completed duration_ms=%.1f",
            self.trace_id, step_id, entry.agent, entry.tool, entry.duration_ms,
        )

    def log_step_failed(self, step_id: int, error: str) -> None:
        entry = self._find_entry(step_id)
        if not entry:
            return
        now = time.time()
        entry.status = "failed"
        entry.completed_at = now
        entry.duration_ms = (now - entry.started_at) * 1000
        entry.error = error
        logger.error(
            "context_engine trace_id=%s step=%s agent=%s tool=%s status=failed error=%s",
            self.trace_id, step_id, entry.agent, entry.tool, error,
        )

    def log_step_skipped(self, step_id: int, reason: str) -> None:
        entry = TraceEntry(step_id=step_id, agent="", tool="", status="skipped", started_at=time.time())
        entry.output_summary = reason
        self.entries.append(entry)
        logger.info("context_engine trace_id=%s step=%s status=skipped reason=%s", self.trace_id, step_id, reason)

    def finalize(self, status: str = "completed") -> None:
        self.status = status
        self.completed_at = time.time()
        self.total_duration_ms = (self.completed_at - self.started_at) * 1000
        logger.info(
            "context_engine trace_id=%s status=%s total_duration_ms=%.1f steps=%d",
            self.trace_id, status, self.total_duration_ms, len(self.entries),
        )

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "goal": self.goal[:200],
            "status": self.status,
            "total_duration_ms": self.total_duration_ms,
            "entries": [
                {
                    "step_id": e.step_id,
                    "agent": e.agent,
                    "tool": e.tool,
                    "status": e.status,
                    "duration_ms": e.duration_ms,
                    "output_summary": e.output_summary,
                    "error": e.error,
                }
                for e in self.entries
            ],
        }

    def _find_entry(self, step_id: int) -> TraceEntry | None:
        for e in reversed(self.entries):
            if e.step_id == step_id:
                return e
        return None
