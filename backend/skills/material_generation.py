"""LangChain tool for starting MatterGen magnetic material generation."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from generation.exceptions import GenerationError
from generation.manager import get_generation_manager
from generation.schemas import GenerationRequest


class MaterialGenerationInput(BaseModel):
    """Input arguments accepted by the generation tool."""

    model_id: Optional[str] = Field(
        default=None,
        description="可选的内部模型 ID，通常由系统自动选择。",
    )
    conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="模型条件，例如 dft_mag_density、hhi_score、space_group。",
    )
    target_magnetic_density: Optional[float] = Field(
        default=None,
        gt=0,
        le=1,
        description="目标 DFT 磁密度，单位为每立方埃，例如 0.15。",
    )
    num_candidates: int = Field(
        default=2,
        ge=1,
        le=16,
        description="需要生成的候选结构数量。",
    )
    guidance_scale: float = Field(
        default=2.0,
        ge=0,
        le=20,
        description="条件生成引导强度。",
    )
    seed: Optional[int] = Field(
        default=None,
        description="可选的随机种子，用于可复现实验。",
    )


class MaterialGenerationTool(BaseTool):
    """Create asynchronous MatterGen generation jobs."""

    name: str = "material_generation"
    description: str = (
        "创建新材料候选生成任务。"
        "用户要求生成、设计、发现、探索或寻找尚未确定的磁性材料候选时使用。"
        "用户不需要知道 MatterGen 或任何内部模型名称。"
        "该工具只提交后台任务并返回 job_id，不等待扩散采样完成。"
        "不要把该工具用于预测已有材料的磁密度。"
        "参数包括 model_id、conditions、target_magnetic_density、"
        "num_candidates、guidance_scale 和 seed。"
    )
    args_schema: Type[BaseModel] = MaterialGenerationInput

    def _run(
        self,
        model_id: Optional[str] = None,
        conditions: Optional[dict[str, Any]] = None,
        target_magnetic_density: Optional[float] = None,
        num_candidates: int = 2,
        guidance_scale: float = 2.0,
        seed: Optional[int] = None,
    ) -> str:
        try:
            return asyncio.run(
                self._arun(
                    target_magnetic_density=target_magnetic_density,
                    model_id=model_id,
                    conditions=conditions or {},
                    num_candidates=num_candidates,
                    guidance_scale=guidance_scale,
                    seed=seed,
                )
            )
        except RuntimeError as exc:
            if "asyncio.run() cannot be called" in str(exc):
                return json.dumps(
                    {
                        "action": "chat",
                        "error": "生成工具必须在异步 Agent 上下文中调用。",
                    },
                    ensure_ascii=False,
                )
            raise

    async def _arun(
        self,
        model_id: Optional[str] = None,
        conditions: Optional[dict[str, Any]] = None,
        target_magnetic_density: Optional[float] = None,
        num_candidates: int = 2,
        guidance_scale: float = 2.0,
        seed: Optional[int] = None,
    ) -> str:
        manager = get_generation_manager()
        await manager.startup()
        request = GenerationRequest(
            model_id=model_id,
            conditions=conditions or {},
            target_magnetic_density=target_magnetic_density,
            num_candidates=num_candidates,
            guidance_scale=guidance_scale,
            seed=seed,
        )

        try:
            job = await manager.submit(request)
        except GenerationError as exc:
            return json.dumps(
                {
                    "action": "chat",
                    "error": exc.message,
                    "error_code": exc.code,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "action": "generate",
                "job_id": job.job_id,
                "status": job.status,
                "message": "已创建磁性材料生成任务，将在后台执行。",
            },
            ensure_ascii=False,
        )
