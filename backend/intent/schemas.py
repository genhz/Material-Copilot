"""Structured intent decisions produced before Agent execution."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


IntentLabel = Literal[
    "science_chat",
    "material_lookup",
    "element_substitution",
    "material_generation",
    "clarification",
]


class IntentDecision(BaseModel):
    """Semantic route and optional generation parameters."""

    intent: IntentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    target_magnetic_density: Optional[float] = Field(default=None, gt=0, le=1)
    num_candidates: Optional[int] = Field(default=None, ge=1, le=16)
    guidance_scale: Optional[float] = Field(default=None, ge=0, le=20)
    seed: Optional[int] = None

