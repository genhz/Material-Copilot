"""Create editable material workflows from structured user requests."""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from agent_workflow.schemas import (
    ExecutionPlan,
    MaterialRequestSpec,
    PlanStep,
)
from agent_workflow.semantics import extract_semantics
from intent.classifier import IntentClassifier, _heuristic_decision


class WorkflowPlanner:
    """Understand a request and produce a plan without executing it."""

    def __init__(self):
        self._classifier = None

    async def _classify(self, text: str, history):
        heuristic = _heuristic_decision(text)
        if heuristic is not None:
            return heuristic

        if self._classifier is None:
            from config import get_llm_config
            from langchain_openai import ChatOpenAI

            config = get_llm_config()
            llm = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.1,
            )
            self._classifier = IntentClassifier(llm)
        return await self._classifier.classify(text, history)

    async def propose(
        self,
        *,
        session_id: str,
        message: str,
        history: Optional[Sequence[dict]] = None,
        previous_plan: Optional[ExecutionPlan] = None,
        revision_instruction: Optional[str] = None,
    ) -> Optional[ExecutionPlan]:
        combined_text = message
        if revision_instruction:
            combined_text = f"{message}\n用户修改要求：{revision_instruction}"

        spec = extract_semantics(combined_text)
        decision = (
            _heuristic_decision(message)
            if previous_plan is not None
            else await self._classify(combined_text, history)
        )
        if decision and decision.intent != "material_generation":
            return None
        if decision is None and not any(
            cue in combined_text
            for cue in ("生成", "设计", "探索", "候选", "新材料", "新型材料")
        ):
            return None

        count_match = None
        import re

        count_match = re.search(
            r"(?:候选(?:数|数量)?(?:改为|设为|为)?\s*)?(\d+)\s*(?:个|种)",
            combined_text,
        )
        if count_match is None:
            count_match = re.search(
                r"候选(?:数|数量)?(?:改为|设为|为)?\s*(\d+)",
                combined_text,
            )
        target_count = (
            max(1, min(int(count_match.group(1)), 16))
            if count_match
            else 8
        )
        seed = previous_plan.steps[0].seed if previous_plan else None

        steps = self._build_steps(
            spec,
            target_count=target_count,
            seed=seed,
            decision=decision,
        )
        summary = self._build_summary(spec, target_count)
        assumptions = [
            "所有生成候选都会执行元素硬约束过滤。",
            "没有性质评估器时，目标性质只作为生成引导，不能视为已验证。",
        ]
        questions = list(spec.ambiguities)

        plan_id = previous_plan.plan_id if previous_plan else str(uuid.uuid4())
        revision = (previous_plan.revision + 1) if previous_plan else 1
        return ExecutionPlan(
            plan_id=plan_id,
            session_id=session_id,
            revision=revision,
            original_message=(
                previous_plan.original_message if previous_plan else message
            ),
            summary=summary,
            assumptions=assumptions,
            questions=questions,
            request_spec=spec,
            steps=steps,
        )

    def _build_steps(
        self,
        spec: MaterialRequestSpec,
        *,
        target_count: int,
        seed: Optional[int],
        decision,
    ) -> list[PlanStep]:
        oversample = max(8, min(16, target_count * 4))
        steps: list[PlanStep] = []
        objective_names = {item.property for item in spec.objectives}
        has_magnetic = "dft_mag_density" in objective_names
        has_stability = "energy_above_hull" in objective_names
        wants_hhi = (
            decision is not None
            and decision.model_id == "dft_mag_density_hhi_score"
        )
        chemical_system = spec.chemical_system

        if has_magnetic:
            magnetic = next(
                item
                for item in spec.objectives
                if item.property == "dft_mag_density"
            )
            model_id = (
                "dft_mag_density_hhi_score"
                if wants_hhi
                else "dft_mag_density"
            )
            conditions: dict[str, float] = {
                "dft_mag_density": magnetic.target
            }
            if wants_hhi:
                conditions["hhi_score"] = 0.2
            steps.append(
                self._generate_step(
                    model_id=model_id,
                    title="生成磁性能候选",
                    description=(
                        f"使用 {model_id} 生成磁密度目标为 "
                        f"{magnetic.target} 的候选。"
                    ),
                    conditions=conditions,
                    num_candidates=oversample,
                    seed=seed,
                )
            )

        if chemical_system:
            chemistry_model = (
                "chemical_system_energy_above_hull"
                if has_stability
                else "chemical_system"
            )
            chemistry_conditions: dict[str, float | str] = {
                "chemical_system": chemical_system
            }
            if has_stability:
                stability = next(
                    item
                    for item in spec.objectives
                    if item.property == "energy_above_hull"
                )
                chemistry_conditions["energy_above_hull"] = stability.target
            steps.append(
                self._generate_step(
                    model_id=chemistry_model,
                    title="生成指定元素体系候选",
                    description=(
                        f"使用 {chemistry_model} 约束到 "
                        f"{chemical_system} 元素体系。"
                    ),
                    conditions=chemistry_conditions,
                    num_candidates=oversample,
                    seed=seed,
                )
            )

        if not steps:
            band_gap = next(
                (
                    item
                    for item in spec.objectives
                    if item.property == "dft_band_gap"
                ),
                None,
            )
            if band_gap:
                steps.append(
                    self._generate_step(
                        model_id="dft_band_gap",
                        title="生成目标带隙候选",
                        description=(
                            f"生成带隙约为 {band_gap.target} eV 的候选。"
                        ),
                        conditions={"dft_band_gap": band_gap.target},
                        num_candidates=oversample,
                        seed=seed,
                    )
                )
            else:
                steps.append(
                    self._generate_step(
                        model_id="mattergen_base",
                        title="通用材料探索",
                        description="使用通用模型生成无机材料候选。",
                        conditions={},
                        num_candidates=oversample,
                        seed=seed,
                    )
                )

        steps.append(
            PlanStep(
                id=f"filter-{uuid.uuid4().hex[:8]}",
                kind="filter",
                title="执行元素与组成硬约束筛选",
                description=(
                    "删除必须包含、允许包含和禁止包含元素不满足的候选。"
                ),
            )
        )
        steps.append(
            PlanStep(
                id=f"rank-{uuid.uuid4().hex[:8]}",
                kind="rank",
                title="汇总与排序",
                description="合并不同生成器结果并返回去重后的候选摘要。",
            )
        )
        return steps

    def _generate_step(
        self,
        *,
        model_id: str,
        title: str,
        description: str,
        conditions: dict,
        num_candidates: int,
        seed: Optional[int],
    ) -> PlanStep:
        return PlanStep(
            id=f"generate-{uuid.uuid4().hex[:8]}",
            kind="generate",
            title=title,
            description=description,
            model_id=model_id,
            conditions=conditions,
            num_candidates=num_candidates,
            guidance_scale=3.0,
            seed=seed,
        )

    def _build_summary(
        self,
        spec: MaterialRequestSpec,
        target_count: int,
    ) -> str:
        pieces = ["构建一个包含生成、硬约束过滤和汇总排序的材料探索 Workflow。"]
        if spec.required_elements:
            pieces.append(
                "必须包含元素：" + "、".join(spec.required_elements) + "。"
            )
        if spec.allowed_elements:
            pieces.append(
                "允许元素范围：" + "、".join(spec.allowed_elements) + "。"
            )
        if spec.excluded_elements:
            pieces.append(
                "禁止元素：" + "、".join(spec.excluded_elements) + "。"
            )
        if spec.objectives:
            objective_text = "；".join(
                f"{item.property} {item.operator} {item.target}"
                for item in spec.objectives
            )
            pieces.append("目标：" + objective_text + "。")
        pieces.append(f"目标有效候选数：{target_count}。")
        return "".join(pieces)
