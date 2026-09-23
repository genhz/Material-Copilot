"""Formal workflow, plan, step, and result state transitions."""

from __future__ import annotations

from enum import Enum


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    CLARIFICATION = "clarification"
    READY = "ready"
    CONFIRMED = "confirmed"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABORTED = "aborted"


class PlanStatus(str, Enum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABORTED = "aborted"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowResultStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"


WORKFLOW_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: frozenset(
        {WorkflowStatus.CLARIFICATION, WorkflowStatus.READY}
    ),
    WorkflowStatus.CLARIFICATION: frozenset(
        {WorkflowStatus.DRAFT, WorkflowStatus.READY}
    ),
    WorkflowStatus.READY: frozenset(
        {WorkflowStatus.DRAFT, WorkflowStatus.CLARIFICATION, WorkflowStatus.CONFIRMED}
    ),
    WorkflowStatus.CONFIRMED: frozenset(
        {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.RUNNING: frozenset(
        {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.PARTIAL,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.ABORTED,
        }
    ),
    WorkflowStatus.COMPLETED: frozenset(),
    WorkflowStatus.PARTIAL: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
    WorkflowStatus.ABORTED: frozenset(),
}

WORKFLOW_TERMINAL_STATUSES = frozenset(
    {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.PARTIAL,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.ABORTED,
    }
)


PLAN_TRANSITIONS: dict[PlanStatus, frozenset[PlanStatus]] = {
    PlanStatus.AWAITING_CONFIRMATION: frozenset(
        {PlanStatus.CONFIRMED, PlanStatus.CANCELLED}
    ),
    PlanStatus.CONFIRMED: frozenset(
        {PlanStatus.EXECUTING, PlanStatus.CANCELLED}
    ),
    PlanStatus.EXECUTING: frozenset(
        {
            PlanStatus.COMPLETED,
            PlanStatus.PARTIAL,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
            PlanStatus.ABORTED,
        }
    ),
    PlanStatus.COMPLETED: frozenset(),
    PlanStatus.PARTIAL: frozenset(),
    PlanStatus.FAILED: frozenset(),
    PlanStatus.CANCELLED: frozenset(),
    PlanStatus.ABORTED: frozenset(),
}

PLAN_TERMINAL_STATUSES = frozenset(
    {
        PlanStatus.COMPLETED,
        PlanStatus.PARTIAL,
        PlanStatus.FAILED,
        PlanStatus.CANCELLED,
        PlanStatus.ABORTED,
    }
)


STEP_TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset(
        {
            StepStatus.RUNNING,
            StepStatus.BLOCKED,
            StepStatus.SKIPPED,
            StepStatus.CANCELLED,
        }
    ),
    StepStatus.RUNNING: frozenset(
        {
            StepStatus.COMPLETED,
            StepStatus.FAILED,
            StepStatus.BLOCKED,
            StepStatus.CANCELLED,
        }
    ),
    StepStatus.COMPLETED: frozenset(),
    StepStatus.FAILED: frozenset({StepStatus.RUNNING}),
    StepStatus.BLOCKED: frozenset(),
    StepStatus.SKIPPED: frozenset(),
    StepStatus.CANCELLED: frozenset(),
}


class InvalidStateTransition(ValueError):
    """Raised when a state object tries an illegal transition."""


def ensure_transition(current: Enum, target: Enum, transitions: dict) -> None:
    """Validate one transition while allowing idempotent writes."""

    if current == target:
        return
    allowed = transitions.get(current, frozenset())
    if target not in allowed:
        raise InvalidStateTransition(
            f"Illegal transition: {current.value} -> {target.value}"
        )


def aggregate_workflow_status(
    job_statuses: list[object],
    *,
    has_failures: bool = False,
) -> WorkflowStatus:
    """Aggregate independent Job states into one Workflow terminal state."""

    values = [
        getattr(status, "value", str(status))
        for status in job_statuses
    ]
    completed = values.count("completed")
    cancelled = values.count("cancelled")
    if values and completed == len(values) and not has_failures:
        return WorkflowStatus.COMPLETED
    if completed > 0:
        return WorkflowStatus.PARTIAL
    if values and cancelled == len(values):
        return WorkflowStatus.CANCELLED
    return WorkflowStatus.FAILED
