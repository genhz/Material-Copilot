"""Execute planning-time tool calls and return observations."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from agent_runtime.planner import AgentPlanner
from agent_runtime.tool_registry import ToolDefinition, ToolRegistry
from agent_workflow.schemas import ExecutionPlan


class ToolObservation(BaseModel):
    """Normalized result from one ReAct tool call."""

    tool: str
    status: str = "ok"
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    @property
    def plan(self) -> Optional[ExecutionPlan]:
        raw = self.output.get("plan")
        if isinstance(raw, ExecutionPlan):
            return raw
        if isinstance(raw, dict):
            return ExecutionPlan.model_validate(raw)
        return None


class AgentToolExecutor:
    """Dispatch LLM-selected tools without bypassing plan confirmation."""

    def __init__(
        self,
        planner: AgentPlanner,
        tool_registry: ToolRegistry,
    ):
        self.planner = planner
        self.tool_registry = tool_registry

    async def execute(
        self,
        *,
        action: str,
        arguments: dict[str, Any],
        session_id: str,
        message: str,
        previous_plan: Optional[ExecutionPlan] = None,
        reasoning_trace: Optional[list[dict[str, Any]]] = None,
    ) -> ToolObservation:
        try:
            if action == "choose_tool":
                tool = self.tool_registry.choose_tool(
                    requested_name=arguments.get("tool_name"),
                    capability=arguments.get("capability"),
                    properties=list(arguments.get("properties") or []),
                )
                return ToolObservation(
                    tool="choose_tool",
                    status="selected",
                    output={"tool": tool.model_dump(mode="json")},
                )

            if action in {"plan_generation", "revise_plan"}:
                plan_arguments = dict(arguments)
                if action == "plan_generation":
                    plan_arguments["task_type"] = "material_generation"
                elif previous_plan is not None:
                    plan_arguments = {
                        **self.planner.arguments_from_plan(previous_plan),
                        **{
                            key: value
                            for key, value in arguments.items()
                            if value is not None
                        },
                    }
                plan = self.planner.build_plan(
                    session_id=session_id,
                    message=message,
                    arguments=plan_arguments,
                    previous_plan=previous_plan,
                    reasoning_trace=reasoning_trace or [],
                )
                return ToolObservation(
                    tool=action,
                    status="planned",
                    output={"plan": plan},
                )

            tool = self.tool_registry.get(action)
            if tool and tool.kind == "generation":
                plan_arguments = dict(arguments)
                plan_arguments.setdefault("task_type", "material_generation")
                preferences = list(
                    plan_arguments.get("model_preferences") or []
                )
                if action not in preferences:
                    preferences.append(action)
                plan_arguments["model_preferences"] = preferences
                plan = self.planner.build_plan(
                    session_id=session_id,
                    message=message,
                    arguments=plan_arguments,
                    previous_plan=previous_plan,
                    reasoning_trace=reasoning_trace or [],
                )
                return ToolObservation(
                    tool=action,
                    status="planned",
                    output={"plan": plan},
                )

            if tool and tool.capability in {
                "material_lookup",
                "element_substitution",
                "science_chat",
            }:
                plan_arguments = dict(arguments)
                plan_arguments.setdefault("task_type", tool.capability)
                plan = self.planner.build_plan(
                    session_id=session_id,
                    message=message,
                    arguments=plan_arguments,
                    previous_plan=previous_plan,
                    reasoning_trace=reasoning_trace or [],
                )
                return ToolObservation(
                    tool=action,
                    status="planned",
                    output={"plan": plan},
                )

            return ToolObservation(
                tool=action,
                status="error",
                error=f"Unknown or unsupported tool: {action}",
            )
        except Exception as exc:
            return ToolObservation(
                tool=action,
                status="error",
                error=str(exc),
            )

    async def call_tool(
        self,
        tool: ToolDefinition,
        **kwargs: Any,
    ) -> ToolObservation:
        """Compatibility entry point for explicit ToolDefinition calls."""

        return await self.execute(action=tool.name, **kwargs)
