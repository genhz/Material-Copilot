"""Adapter around the local MatterGen inference API."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Optional

from config import MatterGenConfig
from generation.exceptions import GenerationError
from generation.model_registry import MatterGenModelSpec
from generation.schemas import GenerationRequest


ProgressCallback = Callable[..., None]


def resolve_batch_shape(
    total_candidates: int,
    max_batch_size: int,
) -> tuple[int, int]:
    """Split a requested sample count into bounded MatterGen batches."""

    total = max(1, total_candidates)
    max_batch = max(1, max_batch_size)
    if total <= max_batch:
        return total, 1

    num_batches = math.ceil(total / max_batch)
    batch_size = math.ceil(total / num_batches)
    return batch_size, num_batches


class MatterGenAdapter:
    """Load and run the configured MatterGen checkpoint."""

    def __init__(self, config: MatterGenConfig):
        self.config = config

    def preflight(self, model_spec: MatterGenModelSpec) -> None:
        """Validate the local runtime and checkpoint without importing PyTorch."""

        if not self.config.enabled:
            raise GenerationError(
                "MATTERGEN_DISABLED",
                "MatterGen 生成功能当前已禁用。",
                status_code=503,
            )

        model_path = model_spec.checkpoint_dir
        if not model_path.is_dir():
            raise GenerationError(
                "MODEL_WEIGHTS_NOT_FOUND",
                f"{model_spec.display_name} 权重不存在，请下载到：{model_path}；"
                f"下载地址：{model_spec.download_url}",
                status_code=503,
            )

        config_path = model_path / "config.yaml"
        if not config_path.is_file():
            raise GenerationError(
                "MODEL_WEIGHTS_NOT_FOUND",
                f"{model_spec.display_name} 缺少 config.yaml：{config_path}；"
                f"下载地址：{model_spec.download_url}",
                status_code=503,
            )

        checkpoint_candidates = list(model_path.rglob("last.ckpt"))
        if not checkpoint_candidates:
            raise GenerationError(
                "MODEL_WEIGHTS_NOT_FOUND",
                f"{model_spec.display_name} 缺少 last.ckpt：{model_path}；"
                f"下载地址：{model_spec.download_url}",
                status_code=503,
            )

        checkpoint_path = checkpoint_candidates[0]
        if checkpoint_path.stat().st_size < 1024 * 1024:
            raise GenerationError(
                "MODEL_WEIGHTS_NOT_FOUND",
                f"{model_spec.display_name} 的权重仍是 Git LFS 指针，"
                f"请下载到：{model_path}；下载地址：{model_spec.download_url}",
                status_code=503,
            )

        with checkpoint_path.open("rb") as handle:
            prefix = handle.read(64)
        if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise GenerationError(
                "MODEL_WEIGHTS_NOT_FOUND",
                f"{model_spec.display_name} 的权重仍是 Git LFS 指针，"
                f"请下载到：{model_path}；下载地址：{model_spec.download_url}",
                status_code=503,
            )

    def generate(
        self,
        request: GenerationRequest,
        model_spec: MatterGenModelSpec,
        output_dir: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> list[Any]:
        """Generate structures and return MatterGen's pymatgen Structure list."""

        self.preflight(model_spec)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            import torch
            from mattergen.common.utils.data_classes import MatterGenCheckpointInfo
            from mattergen.generator import CrystalGenerator
        except Exception as exc:
            raise GenerationError(
                "MATTERGEN_IMPORT_ERROR",
                f"MatterGen 导入失败：{exc}",
                status_code=503,
            ) from exc

        torch.set_float32_matmul_precision(
            self.config.torch_matmul_precision
        )

        checkpoint_info = MatterGenCheckpointInfo(
            model_path=model_spec.checkpoint_dir,
            load_epoch="last",
            strict_checkpoint_loading=True,
        )

        guidance_scale = (
            request.guidance_scale
            if request.guidance_scale is not None
            else model_spec.default_guidance_scale
        )
        batch_size, num_batches = resolve_batch_shape(
            request.num_candidates,
            self.config.max_batch_size,
        )
        generator = CrystalGenerator(
            checkpoint_info=checkpoint_info,
            properties_to_condition_on=request.conditions,
            batch_size=batch_size,
            num_batches=num_batches,
            sampling_config_name="default",
            record_trajectories=False,
            diffusion_guidance_factor=guidance_scale,
            progress_callback=progress_callback,
            seed=request.seed,
        )

        try:
            structures = generator.generate(output_dir=output_dir)
            return structures[: request.num_candidates]
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError(
                "GENERATION_FAILED",
                f"MatterGen 生成失败：{exc}",
                status_code=500,
            ) from exc
