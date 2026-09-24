"""Compatibility facade for shared material composition constraints."""

from agent_workflow.normalization import (
    ELEMENT_GROUPS,
    ConstraintConflict,
    NormalizedCompositionConstraints,
    canonical_element_group,
    composition_violation,
    expand_element_group,
    normalize_composition_constraints,
)

__all__ = [
    "ConstraintConflict",
    "ELEMENT_GROUPS",
    "NormalizedCompositionConstraints",
    "canonical_element_group",
    "composition_violation",
    "expand_element_group",
    "normalize_composition_constraints",
]
