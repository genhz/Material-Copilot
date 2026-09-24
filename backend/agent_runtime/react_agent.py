"""ReAct reasoning loop for material planning."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional, Sequence

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agent_runtime.executor import AgentToolExecutor, ToolObservation
from agent_runtime.constraints import (
    ConstraintConflict,
    normalize_composition_constraints,
)
from agent_runtime.memory import AgentMemory, InMemoryAgentMemoryStore
from agent_runtime.planner import AgentPlanner
from agent_runtime.reflection import ReflectionEngine, ReflectionResult
from agent_runtime.tool_registry import (
    OBJECTIVE_HINTS,
    ToolDefinition,
    ToolRegistry,
)
from agent_workflow.capability_registry import CapabilityRegistry
from agent_workflow.schemas import ExecutionPlan
from config import get_llm_config


logger = logging.getLogger(__name__)


FORMULA_PATTERN = re.compile(
    r"\b[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)+\b"
)
CHEMICAL_SYSTEM_PATTERN = re.compile(
    r"\b[A-Z][a-z]?(?:-[A-Z][a-z]?)+\b"
)

ELEMENT_ALIASES = {
    "钕": "Nd",
    "铁": "Fe",
    "硼": "B",
    "钴": "Co",
    "镍": "Ni",
    "镝": "Dy",
    "镨": "Pr",
    "钐": "Sm",
    "铈": "Ce",
    "锰": "Mn",
    "铝": "Al",
    "铜": "Cu",
    "锌": "Zn",
    "氧": "O",
    "氮": "N",
    "碳": "C",
    "硅": "Si",
    "锂": "Li",
    "钠": "Na",
}

GENERATION_TERMS = (
    "生成",
    "设计",
    "探索",
    "候选",
    "新材料",
    "发现",
    "寻找",
    "generate",
    "design",
    "explore",
    "discover",
    "find",
)
MATERIAL_CLASS_TERMS = {
    "magnet": ("磁体", "磁铁", "永磁", "magnet"),
}
LOOKUP_TERMS = (
    "查看",
    "查询",
    "看看",
    "晶体结构",
    "结构数据",
    "是多少",
    "lookup",
    "show",
)
SUBSTITUTION_TERMS = (
    "替换",
    "替代",
    "掺杂",
    "换成",
    "substitute",
    "replace",
)
CHAT_TERMS = (
    "什么是",
    "为什么",
    "解释",
    "原理",
    "区别",
    "what is",
    "why",
    "explain",
)


class AgentDecision(BaseModel):
    """Structured JSON returned by the reasoning LLM."""

    thought: str
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ReActStep(BaseModel):
    """One complete Thought -> Action -> Observation cycle."""

    thought: str
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    observation: dict[str, Any] = Field(default_factory=dict)
    confidence: float


class AgentRunResult(BaseModel):
    """Final planning result plus the inspectable reasoning trace."""

    plan: Optional[ExecutionPlan] = None
    response: str
    trace: list[ReActStep] = Field(default_factory=list)
    reflection: Optional[str] = None
    memory: dict[str, Any] = Field(default_factory=dict)


class ReActAgent:
    """Reason, select a tool, observe, reflect, and replan when needed."""

    def __init__(
        self,
        *,
        capability_registry: Optional[CapabilityRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        memory_store: Optional[InMemoryAgentMemoryStore] = None,
        planner: Optional[AgentPlanner] = None,
        executor: Optional[AgentToolExecutor] = None,
        reflection: Optional[ReflectionEngine] = None,
        llm: Optional[Any] = None,
        use_llm: bool = True,
        max_iterations: int = 4,
    ):
        self.tool_registry = (
            tool_registry
            or ToolRegistry(capability_registry=capability_registry)
        )
        self.memory_store = (
            memory_store or InMemoryAgentMemoryStore()
        )
        self.planner = planner or AgentPlanner(
            tool_registry=self.tool_registry,
            memory_store=self.memory_store,
        )
        self.executor = executor or AgentToolExecutor(
            self.planner,
            self.tool_registry,
        )
        self.reflection = reflection or ReflectionEngine()
        self._llm = llm
        self._structured_llm: Any = None
        self.use_llm = use_llm
        self.max_iterations = max_iterations

    @property
    def structured_llm(self) -> Any:
        if self._structured_llm is None:
            llm = self._llm
            if llm is None:
                config = get_llm_config()
                llm = ChatOpenAI(
                    model=config.model,
                    api_key=config.api_key,
                    base_url=config.base_url,
                    temperature=0,
                    timeout=20,
                )
            if hasattr(llm, "with_structured_output"):
                self._structured_llm = llm.with_structured_output(
                    AgentDecision
                )
            else:
                self._structured_llm = llm
        return self._structured_llm

    async def run(
        self,
        message: str,
        *,
        session_id: str,
        history: Optional[Sequence[dict[str, Any]]] = None,
        previous_plan: Optional[ExecutionPlan] = None,
        mode: str = "message",
    ) -> AgentRunResult:
        memory = self.memory_store.get(session_id)
        trace: list[ReActStep] = []
        observations: list[dict[str, Any]] = []
        latest_plan: Optional[ExecutionPlan] = None
        latest_reflection: Optional[ReflectionResult] = None

        for iteration in range(self.max_iterations):
            decision = await self._decide(
                message=message,
                history=history or [],
                memory=memory,
                previous_plan=previous_plan,
                mode=mode,
                observations=observations,
            )
            decision.action = decision.action.removesuffix("()")
            selected_observation = self._selected_tool_observation(
                observations
            )
            if (
                decision.action == "choose_tool"
                and selected_observation is not None
            ):
                tool_name = str(
                    selected_observation.get("tool", {}).get("name") or ""
                )
                if tool_name:
                    decision.action = (
                        "plan_generation"
                        if self.tool_registry.get(tool_name)
                        and self.tool_registry.require(tool_name).kind
                        == "generation"
                        else tool_name
                    )

            observation = await self.executor.execute(
                action=decision.action,
                arguments=decision.arguments,
                session_id=session_id,
                message=message,
                previous_plan=previous_plan,
                reasoning_trace=[
                    step.model_dump(mode="json") for step in trace
                ],
            )
            trace.append(
                ReActStep(
                    thought=decision.thought,
                    action=decision.action,
                    arguments=decision.arguments,
                    observation=observation.model_dump(mode="json"),
                    confidence=decision.confidence,
                )
            )
            observations.append(observation.model_dump(mode="json"))
            plan = observation.plan
            if plan is not None:
                latest_plan = plan

            latest_reflection = await self.reflection.reflect(
                decision=decision,
                observation=observation,
                plan=plan,
                iteration=iteration,
                max_iterations=self.max_iterations,
            )
            trace.append(
                ReActStep(
                    thought=latest_reflection.thought,
                    action="reflect",
                    arguments={
                        "status": latest_reflection.status,
                        "reason": latest_reflection.reason,
                    },
                    observation={},
                    confidence=latest_reflection.confidence,
                )
            )

            if latest_plan is not None:
                if latest_reflection.status != "replan":
                    break
                continue

            if latest_reflection.status == "complete":
                break

        if latest_plan is not None:
            latest_plan.reasoning_trace = [
                step.model_dump(mode="json") for step in trace
            ]
            latest_plan.reflection = (
                latest_reflection.thought if latest_reflection else None
            )
            memory.remember_plan(latest_plan)

        response = self._response(latest_plan)
        return AgentRunResult(
            plan=latest_plan,
            response=response,
            trace=trace,
            reflection=(
                latest_reflection.thought if latest_reflection else None
            ),
            memory=memory.context(),
        )

    async def handle(
        self,
        message: str,
        *,
        session_id: str,
        history: Optional[Sequence[dict[str, Any]]] = None,
        previous_plan: Optional[ExecutionPlan] = None,
    ) -> AgentRunResult:
        return await self.run(
            message,
            session_id=session_id,
            history=history,
            previous_plan=previous_plan,
        )

    async def revise(
        self,
        *,
        session_id: str,
        previous_plan: ExecutionPlan,
        instruction: str,
        history: Optional[Sequence[dict[str, Any]]] = None,
    ) -> AgentRunResult:
        return await self.run(
            instruction,
            session_id=session_id,
            history=history,
            previous_plan=previous_plan,
            mode="revise",
        )

    async def _decide(
        self,
        *,
        message: str,
        history: Sequence[dict[str, Any]],
        memory: AgentMemory,
        previous_plan: Optional[ExecutionPlan],
        mode: str,
        observations: list[dict[str, Any]],
    ) -> AgentDecision:
        if self.use_llm:
            try:
                decision = await asyncio.wait_for(
                    self._llm_decision(
                        message=message,
                        history=history,
                        memory=memory,
                        previous_plan=previous_plan,
                        mode=mode,
                        observations=observations,
                    ),
                    timeout=25,
                )
                return self._validate_and_merge_decision(
                    decision=decision,
                    message=message,
                    memory=memory,
                    previous_plan=previous_plan,
                    mode=mode,
                )
            except Exception as exc:
                logger.warning(
                    "LLM reasoning unavailable; using deterministic fallback: %s",
                    exc,
                )
        return self._fallback_decision(
            message=message,
            memory=memory,
            previous_plan=previous_plan,
            mode=mode,
            observations=observations,
        )

    def _validate_and_merge_decision(
        self,
        *,
        decision: AgentDecision,
        message: str,
        memory: AgentMemory,
        previous_plan: Optional[ExecutionPlan],
        mode: str,
    ) -> AgentDecision:
        """Apply deterministic hard constraints on top of LLM output."""

        if mode == "revise" and previous_plan is not None:
            deterministic = self._apply_revision(
                self.planner.arguments_from_plan(previous_plan),
                message,
                memory,
            )
        else:
            deterministic = self._infer_arguments(message, memory)

        arguments = dict(decision.arguments)
        for key in (
            "task_type",
            "material_class",
            "output_requirements",
            "chemical_system",
            "required_elements",
            "allowed_elements",
            "excluded_elements",
            "constraint_groups",
            "constraint_errors",
            "candidate_count",
            "model_preferences",
        ):
            value = deterministic.get(key)
            if value not in (None, [], {}):
                arguments[key] = value

        arguments["objectives"] = self._merge_objectives(
            list(arguments.get("objectives") or []),
            list(deterministic.get("objectives") or []),
        )
        deterministic_objectives = {
            str(objective.get("property")): objective
            for objective in deterministic.get("objectives") or []
            if objective.get("property")
        }
        for objective in arguments["objectives"]:
            canonical = deterministic_objectives.get(
                str(objective.get("property") or "")
            )
            if canonical is None:
                continue
            objective["target"] = canonical.get("target")
            objective["operator"] = canonical.get("operator")
            objective["unit"] = canonical.get("unit")
            objective["semantic_goal"] = canonical.get("semantic_goal")

        if (
            deterministic.get("task_type") == "material_generation"
            and decision.action in {"material_search", "science_chat"}
            and not deterministic.get("formula")
        ):
            decision.action = "plan_generation"

        decision.arguments = arguments
        return decision

    async def _llm_decision(
        self,
        *,
        message: str,
        history: Sequence[dict[str, Any]],
        memory: AgentMemory,
        previous_plan: Optional[ExecutionPlan],
        mode: str,
        observations: list[dict[str, Any]],
    ) -> AgentDecision:
        system_prompt = f"""你是材料发现平台的 Reasoning Agent。

你的工作循环是：
Thought -> Action -> Observation -> Reflection -> Replan。

只能输出一个 JSON 对象，字段严格为：
{{
  "thought": "分析用户需求",
  "action": "工具名或 choose_tool()",
  "arguments": {{}},
  "confidence": 0.0
}}

规则：
1. 不要直接启动 MatterGen，也不要伪造性质数值。
2. 缺少数值时使用工具建议或生成 ask 参数，由 ExecutionPlan 请求用户确认。
3. 工具选择必须依据 ToolRegistry，不在推理中硬编码模型能力。
4. 用户要生成新材料时，优先选择 plan_generation 生成可确认计划。
5. 修订计划时选择 revise_plan，并给出完整的 arguments patch。
6. arguments 可包含 task_type、chemical_system、objectives、candidate_count、
   model_preferences、formula、input_material。

可用工具：
{self.tool_registry.prompt_description()}

Agent Memory：
{json.dumps(memory.context(), ensure_ascii=False, default=str)}

当前模式：{mode}
当前计划：
{json.dumps(previous_plan.model_dump(mode="json") if previous_plan else None, ensure_ascii=False)}

已有 Observation：
{json.dumps(observations, ensure_ascii=False, default=str)}
"""
        messages: list[Any] = [SystemMessage(content=system_prompt)]
        for item in history[-8:]:
            content = str(item.get("content") or "")
            if item.get("role") == "user":
                messages.append(HumanMessage(content=content))
            elif item.get("role") == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=message))
        result = await self.structured_llm.ainvoke(messages)
        if isinstance(result, AgentDecision):
            return result
        if isinstance(result, dict):
            return AgentDecision.model_validate(result)
        content = getattr(result, "content", result)
        if isinstance(content, str):
            return AgentDecision.model_validate_json(content)
        raise ValueError("LLM did not return AgentDecision JSON")

    def _fallback_decision(
        self,
        *,
        message: str,
        memory: AgentMemory,
        previous_plan: Optional[ExecutionPlan],
        mode: str,
        observations: list[dict[str, Any]],
    ) -> AgentDecision:
        if mode == "revise" and previous_plan is not None:
            arguments = self._apply_revision(
                self.planner.arguments_from_plan(previous_plan),
                message,
                memory,
            )
            return AgentDecision(
                thought=(
                    "结合当前计划和历史参数应用修订，再通过工具注册表"
                    "重新评估能力覆盖。"
                ),
                action="revise_plan",
                arguments=arguments,
                confidence=0.88,
            )

        selected = self._selected_tool_observation(observations)
        if selected:
            tool = selected.get("tool") or {}
            tool_name = str(tool.get("name") or "")
            arguments = self._infer_arguments(message, memory)
            if tool_name:
                descriptor = self.tool_registry.get(tool_name)
                if descriptor and descriptor.kind == "generation":
                    arguments["model_preferences"] = [tool_name]
                    return AgentDecision(
                        thought=(
                            "工具已经由能力注册表选定，现在生成计划。"
                        ),
                        action="plan_generation",
                        arguments=arguments,
                        confidence=0.86,
                    )
                return AgentDecision(
                    thought="工具已经选定，生成对应执行计划。",
                    action=tool_name,
                    arguments=arguments,
                    confidence=0.84,
                )

        arguments = self._infer_arguments(message, memory)
        action = self._action_for_arguments(arguments)
        return AgentDecision(
            thought=self._fallback_thought(arguments),
            action=action,
            arguments=arguments,
            confidence=0.84 if arguments["task_type"] != "science_chat" else 0.7,
        )

    def _infer_arguments(
        self,
        message: str,
        memory: AgentMemory,
    ) -> dict[str, Any]:
        task_type = self._infer_task_type(message)
        composition = self._extract_composition(message)
        objectives = self._extract_objectives(message)
        relative = memory.apply_relative_revision(message)
        objectives = self._merge_objectives(
            objectives,
            relative.get("objectives") or [],
        )
        model_preferences = [
            tool.name
            for tool in self.tool_registry.list_tools()
            if tool.kind == "generation"
            and tool.name.lower() in message.lower()
        ]
        arguments: dict[str, Any] = {
            "task_type": task_type,
            "material_class": self._infer_material_class(message),
            "output_requirements": self._infer_output_requirements(message),
            "chemical_system": composition.get("chemical_system"),
            "required_elements": composition.get("required_elements", []),
            "allowed_elements": composition.get("allowed_elements", []),
            "excluded_elements": (
                composition.get("excluded_elements")
                or list(memory.excluded_elements)
            ),
            "constraint_groups": (
                composition.get("constraint_groups")
                or dict(memory.constraint_groups)
            ),
            "objectives": objectives,
            "candidate_count": self._extract_candidate_count(message),
            "model_preferences": model_preferences,
        }
        try:
            normalized = normalize_composition_constraints(
                required_elements=arguments["required_elements"],
                allowed_elements=arguments["allowed_elements"],
                excluded_elements=arguments["excluded_elements"],
                chemical_system=arguments["chemical_system"],
            )
        except ConstraintConflict as exc:
            arguments["constraint_errors"] = [
                {"code": exc.code, "message": exc.message}
            ]
        else:
            arguments["required_elements"] = list(
                normalized.required_elements
            )
            arguments["allowed_elements"] = list(
                normalized.allowed_elements
            )
            arguments["excluded_elements"] = list(
                normalized.excluded_elements
            )
            arguments["constraint_groups"] = normalized.groups

        formula = self._extract_formula(message)
        if task_type == "material_lookup":
            arguments["formula"] = formula
            arguments["input_material"] = (
                {"formula": formula} if formula else None
            )
        elif task_type == "element_substitution":
            substitutions = self._extract_substitutions(message)
            arguments["formula"] = formula
            arguments["input_material"] = {
                "formula": formula,
                "substitutions": substitutions,
            }
            arguments["substitutions"] = substitutions
        return arguments

    def _apply_revision(
        self,
        base: dict[str, Any],
        instruction: str,
        memory: AgentMemory,
    ) -> dict[str, Any]:
        result = dict(base)
        result["objectives"] = [
            dict(item) for item in result.get("objectives") or []
        ]

        candidate_count = self._extract_candidate_count(instruction)
        if candidate_count is not None:
            result["candidate_count"] = candidate_count

        removed_properties = [
            property_name
            for property_name in self.tool_registry.property_mentioned(
                instruction
            )
            if any(
                cue in instruction
                for cue in ("不要", "去掉", "删除", "移除")
            )
        ]
        if removed_properties:
            removed = set(removed_properties)
            result["objectives"] = [
                objective
                for objective in result["objectives"]
                if objective.get("property") not in removed
            ]

        direct_objectives = self._extract_objectives(instruction)
        if any(
            objective.get("target") is not None
            or objective.get("semantic_goal")
            for objective in direct_objectives
        ):
            result["objectives"] = self._merge_objectives(
                result["objectives"],
                direct_objectives,
            )

        relative = memory.apply_relative_revision(instruction)
        if relative.get("objectives"):
            result["objectives"] = self._merge_objectives(
                result["objectives"],
                relative["objectives"],
            )

        composition_update = self._extract_composition(instruction)
        explicit_system = composition_update.get("chemical_system")
        if explicit_system:
            result["chemical_system"] = explicit_system
            result["allowed_elements"] = composition_update.get(
                "allowed_elements",
                [],
            )
        else:
            allowed_update = self._extract_allowed_elements(instruction)
            if allowed_update:
                combined = list(
                    dict.fromkeys(
                        [
                            *list(result.get("allowed_elements") or []),
                            *allowed_update,
                        ]
                    )
                )
                result["allowed_elements"] = combined
                result["chemical_system"] = "-".join(combined)

        required_update = composition_update.get("required_elements") or []
        if required_update:
            result["required_elements"] = list(
                dict.fromkeys(
                    [
                        *list(result.get("required_elements") or []),
                        *required_update,
                    ]
                )
            )

        excluded_update = composition_update.get("excluded_elements") or []
        allow_rare_earth = any(
            phrase in instruction
            for phrase in (
                "允许稀土",
                "不要排除稀土",
                "取消无稀土",
                "移除无稀土约束",
            )
        )
        if allow_rare_earth:
            result["excluded_elements"] = []
            result.pop("constraint_groups", None)
        elif excluded_update:
            result["excluded_elements"] = list(
                dict.fromkeys(
                    [
                        *list(result.get("excluded_elements") or []),
                        *excluded_update,
                    ]
                )
            )
            groups = dict(result.get("constraint_groups") or {})
            groups.update(composition_update.get("constraint_groups") or {})
            result["constraint_groups"] = groups
        return result

    def _infer_task_type(self, message: str) -> str:
        lowered = message.lower()
        formula = self._extract_formula(message)
        if any(term in lowered for term in SUBSTITUTION_TERMS):
            return "element_substitution"
        if any(term in lowered for term in GENERATION_TERMS):
            return "material_generation"
        if formula and any(term in lowered for term in LOOKUP_TERMS):
            return "material_lookup"
        if any(term in lowered for term in CHAT_TERMS):
            return "science_chat"
        if self.tool_registry.property_mentioned(message):
            return "material_generation"
        return "science_chat"

    @staticmethod
    def _action_for_arguments(arguments: dict[str, Any]) -> str:
        task_type = arguments.get("task_type")
        if task_type == "material_generation":
            return "plan_generation"
        if task_type == "material_lookup":
            return "material_search"
        if task_type == "element_substitution":
            return "element_substitution"
        return "science_chat"

    @staticmethod
    def _fallback_thought(arguments: dict[str, Any]) -> str:
        task_type = arguments.get("task_type")
        if task_type == "material_generation":
            return (
                "用户要求生成材料；先识别体系与目标性质，再由 "
                "ToolRegistry 匹配能力并补齐候选方案。"
            )
        if task_type == "material_lookup":
            return "用户需要查询已有材料数据，应选择材料查询工具。"
        if task_type == "element_substitution":
            return "用户要求修改已有材料组成，应选择元素替换工具。"
        return "这是材料知识问题，应选择科学对话工具。"

    def _extract_composition(self, message: str) -> dict[str, Any]:
        lowered = message.lower()
        required_elements: list[str] = []
        allowed_elements: list[str] = []
        excluded_elements: list[str] = []
        constraint_groups: dict[str, list[str]] = {}
        exact_formula = self._extract_formula(message)
        chemical_system_match = CHEMICAL_SYSTEM_PATTERN.search(message)
        chemical_system = (
            chemical_system_match.group(0)
            if chemical_system_match
            else None
        )

        if "钕铁硼" in message:
            required_elements.extend(["Nd", "Fe", "B"])
            chemical_system = "Nd-Fe-B"
        elif "钕铁合金" in message or "钕铁" in message:
            required_elements.extend(["Nd", "Fe"])
            chemical_system = "Nd-Fe"

        for chinese_name, symbol in ELEMENT_ALIASES.items():
            if (
                f"含{chinese_name}" in message
                or f"加入{chinese_name}" in message
            ):
                required_elements.append(symbol)

        negative_group_patterns = {
            "heavy_rare_earth": (
                "无重稀土",
                "不含重稀土",
                "排除重稀土",
                "禁止重稀土",
                "heavy rare earth free",
            ),
            "rare_earth": (
                "无稀土",
                "不含稀土",
                "排除稀土",
                "禁止稀土",
                "不含镧系",
                "无镧系",
                "rare earth free",
                "rare-earth-free",
            ),
        }
        for group, phrases in negative_group_patterns.items():
            if any(phrase in lowered for phrase in phrases):
                if group == "heavy_rare_earth":
                    excluded_elements.append(group)
                else:
                    excluded_elements.append(group)
                constraint_groups.setdefault(group, [])

        for match in re.finditer(
            r"(?:不含|排除|禁止|去掉|移除)\s*"
            r"([A-Z][a-z]?(?:\s*[,，、和]\s*[A-Z][a-z]?)*)",
            message,
        ):
            excluded_elements.extend(
                re.findall(r"[A-Z][a-z]?", match.group(1))
            )

        if chemical_system:
            allowed_elements = [
                element
                for element in chemical_system.split("-")
                if element
            ]
        return {
            "chemical_system": chemical_system,
            "required_elements": list(dict.fromkeys(required_elements)),
            "allowed_elements": list(dict.fromkeys(allowed_elements)),
            "excluded_elements": list(
                dict.fromkeys(excluded_elements)
            ),
            "constraint_groups": constraint_groups,
            "exact_formula": exact_formula,
        }

    @staticmethod
    def _infer_material_class(message: str) -> Optional[str]:
        lowered = message.lower()
        for material_class, terms in MATERIAL_CLASS_TERMS.items():
            if any(term in lowered for term in terms):
                return material_class
        return None

    @staticmethod
    def _infer_output_requirements(message: str) -> list[str]:
        outputs: list[str] = []
        if any(
            term in message
            for term in ("晶体结构", "结构", "cif", "CIF")
        ):
            outputs.append("crystal_structure")
        return outputs

    def _extract_allowed_elements(self, message: str) -> list[str]:
        elements: list[str] = []
        for match in re.finditer(
            r"(?:允许|可加入|可包含)\s*"
            r"([A-Z][a-z]?(?:\s*[,，、和]\s*[A-Z][a-z]?)*)",
            message,
        ):
            elements.extend(
                re.findall(r"[A-Z][a-z]?", match.group(1))
            )
        for chinese_name, symbol in ELEMENT_ALIASES.items():
            if (
                f"允许{chinese_name}" in message
                or f"允许加入{chinese_name}" in message
            ):
                elements.append(symbol)
        return list(dict.fromkeys(elements))

    def _extract_objectives(
        self,
        message: str,
    ) -> list[dict[str, Any]]:
        lowered = message.lower()
        objectives: list[dict[str, Any]] = []
        for property_name, hint in OBJECTIVE_HINTS.items():
            if not any(
                alias.lower() in lowered for alias in hint.aliases
            ):
                continue
            target = self._extract_target(message, hint.aliases)
            semantic_goal = self._infer_semantic_goal(
                property_name,
                message,
                target,
            )
            operator = self._infer_operator(
                message,
                hint.operator,
                target,
            )
            objectives.append(
                {
                    "property": property_name,
                    "operator": operator,
                    "target": target,
                    "unit": hint.unit,
                    "semantic_goal": semantic_goal,
                    "constraint_type": (
                        "hard"
                        if "必须" in message or "硬约束" in message
                        else "soft"
                    ),
                }
            )
        return sorted(
            objectives,
            key=lambda objective: self._objective_mention_position(
                message,
                str(objective["property"]),
            ),
        )

    @staticmethod
    def _objective_mention_position(
        message: str,
        property_name: str,
    ) -> int:
        hint = OBJECTIVE_HINTS[property_name]
        lowered = message.lower()
        positions = [
            lowered.find(alias.lower())
            for alias in hint.aliases
            if alias.lower() in lowered
        ]
        return min(positions) if positions else len(message)

    @staticmethod
    def _extract_target(
        message: str,
        aliases: Sequence[str],
    ) -> Optional[float]:
        for alias in aliases:
            patterns = (
                re.compile(
                    rf"{re.escape(alias)}.{{0,16}}?"
                    r"(\d+(?:\.\d+)?)",
                    flags=re.IGNORECASE,
                ),
                re.compile(
                    r"(\d+(?:\.\d+)?)\s*(?:eV|ev|GPa|gpa|"
                    r"Å\^-3|angstrom\^-3|/atom)?\s*"
                    rf"(?:的|of\s+)?{re.escape(alias)}",
                    flags=re.IGNORECASE,
                ),
            )
            for pattern in patterns:
                match = pattern.search(message)
                if match:
                    return float(match.group(1))
        return None

    @staticmethod
    def _infer_semantic_goal(
        property_name: str,
        message: str,
        target: Optional[float],
    ) -> Optional[str]:
        if target is not None:
            return "explicit_target"
        lowered = message.lower()
        if property_name == "energy_above_hull":
            if "严格" in message or "strict" in lowered:
                return "strict_stable"
            if "较稳定" in message or "稳定" in message or "stable" in lowered:
                return "stable"
        if property_name == "dft_mag_density" and (
            "高磁" in message
            or "磁体" in message
            or "永磁" in message
            or "magnet" in lowered
            or "high magnetic" in lowered
        ):
            return "high_magnetic_density"
        if property_name == "hhi_score" and (
            "低供应风险" in message or "low supply risk" in lowered
        ):
            return "low_supply_risk"
        return None

    @staticmethod
    def _infer_operator(
        message: str,
        default: str,
        target: Optional[float],
    ) -> str:
        lowered = message.lower()
        if any(
            cue in lowered
            for cue in ("约", "大约", "近似", "around", "approximately")
        ):
            return "~="
        if any(
            cue in lowered
            for cue in (
                "小于",
                "低于",
                "不超过",
                "至多",
                "less than",
                "below",
            )
        ):
            return "<="
        if any(
            cue in lowered
            for cue in (
                "大于",
                "高于",
                "至少",
                "higher",
                "greater",
                "above",
            )
        ):
            return ">="
        if target is not None:
            return "~="
        return default

    @staticmethod
    def _extract_candidate_count(message: str) -> Optional[int]:
        patterns = (
            r"候选(?:数|数量)?(?:改为|设为|为)?\s*(\d+)",
            r"(?:数量|个数)(?:改为|设为|为)?\s*(\d+)",
            r"(\d+)\s*(?:个|种|款)\s*(?:候选|材料|结构)?",
            r"(\d+)\s*(?:candidates?|materials?|structures?)",
        )
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _extract_formula(message: str) -> Optional[str]:
        match = FORMULA_PATTERN.search(message)
        return match.group(0) if match else None

    @staticmethod
    def _extract_substitutions(message: str) -> dict[str, str]:
        match = re.search(
            r"(?P<source>[A-Z][a-z]?)\s*"
            r"(?:换成|替换为|替换成|替代为|改为|to)\s*"
            r"(?P<target>[A-Z][a-z]?)",
            message,
        )
        if not match:
            return {}
        return {match.group("source"): match.group("target")}

    @staticmethod
    def _merge_objectives(
        existing: Sequence[dict[str, Any]],
        updates: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = {
            str(objective.get("property")): dict(objective)
            for objective in existing
            if objective.get("property")
        }
        for objective in updates:
            property_name = str(objective.get("property") or "")
            if not property_name:
                continue
            if property_name in merged:
                merged[property_name].update(
                    {
                        key: value
                        for key, value in objective.items()
                        if value is not None
                    }
                )
            else:
                merged[property_name] = dict(objective)
        return list(merged.values())

    @staticmethod
    def _selected_tool_observation(
        observations: Sequence[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        for observation in reversed(observations):
            if observation.get("status") == "selected":
                return observation.get("output") or {}
        return None

    @staticmethod
    def _response(plan: Optional[ExecutionPlan]) -> str:
        if plan is None:
            return "当前推理没有得到可执行计划，请补充目标或调整请求。"
        if plan.capability_status == "ready":
            return "执行计划已生成，请确认或修改后开始执行。"
        if plan.questions:
            return plan.questions[0]
        return plan.summary
