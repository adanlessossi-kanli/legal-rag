"""Agent Registry — runtime catalog of plannable specialist agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.base import BaseAgent


@dataclass
class AgentCapability:
    name: str
    description: str
    tools: list[str] = field(default_factory=list)


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._capabilities: dict[str, AgentCapability] = {}

    def register(self, name: str, agent: Any, capability: AgentCapability) -> None:
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")
        self._agents[name] = agent
        self._capabilities[name] = capability

    def get_handler(self, agent_name: str) -> Any:
        if agent_name not in self._agents:
            from app.agents.base import AgentError
            raise AgentError("VALIDATION_ERROR", f"Unknown agent: {agent_name}", "registry", "get_handler")
        return self._agents[agent_name]

    def has_agent(self, name: str) -> bool:
        return name in self._agents

    def list_agents(self) -> list[AgentCapability]:
        return list(self._capabilities.values())

    def get_capabilities_description(self) -> str:
        lines = ["Available specialist agents:", ""]
        for i, cap in enumerate(self._capabilities.values(), 1):
            lines.append(f"{i}. {cap.name}")
            lines.append(f"   Description: {cap.description}")
            lines.append(f"   Tools: {', '.join(cap.tools)}")
            lines.append("")
        return "\n".join(lines)
