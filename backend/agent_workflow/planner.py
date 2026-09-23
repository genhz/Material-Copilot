"""Create editable workflows from structured requirements and capabilities."""

from __future__ import annotations

import math
import uuid
from typing import Optional, Sequence

from agent_workflow.capability_registry import (
    CapabilityMatch,
    CapabilityRegistry,
    get_capability_registry,
)
from agent_workflow.schemas import (
    CapabilityPlanningStatus,
    ExecutionPlan,
    MaterialRequestSpec,
    MaterialRequirementSpec,
    PlanStep,
)
from agent_workflow.semantics import RARE_EARTH_ELEMENTS


MAX_CANDIDATES_PER_STEP = 16


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class WorkflowPlanner:
    """Turn a validated requirement into a plan without executing it."""

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
    ):
        self.capability_registry = (
            capability_registry or get_capability_registry()
        )

    def plan(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str] = None,
        previous_plan: Optional[ExecutionPlan] = None,
    ) -> ExecutionPlan:
        """Plan only from the structured requirement and registry facts."""

        if requirement.task_type in {
            "material_lookup",
            "element_substitution",
            "science_chat",
        }:
            return self._plan_tool_requirement(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
            )

        if requirement.exploration_mode == "multi_model":
            return self._plan_multi_model_requirement(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
            )

        normalized, normalization_errors = self._normalize_requirement(
            requirement
        )
        if normalization_errors:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unsupported",
                reasons=normalization_errors,
                candidate_models=[],
            )

        decision = self.capability_registry.resolve(normalized)
        candidate_models = [match.model_id for match in decision.matches]

        if decision.status == "clarification":
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="clarification",
                reasons=list(decision.reasons),
                candidate_models=candidate_models,
            )
        if decision.status != "compatible" or not decision.matches:
            reasons = list(decision.reasons)
            if decision.matches:
                reasons.append("no_complete_capability")
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unsupported",
                reasons=_unique(reasons),
                candidate_models=candidate_models,
            )

        selected = decision.matches[0]
        if selected.runtime_available is not True:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unavailable",
                reasons=[f"{selected.model_id}_runtime_unavailable"],
                candidate_models=candidate_models,
            )

        conditions, missing_conditions, condition_errors = (
            self._build_conditions(normalized, selected)
        )
        if condition_errors:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unsupported",
                reasons=condition_errors,
                candidate_models=candidate_models,
            )
        if missing_conditions:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="clarification",
                reasons=missing_conditions,
                candidate_models=candidate_models,
            )

        return self._build_ready_plan(
            session_id=session_id,
            requirement=normalized,
            original_message=original_message,
            previous_plan=previous_plan,
            selected=selected,
            conditions=conditions,
            candidate_models=candidate_models,
        )

    def _plan_multi_model_requirement(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
    ) -> ExecutionPlan:
        normalized, normalization_errors = self._normalize_requirement(
            requirement
        )
        if normalization_errors:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unsupported",
                reasons=normalization_errors,
                candidate_models=[],
            )

        if normalized.model_preferences:
            matches = []
            for model_id in normalized.model_preferences:
                match = self.capability_registry.match_model(
                    model_id,
                    normalized,
                )
                if match is None:
                    return self._build_decision_plan(
                        session_id=session_id,
                        requirement=normalized,
                        original_message=original_message,
                        previous_plan=previous_plan,
                        capability_status="unsupported",
                        reasons=[f"{model_id}_not_registered"],
                        candidate_models=[],
                    )
                if not match.compatible:
                    return self._build_decision_plan(
                        session_id=session_id,
                        requirement=normalized,
                        original_message=original_message,
                        previous_plan=previous_plan,
                        capability_status="unsupported",
                        reasons=[
                            f"{model_id}_incompatible",
                            *match.reasons,
                        ],
                        candidate_models=[],
                    )
                if match.missing_inputs:
                    return self._build_decision_plan(
                        session_id=session_id,
                        requirement=normalized,
                        original_message=original_message,
                        previous_plan=previous_plan,
                        capability_status="clarification",
                        reasons=list(match.missing_inputs),
                        candidate_models=[model_id],
                    )
                matches.append(match)
        else:
            matches = [
                match
                for match in self.capability_registry.match_requirement(
                    normalized
                )
                if not match.missing_inputs
            ]

        if not matches:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unsupported",
                reasons=["no_compatible_models"],
                candidate_models=[],
            )

        unavailable = [
            match.model_id
            for match in matches
            if match.runtime_available is not True
        ]
        if unavailable:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=normalized,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unavailable",
                reasons=[
                    f"{model_id}_runtime_unavailable"
                    for model_id in unavailable
                ],
                candidate_models=[match.model_id for match in matches],
            )

        steps: list[PlanStep] = []
        candidate_count = normalized.candidate_count or 2
        seed = (
            previous_plan.steps[0].seed
            if previous_plan and previous_plan.steps
            else None
        )
        for match in matches:
            conditions, missing_conditions, condition_errors = (
                self._build_conditions(normalized, match)
            )
            if condition_errors:
                return self._build_decision_plan(
                    session_id=session_id,
                    requirement=normalized,
                    original_message=original_message,
                    previous_plan=previous_plan,
                    capability_status="unsupported",
                    reasons=condition_errors,
                    candidate_models=[item.model_id for item in matches],
                )
            if missing_conditions:
                return self._build_decision_plan(
                    session_id=session_id,
                    requirement=normalized,
                    original_message=original_message,
                    previous_plan=previous_plan,
                    capability_status="clarification",
                    reasons=missing_conditions,
                    candidate_models=[item.model_id for item in matches],
                )
            for count in self._split_candidate_count(candidate_count):
                steps.append(
                    self._generate_step(
                        model_id=match.model_id,
                        model_label=match.capability.display_name,
                        conditions=conditions,
                        num_candidates=count,
                        guidance_scale=(
                            match.capability.default_guidance_scale
                        ),
                        seed=seed,
                    )
                )

        model_ids = [match.model_id for match in matches]
        assumptions = [
            "目标性质用于生成条件引导，不代表生成后已完成性质预测或验证。",
            "多模型探索会为每个兼容模型创建独立 Generation Job。",
            "candidate_count 按每个选中模型分别应用。",
        ]
        return self._new_plan(
            session_id=session_id,
            requirement=normalized,
            original_message=original_message,
            previous_plan=previous_plan,
            capability_status="ready",
            decision_reasons=[],
            candidate_models=model_ids,
            summary=(
                "多模型探索："
                + "、".join(model_ids)
                + f"；每个模型生成 {candidate_count} 个候选。"
            ),
            assumptions=assumptions,
            questions=[],
            steps=steps,
        )

    def _plan_tool_requirement(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
    ) -> ExecutionPlan:
        tool = self.capability_registry.get_tool_capability(
            requirement.task_type
        )
        if tool is None:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="unsupported",
                reasons=[f"{requirement.task_type}_capability_not_registered"],
                candidate_models=[],
            )

        if requirement.task_type == "material_lookup":
            return self._plan_material_lookup(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
                tool_name=tool.name,
            )
        if requirement.task_type == "element_substitution":
            return self._plan_element_substitution(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
                tool_name=tool.name,
            )
        return self._plan_science_chat(
            session_id=session_id,
            requirement=requirement,
            original_message=original_message,
            previous_plan=previous_plan,
            tool_name=tool.name,
        )

    def _plan_material_lookup(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
        tool_name: str,
    ) -> ExecutionPlan:
        material = requirement.input_material
        inputs = {
            key: value
            for key, value in {
                "formula": material.formula if material else None,
                "cif": material.cif if material else None,
                "material_id": material.material_id if material else None,
            }.items()
            if value
        }
        if not inputs:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="clarification",
                reasons=["input_material"],
                candidate_models=[],
            )
        step = self._tool_step(
            kind="material_lookup",
            title="查询材料结构",
            description="查询指定材料的结构与性质数据。",
            tool_name=tool_name,
            inputs=inputs,
        )
        return self._new_plan(
            session_id=session_id,
            requirement=requirement,
            original_message=original_message,
            previous_plan=previous_plan,
            capability_status="ready",
            decision_reasons=[],
            candidate_models=[],
            summary="查询指定材料的晶体结构数据。",
            assumptions=["查询结果来自现有 Materials Project 工具。"],
            questions=[],
            steps=[step],
        )

    def _plan_element_substitution(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
        tool_name: str,
    ) -> ExecutionPlan:
        material = requirement.input_material
        substitutions = material.substitutions if material else {}
        if not substitutions:
            return self._build_decision_plan(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="clarification",
                reasons=["element_substitution_rule"],
                candidate_models=[],
            )
        if material is None or not any(
            (material.cif, material.formula, material.material_id)
        ):
            return self._build_decision_plan(
                session_id=session_id,
                requirement=requirement,
                original_message=original_message,
                previous_plan=previous_plan,
                capability_status="clarification",
                reasons=["input_material"],
                candidate_models=[],
            )

        steps: list[PlanStep] = []
        lookup_step_id: Optional[str] = None
        if not material.cif:
            lookup_inputs = {
                key: value
                for key, value in {
                    "formula": material.formula,
                    "material_id": material.material_id,
                }.items()
                if value
            }
            lookup_step = self._tool_step(
                kind="material_lookup",
                title="获取待替换材料结构",
                description="查询原始材料并取得 CIF 结构。",
                tool_name="material_search",
                inputs=lookup_inputs,
            )
            steps.append(lookup_step)
            lookup_step_id = lookup_step.id

        substitution_inputs = {
            "formula": material.formula,
            "cif": material.cif,
            "substitutions": substitutions,
        }
        substitution_step = self._tool_step(
            kind="element_substitution",
            title="执行元素替换",
            description="使用现有 CIF 处理工具替换指定元素。",
            tool_name=tool_name,
            inputs=substitution_inputs,
            depends_on=[lookup_step_id] if lookup_step_id else [],
        )
        steps.append(substitution_step)
        return self._new_plan(
            session_id=session_id,
            requirement=requirement,
            original_message=original_message,
            previous_plan=previous_plan,
            capability_status="ready",
            decision_reasons=[],
            candidate_models=[],
            summary=(
                "查询原始结构后执行元素替换。"
                if lookup_step_id
                else "执行元素替换。"
            ),
            assumptions=[
                "元素替换保持原有晶格框架，不执行结构弛豫或 DFT 验证。"
            ],
            questions=[],
            steps=steps,
        )

    def _plan_science_chat(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
        tool_name: str,
    ) -> ExecutionPlan:
        message = original_message or self._original_message(requirement)
        step = self._tool_step(
            kind="science_chat",
            title="材料科学问答",
            description="使用现有材料科学对话工具回答问题。",
            tool_name=tool_name,
            inputs={"message": message},
        )
        return self._new_plan(
            session_id=session_id,
            requirement=requirement,
            original_message=message,
            previous_plan=previous_plan,
            capability_status="ready",
            decision_reasons=[],
            candidate_models=[],
            summary="回答材料科学问题。",
            assumptions=[],
            questions=[],
            steps=[step],
        )

    async def propose(
        self,
        *,
        session_id: str,
        message: str,
        history: Optional[Sequence[dict]] = None,
        previous_plan: Optional[ExecutionPlan] = None,
        revision_instruction: Optional[str] = None,
    ) -> Optional[ExecutionPlan]:
        """Compatibility entry for callers that still provide raw text."""

        from agent_workflow.semantics import extract_semantics
        from intent.classifier import _heuristic_decision

        combined_text = message
        if revision_instruction:
            combined_text = f"{message}\n用户修改要求：{revision_instruction}"
        decision = _heuristic_decision(combined_text)
        if decision and decision.intent != "material_generation":
            return None
        if decision is None and not any(
            cue in combined_text
            for cue in ("生成", "设计", "探索", "候选", "新材料", "新型材料")
        ):
            return None

        requirement = extract_semantics(combined_text)
        return self.plan(
            session_id=session_id,
            requirement=requirement,
            original_message=message,
            previous_plan=previous_plan,
        )

    def _build_ready_plan(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
        selected: CapabilityMatch,
        conditions: dict[str, float | int | str],
        candidate_models: list[str],
    ) -> ExecutionPlan:
        candidate_count = requirement.candidate_count or 2
        counts = self._split_candidate_count(candidate_count)
        seed = previous_plan.steps[0].seed if previous_plan and previous_plan.steps else None
        steps = [
            self._generate_step(
                model_id=selected.model_id,
                model_label=selected.capability.display_name,
                conditions=conditions,
                num_candidates=count,
                guidance_scale=selected.capability.default_guidance_scale,
                seed=seed,
            )
            for count in counts
        ]
        assumptions = [
            "目标性质用于生成条件引导，不代表生成后已完成性质预测或验证。",
            "元素组成约束由现有候选校验器执行。",
        ]
        if len(counts) > 1:
            assumptions.append(
                f"候选数 {candidate_count} 已拆分为 {len(counts)} 个生成步骤，"
                f"每步不超过 {MAX_CANDIDATES_PER_STEP} 个。"
            )
        assumptions.extend(requirement.assumptions)

        summary = self._ready_summary(
            requirement,
            selected,
            candidate_count,
            len(counts),
        )
        return self._new_plan(
            session_id=session_id,
            requirement=requirement,
            original_message=original_message,
            previous_plan=previous_plan,
            capability_status="ready",
            decision_reasons=[],
            candidate_models=candidate_models,
            summary=summary,
            assumptions=_unique(assumptions),
            questions=[],
            steps=steps,
        )

    def _build_decision_plan(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
        capability_status: CapabilityPlanningStatus,
        reasons: list[str],
        candidate_models: list[str],
    ) -> ExecutionPlan:
        questions = self._questions_for_status(
            capability_status,
            reasons,
        )
        summary = self._decision_summary(
            capability_status,
            reasons,
            candidate_models,
        )
        return self._new_plan(
            session_id=session_id,
            requirement=requirement,
            original_message=original_message,
            previous_plan=previous_plan,
            capability_status=capability_status,
            decision_reasons=_unique(reasons),
            candidate_models=candidate_models,
            summary=summary,
            assumptions=list(requirement.assumptions),
            questions=questions,
            steps=[],
        )

    def _new_plan(
        self,
        *,
        session_id: str,
        requirement: MaterialRequirementSpec,
        original_message: Optional[str],
        previous_plan: Optional[ExecutionPlan],
        capability_status: CapabilityPlanningStatus,
        decision_reasons: list[str],
        candidate_models: list[str],
        summary: str,
        assumptions: list[str],
        questions: list[str],
        steps: list[PlanStep],
    ) -> ExecutionPlan:
        return ExecutionPlan(
            plan_id=previous_plan.plan_id if previous_plan else str(uuid.uuid4()),
            session_id=session_id,
            revision=(previous_plan.revision + 1) if previous_plan else 1,
            original_message=(
                previous_plan.original_message
                if previous_plan
                else (original_message or self._original_message(requirement))
            ),
            summary=summary,
            assumptions=assumptions,
            questions=questions,
            capability_status=capability_status,
            decision_reasons=decision_reasons,
            candidate_models=candidate_models,
            request_spec=requirement,
            steps=steps,
        )

    def _build_conditions(
        self,
        requirement: MaterialRequirementSpec,
        selected: CapabilityMatch,
    ) -> tuple[dict[str, float | int | str], list[str], list[str]]:
        objectives = {
            objective.property: objective
            for objective in requirement.objectives
        }
        conditions: dict[str, float | int | str] = {}
        missing: list[str] = []
        errors: list[str] = []

        for property_name in selected.matched_objectives:
            objective = objectives.get(property_name)
            if objective is None or objective.target is None:
                missing.append(f"{property_name}_target")
                continue
            condition = selected.capability.objective_constraints.get(
                property_name
            )
            if condition is None:
                errors.append(f"{property_name}_not_a_generation_condition")
                continue
            constraint_error = self._validate_condition(
                property_name,
                objective.target,
                condition,
                objective.unit,
            )
            if constraint_error:
                errors.append(constraint_error)
                continue
            conditions[property_name] = objective.target

        for required_input in selected.capability.required_inputs:
            if required_input == "chemical_system":
                value = requirement.composition.chemical_system
                if value:
                    conditions["chemical_system"] = value
                else:
                    missing.append("chemical_system")
            elif required_input == "space_group":
                value = requirement.structure.space_group
                if value is not None:
                    conditions["space_group"] = value
                else:
                    missing.append("space_group")

        return conditions, _unique(missing), _unique(errors)

    @staticmethod
    def _validate_condition(
        property_name: str,
        target: float | int,
        condition: dict[str, object],
        objective_unit: Optional[str],
    ) -> Optional[str]:
        minimum = condition.get("minimum")
        maximum = condition.get("maximum")
        if minimum is not None and float(target) < float(minimum):
            return f"{property_name}_below_supported_range"
        if maximum is not None and float(target) > float(maximum):
            return f"{property_name}_above_supported_range"
        expected_unit = condition.get("unit")
        if (
            expected_unit
            and objective_unit
            and str(expected_unit) != objective_unit
        ):
            return f"{property_name}_unit_mismatch"
        return None

    @staticmethod
    def _split_candidate_count(total: int) -> list[int]:
        total = max(1, total)
        if total <= MAX_CANDIDATES_PER_STEP:
            return [total]
        step_count = math.ceil(total / MAX_CANDIDATES_PER_STEP)
        base, remainder = divmod(total, step_count)
        return [
            base + (1 if index < remainder else 0)
            for index in range(step_count)
        ]

    @staticmethod
    def _normalize_requirement(
        requirement: MaterialRequirementSpec,
    ) -> tuple[MaterialRequirementSpec, list[str]]:
        composition = requirement.composition
        errors: list[str] = []

        if "rare_earth" in composition.required_elements:
            errors.append("rare_earth_any_of_constraint_not_supported")

        excluded = [
            element
            for value in composition.excluded_elements
            for element in (
                RARE_EARTH_ELEMENTS if value == "rare_earth" else [value]
            )
        ]
        allowed = [
            element
            for value in composition.allowed_elements
            for element in (
                RARE_EARTH_ELEMENTS if value == "rare_earth" else [value]
            )
        ]
        if not errors and (
            excluded != composition.excluded_elements
            or allowed != composition.allowed_elements
        ):
            normalized_composition = composition.model_copy(
                update={
                    "excluded_elements": _unique(excluded),
                    "allowed_elements": _unique(allowed),
                }
            )
            normalized = requirement.model_copy(
                update={
                    "composition": normalized_composition,
                    "excluded_elements": normalized_composition.excluded_elements,
                    "allowed_elements": normalized_composition.allowed_elements,
                }
            )
            return normalized, errors
        return requirement, errors

    def _generate_step(
        self,
        *,
        model_id: str,
        model_label: str,
        conditions: dict[str, float | int | str],
        num_candidates: int,
        guidance_scale: float,
        seed: Optional[int],
    ) -> PlanStep:
        objective_text = "，".join(
            f"{name}={value}" for name, value in conditions.items()
        )
        return PlanStep(
            id=f"generate-{uuid.uuid4().hex[:8]}",
            kind="generate",
            title=f"使用{model_label}生成候选",
            description=(
                f"使用 {model_id} 生成 {num_candidates} 个候选；"
                f"生成条件：{objective_text or '无条件'}。"
                "该条件不代表生成后的性质验证。"
            ),
            model_id=model_id,
            conditions=conditions,
            num_candidates=num_candidates,
            guidance_scale=guidance_scale,
            seed=seed,
            required=False,
            on_failure="continue",
            max_retries=1,
            retry_delay_seconds=1.0,
            produces_candidates=True,
        )

    @staticmethod
    def _tool_step(
        *,
        kind: str,
        title: str,
        description: str,
        tool_name: str,
        inputs: dict[str, object],
        depends_on: Optional[list[str]] = None,
    ) -> PlanStep:
        return PlanStep(
            id=f"{kind}-{uuid.uuid4().hex[:8]}",
            kind=kind,  # type: ignore[arg-type]
            title=title,
            description=description,
            inputs={
                **inputs,
                "_tool": tool_name,
            },
            required=True,
            on_failure="abort",
            depends_on=depends_on or [],
        )

    @staticmethod
    def _ready_summary(
        requirement: MaterialRequirementSpec,
        selected: CapabilityMatch,
        candidate_count: int,
        step_count: int,
    ) -> str:
        objective_text = "、".join(
            objective.property
            for objective in requirement.objectives
        ) or "组成/结构条件"
        batch_text = (
            f"，拆分为 {step_count} 个生成步骤"
            if step_count > 1
            else ""
        )
        return (
            f"使用“{selected.capability.display_name}”生成 "
            f"{candidate_count} 个候选{batch_text}。目标：{objective_text}。"
        )

    @staticmethod
    def _decision_summary(
        capability_status: str,
        reasons: list[str],
        candidate_models: list[str],
    ) -> str:
        if capability_status == "clarification":
            return "当前需求缺少生成所需的必要信息，尚未创建执行步骤。"
        if capability_status == "unavailable":
            return "能力已注册，但当前运行环境无法执行对应模型。"
        if candidate_models:
            return (
                "当前没有完整覆盖全部要求的能力；"
                f"只有部分候选能力：{'、'.join(candidate_models)}。"
            )
        return "当前平台没有支持该需求的能力，未创建执行计划。"

    @staticmethod
    def _questions_for_status(
        capability_status: str,
        reasons: list[str],
    ) -> list[str]:
        if capability_status == "clarification":
            questions = []
            for reason in reasons:
                if reason == "material_property_objective":
                    questions.append("请说明你希望优化的具体材料性质。")
                elif reason.endswith("_target"):
                    property_name = reason.removesuffix("_target")
                    questions.append(
                        f"请说明 {property_name} 的目标数值和单位。"
                    )
                elif reason == "chemical_system":
                    questions.append("请说明要生成的元素体系。")
                elif reason == "space_group":
                    questions.append("请说明目标空间群编号。")
                else:
                    questions.append(f"请补充：{reason}")
            return _unique(questions)
        if capability_status == "unavailable":
            return ["当前环境缺少所需模型权重，暂时无法执行该计划。"]
        if reasons:
            return ["当前平台没有完整能力满足全部需求。"]
        return []

    @staticmethod
    def _original_message(
        requirement: MaterialRequirementSpec,
    ) -> str:
        return "结构化材料需求"

    def _build_steps(
        self,
        spec: MaterialRequestSpec,
        *,
        target_count: int,
        seed: Optional[int],
        decision=None,
    ) -> list[PlanStep]:
        """Compatibility helper for callers that already built a requirement."""

        requirement = spec.model_copy(
            update={"candidate_count": target_count}
        )
        return self.plan(
            session_id="compatibility",
            requirement=requirement,
        ).steps
