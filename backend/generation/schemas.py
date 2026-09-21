"""Pydantic schemas for MatterGen generation jobs and campaigns."""

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

ConditionValue = float | int | str


class GenerationRequest(BaseModel):
    """Validated request for one MatterGen generation job."""

    model_id: Optional[str] = None
    conditions: dict[str, ConditionValue] = Field(default_factory=dict)
    target_magnetic_density: Optional[float] = Field(
        default=None, gt=0, le=1
    )
    hhi_score: Optional[float] = Field(default=None, ge=0, le=1)
    num_candidates: int = Field(default=2, ge=1, le=16)
    guidance_scale: Optional[float] = Field(default=None, ge=0, le=20)
    seed: Optional[int] = None

    def _input_conditions(self) -> dict[str, ConditionValue]:
        merged = dict(self.conditions)
        if self.target_magnetic_density is not None:
            merged.setdefault(
                "dft_mag_density", self.target_magnetic_density
            )
        if self.hhi_score is not None:
            merged.setdefault("hhi_score", self.hhi_score)
        return merged

    def resolve_model_id(self) -> str:
        if self.model_id:
            return self.model_id

        keys = set(self._input_conditions())
        if {"chemical_system", "energy_above_hull"} <= keys:
            return "chemical_system_energy_above_hull"
        if {"dft_mag_density", "hhi_score"} <= keys:
            return "dft_mag_density_hhi_score"
        if "chemical_system" in keys:
            return "chemical_system"
        if "dft_mag_density" in keys:
            return "dft_mag_density"
        if "dft_band_gap" in keys:
            return "dft_band_gap"
        if "ml_bulk_modulus" in keys:
            return "ml_bulk_modulus"
        if "space_group" in keys:
            return "space_group"
        return "dft_mag_density"

    def resolved_conditions(self) -> dict[str, ConditionValue]:
        from generation.model_registry import get_model_spec

        spec = get_model_spec(self.resolve_model_id())
        supplied = self._input_conditions()
        unknown = set(supplied) - set(spec.conditions)
        if unknown:
            raise ValueError(
                f"模型 {spec.model_id} 不支持条件：{sorted(unknown)}"
            )

        resolved: dict[str, ConditionValue] = {}
        for name, condition in spec.conditions.items():
            value = supplied.get(name, condition.default)
            if value is None and condition.required:
                raise ValueError(f"缺少模型条件：{name}")

            if condition.value_type == "string":
                value = str(value)
            elif condition.value_type == "int":
                value = int(value)
            else:
                value = float(value)

            if condition.minimum is not None or condition.maximum is not None:
                numeric_value = float(value)
                if (
                    condition.minimum is not None
                    and numeric_value < condition.minimum
                ):
                    raise ValueError(
                        f"{name} 小于允许值 {condition.minimum}"
                    )
                if (
                    condition.maximum is not None
                    and numeric_value > condition.maximum
                ):
                    raise ValueError(
                        f"{name} 大于允许值 {condition.maximum}"
                    )
            resolved[name] = value

        return resolved

    def normalized(self) -> "GenerationRequest":
        return self.model_copy(
            update={
                "model_id": self.resolve_model_id(),
                "conditions": self.resolved_conditions(),
            }
        )


class GenerationJob(BaseModel):
    """Persisted generation job state."""

    job_id: str
    status: JobStatus = "queued"
    phase: JobPhase = "queued"
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: Optional[str] = None
    sequence: int = 0
    model_id: str = "dft_mag_density"
    model_label: Optional[str] = None
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
    model_id: str = "legacy"
    model_label: str = "旧版 MatterGen"
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
    """Registered MatterGen model metadata."""

    model_id: str
    display_name: str
    description: str
    category: str
    available: bool
    conditions: dict[str, Any]
    missing_reason: Optional[str] = None
    download_url: Optional[str] = None


CampaignStatus = Literal[
    "queued",
    "running",
    "partial",
    "completed",
    "failed",
    "cancelled",
]


class CampaignRunRequest(BaseModel):
    model_id: str
    conditions: dict[str, ConditionValue] = Field(default_factory=dict)
    num_candidates: int = Field(default=2, ge=1, le=16)
    guidance_scale: Optional[float] = Field(default=None, ge=0, le=20)
    seed: Optional[int] = None


class CampaignRequest(BaseModel):
    name: str = "MatterGen campaign"
    runs: list[CampaignRunRequest] = Field(min_length=1, max_length=12)
    max_concurrency: int = Field(default=1, ge=1, le=2)


class CampaignRunState(BaseModel):
    run_id: str
    model_id: str
    model_label: str
    conditions: dict[str, Any]
    request: GenerationRequest
    job_id: Optional[str] = None
    status: JobStatus = "queued"
    progress: float = 0.0
    error_message: Optional[str] = None


class CampaignJob(BaseModel):
    campaign_id: str
    name: str
    status: CampaignStatus = "queued"
    progress: float = 0.0
    runs: list[CampaignRunState] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: Optional[datetime] = None


class CampaignCandidateGroup(BaseModel):
    model_id: str
    model_label: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    candidates: list[GeneratedCandidate] = Field(default_factory=list)


class CampaignCandidateCollection(BaseModel):
    campaign_id: str
    groups: list[CampaignCandidateGroup] = Field(default_factory=list)
    candidates: list[GeneratedCandidate] = Field(default_factory=list)
    total_count: int = 0
