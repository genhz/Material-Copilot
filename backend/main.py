"""
材料结构敏捷检索与可视化沙盘 - 后端服务
基于 LangChain Agent 架构

架构：
  LangChain Agent (自动意图识别 + 工具调用)
    ├─ MaterialSearchTool (查询晶体结构)
    └─ ChatTool (材料科学问答)
"""

import os
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parent / "artifacts" / "matplotlib"),
)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from agent import execute_agent, AgentResult
from generation.manager import get_generation_manager
from generation.router import router as generation_router
from skills.material_search import MaterialSearchResult

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize and clean up generation workers."""

    manager = get_generation_manager()
    await manager.startup()
    try:
        yield
    finally:
        await manager.shutdown()


# ── FastAPI 应用 ──────────────────────────────────────────────
app = FastAPI(
    title="材料结构检索沙盘 (LangChain Agent 版)",
    version="1.1.0",
    lifespan=lifespan,
)

app.include_router(generation_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 请求 / 响应模型 ──────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class MaterialData(BaseModel):
    formula: str
    material_id: str
    band_gap: Optional[float] = None
    is_magnetic: Optional[bool] = None
    formation_energy: Optional[float] = None
    cif: str
    # Extended properties
    density: Optional[float] = None
    spacegroup_symbol: Optional[str] = None
    spacegroup_number: Optional[int] = None
    crystal_system: Optional[str] = None
    formula_unit: Optional[int] = None
    magnetic_ordering: Optional[str] = None
    elements: Optional[list[str]] = None
    pretty_formula: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    action: str  # "chat" | "render" | "generate"
    material_data: Optional[MaterialData] = None
    job_id: Optional[str] = None
    session_id: Optional[str] = None


# ── 会话历史存储（内存） ──────────────────────────────────────
session_histories: dict[str, list[dict]] = {}

MAX_HISTORY_LENGTH = 20


def get_or_create_session(session_id: Optional[str]) -> str:
    """获取或创建会话 ID"""
    if session_id and session_id in session_histories:
        return session_id
    new_id = str(uuid.uuid4())[:8]
    session_histories[new_id] = []
    return new_id


def get_recent_messages(session_id: str) -> list[dict]:
    """获取最近的消息历史"""
    history = session_histories.get(session_id, [])
    return history[-MAX_HISTORY_LENGTH:]


def add_to_history(session_id: str, role: str, content: str):
    """添加消息到历史"""
    if session_id not in session_histories:
        session_histories[session_id] = []
    if role in ("user", "assistant"):
        session_histories[session_id].append({"role": role, "content": content})


# ── 路由 ──────────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    主聊天接口 — LangChain Agent 架构

    流程：
    1. LangChain Agent 自动判断用户意图
    2. Agent 决定调用哪个工具（chat 或 material_search）
    3. 返回包含 action 字段的响应，前端据此决定 UI 行为
    """
    session_id = get_or_create_session(request.session_id)

    try:
        # 获取历史消息
        history = get_recent_messages(session_id)

        # 添加当前用户消息到历史
        add_to_history(session_id, "user", request.message)

        # ── 执行 LangChain Agent ──
        result = await execute_agent(
            message=request.message,
            history=history,
        )

        # 保存 AI 回复到历史
        add_to_history(session_id, "assistant", result.reply)

        # 构建响应
        material_data = None
        if result.material_data:
            material_data = MaterialData(
                formula=result.material_data.formula,
                material_id=result.material_data.material_id,
                band_gap=result.material_data.band_gap,
                is_magnetic=result.material_data.is_magnetic,
                formation_energy=result.material_data.formation_energy,
                cif=result.material_data.cif,
                density=result.material_data.density,
                spacegroup_symbol=result.material_data.spacegroup_symbol,
                spacegroup_number=result.material_data.spacegroup_number,
                crystal_system=result.material_data.crystal_system,
                formula_unit=result.material_data.formula_unit,
                magnetic_ordering=result.material_data.magnetic_ordering,
                elements=result.material_data.elements,
                pretty_formula=result.material_data.pretty_formula,
            )

        logger.info(f"[API] 响应：action={result.action}, formula={result.material_data.formula if result.material_data else 'N/A'}")

        return ChatResponse(
            reply=result.reply,
            action=result.action,
            material_data=material_data,
            job_id=result.job_id,
            session_id=session_id,
        )

    except Exception as e:
        logger.exception(f"[API] 未知错误：{e}")
        error_reply = f"发生未知错误：{e}"
        add_to_history(session_id, "assistant", error_reply)
        return ChatResponse(
            reply=error_reply,
            action="chat",
            material_data=None,
            job_id=None,
            session_id=session_id,
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/material/search", response_model=MaterialData)
async def direct_material_search(formula: str):
    """
    直接通过 Materials Project API 查询材料数据（不走 Agent）。
    用于前端直接调用搜索功能。
    """
    from skills.material_search import MaterialSearchTool

    tool = MaterialSearchTool()
    try:
        result_json = tool._run(formula)
        result_dict = json.loads(result_json)
        return MaterialData(**result_dict)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=500, detail=str(re))


@app.post("/api/chat/clear")
async def clear_session(session_id: str):
    """清除会话历史"""
    if session_id in session_histories:
        del session_histories[session_id]
    return {"status": "cleared"}
