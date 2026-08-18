"""
材料结构敏捷检索与可视化沙盘 — 后端服务
FastAPI + DeepSeek Function Calling + Materials Project (mp-api)

功能：
  1. 结构化查询：通过 Function Calling 提取化学式 → mp-api 查数据 → 返回 CIF + 属性
  2. 通用问答：非结构化材料科学问题 → 直接调用 DeepSeek 生成回答
  3. 多轮对话：后端维护会话历史，支持上下文追问
"""

import os
import json
import logging
import uuid
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv

from mp_api.client import MPRester

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── FastAPI 应用 ──────────────────────────────────────────────
app = FastAPI(title="材料结构检索沙盘", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DeepSeek 客户端 ───────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

# ── Function Calling 工具定义 ──────────────────────────────────
# 两个工具：结构化查询 + 通用问答
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_material",
            "description": (
                "查询特定材料的晶体结构、物性数据（带隙、磁性、形成能等）。"
                "当用户明确询问某个具体化学式的结构或物性时使用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "formula": {
                        "type": "string",
                        "description": (
                            "化学式，例如 Nd2Fe14B, Fe3O4, LiCoO2, SiO2"
                        ),
                    },
                },
                "required": ["formula"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer_general",
            "description": (
                "回答材料科学领域的通用问题，不需要查询具体材料的结构数据。"
                "当用户的问题涉及材料科学概念、替代方案、趋势分析、比较等时使用此工具。"
                "例如：'钕铁硼能用镧系元素替代吗？'、'什么是带隙？'、'哪些材料适合做永磁体？'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用户的原始问题",
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "上下文信息，如之前讨论过的材料名称。如果没有则为空字符串。"
                        ),
                    },
                },
                "required": ["question"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "你是一个专业的材料信息学助手，专注于材料科学领域的知识问答和数据分析。"
    "你具备以下能力：\n\n"
    "1. **结构化查询**：当用户询问某个具体化学式的晶体结构、带隙、磁性、形成能等物性数据时，"
    "使用 search_material 工具查询 Materials Project 数据库。\n\n"
    "2. **通用问答**：当用户的问题涉及材料科学概念、替代方案、趋势分析、比较等，"
    "不针对某个具体化学式的结构数据时，使用 answer_general 工具。\n\n"
    "3. **上下文理解**：用户可能会在对话中追问（例如先问了 Nd2Fe14B，接着问'那 Fe3O4 呢？'），"
    "你需要理解上下文，正确提取化学式。\n\n"
    "回答规则：\n"
    "- 使用简洁、专业的中文回答\n"
    "- 带隙为 0 或极小时，说明材料可能是金属导体\n"
    "- is_magnetic 为 true 时，说明材料具有磁性\n"
    "- formation_energy_per_atom 越负，结构越稳定\n"
    "- 回答要重点突出关键数据，保持结构化"
)

# ── 请求 / 响应模型 ──────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # 会话 ID，用于多轮对话


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
    elements: Optional[List[str]] = None
    pretty_formula: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    material_data: Optional[MaterialData] = None
    session_id: Optional[str] = None


# ── 会话历史存储（内存） ──────────────────────────────────────
# 实际生产环境应使用 Redis 等持久化存储
session_histories: dict[str, list[dict]] = {}

MAX_HISTORY_LENGTH = 20  # 每次请求最多携带最近 20 条消息


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
    """
    添加消息到历史。
    注意：只保存 user 和 assistant 的最终回复，不保存 tool 消息，
    因为 tool 消息必须对应 tool_call，而 tool_call 是每次请求重新生成的。
    """
    if session_id not in session_histories:
        session_histories[session_id] = []
    # 只保存 user 和 assistant 的最终回复
    if role in ("user", "assistant"):
        session_histories[session_id].append({"role": role, "content": content})


# ── Materials Project 查询函数 ─────────────────────────────────
def search_material_from_mp(formula: str) -> MaterialData:
    """
    通过 mp-api 查询材料数据，返回 formation_energy_per_atom 最低的最稳定结构。
    """
    mp_api_key = os.getenv("MP_API_KEY", "")
    if not mp_api_key:
        raise RuntimeError(
            "MP_API_KEY 未配置。请在 .env 文件中设置你的 Materials Project API Key。"
        )

    with MPRester(api_key=mp_api_key) as mpr:
        docs = mpr.summary.search(
            formula=formula,
            fields=[
                "material_id",
                "structure",
                "band_gap",
                "is_magnetic",
                "formation_energy_per_atom",
                "density",
                "symmetry",  # Contains spacegroup info
                "elements",
                "formula_pretty",
            ],
        )

    if not docs:
        raise ValueError(
            f"在 Materials Project 中未找到化学式为 '{formula}' 的材料。"
        )

    # 取 formation_energy_per_atom 最低的最稳定结构
    best_doc = sorted(docs, key=lambda x: x.formation_energy_per_atom or 0)[0]

    cif_str = best_doc.structure.to(fmt="cif")

    # 安全获取 symmetry (spacegroup) 信息
    spacegroup_symbol = None
    spacegroup_number = None
    crystal_system = None
    if hasattr(best_doc, 'symmetry') and best_doc.symmetry:
        spacegroup_symbol = getattr(best_doc.symmetry, 'symbol', None)
        spacegroup_number = getattr(best_doc.symmetry, 'number', None)
        crystal_system = getattr(best_doc.symmetry, 'crystal_system', None)

    # 构建磁性有序标签
    magnetic_ordering = None
    if best_doc.is_magnetic:
        ordering = getattr(best_doc, 'ordering', None)
        magnetic_ordering = ordering or "FM"

    # 转换 elements 为字符串列表
    elements_raw = getattr(best_doc, 'elements', None)
    elements_list = [str(elem) for elem in elements_raw] if elements_raw else None

    material_data = MaterialData(
        formula=formula,
        material_id=getattr(best_doc, 'material_id', 'unknown') or 'unknown',
        band_gap=getattr(best_doc, 'band_gap', None),
        is_magnetic=getattr(best_doc, 'is_magnetic', None),
        formation_energy=getattr(best_doc, 'formation_energy_per_atom', None),
        cif=cif_str,
        density=getattr(best_doc, 'density', None),
        spacegroup_symbol=spacegroup_symbol,
        spacegroup_number=spacegroup_number,
        crystal_system=crystal_system,
        formula_unit=getattr(best_doc, 'nsites', None),
        magnetic_ordering=magnetic_ordering,
        elements=elements_list,
        pretty_formula=getattr(best_doc, 'formula_pretty', None),
    )

    # 调试输出：确认后端发出的数据
    print(f"[DEBUG] Material data returned: {material_data.model_dump()}")
    return material_data


# ── 路由 ──────────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    主聊天接口。整合 DeepSeek Function Calling 与 Materials Project 查询。
    支持多轮对话，通过 session_id 维持上下文。
    """
    # 获取或创建会话
    session_id = get_or_create_session(request.session_id)

    try:
        # ── 构建消息列表：system + 历史 + 当前 ──
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # 添加历史消息
        history = get_recent_messages(session_id)
        messages.extend(history)

        # 添加当前用户消息
        messages.append({"role": "user", "content": request.message})

        # ── 第 1 轮：让 DeepSeek 判断是否需要调用工具 ──
        first_response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=TOOLS,
        )

        assistant_msg = first_response.choices[0].message

        # 保存用户消息到历史
        add_to_history(session_id, "user", request.message)

        # 检查是否触发了 function calling
        if assistant_msg.tool_calls:
            tool_call = assistant_msg.tool_calls[0]
            tool_name = tool_call.function.name

            # 将 assistant 的 tool_call 消息添加到 messages 中
            # 这样后面的 tool 消息才有对应的 tool_call_id
            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }],
            })

            if tool_name == "search_material":
                # ── 结构化查询：调用 Materials Project ──
                args = json.loads(tool_call.function.arguments)
                formula = args.get("formula", "")

                logger.info(f"Function Calling 触发：search_material(formula='{formula}')")

                material_data = search_material_from_mp(formula)

                # 将查询结果喂回 DeepSeek 生成最终回复
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            {
                                "formula": material_data.formula,
                                "material_id": material_data.material_id,
                                "band_gap": material_data.band_gap,
                                "is_magnetic": material_data.is_magnetic,
                                "formation_energy_per_atom": material_data.formation_energy,
                            }
                        ),
                    }
                )

                final_response = await deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                )

                reply = final_response.choices[0].message.content

                # 保存最终回复到历史
                add_to_history(session_id, "assistant", reply)

                return ChatResponse(
                    reply=reply,
                    material_data=material_data,
                    session_id=session_id,
                )

            elif tool_name == "answer_general":
                # ── 通用问答：直接让 DeepSeek 回答 ──
                args = json.loads(tool_call.function.arguments)
                question = args.get("question", request.message)
                context = args.get("context", "")

                logger.info(f"Function Calling 触发：answer_general(question='{question[:50]}...')")

                # 将问题喂回，让模型直接回答
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            f"用户问题：{question}\n"
                            f"上下文：{context}\n\n"
                            "请用专业的材料科学知识回答用户的问题。"
                        ),
                    }
                )

                final_response = await deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                )

                reply = final_response.choices[0].message.content

                # 保存最终回复到历史
                add_to_history(session_id, "assistant", reply)

                return ChatResponse(
                    reply=reply,
                    material_data=None,
                    session_id=session_id,
                )
            else:
                # 未知工具
                reply = f"抱歉，我不太理解你的问题。请尝试询问具体材料的化学式或材料科学问题。"
                add_to_history(session_id, "assistant", reply)
                return ChatResponse(
                    reply=reply,
                    material_data=None,
                    session_id=session_id,
                )
        else:
            # 没有触发工具调用，直接返回
            reply = assistant_msg.content or "抱歉，我没有收到回复。"
            add_to_history(session_id, "assistant", reply)
            return ChatResponse(
                reply=reply,
                material_data=None,
                session_id=session_id,
            )

    except ValueError as ve:
        logger.warning(f"查询异常：{ve}")
        error_reply = f"查询失败：{ve}"
        add_to_history(session_id, "assistant", error_reply)
        return ChatResponse(
            reply=error_reply,
            material_data=None,
            session_id=session_id,
        )
    except RuntimeError as re:
        logger.error(f"配置异常：{re}")
        error_reply = f"服务器配置错误：{re}"
        add_to_history(session_id, "assistant", error_reply)
        return ChatResponse(
            reply=error_reply,
            material_data=None,
            session_id=session_id,
        )
    except Exception as e:
        logger.exception(f"未知错误：{e}")
        error_reply = f"发生未知错误：{e}"
        add_to_history(session_id, "assistant", error_reply)
        return ChatResponse(
            reply=error_reply,
            material_data=None,
            session_id=session_id,
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── 直接材料搜索接口（不调用大模型）─────────────────────────────────────
@app.get("/api/material/search", response_model=MaterialData)
async def direct_material_search(formula: str):
    """
    直接通过 Materials Project API 查询材料数据。
    不使用大模型，仅返回结构化数据。
    """
    try:
        material_data = search_material_from_mp(formula)
        return material_data
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
