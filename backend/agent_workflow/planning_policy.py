"""Deterministic, inspectable defaults used by the agentic planner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from agent_workflow.schemas import ObjectiveSpec


@dataclass(frozen=True)
class PlanningDecision:
    """One deterministic planning decision and its provenance."""

    parameter: str
    value: Any
    source: str
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "value": self.value,
            "source": self.source,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ObjectivePolicyDefault:
    """Deterministic executable interpretation of a semantic objective."""

    property: str
    operator: str
    target: float
    unit: str
    rationale: str


class PlanningPolicy:
    """Provide controlled execution defaults without making scientific claims."""

    def __init__(
        self,
        *,
        default_candidate_count: Optional[int] = None,
        stability_threshold: Optional[float] = None,
    ):
        self.default_candidate_count = (
            default_candidate_count
            if default_candidate_count is not None
            else int(os.getenv("PLANNING_DEFAULT_CANDIDATE_COUNT", "8"))
        )
        self.stability_threshold = (
            stability_threshold
            if stability_threshold is not None
            else float(os.getenv("PLANNING_STABILITY_THRESHOLD", "0.1"))
        )
        self.semantic_objective_defaults = {
            "energy_above_hull:stable": ObjectivePolicyDefault(
                property="energy_above_hull",
                operator="<=",
                target=self.stability_threshold,
                unit="eV/atom",
                rationale=(
                    "“较稳定”按系统规划策略解释为较低的 "
                    "energy_above_hull。"
                ),
            ),
            "energy_above_hull:strict_stable": ObjectivePolicyDefault(
                property="energy_above_hull",
                operator="<=",
                target=self.stability_threshold / 2,
                unit="eV/atom",
                rationale=(
                    "“更严格稳定”按系统规划策略使用稳定性阈值的 "
                    "一半。"
                ),
            ),
            "energy_above_hull:relaxed_stable": ObjectivePolicyDefault(
                property="energy_above_hull",
                operator="<=",
                target=self.stability_threshold * 2,
                unit="eV/atom",
                rationale=(
                    "“较宽松稳定”按系统规划策略使用稳定性阈值的 "
                    "两倍。"
                ),
            ),
        }

    def candidate_count(
        self,
        explicit_count: Optional[int],
    ) -> PlanningDecision:
        if explicit_count is not None:
            return PlanningDecision(
                parameter="candidate_count",
                value=explicit_count,
                source="user",
                rationale="候选数量由用户明确指定。",
            )
        return PlanningDecision(
            parameter="candidate_count",
            value=self.default_candidate_count,
            source="planning_policy",
            rationale="用户未指定候选数量，采用系统规划策略默认值。",
        )

    def resolve_objective(
        self,
        objective: ObjectiveSpec,
    ) -> Optional[PlanningDecision]:
        if objective.target is not None:
            return PlanningDecision(
                parameter=objective.property,
                value=objective.target,
                source="user",
                rationale="目标数值由用户明确指定。",
            )

        if not objective.semantic_goal:
            return None

        key = f"{objective.property}:{objective.semantic_goal}"
        policy_default = self.semantic_objective_defaults.get(key)
        if policy_default is None:
            return None
        return PlanningDecision(
            parameter=objective.property,
            value=policy_default.target,
            source="planning_policy",
            rationale=policy_default.rationale,
        )


def get_planning_policy() -> PlanningPolicy:
    return PlanningPolicy()
