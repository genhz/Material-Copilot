"""
LangChain Agent 工作流 - 使用 ReAct Agent 进行意图识别和工具调用

架构说明：
- 使用 LangGraph 的 create_react_agent 创建 ReAct Agent
- Agent 根据用户消息自动决定调用哪个工具（chat 或 material_search）
- 不再需要显式的 Router 分类，Agent 自行判断意图
"""
import os
import logging
from typing import Optional, List, Dict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langgraph.prebuilt import create_react_agent

from skills.material_search import MaterialSearchTool, MaterialSearchResult
from skills.chat import ChatTool

logger = logging.getLogger(__name__)

# Agent 系统提示词
AGENT_SYSTEM_PROMPT = """你是一个材料科学助手，拥有以下工具：

1. **material_search**: 查询具体材料的晶体结构数据。当用户要求查看某个化学式的晶体结构、或询问具体材料的物理性质时使用。
   - 例如："显示 Nd2Fe14B 的晶体结构"、"我想看看 Fe3O4 的结构"、"查询 LiCoO2 的数据"

2. **chat**: 与材料科学专家进行对话。用于回答概念性问题、材料推荐、趋势分析等不需要查询具体数据的讨论。
   - 例如："什么是带隙？"、"哪些材料适合做永磁体？"、"钕铁硼能用镧系元素替代吗？"

请根据用户的问题自动选择合适的工具。如果用户的问题涉及具体材料的结构数据，使用 material_search；如果是概念性讨论或材料推荐，使用 chat。

始终使用中文回复用户。"""


class MaterialAgent:
    """材料科学 Agent - 封装 LangChain Agent 的执行逻辑"""

    def __init__(self):
        self._llm: Optional[ChatOpenAI] = None
        self._agent = None
        self._tools = None

    @property
    def llm(self) -> ChatOpenAI:
        """懒加载 LLM 客户端"""
        if self._llm is None:
            api_key = os.getenv("DEEPSEEK_API_KEY", "")
            base_url = "https://api.deepseek.com"

            self._llm = ChatOpenAI(
                model="deepseek-chat",
                api_key=api_key,
                base_url=base_url,
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
            ]
        return self._tools

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
            action = "chat"

            # 遍历消息，提取工具调用结果和最终回复
            for msg in output_messages:
                msg_type = getattr(msg, "type", "")

                if msg_type == "tool_message":
                    # 工具调用结果
                    tool_call = getattr(msg, "tool_call_id", None)
                    content = getattr(msg, "content", "")
                    name = getattr(msg, "name", "")

                    if name == "material_search":
                        action = "render"
                        try:
                            import json
                            output_data = json.loads(content)
                            material_data = MaterialSearchResult(**output_data)
                        except Exception as e:
                            logger.warning(f"解析材料数据失败：{e}")

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
            )

        except Exception as e:
            logger.exception(f"[Agent] 执行失败：{e}")
            return AgentResult(
                reply=f"处理请求时发生错误：{str(e)}",
                action="chat",
                material_data=None,
            )


class AgentResult:
    """Agent 执行结果"""

    def __init__(
        self,
        reply: str,
        action: str,  # "chat" 或 "render"
        material_data=None,
    ):
        self.reply = reply
        self.action = action
        self.material_data = material_data

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "reply": self.reply,
            "action": self.action,
            "material_data": self.material_data.to_dict() if self.material_data else None,
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
