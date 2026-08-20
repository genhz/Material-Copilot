"""
聊天技能 — 处理纯文本对话和材料科学问答
"""
import os
from typing import List, Dict, Optional

from openai import AsyncOpenAI

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


# 系统提示词
CHAT_SYSTEM_PROMPT = (
    "你是一个专业的材料信息学助手，专注于材料科学领域的知识问答。"
    "你具备以下能力：\n\n"
    "1. **材料科学概念解释**：带隙、磁性、形成能、晶体结构等概念的通俗解释\n"
    "2. **材料推荐与建议**：根据应用场景推荐合适的材料\n"
    "3. **趋势分析**：元素替代、性能对比、材料选择建议\n"
    "4. **通用问答**：回答材料科学相关的基础问题\n\n"
    "回答规则：\n"
    "- 使用简洁、专业的中文回答\n"
    "- 必要时使用类比帮助理解\n"
    "- 如果用户询问具体材料的结构数据，建议他们使用搜索功能\n"
    "- 回答要重点突出关键信息，保持结构化"
)


async def chat(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    context: Optional[str] = None,
) -> str:
    """
    处理纯文本对话

    Args:
        message: 用户当前消息
        history: 历史对话记录 (可选)
        context: 上下文信息 (可选)

    Returns:
        str: AI 生成的回复
    """
    client = _get_client()
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
    ]

    # 添加历史消息
    if history:
        messages.extend(history[-10:])  # 最多携带最近 10 条消息

    # 添加上下文
    if context:
        messages.append(
            {"role": "system", "content": f"当前讨论的上下文：{context}"}
        )

    # 添加当前消息
    messages.append({"role": "user", "content": message})

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
        )

        reply = response.choices[0].message.content or "抱歉，我没有理解你的问题。"
        print(f"[Skill:chat] 回复生成成功 (长度：{len(reply)})")
        return reply

    except Exception as e:
        print(f"[Skill:chat] 错误：{e}")
        return f"抱歉，处理你的问题时遇到了错误：{str(e)}"
