# 后端文档 - Reasoning Agent 架构

## 架构说明

主聊天链路使用 `agent_runtime` 中的 Reasoning Agent：

```text
User
  ↓
Thought → Action → Observation → Reflection
  ↓
ExecutionPlan
  ↓
用户确认
  ↓
现有 Workflow State Machine / GenerationManager / MatterGen Worker
```

LLM 每轮只返回结构化 JSON：

```json
{
  "thought": "分析用户需求",
  "action": "choose_tool",
  "arguments": {},
  "confidence": 0.9
}
```

### 原架构 vs 新架构

| 原架构 | 新架构 |
|--------|-------------------|
| `IntentClassifier` 作为主入口 | `ReActAgent` 根据 Thought/Observation 选择工具 |
| `RequirementParser.extract_semantics` | LLM 推理 + `AgentToolExecutor` |
| 大量 `if/elif` 模型选择 | `ToolRegistry` 动态匹配能力 |
| Planner 内硬编码 `model_id` | 按能力覆盖和运行可用性选择工具 |
| 缺参直接 clarification | 生成带 `ask` 步骤和参数建议的 `ExecutionPlan` |

### 新架构优势

1. **可观察**: Thought、Action、Observation、Reflection 都保留在 trace 中
2. **可修订**: Agent Memory 保存体系、确认参数、历史目标和历史工具选择
3. **可扩展**: 新能力进入 `CapabilityRegistry` 后自动出现在 `ToolRegistry`
4. **安全执行**: Agent 只生成 `ExecutionPlan`，成本高的生成仍由用户确认后执行

## 文件结构

```
backend/
├── .venv/               # Python 3.10 统一环境
├── main.py              # FastAPI 入口
├── agent.py             # LangChain Agent 封装
├── agent_runtime/
│   ├── react_agent.py   # Thought/Action/Observation/Reflection 循环
│   ├── memory.py        # 体系、参数、目标、工具选择记忆
│   ├── tool_registry.py # capability、输入、建议值、运行可用性
│   ├── planner.py       # 能力驱动 ExecutionPlan
│   ├── executor.py      # planning-time tool call
│   └── reflection.py    # reflection / replan
├── config.py            # LLM 配置管理
├── skills/
│   ├── __init__.py
│   ├── chat.py          # ChatTool - 对话工具
│   ├── material_search.py  # MaterialSearchTool - 材料搜索
│   ├── element_substitution.py  # ElementSubstitutionTool - 元素替换
│   └── material_generation.py  # MaterialGenerationTool - 材料生成
├── generation/
│   ├── adapter.py       # MatterGen 调用封装
│   ├── manager.py       # 任务管理
│   ├── worker.py        # 独立推理进程
│   ├── evaluator.py     # CIF 后处理
│   ├── store.py         # 文件任务存储
│   └── router.py        # 生成 API
├── vendor/
│   └── mattergen/       # MatterGen 源码、配置和本地权重
├── pyproject.toml       # 依赖配置
├── .env                 # 环境变量 (API Keys)
└── tests/               # 测试
```

## 安装与运行

### 1. 安装依赖

```bash
cd backend
uv sync
```

不要执行 `uv sync --reinstall`。MatterGen 源码位于 `backend/vendor/mattergen/`，MatterGen、PyTorch、PyG 和 MatterSim 已经安装在 `backend/.venv`。

### 2. 配置 LLM

编辑 `.env` 文件，修改以下三个值来切换 LLM 提供商：

```bash
# DeepSeek
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# OpenAI
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# SiliconFlow
LLM_API_KEY=xxxxxxxx
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3
```

### 3. 配置 Materials Project

```bash
MP_API_KEY=xxxxxxxx
```

### 4. 启动服务

```bash
.venv/bin/python -m uvicorn main:app \
  --reload --host 0.0.0.0 --port 8000
```

### 5. 测试 Agent

```bash
.venv/bin/python -m pytest
```

## LLM 配置管理

### config.py

使用统一的环境变量名，直接修改 `.env` 中的值来切换提供商：

```python
from config import get_llm_config

config = get_llm_config()
print(f"Model: {config.model}")      # e.g. "deepseek-chat"
print(f"Base URL: {config.base_url}") # e.g. "https://api.deepseek.com"
print(f"API Key: {config.api_key}")   # e.g. "sk-..."
```

### 环境变量

| 变量名 | 说明 |
|--------|------|
| `LLM_API_KEY` | LLM API 密钥 |
| `LLM_BASE_URL` | LLM API 基础 URL |
| `LLM_MODEL` | 模型名称 |
| `MP_API_KEY` | Materials Project API 密钥 |
| `MATTERGEN_ENABLED` | 是否启用 MatterGen 生成功能 |
| `MATTERGEN_MAX_CONCURRENCY` | Worker 最大并发，3090 单卡推荐为 1 |
| `MATTERGEN_MAX_BATCH_SIZE` | 单个扩散批次的最大候选数，3090 推荐为 8 |
| `MATTERGEN_WORKER_TIMEOUT_SECONDS` | Worker 总超时时间，3090 推荐为 14400 |
| `MATTERGEN_CUDA_ALLOC_CONF` | CUDA 显存分配策略，推荐 `expandable_segments:True` |
| `MATTERGEN_TORCH_MATMUL_PRECISION` | FP32 矩阵计算精度，Ampere 显卡推荐 `high` |

## ToolRegistry

每个工具向推理层暴露统一契约：

```json
{
  "name": "chemical_system_energy_above_hull",
  "capability": "material_generation",
  "required_inputs": ["chemical_system"],
  "optional_inputs": ["energy_above_hull"],
  "runtime_availability": true,
  "default_suggestions": {
    "energy_above_hull": {
      "operator": "<=",
      "value": 0.05,
      "unit": "eV/atom"
    }
  }
}
```

生成工具由 `CapabilityRegistry` 和 `generation.model_registry` 动态生成。增加新 MatterGen checkpoint 后，不需要在 Agent planner 中增加新的 `if/elif`。

## 缺参计划

如果目标参数来自系统建议，Agent 不直接发送不可执行的 clarification，而是生成：

```text
Step 1 Ask:
  energy_above_hull <= 0.05 eV/atom

Step 2 Generate:
  chemical_system_energy_above_hull
```

用户确认计划即表示接受建议值。若没有可执行工具，计划会保留 Ask 步骤并标记为不可确认。

## 组成硬约束

`agent_runtime.constraints` 统一展开元素组并检测冲突：

```text
无稀土
  -> rare_earth
  -> [Sc, Y, La, Ce, Pr, Nd, Pm, Sm,
      Eu, Gd, Tb, Dy, Ho, Er, Tm, Yb, Lu]
```

硬约束不会只保存在自然语言中。Planner 会生成独立的 `filter` 步骤，执行器在候选生成后再次验证：

```text
Generate dft_mag_density
  ↓
Filter: exclude rare_earth
  ↓
Evaluate
  ↓
Rank
```

存在排除约束时会进行最多 32 个候选的过采样，并按每批不超过 16 个拆分 Generation Job。若过滤后没有候选，工作流会发布 `agent.reflection`，提示扩大采样、放宽约束或更换工具。

## Agent Memory

每个 session 记录：

```text
current_research_system
confirmed_parameters
historical_goals
model_history
excluded_elements
constraint_groups
```

因此支持上下文化修订，例如：

```text
生成 8 个磁密度约 0.2 的材料
再提高一点磁密度
```

第二轮会基于历史值生成 `dft_mag_density >= 0.22` 的新计划。

`backend/intent/` 和旧 `RequirementParser`/`WorkflowPlanner` 暂时保留用于兼容和既有测试，但不是主聊天链路入口。

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
    tools=[
        MaterialSearchTool(),
        ChatTool(),
        ElementSubstitutionTool(),
        MaterialGenerationTool(),
    ],
    prompt="你是一个材料科学助手..."
)
```

### 3. 执行

```python
result = await agent.ainvoke({"messages": [...]})
```

### 4. MatterGen 生成

生成任务通过以下接口管理：

```text
POST   /api/generation/jobs
GET    /api/generation/jobs/{job_id}
GET    /api/generation/jobs/{job_id}/candidates
POST   /api/generation/jobs/{job_id}/cancel
GET    /api/generation/models
```

Agent 的 `material_generation` Tool 只负责提交任务并返回 `job_id`。实际推理由 `generation.worker` 独立进程执行。

### 5. WebSocket 实时事件

前端通过统一的 WebSocket 网关订阅任务事件：

```text
ws://127.0.0.1:8000/api/ws
```

订阅消息：

```json
{
  "action": "subscribe",
  "channel": "generation.job",
  "resource_id": "<job_id>",
  "request_id": "<optional>"
}
```

服务端依次返回 `connected`、`subscribed` 和 `snapshot`，之后持续推送 `update`、`heartbeat`，直到任务进入 `completed`、`failed` 或 `cancelled`。REST 状态和候选接口仍保留，用于首次加载、页面恢复和 WebSocket 断线降级。

## MatterGen 模型注册表

后端统一注册九种 MatterGen 权重：

```text
mattergen_base
mp_20_base
dft_mag_density
dft_mag_density_hhi_score
chemical_system
chemical_system_energy_above_hull
dft_band_gap
ml_bulk_modulus
space_group
```

模型条件由 `backend/generation/model_registry.py` 定义。请求可以通过 `conditions` 自动解析模型，也可以显式提交 `model_id`。

模型列表接口：

```text
GET /api/generation/models
```

多模型 Campaign：

```text
POST /api/generation/campaigns
GET  /api/generation/campaigns/{campaign_id}
GET  /api/generation/campaigns/{campaign_id}/candidates
POST /api/generation/campaigns/{campaign_id}/cancel
```

每个 Campaign 默认顺序执行模型，避免多个大模型同时占用 GPU 显存。

## 学习要点

1. **Tool 定义**: 如何将功能封装为 LLM 可调用的工具
2. **Agent 创建**: 使用 `create_react_agent` 快速构建 Agent
3. **消息传递**: LangChain 的消息格式 (`HumanMessage`, `AIMessage`, `ToolMessage`)
4. **工具调用**: LLM 自动决定何时调用哪个工具

## 常见问题

### Q: 为什么不继续使用原有的 Router 架构？

A: 原架构需要手动编写意图分类逻辑，而 LangChain Agent 可以自动学习何时调用工具，代码更简洁，也更容易扩展。

### Q: LangChain 会不会太重？

A: 对于只有几个工具的小项目，确实有些过度设计。但作为学习 Agent 的项目，LangChain 提供了标准的抽象和最佳实践。

### Q: 如何切换 LLM 提供商？

A: 直接修改 `.env` 文件中的 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL` 三个值即可。

### Q: 为什么后端使用 MatterGen 的虚拟环境？

A: MatterGen 对 Python、PyTorch、PyG 和 pymatgen 的版本约束较强。后端直接复用内置的 `backend/.venv`，避免重新安装大型依赖，也能保证本地模型权重可以直接加载。

### Q: MatterGen 条件生成是否等于磁性预测？

A: 不是。`dft_mag_density` 是生成条件，不保证生成结果达到目标磁密度。后续仍需独立磁性预测模型或 DFT 验证。

## 相关文档

- [元素替换工具](element_substitution.md) - 详细说明元素替换/掺杂功能
- [MatterGen 集成重构方案](mattergen-integration-refactor-plan.md) - 完整需求、架构与验收标准

## 参考资源

- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [Tool Calling Agent](https://langchain-ai.github.io/langgraph/how-tos/create-react-agent/)
