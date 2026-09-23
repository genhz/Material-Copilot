"""Deprecated compatibility parser; the main path uses agent_runtime."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional, Sequence

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent_workflow.schemas import (
    CompositionSpec,
    MaterialRequirementSpec,
    ObjectiveSpec,
    StructureSpec,
)
from agent_workflow.normalization import (
    ELEMENT_ALIASES,
    extract_requested_elements,
)
from config import get_llm_config


logger = logging.getLogger(__name__)


REQUIREMENT_PARSER_PROMPT = """你是材料 AI 平台的需求解析器。

你的唯一职责是把用户自然语言转换成 MaterialRequirementSpec。

必须遵守：
1. 只能抽取用户明确表达的需求，不要自行创造科学目标。
2. 不要选择、推荐或验证任何具体模型，输出中不存在 model_id。
3. 不要把“高性能”“性能好”“较优”等模糊表达转换成具体性质。
4. 不要因为模型名称、应用场景或相似概念自行补充科学目标。
5. 不要把“高磁密度”转换成具体数值；target 必须保持 null。
6. 不要把“较稳定”转换成 0.05 eV/atom；target 必须保持 null。
7. 不要把“高矫顽力”“热导率”“强度”等当前不支持的请求映射到磁密度、
   体积模量或其他相似性质。
8. 用户给出了性质但没有给出数值时，在 missing_information 中记录。
9. 用户提出了当前平台不支持的性质时，在 unsupported_requirements 中记录。
10. 用户没有明确数量时，candidate_count 保持 null，由 PlanningPolicy 决定；
    不要修改用户明确给出的数量。
11. 只有用户明确提到模型名称时，才写入 model_preferences；不要验证其可用性。
12. application 只是上下文，不能据此增加用户没有提出的性能目标。

性质标准化示例：
- 磁密度 -> dft_mag_density
- 供应风险/HHI -> hhi_score
- 稳定性/凸包 -> energy_above_hull
- 带隙 -> dft_band_gap
- 体积模量 -> ml_bulk_modulus
- 空间群 -> structure.space_group

语义目标示例：
- 较稳定 -> semantic_goal = stable
- 更严格稳定 -> semantic_goal = strict_stable
- 较宽松稳定 -> semantic_goal = relaxed_stable

任务类型只能是：
material_generation、material_lookup、element_substitution、
science_chat、clarification。

如果用户想生成材料但没有可识别的科学目标，返回 clarification，
并记录 material_property_objective。
"""

REVISION_PARSER_PROMPT = """你是材料 AI 平台的需求修订器。

你会收到一个完整的 previous MaterialRequirementSpec 和用户的一条修订指令。
previous requirement 是未修改字段的事实来源。

你的任务是输出修订后的完整 MaterialRequirementSpec，而不是 patch。

必须遵守：
1. 用户没有修改的字段必须保持原值，不能重新猜测或清空。
2. 只能应用用户明确表达的增、删、改、替换或保留要求。
3. 不要选择或推荐模型，不要输出 model_id。
4. 不要调用工具，不要创建 Workflow、PlanStep 或 generation job。
5. 不要新增用户没有提出的科学目标。
6. 不要为“更好”“性能好”等模糊表达填科学数值。
7. 不要根据应用场景自动增加 coercivity、remanence、Curie temperature 等目标。
8. 不支持的属性必须进入 unsupported_requirements，不能映射成相似属性。
9. 明显改变任务类型时，例如从生成改成查询，必须输出新的 task_type。
10. 候选数量大于 16 时保持用户给出的数字，不要截断。

修订规则：
- “改成 16 个”只修改 candidate_count。
- “磁密度改成 0.25”只修改对应 objective 的 target。
- “保留磁密度要求，改成 Nd-Fe-B”保留 objective，并替换 composition。
- “增加稳定性要求”添加新 objective，但不判断模型能力。
- “不要磁密度要求了”删除对应 objective。
- “不要生成了，查看 Fe3O4”整体切换为 material_lookup。
"""


FORMULA_PATTERN = re.compile(
    r"\b[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)+\b"
)
CHEMICAL_SYSTEM_PATTERN = re.compile(
    r"\b[A-Z][a-z]?(?:-[A-Z][a-z]?)+\b"
)
SYMBOL_PATTERN = re.compile(r"\b[A-Z][a-z]?\b")

GENERATION_CUES = (
    "生成",
    "设计",
    "探索",
    "候选",
    "新材料",
    "新型材料",
    "发现",
    "寻找",
    "得到",
    "做一个",
    "generate",
    "design",
    "discover",
    "find",
    "explore",
    "create",
)
LOOKUP_CUES = (
    "查看",
    "查询",
    "看看",
    "结构",
    "晶体数据",
    "材料数据",
    "是多少",
    "lookup",
    "show",
    "view",
)
SUBSTITUTION_CUES = (
    "替换",
    "替代",
    "掺杂",
    "换成",
    "改为",
    "substitute",
    "replace",
    "dope",
)
SCIENCE_CHAT_CUES = (
    "什么是",
    "是什么意思",
    "为什么",
    "解释",
    "原理",
    "区别",
    "what is",
    "why",
    "explain",
)

SUPPORTED_PROPERTY_ALIASES: dict[str, tuple[str, ...]] = {
    "dft_mag_density": (
        "dft_mag_density",
        "磁密度",
        "magnetic density",
        "magnetization density",
    ),
    "hhi_score": (
        "hhi_score",
        "hhi",
        "供应风险",
        "供应集中度",
        "supply risk",
        "supply concentration",
    ),
    "energy_above_hull": (
        "energy_above_hull",
        "能量高于凸包",
        "凸包",
        "稳定性",
        "较稳定",
        "stable",
        "stability",
    ),
    "dft_band_gap": (
        "dft_band_gap",
        "带隙",
        "band gap",
        "bandgap",
    ),
    "ml_bulk_modulus": (
        "ml_bulk_modulus",
        "体积模量",
        "体模量",
        "bulk modulus",
    ),
}

UNSUPPORTED_PROPERTY_ALIASES: dict[str, tuple[str, ...]] = {
    "coercivity": ("矫顽力", "coercivity", "coercive field"),
    "thermal_conductivity": (
        "热导率",
        "导热率",
        "thermal conductivity",
    ),
    "strength": ("抗拉强度", "机械强度", "高强度", "强度", "strength"),
    "remanence": ("剩磁", "remanence", "remanent magnetization"),
}

TARGET_UNITS = {
    "dft_mag_density": "Å^-3",
    "hhi_score": None,
    "energy_above_hull": "eV/atom",
    "dft_band_gap": "eV",
    "ml_bulk_modulus": "GPa",
    "density": "g/cm^3",
    "strength": "GPa",
    "coercivity": "T",
    "thermal_conductivity": "W/(m·K)",
    "remanence": "T",
}

MODEL_PREFERENCES = (
    "mattergen_base",
    "mp_20_base",
    "dft_mag_density_hhi_score",
    "chemical_system_energy_above_hull",
    "dft_mag_density",
    "chemical_system",
    "dft_band_gap",
    "ml_bulk_modulus",
    "space_group",
)

CRYSTAL_SYSTEMS = {
    "三斜": "triclinic",
    "单斜": "monoclinic",
    "正交": "orthorhombic",
    "四方": "tetragonal",
    "三方": "trigonal",
    "六方": "hexagonal",
    "立方": "cubic",
}


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _normalize_element(value: str) -> str:
    token = value.strip()
    return ELEMENT_ALIASES.get(token, token)


def _extract_formula(text: str) -> Optional[str]:
    match = FORMULA_PATTERN.search(text)
    return match.group(0) if match else None


def _extract_candidate_count(text: str) -> Optional[int]:
    patterns = (
        r"候选(?:数|数量)?(?:改为|设为|为)?\s*(\d+)",
        r"(?:数量|个数)(?:改为|设为|为)?\s*(\d+)",
        r"(\d+)\s*(?:个|种|款)\s*(?:候选|材料|结构)?",
        r"(\d+)\s*(?:candidates?|materials?|structures?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_chemical_system(text: str) -> Optional[str]:
    match = CHEMICAL_SYSTEM_PATTERN.search(text)
    return match.group(0) if match else None


def _extract_composition(text: str) -> CompositionSpec:
    chemical_system = _extract_chemical_system(text)
    allowed_elements: list[str] = (
        chemical_system.split("-") if chemical_system else []
    )

    required_elements = extract_requested_elements(text)
    for marker in ("必须包含", "必须含", "包含", "含有", "含"):
        start = text.find(marker)
        if start < 0:
            continue
        fragment = text[start + len(marker): start + len(marker) + 80]
        required_elements.extend(SYMBOL_PATTERN.findall(fragment))
        required_elements.extend(
            symbol
            for chinese_name, symbol in ELEMENT_ALIASES.items()
            if chinese_name in fragment
        )

    for marker in ("允许", "加入", "可用", "可包含"):
        start = text.find(marker)
        if start < 0:
            continue
        fragment = text[start + len(marker): start + len(marker) + 80]
        allowed_elements.extend(SYMBOL_PATTERN.findall(fragment))
        allowed_elements.extend(
            symbol
            for chinese_name, symbol in ELEMENT_ALIASES.items()
            if chinese_name in fragment
        )

    excluded_elements: list[str] = []
    if any(
        phrase in text
        for phrase in ("不含稀土", "无稀土", "排除稀土", "禁止稀土")
    ):
        excluded_elements.append("rare_earth")

    for marker in ("不含", "排除", "禁止", "去掉"):
        start = text.find(marker)
        if start < 0:
            continue
        fragment = text[start + len(marker): start + len(marker) + 80]
        excluded_elements.extend(SYMBOL_PATTERN.findall(fragment))
        excluded_elements.extend(
            symbol
            for chinese_name, symbol in ELEMENT_ALIASES.items()
            if chinese_name in fragment
        )

    required_elements = [
        element
        for element in _unique(required_elements)
        if element not in excluded_elements
    ]
    allowed_elements = [
        element
        for element in _unique([*allowed_elements, *required_elements])
        if element not in excluded_elements
    ]
    if (
        chemical_system is None
        and required_elements
        and any(cue in text for cue in ("合金", "体系"))
    ):
        chemical_system = "-".join(required_elements)
    return CompositionSpec(
        required_elements=required_elements,
        allowed_elements=allowed_elements,
        excluded_elements=_unique(excluded_elements),
        chemical_system=chemical_system,
    )


def _extract_structure(text: str) -> StructureSpec:
    space_group_match = re.search(
        r"(?:空间群|space\s*group)\s*(?:为|:|=)?\s*(\d{1,3})",
        text,
        flags=re.IGNORECASE,
    )
    space_group = (
        int(space_group_match.group(1)) if space_group_match else None
    )
    crystal_system = next(
        (
            canonical
            for label, canonical in CRYSTAL_SYSTEMS.items()
            if label in text
        ),
        None,
    )
    return StructureSpec(
        space_group=space_group,
        crystal_system=crystal_system,
    )


def _extract_application(text: str) -> Optional[str]:
    if "永磁体" in text or "永磁材料" in text or "permanent magnet" in text:
        return "permanent_magnet"
    if "催化剂" in text or "catalyst" in text:
        return "catalyst"
    if "电池" in text or "battery" in text:
        return "battery"
    if "半导体" in text or "semiconductor" in text:
        return "semiconductor"
    return None


def _extract_exploration_mode(text: str) -> str:
    normalized = text.lower()
    if any(
        cue in normalized
        for cue in (
            "多个模型",
            "多模型",
            "所有模型",
            "全面探索",
            "multi-model",
            "multiple models",
        )
    ):
        return "multi_model"
    return "single_model"


def _extract_model_preferences(text: str) -> list[str]:
    lowered = text.lower()
    preferences = [
        model_id
        for model_id in MODEL_PREFERENCES
        if model_id.lower() in lowered
    ]
    patterns = (
        r"使用\s*[`\"']?([A-Za-z][A-Za-z0-9_.-]{2,})[`\"']?"
        r"\s*(?:模型|model)",
        r"use\s+(?:the\s+)?[`\"']?([A-Za-z][A-Za-z0-9_.-]{2,})"
        r"[`\"']?\s+model",
    )
    for pattern in patterns:
        preferences.extend(
            match.group(1)
            for match in re.finditer(pattern, text, flags=re.IGNORECASE)
        )
    return _unique(preferences)


def _find_number_after_property(
    text: str,
    aliases: Sequence[str],
) -> Optional[float]:
    for alias in aliases:
        pattern = re.compile(
            rf"{re.escape(alias)}.{{0,16}}?"
            r"(\d+(?:\.\d+)?)",
            flags=re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            return float(match.group(1))

        reverse_pattern = re.compile(
            r"(\d+(?:\.\d+)?)\s*(?:eV|ev|GPa|gpa|Å\^-3|"
            rf"angstrom\^-3|/atom)?\s*(?:的|of\s+)?{re.escape(alias)}",
            flags=re.IGNORECASE,
        )
        match = reverse_pattern.search(text)
        if match:
            return float(match.group(1))
    return None


def _explicit_target_present(text: str, property_name: str) -> bool:
    aliases = SUPPORTED_PROPERTY_ALIASES.get(property_name)
    if not aliases:
        return False
    return _find_number_after_property(text, aliases) is not None


def _extract_operator(text: str, property_name: str, target: Optional[float]) -> str:
    lowered = text.lower()
    if any(
        cue in lowered
        for cue in ("约", "大约", "近似", "around", "approximately", "~=")
    ):
        return "~="
    if any(
        cue in lowered
        for cue in (
            "小于",
            "低于",
            "不超过",
            "至多",
            "lower",
            "less than",
            "below",
            "<=",
        )
    ):
        return "<="
    if property_name == "hhi_score" and (
        "低供应风险" in text or "lower supply risk" in lowered
    ):
        return "<="
    if property_name == "energy_above_hull" and (
        "较稳定" in text or "更稳定" in text
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
            ">=",
        )
    ):
        return ">="
    if target is not None:
        return "~="
    if property_name == "dft_mag_density":
        return ">="
    return ">="


def _constraint_type(text: str) -> str:
    if any(
        cue in text
        for cue in ("必须", "硬约束", "hard constraint", "strictly")
    ):
        return "hard"
    return "soft"


def _semantic_goal(
    property_name: str,
    text: str,
    target: Optional[float],
) -> Optional[str]:
    if target is not None:
        return "explicit_target"
    if property_name == "energy_above_hull":
        if any(
            cue in text
            for cue in ("更严格", "非常稳定", "高度稳定", "严格稳定")
        ):
            return "strict_stable"
        if any(cue in text for cue in ("宽松", "稍微稳定")):
            return "relaxed_stable"
        if any(cue in text for cue in ("较稳定", "稳定", "stable")):
            return "stable"
    if property_name == "dft_mag_density" and any(
        cue in text for cue in ("高磁", "磁性高", "high magnetic")
    ):
        return "high_magnetic_density"
    if property_name == "hhi_score" and any(
        cue in text for cue in ("低供应风险", "供应风险低", "low supply risk")
    ):
        return "low_supply_risk"
    return None


def _extract_supported_objectives(text: str) -> list[ObjectiveSpec]:
    lowered = text.lower()
    objectives: list[ObjectiveSpec] = []
    for property_name, aliases in SUPPORTED_PROPERTY_ALIASES.items():
        if not any(alias.lower() in lowered for alias in aliases):
            continue
        target = _find_number_after_property(text, aliases)
        objectives.append(
            ObjectiveSpec(
                property=property_name,
                target=target,
                operator=_extract_operator(text, property_name, target),
                unit=TARGET_UNITS.get(property_name),
                semantic_goal=_semantic_goal(
                    property_name,
                    text,
                    target,
                ),
                constraint_type=_constraint_type(text),
                priority=1 if "优先" in text or "首要" in text else None,
            )
        )
    return objectives


def _extract_unsupported_objectives(text: str) -> list[ObjectiveSpec]:
    lowered = text.lower()
    objectives: list[ObjectiveSpec] = []
    detected: dict[str, tuple[str, Optional[str]]] = {}

    for property_name, aliases in UNSUPPORTED_PROPERTY_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            detected[property_name] = (
                _extract_operator(text, property_name, None),
                None,
            )

    if (
        any(cue in text for cue in ("低密度", "密度低", "lower density"))
        and "磁密度" not in text
    ):
        detected["density"] = ("<=", None)
    if (
        any(cue in text for cue in ("高强度", "强度高", "high strength"))
        and "磁" not in text
    ):
        detected["strength"] = (">=", None)

    for property_name, (operator, _) in detected.items():
        objectives.append(
            ObjectiveSpec(
                property=property_name,
                target=None,
                operator=operator,
                unit=TARGET_UNITS.get(property_name),
                constraint_type="soft",
            )
        )
    return objectives


def _extract_input_material(
    text: str,
    *,
    context: Optional[dict[str, Any]],
) -> tuple[Optional[Any], dict[str, str]]:
    from agent_workflow.schemas import InputMaterialSpec

    formula = _extract_formula(text)
    substitutions: dict[str, str] = {}

    substitution_match = re.search(
        r"(?:把|将)?\s*"
        r"(?P<formula>\b[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)+\b)?"
        r".{0,12}?"
        r"(?P<source>[A-Z][a-z]?|[\u4e00-\u9fff])"
        r"\s*(?:换成|替换为|替换成|替代为|改为|to)\s*"
        r"(?P<target>[A-Z][a-z]?|[\u4e00-\u9fff])",
        text,
        flags=re.IGNORECASE,
    )
    if substitution_match:
        formula = substitution_match.group("formula") or formula
        substitutions[_normalize_element(substitution_match.group("source"))] = (
            _normalize_element(substitution_match.group("target"))
        )

    context_data = context or {}
    formula = formula or context_data.get("formula")
    cif = context_data.get("cif")
    material_id = context_data.get("material_id")
    if not any((formula, cif, material_id, substitutions)):
        return None, substitutions
    return (
        InputMaterialSpec(
            formula=formula,
            cif=cif,
            material_id=material_id,
            substitutions=substitutions,
        ),
        substitutions,
    )


def _detect_task_type(
    text: str,
    *,
    formula: Optional[str],
    supported_objectives: list[ObjectiveSpec],
    unsupported_objectives: list[ObjectiveSpec],
) -> str:
    lowered = text.lower()
    substitution_requested = bool(
        re.search(
            r"(?:把|将).{0,30}?(?:换成|替换为|替换成|替代为|改为)",
            text,
        )
    ) or bool(
        re.search(
            r"(?:[A-Z][a-z]?|[\u4e00-\u9fff])"
            r"\s*(?:换成|替换为|替换成|替代为)",
            text,
        )
    )
    if substitution_requested:
        return "element_substitution"
    if formula and any(cue in lowered for cue in LOOKUP_CUES):
        return "material_lookup"

    generation_requested = any(
        cue in lowered for cue in GENERATION_CUES
    )
    if generation_requested:
        if any(
            phrase in lowered
            for phrase in (
                "性能好",
                "性能较优",
                "性能优异",
                "高性能",
                "good performance",
                "high-performance",
            )
        ) and not supported_objectives and not unsupported_objectives:
            return "clarification"
        return "material_generation"

    if any(cue in lowered for cue in SCIENCE_CHAT_CUES):
        return "science_chat"
    if any(
        alias in lowered
        for aliases in SUPPORTED_PROPERTY_ALIASES.values()
        for alias in aliases
    ):
        return "science_chat"
    return "science_chat"


def _deduplicate_objectives(
    objectives: Sequence[ObjectiveSpec],
) -> list[ObjectiveSpec]:
    result: list[ObjectiveSpec] = []
    indexes: dict[str, int] = {}
    for objective in objectives:
        existing_index = indexes.get(objective.property)
        if existing_index is None:
            indexes[objective.property] = len(result)
            result.append(objective)
            continue
        existing = result[existing_index]
        updates: dict[str, Any] = {}
        if existing.target is None and objective.target is not None:
            updates["target"] = objective.target
            updates["operator"] = objective.operator
        if existing.unit is None and objective.unit is not None:
            updates["unit"] = objective.unit
        if existing.priority is None and objective.priority is not None:
            updates["priority"] = objective.priority
        if updates:
            result[existing_index] = existing.model_copy(update=updates)
    return result


def parse_requirement_deterministically(
    user_message: str,
    *,
    context: Optional[dict[str, Any]] = None,
) -> MaterialRequirementSpec:
    """Normalize explicit properties and values without making model choices."""

    text = user_message.strip()
    composition = _extract_composition(text)
    structure = _extract_structure(text)
    formula = _extract_formula(text)
    supported_objectives = _extract_supported_objectives(text)
    unsupported_objectives = _extract_unsupported_objectives(text)
    task_type = _detect_task_type(
        text,
        formula=formula,
        supported_objectives=supported_objectives,
        unsupported_objectives=unsupported_objectives,
    )
    has_generation_subject = bool(
        formula
        or composition.chemical_system
        or composition.exact_formula
        or structure.space_group is not None
        or structure.crystal_system
    )
    if (
        task_type == "material_generation"
        and not supported_objectives
        and not unsupported_objectives
        and not has_generation_subject
    ):
        task_type = "clarification"
    input_material, substitutions = _extract_input_material(
        text,
        context=context,
    )
    if (
        task_type == "material_lookup"
        and input_material is not None
        and input_material.formula
        and composition.exact_formula is None
    ):
        composition.exact_formula = input_material.formula
    if task_type == "element_substitution" and input_material is not None:
        input_material.substitutions = substitutions

    candidate_count = _extract_candidate_count(text)
    assumptions: list[str] = []

    missing_information: list[str] = []
    if task_type == "clarification":
        missing_information.append("material_property_objective")
    if task_type in {"material_generation", "clarification"}:
        for objective in supported_objectives:
            if objective.target is None:
                missing_information.append(f"{objective.property}_target")
    if task_type == "element_substitution" and (
        input_material is None or input_material.formula is None
    ):
        missing_information.append("input_material")

    application = _extract_application(text)
    material_type = None
    if "合金" in text or "alloy" in text.lower():
        material_type = "alloy"
    elif application == "permanent_magnet":
        material_type = "permanent_magnet"

    return MaterialRequirementSpec(
        task_type=task_type,
        application=application,
        objectives=_deduplicate_objectives(
            [*supported_objectives, *unsupported_objectives]
        ),
        composition=composition,
        structure=structure,
        input_material=input_material,
        candidate_count=candidate_count,
        exploration_mode=_extract_exploration_mode(text),
        model_preferences=_extract_model_preferences(text),
        missing_information=_unique(missing_information),
        unsupported_requirements=_unique(
            [objective.property for objective in unsupported_objectives]
        ),
        assumptions=_unique(assumptions),
        material_type=material_type,
    )


def _merge_unique(left: Sequence[str], right: Sequence[str]) -> list[str]:
    return _unique([*left, *right])


def _merge_requirement_specs(
    deterministic: MaterialRequirementSpec,
    llm_spec: MaterialRequirementSpec,
    user_message: str,
) -> MaterialRequirementSpec:
    """Use deterministic values as precedence and let the LLM add semantics."""

    data = deterministic.model_dump(mode="python")
    if (
        deterministic.task_type == "science_chat"
        and llm_spec.task_type != "science_chat"
    ):
        data["task_type"] = llm_spec.task_type

    data["application"] = deterministic.application or llm_spec.application

    objectives = list(data["objectives"])
    existing_properties = {
        objective["property"] for objective in objectives
    }
    for objective in llm_spec.objectives:
        if objective.property in existing_properties:
            continue
        target = objective.target
        if (
            target is not None
            and not _explicit_target_present(user_message, objective.property)
        ):
            target = None
        objectives.append(
            objective.model_copy(update={"target": target}).model_dump(
                mode="python"
            )
        )
        existing_properties.add(objective.property)
    data["objectives"] = objectives

    deterministic_composition = deterministic.composition.model_dump()
    llm_composition = llm_spec.composition.model_dump()
    data["composition"] = {
        **deterministic_composition,
        **{
            key: value
            for key, value in llm_composition.items()
            if value not in (None, [], "")
        },
    }
    for field_name, value in data["composition"].items():
        data[field_name] = value

    if deterministic.structure.space_group is None:
        data["structure"]["space_group"] = llm_spec.structure.space_group
    if deterministic.structure.crystal_system is None:
        data["structure"]["crystal_system"] = (
            llm_spec.structure.crystal_system
        )
    if deterministic.input_material is None:
        data["input_material"] = (
            llm_spec.input_material.model_dump(mode="python")
            if llm_spec.input_material
            else None
        )

    if deterministic.candidate_count is not None:
        data["candidate_count"] = deterministic.candidate_count
    elif llm_spec.candidate_count is not None:
        data["candidate_count"] = llm_spec.candidate_count

    if (
        deterministic.exploration_mode == "multi_model"
        or llm_spec.exploration_mode == "multi_model"
    ):
        data["exploration_mode"] = "multi_model"
    data["model_preferences"] = _merge_unique(
        deterministic.model_preferences,
        llm_spec.model_preferences,
    )

    constraint_index = {
        constraint.constraint_type: constraint
        for constraint in deterministic.constraints
    }
    for constraint in llm_spec.constraints:
        constraint_index.setdefault(constraint.constraint_type, constraint)
    data["constraints"] = [
        constraint.model_dump(mode="python")
        for constraint in constraint_index.values()
    ]

    data["missing_information"] = _merge_unique(
        deterministic.missing_information,
        llm_spec.missing_information,
    )
    data["unsupported_requirements"] = _merge_unique(
        deterministic.unsupported_requirements,
        llm_spec.unsupported_requirements,
    )
    data["assumptions"] = _merge_unique(
        deterministic.assumptions,
        llm_spec.assumptions,
    )
    return MaterialRequirementSpec.model_validate(data)


def _finalize_requirement_spec(
    spec: MaterialRequirementSpec,
) -> MaterialRequirementSpec:
    """Apply non-scientific defaults after deterministic/LLM reconciliation."""

    data = spec.model_dump(mode="python")
    missing_information = list(spec.missing_information)
    assumptions = list(spec.assumptions)

    has_generation_subject = bool(
        spec.composition.chemical_system
        or spec.composition.exact_formula
        or spec.structure.space_group is not None
        or spec.structure.crystal_system
    )
    if (
        spec.task_type == "material_generation"
        and not spec.objectives
        and not has_generation_subject
    ):
        data["task_type"] = "clarification"

    if data["task_type"] == "material_generation":
        for objective in spec.objectives:
            if (
                objective.property in SUPPORTED_PROPERTY_ALIASES
                and objective.target is None
            ):
                missing_information.append(f"{objective.property}_target")

    if data["task_type"] == "clarification":
        if not spec.objectives:
            missing_information.append("material_property_objective")

    if data["task_type"] == "element_substitution" and (
        spec.input_material is None or spec.input_material.formula is None
    ):
        missing_information.append("input_material")

    data["missing_information"] = _unique(missing_information)
    data["assumptions"] = _unique(assumptions)
    return MaterialRequirementSpec.model_validate(data)


def _merge_revision_specs(
    previous: MaterialRequirementSpec,
    deterministic: MaterialRequirementSpec,
    llm_spec: MaterialRequirementSpec,
    revision_text: str,
) -> MaterialRequirementSpec:
    """Apply LLM semantics without overriding explicit deterministic edits."""

    data = deterministic.model_dump(mode="python")

    if deterministic.task_type == previous.task_type:
        data["task_type"] = previous.task_type

    if (
        deterministic.application == previous.application
        and llm_spec.application
        and llm_spec.application != previous.application
    ):
        data["application"] = llm_spec.application

    deterministic_objectives = {
        objective["property"]: objective
        for objective in data["objectives"]
    }
    has_removal_marker = any(
        marker in revision_text
        for marker in ("不要", "去掉", "删除", "移除", "取消")
    )
    if has_removal_marker and len(previous.objectives) == 1:
        previous_property = previous.objectives[0].property
        if all(
            objective.property != previous_property
            for objective in llm_spec.objectives
        ):
            deterministic_objectives.pop(previous_property, None)

    has_addition_marker = any(
        marker in revision_text
        for marker in ("增加", "新增", "添加", "同时", "并且", "还要")
    )
    for objective in llm_spec.objectives:
        if objective.property in deterministic_objectives:
            continue
        property_known = (
            objective.property in SUPPORTED_PROPERTY_ALIASES
            or objective.property in UNSUPPORTED_PROPERTY_ALIASES
        )
        target = objective.target
        revision_numbers = {
            float(value)
            for value in re.findall(r"\d+(?:\.\d+)?", revision_text)
        }
        target_is_explicit = (
            target is not None
            and any(
                abs(float(target) - number) < 1e-9
                for number in revision_numbers
            )
        )
        if target is not None and not target_is_explicit:
            target = None
        if property_known and (has_addition_marker or target_is_explicit):
            deterministic_objectives[objective.property] = (
                objective.model_copy(update={"target": target}).model_dump(
                    mode="python"
                )
            )
    data["objectives"] = list(deterministic_objectives.values())

    data["missing_information"] = _merge_unique(
        deterministic.missing_information,
        llm_spec.missing_information,
    )
    data["unsupported_requirements"] = _merge_unique(
        deterministic.unsupported_requirements,
        llm_spec.unsupported_requirements,
    )
    data["assumptions"] = _merge_unique(
        deterministic.assumptions,
        llm_spec.assumptions,
    )
    return _finalize_requirement_spec(
        MaterialRequirementSpec.model_validate(data)
    )


class RequirementParser:
    """Parse natural language into a validated MaterialRequirementSpec."""

    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        *,
        use_llm: bool = True,
    ):
        self._llm = llm
        self._structured_llm: Any = None
        self.use_llm = use_llm

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
                )
            self._structured_llm = llm.with_structured_output(
                MaterialRequirementSpec
            )
        return self._structured_llm

    def revise(
        self,
        requirement: MaterialRequirementSpec,
        instruction: str,
    ) -> MaterialRequirementSpec:
        """Apply explicit plan edits with deterministic precedence."""

        revision = parse_requirement_deterministically(instruction)
        explicit_task_change = revision.task_type in {
            "material_lookup",
            "element_substitution",
        } or (
            revision.task_type == "science_chat"
            and any(cue in instruction.lower() for cue in SCIENCE_CHAT_CUES)
        )
        if explicit_task_change:
            return _finalize_requirement_spec(revision)

        data = requirement.model_dump(mode="python")

        if revision.candidate_count is not None:
            data["candidate_count"] = revision.candidate_count

        removal_markers = ("不要", "去掉", "删除", "移除", "取消")
        removed_properties = {
            property_name
            for property_name, aliases in {
                **SUPPORTED_PROPERTY_ALIASES,
                **UNSUPPORTED_PROPERTY_ALIASES,
            }.items()
            if any(marker in instruction for marker in removal_markers)
            and any(alias in instruction for alias in aliases)
        }
        objectives = {
            objective["property"]: objective
            for objective in data["objectives"]
            if objective["property"] not in removed_properties
        }
        replacement_requested = any(
            marker in instruction for marker in ("改成", "换成", "改为")
        ) and not any(
            marker in instruction
            for marker in ("保留", "增加", "新增", "添加", "同时", "并且")
        )
        if replacement_requested and revision.objectives:
            objectives = {
                objective.property: objective.model_dump(mode="python")
                for objective in revision.objectives
            }
        elif (
            revision.unsupported_requirements
            and not any(
                objective.property in SUPPORTED_PROPERTY_ALIASES
                for objective in revision.objectives
            )
            and any(
                marker in instruction
                for marker in ("改成", "换成", "要求")
            )
        ):
            objectives = {
                objective.property: objective.model_dump(mode="python")
                for objective in revision.objectives
            }
        else:
            for objective in revision.objectives:
                if objective.property in removed_properties:
                    continue
                objective_data = objective.model_dump(mode="python")
                existing = objectives.get(objective.property)
                if (
                    existing
                    and objective_data.get("target") is None
                    and existing.get("target") is not None
                ):
                    objective_data["target"] = existing["target"]
                    objective_data["operator"] = existing["operator"]
                    objective_data["unit"] = existing.get("unit")
                objectives[objective.property] = objective_data

        if (
            revision.candidate_count is None
            and not revision.objectives
            and len(objectives) == 1
        ):
            number_match = re.search(
                r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)",
                instruction,
            )
            if number_match:
                property_name, objective = next(iter(objectives.items()))
                expected_unit = (
                    objective.get("unit")
                    or TARGET_UNITS.get(property_name)
                )
                residual = instruction
                for marker in (
                    "改成",
                    "改为",
                    "换成",
                    "大约",
                    "约",
                    "设为",
                    "调整为",
                ):
                    residual = residual.replace(marker, "")
                residual = residual.strip(" ，。,:：")
                allowed_pattern = rf"{re.escape(number_match.group(1))}"
                if expected_unit:
                    allowed_pattern += (
                        rf"(?:\s*{re.escape(str(expected_unit))})?"
                    )
                if re.fullmatch(allowed_pattern, residual, flags=re.IGNORECASE):
                    objective = dict(objective)
                    objective["target"] = float(number_match.group(1))
                    objective["unit"] = expected_unit
                    objectives[property_name] = objective

        stability_objective = objectives.get("energy_above_hull")
        if stability_objective and any(
            cue in instruction
            for cue in ("严格一点", "更严格", "再稳定一点", "更稳定")
        ):
            stability_objective = dict(stability_objective)
            stability_objective["target"] = None
            stability_objective["semantic_goal"] = "strict_stable"
            objectives["energy_above_hull"] = stability_objective
        elif stability_objective and any(
            cue in instruction
            for cue in ("宽松一点", "不用太严格")
        ):
            stability_objective = dict(stability_objective)
            stability_objective["target"] = None
            stability_objective["semantic_goal"] = "relaxed_stable"
            objectives["energy_above_hull"] = stability_objective
        data["objectives"] = list(objectives.values())

        composition = dict(data["composition"])
        revision_composition = revision.composition.model_dump()
        if revision_composition["chemical_system"]:
            composition.update(
                {
                    "chemical_system": revision_composition[
                        "chemical_system"
                    ],
                    "required_elements": revision_composition[
                        "required_elements"
                    ],
                    "allowed_elements": revision_composition[
                        "allowed_elements"
                    ],
                    "excluded_elements": revision_composition[
                        "excluded_elements"
                    ],
                }
            )
        else:
            for field_name in (
                "required_elements",
                "allowed_elements",
                "excluded_elements",
            ):
                composition[field_name] = _unique(
                    [
                        *composition.get(field_name, []),
                        *revision_composition.get(field_name, []),
                    ]
                )
            if revision_composition["allowed_elements"]:
                composition["chemical_system"] = "-".join(
                    composition["allowed_elements"]
                )
        for field_name in (
            "required_elements",
            "allowed_elements",
            "excluded_elements",
            "chemical_system",
        ):
            data[field_name] = composition[field_name]
        data["composition"] = composition

        for field_name in ("space_group", "crystal_system"):
            value = getattr(revision.structure, field_name)
            if value is not None:
                data["structure"][field_name] = value

        if revision.model_preferences:
            data["model_preferences"] = revision.model_preferences
        if revision.exploration_mode == "multi_model":
            data["exploration_mode"] = "multi_model"
        data["unsupported_requirements"] = _unique(
            [
                *data["unsupported_requirements"],
                *revision.unsupported_requirements,
            ]
        )
        data["assumptions"] = _unique(
            [*data["assumptions"], *revision.assumptions]
        )
        revised = MaterialRequirementSpec.model_validate(data)
        return _finalize_requirement_spec(revised)

    async def parse_revision(
        self,
        revision_text: str,
        previous_requirement: MaterialRequirementSpec,
        history: Optional[Sequence[dict[str, Any]]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> MaterialRequirementSpec:
        """Return a complete revised requirement, never a partial patch."""

        deterministic = self.revise(
            previous_requirement,
            revision_text,
        )
        if not self.use_llm:
            return deterministic

        messages: list[Any] = [
            SystemMessage(content=REVISION_PARSER_PROMPT),
            SystemMessage(
                content=(
                    "Previous MaterialRequirementSpec:\n"
                    f"{previous_requirement.model_dump_json(indent=2)}"
                )
            ),
        ]
        for item in (history or [])[-6:]:
            content = str(item.get("content", ""))
            if item.get("role") == "user":
                messages.append(HumanMessage(content=content))
            elif item.get("role") == "assistant":
                messages.append(AIMessage(content=content))
        if context:
            messages.append(
                SystemMessage(content=f"已知上下文：{context}")
            )
        messages.append(HumanMessage(content=revision_text))

        try:
            llm_spec = await asyncio.wait_for(
                self.structured_llm.ainvoke(messages),
                timeout=30,
            )
            return _merge_revision_specs(
                previous_requirement,
                deterministic,
                llm_spec,
                revision_text,
            )
        except Exception as exc:
            logger.warning(
                "Revision parser LLM call failed; using deterministic result: %s",
                exc,
            )
            return deterministic

    async def parse(
        self,
        user_message: str,
        history: Optional[Sequence[dict[str, Any]]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> MaterialRequirementSpec:
        """Parse one message; model capability checks happen in later phases."""

        deterministic = parse_requirement_deterministically(
            user_message,
            context=context,
        )
        if not self.use_llm:
            return _finalize_requirement_spec(deterministic)

        messages: list[Any] = [
            SystemMessage(content=REQUIREMENT_PARSER_PROMPT)
        ]
        for item in (history or [])[-8:]:
            content = str(item.get("content", ""))
            if item.get("role") == "user":
                messages.append(HumanMessage(content=content))
            elif item.get("role") == "assistant":
                messages.append(AIMessage(content=content))
        if context:
            messages.append(
                SystemMessage(content=f"已知上下文：{context}")
            )
        messages.append(HumanMessage(content=user_message))

        try:
            llm_spec = await asyncio.wait_for(
                self.structured_llm.ainvoke(messages),
                timeout=30,
            )
            return _finalize_requirement_spec(
                _merge_requirement_specs(
                    deterministic,
                    llm_spec,
                    user_message,
                )
            )
        except Exception as exc:
            logger.warning(
                "Requirement parser LLM call failed; using deterministic result: %s",
                exc,
            )
            return _finalize_requirement_spec(deterministic)
