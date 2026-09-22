"""Structured requirements, execution plans, and realtime workflow state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PlanStatus = Literal[
    "awaiting_confirmation",
    "confirmed",
    "executing",
    "completed",
    "partial",
    "failed",
    "cancelled",
]

StepStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class ObjectiveSpec(BaseModel):
    """One material property target."""

    property: str
    operator: Literal[">=", "<=", "~="] = ">="
    target: float
    kind: Literal["hard", "soft"] = "soft"


class MaterialRequestSpec(BaseModel):
    """Validated semantic representation of a user's material request."""

    goal: str = "discover_material"
    material_type: Optional[str] = None
    required_elements: list[str] = Field(default_factory=list)
    allowed_elements: list[str] = Field(default_factory=list)
    excluded_elements: list[str] = Field(default_factory=list)
    chemical_system: Optional[str] = None
    objectives: list[ObjectiveSpec] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    """One executable or logical step in a material workflow."""

    id: str
    kind: Literal["generate", "filter", "rank"]
    title: str
    description: str
    status: StepStatus = "pending"
    model_id: Optional[str] = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    num_candidates: Optional[int] = None
    guidance_scale: Optional[float] = None
    seed: Optional[int] = None
    job_id: Optional[str] = None
    progress: float = 0.0
    error_message: Optional[str] = None


class ExecutionPlan(BaseModel):
    """Editable plan proposed before any costly generation starts."""

    plan_id: str
    session_id: str
    revision: int = 1
    status: PlanStatus = "awaiting_confirmation"
    original_message: str
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    request_spec: MaterialRequestSpec
    steps: list[PlanStep]
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class WorkflowRunState(BaseModel):
    """Current execution state for one confirmed plan."""

    workflow_id: str
    plan_id: str
    session_id: str
    status: Literal[
        "queued",
        "running",
        "completed",
        "partial",
        "failed",
        "cancelled",
    ] = "queued"
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_step_id: Optional[str] = None
    job_ids: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    error_message: Optional[str] = None
