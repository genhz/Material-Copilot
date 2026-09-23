"""Structured requirements, execution plans, and realtime workflow state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field, model_validator

from generation.schemas import JobStatus
from agent_workflow.state import (
    PLAN_TRANSITIONS,
    STEP_TRANSITIONS,
    WORKFLOW_TRANSITIONS,
    InvalidStateTransition,
    PlanStatus,
    StepStatus,
    WorkflowResultStatus,
    WorkflowStatus,
    ensure_transition,
)

TaskType = Literal[
    "material_generation",
    "material_lookup",
    "element_substitution",
    "science_chat",
    "clarification",
]
ObjectiveOperator = Literal[">=", "<=", "~="]
ConstraintType = Literal["hard", "soft"]
ExplorationMode = Literal["single_model", "multi_model"]
CapabilityPlanningStatus = Literal[
    "ready",
    "clarification",
    "unsupported",
    "unavailable",
]
ParameterSource = Literal[
    "user",
    "model_default",
    "planning_policy",
    "agent_suggestion",
    "memory",
    "derived",
]


class ObjectiveSpec(BaseModel):
    """One material property target."""

    property: str
    operator: ObjectiveOperator = ">="
    target: Optional[float] = None
    unit: Optional[str] = None
    semantic_goal: Optional[str] = None
    constraint_type: ConstraintType = "soft"
    priority: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_kind(cls, value: Any) -> Any:
        """Accept the previous `kind` field without exposing a second model."""

        if isinstance(value, dict) and "kind" in value:
            updated = dict(value)
            legacy_kind = updated.pop("kind")
            updated.setdefault("constraint_type", legacy_kind)
            return updated
        return value

    @computed_field
    @property
    def kind(self) -> ConstraintType:
        """Serialized compatibility alias for existing workflow consumers."""

        return self.constraint_type


class CompositionSpec(BaseModel):
    """Chemical composition requirements."""

    required_elements: list[str] = Field(default_factory=list)
    allowed_elements: list[str] = Field(default_factory=list)
    excluded_elements: list[str] = Field(default_factory=list)
    chemical_system: Optional[str] = None
    exact_formula: Optional[str] = None


class StructureSpec(BaseModel):
    """Crystal structure requirements."""

    space_group: Optional[int] = Field(default=None, ge=1, le=230)
    crystal_system: Optional[str] = None


class InputMaterialSpec(BaseModel):
    """Existing material referenced by a lookup or substitution request."""

    formula: Optional[str] = None
    cif: Optional[str] = None
    material_id: Optional[str] = None
    substitutions: dict[str, str] = Field(default_factory=dict)


class ConstraintSpec(BaseModel):
    """One non-objective requirement expressed by the user."""

    constraint_type: str
    value: Optional[str | float | int | bool] = None
    unit: Optional[str] = None
    description: Optional[str] = None


class MaterialRequirementSpec(BaseModel):
    """Validated representation of what the user wants to accomplish."""

    task_type: TaskType = "science_chat"
    application: Optional[str] = None

    objectives: list[ObjectiveSpec] = Field(default_factory=list)
    composition: CompositionSpec = Field(default_factory=CompositionSpec)
    structure: StructureSpec = Field(default_factory=StructureSpec)
    input_material: Optional[InputMaterialSpec] = None

    candidate_count: Optional[int] = Field(default=None, ge=1)
    exploration_mode: ExplorationMode = "single_model"
    model_preferences: list[str] = Field(default_factory=list)

    constraints: list[ConstraintSpec] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    # Legacy flat fields are synchronized with `composition` below.
    goal: str = "discover_material"
    material_type: Optional[str] = None
    required_elements: list[str] = Field(default_factory=list)
    allowed_elements: list[str] = Field(default_factory=list)
    excluded_elements: list[str] = Field(default_factory=list)
    chemical_system: Optional[str] = None
    ambiguities: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _synchronize_composition(cls, value: Any) -> Any:
        """Keep old flat composition fields and new nested fields interchangeable."""

        if not isinstance(value, dict):
            return value

        updated = dict(value)
        raw_composition = updated.get("composition")
        composition = (
            dict(raw_composition)
            if isinstance(raw_composition, dict)
            else {}
        )
        for field_name in (
            "required_elements",
            "allowed_elements",
            "excluded_elements",
            "chemical_system",
        ):
            if field_name in updated and field_name not in composition:
                composition[field_name] = updated[field_name]
            elif field_name in composition and field_name not in updated:
                updated[field_name] = composition[field_name]

        if composition:
            updated["composition"] = composition
        return updated

    @model_validator(mode="after")
    def _sync_flat_composition(self) -> "MaterialRequirementSpec":
        """Expose nested parser output through the legacy flat workflow fields."""

        for field_name in (
            "required_elements",
            "allowed_elements",
            "excluded_elements",
            "chemical_system",
        ):
            setattr(self, field_name, getattr(self.composition, field_name))
        return self


# Backward-compatible name used throughout the existing workflow.
MaterialRequestSpec = MaterialRequirementSpec


class PlanStep(BaseModel):
    """One executable or logical step in a material workflow."""

    id: str
    kind: Literal[
        "ask",
        "generate",
        "evaluate",
        "filter",
        "rank",
        "material_lookup",
        "element_substitution",
        "science_chat",
    ]
    title: str
    description: str
    status: StepStatus = StepStatus.PENDING
    model_id: Optional[str] = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    parameter_sources: dict[str, ParameterSource] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    num_candidates: Optional[int] = None
    guidance_scale: Optional[float] = None
    seed: Optional[int] = None
    job_id: Optional[str] = None
    progress: float = 0.0
    error_message: Optional[str] = None
    required: bool = True
    depends_on: list[str] = Field(default_factory=list)
    dependency_policy: Literal["all", "any"] = "all"
    on_failure: Literal["abort", "continue", "retry"] = "abort"
    max_retries: int = Field(default=0, ge=0, le=3)
    retry_delay_seconds: float = Field(default=0.0, ge=0.0, le=30.0)
    produces_candidates: bool = False
    requires_candidates: bool = False
    question: Optional[str] = None
    suggestion: Optional[dict[str, Any]] = None

    def transition(self, target: StepStatus) -> None:
        target = StepStatus(target)
        ensure_transition(self.status, target, STEP_TRANSITIONS)
        self.status = target


class ExecutionPlan(BaseModel):
    """Editable plan proposed before any costly generation starts."""

    plan_id: str
    session_id: str
    revision: int = 1
    status: PlanStatus = PlanStatus.AWAITING_CONFIRMATION
    original_message: str
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    capability_status: CapabilityPlanningStatus = "ready"
    decision_reasons: list[str] = Field(default_factory=list)
    candidate_models: list[str] = Field(default_factory=list)
    planning_decisions: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    reflection: Optional[str] = None
    request_spec: MaterialRequirementSpec
    steps: list[PlanStep]
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def transition(self, target: PlanStatus) -> None:
        target = PlanStatus(target)
        ensure_transition(self.status, target, PLAN_TRANSITIONS)
        self.status = target


class WorkflowResultJob(BaseModel):
    """One generation job included in a workflow result."""

    step_id: str
    job_id: str
    model_id: str
    model_label: Optional[str] = None
    status: JobStatus = JobStatus.QUEUED
    candidate_count: int = 0
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class WorkflowResultStep(BaseModel):
    """Serializable output from a non-generation workflow step."""

    step_id: str
    kind: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class WorkflowResult(BaseModel):
    """Stable result projection returned with a completed workflow."""

    status: WorkflowResultStatus
    task_type: TaskType = "material_generation"
    primary_job_id: Optional[str] = None
    jobs: list[WorkflowResultJob] = Field(default_factory=list)
    steps: list[WorkflowResultStep] = Field(default_factory=list)
    message: Optional[str] = None
    material_data: Optional[dict[str, Any]] = None
    requested_candidate_count: int = 0
    candidate_count: int = 0
    completed_job_count: int = 0
    failed_job_count: int = 0
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRunState(BaseModel):
    """Current execution state for one confirmed plan."""

    workflow_id: str
    plan_id: str
    session_id: str
    status: WorkflowStatus = WorkflowStatus.DRAFT
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_step_id: Optional[str] = None
    job_ids: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    failed_step_id: Optional[str] = None
    blocked_step_ids: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    result: Optional[WorkflowResult] = None

    def transition(self, target: WorkflowStatus) -> None:
        target = WorkflowStatus(target)
        ensure_transition(self.status, target, WORKFLOW_TRANSITIONS)
        self.status = target
