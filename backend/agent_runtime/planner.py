"""Capability-driven plan synthesis for the reasoning agent."""

from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence

from agent_runtime.memory import InMemoryAgentMemoryStore
from agent_runtime.tool_registry import (
    OBJECTIVE_HINTS,
    ParameterSuggestion,
    ToolDefinition,
    ToolRegistry,
)
from agent_workflow.schemas import (
    ExecutionPlan,
    MaterialRequirementSpec,
    ObjectiveSpec,
    PlanStep,
)


class AgentPlanner:
    """Create plans from tool contracts instead of model-specific branches."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        memory_store: Optional[InMemoryAgentMemoryStore] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.memory_store = memory_store

    def build_plan(
        self,
        *,
        session_id: str,
        message: str,
        arguments: dict[str, Any],
        previous_plan: Optional[ExecutionPlan] = None,
        reasoning_trace: Optional[list[dict[str, Any]]] = None,
        reflection: Optional[str] = None,
    ) -> ExecutionPlan:
        task_type = str(
            arguments.get("task_type")
            or (
                previous_plan.request_spec.task_type
                if previous_plan
                else "science_chat"
            )
        )
        if task_type != "material_generation":
            return self._build_material_tool_plan(
                session_id=session_id,
                message=message,
                arguments=arguments,
                task_type=task_type,
                previous_plan=previous_plan,
                reasoning_trace=reasoning_trace or [],
                reflection=reflection,
            )
        return self._build_generation_plan(
            session_id=session_id,
            message=message,
            arguments=arguments,
            previous_plan=previous_plan,
            reasoning_trace=reasoning_trace or [],
            reflection=reflection,
        )

    def arguments_from_plan(
        self,
        plan: ExecutionPlan,
    ) -> dict[str, Any]:
        request = plan.request_spec
        return {
            "task_type": request.task_type,
            "chemical_system": request.composition.chemical_system,
            "required_elements": list(request.composition.required_elements),
            "allowed_elements": list(request.composition.allowed_elements),
            "excluded_elements": list(request.composition.excluded_elements),
            "exact_formula": request.composition.exact_formula,
            "space_group": request.structure.space_group,
            "crystal_system": request.structure.crystal_system,
            "candidate_count": request.candidate_count,
            "exploration_mode": request.exploration_mode,
            "model_preferences": list(request.model_preferences),
            "objectives": [
                objective.model_dump(mode="json")
                for objective in request.objectives
            ],
            "input_material": (
                request.input_material.model_dump(mode="json")
                if request.input_material
                else None
            ),
        }

    def _build_generation_plan(
        self,
        *,
        session_id: str,
        message: str,
        arguments: dict[str, Any],
        previous_plan: Optional[ExecutionPlan],
        reasoning_trace: list[dict[str, Any]],
        reflection: Optional[str],
    ) -> ExecutionPlan:
        memory = (
            self.memory_store.get(session_id)
            if self.memory_store
            else None
        )
        chemical_system = (
            arguments.get("chemical_system")
            or arguments.get("composition", {}).get("chemical_system")
            or (memory.current_research_system if memory else None)
        )
        required_elements = list(arguments.get("required_elements") or [])
        allowed_elements = list(arguments.get("allowed_elements") or [])
        excluded_elements = list(arguments.get("excluded_elements") or [])
        if chemical_system and not allowed_elements:
            allowed_elements = [
                element
                for element in str(chemical_system).split("-")
                if element
            ]

        objectives = self._normalize_objectives(
            arguments.get("objectives") or []
        )
        request = MaterialRequirementSpec(
            task_type="material_generation",
            composition={
                "chemical_system": chemical_system,
                "required_elements": required_elements,
                "allowed_elements": allowed_elements,
                "excluded_elements": excluded_elements,
                "exact_formula": arguments.get("exact_formula"),
            },
            structure={
                "space_group": arguments.get("space_group"),
                "crystal_system": arguments.get("crystal_system"),
            },
            objectives=objectives,
            candidate_count=arguments.get("candidate_count"),
            exploration_mode=arguments.get(
                "exploration_mode",
                "single_model",
            ),
            model_preferences=list(
                arguments.get("model_preferences") or []
            ),
            application=arguments.get("application"),
        )

        selected_tools, selection_reasons = self._select_generation_tools(
            request,
            requested_properties=[
                objective.property for objective in objectives
            ],
        )
        planning_decisions: list[dict[str, Any]] = []
        assumptions: list[str] = []
        ask_steps: list[PlanStep] = []
        generation_steps: list[PlanStep] = []
        evaluation_steps: list[PlanStep] = []
        effective_values: dict[str, float] = {}
        parameter_sources: dict[str, str] = {}
        missing_required: list[str] = []

        preferred_tool = selected_tools[0] if selected_tools else None
        for objective in objectives:
            decision, suggestion = self._resolve_objective(
                objective,
                preferred_tool,
            )
            if decision is not None:
                effective_values[objective.property] = float(decision["value"])
                parameter_sources[objective.property] = str(
                    decision["source"]
                )
                planning_decisions.append(decision)
                if decision["source"] == "agent_suggestion":
                    ask_steps.append(
                        self._ask_step(
                            objective=objective,
                            suggestion=suggestion,
                        )
                    )
            else:
                missing_required.append(objective.property)
                ask_steps.append(
                    self._ask_step(
                        objective=objective,
                        suggestion=suggestion,
                    )
                )

        if selected_tools:
            primary = selected_tools[0]
            missing_required.extend(
                self._missing_tool_inputs(primary, request)
            )
            ask_steps.extend(
                self._required_input_ask_step(name)
                for name in dict.fromkeys(
                    self._missing_tool_inputs(primary, request)
                )
            )
            primary_conditions, condition_sources = self._conditions_for_tool(
                primary,
                request,
                effective_values,
            )
            candidate_decision = self._candidate_decision(request)
            planning_decisions.append(candidate_decision)
            generation_step = self._generate_step(
                tool=primary,
                conditions=primary_conditions,
                candidate_count=int(candidate_decision["value"]),
                parameter_sources={
                    **condition_sources,
                    "candidate_count": str(candidate_decision["source"]),
                },
            )
            generation_steps.append(generation_step)
            planning_decisions.append(
                self._tool_decision(
                    primary,
                    explicit=primary.name in request.model_preferences,
                    memory=memory,
                )
            )

            for extra_tool in selected_tools[1:]:
                covered = set(
                    primary.objective_properties
                ).intersection(extra_tool.objective_properties)
                uncovered = [
                    objective
                    for objective in objectives
                    if objective.property in extra_tool.objective_properties
                    and objective.property not in covered
                ]
                for objective in uncovered:
                    evaluation_steps.append(
                        self._evaluate_step(
                            objective=objective,
                            tool=extra_tool,
                            depends_on=[generation_step.id],
                        )
                    )
                    planning_decisions.append(
                        self._tool_decision(
                            extra_tool,
                            explicit=extra_tool.name
                            in request.model_preferences,
                            memory=memory,
                            role="evaluation",
                        )
                    )

        if not selected_tools:
            if not objectives:
                ask_steps.append(
                    self._ask_step(
                        objective=None,
                        suggestion=None,
                    )
                )
                selection_reasons.append("no_matching_generation_tool")
            else:
                selection_reasons.append("no_matching_generation_tool")

        rank_steps: list[PlanStep] = []
        if (
            generation_steps
            and (evaluation_steps or len(objectives) > 1)
        ):
            rank_dependencies = [
                step.id
                for step in [*generation_steps, *evaluation_steps]
            ]
            rank_steps.append(
                self._rank_step(
                    objectives=objectives,
                    depends_on=rank_dependencies,
                )
            )

        runtime_unavailable = [
            tool.name
            for tool in selected_tools
            if tool.runtime_availability is not True
        ]
        if runtime_unavailable and generation_steps:
            capability_status = "unavailable"
            selection_reasons.extend(
                f"{name}_runtime_unavailable"
                for name in runtime_unavailable
            )
        elif missing_required and generation_steps:
            capability_status = "clarification"
            selection_reasons.extend(missing_required)
        elif generation_steps:
            capability_status = "ready"
        else:
            capability_status = "clarification"

        steps = [
            *ask_steps,
            *generation_steps,
            *evaluation_steps,
            *rank_steps,
        ]
        summary = self._generation_summary(
            primary_tool=(
                selected_tools[0] if selected_tools else None
            ),
            evaluation_tools=selected_tools[1:],
            objectives=objectives,
            candidate_count=request.candidate_count,
            has_evaluation=bool(evaluation_steps),
            has_rank=bool(rank_steps),
        )
        assumptions.extend(
            [
                "目标性质用于工具条件或计划中的评估步骤，不代表已完成 DFT 验证。",
                "没有联合工具时，Agent 会生成主候选并保留后续评估、排序步骤。",
            ]
        )
        if evaluation_steps:
            assumptions.append(
                "若候选缺少目标性质字段，评估步骤应返回未评估观察，不得伪造数值。"
            )

        return self._new_plan(
            session_id=session_id,
            message=message,
            previous_plan=previous_plan,
            request=request,
            capability_status=capability_status,
            decision_reasons=selection_reasons,
            candidate_models=[
                tool.model_id or tool.name for tool in selected_tools
            ],
            planning_decisions=planning_decisions,
            summary=summary,
            assumptions=assumptions,
            questions=[
                step.question or step.description
                for step in ask_steps
                if capability_status != "ready"
            ],
            steps=steps,
            reasoning_trace=reasoning_trace,
            reflection=reflection,
        )

    def _build_material_tool_plan(
        self,
        *,
        session_id: str,
        message: str,
        arguments: dict[str, Any],
        task_type: str,
        previous_plan: Optional[ExecutionPlan],
        reasoning_trace: list[dict[str, Any]],
        reflection: Optional[str],
    ) -> ExecutionPlan:
        input_material = arguments.get("input_material") or {}
        formula = (
            arguments.get("formula")
            or input_material.get("formula")
        )
        substitutions = (
            arguments.get("substitutions")
            or input_material.get("substitutions")
            or {}
        )
        steps: list[PlanStep] = []
        questions: list[str] = []
        capability_status = "ready"
        reasons: list[str] = []

        if task_type == "material_lookup":
            if formula:
                steps.append(
                    self._tool_step(
                        kind="material_lookup",
                        title="查询材料结构",
                        description=f"查询 {formula} 的晶体结构数据。",
                        tool_name="material_search",
                        inputs={"formula": formula},
                    )
                )
            else:
                steps.append(self._ask_step(objective=None, suggestion=None))
                questions.append("请提供要查询的化学式。")
                capability_status = "clarification"
                reasons.append("formula")
        elif task_type == "element_substitution":
            if formula and substitutions:
                steps.append(
                    self._tool_step(
                        kind="element_substitution",
                        title="执行元素替换",
                        description="使用现有结构工具替换指定元素。",
                        tool_name="element_substitution",
                        inputs={
                            "formula": formula,
                            "substitutions": substitutions,
                        },
                    )
                )
            else:
                steps.append(self._ask_step(objective=None, suggestion=None))
                questions.append("请提供待替换材料和元素替换规则。")
                capability_status = "clarification"
                reasons.append("input_material")
        else:
            steps.append(
                self._tool_step(
                    kind="science_chat",
                    title="材料科学问答",
                    description="回答材料科学问题。",
                    tool_name="science_chat",
                    inputs={"message": message},
                )
            )

        request = MaterialRequirementSpec(
            task_type=task_type,  # type: ignore[arg-type]
            input_material=(
                {
                    "formula": formula,
                    "cif": input_material.get("cif"),
                    "material_id": input_material.get("material_id"),
                    "substitutions": substitutions,
                }
                if formula or input_material
                else None
            ),
        )
        return self._new_plan(
            session_id=session_id,
            message=message,
            previous_plan=previous_plan,
            request=request,
            capability_status=capability_status,
            decision_reasons=reasons,
            candidate_models=[],
            planning_decisions=[],
            summary=f"执行 {task_type} 工具链。",
            assumptions=[],
            questions=questions,
            steps=steps,
            reasoning_trace=reasoning_trace,
            reflection=reflection,
        )

    def _normalize_objectives(
        self,
        values: Sequence[Any],
    ) -> list[ObjectiveSpec]:
        objectives: list[ObjectiveSpec] = []
        seen: set[str] = set()
        for value in values:
            data = (
                value.model_dump(mode="python")
                if hasattr(value, "model_dump")
                else dict(value)
            )
            raw_property = str(data.get("property") or "")
            property_name = (
                self.tool_registry.normalize_property(raw_property)
                or raw_property
            )
            if not property_name or property_name in seen:
                continue
            hint = OBJECTIVE_HINTS.get(property_name)
            objectives.append(
                ObjectiveSpec(
                    property=property_name,
                    operator=data.get("operator")
                    or (hint.operator if hint else ">="),
                    target=data.get("target"),
                    unit=data.get("unit") or (hint.unit if hint else None),
                    semantic_goal=data.get("semantic_goal"),
                    constraint_type=data.get("constraint_type", "soft"),
                    priority=data.get("priority"),
                )
            )
            seen.add(property_name)
        return objectives

    def _select_generation_tools(
        self,
        request: MaterialRequirementSpec,
        *,
        requested_properties: Sequence[str],
    ) -> tuple[list[ToolDefinition], list[str]]:
        tools = self.tool_registry.generation_tools()
        if request.model_preferences:
            preferred = set(request.model_preferences)
            tools = [tool for tool in tools if tool.name in preferred]
            if not tools:
                return [], ["explicit_tool_not_registered"]

        requested = set(requested_properties)
        candidates = [
            tool
            for tool in tools
            if not self._missing_tool_inputs(tool, request)
        ]
        if not candidates:
            candidates = tools

        selected: list[ToolDefinition] = []
        reasons: list[str] = []
        remaining = set(requested)

        if not requested:
            if request.composition.chemical_system:
                candidates = [
                    tool
                    for tool in candidates
                    if "chemical_system" in tool.input_schema
                    and not tool.objective_properties
                ] or candidates
            else:
                candidates = [
                    tool
                    for tool in candidates
                    if not tool.objective_properties
                    and not tool.required_inputs
                ]
            if candidates:
                return [self._best_tool(candidates, requested)], reasons
            return [], ["no_generation_tool_for_request"]

        while remaining:
            ranked = [
                tool
                for tool in candidates
                if tool not in selected
                and remaining.intersection(tool.objective_properties)
            ]
            if not ranked:
                reasons.append(
                    "no_joint_tool_for:"
                    + ",".join(sorted(remaining))
                )
                break
            selected_tool = self._best_tool(ranked, remaining)
            selected.append(selected_tool)
            remaining.difference_update(selected_tool.objective_properties)

        if len(selected) > 1:
            reasons.append("no_joint_model")
        return selected, reasons

    def _best_tool(
        self,
        tools: Sequence[ToolDefinition],
        requested: set[str],
    ) -> ToolDefinition:
        return sorted(
            tools,
            key=lambda tool: (
                -len(requested.intersection(tool.objective_properties)),
                len(set(tool.objective_properties) - requested),
                -len(tool.required_inputs),
                tool.runtime_availability is not True,
                tool.name,
            ),
        )[0]

    @staticmethod
    def _missing_tool_inputs(
        tool: ToolDefinition,
        request: MaterialRequirementSpec,
    ) -> list[str]:
        missing: list[str] = []
        for input_name in tool.required_inputs:
            if input_name == "chemical_system":
                if not request.composition.chemical_system:
                    missing.append(input_name)
            elif input_name == "space_group":
                if request.structure.space_group is None:
                    missing.append(input_name)
            else:
                missing.append(input_name)
        return missing

    def _resolve_objective(
        self,
        objective: ObjectiveSpec,
        preferred_tool: Optional[ToolDefinition],
    ) -> tuple[Optional[dict[str, Any]], Optional[ParameterSuggestion]]:
        if objective.target is not None:
            return (
                {
                    "parameter": objective.property,
                    "value": objective.target,
                    "source": "user",
                    "rationale": "目标数值由用户明确给出。",
                },
                None,
            )

        suggestion = self.tool_registry.parameter_suggestion(
            objective.property,
            semantic_goal=objective.semantic_goal,
            preferred_tool=preferred_tool.name if preferred_tool else None,
        )
        if suggestion is None or suggestion.value is None:
            return None, suggestion
        return (
            {
                "parameter": objective.property,
                "value": suggestion.value,
                "source": "agent_suggestion",
                "rationale": suggestion.rationale,
            },
            suggestion,
        )

    def _conditions_for_tool(
        self,
        tool: ToolDefinition,
        request: MaterialRequirementSpec,
        effective_values: dict[str, float],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        conditions: dict[str, Any] = {}
        sources: dict[str, str] = {}
        for name in tool.required_inputs:
            if name == "chemical_system":
                value = request.composition.chemical_system
            elif name == "space_group":
                value = request.structure.space_group
            else:
                value = None
            if value is not None:
                conditions[name] = value
                sources[name] = (
                    "user"
                    if name == "chemical_system"
                    and request.composition.chemical_system
                    else "derived"
                )

        for name in tool.objective_properties:
            if name not in effective_values:
                continue
            conditions[name] = effective_values[name]
            source = "user"
            for objective in request.objectives:
                if objective.property == name:
                    source = (
                        "user"
                        if objective.target is not None
                        else "agent_suggestion"
                    )
                    break
            sources[name] = source
        return conditions, sources

    @staticmethod
    def _candidate_decision(
        request: MaterialRequirementSpec,
    ) -> dict[str, Any]:
        if request.candidate_count is not None:
            return {
                "parameter": "candidate_count",
                "value": request.candidate_count,
                "source": "user",
                "rationale": "候选数量由用户明确指定。",
            }
        return {
            "parameter": "candidate_count",
            "value": 8,
            "source": "planning_policy",
            "rationale": "未指定候选数量，使用 Agent 默认值 8。",
        }

    @staticmethod
    def _tool_decision(
        tool: ToolDefinition,
        *,
        explicit: bool,
        memory: Any,
        role: str = "generation",
    ) -> dict[str, Any]:
        historical = bool(
            memory
            and any(
                item.tool_name == tool.name
                for item in memory.model_history
            )
        )
        source = (
            "user"
            if explicit
            else ("memory" if historical else "derived")
        )
        return {
            "parameter": "model_id",
            "value": tool.model_id or tool.name,
            "source": source,
            "role": role,
            "rationale": (
                "工具由用户显式指定。"
                if explicit
                else (
                    "沿用 Agent Memory 中的历史工具选择。"
                    if historical
                    else "工具由 ToolRegistry 能力覆盖和运行可用性动态选择。"
                )
            ),
        }

    @staticmethod
    def _ask_step(
        *,
        objective: Optional[ObjectiveSpec],
        suggestion: Optional[ParameterSuggestion],
    ) -> PlanStep:
        if objective is None:
            question = "请补充要优化的材料性质或目标范围。"
            title = "确认材料目标"
            description = question
            inputs: dict[str, Any] = {}
        else:
            title = f"确认 {objective.property}"
            suggestion_text = (
                suggestion.display()
                if suggestion and suggestion.value is not None
                else "待补充"
            )
            question = (
                f"{objective.property} 使用建议值 {suggestion_text}，"
                "可以确认或修改。"
            )
            description = f"建议：{suggestion_text}"
            inputs = {
                "parameter": objective.property,
                "operator": (
                    suggestion.operator
                    if suggestion
                    else objective.operator
                ),
                "target": suggestion.value if suggestion else None,
                "unit": (
                    suggestion.unit
                    if suggestion
                    else objective.unit
                ),
            }
        return PlanStep(
            id=f"ask-{uuid.uuid4().hex[:8]}",
            kind="ask",
            title=title,
            description=description,
            inputs=inputs,
            question=question,
            suggestion=(
                suggestion.model_dump(mode="json")
                if suggestion
                else None
            ),
            required=False,
            on_failure="continue",
        )

    @staticmethod
    def _required_input_ask_step(input_name: str) -> PlanStep:
        labels = {
            "chemical_system": "元素体系",
            "space_group": "空间群",
        }
        label = labels.get(input_name, input_name)
        return PlanStep(
            id=f"ask-{uuid.uuid4().hex[:8]}",
            kind="ask",
            title=f"确认{label}",
            description=f"请提供 {input_name} 后再执行生成步骤。",
            question=f"请提供 {input_name}。",
            inputs={"parameter": input_name},
            required=True,
            on_failure="abort",
        )

    @staticmethod
    def _generate_step(
        *,
        tool: ToolDefinition,
        conditions: dict[str, Any],
        candidate_count: int,
        parameter_sources: dict[str, str],
    ) -> PlanStep:
        condition_text = "，".join(
            f"{name}={value}" for name, value in conditions.items()
        )
        return PlanStep(
            id=f"generate-{uuid.uuid4().hex[:8]}",
            kind="generate",
            title=f"生成候选（{tool.name}）",
            description=(
                f"通过 {tool.name} 生成 {candidate_count} 个候选；"
                f"条件：{condition_text or '无条件'}。"
            ),
            model_id=tool.model_id or tool.name,
            conditions=conditions,
            parameter_sources=parameter_sources,
            num_candidates=candidate_count,
            guidance_scale=2.0,
            required=True,
            on_failure="abort",
            max_retries=1,
            retry_delay_seconds=1.0,
            produces_candidates=True,
        )

    @staticmethod
    def _evaluate_step(
        *,
        objective: ObjectiveSpec,
        tool: ToolDefinition,
        depends_on: list[str],
    ) -> PlanStep:
        return PlanStep(
            id=f"evaluate-{uuid.uuid4().hex[:8]}",
            kind="evaluate",
            title=f"评估 {objective.property}",
            description=(
                f"使用 {tool.name} 对应的评估能力检查 "
                f"{objective.property}；当前没有联合生成模型。"
            ),
            inputs={
                "property": objective.property,
                "operator": objective.operator,
                "target": objective.target,
                "unit": objective.unit,
                "evaluation_tool": tool.name,
            },
            depends_on=depends_on,
            requires_candidates=True,
            required=False,
            on_failure="continue",
        )

    @staticmethod
    def _rank_step(
        *,
        objectives: Sequence[ObjectiveSpec],
        depends_on: list[str],
    ) -> PlanStep:
        return PlanStep(
            id=f"rank-{uuid.uuid4().hex[:8]}",
            kind="rank",
            title="排序候选",
            description="按已确认目标汇总并排序候选。",
            inputs={
                "objectives": [
                    objective.model_dump(mode="json")
                    for objective in objectives
                ]
            },
            depends_on=depends_on,
            requires_candidates=True,
            required=True,
            on_failure="abort",
        )

    @staticmethod
    def _tool_step(
        *,
        kind: str,
        title: str,
        description: str,
        tool_name: str,
        inputs: dict[str, Any],
    ) -> PlanStep:
        return PlanStep(
            id=f"{kind}-{uuid.uuid4().hex[:8]}",
            kind=kind,  # type: ignore[arg-type]
            title=title,
            description=description,
            inputs={**inputs, "_tool": tool_name},
            required=True,
            on_failure="abort",
        )

    @staticmethod
    def _generation_summary(
        *,
        primary_tool: Optional[ToolDefinition],
        evaluation_tools: Sequence[ToolDefinition],
        objectives: Sequence[ObjectiveSpec],
        candidate_count: Optional[int],
        has_evaluation: bool,
        has_rank: bool,
    ) -> str:
        def labels_for(tool: Optional[ToolDefinition]) -> list[str]:
            if tool is None:
                return []
            properties = set(tool.objective_properties)
            return [
                {
                    "high_magnetic_density": "magnetic",
                    "higher_magnetic_density": "magnetic",
                    "strict_stable": "stable",
                    "relaxed_stable": "stable",
                    "low_supply_risk": "supply risk",
                }.get(
                    objective.semantic_goal or "",
                    objective.semantic_goal or objective.property,
                )
                for objective in objectives
                if objective.property in properties
            ]

        primary_labels = labels_for(primary_tool)
        if not primary_labels:
            primary_labels = [primary_tool.name if primary_tool else "candidate"]
        parts = [f"Generate {primary_labels[0]}"]
        for tool in evaluation_tools:
            labels = labels_for(tool)
            if labels:
                parts.append(f"Evaluate {labels[0]}")
        if has_evaluation and len(parts) == 1:
            parts.append("Evaluate objective")
        if has_rank:
            parts.append("Rank")
        count = candidate_count or 8
        return (
            " → ".join(parts)
            + f"；生成 {count} 个候选。"
        )

    @staticmethod
    def _new_plan(
        *,
        session_id: str,
        message: str,
        previous_plan: Optional[ExecutionPlan],
        request: MaterialRequirementSpec,
        capability_status: str,
        decision_reasons: list[str],
        candidate_models: list[str],
        planning_decisions: list[dict[str, Any]],
        summary: str,
        assumptions: list[str],
        questions: list[str],
        steps: list[PlanStep],
        reasoning_trace: list[dict[str, Any]],
        reflection: Optional[str],
    ) -> ExecutionPlan:
        return ExecutionPlan(
            plan_id=(
                previous_plan.plan_id
                if previous_plan
                else str(uuid.uuid4())
            ),
            session_id=session_id,
            revision=(previous_plan.revision + 1) if previous_plan else 1,
            original_message=(
                previous_plan.original_message
                if previous_plan
                else message
            ),
            summary=summary,
            assumptions=assumptions,
            questions=questions,
            capability_status=capability_status,  # type: ignore[arg-type]
            decision_reasons=list(dict.fromkeys(decision_reasons)),
            candidate_models=list(dict.fromkeys(candidate_models)),
            planning_decisions=planning_decisions,
            reasoning_trace=reasoning_trace,
            reflection=reflection,
            request_spec=request,
            steps=steps,
        )
