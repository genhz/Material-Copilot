"""
LangChain Agent 工作流 - 使用 ReAct Agent 进行意图识别和工具调用

架构说明：
- 使用 LangGraph 的 create_react_agent 创建 ReAct Agent
- Agent 根据用户消息自动决定调用哪个工具（chat 或 material_search）
- 不再需要显式的 Router 分类，Agent 自行判断意图
- LLM 配置从环境变量加载，支持多个提供商（DeepSeek、OpenAI 等）
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parent / "artifacts" / "matplotlib"),
)

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langgraph.prebuilt import create_react_agent

from skills.material_search import MaterialSearchTool, MaterialSearchResult
from skills.chat import ChatTool
from skills.element_substitution import ElementSubstitutionTool
from skills.material_generation import MaterialGenerationTool
from generation.manager import get_generation_manager
from generation.schemas import GenerationRequest
from intent.classifier import IntentClassifier
from config import get_llm_config

logger = logging.getLogger(__name__)

# Agent 系统提示词
AGENT_SYSTEM_PROMPT = """你是一个材料科学助手，拥有以下工具：

1. **material_search**: 查询具体材料的晶体结构数据。当用户要求查看某个化学式的晶体结构、或询问具体材料的物理性质时使用。
   - 例如："显示 Nd2Fe14B 的晶体结构"、"我想看看 Fe3O4 的结构"、"查询 LiCoO2 的数据"

2. **chat**: 与材料科学专家进行对话。用于回答概念性问题、材料推荐、趋势分析等不需要查询具体数据的讨论。
   - 例如："什么是带隙？"、"哪些材料适合做永磁体？"、"钕铁硼能用镧系元素替代吗？"

3. **element_substitution**: 替换晶体结构中的元素。当用户要求进行元素替代、掺杂、或修改化学式时使用。
   - 例如："把 Fe 替换成 Co"、"用 La 替代 Nd"、"将 Nd2Fe14B 中的 Fe 全部替换为 Co"
   - 需要提供当前材料的 CIF 文件和替换规则，返回替换后的新结构和化学式

4. **material_generation**: 根据目标磁密度生成新的无机材料候选结构。
   - 例如："生成磁密度约 0.15 的磁性材料"、"设计两个高磁密度候选材料"
   - 用户不需要知道 MatterGen；只要用户想发现、设计、探索或寻找新的材料候选，就应使用该工具
   - 该工具只创建后台任务并返回 job_id，不会等待生成完成
   - 不用于预测已有材料的磁密度

请根据用户的问题自动选择合适的工具。如果用户的问题涉及具体材料的结构数据，使用 material_search；如果是概念性讨论或材料推荐，使用 chat；如果需要修改已有材料元素组成，使用 element_substitution；如果用户要求生成或设计新的磁性材料候选，使用 material_generation。

始终使用中文回复用户。"""


class MaterialAgent:
    """材料科学 Agent - 封装 LangChain Agent 的执行逻辑"""

    def __init__(self):
        self._llm: Optional[ChatOpenAI] = None
        self._agent = None
        self._tools = None
        self._intent_classifier: Optional[IntentClassifier] = None

    @property
    def llm(self) -> ChatOpenAI:
        """懒加载 LLM 客户端"""
        if self._llm is None:
            # 从配置加载 LLM 设置
            config = get_llm_config()

            self._llm = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.1,  # 低温度确保工具调用一致性
            )
        return self._llm

    @property
    def tools(self) -> list:
        """懒加载工具列表"""
        if self._tools is None:
            self._tools = [
                MaterialSearchTool(),
                ChatTool(),
                ElementSubstitutionTool(),
                MaterialGenerationTool(),
            ]
        return self._tools

    @property
    def intent_classifier(self) -> IntentClassifier:
        if self._intent_classifier is None:
            self._intent_classifier = IntentClassifier(self.llm)
        return self._intent_classifier

    @property
    def agent(self):
        """懒加载 Agent"""
        if self._agent is None:
            # 使用 LangGraph 创建 ReAct Agent
            self._agent = create_react_agent(
                model=self.llm,
                tools=self.tools,
                prompt=AGENT_SYSTEM_PROMPT,
            )
        return self._agent

    async def invoke(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> "AgentResult":
        """
        调用 Agent 处理用户消息

        Args:
            message: 用户消息
            history: 对话历史

        Returns:
            AgentResult: Agent 执行结果
        """
        try:
            decision = await self.intent_classifier.classify(message, history)
        except Exception as exc:
            logger.warning("Intent routing skipped: %s", exc)
            decision = None

        if decision is not None:
            logger.info(
                "[Intent] intent=%s confidence=%.2f clarification=%s",
                decision.intent,
                decision.confidence,
                decision.needs_clarification,
            )

        if (
            decision
            and decision.intent == "material_generation"
            and decision.confidence >= 0.75
        ):
            return await self._start_generation(message, decision)

        if decision and (
            decision.intent == "clarification" or decision.needs_clarification
        ):
            return AgentResult(
                reply=(
                    decision.clarification_question
                    or "请再说明你希望寻找的材料目标，我可以继续为你设计候选。"
                ),
                action="chat",
                material_data=None,
                job_id=None,
            )

        # 构建消息历史
        messages = []

        # 添加历史消息
        if history:
            for msg in history[-10:]:  # 最多携带最近 10 条
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # 添加当前消息
        messages.append(HumanMessage(content=message))

        try:
            # 执行 Agent
            result = await self.agent.ainvoke({
                "messages": messages,
            })

            # 提取最后的消息作为回复
            output_messages = result.get("messages", [])
            output = ""
            material_data = None
            job_id = None
            action = "chat"

            # 遍历消息，提取工具调用结果和最终回复
            for msg in output_messages:
                msg_type = getattr(msg, "type", "")

                if msg_type == "tool":
                    # 工具调用结果
                    content = getattr(msg, "content", "")
                    name = getattr(msg, "name", "")

                    if name == "material_search":
                        action = "render"
                        try:
                            output_data = json.loads(content)
                            material_data = MaterialSearchResult(**output_data)
                        except Exception as e:
                            logger.warning(f"解析材料数据失败：{e}")

                    elif name == "element_substitution":
                        action = "render"
                        try:
                            output_data = json.loads(content)
                            material_data = MaterialSearchResult(**output_data)
                        except Exception as e:
                            logger.warning(f"解析元素替换结果失败：{e}")

                    elif name == "material_generation":
                        try:
                            output_data = json.loads(content)
                            if output_data.get("job_id"):
                                action = "generate"
                                job_id = output_data["job_id"]
                        except Exception as e:
                            logger.warning(f"解析材料生成结果失败：{e}")

                elif msg_type == "ai":
                    # AI 回复
                    output = getattr(msg, "content", output)

            # 如果没有提取到 AI 回复，尝试从其他格式获取
            if not output and isinstance(result, dict):
                output = result.get("output", "")

            # 如果还是没有，尝试直接获取 messages 的最后一条内容
            if not output and output_messages:
                last_msg = output_messages[-1]
                output = getattr(last_msg, "content", str(last_msg))

            logger.info(f"[Agent] 执行完成：action={action}, material={material_data.formula if material_data else 'N/A'}")

            return AgentResult(
                reply=output,
                action=action,
                material_data=material_data,
                job_id=job_id,
            )

        except Exception as e:
            logger.exception(f"[Agent] 执行失败：{e}")
            return AgentResult(
                reply=f"处理请求时发生错误：{str(e)}",
                action="chat",
                material_data=None,
                job_id=None,
            )

    async def _start_generation(self, message: str, decision) -> "AgentResult":
        manager = get_generation_manager()
        await manager.startup()
        request = GenerationRequest(
            target_magnetic_density=decision.target_magnetic_density or 0.15,
            num_candidates=decision.num_candidates or 2,
            guidance_scale=decision.guidance_scale or 2.0,
            seed=decision.seed,
        )

        try:
            job = await manager.submit(request)
        except Exception as exc:
            logger.exception("Unable to start material generation")
            return AgentResult(
                reply=f"暂时无法创建材料生成任务：{exc}",
                action="chat",
                material_data=None,
                job_id=None,
            )

        return AgentResult(
            reply=(
                f"已开始设计 {request.num_candidates} 个磁性材料候选，"
                f"目标磁密度为 {request.target_magnetic_density} Å⁻³。"
                "生成过程会在候选面板中实时显示。"
            ),
            action="generate",
            material_data=None,
            job_id=job.job_id,
        )


class AgentResult:
    """Agent 执行结果"""

    def __init__(
        self,
        reply: str,
        action: str,  # "chat" | "render" | "generate"
        material_data=None,
        job_id: Optional[str] = None,
    ):
        self.reply = reply
        self.action = action
        self.material_data = material_data
        self.job_id = job_id

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "reply": self.reply,
            "action": self.action,
            "material_data": self.material_data.to_dict() if self.material_data else None,
            "job_id": self.job_id,
        }


# 全局 Agent 实例（懒加载）
_agent: Optional[MaterialAgent] = None


def get_agent() -> MaterialAgent:
    """获取全局 Agent 实例"""
    global _agent
    if _agent is None:
        _agent = MaterialAgent()
    return _agent


async def execute_agent(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> AgentResult:
    """
    执行 Agent 处理用户消息

    这是主入口函数，被 main.py 调用。

    Args:
        message: 用户消息
        history: 对话历史

    Returns:
        AgentResult: Agent 执行结果
    """
    agent = get_agent()
    return await agent.invoke(message, history)
