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
- TailwindCSS (响应式布局与原子化原子化 CSS)
- Element Plus (UI 组件库)
- 3Dmol.js (WebGL 晶体结构渲染)

**后端 (Backend):**
- Python 3.10+
- FastAPI (高性能异步 REST API)
- mp-api (Materials Project 官方 SDK)
- OpenAI SDK (调用 DeepSeek 模型)

## 🚀 快速开始 (Getting Started)

### 1. 环境准备与 API 密钥

在运行项目前，你需要获取以下两个 API Key：
- **Materials Project API Key:** 访问 [Materials Project](https://nextgen.materialsproject.org/) 注册获取。
- **DeepSeek API Key:** 访问 [DeepSeek 开放平台](https://platform.deepseek.com/) 获取。

### 2. 后端服务启动

```bash
# 进入后端目录
cd backend

# 推荐使用 Conda 虚拟环境
conda create -n material-copilot python=3.11 -y
conda activate material-copilot

# 安装依赖
pip install -r requirements.txt

# 配置环境变量 (或者直接修改 .env 文件)
export MP_API_KEY="your_mp_api_key_here"
export DEEPSEEK_API_KEY="your_deepseek_api_key_here"

# 启动 FastAPI 服务 (默认运行在 http://localhost:8000)
uvicorn main:app --reload