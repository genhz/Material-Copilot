# 🧬 Material-Copilot

> **A conversational AI assistant for agile materials retrieval and interactive 3D visualization.**
> 
> 基于大语言模型（LLM）与 Materials Project API 的敏捷材料检索与 3D 交互沙盘。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Vue 3](https://img.shields.io/badge/Vue.js-3.0-4FC08D?logo=vue.js)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Powered by DeepSeek](https://img.shields.io/badge/Powered_by-DeepSeek-black.svg)]()

Material-Copilot 是一个专为材料科学（特别是磁性材料、稀土合金等复杂结构研究）打造的轻量级科研辅助工具。它通过引入大模型的 Function Calling 能力，将繁琐的材料数据库检索过程简化为自然语言对话，并在前端实现晶体结构的无缝、沉浸式 3D 渲染。

## ✨ 核心特性 (Features)

- 💬 **对话即检索 (Chat-to-Retrieve)：** 抛弃复杂的搜索表单，直接通过自然语言（例如：“查一下 Nd2Fe14B 的带隙和磁性”）获取材料数据。
- 🔮 **沉浸式 3D 沙盘：** 底层全屏 3D 画布，实时渲染 CIF 晶体结构（支持球棍模型，带元素高亮标注），支持拖拽旋转与缩放。
- 📊 **物性数据抽屉：** 优雅的毛玻璃侧边卡片，直观展示形成能 (Formation Energy)、带隙 (Band Gap)、磁性状态等关键参数。
- 🌓 **深浅色主题平滑切换 (Dark/Light Mode)：** 完美适配夜间科研工作，3D 背景与 UI 元素智能联动。
- 🚀 **前后端解耦架构：** Vue 3 (Vite) + FastAPI 的极致轻量组合，易于扩展更多计算模型（如 GNN 预测或晶格动力学模拟）。

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
- Python 3.11+
- FastAPI (高性能异步 REST API)
- mp-api (Materials Project 官方 SDK)
- OpenAI SDK (调用 DeepSeek 模型)

## 🚀 快速开始 (Getting Started)

### 1. 环境准备 (Prerequisites)

确保你的系统已安装以下工具：

| 工具 | 版本要求 | 说明 |
|------|----------|------|
| [Node.js](https://nodejs.org/) | v18+ 或 v20+ | 前端运行环境 |
| [Python](https://www.python.org/) | 3.11+ | 后端运行环境 |
| [uv](https://github.com/astral-sh/uv) | 最新 | 高性能 Python 包管理器（替代 pip/conda） |

**安装 uv:**
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip 安装
pip install uv
```

### 2. 获取 API 密钥

在运行项目前，你需要获取以下两个 API Key：
- **Materials Project API Key:** 访问 [Materials Project](https://nextgen.materialsproject.org/) 注册获取。
- **DeepSeek API Key:** 访问 [DeepSeek 开放平台](https://platform.deepseek.com/) 获取。

### 3. 后端服务启动

```bash
# 进入后端目录
cd backend

# 使用 uv 创建虚拟环境并安装依赖
uv venv --python 3.11
source .venv/bin/activate  # macOS/Linux
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
uv pip install -r requirements.txt

# 配置环境变量 (推荐方式：复制 .env.example 并编辑)
cp .env.example .env
# 编辑 .env 文件，填入你的 API keys:
#   MP_API_KEY="your_mp_api_key_here"
#   DEEPSEEK_API_KEY="your_deepseek_api_key_here"

# 或者直接导出环境变量
export MP_API_KEY="your_mp_api_key_here"
export DEEPSEEK_API_KEY="your_deepseek_api_key_here"

# 启动 FastAPI 服务 (默认运行在 http://localhost:8000)
uvicorn main:app --reload
```

### 4. 前端服务启动

```bash
# 进入前端目录
cd frontend

# 安装依赖 (推荐使用 pnpm 或 npm)
npm install
# 或 pnpm install

# 启动开发服务器 (默认运行在 http://localhost:5173)
npm run dev

# 构建生产版本
npm run build
```

启动后，浏览器访问 `http://localhost:5173` 即可使用。

## 🏗️ 架构设计 (Architecture)

### Router-Workflow-Skills 架构

本项目采用基于 LLM Function Calling 的智能路由架构，将用户意图自动分类并分发到不同的处理分支：

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   用户输入   │ ──▶ │  Router 路由  │ ──▶ │  Workflow   │
│  (消息)     │     │ (意图分类)    │     │  工作流     │
└─────────────┘     └──────────────┘     └─────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                                                 ▼
          ┌──────────────────┐                            ┌──────────────────┐
          │  Branch A: CHAT  │                            │ Branch B: RENDER │
          │  纯文本对话       │                            │ 3D 晶体渲染        │
          │  - chat_skill    │                            │ - material_search│
          │  - DeepSeek      │                            │ - mp-api         │
          └──────────────────┘                            │ - LLM summary    │
                    │                                     └──────────────────┘
                    ▼                                                 │
          ┌──────────────────┐                            │
          │ action: "chat"   │                            │
          │ (侧边栏关闭)      │                            ▼
          └──────────────────┘                   ┌──────────────────┐
                                                  │ action: "render" │
                                                  │ (侧边栏打开)      │
                                                  └──────────────────┘
```

**核心组件:**

| 组件 | 文件 | 职责 |
|------|------|------|
| **Router** | `backend/router.py` | 使用 DeepSeek 模型分析用户消息，返回意图 (`CHAT` 或 `RENDER_3D`) |
| **Workflow** | `backend/workflow.py` | 根据路由结果分发到不同处理分支 |
| **Skills** | `backend/skills/` | 可复用的原子能力单元 |
| └─ chat_skill | `backend/skills/chat.py` | 处理纯文本对话 |
| └─ material_search | `backend/skills/material_search.py` | 查询 Materials Project 数据库 |

**意图分类示例:**

| 用户输入 | 意图 | 响应 |
|----------|------|------|
| "Nd₂Fe₁₄B" | RENDER_3D | 打开 3D 晶体视图，显示 cif 结构 |
| "查看 Fe3O4 的晶体结构" | RENDER_3D | 打开 3D 晶体视图，显示 cif 结构 |
| "什么是带隙？" | CHAT | 纯文本解释，侧边栏保持关闭 |
| "哪些材料适合做永磁体？" | CHAT | 材料推荐列表，侧边栏保持关闭 |
| "Nd2Fe14B 的磁性如何？" | CHAT | 文本解释（已渲染过该材料时） |

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
├── backend/                  # 后端 FastAPI 项目
│   ├── main.py               # API 入口
│   ├── router.py             # 意图路由器
│   ├── workflow.py           # 工作流编排
│   ├── skills/               # 技能模块
│   │   ├── chat.py           # 聊天技能
│   │   └── material_search.py# 材料检索技能
│   ├── models.py             # Pydantic 数据模型
│   ├── requirements.txt      # Python 依赖
│   └── .env.example          # 环境变量模板
│
└── README.md                 # 项目文档
```

## ❓ 常见问题 (FAQ)

### 1. 化学式数字必须下标吗？

**不需要。** 后端会自动处理常见的化学式格式：
- `Nd2Fe14B` ✅（推荐，键盘直接输入）
- `Nd₂Fe₁₄B` ✅（带下标 Unicode）
- `Nd2Fe14 B` ✅（空格分隔）

所有格式都会被 Router 识别为 `RENDER_3D` 意图，并正确查询 Materials Project 数据库。

### 2. Skills 是什么？

本项目中的 **Skills** 不是传统的 Markdown 文档，而是**可调用的 Python 函数模块**。每个 Skill 封装了一个原子能力：

```python
# backend/skills/chat.py
async def chat_skill(message: str, history: list) -> ChatResult:
    """处理纯文本对话"""
    ...

# backend/skills/material_search.py  
def search_material(formula: str) -> MaterialSearchResult:
    """查询 Materials Project 数据库"""
    ...
```

这种设计使得：
- ✅ **可复用**: Skills 可被多个 Workflow 调用
- ✅ **可测试**: 每个 Skill 独立单元测试
- ✅ **易扩展**: 新增能力只需添加新 Skill 文件

### 3. 如何添加新的材料数据库？

修改 `backend/skills/material_search.py`，在 `search_material()` 函数中添加新的数据源：

```python
def search_material(formula: str) -> MaterialSearchResult:
    # 1. Materials Project
    mp_data = query_mp_api(formula)
    
    # 2. 新增：其他数据库
    # other_data = query_other_db(formula)
    
    return MaterialSearchResult(...)
```

## 🐛 故障排除 (Troubleshooting)

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 后端启动报错 `ModuleNotFoundError` | 虚拟环境未激活 | 运行 `source .venv/bin/activate` |
| API 返回 `401 Unauthorized` | API Key 无效或缺失 | 检查 `.env` 文件中的 key 是否正确 |
| 前端 `npm run dev` 报错 | Node 版本过低 | 升级到 Node.js v18+ |
| 3D 画布不显示 | 浏览器不支持 WebGL | 使用 Chrome/Firefox/Edge 最新版 |
| 侧边栏显示 N/A | 材料数据字段缺失 | 检查后端 `MaterialData` 模型是否完整 |
| 主题切换后 3D 背景不变 | 缓存问题 | 刷新页面或检查浏览器控制台错误 |

### 调试模式

**后端调试:**
```bash
# 查看详细日志
uvicorn main:app --reload --log-level debug
```

**前端调试:**
```bash
# 启动开发服务器（带详细日志）
npm run dev

# 打开浏览器开发者工具 (F12) 查看控制台
```

## 📄 许可证 (License)

MIT License © 2026 Material-Copilot Project

## 🙏 致谢 (Acknowledgements)

- [Materials Project](https://materialsproject.org/) - 晶体结构数据
- [DeepSeek](https://platform.deepseek.com/) - LLM Function Calling
- [3Dmol.js](https://3dmol.csb.pitt.edu/) - 3D 渲染引擎
- [Vue.js](https://vuejs.org/) - 前端框架
- [FastAPI](https://fastapi.tiangolo.com/) - 后端框架