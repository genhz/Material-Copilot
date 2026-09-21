"""Pydantic schemas for MatterGen generation jobs."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


JobStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]

JobPhase = Literal[
    "queued",
    "loading_model",
    "generating",
    "postprocessing",
    "completed",
    "failed",
    "cancelled",
]


class GenerationRequest(BaseModel):
    """Validated request for a magnetic-material generation job."""

    target_magnetic_density: float = Field(gt=0, le=1)
    num_candidates: int = Field(default=2, ge=1, le=16)
    guidance_scale: float = Field(default=2.0, ge=0, le=20)
    seed: Optional[int] = None


class GenerationJob(BaseModel):
    """Persisted generation job state."""

    job_id: str
    status: JobStatus = "queued"
    phase: JobPhase = "queued"
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: Optional[str] = None
    sequence: int = 0
    model_id: str = "dft_mag_density"
    request: GenerationRequest
    created_at: datetime
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    worker_pid: Optional[int] = None


class GeneratedCandidate(BaseModel):
    """A validated CIF candidate returned by MatterGen."""

    candidate_id: str
    material_id: str
    formula: str
    pretty_formula: str
    cif: str
    density: Optional[float] = None
    formula_unit: Optional[int] = None
    elements: list[str] = Field(default_factory=list)
    source: Literal["mattergen"] = "mattergen"
    generation_conditions: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    spacegroup_symbol: Optional[str] = None
    spacegroup_number: Optional[int] = None
    crystal_system: Optional[str] = None


class CandidateCollection(BaseModel):
    """Persisted candidate collection and validation summary."""

    candidates: list[GeneratedCandidate] = Field(default_factory=list)
    invalid_count: int = 0
    total_count: int = 0
    validation: dict[str, Any] = Field(default_factory=dict)


class ModelInfo(BaseModel):
    """Available MatterGen model metadata."""

    model_id: str
    available: bool
    conditions: list[str]
