"""Session memory for research context and follow-up revisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from agent_runtime.tool_registry import OBJECTIVE_HINTS


class GoalMemory(BaseModel):
    """One remembered user goal."""

    message: str
    chemical_system: Optional[str] = None
    objectives: list[dict[str, Any]] = Field(default_factory=list)
    candidate_count: Optional[int] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ModelSelectionMemory(BaseModel):
    """One tool/model selection made by the capability registry."""

    tool_name: str
    capability: str = "material_generation"
    reason: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AgentMemory(BaseModel):
    """Persistent research context for one agent session."""

    session_id: str
    current_research_system: Optional[str] = None
    confirmed_parameters: dict[str, Any] = Field(default_factory=dict)
    proposed_parameters: dict[str, Any] = Field(default_factory=dict)
    historical_goals: list[GoalMemory] = Field(default_factory=list)
    model_history: list[ModelSelectionMemory] = Field(default_factory=list)
    last_plan_id: Optional[str] = None
    last_plan_revision: Optional[int] = None

    def remember_plan(self, plan: Any) -> None:
        """Record a proposed plan without treating suggestions as confirmed."""

        request = plan.request_spec
        system = getattr(request.composition, "chemical_system", None)
        if system:
            self.current_research_system = system

        objectives = [
            objective.model_dump(mode="json")
            for objective in request.objectives
        ]
        if request.task_type == "material_generation":
            self.historical_goals.append(
                GoalMemory(
                    message=plan.original_message,
                    chemical_system=system,
                    objectives=objectives,
                    candidate_count=request.candidate_count,
                )
            )
            self.historical_goals = self.historical_goals[-20:]

        for decision in plan.planning_decisions:
            parameter = decision.get("parameter")
            if not parameter or decision.get("value") is None:
                continue
            source = decision.get("source")
            if parameter == "model_id":
                self.model_history.append(
                    ModelSelectionMemory(
                        tool_name=str(decision["value"]),
                        reason=str(decision.get("rationale") or ""),
                    )
                )
                self.model_history = self.model_history[-20:]
            elif source in {"user", "memory"}:
                self.confirmed_parameters[parameter] = decision["value"]
            else:
                self.proposed_parameters[parameter] = decision["value"]

        for step in plan.steps:
            if step.parameter_sources.get("model_id") == "memory":
                self.model_history.append(
                    ModelSelectionMemory(
                        tool_name=step.model_id or "unknown",
                        reason="沿用 Agent Memory 中的历史工具选择。",
                    )
                )
        self.last_plan_id = plan.plan_id
        self.last_plan_revision = plan.revision

    def confirm_plan(self, plan: Any) -> None:
        """Promote a user-confirmed plan's proposed parameters."""

        for decision in plan.planning_decisions:
            parameter = decision.get("parameter")
            value = decision.get("value")
            if not parameter or parameter == "model_id" or value is None:
                continue
            self.confirmed_parameters[parameter] = value
            self.proposed_parameters.pop(parameter, None)
        self.last_plan_id = plan.plan_id
        self.last_plan_revision = plan.revision

    def apply_relative_revision(
        self,
        instruction: str,
    ) -> dict[str, Any]:
        """Resolve phrases such as “再提高一点磁密度” from prior context."""

        lowered = instruction.lower()
        mentioned = [
            property_name
            for property_name, hint in OBJECTIVE_HINTS.items()
            if any(alias.lower() in lowered for alias in hint.aliases)
        ]
        property_name = mentioned[0] if mentioned else self._last_property()
        if property_name is None:
            return {}

        increase = any(
            cue in instruction
            for cue in (
                "提高",
                "增加",
                "升高",
                "调高",
                "更高",
                "再高",
                "increase",
                "raise",
            )
        )
        decrease = any(
            cue in instruction
            for cue in (
                "降低",
                "减少",
                "调低",
                "更低",
                "再低",
                "decrease",
                "lower",
            )
        )
        stricter = "严格" in instruction or "strict" in lowered
        if not (increase or decrease or stricter):
            return {}

        base = self._base_value(property_name)
        if base is None:
            suggestion = self._suggested_value(property_name)
            if suggestion is None:
                return {}
            base = suggestion

        delta = self._increment(property_name, instruction)
        if property_name == "energy_above_hull":
            target = base - delta if (decrease or stricter) else base + delta
            operator = "<="
            semantic_goal = "strict_stable" if (decrease or stricter) else "relaxed_stable"
        else:
            target = base + delta if increase else base - delta
            operator = (
                ">="
                if property_name == "dft_mag_density"
                else ("<=" if decrease else ">=")
            )
            semantic_goal = (
                "higher_magnetic_density"
                if property_name == "dft_mag_density" and increase
                else None
            )

        target = max(0.0, round(float(target), 4))
        return {
            "objectives": [
                {
                    "property": property_name,
                    "operator": operator,
                    "target": target,
                    "unit": OBJECTIVE_HINTS[property_name].unit,
                    "semantic_goal": semantic_goal,
                    "constraint_type": "soft",
                }
            ],
            "reason": (
                f"根据 Agent Memory 将 {property_name} 从 "
                f"{base:g} 调整为 {target:g}。"
            ),
        }

    def context(self) -> dict[str, Any]:
        return {
            "current_research_system": self.current_research_system,
            "confirmed_parameters": self.confirmed_parameters,
            "proposed_parameters": self.proposed_parameters,
            "historical_goals": [
                goal.model_dump(mode="json")
                for goal in self.historical_goals[-5:]
            ],
            "model_history": [
                selection.model_dump(mode="json")
                for selection in self.model_history[-5:]
            ],
        }

    def _last_property(self) -> Optional[str]:
        for goal in reversed(self.historical_goals):
            if goal.objectives:
                return str(goal.objectives[-1].get("property") or "") or None
        return None

    def _base_value(self, property_name: str) -> Optional[float]:
        value = self.confirmed_parameters.get(property_name)
        if value is None:
            value = self.proposed_parameters.get(property_name)
        if value is None:
            for goal in reversed(self.historical_goals):
                for objective in reversed(goal.objectives):
                    if (
                        objective.get("property") == property_name
                        and objective.get("target") is not None
                    ):
                        value = objective["target"]
                        break
                if value is not None:
                    break
        return float(value) if value is not None else None

    @staticmethod
    def _suggested_value(property_name: str) -> Optional[float]:
        hint = OBJECTIVE_HINTS.get(property_name)
        return hint.suggested_value if hint else None

    @staticmethod
    def _increment(property_name: str, instruction: str) -> float:
        small = "一点" in instruction or "稍微" in instruction
        if property_name == "energy_above_hull":
            return 0.005 if small else 0.01
        if property_name == "dft_mag_density":
            return 0.02 if small else 0.05
        return 0.01 if small else 0.05


class InMemoryAgentMemoryStore:
    """Process-local memory store, matching the current session service."""

    def __init__(self) -> None:
        self._memory: dict[str, AgentMemory] = {}

    def get(self, session_id: str) -> AgentMemory:
        memory = self._memory.get(session_id)
        if memory is None:
            memory = AgentMemory(session_id=session_id)
            self._memory[session_id] = memory
        return memory

    def get_or_create(self, session_id: str) -> AgentMemory:
        return self.get(session_id)

    def clear(self, session_id: str) -> None:
        self._memory.pop(session_id, None)
