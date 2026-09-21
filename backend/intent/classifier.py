"""Classify user intent without requiring MatterGen-specific vocabulary."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional, Sequence

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from intent.schemas import IntentDecision


logger = logging.getLogger(__name__)


CLASSIFIER_SYSTEM_PROMPT = """你是材料科学应用的意图分类器。

用户通常不知道 MatterGen 等内部模型名称，因此不能要求用户说出 MatterGen。
请根据用户真正想完成的任务进行分类：

1. material_generation:
   用户希望发现、设计、生成、探索、推荐或寻找新的材料候选结构。
   例如：
   - 帮我设计几种新的磁性材料
   - 给我一些还没被材料库收录的候选结构
   - 想找高磁化强度材料，给我几个方案
   - 不用查已有材料，帮我探索新材料

2. material_lookup:
   用户查询已知的化学式、已有晶体结构或 Materials Project 数据。
   例如：查看 Nd2Fe14B 结构、Fe3O4 的带隙是多少。

3. element_substitution:
   用户要求对已有结构做元素替换、掺杂或改变化学式。
   例如：把 Fe 换成 Co、用 La 替代 Nd。

4. science_chat:
   概念解释、原理讨论、泛泛推荐或不要求立即执行具体材料操作。
   例如：什么是带隙、为什么永磁材料会退磁。

5. clarification:
   请求存在关键歧义，无法安全决定操作。

分类规则：
- 不要把“生成能”误判为 material_generation。
- 已有化学式加“结构/数据/性质”通常是 material_lookup。
- 用户未提及 MatterGen 不影响 material_generation 判定。
- 只要明确表示要探索或设计新的材料候选，就使用 material_generation。
- 目标磁密度未给时默认 0.15，候选数量默认 2，引导系数默认 2.0。
- “高磁密度”可映射为 0.2。
- 低稀土成本、HHI 或供应风险目前不能由 dft_mag_density 模型严格保证；
  如果用户只要求这些复杂约束，设置 needs_clarification=true。
"""


GENERATION_CUES = (
    "设计",
    "探索",
    "候选",
    "新材料",
    "新型材料",
    "尚未",
    "还没被",
    "未被收录",
    "几个可能",
    "几个方案",
    "找几种",
    "找一些",
)
LOOKUP_CUES = (
    "查询",
    "查看",
    "看看",
    "结构",
    "数据",
    "带隙是多少",
    "磁密度是多少",
    "材料 id",
)
SUBSTITUTION_CUES = ("替换", "替代", "掺杂", "换成", "改为")
FORMULA_PATTERN = re.compile(r"\b[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)+\b")


def _heuristic_decision(message: str) -> Optional[IntentDecision]:
    """Handle high-confidence routes without an LLM call."""

    normalized = message.strip()
    has_formula = bool(FORMULA_PATTERN.search(normalized))

    if any(cue in normalized for cue in SUBSTITUTION_CUES):
        return IntentDecision(
            intent="element_substitution",
            confidence=0.92,
        )

    if has_formula and any(cue in normalized for cue in LOOKUP_CUES):
        return IntentDecision(
            intent="material_lookup",
            confidence=0.9,
        )

    generation_requested = (
        "生成能" not in normalized
        and (
            any(cue in normalized for cue in GENERATION_CUES)
            or ("生成" in normalized and not has_formula)
            or "找新材料" in normalized
        )
    )
    if generation_requested:
        target_density = 0.2 if "高磁" in normalized else 0.15
        count_match = re.search(r"(\d+)\s*(?:个|种)", normalized)
        count = int(count_match.group(1)) if count_match else 2
        count = max(1, min(count, 16))

        needs_clarification = (
            "低稀土" in normalized
            or "供应风险" in normalized
            or "hhi" in normalized.lower()
        )
        question = None
        if needs_clarification:
            question = (
                "当前模型可以优化磁密度，但不能严格保证低稀土成本或供应风险。"
                "是否先按高磁密度生成 2 个候选？"
            )

        return IntentDecision(
            intent="clarification" if needs_clarification else "material_generation",
            confidence=0.88,
            needs_clarification=needs_clarification,
            clarification_question=question,
            target_magnetic_density=target_density,
            num_candidates=count,
            guidance_scale=2.0,
        )

    return None


class IntentClassifier:
    """Use deterministic guards first, then LLM structured classification."""

    def __init__(self, llm: ChatOpenAI):
        self._llm = llm
        self._structured_llm = llm.with_structured_output(IntentDecision)

    async def classify(
        self,
        message: str,
        history: Optional[Sequence[dict]] = None,
    ) -> Optional[IntentDecision]:
        heuristic = _heuristic_decision(message)
        if heuristic is not None:
            return heuristic

        messages = [SystemMessage(content=CLASSIFIER_SYSTEM_PROMPT)]
        for item in (history or [])[-6:]:
            if item.get("role") == "user":
                messages.append(HumanMessage(content=item.get("content", "")))
            elif item.get("role") == "assistant":
                messages.append(AIMessage(content=item.get("content", "")))
        messages.append(HumanMessage(content=message))

        try:
            decision = await asyncio.wait_for(
                self._structured_llm.ainvoke(messages),
                timeout=20,
            )
            return decision
        except Exception as exc:
            logger.warning("Intent classification failed: %s", exc)
            return None
