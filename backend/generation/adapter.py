"""Adapter around the local MatterGen inference API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from config import MatterGenConfig
from generation.exceptions import GenerationError
from generation.schemas import GenerationRequest


ProgressCallback = Callable[..., None]


class MatterGenAdapter:
    """Load and run the configured MatterGen checkpoint."""

    def __init__(self, config: MatterGenConfig):
        self.config = config

    def preflight(self) -> None:
        """Validate the local runtime and checkpoint without importing PyTorch."""

        if not self.config.enabled:
            raise GenerationError(
                "MATTERGEN_DISABLED",
                "MatterGen 生成功能当前已禁用。",
                status_code=503,
            )

        if self.config.model_id != "dft_mag_density":
            raise GenerationError(
                "MODEL_NOT_ALLOWED",
                f"不支持的 MatterGen 模型：{self.config.model_id}",
                status_code=400,
            )

        model_path = self.config.model_path
        if not model_path.is_dir():
            raise GenerationError(
                "MODEL_NOT_FOUND",
                f"MatterGen 模型目录不存在：{model_path}",
                status_code=503,
            )

        config_path = model_path / "config.yaml"
        if not config_path.is_file():
            raise GenerationError(
                "CHECKPOINT_INVALID",
                f"MatterGen 模型配置不存在：{config_path}",
                status_code=503,
            )

        checkpoint_candidates = list(model_path.rglob("last.ckpt"))
        if not checkpoint_candidates:
            raise GenerationError(
                "CHECKPOINT_INVALID",
                f"MatterGen checkpoint 不存在：{model_path}",
                status_code=503,
            )

        checkpoint_path = checkpoint_candidates[0]
        if checkpoint_path.stat().st_size < 1024 * 1024:
            raise GenerationError(
                "CHECKPOINT_INVALID",
                "MatterGen checkpoint 看起来仍是 Git LFS 指针，而不是完整权重。",
                status_code=503,
            )

        with checkpoint_path.open("rb") as handle:
            prefix = handle.read(64)
        if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise GenerationError(
                "CHECKPOINT_INVALID",
                "MatterGen checkpoint 仍是 Git LFS 指针。",
                status_code=503,
            )

        if "dft_mag_density" not in config_path.read_text(encoding="utf-8"):
            raise GenerationError(
                "CHECKPOINT_INVALID",
                "模型配置不包含 dft_mag_density 条件。",
                status_code=503,
            )

    def generate(
        self,
        request: GenerationRequest,
        output_dir: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> list[Any]:
        """Generate structures and return MatterGen's pymatgen Structure list."""

        self.preflight()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from mattergen.common.utils.data_classes import MatterGenCheckpointInfo
            from mattergen.generator import CrystalGenerator
        except Exception as exc:
            raise GenerationError(
                "MATTERGEN_IMPORT_ERROR",
                f"MatterGen 导入失败：{exc}",
                status_code=503,
            ) from exc

        checkpoint_info = MatterGenCheckpointInfo(
            model_path=self.config.model_path,
            load_epoch="last",
            strict_checkpoint_loading=True,
        )

        generator = CrystalGenerator(
            checkpoint_info=checkpoint_info,
            properties_to_condition_on={
                "dft_mag_density": request.target_magnetic_density,
            },
            batch_size=request.num_candidates,
            num_batches=1,
            sampling_config_name="default",
            record_trajectories=False,
            diffusion_guidance_factor=request.guidance_scale,
            progress_callback=progress_callback,
            seed=request.seed,
        )

        try:
            return generator.generate(output_dir=output_dir)
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError(
                "GENERATION_FAILED",
                f"MatterGen 生成失败：{exc}",
                status_code=500,
            ) from exc

