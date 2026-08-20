"""
工作流调度器 — 根据 Router 意图分类结果执行对应分支
"""
import os
import json
import logging
from typing import Optional, Dict

from openai import AsyncOpenAI
from skills.material_search import search_material, MaterialSearchResult
from skills.chat import chat as chat_skill
from router import classify_intent, IntentResult

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

# 材料数据总结提示词
SUMMARY_SYSTEM_PROMPT = (
    "你是一个材料科学分析助手。用户查询了一个具体材料，"
    "现在你需要根据以下数据生成一段简洁专业的中文总结。"
    "总结应包含：化学式、晶体结构信息、带隙特性、磁性、形成能等关键数据。"
    "使用 Markdown 格式，重点数据加粗显示。"
)


class WorkflowResult:
    """工作流执行结果"""

    def __init__(
        self,
        reply: str,
        action: str,  # "chat" 或 "render"
        material_data: Optional[MaterialSearchResult] = None,
    ):
        self.reply = reply
        self.action = action
        self.material_data = material_data

    def to_dict(self) -> dict:
        """转换为 API 响应格式"""
        return {
            "reply": self.reply,
            "action": self.action,
            "material_data": self.material_data.to_dict() if self.material_data else None,
        }


async def execute_workflow(
    message: str,
    history: Optional[list[Dict[str, str]]] = None,
) -> WorkflowResult:
    """
    执行工作流调度

    1. Router 意图分类
    2. 根据意图执行对应分支：
       - CHAT: 调用 chat skill，返回纯文本
       - RENDER_3D: 调用 material_search skill，再让 LLM 生成总结

    Args:
        message: 用户消息
        history: 对话历史

    Returns:
        WorkflowResult: 工作流结果
    """
    # ── 第 1 步：意图分类 ──
    intent = await classify_intent(message)
    logger.info(f"[Workflow] 意图分类：{intent.intent}")

    # ── 第 2 步：分支执行 ──
    if intent.intent == "CHAT":
        return await _branch_chat(message, history)
    else:
        return await _branch_render_3d(intent, message, history)


async def _branch_chat(
    message: str,
    history: Optional[list[Dict[str, str]]] = None,
) -> WorkflowResult:
    """
    分支 A：纯文本对话
    """
    logger.info("[Workflow] 执行 CHAT 分支")
    reply = await chat_skill(message=message, history=history)
    return WorkflowResult(reply=reply, action="chat")


async def _branch_render_3d(
    intent: "IntentResult",
    message: str,
    history: Optional[list[Dict[str, str]]] = None,
) -> WorkflowResult:
    """
    分支 B：渲染 3D 晶体结构
    """
    formula = intent.formula
    if not formula:
        # 如果 Router 没有提取出化学式，尝试从消息中提取
        formula = _extract_formula_from_message(message)

    if not formula:
        # 无法提取化学式，降级为 CHAT
        logger.warning("[Workflow] 无法提取化学式，降级为 CHAT 分支")
        reply = await chat_skill(message=message, history=history)
        return WorkflowResult(reply=reply, action="chat")

    logger.info(f"[Workflow] 执行 RENDER_3D 分支，化学式：{formula}")

    try:
        # 调用材料搜索技能
        material_data = search_material(formula)

        # 让 LLM 生成总结
        summary = await _generate_summary(material_data)

        return WorkflowResult(
            reply=summary,
            action="render",
            material_data=material_data,
        )

    except ValueError as ve:
        logger.warning(f"[Workflow] 材料查询失败：{ve}")
        return WorkflowResult(
            reply=f"抱歉，未找到化学式为 '{formula}' 的材料数据。请检查化学式是否正确。",
            action="chat",
        )
    except RuntimeError as re:
        logger.error(f"[Workflow] 配置错误：{re}")
        return WorkflowResult(
            reply=f"服务器配置错误：{re}",
            action="chat",
        )
    except Exception as e:
        logger.exception(f"[Workflow] 未知错误：{e}")
        return WorkflowResult(
            reply=f"查询时发生错误：{str(e)}",
            action="chat",
        )


async def _generate_summary(material_data: MaterialSearchResult) -> str:
    """
    让 LLM 根据材料数据生成一段总结
    """
    # 转换 crystal_system 为字符串（避免 CrystalSystem 枚举序列化问题）
    crystal_system = str(material_data.crystal_system) if material_data.crystal_system else None

    data_json = json.dumps(
        {
            "formula": material_data.formula,
            "material_id": material_data.material_id,
            "band_gap": material_data.band_gap,
            "is_magnetic": material_data.is_magnetic,
            "formation_energy": material_data.formation_energy,
            "density": material_data.density,
            "spacegroup_symbol": material_data.spacegroup_symbol,
            "spacegroup_number": material_data.spacegroup_number,
            "crystal_system": crystal_system,
            "elements": material_data.elements,
            "pretty_formula": material_data.pretty_formula,
        },
        ensure_ascii=False,
    )

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"以下是查询到的材料数据，请生成一段简洁专业的中文总结：\n\n{data_json}",
                },
            ],
            temperature=0.5,
            max_tokens=500,
        )

        summary = response.choices[0].message.content or "数据查询成功，但无法生成总结。"
        logger.info(f"[Workflow] 总结生成成功 (长度：{len(summary)})")
        return summary

    except Exception as e:
        logger.error(f"[Workflow] 总结生成失败：{e}")
        return (
            f"已查询到 **{material_data.formula}** 的数据："
            f"带隙 {material_data.band_gap} eV，"
            f"磁性 {'是' if material_data.is_magnetic else '否'}，"
            f"生成能 {material_data.formation_energy} eV/atom。"
        )


def _extract_formula_from_message(message: str) -> Optional[str]:
    """
    从消息中提取化学式（简单启发式方法）
    """
    import re

    # 匹配常见化学式模式：如 Nd2Fe14B, Fe3O4, LiCoO2
    pattern = r'[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*){1,5}'
    matches = re.findall(pattern, message)

    if matches:
        # 取最长的匹配（通常是完整的化学式）
        formula = max(matches, key=len)
        if len(formula) >= 3:  # 至少 3 个字符
            return formula

    return None
