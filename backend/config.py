"""
LLM 配置管理 - 从环境变量加载 LLM 配置

使用统一的环境变量名，直接修改 .env 文件中的值来切换提供商。
"""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class LLMConfig:
    """LLM 配置数据类"""
    api_key: str
    base_url: str
    model: str

    @classmethod
    def load(cls) -> "LLMConfig":
        """
        从环境变量加载 LLM 配置

        Returns:
            LLMConfig: 配置对象

        Raises:
            ValueError: 如果 API Key 缺失
        """
        api_key = os.getenv("LLM_API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", "")
        model = os.getenv("LLM_MODEL", "")

        # 验证必要配置
        if not api_key:
            raise ValueError(
                "LLM_API_KEY 未配置。请在 .env 文件中设置 LLM_API_KEY"
            )

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    def __repr__(self) -> str:
        return f"LLMConfig(model='{self.model}', base_url='{self.base_url}')"


# 全局配置实例（懒加载）
_config: Optional[LLMConfig] = None


def get_llm_config() -> LLMConfig:
    """
    获取全局 LLM 配置实例

    Returns:
        LLMConfig: 配置对象
    """
    global _config
    if _config is None:
        _config = LLMConfig.load()
    return _config


def reload_llm_config() -> LLMConfig:
    """
    重新加载 LLM 配置（用于热更新）

    Returns:
        LLMConfig: 新的配置对象
    """
    global _config
    _config = LLMConfig.load()
    return _config


@dataclass(frozen=True)
class MatterGenConfig:
    """MatterGen runtime configuration."""

    enabled: bool
    artifact_root: Path
    max_concurrency: int
    max_batch_size: int
    job_retention_days: int
    worker_timeout_seconds: int
    cuda_alloc_conf: str
    torch_matmul_precision: str

    @classmethod
    def load(cls) -> "MatterGenConfig":
        backend_root = Path(__file__).resolve().parent

        default_artifact_root = backend_root / "artifacts" / "generation"

        return cls(
            enabled=os.getenv("MATTERGEN_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"},
            artifact_root=Path(
                os.getenv("MATTERGEN_ARTIFACT_ROOT", str(default_artifact_root))
            ).expanduser().resolve(),
            max_concurrency=max(
                1, int(os.getenv("MATTERGEN_MAX_CONCURRENCY", "1"))
            ),
            max_batch_size=max(
                1, int(os.getenv("MATTERGEN_MAX_BATCH_SIZE", "8"))
            ),
            job_retention_days=max(
                1, int(os.getenv("MATTERGEN_JOB_RETENTION_DAYS", "7"))
            ),
            worker_timeout_seconds=max(
                1, int(os.getenv("MATTERGEN_WORKER_TIMEOUT_SECONDS", "14400"))
            ),
            cuda_alloc_conf=os.getenv(
                "MATTERGEN_CUDA_ALLOC_CONF",
                "expandable_segments:True",
            ),
            torch_matmul_precision=os.getenv(
                "MATTERGEN_TORCH_MATMUL_PRECISION",
                "high",
            ),
        )


@lru_cache
def get_mattergen_config() -> MatterGenConfig:
    """Load MatterGen configuration once per process."""

    return MatterGenConfig.load()


def reload_mattergen_config() -> MatterGenConfig:
    """Reload MatterGen configuration for tests and hot updates."""

    get_mattergen_config.cache_clear()
    return get_mattergen_config()
