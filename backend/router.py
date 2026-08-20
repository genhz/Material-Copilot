"""
意图路由器 — 使用 DeepSeek 快速分类用户意图
"""
import os
import json
import logging
from typing import Literal, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# DeepSeek 客户端（懒加载）
_deepseek_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _deepseek_client
    if _deepseek_client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        _deepseek_client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
    return _deepseek_client


# 意图分类枚举
IntentType = Literal["CHAT", "RENDER_3D"]


class IntentResult:
    """意图分类结果"""

    def __init__(self, intent: IntentType, formula: str | None = None):
        self.intent = intent
        self.formula = formula

    def __repr__(self):
        if self.formula:
            return f"IntentResult(intent='{self.intent}', formula='{self.formula}')"
        return f"IntentResult(intent='{self.intent}')"


# 意图分类提示词
ROUTER_SYSTEM_PROMPT = """你是一个意图分类器。分析用户的消息，判断其意图属于以下两类之一：

1. **CHAT**（闲聊/探讨/推荐）：用户只是在询问概念、寻求建议、讨论话题，不需要查看具体材料的晶体结构。
   - 例如："什么是带隙？"、"哪些材料适合做永磁体？"、"钕铁硼能用镧系元素替代吗？"

2. **RENDER_3D**（渲染晶体结构）：用户明确要求查看某个具体化学式的晶体结构。
   - 例如："显示 Nd2Fe14B 的晶体结构"、"我想看看 Fe3O4 的结构"
   - 即使用户只输入了一个化学式（如 "Nd2Fe14B"），也视为 RENDER_3D

请严格按照以下 JSON 格式回复，不要包含任何其他内容：
{"intent": "CHAT" | "RENDER_3D", "formula": "化学式或 null"}

如果意图是 CHAT，formula 字段必须为 null。
如果意图是 RENDER_3D，formula 字段必须提取出化学式（如 "Nd2Fe14B"）。"""


async def classify_intent(message: str) -> IntentResult:
    """
    对用户消息进行意图分类

    Args:
        message: 用户输入的消息

    Returns:
        IntentResult: 意图分类结果
    """
    client = _get_client()

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.1,  # 低温度确保分类一致性
            max_tokens=100,
        )

        content = response.choices[0].message.content or ""
        # 清理可能存在的 markdown 代码块
        content = content.strip().strip("```json").strip("```").strip()

        logger.info(f"[Router] 原始分类结果：{content}")

        parsed = json.loads(content)
        intent = parsed.get("intent", "CHAT")
        formula = parsed.get("formula")

        # 验证意图类型
        if intent not in ("CHAT", "RENDER_3D"):
            logger.warning(f"[Router] 无效意图：{intent}，默认使用 CHAT")
            intent = "CHAT"

        result = IntentResult(intent=intent, formula=formula)
        logger.info(f"[Router] 分类结果：{result}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[Router] JSON 解析失败：{e}，原始内容：{content}")
        # 降级：默认 CHAT
        return IntentResult(intent="CHAT")

    except Exception as e:
        logger.error(f"[Router] 分类失败：{e}，降级为 CHAT")
        return IntentResult(intent="CHAT")
