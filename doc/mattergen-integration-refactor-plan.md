# MatterGen 后端集成重构需求与执行方案

> 文档状态：首版已实施，保留为维护与扩展基线  
> 目标读者：负责实施本次重构的 Agent  
> 项目路径：`/Users/genhz/Documents/code/material-sandbox`  
> 更新日期：2026-09-20

## 1. 文档目的

本文档是 MatterGen 与 Material-Copilot 后端集成的完整需求说明和执行方案。

执行 Agent 不应只根据代码现状自行推断需求。开始修改代码前，必须完整阅读本文档，并遵守其中的环境、架构、接口、兼容性和验收约束。

本次重构的最终目标是：

1. 在现有后端中接入 MatterGen 的磁性材料候选生成能力。
2. 直接复用已经安装好的 MatterGen Python 3.10 环境，不重新安装 PyTorch 等大型依赖。
3. 统一使用 `backend/.venv`，不创建新的虚拟环境。
4. 保留现有材料查询、AI 聊天和元素替换功能。
5. 将 MatterGen 推理作为独立后台任务执行，不能阻塞 FastAPI 主进程。
6. 第一版只接入 `dft_mag_density` 模型和 `dft_mag_density` 条件。
7. 生成候选结构必须能够被 pymatgen 解析，并复用到现有 3D 晶体查看器。
8. 为后续接入 MatterSim 评估和磁性属性预测器保留扩展点。

## 2. 项目背景

### 2.1 当前 Material-Copilot 架构

当前项目是前后端分离结构：

```text
Material-Copilot/
├── frontend/              Vue 3 + Vite + TypeScript
├── backend/               FastAPI + LangChain/LangGraph
├── mattergen/             Microsoft MatterGen
└── doc/                   项目文档
```

后端现有主要接口：

```text
POST /api/chat
GET  /api/material/search
POST /api/chat/clear
GET  /health
```

后端现有 LangChain Tools：

```text
chat
material_search
element_substitution
```

前端现有主要流程：

```text
用户输入材料化学式
    -> 后端查询 Materials Project
    -> 返回 MaterialData
    -> CrystalViewer 渲染 CIF
    -> MaterialPanel 展示物性
```

AI 对话流程：

```text
用户与 AIAssistant 对话
    -> /api/chat
    -> Agent 调用工具
    -> action=chat 或 action=render
    -> render 时更新 currentMaterial
```

### 2.2 MatterGen 的定位

MatterGen 是 Microsoft 开源的扩散生成模型，用于生成无机晶体结构。它可以同时生成：

- 原子类型
- 原子坐标
- 晶格参数

MatterGen 不是传统意义上的“给定结构预测属性”模型。它主要用于：

- 无条件生成新晶体结构
- 根据目标性质生成候选结构
- 根据化学体系或空间群进行条件生成
- 通过微调支持自定义属性约束

本次使用的模型：

```text
checkpoint: backend/vendor/mattergen/checkpoints/dft_mag_density
condition: dft_mag_density
model: MatterGen 1.0.3
```

`dft_mag_density` 是生成条件，不是对生成结果磁密度的后验预测。生成完成不代表候选材料的实际磁密度一定达到目标值。

### 2.3 已确认的本地模型文件

本地权重路径：

```text
/Users/genhz/Documents/code/material-sandbox/backend/vendor/mattergen/checkpoints/dft_mag_density/checkpoints/last.ckpt
```

已验证文件：

```text
size: 511777278 bytes
sha256: 01dd3e86805165412e0810e2a77a4756f8e1020f3ff2707c74af0a3f88a1bb8e
```

当前目录还包含：

```text
backend/vendor/mattergen/checkpoints/dft_mag_density/checkpoints/last.ckpt.lfs-pointer
```

该文件是原 Git LFS 指针备份。执行 Agent 不要删除、覆盖或重新执行 Git LFS checkout。

## 3. 已确认的环境状态

### 3.1 唯一允许使用的 Python 环境

```text
/Users/genhz/Documents/code/material-sandbox/backend/.venv
```

当前版本：

```text
Python: 3.10.21
PyTorch: 2.4.1
torch-geometric: 2.8.0.post1
MatterGen: 1.0.3
MatterSim: 1.1.2
pymatgen: 2024.10.29
mp-api: 0.43.0
numpy: 1.26.4
pydantic: 2.13.5
pytorch-lightning: 2.0.6
hydra-core: 1.3.1
emmet-core: 0.85.1
```

该环境已经能够成功加载 `dft_mag_density` 权重并执行 MatterGen 扩散采样。

### 3.2 已移除的旧环境

原 Python 3.13 `backend/.venv` 已删除。原 `mattergen/.venv` 已迁移为
`backend/.venv`，现在同时承载后端和 MatterGen。

### 3.3 环境操作硬性约束

执行 Agent 必须遵守：

- 不执行 `uv venv`
- 不创建新的 Python 环境
- 不执行 `uv sync --reinstall`
- 不重新安装 PyTorch、PyG、MatterSim 或 MatterGen
- 不删除 `backend/.venv`
- 不使用 `uv run` 启动后端，统一使用 `backend/.venv/bin/python`
- 不进行 `.venv` 备份
- 不提交 `.venv`

允许并推荐使用普通 `uv sync`。MatterGen 已声明为后端路径依赖，因此 uv
不会再把它当成多余包删除：

```bash
cd /Users/genhz/Documents/code/material-sandbox/backend
uv sync
```

首次执行时，此命令会根据 `uv.lock` 恢复 MatterGen、PyTorch、PyG、
MatterSim 及后端依赖；后续执行只校验环境。

## 4. MatterGen 源码状态

MatterGen 已从根目录迁移到：

```text
backend/vendor/mattergen/
```

原根目录 `mattergen/`、Git gitlink 和 `.gitmodules` 已移除。嵌套的
`backend/vendor/mattergen/.git` 也已移除，因此 MatterGen 现在是后端仓库中的普通源码目录。

必须保留：

- `backend/vendor/mattergen/mattergen/` 源码
- `backend/vendor/mattergen/checkpoints/dft_mag_density/config.yaml`
- `backend/vendor/mattergen/checkpoints/dft_mag_density/checkpoints/last.ckpt`
- MatterGen 的 MIT License 和 NOTICE

不得对已迁移目录执行：

- `git reset --hard`
- `git clean`
- Git LFS checkout
- 覆盖 `last.ckpt`
- 删除 `last.ckpt.lfs-pointer`

## 5. 需求范围

### 5.1 本期必须完成

- 统一 Python 版本为 3.10
- 后端依赖增量安装到 MatterGen 环境
- 修改后端启动方式
- 设计并实现 MatterGen Adapter
- 实现后台生成任务
- 实现生成任务 API
- 接入 LangChain Agent
- 前端显示生成进度和候选列表
- 选中候选后复用现有 3D 查看器
- 增加任务取消能力
- 保留现有功能
- 完整测试和文档更新

### 5.2 本期不做

- 不训练 MatterGen
- 不微调 MatterGen
- 不接入 `dft_mag_density_hhi_score`
- 不接入 `chemical_system`
- 不实现精确化学计量比生成
- 不实现给定结构的磁密度预测
- 不将 MatterSim 评估作为首版阻塞条件
- 不实现分布式任务队列
- 不引入 Redis、Celery 或 Kubernetes
- 不重构整个前端设计
- 不替换现有 CrystalViewer

### 5.3 后续可扩展

- MatterSim 稳定性、新颖性和唯一性评估
- 独立磁性属性预测模型
- `dft_mag_density_hhi_score`
- `chemical_system` 过滤器
- 联合属性模型
- 多任务并发
- GPU 远程推理
- 候选材料比较和排序

## 6. 目标架构

### 6.1 进程架构

API 和 MatterGen 推理共用同一个 Python 环境，但必须运行在两个进程中：

```text
backend/.venv/bin/python
    ├── FastAPI API 进程
    │     ├── 参数校验
    │     ├── 任务提交
    │     ├── 状态查询
    │     ├── LangChain Agent
    │     └── 候选读取
    │
    └── MatterGen Worker 子进程
          ├── 加载模型
          ├── 执行扩散采样
          ├── 写入进度
          ├── 保存 CIF
          └── 返回最终状态
```

FastAPI 主进程不得直接执行完整 MatterGen 推理。

Worker 必须使用：

```python
sys.executable
```

这样可以保证 Worker 使用启动后端时的 MatterGen Python 环境，禁止在代码中硬编码虚拟环境路径。

### 6.2 首版进程模型

首版采用“每个任务一个 Worker 子进程”模型：

```text
API 收到任务
    -> 写入 job.json，状态 queued
    -> 获取全局并发锁
    -> 启动 Worker 子进程
    -> 状态 running
    -> Worker 完成并写 candidates.json
    -> API 返回 completed
```

优点：

- 不阻塞 FastAPI
- 取消任务时可以终止子进程
- Worker 崩溃不会拖垮 API
- 不需要引入分布式队列

限制：

- 每个任务会重新加载模型
- 首版最大并发数固定为 1
- 后续可以升级为常驻 Worker

## 7. 目标代码结构

```text
backend/
├── .venv/                 # Python 3.10 统一环境
├── .python-version
├── pyproject.toml
├── uv.lock
├── README.md
├── main.py
├── agent.py
├── config.py
├── generation/
│   ├── __init__.py
│   ├── schemas.py
│   ├── exceptions.py
│   ├── store.py
│   ├── manager.py
│   ├── worker.py
│   ├── adapter.py
│   └── evaluator.py
├── skills/
│   ├── __init__.py
│   ├── chat.py
│   ├── material_search.py
│   ├── element_substitution.py
│   └── material_generation.py
├── vendor/
│   └── mattergen/         # 内置 MatterGen 源码、配置和本地权重
└── artifacts/
    └── generation/
```

建议不要一次性重构所有后端文件。优先新增 `generation/` 包，并只对 `main.py`、`agent.py` 和 `skills/__init__.py` 做必要修改。

## 8. Python 与依赖方案

### 8.1 pyproject.toml 目标

`backend/pyproject.toml` 至少需要修改：

```toml
requires-python = ">=3.10,<3.11"

dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-community>=0.3.0",
    "langgraph>=0.2.0",
    "mp-api==0.43.0",
    "pymatgen==2024.10.29",
    "numpy==1.26.4",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "setuptools<81",
    "mattergen",
    "torch==2.4.1; sys_platform == 'darwin'",
    "torch_cluster",
    "torch_scatter",
    "torch_sparse",
]
```

必须同时声明：

```toml
[tool.uv.sources]
mattergen = { path = "vendor/mattergen", editable = true }
```

并为 `torch_cluster`、`torch_scatter` 和 `torch_sparse` 提供 PyG 预编译
wheel 源。锁文件只针对 `darwin` 和 `linux` 解析，避免 uv 为 Windows
源码构建 PyG 扩展。

### 8.2 Python 版本文件

`backend/.python-version` 修改为：

```text
3.10
```

### 8.3 依赖同步

```bash
cd /Users/genhz/Documents/code/material-sandbox/backend
uv lock
uv sync
```

执行 Agent 必须确认没有发生以下行为：

- 使用现有 `backend/.venv`
- 没有卸载 MatterGen
- 没有重新安装 PyTorch
- 没有修改 MatterSim
- 没有删除生成模型

### 8.4 环境验证

```bash
cd /Users/genhz/Documents/code/material-sandbox/backend

.venv/bin/python -c \
  "import sys, fastapi, langchain, pymatgen, numpy, torch, mattergen; print(sys.executable); print(torch.__version__)"
```

预期：

```text
sys.executable 指向 backend/.venv/bin/python
torch.__version__ == 2.4.1
```

### 8.5 requirements.txt

`backend/requirements.txt` 不再作为安装来源。可以删除，或者将其改成说明文件，明确指出：

- 使用 `pyproject.toml` + `uv.lock`
- Python 环境使用 `backend/.venv`
- 不允许根据 requirements.txt 重建独立环境

## 9. 启动与运行方式

### 9.1 后端启动

```bash
cd /Users/genhz/Documents/code/material-sandbox/backend
.venv/bin/python -m uvicorn main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8000
```

禁止使用：

```bash
uv run uvicorn main:app --reload
```

### 9.2 测试启动

```bash
cd /Users/genhz/Documents/code/material-sandbox/backend
.venv/bin/python -m pytest
```

### 9.3 Apple Silicon

启动 API 和 Worker 时设置：

```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1
```

如果不设置，部分 PyTorch 操作在 MPS 上可能直接报错。

## 10. 配置项

在 `backend/.env.example` 和配置模块中增加：

```text
MATTERGEN_ENABLED=true
MATTERGEN_MODEL_ID=dft_mag_density
MATTERGEN_MODEL_PATH=vendor/mattergen/checkpoints/dft_mag_density
MATTERGEN_ARTIFACT_ROOT=artifacts/generation
MATTERGEN_MAX_CONCURRENCY=1
MATTERGEN_JOB_RETENTION_DAYS=7
MATTERGEN_WORKER_TIMEOUT_SECONDS=7200
PYTORCH_ENABLE_MPS_FALLBACK=1
```

配置要求：

- 模型路径默认基于仓库根目录解析，不要硬编码 `/Users/genhz`
- 客户端不能提交任意模型路径
- 模型 ID 使用允许列表
- `MATTERGEN_ENABLED=false` 时，后端不导入或加载 MatterGen
- 模型路径不存在时，API 仍能启动，但生成接口返回 `503`

## 11. MatterGen Adapter 需求

新增文件：

```text
backend/generation/adapter.py
```

### 11.1 导入

```python
from mattergen.common.utils.data_classes import MatterGenCheckpointInfo
from mattergen.generator import CrystalGenerator
```

### 11.2 模型检查点

```python
MatterGenCheckpointInfo(
    model_path=model_path,
    load_epoch="last",
    strict_checkpoint_loading=True,
)
```

### 11.3 生成参数

首版固定支持：

```python
properties_to_condition_on = {
    "dft_mag_density": target_magnetic_density,
}
```

MatterGen 调用映射：

```text
API target_magnetic_density -> properties_to_condition_on.dft_mag_density
API guidance_scale          -> diffusion_guidance_factor
API num_candidates          -> batch_size
API seed                    -> seed
```

固定参数：

```python
num_batches = 1
record_trajectories = False
```

### 11.4 参数限制

```text
target_magnetic_density: > 0 且 <= 1
num_candidates: 1 到 16
guidance_scale: >= 0
seed: 可选整数
```

### 11.5 设备

设备选择交给 MatterGen 的 `get_device()`：

```text
CUDA可用 -> CUDA
MPS可用  -> MPS
否则     -> CPU
```

### 11.6 预检查

启动 Worker 前检查：

- `mattergen` 包可导入
- checkpoint 文件存在
- checkpoint 文件不是 LFS pointer
- `config.yaml` 存在
- 模型目录包含 `config.yaml`
- `dft_mag_density` 出现在模型条件中

### 11.7 错误分类

至少区分：

```text
MODEL_NOT_FOUND
CHECKPOINT_INVALID
MATTERGEN_DISABLED
MATTERGEN_IMPORT_ERROR
GENERATION_FAILED
GENERATION_TIMEOUT
GENERATION_CANCELLED
INVALID_OUTPUT
```

## 12. 后台任务设计

### 12.1 任务状态

```text
queued
running
completed
failed
cancelled
```

### 12.2 首版存储

使用文件系统，不引入数据库：

```text
backend/artifacts/generation/{job_id}/
├── request.json
├── job.json
├── stdout.log
├── stderr.log
├── candidates.json
├── candidates/
│   ├── 000.cif
│   └── 001.cif
└── generated_crystals_cif.zip
```

### 12.3 job.json 字段

至少包括：

```json
{
  "job_id": "uuid",
  "status": "queued",
  "progress": 0.0,
  "model_id": "dft_mag_density",
  "request": {},
  "created_at": "ISO-8601",
  "started_at": null,
  "completed_at": null,
  "error_code": null,
  "error_message": null,
  "worker_pid": null
}
```

### 12.4 进度

MatterGen 默认采样步数为 1000。

`ProgressCallback` 目前在 batch 级别调用。首版只有一批候选时，进度可能从 `0.0` 直接跳到 `1.0`。

执行 Agent 不得伪造精确到扩散步的进度。接口可以返回粗略进度，也可以根据 Worker 日志解析额外进度，但必须明确来源。

### 12.5 并发

- 全局最大并发为 1
- 新任务进入队列
- 不能在 API 进程中并行加载多个模型
- 不能同时执行多个 MPS 推理

### 12.6 取消

取消流程：

1. 更新请求状态为 `cancelled`
2. 向 Worker 进程发送 `SIGTERM`
3. 等待最多 10 秒
4. 未退出则发送 `SIGKILL`
5. 更新 `job.json`
6. 确保没有残留子进程

### 12.7 原子写入

所有 JSON 状态更新必须：

1. 写入同目录临时文件
2. `flush`
3. `os.replace`

不能让 API 读取到半个 JSON 文件。

## 13. 后端 API 设计

### 13.1 GenerationRequest

```python
class GenerationRequest(BaseModel):
    target_magnetic_density: float = Field(gt=0, le=1)
    num_candidates: int = Field(default=2, ge=1, le=16)
    guidance_scale: float = Field(default=2.0, ge=0)
    seed: int | None = None
```

### 13.2 GenerationJob

```python
class GenerationJob(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: float
    model_id: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
```

### 13.3 GeneratedCandidate

```python
class GeneratedCandidate(BaseModel):
    candidate_id: str
    material_id: str
    formula: str
    pretty_formula: str
    cif: str
    density: float | None
    formula_unit: int | None
    elements: list[str]
    source: Literal["mattergen"]
    generation_conditions: dict
    validation: dict
```

生成候选不能伪造以下值：

```text
band_gap
is_magnetic
formation_energy
magnetic_ordering
```

它们必须保持 `None`，直到有可信的预测器或 DFT 结果。

### 13.4 API 端点

```text
POST   /api/generation/jobs
GET    /api/generation/jobs/{job_id}
GET    /api/generation/jobs/{job_id}/candidates
POST   /api/generation/jobs/{job_id}/cancel
GET    /api/generation/models
```

### 13.5 API 行为

`POST /api/generation/jobs`

- 成功返回 `202`
- 立即返回 `job_id`
- 不等待推理完成
- `MATTERGEN_ENABLED=false` 返回 `503`
- 参数错误返回 `422`

`GET /api/generation/jobs/{job_id}`

- 返回任务状态和进度
- 不存在返回 `404`

`GET /api/generation/jobs/{job_id}/candidates`

- 仅任务 `completed` 时返回候选
- 非完成状态返回 `409`
- 失败任务返回错误码

`POST /api/generation/jobs/{job_id}/cancel`

- 活动任务取消后返回 `cancelled`
- 终态任务返回 `409`

`GET /api/generation/models`

首版只返回：

```json
[
  {
    "model_id": "dft_mag_density",
    "available": true,
    "conditions": ["dft_mag_density"]
  }
]
```

## 14. 候选结构转换

新增：

```text
backend/generation/evaluator.py
```

处理步骤：

1. 读取 `generated_crystals_cif.zip`
2. 按稳定顺序读取其中的 `.cif`
3. 使用 `Structure.from_str(..., fmt="cif")` 解析
4. 验证晶格矩阵和坐标是有限值
5. 验证结构至少包含一个原子
6. 提取 reduced formula
7. 提取元素种类
8. 提取密度和原子数
9. 安全尝试计算空间群
10. 生成 `GeneratedCandidate`
11. 写入 `candidates.json`
12. 单独保存每个候选 CIF

不要将 ZIP 解压到不可信路径。建议直接在内存中读取 ZIP member。

候选 ID：

```text
candidate_id = mg-{job_id}-{index:03d}
material_id  = candidate_id
```

`material_id` 不能伪装成 Materials Project ID。

## 15. LangChain Agent 集成

新增：

```text
backend/skills/material_generation.py
```

Tool 名称：

```text
material_generation
```

Tool 参数：

```python
class MaterialGenerationInput(BaseModel):
    target_magnetic_density: float
    num_candidates: int = 2
    guidance_scale: float = 2.0
    seed: int | None = None
```

Tool 行为：

1. 校验参数
2. 调用 GenerationManager 提交任务
3. 返回 JSON

返回示例：

```json
{
  "action": "generate",
  "job_id": "abc123",
  "message": "已创建磁性材料生成任务"
}
```

Tool 不得等待推理完成。

Agent 提示词必须明确：

- “查询 Nd2Fe14B”使用 `material_search`
- “把 Nd 替换成 La”使用 `element_substitution`
- “生成磁密度约 0.15 的候选材料”使用 `material_generation`
- “预测已有结构的磁密度”当前无可用预测工具，必须说明限制
- 不能用 `material_generation` 冒充属性预测

修改：

```text
backend/agent.py
backend/skills/__init__.py
backend/main.py
```

扩展：

```text
AgentResult.action = "generate"
AgentResult.job_id = "..."
ChatResponse.action = "generate"
ChatResponse.job_id = "..."
```

确保原有：

```text
action=chat
action=render
```

行为不变。

## 16. 前端集成需求

修改：

```text
frontend/src/types/material.ts
frontend/src/api/material.ts
frontend/src/composables/useAIChat.ts
frontend/src/components/chat/AIAssistant.vue
frontend/src/components/MainView.vue
```

建议新增：

```text
frontend/src/composables/useGeneration.ts
frontend/src/components/generation/GenerationPanel.vue
frontend/src/components/generation/CandidateCard.vue
```

### 16.1 类型扩展

```typescript
export type ChatAction = 'chat' | 'render' | 'generate'

export interface GenerationJob {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  error_code?: string | null
  error_message?: string | null
}

export interface GeneratedCandidate {
  candidate_id: string
  material_id: string
  formula: string
  pretty_formula: string
  cif: string
  density?: number | null
  formula_unit?: number | null
  elements: string[]
  source: 'mattergen'
  generation_conditions: Record<string, unknown>
  validation: Record<string, unknown>
}
```

### 16.2 交互流程

```text
用户在 AI 助手中请求生成
    -> /api/chat 返回 action=generate 和 job_id
    -> MainView 打开 GenerationPanel
    -> 前端轮询任务状态
    -> 完成后加载候选列表
    -> 点击候选
    -> 转换为现有 MaterialData
    -> CrystalViewer 渲染 CIF
```

轮询要求：

- 首次间隔约 1 秒
- 最大间隔约 5 秒
- 到达终态后停止
- 页面刷新后可根据 job_id 恢复轮询
- 支持取消

### 16.3 UI 要求

- 显示 `queued/running/completed/failed/cancelled`
- 显示粗略进度
- 显示目标磁密度
- 不显示未知物性为 0
- 不能显示 `band_gap=0`
- 不能将候选标为 MP 数据
- 保持现有视觉风格
- 不覆盖现有 3D 查看器
- 移动端候选列表不能遮挡主操作

## 17. 兼容性要求

### 17.1 现有 API

以下接口必须继续工作：

```text
POST /api/chat
GET  /api/material/search
POST /api/chat/clear
GET  /health
```

### 17.2 现有 Agent Tools

以下工具必须继续可用：

```text
chat
material_search
element_substitution
```

pymatgen 从 `2026.5.4` 降到 `2024.10.29` 后，必须重点测试：

```text
backend/skills/material_search.py
backend/skills/element_substitution.py
```

尤其验证：

- `MPRester.summary.search`
- `Structure.from_str`
- `structure.to(fmt="cif")`
- `site.species` 操作
- `SpacegroupAnalyzer`

### 17.3 功能开关

必须支持：

```text
MATTERGEN_ENABLED=false
```

关闭后：

- API 可以正常启动
- 不导入 MatterGen
- 不加载模型
- 不启动 Worker
- 原有功能可用
- 生成接口返回明确错误

## 18. 测试方案

### 18.1 环境测试

```bash
cd /Users/genhz/Documents/code/material-sandbox/backend

.venv/bin/python -c \
  "import sys, fastapi, langchain, pymatgen, numpy, torch, mattergen; print(sys.executable, torch.__version__)"
```

### 18.2 单元测试

必须新增：

- GenerationRequest 参数校验
- job.json 原子读写
- 状态流转测试
- Worker 命令使用 `sys.executable`
- Adapter 参数映射
- 模型路径检查
- ZIP 中 CIF 读取
- 非法 CIF 处理
- 取消逻辑
- 功能开关

单元测试不得加载真实 488 MB 模型。

### 18.3 API 测试

使用 FakeRunner 或 monkeypatch：

- POST 返回 202
- 后台任务可完成
- 状态可查询
- 候选可查询
- 任务可取消
- 不存在任务返回 404
- 未完成任务候选返回 409
- MatterGen 关闭返回 503

### 18.4 现有测试

```bash
cd /Users/genhz/Documents/code/material-sandbox/backend
.venv/bin/python -m pytest
```

必须确认原有后端测试通过。

### 18.5 前端验证

```bash
cd /Users/genhz/Documents/code/material-sandbox/frontend
npm run build
```

如果可用，使用浏览器验证：

- 聊天
- 生成任务进度
- 候选列表
- 候选 3D 展示
- 取消
- 错误状态

### 18.6 真实 MatterGen 冒烟测试

真实测试只要求验证：

1. MatterGen 可导入
2. checkpoint 可加载
3. 条件参数正确
4. MPS/CPU 设备选择正确
5. 扩散采样开始执行
6. Worker 能写入 `running`
7. 取消后无残留进程

Apple M4 上 1000 步采样可能耗时数十分钟，不要求每次测试等待完成。

已验证事实：

```text
batch_size=2
num_batches=1
target_magnetic_density=0.15
guidance_scale=2.0
record_trajectories=False
```

该配置可以成功加载模型并运行到约 `265/1000` 步。MPS 会对 `aten::index_copy.out` 回退到 CPU。

### 18.7 完整端到端测试

在可用 GPU 环境中执行：

1. 创建生成任务
2. 等待完成
3. 获取候选
4. 验证 CIF
5. 前端渲染
6. 下载文件
7. 检查错误和日志

## 19. 验收标准

以下条件全部满足才算完成：

- 使用 `backend/.venv` 作为唯一 Python 环境
- `backend/.venv` 同时包含后端和 MatterGen 依赖
- 没有重装 PyTorch
- 没有删除 MatterGen 依赖
- MatterGen 可导入
- `dft_mag_density` checkpoint 可加载
- FastAPI 启动时不会加载 MatterGen 模型
- 生成 API 立即返回 `job_id`
- Worker 使用 `sys.executable`
- 支持任务进度查询
- 支持任务取消
- 生成候选 CIF 可解析
- 前端可展示候选并渲染 3D
- 原有 API 和 Agent 工具正常
- `MATTERGEN_ENABLED=false` 可禁用新功能
- 模型权重和生成结果不提交到 Git
- 文档包含精确启动命令和测试命令
- MatterGen 子仓库来源和版本已被明确记录

## 20. 建议实施顺序

### 阶段 1：环境与基线

- 修改 `requires-python`
- 修改 `.python-version`
- 锁定后端依赖
- 增量安装到 MatterGen 环境
- 运行现有测试
- 修复 pymatgen/mp-api 兼容问题

### 阶段 2：任务基础设施

- 新增 `generation/schemas.py`
- 新增 `generation/store.py`
- 新增 `generation/manager.py`
- 使用 FakeRunner 测试状态流转

### 阶段 3：MatterGen Adapter

- 新增 `generation/adapter.py`
- 新增 `generation/worker.py`
- 实现模型预检查
- 实现 Worker 子进程
- 实现日志和错误处理

### 阶段 4：候选处理

- 新增 `generation/evaluator.py`
- 读取 ZIP
- 解析 CIF
- 生成 candidates.json
- 写入独立 CIF

### 阶段 5：后端 API

- 新增 generation routes
- 接入 `main.py`
- 添加功能开关
- 完成 API 测试

### 阶段 6：Agent

- 新增 `material_generation.py`
- 注册 Tool
- 扩展 AgentResult 和 ChatResponse
- 更新系统提示词

### 阶段 7：前端

- 扩展类型
- 新增 API 方法
- 新增 useGeneration
- 新增 GenerationPanel
- 接入 MainView 和 AIAssistant

### 阶段 8：真实测试

- MatterGen 导入和模型加载
- MPS 冒烟测试
- Worker 启动和取消
- 前端端到端测试

### 阶段 9：文档和清理

- 更新 README
- 更新 .env.example
- 更新 .gitignore
- 确认 MatterGen 内置源码路径和本地权重
- 确认无权重和 artifacts 进入 Git

## 21. Git 与文件规则

需要加入 `.gitignore`：

```text
backend/.venv/
backend/artifacts/
backend/results/
backend/vendor/mattergen/results/
backend/vendor/mattergen/mattergen.egg-info/
backend/vendor/mattergen/checkpoints/**/*.ckpt
*.ckpt.lfs-pointer
.DS_Store
```

注意：

- 不要忽略 MatterGen 源码
- 不要忽略 `config.yaml`
- 大型 checkpoint 权重不提交到父仓库
- 生成结果必须忽略
- 不提交 `.env`
- 不提交真实 API Key

## 22. 已知风险

### 22.1 Apple M4 性能

- MPS 对部分算子不支持
- `aten::index_copy.out` 会回退到 CPU
- 1000 步采样可能耗时数十分钟
- 不适合在请求线程中同步运行

### 22.2 依赖兼容

- 后端必须降到 Python 3.10 可用的 pymatgen/mp-api 版本
- 当前后端最新依赖锁定结果不可复用
- 不能重装 MatterGen 依赖

### 22.3 科学准确性

- 条件生成不等于属性预测
- 生成成功不等于目标磁密度满足
- MatterGen 仅训练至最多 20 个晶胞原子
- 不支持有机晶体、非晶体和原子序数大于 84 的元素
- 后续必须接入独立预测器或 DFT

### 22.4 内置源码

- MatterGen 已迁移到 `backend/vendor/mattergen/`
- 独立 Git 历史和 `.gitmodules` 已移除
- checkpoint 权重保留在本地并加入 `.gitignore`
- 不要重新创建外部 MatterGen 子仓库

## 23. 执行 Agent 禁止事项

执行 Agent 不得：

1. 创建新的虚拟环境。
2. 重装 PyTorch、PyG、MatterSim。
3. 删除 `backend/.venv`。
4. 将 MatterGen 迁移回根目录。
5. 在 FastAPI 请求内部执行完整扩散推理。
6. 在服务启动时加载模型。
7. 把 MatterGen 生成结果标成 Materials Project 数据。
8. 伪造磁密度、带隙、磁性等未验证属性。
9. 允许客户端提交任意模型路径。
10. 把 `dft_mag_density` 描述成属性预测模型。
11. 删除或覆盖已下载的 checkpoint。
12. 执行 Git LFS checkout 覆盖本地权重。
13. 提交 `.venv`、weights、artifacts。
14. 让生成任务无限并发。
15. 让取消操作留下僵尸 Worker。

## 24. 完成定义

当以下内容全部交付时，任务完成：

- 统一环境可用
- MatterGen Adapter 可实现真实推理
- Worker 子进程可启动、监控和取消
- 任务 API 完成
- Agent Tool 完成
- 前端进度和候选项展示完成
- 原有功能无回归
- 测试通过
- 文档完整
- Git 状态干净且不包含不应提交的生成物

执行 Agent 完成后，需要在交付说明中报告：

1. 修改的文件列表
2. 实际执行的测试命令
3. 测试结果
4. 未完成的验证项
5. 已知风险
6. 启动后端的精确命令
