"""Observation reflection and replan decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel

from agent_runtime.executor import ToolObservation
from agent_workflow.schemas import ExecutionPlan

if TYPE_CHECKING:
    from agent_runtime.react_agent import AgentDecision


class ReflectionResult(BaseModel):
    """Outcome of one reflection pass."""

    thought: str
    status: Literal["continue", "replan", "complete"]
    confidence: float
    reason: str


class ReflectionEngine:
    """Reflect on an observation without hardcoding a scientific workflow."""

    async def reflect(
        self,
        *,
        decision: "AgentDecision",
        observation: ToolObservation,
        plan: Optional[ExecutionPlan],
        iteration: int,
        max_iterations: int,
    ) -> ReflectionResult:
        if plan is not None:
            if plan.capability_status == "unavailable" and iteration < max_iterations:
                return ReflectionResult(
                    thought=(
                        "当前工具运行不可用，需要重新选择或调整计划能力。"
                    ),
                    status="replan",
                    confidence=0.72,
                    reason="runtime_unavailable",
                )
            return ReflectionResult(
                thought="计划已经形成，可以交给用户确认。",
                status="complete",
                confidence=max(decision.confidence, 0.8),
                reason="plan_ready",
            )

        if observation.status in {"selected"}:
            return ReflectionResult(
                thought=(
                    "工具已选定，下一轮需要根据工具输入契约生成计划。"
                ),
                status="continue",
                confidence=0.82,
                reason="tool_selected",
            )

        if observation.status == "error":
            status = "replan" if iteration < max_iterations else "complete"
            return ReflectionResult(
                thought="工具执行失败，需要根据错误观察重新规划。",
                status=status,
                confidence=0.55,
                reason=observation.error or "tool_error",
            )

        if decision.confidence < 0.55 and iteration < max_iterations:
            return ReflectionResult(
                thought="置信度不足，需要继续推理或补充工具观察。",
                status="replan",
                confidence=decision.confidence,
                reason="low_confidence",
            )

        return ReflectionResult(
            thought="当前观察足以结束本轮推理。",
            status="complete",
            confidence=decision.confidence,
            reason="observation_complete",
        )

    def describe(self, result: ReflectionResult) -> dict[str, Any]:
        return result.model_dump(mode="json")
