# 材料结构检索沙盘 - LangChain Agent 版

## 架构重构说明

本项目已使用 **LangChain** 重构，从原有的 `Router → Workflow → Skills` 架构升级为 **LangChain Agent** 架构。

### 原架构 vs 新架构

| 原架构 | 新架构 (LangChain) |
|--------|-------------------|
| `router.py` - 意图分类器 | 由 Agent 自动判断意图 |
| `workflow.py` - 工作流调度 | 由 LangGraph ReAct Agent 处理 |
| `skills/*.py` - 技能实现 | `LangChain Tools` |

### 新架构优势

1. **更简洁**: 不再需要显式的 Router 分类，Agent 自动决定调用哪个工具
2. **更灵活**: 可以轻松添加新工具，Agent 会自动学习何时使用它们
3. **更符合 Agent 范式**: 使用 LangGraph 的 ReAct 模式，是学习 Agent 开发的好例子

## 文件结构

```
backend/
├── main.py              # FastAPI 入口
├── agent.py             # LangChain Agent 封装
├── skills/
│   ├── __init__.py
│   ├── chat.py          # ChatTool - 对话工具
│   └── material_search.py  # MaterialSearchTool - 材料搜索工具
├── pyproject.toml       # uv 包管理配置
├── .env                 # 环境变量 (API Keys)
└── test_agent.py        # 测试脚本
```

## 安装与运行

### 1. 安装 uv (如果未安装)

```bash
brew install uv
```

### 2. 安装依赖

```bash
cd backend
uv sync
```

### 3. 配置环境变量

在 `.env` 文件中配置：

```
DEEPSEEK_API_KEY=your_deepseek_api_key
MP_API_KEY=your_materials_project_api_key
```

### 4. 启动服务

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 测试 Agent

```bash
uv run python test_agent.py
```

## 依赖说明

```toml
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-community>=0.3.0",
    "langgraph>=0.2.0",
    "mp-api>=0.38.0",
    "pymatgen>=2023.0.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
]
```

## LangChain 核心概念

### 1. Tool (工具)

```python
from langchain_core.tools import BaseTool

class MaterialSearchTool(BaseTool):
    name = "material_search"
    description = "查询材料的晶体结构数据..."
    
    def _run(self, formula: str) -> str:
        # 实现工具逻辑
        pass
```

### 2. Agent (智能体)

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model=llm,
    tools=[MaterialSearchTool(), ChatTool()],
    prompt="你是一个材料科学助手..."
)
```

### 3. 执行

```python
result = await agent.ainvoke({"messages": [...]})
```

## 学习要点

1. **Tool 定义**: 如何将功能封装为 LLM 可调用的工具
2. **Agent 创建**: 使用 `create_react_agent` 快速构建 Agent
3. **消息传递**: LangChain 的消息格式 (`HumanMessage`, `AIMessage`, `ToolMessage`)
4. **工具调用**: LLM 自动决定何时调用哪个工具

## 常见问题

### Q: 为什么不继续使用原有的 Router 架构？

A: 原架构需要手动编写意图分类逻辑，而 LangChain Agent 可以自动学习何时调用工具，代码更简洁，也更容易扩展。

### Q: LangChain 会不会太重？

A: 对于只有 2 个工具的小项目，确实有些过度设计。但作为学习 Agent 的项目，LangChain 提供了标准的抽象和最佳实践。

### Q: 测试报错 "Insufficient Balance"

A: 这是 DeepSeek API 余额不足，需要充值或更换 API Key。代码逻辑是正确的。

## 参考资源

- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [Tool Calling Agent](https://langchain-ai.github.io/langgraph/how-tos/create-react-agent/)
