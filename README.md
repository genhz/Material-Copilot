# 🧬 Material-Copilot

> **A conversational AI assistant for agile materials retrieval and interactive 3D visualization.**
> 
> 基于 LangChain Agent 与 Materials Project API 的材料科学智能助手。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Vue 3](https://img.shields.io/badge/Vue.js-3.0-4FC08D?logo=vue.js)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-Agent-1c3c3c?logo=langchain)](https://python.langchain.com/)
[![uv](https://img.shields.io/badge/Package%20Manager-uv-ffd547?logo=python)](https://github.com/astral-sh/uv)

Material-Copilot 是一个专为材料科学（特别是磁性材料、稀土合金等复杂结构研究）打造的轻量级科研辅助工具。它通过 **LangChain Agent** 实现智能意图识别，将繁琐的材料数据库检索过程简化为自然语言对话，并在前端实现晶体结构的无缝、沉浸式 3D 渲染。

## ✨ 核心特性 (Features)

- 💬 **对话即检索 (Chat-to-Retrieve):** 抛弃复杂的搜索表单，直接通过自然语言获取材料数据
- 🤖 **LangChain Agent 驱动:** 使用 ReAct Agent 自动判断用户意图，无需手动路由
- 🔮 **沉浸式 3D 沙盘:** 底层全屏 3D 画布，实时渲染 CIF 晶体结构（支持球棍模型，带元素高亮标注）
- 📊 **物性数据抽屉:** 优雅的毛玻璃侧边卡片，直观展示形成能、带隙、磁性状态等关键参数
- 🌓 **深浅色主题平滑切换:** 完美适配夜间科研工作，3D 背景与 UI 元素智能联动
- 🚀 **前后端解耦架构:** Vue 3 (Vite) + FastAPI 的极致轻量组合

## 📸 界面预览 (Screenshots)

<p align="center">
  <img src="doc/frontend.png" width="95%">
</p>

## 🛠️ 技术栈 (Tech Stack)

**前端 (Frontend):**
- Vue 3 (Composition API) + Vite
- TailwindCSS (响应式布局与原子化 CSS)
- Element Plus (UI 组件库)
- 3Dmol.js (WebGL 晶体结构渲染)

**后端 (Backend):**
- Python 3.13+
- FastAPI (高性能异步 REST API)
- **LangChain + LangGraph** (Agent 框架)
- **uv** (高性能包管理器)
- mp-api (Materials Project 官方 SDK)
- OpenAI SDK (调用 DeepSeek 模型)

## 🚀 快速开始 (Getting Started)

### 1. 环境准备 (Prerequisites)

确保你的系统已安装以下工具：

| 工具 | 版本要求 | 说明 |
|------|----------|------|
| [Node.js](https://nodejs.org/) | v18+ 或 v20+ | 前端运行环境 |
| [Python](https://www.python.org/) | 3.13+ | 后端运行环境 |
| [uv](https://github.com/astral-sh/uv) | 最新 | 高性能 Python 包管理器 |

**安装 uv:**

```bash
# macOS / Linux
brew install uv

# 或
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 获取 API 密钥

在运行项目前，你需要获取以下两个 API Key：
- **Materials Project API Key:** 访问 [Materials Project](https://nextgen.materialsproject.org/) 注册获取
- **DeepSeek API Key:** 访问 [DeepSeek 开放平台](https://platform.deepseek.com/) 获取

### 3. 后端服务启动

```bash
# 进入后端目录
cd backend

# 使用 uv 安装依赖（自动创建虚拟环境）
uv sync

# 配置环境变量（推荐方式：复制 .env.example 并编辑）
cp .env.example .env
# 编辑 .env 文件，填入你的 API keys:
#   MP_API_KEY="your_mp_api_key_here"
#   DEEPSEEK_API_KEY="your_deepseek_api_key_here"

# 启动 FastAPI 服务 (默认运行在 http://localhost:8000)
uv run uvicorn main:app --reload
```

### 4. 前端服务启动

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器 (默认运行在 http://localhost:5173)
npm run dev

# 构建生产版本
npm run build
```

启动后，浏览器访问 `http://localhost:5173` 即可使用。

## 🏗️ 架构设计 (Architecture)

### LangChain Agent 架构

本项目采用 **LangChain ReAct Agent** 实现智能意图识别和工具调用：

```
┌─────────────┐     ┌─────────────────────────┐     ┌──────────────────────┐
│   用户输入   │ ──▶ │  LangChain Agent        │ ──▶ │ 自动选择工具        │
│  (消息)     │     │  (ReAct + LangGraph)    │     │                      │
└─────────────┘     └─────────────────────────┘     └──────────────────────┘
                                                       │
                    ┌──────────────────────────────────┼──────────────────┐
                    ▼                                  ▼                  ▼
          ┌──────────────────┐              ┌──────────────────┐  ┌────────────────┐
          │  ChatTool        │              │ MaterialSearch   │  │ 其他工具...   │
          │  材料科学问答    │              │ 晶体结构查询     │  │                │
          │  - 概念解释      │              │ - CIF 数据       │  │                │
          │  - 材料推荐      │              │ - 物性参数       │  │                │
          └──────────────────┘              └──────────────────┘  └────────────────┘
                    │                                  │
                    ▼                                  ▼
          ┌──────────────────┐              ┌──────────────────┐
          │ action: "chat"   │              │ action: "render" │
          │ (侧边栏关闭)      │              │ (侧边栏打开 + 3D) │
          └──────────────────┘              └──────────────────┘
```

**核心组件:**

| 组件 | 文件 | 职责 |
|------|------|------|
| **Agent** | `backend/agent.py` | LangChain ReAct Agent，自动判断意图并调用工具 |
| **ChatTool** | `backend/skills/chat.py` | 材料科学领域的对话工具 |
| **MaterialSearchTool** | `backend/skills/material_search.py` | 查询 Materials Project 数据库 |

**意图识别示例:**

| 用户输入 | Agent 行为 | 响应 |
|----------|-----------|------|
| "Nd₂Fe₁₄B" | 调用 `material_search` | 打开 3D 晶体视图，显示 cif 结构 |
| "查看 Fe3O4 的晶体结构" | 调用 `material_search` | 打开 3D 晶体视图，显示 cif 结构 |
| "什么是带隙？" | 调用 `chat` | 纯文本解释，侧边栏保持关闭 |
| "哪些材料适合做永磁体？" | 调用 `chat` | 材料推荐列表，侧边栏保持关闭 |
| "Nd2Fe14B 的磁性如何？" | 调用 `chat` (已渲染时) / `material_search` (未渲染时) | 根据上下文智能选择 |

### 项目结构

```
material-sandbox/
├── frontend/                 # 前端 Vue 3 项目
│   ├── src/
│   │   ├── components/       # UI 组件
│   │   │   ├── MainView.vue  # 主视图（3D 画布 + 侧边栏）
│   │   │   ├── crystal/      # 3D 晶体相关组件
│   │   │   └── chat/         # AI 聊天相关组件
│   │   ├── composables/      # 组合式函数
│   │   │   ├── useAIChat.ts  # AI 对话逻辑
│   │   │   └── useTheme.ts   # 主题切换逻辑
│   │   ├── types/            # TypeScript 类型定义
│   │   └── App.vue           # 根组件
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                  # 后端 FastAPI + LangChain 项目
│   ├── main.py               # API 入口
│   ├── agent.py              # LangChain Agent 封装
│   ├── skills/               # LangChain Tools
│   │   ├── chat.py           # ChatTool - 对话工具
│   │   └── material_search.py# MaterialSearchTool - 材料搜索
│   ├── pyproject.toml        # uv 包管理配置
│   ├── uv.lock               # 依赖锁定文件
│   ├── test_agent.py         # Agent 测试脚本
│   └── README.md             # 后端详细文档
│
└── README.md                 # 项目文档
```

## ❓ 常见问题 (FAQ)

### 1. 化学式数字必须下标吗？

**不需要。** 后端会自动处理常见的化学式格式：
- `Nd2Fe14B` ✅（推荐，键盘直接输入）
- `Nd₂Fe₁₄B` ✅（带下标 Unicode）
- `Nd2Fe14 B` ✅（空格分隔）

所有格式都会被 Agent 识别并正确查询 Materials Project 数据库。

### 2. 为什么选择 LangChain？

LangChain 提供了标准的 Agent 抽象和工具调用机制，使得：
- ✅ **意图识别自动化:** 不再需要手动编写 Router 分类逻辑
- ✅ **工具易扩展:** 新增工具只需继承 `BaseTool`，Agent 会自动学习调用时机
- ✅ **符合最佳实践:** 使用 LangGraph 的 ReAct 模式，是学习 Agent 开发的好例子

### 3. 如何添加新的工具？

1. 在 `backend/skills/` 下创建新文件，继承 `BaseTool`：

```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    param: str = Field(..., description="参数描述")

class MyTool(BaseTool):
    name = "my_tool"
    description = "工具描述"
    args_schema: Type[BaseModel] = MyToolInput
    
    def _run(self, param: str) -> str:
        # 实现工具逻辑
        pass
```

2. 在 `agent.py` 的 `tools` 列表中添加新工具

### 4. 如何添加新的材料数据库？

修改 `backend/skills/material_search.py`，在 `MaterialSearchTool._run()` 中添加新的数据源：

```python
def _run(self, formula: str) -> str:
    # 1. Materials Project
    mp_data = self._query_mp_api(formula)
    
    # 2. 新增：其他数据库
    # other_data = self._query_other_db(formula)
    
    return json.dumps({...})
```

## 🐛 故障排除 (Troubleshooting)

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| `uv: command not found` | uv 未安装 | 运行 `brew install uv` |
| `Insufficient Balance` | DeepSeek API 余额不足 | 充值或更换 API Key |
| API 返回 `401 Unauthorized` | API Key 无效或缺失 | 检查 `.env` 文件中的 key 是否正确 |
| 前端 `npm run dev` 报错 | Node 版本过低 | 升级到 Node.js v18+ |
| 3D 画布不显示 | 浏览器不支持 WebGL | 使用 Chrome/Firefox/Edge 最新版 |
| 侧边栏显示 N/A | 材料数据字段缺失 | 检查后端 `MaterialData` 模型是否完整 |

### 调试模式

**后端调试:**
```bash
cd backend
uv run uvicorn main:app --reload --log-level debug

# 测试 Agent
uv run python test_agent.py
```

**前端调试:**
```bash
cd frontend
npm run dev

# 打开浏览器开发者工具 (F12) 查看控制台
```

## 📖 学习资源

如果你想深入学习 LangChain Agent 开发，可以参考：

- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [ReAct Agent 教程](https://langchain-ai.github.io/langgraph/how-tos/create-react-agent/)
- [backend/README.md](backend/README.md) - 本项目后端详细文档

## 📄 许可证 (License)

MIT License © 2026 Material-Copilot Project

## 🙏 致谢 (Acknowledgements)

- [Materials Project](https://materialsproject.org/) - 晶体结构数据
- [DeepSeek](https://platform.deepseek.com/) - LLM 服务
- [3Dmol.js](https://3dmol.csb.pitt.edu/) - 3D 渲染引擎
- [Vue.js](https://vuejs.org/) - 前端框架
- [FastAPI](https://fastapi.tiangolo.com/) - 后端框架
- [LangChain](https://python.langchain.com/) - Agent 框架
- [uv](https://github.com/astral-sh/uv) - 包管理器
