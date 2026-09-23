"""Registry of tools exposed to the reasoning agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field

from agent_workflow.capability_registry import (
    CapabilityRegistry,
    get_capability_registry,
)


@dataclass(frozen=True)
class ObjectiveHint:
    """Model-independent vocabulary and defaults for one objective."""

    property: str
    aliases: tuple[str, ...]
    unit: Optional[str]
    operator: str
    suggested_value: Optional[float]
    rationale: str


OBJECTIVE_HINTS: dict[str, ObjectiveHint] = {
    "dft_mag_density": ObjectiveHint(
        property="dft_mag_density",
        aliases=(
            "dft_mag_density",
            "磁密度",
            "磁化强度",
            "高磁",
            "高磁性",
            "magnetic density",
            "magnetization density",
        ),
        unit="Å^-3",
        operator=">=",
        suggested_value=0.2,
        rationale="“高磁”可先按系统建议的磁密度下限继续规划。",
    ),
    "hhi_score": ObjectiveHint(
        property="hhi_score",
        aliases=(
            "hhi_score",
            "hhi",
            "供应风险",
            "供应集中度",
            "supply risk",
            "supply concentration",
        ),
        unit=None,
        operator="<=",
        suggested_value=0.3,
        rationale="“低供应风险”可先按建议的 HHI 上限继续规划。",
    ),
    "energy_above_hull": ObjectiveHint(
        property="energy_above_hull",
        aliases=(
            "energy_above_hull",
            "energy above hull",
            "能量高于凸包",
            "凸包",
            "稳定性",
            "较稳定",
            "stable",
            "stability",
        ),
        unit="eV/atom",
        operator="<=",
        suggested_value=0.05,
        rationale="“较稳定”按建议阈值 energy_above_hull <= 0.05 eV/atom。",
    ),
    "dft_band_gap": ObjectiveHint(
        property="dft_band_gap",
        aliases=(
            "dft_band_gap",
            "带隙",
            "能带间隙",
            "band gap",
            "bandgap",
        ),
        unit="eV",
        operator="~=",
        suggested_value=None,
        rationale="带隙需要目标数值或由用户修订确认。",
    ),
    "ml_bulk_modulus": ObjectiveHint(
        property="ml_bulk_modulus",
        aliases=(
            "ml_bulk_modulus",
            "体积模量",
            "体模量",
            "bulk modulus",
        ),
        unit="GPa",
        operator=">=",
        suggested_value=None,
        rationale="体积模量目标需要用户确认。",
    ),
    "space_group": ObjectiveHint(
        property="space_group",
        aliases=("space_group", "空间群", "space group"),
        unit=None,
        operator="~=",
        suggested_value=None,
        rationale="空间群目标需要用户确认。",
    ),
}


SEMANTIC_SUGGESTIONS: dict[str, tuple[str, float]] = {
    "stable": ("<=", 0.05),
    "strict_stable": ("<=", 0.025),
    "relaxed_stable": ("<=", 0.1),
    "high_magnetic_density": (">=", 0.2),
    "higher_magnetic_density": (">=", 0.22),
    "low_supply_risk": ("<=", 0.3),
}


class ParameterSuggestion(BaseModel):
    """One suggested parameter value shown in an Ask plan step."""

    parameter: str
    operator: str = ">="
    value: Optional[float] = None
    unit: Optional[str] = None
    rationale: str
    semantic_goal: Optional[str] = None

    def display(self) -> str:
        if self.value is None:
            return self.parameter
        unit = f" {self.unit}" if self.unit else ""
        return f"{self.parameter} {self.operator} {self.value}{unit}"


class ToolDefinition(BaseModel):
    """LLM-visible contract for one executable or planning tool."""

    name: str
    capability: str
    description: str
    required_inputs: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)
    default_suggestions: dict[str, ParameterSuggestion] = Field(
        default_factory=dict
    )
    runtime_availability: Optional[bool] = None
    objective_properties: list[str] = Field(default_factory=list)
    model_id: Optional[str] = None
    kind: str = "tool"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)

    @property
    def runtime_available(self) -> Optional[bool]:
        """Compatibility alias used by callers that prefer an adjective form."""

        return self.runtime_availability

    def as_prompt_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ToolRegistry:
    """Expose capabilities, input contracts, defaults, and runtime state."""

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
    ):
        self.capability_registry = (
            capability_registry or get_capability_registry()
        )
        self._tools: dict[str, ToolDefinition] = {}
        self._install_planning_tools()
        self._install_material_tools()
        self._install_generation_tools()

    def _install_planning_tools(self) -> None:
        self._tools["plan_generation"] = ToolDefinition(
            name="plan_generation",
            capability="agent_planning",
            description=(
                "将推理得到的材料目标转换成可确认的 ExecutionPlan；"
                "缺省数值会形成 Ask 步骤，不会直接启动生成任务。"
            ),
            required_inputs=["objectives"],
            optional_inputs=["chemical_system", "candidate_count"],
            input_schema={
                "task_type": "material_generation",
                "objectives": "list[ObjectiveSpec]",
                "chemical_system": "string",
                "candidate_count": "integer",
            },
            outputs=["ExecutionPlan"],
            runtime_availability=True,
            kind="planning",
        )
        self._tools["revise_plan"] = ToolDefinition(
            name="revise_plan",
            capability="agent_planning",
            description=(
                "基于当前计划和 Agent Memory 生成新的计划 revision。"
            ),
            required_inputs=["previous_plan", "instruction"],
            optional_inputs=["objectives", "candidate_count"],
            input_schema={
                "previous_plan": "ExecutionPlan",
                "instruction": "string",
            },
            outputs=["ExecutionPlan"],
            runtime_availability=True,
            kind="planning",
        )

    def _install_material_tools(self) -> None:
        self._tools["material_search"] = ToolDefinition(
            name="material_search",
            capability="material_lookup",
            description="查询已知材料的晶体结构和基础性质。",
            required_inputs=["formula"],
            optional_inputs=["material_id"],
            runtime_availability=True,
            input_schema={"formula": "string"},
            outputs=["material_data"],
            kind="tool",
        )
        self._tools["element_substitution"] = ToolDefinition(
            name="element_substitution",
            capability="element_substitution",
            description="在已有结构上执行元素替换或掺杂。",
            required_inputs=["input_material", "substitutions"],
            optional_inputs=["formula", "cif"],
            runtime_availability=True,
            input_schema={
                "formula": "string",
                "cif": "string",
                "substitutions": "dict[string,string]",
            },
            outputs=["material_data"],
            kind="tool",
        )
        self._tools["science_chat"] = ToolDefinition(
            name="science_chat",
            capability="science_chat",
            description="回答材料科学概念、解释和讨论问题。",
            required_inputs=["message"],
            optional_inputs=["history"],
            runtime_availability=True,
            input_schema={"message": "string"},
            outputs=["message"],
            kind="tool",
        )

    def _install_generation_tools(self) -> None:
        for capability in self.capability_registry.all(
            include_runtime=True
        ):
            condition_names = list(capability.supported_conditions)
            required_inputs = list(capability.required_inputs)
            optional_inputs = [
                name
                for name in condition_names
                if name not in required_inputs
            ]
            suggestions = {
                name: suggestion
                for name in condition_names
                if (
                    suggestion := self._suggestion_for_condition(
                        name,
                        capability.objective_constraints.get(name, {}),
                    )
                )
                is not None
            }
            self._tools[capability.model_id] = ToolDefinition(
                name=capability.model_id,
                capability="material_generation",
                description=capability.display_name,
                required_inputs=required_inputs,
                optional_inputs=optional_inputs,
                default_suggestions=suggestions,
                runtime_availability=capability.runtime_available,
                objective_properties=list(
                    capability.supported_properties
                ),
                model_id=capability.model_id,
                kind="generation",
                input_schema={
                    name: {
                        "required": name in required_inputs,
                        "type": condition.get("type"),
                        "default": condition.get("default"),
                        "minimum": condition.get("minimum"),
                        "maximum": condition.get("maximum"),
                        "unit": condition.get("unit"),
                    }
                    for name, condition in (
                        capability.objective_constraints.items()
                    )
                },
                outputs=["candidate_batch"],
            )

    @staticmethod
    def _suggestion_for_condition(
        name: str,
        condition: dict[str, object],
    ) -> Optional[ParameterSuggestion]:
        hint = OBJECTIVE_HINTS.get(name)
        if hint is not None:
            value = hint.suggested_value
            if value is None and condition.get("default") is not None:
                value = float(condition["default"])
            return ParameterSuggestion(
                parameter=name,
                operator=hint.operator,
                value=value,
                unit=hint.unit or (
                    str(condition["unit"])
                    if condition.get("unit")
                    else None
                ),
                rationale=hint.rationale,
            )

        default = condition.get("default")
        if default is None:
            return None
        if condition.get("type") not in {"float", "int"}:
            return None
        return ParameterSuggestion(
            parameter=name,
            operator=">=",
            value=float(default),
            unit=(
                str(condition["unit"])
                if condition.get("unit")
                else None
            ),
            rationale=f"{name} 使用工具注册表中的默认建议值。",
        )

    def list_tools(
        self,
        *,
        capability: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> list[ToolDefinition]:
        return [
            tool
            for tool in self._tools.values()
            if (
                (capability is None or tool.capability == capability)
                and (kind is None or tool.kind == kind)
            )
        ]

    def generation_tools(self) -> list[ToolDefinition]:
        return self.list_tools(kind="generation")

    def list(self) -> list[ToolDefinition]:
        return self.list_tools()

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self.get(name)

    def require(self, name: str) -> ToolDefinition:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Unknown tool: {name}")
        return tool

    def normalize_property(self, value: str) -> Optional[str]:
        lowered = value.strip().lower()
        if lowered in OBJECTIVE_HINTS:
            return lowered
        for property_name, hint in OBJECTIVE_HINTS.items():
            if any(alias.lower() == lowered for alias in hint.aliases):
                return property_name
        return None

    def property_mentioned(self, text: str) -> list[str]:
        lowered = text.lower()
        return [
            property_name
            for property_name, hint in OBJECTIVE_HINTS.items()
            if any(alias.lower() in lowered for alias in hint.aliases)
        ]

    def parameter_suggestion(
        self,
        property_name: str,
        *,
        semantic_goal: Optional[str] = None,
        preferred_tool: Optional[str] = None,
    ) -> Optional[ParameterSuggestion]:
        if semantic_goal and semantic_goal in SEMANTIC_SUGGESTIONS:
            operator, value = SEMANTIC_SUGGESTIONS[semantic_goal]
            hint = OBJECTIVE_HINTS.get(property_name)
            return ParameterSuggestion(
                parameter=property_name,
                operator=operator,
                value=value,
                unit=hint.unit if hint else None,
                rationale=(
                    hint.rationale
                    if hint
                    else f"{property_name} 使用语义目标建议值。"
                ),
                semantic_goal=semantic_goal,
            )

        if preferred_tool:
            tool = self.get(preferred_tool)
            if tool and property_name in tool.default_suggestions:
                return tool.default_suggestions[property_name].model_copy(
                    update={"semantic_goal": semantic_goal}
                )

        for tool in self.generation_tools():
            if property_name in tool.default_suggestions:
                return tool.default_suggestions[property_name].model_copy(
                    update={"semantic_goal": semantic_goal}
                )
        return None

    def choose_tool(
        self,
        *,
        requested_name: Optional[str] = None,
        capability: Optional[str] = None,
        properties: Optional[list[str]] = None,
    ) -> ToolDefinition:
        if requested_name:
            return self.require(requested_name)

        requested = set(properties or [])
        candidates = self.generation_tools() if requested else []
        if capability:
            candidates = [
                tool
                for tool in self.list_tools()
                if tool.capability == capability
            ]

        if candidates:
            candidates.sort(
                key=lambda tool: (
                    -len(requested.intersection(tool.objective_properties)),
                    len(set(tool.objective_properties) - requested),
                    tool.runtime_availability is not True,
                    tool.name,
                )
            )
            return candidates[0]

        for tool in self.list_tools():
            if tool.capability == capability:
                return tool
        return self.require("science_chat")

    def prompt_description(self) -> str:
        lines = []
        for tool in self.list_tools():
            lines.append(
                f"- {tool.name} ({tool.capability}): {tool.description}; "
                f"required={tool.required_inputs}; "
                f"optional={tool.optional_inputs}; "
                f"runtime_available={tool.runtime_availability}"
            )
        return "\n".join(lines)
