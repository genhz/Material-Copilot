"""Capability matching over the existing MatterGen model registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional, Sequence

from agent_workflow.schemas import MaterialRequirementSpec
from config import get_mattergen_config
from generation.adapter import MatterGenAdapter
from generation.exceptions import GenerationError
from generation.model_registry import (
    MatterGenModelSpec,
    list_model_specs,
)


RuntimeProbe = Callable[[MatterGenModelSpec], Optional[bool]]
MatchCoverage = Literal["full", "partial", "incompatible"]
DecisionStatus = Literal[
    "compatible",
    "clarification",
    "unsupported",
    "no_match",
    "preference_incompatible",
    "preference_not_found",
]


@dataclass(frozen=True)
class ModelCapability:
    """Public capability view derived from one MatterGenModelSpec."""

    model_id: str
    display_name: str
    task_types: tuple[str, ...]
    supported_properties: tuple[str, ...]
    supported_conditions: tuple[str, ...]
    objective_constraints: dict[str, dict[str, object]]
    objective_sets: tuple[frozenset[str], ...]
    required_inputs: tuple[str, ...]
    supports_composition: bool
    supports_exact_formula: bool
    supports_space_group: bool
    supports_crystal_system: bool
    postprocessors: tuple[str, ...]
    default_guidance_scale: float
    static_available: bool
    runtime_available: Optional[bool]

    @property
    def joint_objectives(self) -> tuple[tuple[str, ...], ...]:
        return tuple(
            tuple(sorted(objective_set))
            for objective_set in self.objective_sets
            if len(objective_set) > 1
        )


@dataclass(frozen=True)
class ToolCapability:
    """Capability implemented by one existing material tool."""

    name: str
    task_type: str
    step_kind: str
    description: str
    requires_confirmation: bool = True


@dataclass(frozen=True)
class CapabilityMatch:
    """Detailed capability match for one requirement/model pair."""

    capability: ModelCapability
    compatible: bool
    coverage: MatchCoverage
    matched_objectives: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    postprocessors: tuple[str, ...]
    runtime_available: Optional[bool]
    reasons: tuple[str, ...]

    @property
    def model_id(self) -> str:
        return self.capability.model_id

    @property
    def supports(self) -> dict[str, bool]:
        """Expose inspectable capability evidence to planning policy code."""

        evidence = {
            property_name: property_name in self.matched_objectives
            for property_name in self.capability.supported_properties
        }
        evidence.update(
            {
                "chemical_system": self.capability.supports_composition,
                "space_group": self.capability.supports_space_group,
                "exact_formula": self.capability.supports_exact_formula,
                "crystal_system": self.capability.supports_crystal_system,
            }
        )
        return evidence


@dataclass(frozen=True)
class CapabilityDecision:
    """Aggregate result used by the Planner without making execution decisions."""

    status: DecisionStatus
    matches: tuple[CapabilityMatch, ...]
    reasons: tuple[str, ...]

    @property
    def compatible_models(self) -> tuple[str, ...]:
        return tuple(match.model_id for match in self.matches)


class CapabilityRegistry:
    """Query static model capabilities and runtime preflight independently."""

    def __init__(
        self,
        model_specs: Optional[Sequence[MatterGenModelSpec]] = None,
        *,
        runtime_probe: Optional[RuntimeProbe] = None,
        cache_runtime: bool = True,
    ):
        specs = list(
            list_model_specs() if model_specs is None else model_specs
        )
        self._specs = {spec.model_id: spec for spec in specs}
        self._spec_order = {spec.model_id: index for index, spec in enumerate(specs)}
        self._runtime_probe = runtime_probe or self._default_runtime_probe()
        self._cache_runtime = cache_runtime
        self._runtime_cache: dict[str, Optional[bool]] = {}
        self._tool_capabilities = {
            capability.task_type: capability
            for capability in (
                ToolCapability(
                    name="material_search",
                    task_type="material_lookup",
                    step_kind="material_lookup",
                    description="查询 Materials Project 中的材料结构与性质。",
                ),
                ToolCapability(
                    name="element_substitution",
                    task_type="element_substitution",
                    step_kind="element_substitution",
                    description="替换已有材料结构中的元素。",
                ),
                ToolCapability(
                    name="chat",
                    task_type="science_chat",
                    step_kind="science_chat",
                    description="回答材料科学概念和讨论问题。",
                ),
            )
        }

    @staticmethod
    def _default_runtime_probe() -> RuntimeProbe:
        adapter = MatterGenAdapter(get_mattergen_config())

        def probe(spec: MatterGenModelSpec) -> bool:
            try:
                adapter.preflight(spec)
                return True
            except GenerationError:
                return False

        return probe

    def runtime_available(self, model_id: str) -> Optional[bool]:
        spec = self._specs.get(model_id)
        if spec is None:
            return None
        if self._cache_runtime and model_id in self._runtime_cache:
            return self._runtime_cache[model_id]

        try:
            available = self._runtime_probe(spec)
        except Exception:
            available = False

        if self._cache_runtime:
            self._runtime_cache[model_id] = available
        return available

    def get_tool_capability(
        self,
        task_type: str,
    ) -> Optional[ToolCapability]:
        return self._tool_capabilities.get(task_type)

    def tool_capabilities(self) -> list[ToolCapability]:
        return list(self._tool_capabilities.values())

    def get(
        self,
        model_id: str,
        *,
        include_runtime: bool = True,
    ) -> Optional[ModelCapability]:
        spec = self._specs.get(model_id)
        if spec is None:
            return None
        return self._to_capability(
            spec,
            runtime_available=(
                self.runtime_available(model_id) if include_runtime else None
            ),
        )

    def all(self, *, include_runtime: bool = True) -> list[ModelCapability]:
        return [
            capability
            for spec in self._specs.values()
            if (
                capability := self.get(
                    spec.model_id,
                    include_runtime=include_runtime,
                )
            )
            is not None
        ]

    def supports(
        self,
        model_id: str,
        requirement: MaterialRequirementSpec,
    ) -> bool:
        match = self.match_model(model_id, requirement)
        return bool(
            match
            and match.compatible
            and not match.missing_inputs
        )

    def find_compatible(
        self,
        requirement: MaterialRequirementSpec,
    ) -> list[ModelCapability]:
        matches = self.match_requirement(requirement)
        full_matches = [
            match for match in matches if not match.missing_inputs
        ]
        return [
            match.capability
            for match in (full_matches or matches)
        ]

    def match_model(
        self,
        model_id: str,
        requirement: MaterialRequirementSpec,
    ) -> Optional[CapabilityMatch]:
        spec = self._specs.get(model_id)
        if spec is None:
            return None
        return self._match_spec(spec, requirement)

    def match_requirement(
        self,
        requirement: MaterialRequirementSpec,
    ) -> list[CapabilityMatch]:
        """Return all compatible matches, ranked by non-subjective facts."""

        specs = list(self._specs.values())
        if requirement.model_preferences:
            preferred = set(requirement.model_preferences)
            specs = [
                spec for spec in specs if spec.model_id in preferred
            ]

        matches = [
            match
            for spec in specs
            if (match := self._match_spec(spec, requirement)).compatible
        ]
        matches.sort(key=self._match_priority)
        return matches

    def resolve(
        self,
        requirement: MaterialRequirementSpec,
    ) -> CapabilityDecision:
        """Explain whether a requirement can be mapped to static capabilities."""

        if requirement.task_type == "clarification":
            return CapabilityDecision(
                status="clarification",
                matches=(),
                reasons=tuple(
                    requirement.missing_information
                    or ["material_property_objective"]
                ),
            )
        if requirement.task_type != "material_generation":
            return CapabilityDecision(
                status="no_match",
                matches=(),
                reasons=("requirement is not a material generation task",),
            )
        if requirement.unsupported_requirements:
            return CapabilityDecision(
                status="unsupported",
                matches=(),
                reasons=tuple(requirement.unsupported_requirements),
            )
        if not self._has_matchable_requirement(requirement):
            return CapabilityDecision(
                status="unsupported",
                matches=(),
                reasons=("material_property_objective",),
            )

        if requirement.model_preferences:
            unknown = [
                model_id
                for model_id in requirement.model_preferences
                if model_id not in self._specs
            ]
            if unknown:
                return CapabilityDecision(
                    status="preference_not_found",
                    matches=(),
                    reasons=tuple(unknown),
                )

        matches = self.match_requirement(requirement)
        if matches:
            full_matches = [
                match for match in matches if not match.missing_inputs
            ]
            if not full_matches:
                missing_inputs = tuple(
                    dict.fromkeys(
                        input_name
                        for match in matches
                        for input_name in match.missing_inputs
                    )
                )
                return CapabilityDecision(
                    status="unsupported",
                    matches=tuple(matches),
                    reasons=(
                        "no_complete_capability_for_requirement",
                        *missing_inputs,
                    ),
                )
            return CapabilityDecision(
                status="compatible",
                matches=tuple(full_matches),
                reasons=(),
            )
        if requirement.model_preferences:
            return CapabilityDecision(
                status="preference_incompatible",
                matches=(),
                reasons=tuple(requirement.model_preferences),
            )
        return CapabilityDecision(
            status="unsupported",
            matches=(),
            reasons=tuple(
                objective.property
                for objective in requirement.objectives
            )
            or ("no_registered_capability",),
        )

    def _to_capability(
        self,
        spec: MatterGenModelSpec,
        *,
        runtime_available: Optional[bool],
    ) -> ModelCapability:
        supported_properties = tuple(
            sorted(
                {
                    property_name
                    for objective_set in spec.objective_sets
                    for property_name in objective_set
                }
            )
        )
        return ModelCapability(
            model_id=spec.model_id,
            display_name=spec.display_name,
            task_types=spec.task_types,
            supported_properties=supported_properties,
            supported_conditions=tuple(spec.conditions),
            objective_constraints={
                name: condition.as_dict()
                for name, condition in spec.conditions.items()
            },
            objective_sets=spec.objective_sets,
            required_inputs=spec.required_inputs,
            supports_composition=spec.supports_composition,
            supports_exact_formula=spec.supports_exact_formula,
            supports_space_group=spec.supports_space_group,
            supports_crystal_system=spec.supports_crystal_system,
            postprocessors=spec.postprocessors,
            default_guidance_scale=spec.default_guidance_scale,
            static_available=spec.static_available,
            runtime_available=runtime_available,
        )

    def _match_spec(
        self,
        spec: MatterGenModelSpec,
        requirement: MaterialRequirementSpec,
    ) -> CapabilityMatch:
        capability = self._to_capability(
            spec,
            runtime_available=self.runtime_available(spec.model_id),
        )
        if (
            not spec.static_available
            or requirement.task_type != "material_generation"
        ):
            return self._incompatible(
                capability,
                "static capability unavailable"
                if not spec.static_available
                else "requirement is not a material generation task",
            )

        if requirement.unsupported_requirements:
            return self._incompatible(
                capability,
                "unsupported requirements: "
                + ", ".join(requirement.unsupported_requirements),
            )

        objective_properties = self._objective_properties(requirement)
        objective_set = self._select_objective_set(
            objective_properties,
            spec.objective_sets,
        )
        if objective_set is None:
            return self._incompatible(
                capability,
                "objectives are not covered by one generation capability",
            )

        missing_context: list[str] = []
        for required_input in spec.required_inputs:
            if required_input == "chemical_system":
                if not requirement.composition.chemical_system:
                    missing_context.append("chemical_system")
            elif required_input == "space_group":
                if requirement.structure.space_group is None:
                    missing_context.append("space_group")

        if missing_context:
            return self._incompatible(
                capability,
                "missing required inputs: " + ", ".join(missing_context),
            )

        if (
            requirement.composition.exact_formula
            and not spec.supports_exact_formula
        ):
            return self._incompatible(
                capability,
                "exact formula generation is not supported",
            )

        additional_objectives = sorted(
            objective_set - objective_properties
        )

        postprocessors: list[str] = []
        coverage: MatchCoverage = (
            "partial" if additional_objectives else "full"
        )
        reasons: list[str] = []
        if additional_objectives:
            reasons.append(
                "additional inputs required: "
                + ", ".join(additional_objectives)
            )

        composition = requirement.composition
        if composition.chemical_system:
            if spec.supports_composition:
                reasons.append("chemical system is a generation condition")
            elif (
                objective_properties
                and "element_composition_filter" in spec.postprocessors
            ):
                coverage = "partial"
                postprocessors.append("element_composition_filter")
                reasons.append(
                    "chemical system is satisfied by post-generation filtering"
                )
            else:
                return self._incompatible(
                    capability,
                    "chemical system is not supported by this model",
                )

        if (
            composition.required_elements
            or composition.allowed_elements
            or composition.excluded_elements
        ):
            if "element_composition_filter" not in spec.postprocessors:
                return self._incompatible(
                    capability,
                    "element composition constraints are not supported",
                )
            coverage = "partial" if coverage == "full" else coverage
            postprocessors.append("element_composition_filter")
            reasons.append("element constraints use the composition postprocessor")

        if requirement.structure.space_group is not None:
            if not spec.supports_space_group:
                return self._incompatible(
                    capability,
                    "space group generation is not supported by this model",
                )
            reasons.append("space group is a generation condition")

        if requirement.structure.crystal_system:
            if not spec.supports_crystal_system:
                return self._incompatible(
                    capability,
                    "crystal system generation is not supported by this model",
                )

        return CapabilityMatch(
            capability=capability,
            compatible=True,
            coverage=coverage,
            matched_objectives=tuple(sorted(objective_properties)),
            missing_inputs=tuple(additional_objectives),
            postprocessors=tuple(dict.fromkeys(postprocessors)),
            runtime_available=capability.runtime_available,
            reasons=tuple(reasons),
        )

    def _incompatible(
        self,
        capability: ModelCapability,
        reason: str,
        *,
        coverage: MatchCoverage = "incompatible",
        matched_objectives: tuple[str, ...] = (),
    ) -> CapabilityMatch:
        return CapabilityMatch(
            capability=capability,
            compatible=False,
            coverage=coverage,
            matched_objectives=matched_objectives,
            missing_inputs=(),
            postprocessors=(),
            runtime_available=capability.runtime_available,
            reasons=(reason,),
        )

    @staticmethod
    def _objective_properties(
        requirement: MaterialRequirementSpec,
    ) -> frozenset[str]:
        return frozenset(
            objective.property
            for objective in requirement.objectives
            if objective.property
            not in requirement.unsupported_requirements
        )

    @staticmethod
    def _select_objective_set(
        required: frozenset[str],
        available_sets: Sequence[frozenset[str]],
    ) -> Optional[frozenset[str]]:
        covering = [
            objective_set
            for objective_set in available_sets
            if required.issubset(objective_set)
        ]
        if not covering:
            return None
        return min(
            covering,
            key=lambda objective_set: (
                len(objective_set - required),
                len(objective_set),
                tuple(sorted(objective_set)),
            ),
        )

    @staticmethod
    def _has_matchable_requirement(
        requirement: MaterialRequirementSpec,
    ) -> bool:
        return bool(
            requirement.objectives
            or requirement.composition.chemical_system
            or requirement.composition.exact_formula
            or requirement.composition.required_elements
            or requirement.composition.allowed_elements
            or requirement.composition.excluded_elements
            or requirement.structure.space_group is not None
            or requirement.structure.crystal_system
        )

    def _match_priority(
        self,
        match: CapabilityMatch,
    ) -> tuple[int, int, int, int, int, int]:
        required_count = len(match.matched_objectives)
        joint_priority = 0 if required_count > 1 else 1
        missing_input_priority = 0 if not match.missing_inputs else 1
        coverage_priority = {
            "full": 0,
            "partial": 1,
            "incompatible": 2,
        }[match.coverage]
        postprocessor_priority = len(match.postprocessors)
        runtime_priority = {
            True: 0,
            None: 1,
            False: 2,
        }[match.runtime_available]
        return (
            joint_priority,
            missing_input_priority,
            coverage_priority,
            postprocessor_priority,
            runtime_priority,
            self._spec_order[match.model_id],
        )


_registry: Optional[CapabilityRegistry] = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry
