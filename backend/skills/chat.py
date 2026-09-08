"""
聊天工具 - 基于 LangChain Tool 接口封装对话能力
"""
from typing import Type, Optional, List, Dict
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from config import get_llm_config


class ChatInput(BaseModel):
    """聊天工具的输入模型"""
    message: str = Field(..., description="用户要询问的问题或消息内容")


class ChatTool(BaseTool):
    """
    聊天工具 - 处理材料科学领域的问答和讨论

    当用户询问概念、寻求建议、讨论话题、或需要材料推荐时使用。
    适合回答"什么是带隙？"、"哪些材料适合做永磁体？"等问题。
    """
    name: str = "chat"
    description: str = (
        "与材料科学专家进行对话。"
        "用于回答概念性问题、材料推荐、趋势分析、以及不需要查询具体材料数据的讨论。"
        "例如：'什么是带隙？'、'哪些材料适合做永磁体？'、'钕铁硼能用镧系元素替代吗？'"
    )
    args_schema: Type[BaseModel] = ChatInput

    # 系统提示词
    SYSTEM_PROMPT: str = (
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: Optional[ChatOpenAI] = None

    @property
    def client(self) -> ChatOpenAI:
        """懒加载 ChatOpenAI 客户端"""
        if self._client is None:
            # 从配置加载 LLM 设置
            config = get_llm_config()

            self._client = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.7,
                max_tokens=1000,
            )
        return self._client

    def _run(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
    ) -> str:
        """
        同步执行聊天回复

        Args:
            message: 用户当前消息
            history: 历史对话记录 (可选)
            context: 上下文信息 (可选)

        Returns:
            str: AI 生成的回复
        """
        return self._chat(message, history, context)

    async def _arun(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
    ) -> str:
        """异步执行聊天回复"""
        return self._chat(message, history, context)

    def _chat(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
    ) -> str:
        """执行聊天对话"""
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
        ]

        # 添加历史消息
        if history:
            for msg in history[-10:]:  # 最多携带最近 10 条消息
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # 添加上下文
        if context:
            messages.append(
                SystemMessage(content=f"当前讨论的上下文：{context}")
            )

        # 添加当前消息
        messages.append(HumanMessage(content=message))

        try:
            response = self.client.invoke(messages)
            reply = response.content or "抱歉，我没有理解你的问题。"
            print(f"[ChatTool] 回复生成成功 (长度：{len(reply)})")
            return reply

        except Exception as e:
            print(f"[ChatTool] 错误：{e}")
            return f"抱歉，处理你的问题时遇到了错误：{str(e)}"
