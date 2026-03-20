import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine


@dataclass
class AgentError(Exception):
    error_type: str
    message: str
    agent: str
    tool: str
    retryable: bool = False

    def to_dict(self) -> dict:
        return {
            "error": {
                "type": self.error_type,
                "message": self.message,
                "agent": self.agent,
                "tool": self.tool,
                "retryable": self.retryable,
            }
        }


@dataclass
class AgentStatus:
    agent: str
    status: str


StatusCallback = Callable[[str, str], Coroutine[Any, Any, None]]


class BaseAgent:
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"agent.{name}")
        self._tools: dict[str, Callable] = {}

    def register_tools(self) -> None:
        raise NotImplementedError

    def tool(self, name: str):
        """Decorator to register a tool handler."""
        def decorator(fn: Callable) -> Callable:
            self._tools[name] = fn
            return fn
        return decorator

    async def call_tool(self, name: str, params: dict) -> Any:
        if name not in self._tools:
            raise AgentError("VALIDATION_ERROR", f"Unknown tool: {name}", self.name, name)
        start = time.time()
        try:
            result = await self._tools[name](params)
            self._log_call(name, (time.time() - start) * 1000, "ok")
            return result
        except AgentError:
            self._log_call(name, (time.time() - start) * 1000, "error")
            raise
        except Exception as e:
            self._log_call(name, (time.time() - start) * 1000, "error")
            raise AgentError("INTERNAL_ERROR", str(e), self.name, name) from e

    async def health(self) -> str:
        return "ok"

    def _validate_required(self, params: dict, fields: list[str], tool: str) -> None:
        for f in fields:
            val = params.get(f)
            if val is None or (isinstance(val, str) and not val.strip()):
                raise AgentError("VALIDATION_ERROR", f"Missing required field: {f}", self.name, tool)

    def _validate_string_length(self, value: str, name: str, min_len: int, max_len: int, tool: str) -> None:
        if len(value) < min_len or len(value) > max_len:
            raise AgentError(
                "VALIDATION_ERROR",
                f"{name} length must be between {min_len} and {max_len}, got {len(value)}",
                self.name, tool,
            )

    def _validate_int_range(self, value: int, name: str, min_val: int, max_val: int, tool: str) -> None:
        if value < min_val or value > max_val:
            raise AgentError(
                "VALIDATION_ERROR",
                f"{name} must be between {min_val} and {max_val}, got {value}",
                self.name, tool,
            )

    def _log_call(self, tool: str, duration_ms: float, status: str, **extra) -> None:
        self.logger.info(
            "tool_call agent=%s tool=%s duration_ms=%.1f status=%s",
            self.name, tool, duration_ms, status,
            extra={"agent": self.name, "tool": tool, "duration_ms": round(duration_ms, 1), "status": status, **extra},
        )
