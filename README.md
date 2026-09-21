# 🧬 Material-Copilot

> **A conversational AI assistant for agile materials retrieval and interactive 3D visualization.**
> 
> 基于 LangChain Agent 与 Materials Project API 的材料科学智能助手。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Vue 3](https://img.shields.io/badge/Vue.js-3.0-4FC08D?logo=vue.js)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-Agent-1c3c3c?logo=langchain)](https://python.langchain.com/)

Material-Copilot 是一个专为材料科学（特别是磁性材料、稀土合金等复杂结构研究）打造的轻量级科研辅助工具。它通过 **LangChain Agent** 实现智能意图识别，将繁琐的材料数据库检索过程简化为自然语言对话，并在前端实现晶体结构的无缝、沉浸式 3D 渲染。

## ✨ 核心特性

- 💬 **对话即检索** — 通过自然语言获取材料数据，无需复杂表单
- 🤖 **LangChain Agent 驱动** — ReAct Agent 自动判断意图，智能调用工具
- 🔮 **沉浸式 3D 沙盘** — 全屏 3D 画布实时渲染 CIF 晶体结构
- 🧪 **MatterGen 候选生成** — 根据目标磁密度异步生成新材料候选
- 📊 **物性数据卡片** — 展示形成能、带隙、磁性等关键参数
- 🌓 **深浅色主题** — 适配夜间科研工作
- 🚀 **前后端解耦** — Vue 3 + FastAPI 轻量架构

## 📸 界面预览

<p align="center">
  <img src="doc/frontend.png" width="95%">
</p>

## 🛠️ 技术栈

| 前端 | 后端 |
|------|------|
| Vue 3 + Vite | FastAPI |
| TailwindCSS | LangChain + LangGraph |
| Element Plus | mp-api (Materials Project) |
| 3Dmol.js | MatterGen + PyTorch |
| ECharts | 任意 OpenAI 兼容 LLM |

## 🚀 快速开始

### 1. 获取 API 密钥

- **Materials Project API Key:** [注册获取](https://nextgen.materialsproject.org/)
- **LLM API Key:** 支持 DeepSeek、OpenAI 等任意 OpenAI 兼容接口

### 2. 配置 LLM

编辑 `backend/.env`，修改以下三个值来切换 LLM 提供商，例如：

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

### 3. 后端启动

```bash
cd backend
cp .env.example .env
# 编辑 .env 填入 API keys

# 安装或同步后端与 MatterGen 的统一依赖
uv sync

# 启动后端
.venv/bin/python -m uvicorn main:app \
  --reload --host 0.0.0.0 --port 8000
```

`backend/.venv` 是后端与 MatterGen 共用的 Python 3.10 环境。不要运行 `uv sync --reinstall`，避免重新安装 PyTorch、PyG 和 MatterSim。

### 4. 前端启动

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173` 即可使用。

## 🏗️ 架构设计

### LangChain Agent 架构

```
用户输入 ──▶ LangChain Agent ──▶ 自动选择工具
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
        ChatTool            MaterialSearch         ElementSubstitution
     材料科学问答            晶体结构查询              元素替换/掺杂
                                      │
                                      ▼
                            MaterialGeneration
                            MatterGen 候选生成
```

**核心组件:**

| 组件 | 文件 | 职责 |
|------|------|------|
| **Agent** | `backend/agent.py` | LangChain ReAct Agent，智能意图识别 |
| **ChatTool** | `backend/skills/chat.py` | 材料科学领域对话 |
| **MaterialSearchTool** | `backend/skills/material_search.py` | 查询 Materials Project 数据库 |
| **ElementSubstitutionTool** | `backend/skills/element_substitution.py` | 元素替换/掺杂 |
| **MaterialGenerationTool** | `backend/skills/material_generation.py` | 提交 MatterGen 磁性材料生成任务 |

**意图识别示例:**

| 用户输入 | Agent 行为 | 响应 |
|----------|-----------|------|
| "Nd₂Fe₁₄B" | `material_search` | 打开 3D 晶体视图 |
| "查看 Fe3O4 的晶体结构" | `material_search` | 打开 3D 晶体视图 |
| "什么是带隙？" | `chat` | 纯文本解释 |
| "哪些材料适合做永磁体？" | `chat` | 材料推荐 |
| "把 Nd2Fe14B 中的 Fe 替换成 Co" | `element_substitution` | 显示 Nd2Co14B 结构 |
| "生成磁密度约 0.15 的候选材料" | `material_generation` | 创建后台生成任务 |

### 项目结构

```
material-sandbox/
├── frontend/              # Vue 3 前端项目
│   ├── src/
│   │   ├── components/    # UI 组件
│   │   ├── composables/   # 组合式函数
│   │   └── App.vue
│   └── package.json
│
├── backend/               # FastAPI + LangChain + MatterGen 后端
│   ├── .venv/             # Python 3.10 统一环境
│   ├── main.py            # API 入口
│   ├── agent.py           # LangChain Agent
│   ├── vendor/mattergen/  # 内置 MatterGen 源码与本地权重
│   ├── skills/            # LangChain Tools
│   │   ├── chat.py
│   │   ├── material_search.py
│   │   ├── element_substitution.py
│   │   └── material_generation.py
│   ├── generation/        # 后台生成任务、Worker 和 CIF 后处理
│   ├── artifacts/         # 运行时任务和候选结构
│   └── pyproject.toml
│
└── doc/                   # 项目文档
    ├── frontend.png
    ├── backend.md         # 后端详细文档
    ├── element_substitution.md  # 元素替换工具文档
    └── mattergen-integration-refactor-plan.md
```

## ❓ 常见问题

### 化学式必须用下标吗？

不需要。`Nd2Fe14B`、`Nd₂Fe₁₄B`、`Nd2Fe14 B` 都能自动识别。

### 元素替换的数据从哪来？

1. 先执行元素替换生成新化学式
2. 优先从 Materials Project 查询真实物性数据
3. 如果 MP 没有，使用结构计算值并标注"需 DFT 计算"

详见 [元素替换工具文档](doc/element_substitution.md)。

### 如何添加新工具？

在 `backend/skills/` 下创建新文件继承 `BaseTool`，然后在 `agent.py` 中注册即可。

### 如何进行磁性材料生成？

在 AI 助手中输入类似“生成磁密度约 0.15 的候选材料”。Agent 会创建后台任务，前端显示进度；完成后的候选可以点击并在 3D 视图中查看。

MatterGen 的条件生成不代表目标磁密度已经得到验证，后续仍需独立磁性预测器或 DFT 计算。

## 🐛 故障排除

| 问题 | 解决方案 |
|------|----------|
| `LLM_API_KEY 未配置` | 检查 `.env` 中 `LLM_API_KEY` 是否正确设置 |
| `Insufficient Balance` | LLM API 余额不足，需充值或更换 Key |
| `401 Unauthorized` | 检查 `.env` 中 API Key 是否正确 |
| 3D 画布不显示 | 使用 Chrome/Firefox/Edge 最新版 |
| `No module named 'pkg_resources'` | 确认 `setuptools<81` 已安装且没有重装 MatterGen 环境 |
| MatterGen Worker 启动失败 | 检查 `MATTERGEN_MODEL_PATH` 和 checkpoint 文件大小 |

**后端调试:**
```bash
cd backend
.venv/bin/python -m uvicorn main:app \
  --reload --log-level debug
```

## 📖 学习资源

- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [后端详细文档](doc/backend.md)
- [MatterGen 集成重构方案](doc/mattergen-integration-refactor-plan.md)

## 📄 许可证

MIT License © 2026 Material-Copilot Project

## 🙏 致谢

- [Materials Project](https://materialsproject.org/) - 晶体结构数据
- [3Dmol.js](https://3dmol.csb.pitt.edu/) - 3D 渲染引擎
