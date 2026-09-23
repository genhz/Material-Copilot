"""Plan-first material agent workflow."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AgentWorkflowService",
    "get_agent_workflow_service",
]


def __getattr__(name: str) -> Any:
    """Load service exports lazily to avoid runtime import cycles."""

    if name in __all__:
        from agent_workflow import service

        return getattr(service, name)
    raise AttributeError(name)
